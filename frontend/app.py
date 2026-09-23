"""Gestão de Serviços Adicionais - tela do operador (perícia de campo).

Fluxo: dados do caso -> provas -> veredito do motor de regras -> confirmação
(cria o cartão no Trello) -> texto pronto pra copiar e mandar manualmente no
WhatsApp comum. Depois, a seção "Propostas em Negociação" deixa o operador
dar baixa manual na resposta do cliente (aceite/recusa/dúvida), o que
atualiza o cartão do Trello via comentário - sem nenhuma API do WhatsApp.
"""

import os
import re

import httpx
import streamlit as st

from backend_bootstrap import garantir_backend_rodando

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Gestão de Serviços Adicionais",
    page_icon="\U0001f4cb",
    layout="centered",
)

if not garantir_backend_rodando():
    st.error(
        "O backend não respondeu a tempo. Recarregue a página em alguns segundos "
        "(no Streamlit Cloud o primeiro carregamento após o app dormir demora um pouco)."
    )
    st.stop()

# --------------------------------------------------------------------------
# Estilo
# --------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .bloco-titulo {
        display: flex;
        align-items: center;
        gap: 0.6rem;
        margin-bottom: 0.2rem;
    }
    .bloco-numero {
        background-color: #075E54;
        color: white;
        font-weight: 700;
        width: 1.8rem;
        height: 1.8rem;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.95rem;
        flex-shrink: 0;
    }
    .bloco-subtitulo {
        color: #6b7280;
        font-size: 0.88rem;
        margin-top: -0.3rem;
        margin-bottom: 0.8rem;
    }
    .painel-veredito {
        border-radius: 12px;
        padding: 1.2rem 1.4rem;
        margin: 0.6rem 0 1rem 0;
        border-left: 6px solid;
        color: #111827;
    }
    .painel-veredito * {
        color: #111827 !important;
    }
    .painel-cobranca {
        background-color: #ecfdf5;
        border-left-color: #16a34a;
    }
    .painel-cortesia {
        background-color: #eff6ff;
        border-left-color: #2563eb;
    }
    .painel-valor {
        font-size: 2.1rem;
        font-weight: 800;
        margin: 0.2rem 0;
    }
    .painel-tag {
        display: inline-block;
        background-color: rgba(0,0,0,0.08);
        border-radius: 999px;
        padding: 0.15rem 0.7rem;
        font-size: 0.82rem;
        font-weight: 600;
        margin-bottom: 0.4rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def titulo_bloco(numero: str, titulo: str, subtitulo: str = "") -> None:
    st.markdown(
        f"""
        <div class="bloco-titulo">
            <div class="bloco-numero">{numero}</div>
            <h3 style="margin:0;">{titulo}</h3>
        </div>
        {f'<div class="bloco-subtitulo">{subtitulo}</div>' if subtitulo else ''}
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Constantes (label na tela -> valor esperado pela API)
# --------------------------------------------------------------------------
PORTE_OPCOES = {
    "Microempresa": "microempresa",
    "Empresa de Pequeno Porte (EPP)": "pequeno_porte",
    "Médio/Grande Porte": "medio_grande",
}
COMPLEXIDADE_OPCOES = {
    "Baixa": "baixa",
    "Média (+25%)": "media",
    "Alta (+50%)": "alta",
}
REGIME_OPCOES = {
    "Simples Nacional": "simples_nacional",
    "Lucro Presumido": "lucro_presumido",
    "Lucro Real": "lucro_real",
}
SETOR_OPCOES = {
    "Fiscal": "fiscal",
    "Simples Nacional": "simples_nacional",
    "Pessoal": "pessoal",
    "Contábil": "contabil",
}
AVISOS_CLIENTE_OPCOES = {
    "2x": 2,
    "3x": 3,
    "4x": 4,
    "5x ou mais": 5,
}


def normalizar_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def cnpj_valido(cnpj: str) -> bool:
    return len(normalizar_digitos(cnpj)) == 14


def formatar_moeda(valor: float) -> str:
    texto = f"{valor:,.2f}"
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def eh_cortesia(proposta: dict) -> bool:
    return proposta.get("qtd_competencias", 0) <= 0


def montar_texto_whatsapp(proposta: dict, razao_social: str, descricao: str) -> str:
    competencia_texto = f"{proposta.get('qtd_competencias', 0)} competência(s)"
    return (
        f"Olá! Sou da equipe Contaseg, tudo bem?\n\n"
        f"Durante a conferência da sua empresa {razao_social}, identificamos uma "
        f"inconsistência apontada pelo estado na malha fiscal, envolvendo {competencia_texto}: "
        f"{descricao.strip()}\n\n"
        f"Esse procedimento constitui um serviço adicional.\n\n"
        f"Valor do serviço: {formatar_moeda(proposta['valor_final'])}. Para podermos fazer o "
        f"serviço, precisamos do seu aceite, podemos prosseguir?"
    )


def buscar_propostas_aguardando(api_base_url: str) -> list:
    try:
        resp = httpx.get(f"{api_base_url}/propostas", params={"status": "aguardando_resposta"}, timeout=10.0)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError:
        return None


@st.cache_data(ttl=30)
def buscar_coordenadores(api_base_url: str) -> list:
    try:
        resp = httpx.get(f"{api_base_url}/funcionarios", params={"cargo": "coordenador"}, timeout=5.0)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError:
        return []


def buscar_propostas_para_aprovar(api_base_url: str) -> list:
    try:
        resp = httpx.get(
            f"{api_base_url}/propostas", params={"status": "aguardando_aprovacao_valor"}, timeout=10.0
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError:
        return None


def buscar_detalhe_proposta(api_base_url: str, proposta_id: int) -> dict:
    resp = httpx.get(f"{api_base_url}/propostas/{proposta_id}/detalhe", timeout=10.0)
    resp.raise_for_status()
    return resp.json()


# --------------------------------------------------------------------------
# Estado da sessão
# --------------------------------------------------------------------------
for chave, valor_inicial in {
    "proposta_atual": None,
    "acao_pos_analise": None,
    "texto_para_copiar": None,
    "razao_social_confirmada": None,
    "descricao_confirmada": None,
}.items():
    if chave not in st.session_state:
        st.session_state[chave] = valor_inicial


def reiniciar_caso() -> None:
    st.session_state.proposta_atual = None
    st.session_state.acao_pos_analise = None
    st.session_state.texto_para_copiar = None
    st.session_state.razao_social_confirmada = None
    st.session_state.descricao_confirmada = None


# --------------------------------------------------------------------------
# Sidebar - identificação do operador (digita o próprio nome, sem senha -
# a lista de operadores cresce sozinha conforme as pessoas usam o sistema)
# --------------------------------------------------------------------------
with st.sidebar:
    st.subheader("Sessão")
    operador_nome = st.text_input("Seu nome (operador)", placeholder="Ex: Maria")
    st.caption("Digite seu nome - sem senha. Só a aprovação de valor pela coordenação exige senha.")

# --------------------------------------------------------------------------
# Cabeçalho
# --------------------------------------------------------------------------
st.title("Gestão de Serviços Adicionais")
st.caption(
    "Tela do operador: preencha a perícia técnica, analise o caso, confirme a proposta e "
    "copie o texto para mandar manualmente no WhatsApp comum - sem API, sem botões pro cliente."
)
st.divider()

tab_sistema, tab_manual = st.tabs(["\U0001f5c2️ Sistema", "\U0001f4d6 Manual de Uso e Diretrizes"])

with tab_sistema:
    # ----------------------------------------------------------------------
    # Bloco 1 - Dados do cliente e do caso
    # ----------------------------------------------------------------------
    with st.container(border=True):
        titulo_bloco("1", "Dados do Cliente e Caso", "Identificação do cliente e características do caso fiscal.")

        st.selectbox(
            "Tipo de Serviço", ["Malha Fiscal"],
            help="Único serviço adicional disponível no sistema por enquanto - "
            "mais opções serão liberadas aqui conforme o sistema crescer.",
        )

        col_razao, col_cnpj = st.columns([2, 1])
        with col_razao:
            razao_social = st.text_input("Razão Social", placeholder="Ex: Empresa Exemplo LTDA")
        with col_cnpj:
            cnpj = st.text_input("CNPJ", placeholder="00.000.000/0000-00")

        col_setor, col_porte = st.columns(2)
        with col_setor:
            setor_label = st.selectbox("Setor Responsável", list(SETOR_OPCOES.keys()))
        with col_porte:
            porte_label = st.selectbox(
                "Porte da Empresa", list(PORTE_OPCOES.keys()), help="Informativo - não afeta o preço."
            )

        col_qtd, col_regime = st.columns(2)
        with col_qtd:
            qtd_competencias = st.number_input(
                "Competências Afetadas", min_value=0, max_value=24, value=1, step=1,
                help="Use 0 quando o caso for uma cortesia, sem cobrança.",
            )
        with col_regime:
            regime_label = st.selectbox("Regime Tributário", list(REGIME_OPCOES.keys()))

        complexidade_label = st.selectbox(
            "Complexidade do Caso", list(COMPLEXIDADE_OPCOES.keys()),
            help="Baixa = preço normal. Média = +25%. Alta = +50%.",
        )

        descricao_inconsistencia = st.text_area(
            "Descrição da Inconsistência Fiscal",
            placeholder="Cole aqui o detalhamento técnico do problema identificado...",
            height=140,
        )

    # ----------------------------------------------------------------------
    # Bloco 2 - Anexo de provas
    # ----------------------------------------------------------------------
    with st.container(border=True):
        titulo_bloco("2", "Anexo de Provas (obrigatório)")
        st.info(
            "Anexe aqui prints ou e-mails provando que o cliente já havia sido orientado "
            "anteriormente. Obrigatório: sem isso o caso é só assessoria, não gera cobrança."
        )
        avisos_label = st.selectbox(
            "Quantas vezes o cliente foi avisado sobre essa competência?",
            list(AVISOS_CLIENTE_OPCOES.keys()),
            help="Confirma que é cobrança, não cortesia: o cliente foi avisado e não "
            "regularizou. Não muda o valor sozinho - só pesa no preço se esse cliente já "
            "tiver histórico de cobrança aceita em outras competências.",
        )
        anexos = st.file_uploader(
            "Provas de aviso prévio",
            type=["png", "jpg", "jpeg", "pdf"],
            accept_multiple_files=True,
            label_visibility="collapsed",
        )
        if anexos:
            st.caption(f"{len(anexos)} arquivo(s) anexado(s): " + ", ".join(a.name for a in anexos))

    # ----------------------------------------------------------------------
    # Bloco 3 - Análise, veredito e confirmação
    # ----------------------------------------------------------------------
    with st.container(border=True):
        titulo_bloco("3", "Análise, Veredito e Confirmação", "O motor de regras avalia o caso contra a tabela de preços oficial.")

        analisar_clicado = st.button("Analisar Caso e Calcular Preço", type="primary", use_container_width=True)

        if analisar_clicado:
            erros = []
            if not razao_social.strip():
                erros.append("Informe a Razão Social do cliente.")
            if not cnpj_valido(cnpj):
                erros.append("CNPJ inválido - informe os 14 dígitos.")
            if not descricao_inconsistencia.strip():
                erros.append("Descreva a inconsistência fiscal identificada.")
            if not operador_nome.strip():
                erros.append("Informe seu nome na barra lateral (Sessão) antes de analisar o caso.")
            if not anexos:
                erros.append(
                    "Anexe pelo menos uma prova de aviso prévio (print, e-mail ou notificação) - "
                    "sem isso o caso não pode ser analisado, é só assessoria, não gera cobrança."
                )

            if erros:
                for erro in erros:
                    st.error(erro)
            else:
                dados_form = {
                    "razao_social": razao_social,
                    "cnpj": cnpj,
                    "setor": SETOR_OPCOES[setor_label],
                    "porte_empresa": PORTE_OPCOES[porte_label],
                    "complexidade": COMPLEXIDADE_OPCOES[complexidade_label],
                    "regime_tributario": REGIME_OPCOES[regime_label],
                    "qtd_competencias": int(qtd_competencias),
                    "descricao_inconsistencia": descricao_inconsistencia,
                    "qtd_avisos_cliente": AVISOS_CLIENTE_OPCOES[avisos_label],
                    "operador_nome": operador_nome,
                }
                arquivos_form = [
                    ("anexos", (arquivo.name, arquivo.getvalue(), arquivo.type or "application/octet-stream"))
                    for arquivo in (anexos or [])
                ]
                with st.spinner("Consultando o motor de regras..."):
                    try:
                        resp = httpx.post(
                            f"{API_BASE_URL}/propostas/analisar",
                            data=dados_form,
                            files=arquivos_form or None,
                            timeout=20.0,
                        )
                    except httpx.ConnectError:
                        st.error(
                            f"Não foi possível conectar ao backend em {API_BASE_URL}. "
                            "Confirme se o servidor FastAPI está rodando."
                        )
                    else:
                        if resp.status_code == 200:
                            st.session_state.proposta_atual = resp.json()
                            st.session_state.acao_pos_analise = None
                            st.session_state.texto_para_copiar = None
                            st.session_state.razao_social_confirmada = razao_social
                            st.session_state.descricao_confirmada = descricao_inconsistencia
                        else:
                            try:
                                detalhe = resp.json().get("detail", resp.text)
                            except ValueError:
                                detalhe = resp.text
                            st.error(f"Erro do backend ({resp.status_code}): {detalhe}")

        proposta = st.session_state.proposta_atual
        if proposta:
            cortesia = eh_cortesia(proposta)
            classe_painel = "painel-cortesia" if cortesia else "painel-cobranca"
            tag_texto = "CORTESIA" if cortesia else "PASSÍVEL DE COBRANÇA"

            st.markdown(
                f"""
                <div class="painel-veredito {classe_painel}">
                    <span class="painel-tag">Proposta {proposta['numero_proposta']} - {tag_texto}</span>
                    <div class="painel-valor">{formatar_moeda(proposta['valor_final'])}</div>
                    <div><b>Classificação:</b> {proposta['classificacao']}</div>
                    <div style="margin-top:0.4rem;">{proposta['diagnostico_texto']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if cortesia:
                st.warning(
                    "Caso classificado como cortesia: nada é enviado ao cliente pelo WhatsApp. "
                    "Registre o motivo internamente e crie a atividade normal do setor."
                )
            elif proposta["status"] == "aguardando_aprovacao_valor":
                st.info(
                    f"Proposta aguardando aprovação de valor pela coordenação de "
                    f"**{proposta['setor']}**. O operador não tem mais ação aqui até a decisão."
                )
            elif proposta["status"] == "rascunho":
                col_confirmar, col_revisar = st.columns(2)
                with col_confirmar:
                    if st.button("Confirmar Proposta", type="primary", use_container_width=True):
                        try:
                            resp = httpx.post(f"{API_BASE_URL}/propostas/{proposta['id']}/confirmar", timeout=15.0)
                        except httpx.ConnectError:
                            st.error(f"Não foi possível conectar ao backend em {API_BASE_URL}.")
                        else:
                            if resp.status_code == 200:
                                st.session_state.proposta_atual = resp.json()
                                st.rerun()
                            else:
                                try:
                                    detalhe = resp.json().get("detail", resp.text)
                                except ValueError:
                                    detalhe = resp.text
                                st.error(f"Erro do backend ({resp.status_code}): {detalhe}")
                with col_revisar:
                    if st.button("Solicitar Revisão de Valor à Coordenação", use_container_width=True):
                        st.session_state.acao_pos_analise = "revisao"

                if st.session_state.acao_pos_analise == "revisao":
                    st.markdown("---")
                    st.write(
                        f"O valor sugerido será enviado para aprovação da coordenação de "
                        f"**{proposta['setor']}**. O operador não pode alterar o valor diretamente."
                    )
                    motivo_revisao = st.text_area(
                        "Justifique por que você acha que o valor está incorreto",
                        placeholder="Ex: cliente tem histórico de bom pagador, ou caso tem particularidade não coberta pela regra...",
                    )
                    if st.button("Enviar Solicitação para Coordenação"):
                        if not motivo_revisao.strip():
                            st.error("Informe a justificativa antes de enviar a solicitação.")
                        else:
                            try:
                                resp = httpx.post(
                                    f"{API_BASE_URL}/propostas/{proposta['id']}/solicitar_revisao",
                                    json={"motivo": motivo_revisao},
                                    timeout=15.0,
                                )
                            except httpx.ConnectError:
                                st.error(f"Não foi possível conectar ao backend em {API_BASE_URL}.")
                            else:
                                if resp.status_code == 200:
                                    st.session_state.proposta_atual = resp.json()
                                    st.rerun()
                                else:
                                    try:
                                        detalhe = resp.json().get("detail", resp.text)
                                    except ValueError:
                                        detalhe = resp.text
                                    st.error(f"Erro do backend ({resp.status_code}): {detalhe}")

            elif proposta["status"] == "aguardando_resposta":
                if proposta.get("trello_card_url"):
                    st.success(f"Cartão criado no Trello: {proposta['trello_card_url']}")
                else:
                    st.warning(
                        "Trello não configurado neste ambiente (.env sem TRELLO_API_KEY/TOKEN) - "
                        "cartão NÃO foi criado de verdade, só o status avançou."
                    )

                texto_whatsapp = montar_texto_whatsapp(
                    proposta,
                    st.session_state.razao_social_confirmada or razao_social,
                    st.session_state.descricao_confirmada or descricao_inconsistencia,
                )
                st.write("**Texto para copiar e enviar manualmente no WhatsApp:**")
                st.code(texto_whatsapp, language=None)
                st.caption("Sem links ou botões - copie e cole na conversa comum com o cliente.")

    # ----------------------------------------------------------------------
    # Reiniciar
    # ----------------------------------------------------------------------
    st.divider()
    if st.button("Novo Caso"):
        reiniciar_caso()
        st.rerun()

    # ----------------------------------------------------------------------
    # Propostas em Negociação - baixa manual da resposta do cliente
    # ----------------------------------------------------------------------
    st.divider()
    st.header("Propostas em Negociação")
    st.caption(
        "Casos com proposta já enviada manualmente pelo WhatsApp, aguardando a resposta do cliente. "
        "Registre aqui o que o cliente respondeu na conversa."
    )

    pendentes = buscar_propostas_aguardando(API_BASE_URL)
    if pendentes is None:
        st.warning(f"Não foi possível carregar as propostas pendentes de {API_BASE_URL}.")
    elif not pendentes:
        st.info("Nenhuma proposta aguardando resposta do cliente no momento.")
    else:
        opcoes_pendentes = {
            f"{p['numero_proposta']} - {p['razao_social']} - {formatar_moeda(p['valor_final'] or 0.0)}": p["id"]
            for p in pendentes
        }
        escolha_pendente = st.selectbox("Selecione a proposta", list(opcoes_pendentes.keys()), key="negociacao_escolha")
        proposta_negociacao_id = opcoes_pendentes[escolha_pendente]

        col_aceite, col_recusa, col_duvida = st.columns(3)
        with col_aceite:
            aceite_clicado = st.button("Registrar Aceite", type="primary", use_container_width=True)
        with col_recusa:
            recusa_clicado = st.button("Registrar Recusa", use_container_width=True)
        with col_duvida:
            duvida_clicado = st.button("Cliente com Dúvidas", use_container_width=True)

        resposta_escolhida = None
        if aceite_clicado:
            resposta_escolhida = "aceito"
        elif recusa_clicado:
            resposta_escolhida = "nao_aceito"
        elif duvida_clicado:
            resposta_escolhida = "falar_com_responsavel"

        if resposta_escolhida:
            try:
                resp = httpx.post(
                    f"{API_BASE_URL}/propostas/{proposta_negociacao_id}/registrar_resposta",
                    json={"resposta": resposta_escolhida},
                    timeout=15.0,
                )
            except httpx.ConnectError:
                st.error(f"Não foi possível conectar ao backend em {API_BASE_URL}.")
            else:
                if resp.status_code == 200:
                    st.success(f"Resposta '{resposta_escolhida}' registrada e cartão do Trello atualizado.")
                    st.rerun()
                else:
                    try:
                        detalhe = resp.json().get("detail", resp.text)
                    except ValueError:
                        detalhe = resp.text
                    st.error(f"Erro do backend ({resp.status_code}): {detalhe}")

    # ----------------------------------------------------------------------
    # Painel da Coordenação / Gestão - aprovação de valor com senha de assinatura
    # ----------------------------------------------------------------------
    st.divider()
    st.header("Painel da Coordenação / Gestão")
    st.caption(
        "Casos onde o operador discordou do valor calculado e pediu revisão. "
        "Só o coordenador do setor (com a própria senha) pode decidir aqui."
    )

    coordenadores = buscar_coordenadores(API_BASE_URL)
    if not coordenadores:
        st.warning(f"Não foi possível carregar coordenadores de {API_BASE_URL}.")
    else:
        opcoes_coordenador = {f"{c['nome']} ({c['setor']})": c for c in coordenadores}
        escolha_coordenador = st.selectbox("Coordenador(a) logado(a)", list(opcoes_coordenador.keys()))
        coordenador_atual = opcoes_coordenador[escolha_coordenador]

        pendentes_aprovacao = buscar_propostas_para_aprovar(API_BASE_URL)
        if pendentes_aprovacao is None:
            st.warning(f"Não foi possível carregar as propostas pendentes de aprovação de {API_BASE_URL}.")
        else:
            pendentes_do_setor = [p for p in pendentes_aprovacao if p["setor"] == coordenador_atual["setor"]]

            if not pendentes_do_setor:
                st.info(f"Nenhuma proposta aguardando aprovação no setor '{coordenador_atual['setor']}'.")
            else:
                opcoes_aprovacao = {
                    f"{p['numero_proposta']} - {p['razao_social']} - {formatar_moeda(p['valor_final'] or 0.0)}": p["id"]
                    for p in pendentes_do_setor
                }
                escolha_aprovacao = st.selectbox(
                    "Selecione o pedido de revisão", list(opcoes_aprovacao.keys()), key="aprovacao_escolha"
                )
                proposta_aprovacao_id = opcoes_aprovacao[escolha_aprovacao]

                detalhe = buscar_detalhe_proposta(API_BASE_URL, proposta_aprovacao_id)

                col_info, col_acao = st.columns(2)
                with col_info:
                    st.write(f"**Cliente:** {detalhe['razao_social']} (CNPJ {detalhe['cnpj']})")
                    st.write(f"**Operador:** {detalhe['operador_nome']}")
                    st.write(f"**Competências:** {', '.join(detalhe['competencias'])}")
                    st.write(f"**Valor calculado pelo motor:** {formatar_moeda(detalhe['valor_sugerido'])}")
                    st.write(f"**Classificação:** {detalhe['classificacao']}")
                    st.write("**Justificativa do operador para a revisão:**")
                    st.info(detalhe.get("motivo_solicitacao_revisao") or "(nenhuma justificativa registrada)")

                    if detalhe["anexos"]:
                        st.write("**Prova(s) anexada(s):**")
                        for anexo in detalhe["anexos"]:
                            url_arquivo = f"{API_BASE_URL}/propostas/{proposta_aprovacao_id}/anexos/{anexo['id']}/arquivo"
                            try:
                                conteudo = httpx.get(url_arquivo, timeout=10.0).content
                            except httpx.HTTPError:
                                st.caption(f"Não foi possível carregar {anexo['nome_arquivo']}.")
                            else:
                                if anexo["tipo_mime"].startswith("image/"):
                                    st.image(conteudo, caption=anexo["nome_arquivo"], width=250)
                                else:
                                    st.download_button(
                                        f"Baixar {anexo['nome_arquivo']}", data=conteudo,
                                        file_name=anexo["nome_arquivo"], mime=anexo["tipo_mime"],
                                    )
                    else:
                        st.caption("Nenhuma prova anexada nesta proposta.")

                with col_acao:
                    valor_final_coordenador = st.number_input(
                        "Valor Final", min_value=0.0, value=float(detalhe["valor_sugerido"]), step=10.0,
                        key=f"valor_final_{proposta_aprovacao_id}",
                    )
                    motivo_ajuste_coordenador = st.text_area(
                        "Justificativa da decisão (obrigatória)",
                        placeholder="Ex: mantive o valor calculado / reduzi por bom histórico do cliente...",
                        key=f"motivo_ajuste_{proposta_aprovacao_id}",
                    )
                    senha_coordenador = st.text_input(
                        "Senha de Assinatura Eletrônica", type="password",
                        key=f"senha_{proposta_aprovacao_id}",
                    )

                    if st.button("Aprovar e Criar Cartão no Trello", type="primary", use_container_width=True):
                        if not motivo_ajuste_coordenador.strip():
                            st.error("Informe a justificativa da decisão antes de aprovar.")
                        elif not senha_coordenador:
                            st.error("Informe a senha de assinatura eletrônica.")
                        else:
                            try:
                                resp = httpx.post(
                                    f"{API_BASE_URL}/propostas/{proposta_aprovacao_id}/aprovar_valor",
                                    json={
                                        "funcionario_id": coordenador_atual["id"],
                                        "valor_final": valor_final_coordenador,
                                        "motivo_ajuste": motivo_ajuste_coordenador,
                                        "senha": senha_coordenador,
                                    },
                                    timeout=15.0,
                                )
                            except httpx.ConnectError:
                                st.error(f"Não foi possível conectar ao backend em {API_BASE_URL}.")
                            else:
                                if resp.status_code == 200:
                                    resultado = resp.json()
                                    st.success(
                                        f"Proposta aprovada com valor final {formatar_moeda(resultado['valor_final'])}. "
                                        f"Status: {resultado['status']}."
                                    )
                                    if resultado.get("trello_card_url"):
                                        st.success(f"Cartão criado no Trello: {resultado['trello_card_url']}")
                                    else:
                                        st.warning(
                                            "Trello não configurado neste ambiente - cartão NÃO foi criado de "
                                            "verdade, só o status avançou."
                                        )
                                    st.rerun()
                                else:
                                    try:
                                        detalhe_erro = resp.json().get("detail", resp.text)
                                    except ValueError:
                                        detalhe_erro = resp.text
                                    st.error(f"Erro ({resp.status_code}): {detalhe_erro}")

with tab_manual:
    st.markdown(
        """
## \U0001f477 Para Operadores

**Passo a passo:**

1. Na barra lateral (**Sessão**), digite o seu nome. Não precisa de senha - só pra registrar quem fez a análise.
2. Preencha os **Dados do Cliente e Caso**: Razão Social, CNPJ, Setor Responsável, Porte, Competências Afetadas, Regime Tributário, Complexidade e a Descrição da Inconsistência Fiscal.
3. **Anexe a prova de aviso prévio** (print de conversa, e-mail ou notificação mostrando que o cliente já foi avisado antes). Isso é **obrigatório** - sem anexo, o sistema não deixa nem analisar o caso.
4. Informe **quantas vezes o cliente foi avisado** sobre essa competência (2x a 5x ou mais) - isso fica registrado como justificativa no cartão, mas não muda o valor sozinho.
5. Clique em **"Analisar Caso e Calcular Preço"** - o motor de regras calcula o valor automaticamente, sem ninguém decidir isso na mão.
6. Se concordar com o valor calculado, clique em **"Confirmar Proposta"** - isso cria o cartão no Trello (controle interno, sempre com prazo de 48h e responsável definido) e libera o texto pronto.
7. **Copie o texto** (tem um ícone de copiar no canto do bloco de código) e **cole direto na conversa do WhatsApp comum** com o cliente - o sistema não manda nada sozinho, não tem link nem botão automático.
8. Depois que o cliente responder pelo WhatsApp, volte na seção **"Propostas em Negociação"**, selecione o caso pelo nome/número e registre o que ele respondeu: **Aceite**, **Recusa** ou **Cliente com Dúvidas**.

---

### ⚠️ Casos de Cortesia

Se você colocar **0 (zero)** em "Competências Afetadas", o sistema entende que **não é pra cobrar** - é um caso de cortesia.

Nesse caso, **não aparece nenhum texto pra copiar e nenhum cartão é criado pro cliente**. O sistema só mostra um aviso interno pra você registrar o motivo e seguir com o atendimento normal do setor.

**Não ligue nem avise o cliente que decidimos não cobrar** - isso fica só registrado internamente.

---

### ⚠️ Cliente recorrente (cobrança automática mais alta)

Se o mesmo cliente (mesmo CNPJ) já teve proposta aceita em **duas competências diferentes antes** desta, o sistema aplica automaticamente um adicional de **+50%** no valor - é o sinal de que o cliente continua caindo em malha mesmo depois de já ter pago antes. Isso é calculado sozinho pelo sistema, você não precisa fazer nada além de preencher o caso normalmente.

---

### ⚠️ Se você achar que o valor calculado está errado

Você **não pode alterar o valor** diretamente - isso é proposital, pra manter o preço justo e igual pra todo mundo. Clique em **"Solicitar Revisão de Valor à Coordenação"**, escreva o motivo, e a coordenação do seu setor decide.

---

## \U0001f9ed Para a Coordenação

Quando um operador pede revisão de valor, o caso aparece na seção **"Painel da Coordenação / Gestão"**, no final da tela (aba Sistema).

**Como aprovar:**

1. Escolha o seu nome em **"Coordenador(a) logado(a)"**.
2. Selecione o caso na lista (só aparecem os casos do seu setor).
3. Confira os dados: valor calculado pelo motor, a justificativa do operador e **a prova anexada** (imagem aparece na tela, PDF vira botão de download).
4. Defina o **Valor Final** (pode manter o valor sugerido ou ajustar).
5. Escreva a **Justificativa da decisão** - obrigatório, mesmo se for só "mantive o valor calculado".
6. Digite a sua **Senha de Assinatura Eletrônica** pessoal.
7. Clique em **"Aprovar e Criar Cartão no Trello"**.

Se a senha estiver errada, o sistema bloqueia e mostra um erro em vermelho - ninguém aprova nada sem a senha certa. Se você não tem senha cadastrada ainda, fale com quem administra o sistema.
        """
    )
