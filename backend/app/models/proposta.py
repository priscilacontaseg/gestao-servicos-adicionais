from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from ..timeutils import agora_utc
from .enums import (
    ComplexidadeCaso,
    PorteEmpresa,
    RegimeTributario,
    RespostaCliente,
    Setor,
    StatusProposta,
)


class Proposta(SQLModel, table=True):
    __tablename__ = "propostas"

    id: Optional[int] = Field(default=None, primary_key=True)
    numero_proposta: str = Field(unique=True, index=True)

    cliente_id: int = Field(foreign_key="clientes.id", index=True)
    operador_id: int = Field(foreign_key="funcionarios.id", index=True)
    setor: Setor = Field(index=True)

    # Pericia tecnica (dados que o operador alimenta na tela do Streamlit)
    porte_empresa: PorteEmpresa  # informativo - nao entra na formula de preco
    complexidade: ComplexidadeCaso  # o que de fato multiplica o preco
    regime_tributario: RegimeTributario
    qtd_competencias: int
    competencias: List[str] = Field(sa_column=Column(JSON))
    descricao_inconsistencia: str

    # Veredito do motor de regras (Passo 3 - "Analisar Caso")
    regra_precificacao_id: Optional[int] = Field(
        default=None, foreign_key="regras_precificacao.id"
    )
    classificacao: Optional[str] = None
    justificativa: Optional[str] = None
    diagnostico_texto: Optional[str] = None
    valor_sugerido: Optional[float] = None

    # Governanca de ajuste de valor: o operador nunca edita o valor. Se ele
    # discordar do veredito, a proposta vai para aguardando_aprovacao_valor e
    # somente o coordenador do setor (ou gestor) pode ajustar, com justificativa
    # obrigatoria. Sem ajuste, valor_final == valor_sugerido.
    valor_final: Optional[float] = None
    motivo_solicitacao_revisao: Optional[str] = None
    ajustado_por_id: Optional[int] = Field(
        default=None, foreign_key="funcionarios.id"
    )
    motivo_ajuste: Optional[str] = None
    ajustado_em: Optional[datetime] = None

    # Negociacao manual (WhatsApp conversacional, sem API) e baixa manual
    status: StatusProposta = Field(default=StatusProposta.RASCUNHO, index=True)
    prazo_fiscal: Optional[date] = None
    data_envio: Optional[datetime] = None  # quando entrou em aguardando_resposta
    data_resposta: Optional[datetime] = None
    resposta: Optional[RespostaCliente] = None

    # Trello - cartao criado assim que a proposta entra em aguardando_resposta;
    # dali em diante so recebe comentarios/membros, nunca muda de lista.
    trello_card_id: Optional[str] = None
    trello_card_url: Optional[str] = None

    criado_em: datetime = Field(default_factory=agora_utc)
    atualizado_em: datetime = Field(default_factory=agora_utc)
