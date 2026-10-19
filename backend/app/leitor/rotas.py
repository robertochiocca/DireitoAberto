"""API do leitor de processos (`/api/v1/documentos`).

Privacidade por desenho (docs/security-audit.md, "Riscos específicos do
módulo de leitura de processos"):

- todo documento tem dono; quem não é o dono recebe 404, como se o documento
  não existisse (não confirma que o identificador é válido);
- o identificador é aleatório (128 bits), não sequencial;
- só o texto extraído é guardado, nunca o arquivo, e só até `expira_em`
  (`DIREITO_ABERTO_DOCUMENTOS_RETENCAO_HORAS`, padrão 24 h); vencidos são
  apagados a cada acesso ao módulo;
- nada é enviado a provedor de IA: a leitura e as respostas são locais.

O processo fictício de demonstração (`/documentos/exemplo`) é público: não
tem dado pessoal e serve para conhecer o leitor sem criar conta.
"""

from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .. import auth
from ..db import DocumentoProcesso, Usuario, agora, get_db
from ..documentos import DocumentoGrandeDemais, DocumentoInvalido, ler_upload_limitado
from ..seguranca import limitar
from .analise import analisar
from .extracao import DocumentoExtraido, Pagina, extrair
from .perguntas import responder

RETENCAO = timedelta(hours=float(os.environ.get("DIREITO_ABERTO_DOCUMENTOS_RETENCAO_HORAS", 24)))
MAX_POR_USUARIO = int(os.environ.get("DIREITO_ABERTO_DOCUMENTOS_POR_USUARIO", 10))
LIMITE_BYTES = int(float(os.environ.get("DIREITO_ABERTO_LEITOR_MAX_MB", 20)) * 1024 * 1024)
EXEMPLO = Path(__file__).resolve().parent.parent.parent / "data" / "exemplos" / "processo-ficticio.pdf"

router = APIRouter(prefix="/documentos", tags=["leitor de processos"])


class Pergunta(BaseModel):
    pergunta: str = Field(..., min_length=3, max_length=500, examples=["O juiz já tomou alguma decisão?"])


# ---------------------------------------------------------------- serialização
def _paginas_para_json(doc: DocumentoExtraido) -> str:
    return json.dumps(
        [{"numero": p.numero, "texto": p.texto, "estado": p.estado, "folha": p.folha} for p in doc.paginas],
        ensure_ascii=False,
    )


def _doc_do_registro(registro: DocumentoProcesso) -> DocumentoExtraido:
    paginas = [Pagina(**p) for p in json.loads(registro.paginas_json)]
    return DocumentoExtraido(registro.nome, registro.hash_sha256, paginas)


def _utc(momento: datetime) -> datetime:
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)  # SQLite perde o fuso


def _resumo_registro(r: DocumentoProcesso) -> dict:
    return {
        "id": r.id,
        "nome": r.nome,
        "total_paginas": r.total_paginas,
        "criado_em": _utc(r.criado_em).isoformat(),
        "expira_em": _utc(r.expira_em).isoformat(),
    }


def _completo(doc: DocumentoExtraido, analise: dict, meta: dict) -> dict:
    return {
        **meta,
        "paginas": [
            {"numero": p.numero, "folha": p.folha, "estado": p.estado, "texto": p.texto} for p in doc.paginas
        ],
        "analise": analise,
    }


# ---------------------------------------------------------------- acesso
def expurgar_vencidos(db: Session) -> None:
    db.execute(delete(DocumentoProcesso).where(DocumentoProcesso.expira_em <= agora()))
    db.commit()


def _do_dono(db: Session, usuario: Usuario, documento_id: str) -> DocumentoProcesso:
    expurgar_vencidos(db)
    registro = db.scalar(
        select(DocumentoProcesso).where(
            DocumentoProcesso.id == documento_id, DocumentoProcesso.usuario_id == usuario.id
        )
    )
    if registro is None:
        # Mesmo 404 para "não existe" e "é de outra pessoa".
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    return registro


@lru_cache(maxsize=1)
def _exemplo() -> tuple[DocumentoExtraido, dict]:
    doc = extrair(EXEMPLO.name, EXEMPLO.read_bytes())
    return doc, analisar(doc)


