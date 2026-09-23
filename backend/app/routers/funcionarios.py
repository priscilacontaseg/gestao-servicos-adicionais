"""Endpoint de leitura minimo, necessario para o frontend saber quem
selecionar como operador/coordenador logado (nao ha sistema de autenticacao
de verdade ainda - isso e um passo pendente, nao coberto neste escopo).

IMPORTANTE: sempre usar FuncionarioPublico como response_model aqui - o
model Funcionario (tabela) carrega senha_hash, e nunca pode ser serializado
direto numa resposta de API."""

from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..database import get_session
from ..models import CargoFuncionario, Funcionario
from ..schemas import FuncionarioPublico

router = APIRouter(prefix="/funcionarios", tags=["funcionarios"])


@router.get("", response_model=List[FuncionarioPublico])
def listar_funcionarios(
    cargo: Optional[CargoFuncionario] = None,
    session: Session = Depends(get_session),
):
    query = select(Funcionario).where(Funcionario.ativo == True)  # noqa: E712
    if cargo:
        query = query.where(Funcionario.cargo == cargo)
    return session.exec(query).all()
