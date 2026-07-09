"""Retriever semântico (embeddings + ChromaDB) atrás da mesma interface do BM25.

Ativação por variável de ambiente:

    DIREITO_ABERTO_RETRIEVER=semantico

Requer `pip install chromadb`. O embedding padrão do Chroma (all-MiniLM-L6-v2
via ONNX) é baixado na primeira execução; sem rede ou sem a dependência,
`criar_retriever()` cai automaticamente no BM25 — a API nunca quebra por isso.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from .retrieval import DATA_PATH, Resultado, Retriever

logger = logging.getLogger(__name__)


class EmbeddingRetriever:
    """Busca vetorial sobre o corpus, com a mesma assinatura de `Retriever.buscar`."""

    def __init__(self, data_path: Path = DATA_PATH):
        import chromadb  # import tardio: dependência opcional

        # Reaproveita o carregamento/normalização do corpus do retriever lexical.
        self._base = Retriever(data_path)
        self.artigos = self._base.artigos

        self._client = chromadb.EphemeralClient()
        self._collection = self._client.create_collection(
            "legislacao", metadata={"hnsw:space": "cosine"}
        )
        self._collection.add(
            ids=[art["id"] for art in self.artigos],
            documents=[
                f"{art['lei']} {art['artigo']}. {art['resumo']} {art['texto']}"
                for art in self.artigos
            ],
            metadatas=[{"tema": art["tema"]} for art in self.artigos],
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
        res = self._collection.query(
            query_texts=[pergunta],
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
    if os.environ.get("DIREITO_ABERTO_RETRIEVER", "bm25").lower() in ("semantico", "semantic"):
        try:
            retriever = EmbeddingRetriever()
            logger.info("Retriever semântico (ChromaDB) ativado.")
            return retriever
        except Exception as exc:  # sem chromadb, sem modelo ou sem rede
            logger.warning("Retriever semântico indisponível (%s); usando BM25.", exc)
    return Retriever()
