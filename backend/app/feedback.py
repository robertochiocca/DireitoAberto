"""Feedback controlado: quem usa aponta um problema num dispositivo citado; uma pessoa faz a triagem.

Regras (docs/feedback.md):

- feedback **nunca** muda nada sozinho — nem o texto da base, nem a vigência, nem a confiança, nem a
  política de resposta. Nenhum módulo de busca, validação ou geração lê esta tabela. Ele entra numa
  fila; a triagem humana (`scripts/feedback.py`) decide; o máximo que uma triagem "procedente" faz é
  abrir uma pendência de revisão na entrada do corpus, registrada no histórico com responsável e motivo;
- muitos feedbacks iguais não viram correção automática: viram prioridade na fila (`feedback.py resumo`);
- dado mínimo: dispositivo, categoria e, se a pessoa quiser, um comentário curto. A pergunta não é
  copiada. CPF, e-mail, telefone e número de processo escritos no comentário são mascarados antes de
  gravar. Com conta, o feedback fica ligado a ela (sai na exportação e é apagado com a conta);
- não é usado para treinar modelo nem compartilhado; é apagado depois de
  `DIREITO_ABERTO_RETENCAO_FEEDBACK_DIAS` (padrão 365; app/manutencao.py).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import auditoria, auth
from .db import Feedback, Usuario, get_db
from .retrieval import DATA_PATH
from .seguranca import endereco_do_cliente, verificar_limite

CATEGORIAS = {
    "texto_nao_confere": "O texto mostrado não confere com a lei",
    "norma_revogada_ou_alterada": "A norma foi revogada ou alterada",
    "dispositivo_nao_se_aplica": "O dispositivo não tem a ver com a pergunta",
    "explicacao_confusa": "A explicação está confusa, incompleta ou errada",
    "outro": "Outro problema",
}
ESTADOS = ("novo", "procedente", "improcedente", "duplicado")
MAX_COMENTARIO = 600
AVISO = ("Recebido. Uma pessoa vai conferir. O retorno não muda a resposta na hora nem corrige a base "
         "automaticamente.")

_DADOS_PESSOAIS = [
    # número de processo (CNJ) antes do CPF: os dois têm grupos de dígitos
    (re.compile(r"\b\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4}\b"), "[número de processo removido]"),
    (re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"), "[CPF removido]"),
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[e-mail removido]"),
    (re.compile(r"(?:\+?55\s?)?\(?\b\d{2}\)?\s?9?\d{4}[-\s]?\d{4}\b"), "[telefone removido]"),
]


def mascarar(texto: str) -> str:
    """Mascara CPF, e-mail, telefone e número de processo — o comentário é sobre a lei, não sobre a pessoa."""
    for regex, troca in _DADOS_PESSOAIS:
        texto = regex.sub(troca, texto)
    return texto


_ids: dict = {"chave": None, "ids": frozenset()}


def ids_do_corpus() -> frozenset[str]:
    caminho = Path(DATA_PATH)
    estado = caminho.stat()
    chave = (estado.st_mtime_ns, estado.st_size)
    if _ids["chave"] != chave:
        artigos = json.loads(caminho.read_text(encoding="utf-8"))["artigos"]
        _ids.update(chave=chave, ids=frozenset(a["id"] for a in artigos))
    return _ids["ids"]


class FeedbackEntrada(BaseModel):
    dispositivo_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9-]+$")
    categoria: Literal["texto_nao_confere", "norma_revogada_ou_alterada", "dispositivo_nao_se_aplica",
                       "explicacao_confusa", "outro"]
    comentario: str | None = Field(None, max_length=MAX_COMENTARIO)


class FeedbackRecebido(BaseModel):
    id: int
    estado: str
    aviso: str


router = APIRouter(tags=["feedback"])


@router.post("/feedback", status_code=201, response_model=FeedbackRecebido)
def enviar_feedback(
    payload: FeedbackEntrada,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(auth.usuario_opcional),
):
    """Aponta um problema num dispositivo citado. Vai para triagem humana; não muda a base sozinho."""
    endereco = endereco_do_cliente(request)
    verificar_limite("feedback", endereco)
    if payload.dispositivo_id not in ids_do_corpus():
        raise HTTPException(status_code=404, detail="Dispositivo não encontrado na base.")
    comentario = mascarar(" ".join(payload.comentario.split())) if payload.comentario else None
    registro = Feedback(usuario_id=usuario.id if usuario else None, dispositivo_id=payload.dispositivo_id,
                        categoria=payload.categoria, comentario=comentario or None)
    db.add(registro)
    auditoria.registrar(db, "feedback_enviado", usuario_id=usuario.id if usuario else None, endereco=endereco)
    db.commit()
    return FeedbackRecebido(id=registro.id, estado=registro.estado, aviso=AVISO)
