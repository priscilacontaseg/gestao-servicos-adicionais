"""Sobe o FastAPI (backend/app/main.py) como thread em segundo plano, dentro
do MESMO processo Python do Streamlit.

Por que isso existe: o Streamlit Community Cloud roda um unico processo por
app (so `streamlit run <arquivo>`), sem suporte a subir um segundo servico
lado a lado. Em vez de reescrever o frontend pra chamar as funcoes do
backend diretamente (o que jogaria fora toda a validacao/schemas do FastAPI),
a solucao mais simples e stable e nascer o uvicorn numa thread daemon dentro
do processo do proprio Streamlit, e o frontend continua chamando
http://localhost:8000 normalmente via httpx - exatamente como ja fazia.

Local/dev: se voce ja tem o backend rodando manualmente (uvicorn separado,
como nos scripts de preview), este modulo detecta a porta ocupada e nao
sobe nada - sem conflito entre os dois jeitos de rodar.
"""

import socket
import sys
import threading
import time
from pathlib import Path

_LOCK = threading.Lock()
_PORTA_PADRAO = 8000


def _porta_em_uso(porta: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, porta)) == 0


def garantir_backend_rodando(porta: int = _PORTA_PADRAO, timeout_segundos: float = 15.0) -> bool:
    """Garante que algo esteja escutando em localhost:porta - o backend
    embutido, se ainda nao tiver nada, ou o que ja estiver rodando (dev
    manual). Retorna True se ficou disponivel dentro do timeout."""
    with _LOCK:
        if not _porta_em_uso(porta):
            backend_dir = Path(__file__).resolve().parent.parent / "backend"
            if str(backend_dir) not in sys.path:
                sys.path.insert(0, str(backend_dir))

            from app.main import app as fastapi_app  # import local, precisa do sys.path acima

            import uvicorn

            def _rodar() -> None:
                uvicorn.run(fastapi_app, host="127.0.0.1", port=porta, log_level="warning")

            threading.Thread(target=_rodar, daemon=True, name="fastapi-embutido").start()

    limite = time.monotonic() + timeout_segundos
    while time.monotonic() < limite:
        if _porta_em_uso(porta):
            return True
        time.sleep(0.3)
    return False
