"""Autenticação: senhas com PBKDF2 (stdlib) e tokens de sessão opacos.

Sem dependências externas de criptografia: hash de senha via
`hashlib.pbkdf2_hmac` com salt aleatório, e tokens aleatórios guardados
no banco apenas como SHA-256 (vazamento do banco não vaza tokens).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db import TokenSessao, Usuario, get_db

_PBKDF2_ITERACOES = 240_000

_bearer = HTTPBearer(auto_error=False)


def gerar_hash_senha(senha: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, _PBKDF2_ITERACOES)
    return f"{salt.hex()}:{dk.hex()}"


def verificar_senha(senha: str, armazenado: str) -> bool:
    try:
        salt_hex, dk_hex = armazenado.split(":")
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(salt_hex), _PBKDF2_ITERACOES)
    return hmac.compare_digest(dk.hex(), dk_hex)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def criar_token(db: Session, usuario: Usuario) -> str:
    token = secrets.token_urlsafe(32)
    db.add(TokenSessao(token_hash=_hash_token(token), usuario_id=usuario.id))
    db.commit()
    return token


def _usuario_do_token(db: Session, token: str) -> Usuario | None:
    registro = db.get(TokenSessao, _hash_token(token))
    return registro.usuario if registro else None


def usuario_opcional(
    credenciais: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Usuario | None:
    """Identifica o usuário se houver token válido; anônimo caso contrário."""
    if credenciais is None:
        return None
    return _usuario_do_token(db, credenciais.credentials)


def usuario_obrigatorio(
    credenciais: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Usuario:
    usuario = None
    if credenciais is not None:
        usuario = _usuario_do_token(db, credenciais.credentials)
    if usuario is None:
        raise HTTPException(status_code=401, detail="Token ausente ou inválido.")
    return usuario
