from fastapi import FastAPI

from .database import create_db_and_tables
from .routers import funcionarios, propostas

app = FastAPI(title="Gestao de Servicos Adicionais")


@app.on_event("startup")
def on_startup() -> None:
    create_db_and_tables()


app.include_router(propostas.router)
app.include_router(funcionarios.router)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
