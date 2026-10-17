"""Testes da camada de vigência.

Um RAG jurídico erra de dois jeitos: citando regra revogada como se valesse,
ou citando regra futura antes da hora. Estes testes cobrem o segundo caso,
que é o risco vivo da base hoje (EC 141/2026 e novo SAC em vacatio legis).
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.llm import _montar_contexto, resposta_extrativa, rotulo_vigencia
from app.main import app
from app.retrieval import Retriever

client = TestClient(app)

STATUS_VALIDOS = {"vigente", "em_vacatio", "revogada", "inconstitucional"}


@pytest.fixture(scope="module")
def retriever():
    return Retriever()


def test_todo_dispositivo_tem_bloco_de_vigencia(retriever):
    for art in retriever.artigos:
        v = art.get("vigencia")
        assert v, f"{art['id']} sem bloco de vigência"
        assert v["status"] in STATUS_VALIDOS, f"{art['id']}: status {v['status']!r}"
        assert v["conferida_em"], f"{art['id']} sem data de conferência"


def test_em_vacatio_exige_data_futura_coerente(retriever):
    em_vacatio = [a for a in retriever.artigos if a["vigencia"]["status"] == "em_vacatio"]
    assert em_vacatio, "a base deveria ter normas publicadas e ainda sem efeito"
    for art in em_vacatio:
        inicio = art["vigencia"]["entra_em_vigor_em"]
        assert inicio, f"{art['id']}: em vacatio sem data de início"
        date.fromisoformat(inicio)  # levanta se o formato estiver errado


def test_resultado_carrega_vigencia_e_expoe_em_vigor(retriever):
    por_id = {r.id: r for r in retriever.buscar("escala 6x1 jornada semanal", top_k=8)}
    assert "cf-7-xiii" in por_id, "a nova jornada deveria ser recuperável"
    novo = por_id["cf-7-xiii"]
    assert novo.em_vigor is False
    assert novo.vigencia["entra_em_vigor_em"]

    antigo = retriever.buscar("produto com defeito troca", top_k=1)[0]
    assert antigo.em_vigor is True


def test_sac_novo_e_recuperavel(retriever):
    ids = [r.id for r in retriever.buscar("o SAC não me atende para cancelar", top_k=5)]
    assert "decreto13135-sac" in ids, ids


def test_rotulo_de_vigencia_por_status():
    assert "Em vigor" in rotulo_vigencia({"status": "vigente"})
    futuro = rotulo_vigencia({"status": "em_vacatio", "entra_em_vigor_em": "2026-11-02"})
    assert "AINDA NÃO ESTÁ EM VIGOR" in futuro and "02/11/2026" in futuro
    assert "REVOGADO" in rotulo_vigencia({"status": "revogada"})


def test_contexto_do_llm_marca_a_situacao(retriever):
    artigos = retriever.buscar("escala 6x1 jornada semanal", top_k=8)
    contexto = _montar_contexto([a for a in artigos if a.id == "cf-7-xiii"])
    assert "AINDA NÃO ESTÁ EM VIGOR" in contexto
    assert "Nota de vigência:" in contexto


def test_modo_extrativo_avisa_norma_futura(retriever):
    artigos = [a for a in retriever.buscar("escala 6x1 jornada semanal", top_k=8)
               if a.id == "cf-7-xiii"]
    texto = resposta_extrativa("qual a jornada máxima?", artigos)
    assert "AINDA NÃO ESTÁ EM VIGOR" in texto
    assert "Defensoria" in texto


def test_api_filtra_por_status():
    resp = client.get("/api/v1/artigos", params={"status": "em_vacatio"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 2
    ids = {a["id"] for a in body["artigos"]}
    assert {"cf-7-xiii", "decreto13135-sac"} <= ids
    assert all(a["vigencia"]["status"] == "em_vacatio" for a in body["artigos"])


def test_api_perguntar_devolve_vigencia():
    resp = client.post("/api/v1/perguntar", json={"pergunta": "quantas horas posso trabalhar por semana"})
    assert resp.status_code == 200
    artigos = resp.json()["artigos"]
    assert artigos and all("vigencia" in a for a in artigos)
    assert all(a["vigencia"]["status"] in STATUS_VALIDOS for a in artigos)


def test_fila_de_vigencia():
    resp = client.get("/api/v1/vigencia", params={"dias": 3650})
    assert resp.status_code == 200
    body = resp.json()
    entrando = body["entram_em_vigor"]
    assert entrando, "deveria listar as normas em vacatio"
    assert all(i["dias_restantes"] > 0 for i in entrando)
    datas = [i["entra_em_vigor_em"] for i in entrando]
    assert datas == sorted(datas), "a fila deve vir em ordem cronológica"


def test_fila_de_vigencia_respeita_janela():
    curta = client.get("/api/v1/vigencia", params={"dias": 1}).json()["entram_em_vigor"]
    longa = client.get("/api/v1/vigencia", params={"dias": 3650}).json()["entram_em_vigor"]
    assert len(curta) <= len(longa)


def test_estatisticas_reportam_status_e_conferencia():
    body = client.get("/api/v1/estatisticas").json()
    assert body["dispositivos_por_status"]["em_vacatio"] >= 2
    assert body["dispositivos_por_status"]["vigente"] > 0
    assert body["vigencia_conferida_em"]


def test_conferencia_agregada_reporta_o_pior_caso():
    """A data do corpus é a mais antiga, não a mais recente.

    O campo existe para dizer o quanto a base pode estar velha; usar a
    conferência mais recente anunciaria um frescor que a base não tem.
    """
    body = client.get("/api/v1/estatisticas").json()
    datas = [a["vigencia"]["conferida_em"]
             for a in client.get("/api/v1/artigos").json()["artigos"]]
    assert body["vigencia_conferida_em"] == min(datas)
