from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

from ..timeutils import agora_utc
from .enums import CargoFuncionario, Setor


class Funcionario(SQLModel, table=True):
    __tablename__ = "funcionarios"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str
    email: str = Field(unique=True, index=True)
    cargo: CargoFuncionario

    # Coordenadores e operadores pertencem a um setor. Financeiro (Ana Paula) e
    # gestores atuam entre setores, por isso o campo eh opcional.
    setor: Optional[Setor] = Field(default=None, index=True)

    # Member ID do Trello (idMembers, para adicionar como membro do cartao) e
    # username do Trello (para @mencao real no texto do comentario - o Trello
    # so cria o link/notificacao de mencao pelo @username, nao pelo ID nem
    # pelo nome completo). A criacao do cartao usa uma conta de servico unica,
    # nao o token individual do funcionario.
    trello_member_id: Optional[str] = Field(default=None)
    trello_username: Optional[str] = Field(default=None)

    # Senha de assinatura eletronica (hash SHA-256, nunca texto puro - ver
    # security.py). So coordenadores/gestores que aprovam valor precisam
    # dela; demais cargos ficam com None. NUNCA incluir este campo em
    # response_model nenhum - usar FuncionarioPublico para qualquer retorno
    # de API.
    senha_hash: Optional[str] = Field(default=None)

    ativo: bool = Field(default=True)
    criado_em: datetime = Field(default_factory=agora_utc)
