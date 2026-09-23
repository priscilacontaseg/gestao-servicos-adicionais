"""Integracao com a API REST classica do Trello (api.trello.com/1/...).

Um unico cartao por proposta, criado uma vez quando ela entra em
aguardando_resposta, na lista fixa configurada (TRELLO_LIST_ID). Dali em
diante o cartao NUNCA muda de lista - aceite/recusa/duvida viram apenas
comentarios (e membros) no mesmo cartao, porque e assim que o time usa esse
board hoje (uma unica coluna de malha fiscal).

Sem TRELLO_API_KEY/TRELLO_API_TOKEN configurados (.env), as funcoes fazem
no-op e retornam None, para nao travar o uso local/dev sem credenciais reais.
"""

import os
from typing import Optional

import httpx

TRELLO_API_KEY = os.getenv("TRELLO_API_KEY", "")
TRELLO_API_TOKEN = os.getenv("TRELLO_API_TOKEN", "")
TRELLO_LIST_ID = os.getenv("TRELLO_LIST_ID", "")

TRELLO_BASE_URL = "https://api.trello.com/1"


def configurado() -> bool:
    return bool(TRELLO_API_KEY and TRELLO_API_TOKEN and TRELLO_LIST_ID)


def _auth_params() -> dict:
    return {"key": TRELLO_API_KEY, "token": TRELLO_API_TOKEN}


def criar_cartao(
    nome: str,
    descricao: str,
    membros_ids: Optional[list] = None,
    due: Optional[str] = None,
) -> Optional[dict]:
    """Cria o cartao na lista fixa. Retorna {'id', 'url'} ou None se o Trello
    nao estiver configurado (modo local/dev sem credenciais).

    due: data-limite em ISO 8601 (ex: "2026-09-25T16:36:00.000Z"). Politica da
    empresa: todo cartao tem que ter data e responsavel - nunca criar sem."""
    if not configurado():
        return None

    payload = {
        **_auth_params(),
        "idList": TRELLO_LIST_ID,
        "name": nome,
        "desc": descricao,
    }
    if membros_ids:
        payload["idMembers"] = ",".join(m for m in membros_ids if m)
    if due:
        payload["due"] = due

    resp = httpx.post(f"{TRELLO_BASE_URL}/cards", params=payload, timeout=15.0)
    resp.raise_for_status()
    dados = resp.json()
    return {"id": dados["id"], "url": dados["shortUrl"]}


def adicionar_comentario(card_id: str, texto: str) -> None:
    if not configurado():
        return
    resp = httpx.post(
        f"{TRELLO_BASE_URL}/cards/{card_id}/actions/comments",
        params={**_auth_params(), "text": texto},
        timeout=15.0,
    )
    resp.raise_for_status()


def adicionar_membro(card_id: str, membro_id: str) -> None:
    if not configurado() or not membro_id:
        return
    resp = httpx.post(
        f"{TRELLO_BASE_URL}/cards/{card_id}/idMembers",
        params={**_auth_params(), "value": membro_id},
        timeout=15.0,
    )
    resp.raise_for_status()
