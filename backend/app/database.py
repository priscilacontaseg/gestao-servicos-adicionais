import os

from dotenv import load_dotenv
from sqlmodel import Session, SQLModel, create_engine

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://usuario:senha@localhost:5432/gestao_servicos_adicionais",
)

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,  # evita erro de "conexao fechada" em Postgres gerenciado (Neon/Supabase/Railway)
)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
