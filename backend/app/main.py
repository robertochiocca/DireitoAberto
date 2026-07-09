"""API do DireitoAberto — RAG jurídico sobre legislação brasileira."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .llm import gerar_resposta, resposta_extrativa
from .retrieval import DATA_PATH, Retriever, normalizar

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

AVISO_LEGAL = (
    "O DireitoAberto oferece informação jurídica geral, não aconselhamento "
    "sobre casos concretos. Procure a Defensoria Pública (gratuita) ou um "
    "advogado antes de tomar decisões."
)

app = FastAPI(
    title="DireitoAberto API",
    description="Letramento jurídico com RAG sobre a legislação brasileira.",
    version="0.2.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

retriever = Retriever()

# Contador em memória (zera a cada deploy). A persistência em banco
# (PostgreSQL) está no roadmap.
_contador_consultas = 0
_contador_lock = threading.Lock()


def _registrar_consulta() -> None:
    global _contador_consultas
    with _contador_lock:
        _contador_consultas += 1


class Pergunta(BaseModel):
    pergunta: str = Field(..., min_length=3, max_length=1000, examples=[
        "A empresa não quer trocar meu notebook defeituoso"
    ])
    tema: str | None = Field(
        None, description="Filtra a busca por área (ex.: consumidor, trabalho, familia)."
    )


class ArtigoEncontrado(BaseModel):
    id: str
    lei: str
    artigo: str
    tema: str
    texto: str
    resumo: str
    fonte: str
    score: float


class Resposta(BaseModel):
    resposta: str
    artigos: list[ArtigoEncontrado]
    gerado_por_llm: bool
    aviso: str = AVISO_LEGAL


@app.get("/api/saude")
def saude():
    return {"status": "ok", "artigos_no_corpus": len(retriever.artigos)}


@app.get("/api/estatisticas")
def estatisticas():
    leis = {art["lei"] for art in retriever.artigos}
    atualizado_em = datetime.fromtimestamp(
        DATA_PATH.stat().st_mtime, tz=timezone.utc
    )
    return {
        "leis_indexadas": len(leis),
        "artigos_indexados": len(retriever.artigos),
        "temas": retriever.temas(),
        "consultas_realizadas": _contador_consultas,
        "base_atualizada_em": atualizado_em.isoformat(),
    }


@app.get("/api/artigos")
def listar_artigos(
    tema: str | None = Query(None, description="Filtra por área temática."),
    busca: str | None = Query(
        None, description="Filtra por trecho do nome da lei ou do artigo (ex.: '8.078' ou 'art. 18')."
    ),
):
    artigos = retriever.artigos
    if tema:
        artigos = [a for a in artigos if a["tema"] == tema]
    if busca:
        alvo = normalizar(busca)
        artigos = [
            a for a in artigos
            if all(t in normalizar(f"{a['lei']} {a['artigo']}") for t in alvo)
        ]
    return {
        "total": len(artigos),
        "artigos": [
            {k: art[k] for k in ("id", "lei", "artigo", "tema", "resumo", "fonte")}
            for art in artigos
        ],
    }


@app.post("/api/perguntar", response_model=Resposta)
def perguntar(payload: Pergunta):
    _registrar_consulta()
    artigos = retriever.buscar(payload.pergunta, tema=payload.tema)
    texto_llm = gerar_resposta(payload.pergunta, artigos)
    return Resposta(
        resposta=texto_llm or resposta_extrativa(payload.pergunta, artigos),
        artigos=[ArtigoEncontrado(**vars(a)) for a in artigos],
        gerado_por_llm=texto_llm is not None,
    )


@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/dados.js", include_in_schema=False)
def frontend_dados():
    return FileResponse(FRONTEND_DIR / "dados.js")
