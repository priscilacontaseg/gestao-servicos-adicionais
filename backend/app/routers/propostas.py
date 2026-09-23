import re
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlmodel import Session, select
from sqlalchemy import func

from .. import trello_client
from ..database import get_session
from ..models import (
    AnexoProposta,
    CargoFuncionario,
    Cliente,
    ComplexidadeCaso,
    Funcionario,
    PorteEmpresa,
    Proposta,
    RegimeTributario,
    RespostaCliente,
    Setor,
    StatusProposta,
)
from ..pricing import buscar_regra_vigente, calcular_precificacao
from ..schemas import AnexoResumo, AprovarValorIn, PropostaResumo, RegistrarRespostaIn, SolicitarRevisaoIn
from ..security import verificar_senha
from ..timeutils import agora_utc

router = APIRouter(prefix="/propostas", tags=["propostas"])


def _normalizar_cnpj(cnpj: str) -> str:
    return re.sub(r"\D", "", cnpj)


def _gerar_numero_proposta(session: Session) -> str:
    ano = datetime.utcnow().year
    prefixo = f"RET-{ano}-"
    existentes = session.exec(
        select(Proposta).where(Proposta.numero_proposta.like(f"{prefixo}%"))
    ).all()
    proximo = len(existentes) + 1
    return f"{prefixo}{proximo:04d}"


def _buscar_ou_criar_operador(session: Session, nome: str) -> Funcionario:
    """Operadores nao tem tela de cadastro nem senha - digitam o proprio nome
    e o sistema reaproveita o registro se o nome ja existir (case-insensitive)
    ou cria um novo na hora. Lista de operadores cresce organicamente."""
    nome_normalizado = nome.strip()
    existente = session.exec(
        select(Funcionario).where(
            func.lower(Funcionario.nome) == nome_normalizado.lower(),
            Funcionario.cargo == CargoFuncionario.OPERADOR,
        )
    ).first()
    if existente:
        if not existente.ativo:
            existente.ativo = True
            session.add(existente)
            session.commit()
            session.refresh(existente)
        return existente

    novo = Funcionario(nome=nome_normalizado, cargo=CargoFuncionario.OPERADOR, ativo=True)
    session.add(novo)
    session.commit()
    session.refresh(novo)
    return novo


def _buscar_coordenador_do_setor(session: Session, setor: Setor) -> Optional[Funcionario]:
    return session.exec(
        select(Funcionario).where(
            Funcionario.cargo == CargoFuncionario.COORDENADOR,
            Funcionario.setor == setor,
            Funcionario.ativo == True,  # noqa: E712
        )
    ).first()


def _mencao(funcionario: Optional[Funcionario]) -> str:
    """@username se tivermos o cadastro do Trello, senao so o nome (sem
    virar link/notificacao real, mas nao quebra o comentario)."""
    if funcionario and funcionario.trello_username:
        return f"@{funcionario.trello_username}"
    return funcionario.nome if funcionario else "responsavel"


def _criar_cartao_e_avancar(proposta: Proposta, session: Session) -> Proposta:
    """Transicao comum para AGUARDANDO_RESPOSTA: cria o cartao no Trello
    (uma unica vez, na lista fixa de malha fiscal) e registra o link. Se o
    Trello nao estiver configurado (.env sem chave/token), segue sem cartao
    real - util para rodar local/dev sem credenciais."""
    operador = session.get(Funcionario, proposta.operador_id)
    cliente = session.get(Cliente, proposta.cliente_id)

    titulo = (
        f"{cliente.razao_social} - Malha competencia(s) "
        f"{', '.join(proposta.competencias)} - R$ {proposta.valor_final:.2f}"
    )
    descricao = (
        f"Proposta: {proposta.numero_proposta}\n"
        f"Cliente: {cliente.razao_social} (CNPJ {cliente.cnpj})\n"
        f"Problema identificado: {proposta.descricao_inconsistencia}\n"
        f"Resultado da avaliacao: {proposta.classificacao}\n"
        f"Justificativa: {proposta.diagnostico_texto}\n"
        f"Valor: R$ {proposta.valor_final:.2f}\n"
        f"Operador responsavel: {operador.nome if operador else '-'}\n"
        f"Status: aguardando resposta do cliente (WhatsApp manual)."
    )
    membros = [operador.trello_member_id] if operador and operador.trello_member_id else []

    cartao = trello_client.criar_cartao(titulo, descricao, membros_ids=membros)
    if cartao:
        proposta.trello_card_id = cartao["id"]
        proposta.trello_card_url = cartao["url"]

    proposta.status = StatusProposta.AGUARDANDO_RESPOSTA
    proposta.data_envio = agora_utc()
    proposta.atualizado_em = agora_utc()
    session.add(proposta)
    session.commit()
    session.refresh(proposta)
    return proposta


