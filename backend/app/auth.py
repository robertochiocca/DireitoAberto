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

_PBKDF2_ITERACOES = 240_000

VALIDADE_TOKEN = timedelta(hours=float(os.environ.get("DIREITO_ABERTO_TOKEN_VALIDADE_HORAS", 720)))

esquema_bearer = HTTPBearer(auto_error=False)

# Hash de uma senha qualquer, usado quando o e-mail não existe: o login
# calcula o PBKDF2 do mesmo jeito, e o tempo de resposta não revela quais
# e-mails têm conta.
_HASH_FICTICIO = None


def gerar_hash_senha(senha: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, _PBKDF2_ITERACOES)
    return f"{salt.hex()}:{dk.hex()}"


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


def revogar_todos(db: Session, usuario: Usuario) -> None:
    db.execute(delete(TokenSessao).where(TokenSessao.usuario_id == usuario.id))
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
