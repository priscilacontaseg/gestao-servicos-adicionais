"""Motor de regras deterministico de precificacao.

Formula: valor_base_competencia (por regime, tabela regras_precificacao)
         x qtd_competencias
         x multiplicador_reincidencia (da regra, aplicado se houver anexo)
         x multiplicador_complexidade (constante abaixo, Baixa/Media/Alta)

Zero uso de LLM/IA aqui - e 100% reproduzivel e auditavel.
"""

from datetime import date
from typing import Optional, TypedDict

from sqlmodel import Session, select

from .models import ComplexidadeCaso, RegimeTributario, RegraPrecificacao

# Multiplicadores de complexidade: constante fixa, nao versionada no banco
# (o proprio Felipe descreveu como "algo assim" - ajustar aqui se necessario).
MULTIPLICADOR_COMPLEXIDADE = {
    ComplexidadeCaso.BAIXA: 1.0,
    ComplexidadeCaso.MEDIA: 1.25,
    ComplexidadeCaso.ALTA: 1.50,
}


class ResultadoVeredito(TypedDict):
    cortesia: bool
    classificacao: str
    diagnostico: str
    valor_sugerido: float


def buscar_regra_vigente(
    session: Session, regime_tributario: RegimeTributario
) -> Optional[RegraPrecificacao]:
    hoje = date.today()
    regras = session.exec(
        select(RegraPrecificacao)
        .where(RegraPrecificacao.regime_tributario == regime_tributario)
        .where(RegraPrecificacao.ativo == True)  # noqa: E712
        .where(RegraPrecificacao.vigente_de <= hoje)
        .order_by(RegraPrecificacao.vigente_de.desc())
    ).all()
    for regra in regras:
        if regra.vigente_ate is None or regra.vigente_ate >= hoje:
            return regra
    return None


def calcular_precificacao(
    regra: Optional[RegraPrecificacao],
    qtd_competencias: int,
    complexidade: ComplexidadeCaso,
    tem_provas: bool,
) -> ResultadoVeredito:
    if qtd_competencias <= 0:
        return {
            "cortesia": True,
            "classificacao": "Cortesia - nao gera cobranca",
            "diagnostico": (
                "Nenhuma competencia com cobranca associada. Registre o motivo "
                "internamente e crie uma atividade normal, sem enviar proposta ao cliente."
            ),
            "valor_sugerido": 0.0,
        }

    if regra is None:
        raise ValueError("Nenhuma regra de precificacao vigente para o regime informado.")

    multiplicador_reincidencia = regra.multiplicador_reincidencia if tem_provas else 1.0
    multiplicador_complexidade = MULTIPLICADOR_COMPLEXIDADE[complexidade]

    valor_sugerido = round(
        regra.valor_base_competencia
        * qtd_competencias
        * multiplicador_reincidencia
        * multiplicador_complexidade,
        2,
    )

    classificacao = "Retrabalho Reincidente" if tem_provas else "Caso Novo com Cobranca"
    diagnostico = (
        "Caso com aviso previo documentado nos anexos. "
        f"Classificacao: {classificacao}. Complexidade: {complexidade.value}."
        if tem_provas
        else (
            f"Caso sem aviso previo documentado. Classificacao: {classificacao}. "
            f"Complexidade: {complexidade.value}."
        )
    )

    return {
        "cortesia": False,
        "classificacao": classificacao,
        "diagnostico": diagnostico,
        "valor_sugerido": valor_sugerido,
    }
