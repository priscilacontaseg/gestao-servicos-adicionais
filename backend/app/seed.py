"""Popula dados de referencia: tabela oficial de precos e um conjunto
minimo de funcionarios (coordenadores por setor + financeiro + 1 operador
de testes, ja que ainda nao ha tela de cadastro nem autenticacao).

Uso: python -m app.seed  (executar de dentro de backend/, com o venv ativo)
Idempotente: roda quantas vezes precisar - cria quem falta e atualiza os
dados do Trello de quem ja existe (util quando o mapeamento for corrigido).
"""

import os
from datetime import date
from typing import Optional

from sqlmodel import Session, select

from .database import create_db_and_tables, engine
from .models import CargoFuncionario, Funcionario, RegimeTributario, RegraPrecificacao, Setor
from .security import hash_senha

# Senhas iniciais NUNCA ficam no codigo-fonte (isso e publico no GitHub) - vem
# de variavel de ambiente, so na hora de rodar o seed. Se nao for definida,
# o funcionario fica sem senha (nao consegue aprovar nada ate alguem definir).
SENHA_INICIAL_MARLI = os.getenv("SEED_SENHA_MARLI")
SENHA_INICIAL_GUSTAVO = os.getenv("SEED_SENHA_GUSTAVO")

# Tabela oficial de precos por competencia (confirmada por Felipe em 2026-09-22).
# Reincidencia (anexo de prova) multiplica por 1.5x obrigatoriamente.
REGRAS_OFICIAIS = [
    (RegimeTributario.SIMPLES_NACIONAL, 50.0),
    (RegimeTributario.LUCRO_PRESUMIDO, 75.0),
    (RegimeTributario.LUCRO_REAL, 100.0),
]

# Coordenadores reais + financeiro, com usuario/ID do Trello real do board
# CONTABILIDADE/FISCAL/DP (consultados em 2026-09-22 via conector Trello).
# trello_username -> usado para @mencao no texto do comentario.
# trello_member_id -> usado para adicionar como membro do cartao (idMembers).
FUNCIONARIOS_INICIAIS = [
    dict(
        nome="Marli", email="marli@contaseg.com.br",
        cargo=CargoFuncionario.COORDENADOR, setor=Setor.FISCAL,
        trello_username="coordenacaofiscalmarli", trello_member_id="64908b0bbed5ad37c1eebe02",
        senha_hash=hash_senha(SENHA_INICIAL_MARLI) if SENHA_INICIAL_MARLI else None,
    ),
    dict(
        nome="Gustavo", email="gustavo@contaseg.com.br",
        cargo=CargoFuncionario.COORDENADOR, setor=Setor.SIMPLES_NACIONAL,
        trello_username="gustavofiscal", trello_member_id="62d54dceb08d7831ac76c711",
        senha_hash=hash_senha(SENHA_INICIAL_GUSTAVO) if SENHA_INICIAL_GUSTAVO else None,
    ),
    dict(
        nome="Daniel", email="daniel@contaseg.com.br",
        cargo=CargoFuncionario.COORDENADOR, setor=Setor.PESSOAL,
        trello_username="danielpcima", trello_member_id="5d39d7028b9b5b62521ced10",
        senha_hash=None,  # sem senha definida ainda - nao consegue aprovar ate ter uma
    ),
    dict(
        nome="Regina", email="regina@contaseg.com.br",
        cargo=CargoFuncionario.COORDENADOR, setor=Setor.CONTABIL,
        trello_username="coordenacaoctb", trello_member_id="618bc3437d59c16175d5686e",
        senha_hash=None,
    ),
    dict(
        nome="Ana Paula", email="anapaula@contaseg.com.br",
        cargo=CargoFuncionario.FINANCEIRO, setor=None,
        trello_username="anapaula02452042", trello_member_id="5ee8dc760882127052ca1305",
        senha_hash=None,
    ),
    dict(
        nome="Operador de Testes", email="operador.teste@contaseg.com.br",
        cargo=CargoFuncionario.OPERADOR, setor=None,
        trello_username=None, trello_member_id=None,
        senha_hash=None,
    ),
]


def seed_regras_precificacao(session: Session) -> None:
    for regime, valor_base in REGRAS_OFICIAIS:
        ja_existe = session.exec(
            select(RegraPrecificacao).where(
                RegraPrecificacao.regime_tributario == regime,
                RegraPrecificacao.ativo == True,  # noqa: E712
            )
        ).first()
        if ja_existe:
            continue
        session.add(
            RegraPrecificacao(
                regime_tributario=regime,
                valor_base_competencia=valor_base,
                multiplicador_reincidencia=1.5,
                vigente_de=date(2026, 1, 1),
                ativo=True,
            )
        )
    session.commit()


def seed_funcionarios(session: Session) -> None:
    for dados in FUNCIONARIOS_INICIAIS:
        existente: Optional[Funcionario] = session.exec(
            select(Funcionario).where(Funcionario.email == dados["email"])
        ).first()
        if existente:
            existente.trello_username = dados["trello_username"]
            existente.trello_member_id = dados["trello_member_id"]
            if dados["senha_hash"] is not None:
                existente.senha_hash = dados["senha_hash"]
            session.add(existente)
        else:
            session.add(Funcionario(**dados, ativo=True))
    session.commit()


def main() -> None:
    create_db_and_tables()
    with Session(engine) as session:
        seed_regras_precificacao(session)
        seed_funcionarios(session)
    print("Seed concluido: regras_precificacao e funcionarios populados/atualizados.")
    if not SENHA_INICIAL_MARLI or not SENHA_INICIAL_GUSTAVO:
        print(
            "AVISO: SEED_SENHA_MARLI e/ou SEED_SENHA_GUSTAVO nao foram definidas - "
            "esse(s) coordenador(es) ficaram SEM senha e nao conseguem aprovar valor "
            "ate voce rodar o seed de novo passando essas variaveis."
        )


if __name__ == "__main__":
    main()
