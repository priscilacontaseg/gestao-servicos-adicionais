from datetime import datetime
from typing import Optional

from sqlalchemy import Column, LargeBinary
from sqlmodel import Field, SQLModel

from ..timeutils import agora_utc


class AnexoProposta(SQLModel, table=True):
    """Provas de aviso previo (prints de WhatsApp antigo, e-mails, notificacoes)
    anexadas na pericia tecnica. O binario fica gravado direto no Postgres
    (coluna bytea) - decisao deliberada: valor de prova em caso de contestacao
    da cobranca importa mais aqui do que a eficiencia de guardar em disco/S3,
    e assim o anexo persiste no mesmo backup do resto dos dados da proposta."""

    __tablename__ = "anexos_proposta"

    id: Optional[int] = Field(default=None, primary_key=True)
    proposta_id: int = Field(foreign_key="propostas.id", index=True)

    nome_arquivo: str
    tipo_mime: str
    tamanho_bytes: int
    conteudo: bytes = Field(sa_column=Column(LargeBinary, nullable=False))

    enviado_por_id: int = Field(foreign_key="funcionarios.id")
    enviado_em: datetime = Field(default_factory=agora_utc)
