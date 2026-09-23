from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

from ..timeutils import agora_utc


class Cliente(SQLModel, table=True):
    __tablename__ = "clientes"

    id: Optional[int] = Field(default=None, primary_key=True)
    cnpj: str = Field(unique=True, index=True)
    razao_social: str
    nome_contato: Optional[str] = None

    opt_in_whatsapp: bool = Field(default=False)
    opt_in_registrado_em: Optional[datetime] = None

    ativo: bool = Field(default=True)
    criado_em: datetime = Field(default_factory=agora_utc)