@router.post("/analisar", response_model=Proposta)
def analisar_proposta(
    razao_social: str = Form(...),
    cnpj: str = Form(...),
    setor: Setor = Form(...),
    porte_empresa: PorteEmpresa = Form(...),
    complexidade: ComplexidadeCaso = Form(...),
    regime_tributario: RegimeTributario = Form(...),
    qtd_competencias: int = Form(...),
    descricao_inconsistencia: str = Form(...),
    operador_nome: str = Form(...),
    anexos: List[UploadFile] = File(default=[]),
    session: Session = Depends(get_session),
) -> Proposta:
    if not operador_nome.strip():
        raise HTTPException(400, "Informe o nome do operador.")
    operador = _buscar_ou_criar_operador(session, operador_nome)

    anexos_validos = [a for a in anexos if a.filename]
    if not anexos_validos:
        raise HTTPException(
            400,
            "E obrigatorio anexar pelo menos uma prova de aviso previo (print, e-mail ou "
            "notificacao) para analisar o caso. Sem prova de que o cliente ja foi avisado "
            "antes, o caso e so assessoria - nao gera cobranca.",
        )
    tem_provas = True

    cnpj_normalizado = _normalizar_cnpj(cnpj)
    if len(cnpj_normalizado) != 14:
        raise HTTPException(400, "CNPJ invalido - informe os 14 digitos.")

    cliente = session.exec(
        select(Cliente).where(Cliente.cnpj == cnpj_normalizado)
    ).first()
    if cliente is None:
        cliente = Cliente(
            cnpj=cnpj_normalizado,
            razao_social=razao_social,
        )
    else:
        cliente.razao_social = razao_social
    session.add(cliente)
    session.commit()
    session.refresh(cliente)

    regra = None
    if qtd_competencias > 0:
        regra = buscar_regra_vigente(session, regime_tributario)
        if regra is None:
            raise HTTPException(
                400,
                f"Nenhuma regra de precificacao vigente para o regime "
                f"'{regime_tributario.value}'. Rode o seed (app/seed.py) ou cadastre uma regra.",
            )

    resultado = calcular_precificacao(regra, qtd_competencias, complexidade, tem_provas)

    proposta = Proposta(
        numero_proposta=_gerar_numero_proposta(session),
        cliente_id=cliente.id,
        operador_id=operador.id,
        setor=setor,
        porte_empresa=porte_empresa,
        complexidade=complexidade,
        regime_tributario=regime_tributario,
        qtd_competencias=qtd_competencias,
        competencias=[f"Competencia {i + 1}" for i in range(qtd_competencias)],
        descricao_inconsistencia=descricao_inconsistencia,
        regra_precificacao_id=regra.id if regra else None,
        classificacao=resultado["classificacao"],
        diagnostico_texto=resultado["diagnostico"],
        valor_sugerido=resultado["valor_sugerido"],
        valor_final=resultado["valor_sugerido"],
        status=StatusProposta.RASCUNHO,
    )
    session.add(proposta)
    session.commit()
    session.refresh(proposta)

    for anexo in anexos_validos:
        conteudo = anexo.file.read()
        session.add(
            AnexoProposta(
                proposta_id=proposta.id,
                nome_arquivo=anexo.filename,
                tipo_mime=anexo.content_type or "application/octet-stream",
                tamanho_bytes=len(conteudo),
                conteudo=conteudo,
                enviado_por_id=operador.id,
            )
        )
    session.commit()
    session.refresh(proposta)
    return proposta


@router.post("/{proposta_id}/confirmar", response_model=Proposta)
def confirmar_proposta(proposta_id: int, session: Session = Depends(get_session)) -> Proposta:
    """Operador aceita o valor calculado (sem discordar) -> pronto para
    negociar manualmente com o cliente. Cria o cartao no Trello agora."""
    proposta = session.get(Proposta, proposta_id)
    if proposta is None:
        raise HTTPException(404, "Proposta nao encontrada.")
    if proposta.qtd_competencias <= 0:
        raise HTTPException(400, "Proposta de cortesia nao gera negociacao com o cliente.")
    if proposta.status != StatusProposta.RASCUNHO:
        raise HTTPException(
            400,
            f"Proposta em status '{proposta.status.value}' nao pode ser confirmada "
            "(precisa estar em 'rascunho').",
        )
    return _criar_cartao_e_avancar(proposta, session)


