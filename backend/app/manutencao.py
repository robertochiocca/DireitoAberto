"""Retenção: o que tem prazo para existir é apagado no prazo, mesmo que ninguém abra a tela correspondente.

Antes, documentos vencidos do leitor só eram apagados quando alguém usava o leitor, e tokens vencidos só
quando eram apresentados. Agora, a cada `INTERVALO_S` (padrão: 1 hora), a primeira requisição dispara a
limpeza de:

- sessões vencidas (`auth.VALIDADE_TOKEN`);
- documentos do leitor com `expira_em` no passado (dados de terceiros de processos);
- consultas com texto, de quem tem conta, mais velhas que `DIREITO_ABERTO_RETENCAO_HISTORICO_DIAS`
  (padrão: 365 dias — decisão de produto a confirmar; 0 desliga);
- eventos de auditoria mais velhos que `DIREITO_ABERTO_RETENCAO_AUDITORIA_DIAS` (padrão: 180 dias);
- feedbacks mais velhos que `DIREITO_ABERTO_RETENCAO_FEEDBACK_DIAS` (padrão: 365 dias; o que a triagem
  decidiu sobre o corpus fica no histórico do corpus, sem o comentário).

Sem tarefa em segundo plano nem agendador externo: a limpeza roda dentro de uma requisição, protegida por
trava, e falha nela nunca derruba a requisição.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import timedelta

from sqlalchemy import delete

from .auth import VALIDADE_TOKEN
from .db import Consulta, DocumentoProcesso, EventoAuditoria, Feedback, SessionLocal, TokenSessao, agora

logger = logging.getLogger(__name__)
INTERVALO_S = float(os.environ.get("DIREITO_ABERTO_MANUTENCAO_INTERVALO_S", 3600))
_trava = threading.Lock()
_ultima = 0.0


def _dias(variavel: str, padrao: int) -> int:
    return int(os.environ.get(variavel, padrao))


def expurgar(db) -> dict[str, int]:
    """Apaga o que venceu; devolve quantas linhas saíram de cada tabela."""
    momento = agora()
    apagados = {
        "sessoes": db.execute(delete(TokenSessao).where(TokenSessao.criado_em < momento - VALIDADE_TOKEN)).rowcount,
        "documentos": db.execute(delete(DocumentoProcesso).where(DocumentoProcesso.expira_em < momento)).rowcount,
    }
    if (dias := _dias("DIREITO_ABERTO_RETENCAO_HISTORICO_DIAS", 365)) > 0:
        # Só as de quem tem conta: a consulta anônima já não guarda o texto da pergunta.
        apagados["consultas"] = db.execute(delete(Consulta).where(
            Consulta.usuario_id.is_not(None), Consulta.criado_em < momento - timedelta(days=dias))).rowcount
    if (dias := _dias("DIREITO_ABERTO_RETENCAO_AUDITORIA_DIAS", 180)) > 0:
        apagados["auditoria"] = db.execute(delete(EventoAuditoria).where(
            EventoAuditoria.em < momento - timedelta(days=dias))).rowcount
    if (dias := _dias("DIREITO_ABERTO_RETENCAO_FEEDBACK_DIAS", 365)) > 0:
        apagados["feedbacks"] = db.execute(delete(Feedback).where(
            Feedback.criado_em < momento - timedelta(days=dias))).rowcount
    db.commit()
    return apagados


def expurgar_se_preciso() -> None:
    """Roda `expurgar` se a última limpeza tem mais de `INTERVALO_S` segundos. Nunca levanta exceção."""
    global _ultima
    if time.monotonic() - _ultima < INTERVALO_S or not _trava.acquire(blocking=False):
        return
    try:
        _ultima = time.monotonic()
        with SessionLocal() as db:
            apagados = expurgar(db)
        if any(apagados.values()):
            logger.info("retenção: apagados %s", apagados)
    except Exception:  # a limpeza nunca derruba a requisição que a disparou
        logger.exception("retenção: falha na limpeza periódica")
    finally:
        _trava.release()
