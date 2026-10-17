"""Testes do benchmark de armadilha temporal.

Cobrem a integridade do dataset (24 pares extraídos do dossiê de fontes) e a
mecânica do experimento — inclusive o braço de mitigação, que é o que liga o
benchmark à camada de vigência do corpus.
"""

import pytest

from app.benchmark import (
    PREFIXO_DISTRATOR,
    carregar_casos,
    distrator_de,
    rodar_bm25,
)
from app.retrieval import Retriever

CAMPOS = {
    "id", "pergunta", "dispositivo", "id_corpus", "tema",
    "vigente", "obsoleto", "mudou_por", "palavras_chave",
}


@pytest.fixture(scope="module")
def casos():
    return carregar_casos()


@pytest.fixture(scope="module")
def relatorio():
    return rodar_bm25()


# ----------------------------------------------------------- dataset
def test_dataset_tem_os_24_pares_do_dossie(casos):
    assert len(casos) == 24


def test_todo_caso_tem_os_campos_e_ids_unicos(casos):
    ids = [c["id"] for c in casos]
    assert len(ids) == len(set(ids)), "ids duplicados no dataset"
    for caso in casos:
        faltando = CAMPOS - set(caso)
        assert not faltando, f"{caso['id']} sem campos {faltando}"
        assert caso["palavras_chave"], f"{caso['id']} sem palavras-chave"
        assert caso["pergunta"].strip().endswith("?"), f"{caso['id']}: pergunta malformada"


def test_vigente_e_obsoleto_sao_diferentes(casos):
    """Se os dois textos coincidissem, o caso não seria uma armadilha."""
    for caso in casos:
        assert caso["vigente"].strip() != caso["obsoleto"].strip(), caso["id"]


def test_id_corpus_aponta_para_dispositivo_existente(casos):
    existentes = {a["id"] for a in Retriever().artigos}
    for caso in casos:
        if caso["id_corpus"]:
            assert caso["id_corpus"] in existentes, (
                f"{caso['id']} aponta para {caso['id_corpus']}, que não está no corpus"
            )


# ----------------------------------------------------------- distratores
def test_distrator_sem_rotulo_se_passa_por_vigente(casos):
    d = distrator_de(casos[0])
    assert d["id"].startswith(PREFIXO_DISTRATOR)
    assert d["vigencia"]["status"] == "vigente", "o distrator precisa enganar o sistema"
    assert d["texto"] == casos[0]["obsoleto"]


def test_distrator_rotulado_entra_como_revogado(casos):
    d = distrator_de(casos[0], rotulado=True)
    assert d["vigencia"]["status"] == "revogada"
    assert d["vigencia"]["alterada_por"] == [casos[0]["mudou_por"]]
    assert casos[0]["vigente"] in d["vigencia"]["nota"]


# ----------------------------------------------------------- experimento
def test_metricas_sao_coerentes(relatorio):
    r = relatorio
    assert r.total == 24
    assert 0 <= r.cobertos <= r.total
    assert r.vigentes_recuperados <= r.cobertos
    assert r.distratores_recuperados <= r.total
    assert r.inversoes <= r.cobertos
    for pct in (r.cobertura_pct, r.recall_vigente_pct, r.contaminacao_pct,
                r.inversao_pct, r.resposta_contaminada_pct):
        assert 0.0 <= pct <= 100.0


def test_fonte_desatualizada_contamina_as_respostas(relatorio):
    """O achado central: indexar o texto de 2006 envenena o resultado."""
    assert relatorio.contaminacao_pct > 50, (
        "o experimento perdeu o sentido se o distrator quase não é recuperado"
    )
    assert relatorio.respostas_contaminadas > 0


def test_rotulo_de_vigencia_neutraliza_o_dano(relatorio):
    """Mitigação: o distrator continua sendo recuperado, mas agora avisado."""
    assert relatorio.com_mitigacao
    assert relatorio.distratores_rotulados_recuperados > 0
    assert relatorio.respostas_alertadas == relatorio.distratores_rotulados_recuperados, (
        "toda resposta que cita texto revogado deve trazer o aviso"
    )
    assert relatorio.alerta_pct == 100.0


def test_quando_o_corpus_cobre_o_caso_ele_e_recuperado(relatorio):
    cobertos = [c for c in relatorio.casos if c.coberto]
    assert cobertos, "o dataset deveria ter casos cobertos pelo corpus"
    assert all(c.vigente_recuperado for c in cobertos)


def test_relatorio_serializa_para_json(relatorio):
    dados = relatorio.para_json()
    assert dados["retriever"] == "bm25"
    assert dados["metricas"]["casos"] == 24
    assert "mitigacao_por_rotulo" in dados["metricas"]
    assert len(dados["casos"]) == 24
    assert {"id", "pergunta", "coberto", "inversao"} <= set(dados["casos"][0])
