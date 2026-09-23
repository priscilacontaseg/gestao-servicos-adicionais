"""Motor de regras deterministico de precificacao.

Formula: valor_base_competencia (por regime, tabela regras_precificacao)
         x qtd_competencias
         x multiplicador_reincidencia (da regra, aplicado se houver anexo)
         x multiplicador_complexidade (constante abaixo, Baixa/Media/Alta)
         x multiplicador_recorrencia_cliente (+50% se o cliente ja teve 2+
           competencias diferentes com proposta aceita/paga antes desta -
           "cliente que mesmo pagando nunca muda e sempre cai")

qtd_avisos_cliente (quantas vezes esse aviso especifico foi dado, 2 a 5+) e
so registro/justificativa no card - nao entra na formula, decidido por
Felipe: um cliente avisado 2x sobre a primeira vez dele no sistema ainda nao
e "recorrente", so vira quando o padrao se repete entre competencias/epocas
diferentes (isso sim o sistema conta sozinho, via historico de propostas).

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

# A partir de quantas competencias DIFERENTES ja aceitas/pagas antes o
# cliente vira "recorrente" (na 3a vez que aparece no total: 2 anteriores +
# esta) e passa a levar o multiplicador extra.
LIMITE_PROPOSTAS_ACEITAS_PARA_RECORRENCIA = 2
MULTIPLICADOR_RECORRENCIA_CLIENTE = 1.5


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
    qtd_avisos_cliente: Optional[int] = None,
    propostas_aceitas_anteriores_cliente: int = 0,
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
    cliente_recorrente = propostas_aceitas_anteriores_cliente >= LIMITE_PROPOSTAS_ACEITAS_PARA_RECORRENCIA
    multiplicador_recorrencia_cliente = MULTIPLICADOR_RECORRENCIA_CLIENTE if cliente_recorrente else 1.0

    valor_sugerido = round(
        regra.valor_base_competencia
        * qtd_competencias
        * multiplicador_reincidencia
        * multiplicador_complexidade
        * multiplicador_recorrencia_cliente,
        2,
    )

    classificacao = "Retrabalho Reincidente" if tem_provas else "Caso Novo com Cobranca"
    if cliente_recorrente:
        classificacao += " - Cliente Recorrente"

    diagnostico = (
        "Caso com aviso previo documentado nos anexos. "
        f"Classificacao: {classificacao}. Complexidade: {complexidade.value}."
        if tem_provas
        else (
            f"Caso sem aviso previo documentado. Classificacao: {classificacao}. "
            f"Complexidade: {complexidade.value}."
        )
    )
    if qtd_avisos_cliente:
        diagnostico += f" Cliente avisado {qtd_avisos_cliente}x sobre essa competencia sem regularizacao."
    if cliente_recorrente:
        diagnostico += (
            f" Cliente ja teve {propostas_aceitas_anteriores_cliente} cobranca(s) aceita(s) em "
            "competencias anteriores - valor com multiplicador de recorrencia (+50%)."
        )

    return {
        "cortesia": False,
        "classificacao": classificacao,
        "diagnostico": diagnostico,
        "valor_sugerido": valor_sugerido,
    }
