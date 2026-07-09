"""API do DireitoAberto — RAG jurídico sobre legislação brasileira."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .llm import gerar_resposta, resposta_extrativa
from .retrieval import Retriever

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

AVISO_LEGAL = (
    "O DireitoAberto oferece informação jurídica geral, não aconselhamento "
    "sobre casos concretos. Procure a Defensoria Pública (gratuita) ou um "
    "advogado antes de tomar decisões."
)

app = FastAPI(
    title="DireitoAberto API",
    description="Letramento jurídico com RAG sobre a legislação brasileira.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

retriever = Retriever()


class Pergunta(BaseModel):
    pergunta: str = Field(..., min_length=3, max_length=1000, examples=[
        "A empresa não quer trocar meu notebook defeituoso"
    ])


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


@app.get("/api/artigos")
def listar_artigos():
    return {
        "total": len(retriever.artigos),
        "artigos": [
            {k: art[k] for k in ("id", "lei", "artigo", "tema", "resumo", "fonte")}
            for art in retriever.artigos
        ],
    }


@app.post("/api/perguntar", response_model=Resposta)
def perguntar(payload: Pergunta):
    artigos = retriever.buscar(payload.pergunta)
    texto_llm = gerar_resposta(payload.pergunta, artigos)
    return Resposta(
        resposta=texto_llm or resposta_extrativa(payload.pergunta, artigos),
        artigos=[ArtigoEncontrado(**vars(a)) for a in artigos],
        gerado_por_llm=texto_llm is not None,
    )


@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(FRONTEND_DIR / "index.html")
