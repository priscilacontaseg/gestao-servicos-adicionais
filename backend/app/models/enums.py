from enum import Enum


class CargoFuncionario(str, Enum):
    OPERADOR = "operador"
    COORDENADOR = "coordenador"
    FINANCEIRO = "financeiro"
    GESTOR = "gestor"


class Setor(str, Enum):
    """Setor ao qual a proposta pertence e cujo coordenador tem autoridade
    para aprovar ajustes de valor (ex: fiscal -> Marli, simples_nacional -> Gustavo,
    pessoal -> Daniel, contabil -> Regina)."""

    FISCAL = "fiscal"
    SIMPLES_NACIONAL = "simples_nacional"
    PESSOAL = "pessoal"
    CONTABIL = "contabil"


class PorteEmpresa(str, Enum):
    """Informativo apenas - nao entra na formula de precificacao."""

    MICROEMPRESA = "microempresa"
    PEQUENO_PORTE = "pequeno_porte"
    MEDIO_GRANDE = "medio_grande"


class ComplexidadeCaso(str, Enum):
    """O que de fato mede o esforco do caso (quanto ele cascateia entre
    fiscal, contabil e declaracoes) e por isso multiplica o preco - ao
    contrario do Porte da Empresa, que e so informativo."""

    BAIXA = "baixa"
    MEDIA = "media"
    ALTA = "alta"


class RegimeTributario(str, Enum):
    SIMPLES_NACIONAL = "simples_nacional"
    LUCRO_PRESUMIDO = "lucro_presumido"
    LUCRO_REAL = "lucro_real"


class StatusProposta(str, Enum):
    RASCUNHO = "rascunho"
    AGUARDANDO_APROVACAO_VALOR = "aguardando_aprovacao_valor"
    AGUARDANDO_RESPOSTA = "aguardando_resposta"
    ACEITA = "aceita"
    NAO_ACEITA = "nao_aceita"
    FALAR_COM_RESPONSAVEL = "falar_com_responsavel"
    CANCELADA = "cancelada"


class RespostaCliente(str, Enum):
    """Resposta que o cliente deu no WhatsApp manual/conversacional, registrada
    a mao pelo operador na tela de 'Propostas em Negociacao'."""

    ACEITO = "aceito"
    NAO_ACEITO = "nao_aceito"
    FALAR_COM_RESPONSAVEL = "falar_com_responsavel"
