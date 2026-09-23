from typing import Optional

from sqlmodel import SQLModel

from .models import CargoFuncionario, RespostaCliente, Setor


class SolicitarRevisaoIn(SQLModel):
    motivo: str


class AprovarValorIn(SQLModel):
    funcionario_id: int
    valor_final: float
    motivo_ajuste: str
    senha: str


class RegistrarRespostaIn(SQLModel):
    resposta: RespostaCliente


class PropostaResumo(SQLModel):
    id: int
    numero_proposta: str
    razao_social: str
    cnpj: str
    setor: str
    valor_final: Optional[float]
    status: str
    data_envio: Optional[str]


class FuncionarioPublico(SQLModel):
    """Espelha Funcionario SEM senha_hash - unico schema que a API pode usar
    para retornar dados de funcionario. Nunca usar o model Funcionario direto
    como response_model."""

    id: int
    nome: str
    email: str
    cargo: CargoFuncionario
    setor: Optional[Setor]
    ativo: bool


class AnexoResumo(SQLModel):
    id: int
    nome_arquivo: str
    tipo_mime: str
    tamanho_bytes: int