@router.post("/{proposta_id}/solicitar_revisao", response_model=Proposta)
def solicitar_revisao(
    proposta_id: int,
    payload: SolicitarRevisaoIn,
    session: Session = Depends(get_session),
) -> Proposta:
    proposta = session.get(Proposta, proposta_id)
    if proposta is None:
        raise HTTPException(404, "Proposta nao encontrada.")
    if not payload.motivo.strip():
        raise HTTPException(400, "Justificativa obrigatoria para solicitar revisao.")
    if proposta.status != StatusProposta.RASCUNHO:
        raise HTTPException(
            400,
            f"Proposta em status '{proposta.status.value}' nao pode ser enviada para revisao "
            "(precisa estar em 'rascunho', logo apos a analise).",
        )

    proposta.status = StatusProposta.AGUARDANDO_APROVACAO_VALOR
    proposta.motivo_solicitacao_revisao = payload.motivo
    proposta.atualizado_em = agora_utc()
    session.add(proposta)
    session.commit()
    session.refresh(proposta)
    return proposta


@router.post("/{proposta_id}/aprovar_valor", response_model=Proposta)
def aprovar_valor(
    proposta_id: int,
    payload: AprovarValorIn,
    session: Session = Depends(get_session),
) -> Proposta:
    proposta = session.get(Proposta, proposta_id)
    if proposta is None:
        raise HTTPException(404, "Proposta nao encontrada.")
    if proposta.status != StatusProposta.AGUARDANDO_APROVACAO_VALOR:
        raise HTTPException(
            400,
            f"Proposta em status '{proposta.status.value}' nao esta aguardando "
            "aprovacao de valor.",
        )

    aprovador = session.get(Funcionario, payload.funcionario_id)
    if not aprovador or not aprovador.ativo:
        raise HTTPException(400, "Funcionario aprovador invalido ou inativo.")

    if not verificar_senha(payload.senha, aprovador.senha_hash):
        raise HTTPException(401, "Senha de assinatura eletronica incorreta.")

    tem_alcada = aprovador.cargo == CargoFuncionario.GESTOR or (
        aprovador.cargo == CargoFuncionario.COORDENADOR
        and aprovador.setor == proposta.setor
    )
    if not tem_alcada:
        raise HTTPException(
            403,
            f"{aprovador.nome} (cargo={aprovador.cargo.value}, setor="
            f"{aprovador.setor.value if aprovador.setor else '-'}) nao tem alcada para "
            f"aprovar valores do setor '{proposta.setor.value}'.",
        )

    if not payload.motivo_ajuste.strip():
        raise HTTPException(400, "Justificativa do ajuste e obrigatoria.")

    proposta.valor_final = payload.valor_final
    proposta.ajustado_por_id = aprovador.id
    proposta.motivo_ajuste = payload.motivo_ajuste
    proposta.ajustado_em = agora_utc()
    session.add(proposta)
    session.commit()
    session.refresh(proposta)

    return _criar_cartao_e_avancar(proposta, session)


