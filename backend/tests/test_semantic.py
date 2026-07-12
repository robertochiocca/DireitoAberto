"""Testes do retriever semântico (opt-in).

Rodam apenas quando o chromadb está instalado E o modelo e5 já foi baixado
(primeira execução do retriever semântico faz o download). Sem isso, são
pulados — o CI e ambientes mínimos continuam verdes com o BM25.
"""

import pytest

pytest.importorskip("chromadb")

from app.embeddings import ARQUIVOS, CACHE_DIR  # noqa: E402

_modelo_em_cache = all((CACHE_DIR / nome).exists() for nome in ARQUIVOS)
pytestmark = pytest.mark.skipif(
    not _modelo_em_cache, reason="modelo multilingual-e5-small não baixado"
)


@pytest.fixture(scope="module")
def retriever():
    from app.embeddings import EmbedderMultilingue
    from app.semantic import EmbeddingRetriever

    return EmbeddingRetriever(embedder=EmbedderMultilingue())


def test_vetores_normalizados_dim_384():
    from app.embeddings import EmbedderMultilingue

    emb = EmbedderMultilingue()
    vetor = emb.embed_consulta("produto com defeito")
    assert len(vetor) == 384
    norma = sum(v * v for v in vetor) ** 0.5
    assert abs(norma - 1.0) < 1e-3


# Parafrases sem sobreposição lexical com o corpus — onde o BM25 não alcança.
PARAFRASES = [
    ("a operadora não autorizou meu procedimento médico", "lei9656-35c"),
    ("a companhia aérea me deixou na mão no aeroporto", "anac-400"),
    ("quero cobrar o pai do meu filho que não paga nada", "cc-1694"),
]


@pytest.mark.parametrize("pergunta,esperado", PARAFRASES)
def test_parafrase_sem_palavras_do_corpus(retriever, pergunta, esperado):
    ids = [r.id for r in retriever.buscar(pergunta, top_k=3)]
    assert esperado in ids, f"esperava {esperado} no top-3, veio {ids}"


def test_filtro_por_tema(retriever):
    resultados = retriever.buscar("prazo para cobrança", tema="tributos", top_k=3)
    assert all(r.tema == "tributos" for r in resultados)


def test_duas_instancias_no_mesmo_processo():
    # regressão: o EphemeralClient compartilha estado; nomes de coleção únicos
    from app.embeddings import EmbedderMultilingue
    from app.semantic import EmbeddingRetriever

    emb = EmbedderMultilingue()
    EmbeddingRetriever(embedder=emb)
    EmbeddingRetriever(embedder=emb)
