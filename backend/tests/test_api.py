import os

os.environ["DIREITO_ABERTO_USAR_LLM"] = "0"  # testes não chamam a API de LLM

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_saude():
    resp = client.get("/api/saude")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["artigos_no_corpus"] > 0


def test_listar_artigos():
    resp = client.get("/api/artigos")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == len(body["artigos"])
    assert {"id", "lei", "artigo", "tema", "resumo", "fonte"} <= set(body["artigos"][0])


def test_perguntar_caso_consumidor():
    resp = client.post(
        "/api/perguntar",
        json={"pergunta": "A empresa não quer trocar meu notebook defeituoso"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["gerado_por_llm"] is False  # LLM desligado nos testes
    ids = [a["id"] for a in body["artigos"]]
    assert "cdc-18" in ids
    assert "art. 18" in body["resposta"].lower() or "8.078" in body["resposta"]
    assert "Defensoria" in body["resposta"]
    assert body["aviso"]


def test_perguntar_sem_resultado_orienta_cidadao():
    resp = client.post("/api/perguntar", json={"pergunta": "receita de bolo de fubá"})
    assert resp.status_code == 200
    body = resp.json()
    assert "Defensoria" in body["resposta"]


def test_perguntar_valida_entrada():
    resp = client.post("/api/perguntar", json={"pergunta": "oi"})
    assert resp.status_code == 422
