"""Trilha de auditoria das operações sensíveis — sem conteúdo pessoal.

Registra o quê, quando e com que resultado: `login`, `login_falha`, `login_bloqueado`, `conta_criada`,
`sessao_encerrada`, `sessoes_encerradas`, `senha_trocada`, `conta_excluida`, `dados_exportados`,
`historico_apagado`, `documento_enviado`, `documento_apagado`, `feedback_enviado`. A conta entra como pseudônimo (HMAC-SHA256
do id com um segredo do servidor), o endereço como prefixo de rede (/24 no IPv4, /48 no IPv6). Pergunta,
documento, e-mail e senha nunca entram.

Sem `DIREITO_ABERTO_SEGREDO_AUDITORIA`, o segredo é sorteado a cada início do processo: os pseudônimos não
se ligam entre reinícios. Em produção, configure o segredo (e guarde-o fora do banco).
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import os
import secrets

from sqlalchemy.orm import Session

from .db import EventoAuditoria

logger = logging.getLogger("direitoaberto.auditoria")
_SEGREDO = (os.environ.get("DIREITO_ABERTO_SEGREDO_AUDITORIA") or secrets.token_hex(32)).encode()


def pseudonimo(usuario_id: int | None) -> str | None:
    if usuario_id is None:
        return None
    return hmac.new(_SEGREDO, f"usuario:{usuario_id}".encode(), hashlib.sha256).hexdigest()[:32]


def prefixo_de_rede(endereco: str | None) -> str | None:
    try:
        ip = ipaddress.ip_address((endereco or "").strip())
    except ValueError:
        return None
    rede = ipaddress.ip_network(f"{ip}/{24 if ip.version == 4 else 48}", strict=False)
    return str(rede)


def registrar(db: Session, evento: str, *, usuario_id: int | None = None, endereco: str | None = None,
              resultado: str = "ok") -> None:
    """Grava o evento (na transação de quem chamou) e emite uma linha de log estruturada, sem dados pessoais."""
    registro = EventoAuditoria(evento=evento, conta=pseudonimo(usuario_id), rede=prefixo_de_rede(endereco),
                               resultado=resultado)
    db.add(registro)
    logger.info("auditoria evento=%s resultado=%s conta=%s rede=%s", evento, resultado, registro.conta, registro.rede)