@router.post("/{proposta_id}/registrar_resposta", response_model=Proposta)
def registrar_resposta(
    proposta_id: int,
    payload: RegistrarRespostaIn,
    session: Session = Depends(get_session),
) -> Proposta:
    """Baixa manual: o operador leu a resposta do cliente no WhatsApp comum e
    registra aqui. O cartao NUNCA muda de lista - so recebe comentario (e,
    conforme o caso, um novo membro)."""
    proposta = session.get(Proposta, proposta_id)
    if proposta is None:
        raise HTTPException(404, "Proposta nao encontrada.")
    if proposta.status != StatusProposta.AGUARDANDO_RESPOSTA:
        raise HTTPException(
            400,
            f"Proposta em status '{proposta.status.value}' nao esta aguardando resposta do cliente.",
        )

    agora = agora_utc()
    valor = proposta.valor_final or 0.0
    data_hora_texto = agora.strftime("%d/%m/%Y as %Hh%M")

    if payload.resposta == RespostaCliente.ACEITO:
        ana = session.exec(
            select(Funcionario).where(
                Funcionario.cargo == CargoFuncionario.FINANCEIRO, Funcionario.ativo == True  # noqa: E712
            )
        ).first()
        comentario = (
            f"{_mencao(ana)} Cliente aceitou a proposta de R$ {valor:.2f} em "
            f"{data_hora_texto}. Favor incluir na cobranca."
        )
        if proposta.trello_card_id:
            trello_client.adicionar_comentario(proposta.trello_card_id, comentario)
            if ana and ana.trello_member_id:
                trello_client.adicionar_membro(proposta.trello_card_id, ana.trello_member_id)
        proposta.status = StatusProposta.ACEITA

    elif payload.resposta == RespostaCliente.NAO_ACEITO:
        coordenador = _buscar_coordenador_do_setor(session, proposta.setor)
        prazo_texto = (
            proposta.prazo_fiscal.strftime("%d/%m/%Y") if proposta.prazo_fiscal else "nao informado"
        )
        comentario = (
            f"{_mencao(coordenador)} Cliente recusou a proposta de R$ {valor:.2f} em "
            f"{data_hora_texto}. A inconsistencia permanece sem correcao. Prazo fiscal: "
            f"{prazo_texto}. Risco de multa se nao regularizado. Favor decidir: cortesia "
            f"excepcional, nova negociacao ou formalizacao do risco ao cliente."
        )
        if proposta.trello_card_id:
            trello_client.adicionar_comentario(proposta.trello_card_id, comentario)
            if coordenador and coordenador.trello_member_id:
                trello_client.adicionar_membro(proposta.trello_card_id, coordenador.trello_member_id)
        proposta.status = StatusProposta.NAO_ACEITA

    else:  # FALAR_COM_RESPONSAVEL
        operador = session.get(Funcionario, proposta.operador_id)
        comentario = (
            f"Cliente pediu para falar com o responsavel antes de decidir (registrado em "
            f"{data_hora_texto}). {operador.nome if operador else 'Operador'} deve assumir "
            "o contato manualmente."
        )
        if proposta.trello_card_id:
            trello_client.adicionar_comentario(proposta.trello_card_id, comentario)
        proposta.status = StatusProposta.FALAR_COM_RESPONSAVEL

    proposta.resposta = payload.resposta
    proposta.data_resposta = agora
    proposta.atualizado_em = agora
    session.add(proposta)
    session.commit()
    session.refresh(proposta)
    return proposta


@router.get("/{proposta_id}/detalhe")
def obter_proposta_detalhe(proposta_id: int, session: Session = Depends(get_session)) -> dict:
    """Usado pelo Painel da Coordenacao: dados completos da proposta (valor
    sugerido, competencias, justificativa do operador) + lista de anexos."""
    proposta = session.get(Proposta, proposta_id)
    if proposta is None:
        raise HTTPException(404, "Proposta nao encontrada.")
    cliente = session.get(Cliente, proposta.cliente_id)
    operador = session.get(Funcionario, proposta.operador_id)
    anexos = session.exec(
        select(AnexoProposta).where(AnexoProposta.proposta_id == proposta_id)
    ).all()

    dados = proposta.dict()
    dados["razao_social"] = cliente.razao_social if cliente else "-"
    dados["cnpj"] = cliente.cnpj if cliente else "-"
    dados["operador_nome"] = operador.nome if operador else "-"
    dados["anexos"] = [
        AnexoResumo(
            id=a.id, nome_arquivo=a.nome_arquivo, tipo_mime=a.tipo_mime, tamanho_bytes=a.tamanho_bytes
        ).dict()
        for a in anexos
    ]
    return dados


@router.get("/{proposta_id}/anexos/{anexo_id}/arquivo")
def baixar_anexo(proposta_id: int, anexo_id: int, session: Session = Depends(get_session)) -> Response:
    anexo = session.get(AnexoProposta, anexo_id)
    if anexo is None or anexo.proposta_id != proposta_id:
        raise HTTPException(404, "Anexo nao encontrado.")
    return Response(
        content=anexo.conteudo,
        media_type=anexo.tipo_mime,
        headers={"Content-Disposition": f'inline; filename="{anexo.nome_arquivo}"'},
    )


@router.get("", response_model=List[PropostaResumo])
def listar_propostas(
    status: Optional[StatusProposta] = None,
    session: Session = Depends(get_session),
) -> List[PropostaResumo]:
    query = select(Proposta)
    if status:
        query = query.where(Proposta.status == status)
    propostas = session.exec(query.order_by(Proposta.criado_em)).all()

    resumos = []
    for proposta in propostas:
        cliente = session.get(Cliente, proposta.cliente_id)
        resumos.append(
            PropostaResumo(
                id=proposta.id,
                numero_proposta=proposta.numero_proposta,
                razao_social=cliente.razao_social if cliente else "-",
                cnpj=cliente.cnpj if cliente else "-",
                setor=proposta.setor.value,
                valor_final=proposta.valor_final,
                status=proposta.status.value,
                data_envio=proposta.data_envio.isoformat() if proposta.data_envio else None,
            )
        )
    return resumos
