"""Hash simples da senha de assinatura eletronica dos coordenadores.

SHA-256 sem salt e suficiente para o objetivo real disto (evitar que um
operador digite qualquer coisa e aprove um valor em nome de outra pessoa),
mas NAO e uma pratica de autenticacao de producao - antes de expor este
sistema fora da rede interna, trocar por um hash com salt (ex: bcrypt) e por
autenticacao de verdade (sessao/token), nao um campo de senha por requisicao.
"""

import hashlib


def hash_senha(senha: str) -> str:
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()


def verificar_senha(senha_digitada: str, senha_hash_armazenado: str | None) -> bool:
    if not senha_hash_armazenado or not senha_digitada:
        return False
    return hash_senha(senha_digitada) == senha_hash_armazenado
