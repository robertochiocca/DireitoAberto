"""Testes da comparação de motores de busca.

Não dependem do retriever semântico: usam o BM25 e, onde a mecânica pede dois
motores, um segundo motor de mentira.
"""

import pytest

from collections import defaultdict

from app.comparacao import (
    CONJUNTOS,
    ROTULOS,
    carregar_casos_busca,
    carregar_conjuntos,
    carregar_julgamentos,
    comparar,
    fundir_rrf,
    perguntas_com_gabarito,
)
from app.retrieval import Retriever


@pytest.fixture(scope="module")
def bm25():
    return Retriever()


@pytest.fixture(scope="module")
def tema(bm25):
    return {a["id"]: a["tema"] for a in bm25.artigos}


def _buscador(retriever):
    return lambda q, k: [r.id for r in retriever.buscar(q, top_k=k)]


# ----------------------------------------------------------- dados
def test_gabarito_aponta_para_dispositivos_do_corpus(bm25):
    existentes = {a["id"] for a in bm25.artigos}
    casos = carregar_casos_busca()
    assert len(casos) == 62
    faltando = [(q, e) for q, e in casos if e not in existentes]
    assert not faltando, faltando


def test_julgamentos_tem_rotulos_validos_e_ids_do_corpus(bm25):
    existentes = {a["id"] for a in bm25.artigos}
    for pergunta, rotulos in carregar_julgamentos().items():
        for aid, rotulo in rotulos.items():
            assert rotulo in ROTULOS, f"{pergunta!r}: rótulo {rotulo!r} em {aid}"
            assert aid in existentes, f"{pergunta!r}: {aid} não está no corpus"
        assert "relevante" in rotulos.values(), f"{pergunta!r} sem nenhum artigo relevante"


def test_julgamentos_separam_calibracao_de_validacao():
    conjuntos = carregar_conjuntos()
    assert set(conjuntos.values()) == set(CONJUNTOS)
    assert set(conjuntos) == set(carregar_julgamentos())


def test_parafrases_recebem_o_mesmo_rotulo():
    """Perguntas com o mesmo artigo no gabarito são paráfrases: um artigo
    candidato comum às duas tem de receber o mesmo rótulo nas duas."""
    gabarito = dict(perguntas_com_gabarito())
    rotulos_por_par = defaultdict(dict)
    for pergunta, rotulos in carregar_julgamentos().items():
        for aid, rotulo in rotulos.items():
            rotulos_por_par[(gabarito[pergunta], aid)][pergunta] = rotulo
    divergentes = {par: r for par, r in rotulos_por_par.items() if len(set(r.values())) > 1}
    assert not divergentes, divergentes


def test_perguntas_julgadas_tem_gabarito():
    """Toda pergunta julgada também diz qual é o artigo certo."""
    gabarito = dict(perguntas_com_gabarito())
    for pergunta, rotulos in carregar_julgamentos().items():
        assert pergunta in gabarito, f"{pergunta!r} fora de casos_busca.json"
        assert rotulos.get(gabarito[pergunta]) == "relevante", pergunta


# ----------------------------------------------------------- fusão
def test_rrf_premia_o_consenso_entre_motores():
    # "b" está bem colocado nas duas listas; "a" só lidera uma delas.
    fundida = fundir_rrf([["a", "b", "c"], ["b", "c", "a"]], top=3)
    assert fundida[0] == "b"
    assert len(fundida) == len(set(fundida)) == 3


def test_rrf_respeita_o_top_e_aceita_itens_de_uma_lista_so():
    assert fundir_rrf([["a", "b"], ["c"]], top=2) == ["a", "c"]


# ----------------------------------------------------------- comparação
def test_bm25_acha_o_artigo_certo_e_tem_todo_resultado_julgado(bm25, tema):
    """Trava os julgamentos em sincronia com o BM25: se uma mudança na busca
    puser no top-4 um artigo que ninguém rotulou, o ruído deixa de ser medido
    — e este teste avisa para rotular."""
    (m,) = comparar({"BM25": _buscador(bm25)}, tema)
    assert m.esperado_top3 == m.perguntas == 86
    assert not m.nao_julgados, f"rotule em data/relevancia_julgada.json: {m.nao_julgados}"
    assert m.vagas_julgadas == sum(len(m.resultados[q]) for q in carregar_julgamentos())
    assert sum(sum(c.values()) for c in m.julgados_por_conjunto.values()) == m.vagas_julgadas


def test_com_dois_motores_entra_a_fusao(bm25, tema):
    invertido = lambda q, k: list(reversed(_buscador(bm25)(q, k)))  # noqa: E731
    medicoes = comparar({"BM25": _buscador(bm25), "outro": invertido}, tema)
    assert [m.motor for m in medicoes] == ["BM25", "outro", "híbrido (RRF)"]
    assert medicoes[-1].ms_por_pergunta is None
    assert all(len(r) <= 4 for r in medicoes[-1].resultados.values())


def test_fusao_usa_so_os_motores_indicados(bm25, tema):
    buscar = _buscador(bm25)
    so_um = comparar({"BM25": buscar, "cópia": buscar}, tema, fundir=["BM25"])
    assert [m.motor for m in so_um] == ["BM25", "cópia"]  # um motor só não se funde
    dois = comparar({"BM25": buscar, "cópia": buscar, "extra": buscar}, tema, fundir=["BM25", "cópia"])
    assert dois[-1].motor == "híbrido (RRF)"
