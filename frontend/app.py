"""Gestao de Servicos Adicionais - tela do operador (pericia de campo).

Fluxo: dados do caso -> provas -> veredito do motor de regras -> confirmacao
(cria o cartao no Trello) -> texto pronto pra copiar e mandar manualmente no
WhatsApp comum. Depois, a secao "Propostas em Negociacao" deixa o operador
dar baixa manual na resposta do cliente (aceite/recusa/duvida), o que
atualiza o cartao do Trello via comentario - sem nenhuma API do WhatsApp.
"""

import os
import re

import httpx
import streamlit as st

from backend_bootstrap import garantir_backend_rodando

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Gestao de Servicos Adicionais",
    page_icon="\U0001f4cb",
    layout="centered",
)

if not garantir_backend_rodando():
    st.error(
        "O backend nao respondeu a tempo. Recarregue a pagina em alguns segundos "
        "(no Streamlit Cloud o primeiro carregamento apos o app dormir demora um pouco)."
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
        background-color: rgba(0,0,0,0.06);
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
    "Medio/Grande Porte": "medio_grande",
}
COMPLEXIDADE_OPCOES = {
    "Baixa": "baixa",
    "Media (+25%)": "media",
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
    "Contabil": "contabil",
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
    competencia_texto = f"{proposta.get('qtd_competencias', 0)} competencia(s)"
    return (
        f"Ola! Sou da equipe Contaseg, tudo bem?\n\n"
        f"Durante a conferencia da sua empresa {razao_social}, identificamos uma "
        f"inconsistencia apontada pelo estado na malha fiscal, envolvendo {competencia_texto}: "
        f"{descricao.strip()}\n\n"
        f"Esse procedimento constitui um servico adicional.\n\n"
        f"Valor do servico: {formatar_moeda(proposta['valor_final'])}. Para podermos fazer o "
        f"servico, precisamos do seu aceite, podemos prosseguir?"
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
# Estado da sessao
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
# Sidebar - identificacao do operador (digita o proprio nome, sem senha -
# a lista de operadores cresce sozinha conforme as pessoas usam o sistema)
# --------------------------------------------------------------------------
with st.sidebar:
    st.subheader("Sessao")
    operador_nome = st.text_input("Seu nome (operador)", placeholder="Ex: Maria")
    st.caption("Digite seu nome - sem senha. So a aprovacao de valor pela coordenacao exige senha.")

# --------------------------------------------------------------------------
# Cabecalho
# --------------------------------------------------------------------------
st.title("Gestao de Servicos Adicionais")
st.caption(
    "Tela do operador: preencha a pericia tecnica, analise o caso, confirme a proposta e "
    "copie o texto para mandar manualmente no WhatsApp comum - sem API, sem botoes pro cliente."
)
st.divider()

tab_sistema, tab_manual = st.tabs(["\U0001f5c2️ Sistema", "\U0001f4d6 Manual de Uso e Diretrizes"])

with tab_sistema:
    # ----------------------------------------------------------------------
    # Bloco 1 - Dados do cliente e do caso
    # ----------------------------------------------------------------------
    with st.container(border=True):
        titulo_bloco("1", "Dados do Cliente e Caso", "Identificacao do cliente e caracteristicas do caso fiscal.")

        st.selectbox(
            "Tipo de Servico", ["Malha Fiscal"],
            help="Unico servico adicional disponivel no sistema por enquanto - "
            "mais opcoes serao liberadas aqui conforme o sistema crescer.",
        )

        col_razao, col_cnpj = st.columns([2, 1])
        with col_razao:
            razao_social = st.text_input("Razao Social", placeholder="Ex: Empresa Exemplo LTDA")
        with col_cnpj:
            cnpj = st.text_input("CNPJ", placeholder="00.000.000/0000-00")

        col_setor, col_porte = st.columns(2)
        with col_setor:
            setor_label = st.selectbox("Setor Responsavel", list(SETOR_OPCOES.keys()))
        with col_porte:
            porte_label = st.selectbox(
                "Porte da Empresa", list(PORTE_OPCOES.keys()), help="Informativo - nao afeta o preco."
            )

        col_qtd, col_regime = st.columns(2)
        with col_qtd:
            qtd_competencias = st.number_input(
                "Competencias Afetadas", min_value=0, max_value=24, value=1, step=1,
                help="Use 0 quando o caso for uma cortesia, sem cobranca.",
            )
        with col_regime:
            regime_label = st.selectbox("Regime Tributario", list(REGIME_OPCOES.keys()))

        complexidade_label = st.selectbox(
            "Complexidade do Caso", list(COMPLEXIDADE_OPCOES.keys()),
            help="Baixa = preco normal. Media = +25%. Alta = +50%.",
        )

        descricao_inconsistencia = st.text_area(
            "Descricao da Inconsistencia Fiscal",
            placeholder="Cole aqui o detalhamento tecnico do problema identificado...",
            height=140,
        )

    # ----------------------------------------------------------------------
    # Bloco 2 - Anexo de provas
    # ----------------------------------------------------------------------
    with st.container(border=True):
        titulo_bloco("2", "Anexo de Provas (obrigatorio)")
        st.info(
            "Anexe aqui prints ou e-mails provando que o cliente ja havia sido orientado "
            "anteriormente. Obrigatorio: sem isso o caso e so assessoria, nao gera cobranca."
        )
        anexos = st.file_uploader(
            "Provas de aviso previo",
            type=["png", "jpg", "jpeg", "pdf"],
            accept_multiple_files=True,
            label_visibility="collapsed",
        )
        if anexos:
            st.caption(f"{len(anexos)} arquivo(s) anexado(s): " + ", ".join(a.name for a in anexos))

    # ----------------------------------------------------------------------
    # Bloco 3 - Analise, veredito e confirmacao
    # ----------------------------------------------------------------------
    with st.container(border=True):
        titulo_bloco("3", "Analise, Veredito e Confirmacao", "O motor de regras avalia o caso contra a tabela de precos oficial.")

        analisar_clicado = st.button("Analisar Caso e Calcular Preco", type="primary", use_container_width=True)

        if analisar_clicado:
            erros = []
            if not razao_social.strip():
                erros.append("Informe a Razao Social do cliente.")
            if not cnpj_valido(cnpj):
                erros.append("CNPJ invalido - informe os 14 digitos.")
            if not descricao_inconsistencia.strip():
                erros.append("Descreva a inconsistencia fiscal identificada.")
            if not operador_nome.strip():
                erros.append("Informe seu nome na barra lateral (Sessao) antes de analisar o caso.")
            if not anexos:
                erros.append(
                    "Anexe pelo menos uma prova de aviso previo (print, e-mail ou notificacao) - "
                    "sem isso o caso nao pode ser analisado, e so assessoria, nao gera cobranca."
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
                            f"Nao foi possivel conectar ao backend em {API_BASE_URL}. "
                            "Confirme se o servidor FastAPI esta rodando."
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
            tag_texto = "CORTESIA" if cortesia else "PASSIVEL DE COBRANCA"

            st.markdown(
                f"""
                <div class="painel-veredito {classe_painel}">
                    <span class="painel-tag">Proposta {proposta['numero_proposta']} - {tag_texto}</span>
                    <div class="painel-valor">{formatar_moeda(proposta['valor_final'])}</div>
                    <div><b>Classificacao:</b> {proposta['classificacao']}</div>
                    <div style="margin-top:0.4rem;">{proposta['diagnostico_texto']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if cortesia:
                st.warning(
                    "Caso classificado como cortesia: nada e enviado ao cliente pelo WhatsApp. "
                    "Registre o motivo internamente e crie a atividade normal do setor."
                )
            elif proposta["status"] == "aguardando_aprovacao_valor":
                st.info(
                    f"Proposta aguardando aprovacao de valor pela coordenacao de "
                    f"**{proposta['setor']}**. O operador nao tem mais acao aqui ate a decisao."
                )
            elif proposta["status"] == "rascunho":
                col_confirmar, col_revisar = st.columns(2)
                with col_confirmar:
                    if st.button("Confirmar Proposta", type="primary", use_container_width=True):
                        try:
                            resp = httpx.post(f"{API_BASE_URL}/propostas/{proposta['id']}/confirmar", timeout=15.0)
                        except httpx.ConnectError:
                            st.error(f"Nao foi possivel conectar ao backend em {API_BASE_URL}.")
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
                    if st.button("Solicitar Revisao de Valor a Coordenacao", use_container_width=True):
                        st.session_state.acao_pos_analise = "revisao"

                if st.session_state.acao_pos_analise == "revisao":
                    st.markdown("---")
                    st.write(
                        f"O valor sugerido sera enviado para aprovacao da coordenacao de "
                        f"**{proposta['setor']}**. O operador nao pode alterar o valor diretamente."
                    )
                    motivo_revisao = st.text_area(
                        "Justifique por que voce acha que o valor esta incorreto",
                        placeholder="Ex: cliente tem historico de bom pagador, ou caso tem particularidade nao coberta pela regra...",
                    )
                    if st.button("Enviar Solicitacao para Coordenacao"):
                        if not motivo_revisao.strip():
                            st.error("Informe a justificativa antes de enviar a solicitacao.")
                        else:
                            try:
                                resp = httpx.post(
                                    f"{API_BASE_URL}/propostas/{proposta['id']}/solicitar_revisao",
                                    json={"motivo": motivo_revisao},
                                    timeout=15.0,
                                )
                            except httpx.ConnectError:
                                st.error(f"Nao foi possivel conectar ao backend em {API_BASE_URL}.")
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
                    st.success(f"Cartao criado no Trello: {proposta['trello_card_url']}")
                else:
                    st.warning(
                        "Trello nao configurado neste ambiente (.env sem TRELLO_API_KEY/TOKEN) - "
                        "cartao NAO foi criado de verdade, so o status avancou."
                    )

                texto_whatsapp = montar_texto_whatsapp(
                    proposta,
                    st.session_state.razao_social_confirmada or razao_social,
                    st.session_state.descricao_confirmada or descricao_inconsistencia,
                )
                st.write("**Texto para copiar e enviar manualmente no WhatsApp:**")
                st.code(texto_whatsapp, language=None)
                st.caption("Sem links ou botoes - copie e cole na conversa comum com o cliente.")

    # ----------------------------------------------------------------------
    # Reiniciar
    # ----------------------------------------------------------------------
    st.divider()
    if st.button("Novo Caso"):
        reiniciar_caso()
        st.rerun()

    # ----------------------------------------------------------------------
    # Propostas em Negociacao - baixa manual da resposta do cliente
    # ----------------------------------------------------------------------
    st.divider()
    st.header("Propostas em Negociacao")
    st.caption(
        "Casos com proposta ja enviada manualmente pelo WhatsApp, aguardando a resposta do cliente. "
        "Registre aqui o que o cliente respondeu na conversa."
    )

    pendentes = buscar_propostas_aguardando(API_BASE_URL)
    if pendentes is None:
        st.warning(f"Nao foi possivel carregar as propostas pendentes de {API_BASE_URL}.")
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
            duvida_clicado = st.button("Cliente com Duvidas", use_container_width=True)

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
                st.error(f"Nao foi possivel conectar ao backend em {API_BASE_URL}.")
            else:
                if resp.status_code == 200:
                    st.success(f"Resposta '{resposta_escolhida}' registrada e cartao do Trello atualizado.")
                    st.rerun()
                else:
                    try:
                        detalhe = resp.json().get("detail", resp.text)
                    except ValueError:
                        detalhe = resp.text
                    st.error(f"Erro do backend ({resp.status_code}): {detalhe}")

    # ----------------------------------------------------------------------
    # Painel da Coordenacao / Gestao - aprovacao de valor com senha de assinatura
    # ----------------------------------------------------------------------
    st.divider()
    st.header("Painel da Coordenacao / Gestao")
    st.caption(
        "Casos onde o operador discordou do valor calculado e pediu revisao. "
        "So o coordenador do setor (com a propria senha) pode decidir aqui."
    )

    coordenadores = buscar_coordenadores(API_BASE_URL)
    if not coordenadores:
        st.warning(f"Nao foi possivel carregar coordenadores de {API_BASE_URL}.")
    else:
        opcoes_coordenador = {f"{c['nome']} ({c['setor']})": c for c in coordenadores}
        escolha_coordenador = st.selectbox("Coordenador(a) logado(a)", list(opcoes_coordenador.keys()))
        coordenador_atual = opcoes_coordenador[escolha_coordenador]

        pendentes_aprovacao = buscar_propostas_para_aprovar(API_BASE_URL)
        if pendentes_aprovacao is None:
            st.warning(f"Nao foi possivel carregar as propostas pendentes de aprovacao de {API_BASE_URL}.")
        else:
            pendentes_do_setor = [p for p in pendentes_aprovacao if p["setor"] == coordenador_atual["setor"]]

            if not pendentes_do_setor:
                st.info(f"Nenhuma proposta aguardando aprovacao no setor '{coordenador_atual['setor']}'.")
            else:
                opcoes_aprovacao = {
                    f"{p['numero_proposta']} - {p['razao_social']} - {formatar_moeda(p['valor_final'] or 0.0)}": p["id"]
                    for p in pendentes_do_setor
                }
                escolha_aprovacao = st.selectbox(
                    "Selecione o pedido de revisao", list(opcoes_aprovacao.keys()), key="aprovacao_escolha"
                )
                proposta_aprovacao_id = opcoes_aprovacao[escolha_aprovacao]

                detalhe = buscar_detalhe_proposta(API_BASE_URL, proposta_aprovacao_id)

                col_info, col_acao = st.columns(2)
                with col_info:
                    st.write(f"**Cliente:** {detalhe['razao_social']} (CNPJ {detalhe['cnpj']})")
                    st.write(f"**Operador:** {detalhe['operador_nome']}")
                    st.write(f"**Competencias:** {', '.join(detalhe['competencias'])}")
                    st.write(f"**Valor calculado pelo motor:** {formatar_moeda(detalhe['valor_sugerido'])}")
                    st.write(f"**Classificacao:** {detalhe['classificacao']}")
                    st.write("**Justificativa do operador para a revisao:**")
                    st.info(detalhe.get("motivo_solicitacao_revisao") or "(nenhuma justificativa registrada)")

                    if detalhe["anexos"]:
                        st.write("**Prova(s) anexada(s):**")
                        for anexo in detalhe["anexos"]:
                            url_arquivo = f"{API_BASE_URL}/propostas/{proposta_aprovacao_id}/anexos/{anexo['id']}/arquivo"
                            try:
                                conteudo = httpx.get(url_arquivo, timeout=10.0).content
                            except httpx.HTTPError:
                                st.caption(f"Nao foi possivel carregar {anexo['nome_arquivo']}.")
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
                        "Justificativa da decisao (obrigatoria)",
                        placeholder="Ex: mantive o valor calculado / reduzi por bom historico do cliente...",
                        key=f"motivo_ajuste_{proposta_aprovacao_id}",
                    )
                    senha_coordenador = st.text_input(
                        "Senha de Assinatura Eletronica", type="password",
                        key=f"senha_{proposta_aprovacao_id}",
                    )

                    if st.button("Aprovar e Criar Cartao no Trello", type="primary", use_container_width=True):
                        if not motivo_ajuste_coordenador.strip():
                            st.error("Informe a justificativa da decisao antes de aprovar.")
                        elif not senha_coordenador:
                            st.error("Informe a senha de assinatura eletronica.")
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
                                st.error(f"Nao foi possivel conectar ao backend em {API_BASE_URL}.")
                            else:
                                if resp.status_code == 200:
                                    resultado = resp.json()
                                    st.success(
                                        f"Proposta aprovada com valor final {formatar_moeda(resultado['valor_final'])}. "
                                        f"Status: {resultado['status']}."
                                    )
                                    if resultado.get("trello_card_url"):
                                        st.success(f"Cartao criado no Trello: {resultado['trello_card_url']}")
                                    else:
                                        st.warning(
                                            "Trello nao configurado neste ambiente - cartao NAO foi criado de "
                                            "verdade, so o status avancou."
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

1. Na barra lateral (**Sessao**), digite o seu nome. Nao precisa de senha - so pra registrar quem fez a analise.
2. Preencha os **Dados do Cliente e Caso**: Razao Social, CNPJ, Setor Responsavel, Porte, Competencias Afetadas, Regime Tributario, Complexidade e a Descricao da Inconsistencia Fiscal.
3. **Anexe a prova de aviso previo** (print de conversa, e-mail ou notificacao mostrando que o cliente ja foi avisado antes). Isso e **obrigatorio** - sem anexo, o sistema nao deixa nem analisar o caso.
4. Clique em **"Analisar Caso e Calcular Preco"** - o motor de regras calcula o valor automaticamente, sem ninguem decidir isso na mao.
5. Se concordar com o valor calculado, clique em **"Confirmar Proposta"** - isso cria o cartao no Trello (controle interno) e libera o texto pronto.
6. **Copie o texto** (tem um icone de copiar no canto do bloco de codigo) e **cole direto na conversa do WhatsApp comum** com o cliente - o sistema nao manda nada sozinho, nao tem link nem botao automatico.
7. Depois que o cliente responder pelo WhatsApp, volte na secao **"Propostas em Negociacao"**, selecione o caso pelo nome/numero e registre o que ele respondeu: **Aceite**, **Recusa** ou **Cliente com Duvidas**.

---

### ⚠️ Casos de Cortesia

Se voce colocar **0 (zero)** em "Competencias Afetadas", o sistema entende que **nao e pra cobrar** - e um caso de cortesia.

Nesse caso, **nao aparece nenhum texto pra copiar e nenhum cartao e criado pro cliente**. O sistema so mostra um aviso interno pra voce registrar o motivo e seguir com o atendimento normal do setor.

**Nao ligue nem avise o cliente que decidimos nao cobrar** - isso fica só registrado internamente.

---

### ⚠️ Se voce achar que o valor calculado esta errado

Voce **nao pode alterar o valor** diretamente - isso e proposital, pra manter o preco justo e igual pra todo mundo. Clique em **"Solicitar Revisao de Valor a Coordenacao"**, escreva o motivo, e a coordenacao do seu setor decide.

---

## \U0001f9ed Para a Coordenacao

Quando um operador pede revisao de valor, o caso aparece na secao **"Painel da Coordenacao / Gestao"**, no final da tela (aba Sistema).

**Como aprovar:**

1. Escolha o seu nome em **"Coordenador(a) logado(a)"**.
2. Selecione o caso na lista (so aparecem os casos do seu setor).
3. Confira os dados: valor calculado pelo motor, a justificativa do operador e **a prova anexada** (imagem aparece na tela, PDF vira botao de download).
4. Defina o **Valor Final** (pode manter o valor sugerido ou ajustar).
5. Escreva a **Justificativa da decisao** - obrigatorio, mesmo se for so "mantive o valor calculado".
6. Digite a sua **Senha de Assinatura Eletronica** pessoal.
7. Clique em **"Aprovar e Criar Cartao no Trello"**.

Se a senha estiver errada, o sistema bloqueia e mostra um erro em vermelho - ninguem aprova nada sem a senha certa. Se voce nao tem senha cadastrada ainda, fale com quem administra o sistema.
        """
    )
