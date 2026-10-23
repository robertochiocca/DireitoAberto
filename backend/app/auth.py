"""Autenticação: senhas com PBKDF2 (stdlib) e tokens de sessão opacos.

Sem dependências externas de criptografia: hash de senha via
`hashlib.pbkdf2_hmac` com salt aleatório, e tokens aleatórios guardados
no banco apenas como SHA-256 (vazamento do banco não vaza tokens).

Tokens valem `DIREITO_ABERTO_TOKEN_VALIDADE_HORAS` (padrão: 30 dias) a partir
da criação e podem ser revogados (logout). A validade é calculada sobre a
coluna `criado_em`, que já existia: bancos em produção não precisam de
migração.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete
from sqlalchemy.orm import Session

from .db import TokenSessao, Usuario, agora, get_db

# OWASP (2023+) recomenda 600 mil iterações para PBKDF2-HMAC-SHA256. O hash guarda o algoritmo e o número
# de iterações ("pbkdf2_sha256$600000$salt$dk"): subir o número no futuro não invalida senhas — o login
# refaz o hash antigo. Hashes do formato anterior ("salt:dk", 240 mil iterações) continuam valendo.
ITERACOES_PADRAO = 600_000
_PBKDF2_ITERACOES = int(os.environ.get("DIREITO_ABERTO_PBKDF2_ITERACOES", ITERACOES_PADRAO))
_ITERACOES_LEGADAS = 240_000

VALIDADE_TOKEN = timedelta(hours=float(os.environ.get("DIREITO_ABERTO_TOKEN_VALIDADE_HORAS", 720)))

esquema_bearer = HTTPBearer(auto_error=False)

# Hash de uma senha qualquer, usado quando o e-mail não existe: o login
# calcula o PBKDF2 do mesmo jeito, e o tempo de resposta não revela quais
# e-mails têm conta.
_HASH_FICTICIO = None


def gerar_hash_senha(senha: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, _PBKDF2_ITERACOES)
    return f"pbkdf2_sha256${_PBKDF2_ITERACOES}${salt.hex()}${dk.hex()}"


def _parametros(armazenado: str) -> tuple[int, bytes, str] | None:
    """(iterações, salt, dk em hex) do hash guardado, nos dois formatos."""
    try:
        if armazenado.startswith("pbkdf2_sha256$"):
            _, iteracoes, salt_hex, dk_hex = armazenado.split("$")
            return int(iteracoes), bytes.fromhex(salt_hex), dk_hex
        salt_hex, dk_hex = armazenado.split(":")
        return _ITERACOES_LEGADAS, bytes.fromhex(salt_hex), dk_hex
    except ValueError:
        return None


def precisa_refazer_hash(armazenado: str) -> bool:
    parametros = _parametros(armazenado)
    return parametros is None or parametros[0] < _PBKDF2_ITERACOES or not armazenado.startswith("pbkdf2_sha256$")


def normalizar_email(email: str) -> str:
    return email.strip().lower()


def verificar_senha_ou_gastar_tempo(senha: str, armazenado: str | None) -> bool:
    """Como `verificar_senha`, mas com o mesmo custo quando não há conta."""
    global _HASH_FICTICIO
    if armazenado is None:
        if _HASH_FICTICIO is None:
            _HASH_FICTICIO = gerar_hash_senha(secrets.token_hex(16))
        verificar_senha(senha, _HASH_FICTICIO)
        return False
    return verificar_senha(senha, armazenado)


def verificar_senha(senha: str, armazenado: str) -> bool:
    parametros = _parametros(armazenado)
    if parametros is None:
        return False
    iteracoes, salt, dk_hex = parametros
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, iteracoes)
    return hmac.compare_digest(dk.hex(), dk_hex)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def criar_token(db: Session, usuario: Usuario) -> str:
    token = secrets.token_urlsafe(32)
    db.add(TokenSessao(token_hash=_hash_token(token), usuario_id=usuario.id))
    db.commit()
    return token


def _expirado(registro: TokenSessao) -> bool:
    criado = registro.criado_em
    if criado.tzinfo is None:  # SQLite devolve datas sem fuso; foram gravadas em UTC
        criado = criado.replace(tzinfo=timezone.utc)
    return agora() - criado > VALIDADE_TOKEN


def _usuario_do_token(db: Session, token: str) -> Usuario | None:
    registro = db.get(TokenSessao, _hash_token(token))
    if registro is None:
        return None
    if _expirado(registro):
        db.delete(registro)
        db.commit()
        return None
    return registro.usuario


def revogar_token(db: Session, token: str) -> None:
    db.execute(delete(TokenSessao).where(TokenSessao.token_hash == _hash_token(token)))
    db.commit()


def revogar_todos(db: Session, usuario: Usuario, exceto: str | None = None) -> None:
    """Encerra todas as sessões da conta — menos a do token `exceto`, quando dado (troca de senha)."""
    consulta = delete(TokenSessao).where(TokenSessao.usuario_id == usuario.id)
    if exceto is not None:
        consulta = consulta.where(TokenSessao.token_hash != _hash_token(exceto))
    db.execute(consulta)
    db.commit()


def usuario_opcional(
    credenciais: HTTPAuthorizationCredentials | None = Depends(esquema_bearer),
    db: Session = Depends(get_db),
) -> Usuario | None:
    """Identifica o usuário se houver token válido; anônimo caso contrário."""
    if credenciais is None:
        return None
    return _usuario_do_token(db, credenciais.credentials)


def usuario_obrigatorio(
    credenciais: HTTPAuthorizationCredentials | None = Depends(esquema_bearer),
    db: Session = Depends(get_db),
) -> Usuario:
    usuario = None
    if credenciais is not None:
        usuario = _usuario_do_token(db, credenciais.credentials)
    if usuario is None:
        raise HTTPException(status_code=401, detail="Token ausente ou inválido.")
    return usuario
