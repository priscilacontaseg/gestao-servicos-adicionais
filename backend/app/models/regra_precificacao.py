from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel

from ..timeutils import agora_utc
from .enums import RegimeTributario


class RegraPrecificacao(SQLModel, table=True):
    """Tabela de precos oficial, versionada por regime tributario. Cada
    proposta referencia a regra usada no calculo (Proposta.regra_precificacao_id),
    preservando o historico mesmo se os valores mudarem no futuro.

    O preco final tambem sofre multiplicadores de reincidencia (este campo,
    aplicado quando ha anexo de prova) e de complexidade do caso (constante
    fixa em app/pricing.py, nao versionada aqui)."""

    __tablename__ = "regras_precificacao"

    id: Optional[int] = Field(default=None, primary_key=True)

    regime_tributario: RegimeTributario = Field(index=True)
    valor_base_competencia: float
    multiplicador_reincidencia: float = Field(default=1.5)

    vigente_de: date
    vigente_ate: Optional[date] = None
    ativo: bool = Field(default=True)

    criado_em: datetime = Field(default_factory=agora_utc)
