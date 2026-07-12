"""Retriever semântico (embeddings + ChromaDB) atrás da mesma interface do BM25.

Ativação por variável de ambiente:

    DIREITO_ABERTO_RETRIEVER=semantico

Requer `pip install chromadb`. Por padrão usa o embedder multilíngue de
qualidade (multilingual-e5-small, ver `embeddings.py`), baixado na primeira
execução; com `DIREITO_ABERTO_EMBEDDING=padrao`, usa o embedding nativo do
Chroma (MiniLM inglês — mais fraco em PT-BR). Sem dependências, sem modelo
ou sem rede, `criar_retriever()` cai automaticamente no BM25 — a API nunca
quebra por isso.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from uuid import uuid4

from .retrieval import DATA_PATH, Resultado, Retriever

logger = logging.getLogger(__name__)


class EmbeddingRetriever:
    """Busca vetorial sobre o corpus, com a mesma assinatura de `Retriever.buscar`.

    Com `embedder` (obrigatório para qualidade em PT-BR), os vetores são
    calculados aqui — consultas com prefixo "query: " e documentos com
    "passage: ", como o e5 exige. Sem `embedder`, usa o embedding padrão
    do Chroma.
    """

    def __init__(self, data_path: Path = DATA_PATH, embedder=None):
        import chromadb  # import tardio: dependência opcional

        # Reaproveita o carregamento/normalização do corpus do retriever lexical.
        self._base = Retriever(data_path)
        self.artigos = self._base.artigos
        self._embedder = embedder

        documentos = [
            f"{art['lei']} {art['artigo']}. {art['resumo']} {art['texto']}"
            for art in self.artigos
        ]
        self._client = chromadb.EphemeralClient()
        # O EphemeralClient compartilha estado no processo: nome único evita
        # colisão quando mais de um retriever é criado (ex.: em testes).
        self._collection = self._client.create_collection(
            f"legislacao-{uuid4().hex[:8]}", metadata={"hnsw:space": "cosine"}
        )
        self._collection.add(
            ids=[art["id"] for art in self.artigos],
            documents=documentos,
            metadatas=[{"tema": art["tema"]} for art in self.artigos],
            embeddings=embedder.embed_documentos(documentos) if embedder else None,
        )
        self._por_id = {art["id"]: art for art in self.artigos}

    def temas(self) -> list[str]:
        return self._base.temas()

    def buscar(
        self,
        pergunta: str,
        top_k: int = 4,
        score_minimo: float = 0.2,
        tema: str | None = None,
    ) -> list[Resultado]:
        consulta = (
            {"query_embeddings": [self._embedder.embed_consulta(pergunta)]}
            if self._embedder
            else {"query_texts": [pergunta]}
        )
        res = self._collection.query(
            **consulta,
            n_results=top_k,
            where={"tema": tema} if tema else None,
        )
        resultados = []
        for id_, dist in zip(res["ids"][0], res["distances"][0]):
            score = 1.0 - dist  # similaridade de cosseno
            if score < score_minimo:
                continue
            art = self._por_id[id_]
            resultados.append(
                Resultado(
                    id=art["id"],
                    lei=art["lei"],
                    artigo=art["artigo"],
                    tema=art["tema"],
                    texto=art["texto"],
                    resumo=art["resumo"],
                    fonte=art["fonte"],
                    score=round(score, 3),
                )
            )
        return resultados


def criar_retriever() -> Retriever | EmbeddingRetriever:
    """Fábrica: escolhe o motor de busca conforme o ambiente, com fallback seguro."""
    if os.environ.get("DIREITO_ABERTO_RETRIEVER", "bm25").lower() not in ("semantico", "semantic"):
        return Retriever()

    if os.environ.get("DIREITO_ABERTO_EMBEDDING", "multilingue") != "padrao":
        try:
            from .embeddings import EmbedderMultilingue

            retriever = EmbeddingRetriever(embedder=EmbedderMultilingue())
            logger.info("Retriever semântico (ChromaDB + multilingual-e5-small) ativado.")
            return retriever
        except Exception as exc:
            logger.warning("Embedder multilíngue indisponível (%s); tentando o padrão.", exc)

    try:
        retriever = EmbeddingRetriever()
        logger.info("Retriever semântico (ChromaDB, embedding padrão) ativado.")
        return retriever
    except Exception as exc:  # sem chromadb, sem modelo ou sem rede
        logger.warning("Retriever semântico indisponível (%s); usando BM25.", exc)
    return Retriever()