# ---------------------------------------------------------------- rotas
@router.get("/exemplo")
def exemplo():
    """Processo FICTÍCIO de demonstração, já analisado (público, sem conta)."""
    doc, analise = _exemplo()
    return _completo(doc, analise, {"id": "exemplo", "nome": doc.nome, "total_paginas": doc.total_paginas,
                                    "ficticio": True})


@router.get("/exemplo/arquivo", response_class=FileResponse)
def arquivo_exemplo():
    """O PDF fictício original, para o visualizador mostrar ao lado do texto extraído.

    É a única resposta que pode ir num iframe — da própria origem (o Next
    repassa /api, então para o navegador a origem é a do site).
    """
    return FileResponse(
        EXEMPLO,
        media_type="application/pdf",
        headers={"X-Frame-Options": "SAMEORIGIN", "Content-Security-Policy": "frame-ancestors 'self'",
                 "Content-Disposition": f'inline; filename="{EXEMPLO.name}"'},
    )


@router.post("/exemplo/perguntar", dependencies=[Depends(limitar("perguntar"))])
def perguntar_exemplo(payload: Pergunta):
    doc, analise = _exemplo()
    return responder(doc, analise, payload.pergunta)


@router.post("", status_code=201, dependencies=[Depends(limitar("documento"))])
async def enviar(
    arquivo: UploadFile = File(..., description="Processo em .pdf (ou .txt; páginas separadas por form feed)."),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(auth.usuario_obrigatorio),
):
    expurgar_vencidos(db)
    guardados = db.scalar(
        select(func.count(DocumentoProcesso.id)).where(DocumentoProcesso.usuario_id == usuario.id)
    ) or 0
    if guardados >= MAX_POR_USUARIO:
        raise HTTPException(
            status_code=409,
            detail=f"Você já tem {guardados} documentos guardados. Apague algum para enviar outro.",
        )
    try:
        conteudo = await ler_upload_limitado(arquivo, LIMITE_BYTES)
        # Extração e análise usam CPU: fora do laço de eventos.
        doc = await run_in_threadpool(extrair, arquivo.filename or "documento.pdf", conteudo)
        analise = await run_in_threadpool(analisar, doc)
    except DocumentoGrandeDemais as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except DocumentoInvalido as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    registro = DocumentoProcesso(
        id=secrets.token_hex(16),
        usuario_id=usuario.id,
        nome=(arquivo.filename or "documento.pdf")[:255],
        hash_sha256=doc.hash_sha256,
        total_paginas=doc.total_paginas,
        paginas_json=_paginas_para_json(doc),
        analise_json=json.dumps(analise, ensure_ascii=False),
        expira_em=agora() + RETENCAO,
    )
    db.add(registro)
    db.commit()
    return _completo(doc, analise, _resumo_registro(registro))


@router.get("")
def listar(db: Session = Depends(get_db), usuario: Usuario = Depends(auth.usuario_obrigatorio)):
    expurgar_vencidos(db)
    registros = db.scalars(
        select(DocumentoProcesso)
        .where(DocumentoProcesso.usuario_id == usuario.id)
        .order_by(DocumentoProcesso.criado_em.desc())
    ).all()
    return [_resumo_registro(r) for r in registros]


@router.get("/{documento_id}")
def obter(documento_id: str, db: Session = Depends(get_db), usuario: Usuario = Depends(auth.usuario_obrigatorio)):
    registro = _do_dono(db, usuario, documento_id)
    return _completo(_doc_do_registro(registro), json.loads(registro.analise_json), _resumo_registro(registro))


@router.post("/{documento_id}/perguntar", dependencies=[Depends(limitar("perguntar"))])
def perguntar(
    documento_id: str,
    payload: Pergunta,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(auth.usuario_obrigatorio),
):
    registro = _do_dono(db, usuario, documento_id)
    return responder(_doc_do_registro(registro), json.loads(registro.analise_json), payload.pergunta)


@router.delete("/{documento_id}", status_code=204)
def apagar(documento_id: str, db: Session = Depends(get_db), usuario: Usuario = Depends(auth.usuario_obrigatorio)):
    registro = _do_dono(db, usuario, documento_id)
    db.delete(registro)
    db.commit()
