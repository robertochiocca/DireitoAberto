"""Testes do estado de validação das respostas (app/validacao.py)."""

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import validacao
from app.main import app
from app.retrieval import Resultado, Retriever

client = TestClient(app)
MONITOR_REAL = Path(__file__).resolve().parent.parent / "data" / "monitor"


@pytest.fixture(scope="module")
def corpus():
    return {a["id"]: a for a in Retriever().artigos}


def _resultados(corpus, *ids, score=20.0):
    return [Resultado.de_artigo(corpus[i], score) for i in ids]


def _estado(resposta):
    return resposta.json()["validacao"]["estado"]


def test_fora_do_escopo_abstem():
    """Antes, "tirar o passaporte" voltava com a Lei de Registros Públicos."""
    resp = client.post("/api/v1/perguntar", json={"pergunta": "Como faço para tirar o passaporte?"})
    body = resp.json()
    assert body["artigos"] == []
    assert body["validacao"]["estado"] == "evidencia_insuficiente"
    assert "Não encontrei" in body["resposta"] and "Defensoria" in body["resposta"]
    forca = next(v for v in body["validacao"]["verificacoes"] if v["nome"] == "forca_da_evidencia")
    assert forca["ok"] is False and "limiar" in forca["detalhe"]


def test_limiar_nao_pega_todo_fora_do_escopo():
    """Falha conhecida e medida (docs/avaliacao): "multa por não votar" tem nota 7,1, acima do
    limiar, e ainda volta com dispositivos de outro assunto. Se um dia passar, atualize a avaliação."""
    resp = client.post("/api/v1/perguntar", json={"pergunta": "Qual é a multa por não votar na eleição?"})
    assert resp.json()["artigos"] and _estado(resp) != "evidencia_insuficiente"


def test_pergunta_coberta_tem_evidencia_suficiente():
    resp = client.post("/api/v1/perguntar", json={"pergunta": "Comprei pela internet e me arrependi da compra"})
    assert resp.json()["artigos"]
    assert _estado(resp) == "evidencia_suficiente"  # sem monitor nos testes: texto não conferido
    assert resp.json()["validacao"]["aviso"].startswith("Estes estados descrevem")


def test_texto_conferido_com_a_versao_oficial(monkeypatch, corpus):
    monkeypatch.setenv("DIREITO_ABERTO_MONITOR_DIR", str(MONITOR_REAL))
    v = validacao.avaliar(_resultados(corpus, "cdc-49", "cdc-42"), date(2026, 10, 19))
    assert v["estado"] == "fonte_e_versao_verificadas"
    condensado = validacao.avaliar(_resultados(corpus, "cdc-49", "cdc-26"), date(2026, 10, 19))
    assert condensado["estado"] == "evidencia_suficiente"
    detalhe = next(x for x in condensado["verificacoes"] if x["nome"] == "texto_conferido")["detalhe"]
    assert detalhe.startswith("1 de 2")


def test_norma_fora_de_vigor_ou_em_revisao_pede_revisao_humana():
    resp = client.post("/api/v1/perguntar", json={"pergunta": "fim da escala 6x1 jornada semanal"})
    assert "cf-7-xiii" in [a["id"] for a in resp.json()["artigos"]]
    assert _estado(resp) == "revisao_humana_recomendada"


def test_data_de_inicio_sem_revisao_e_fonte_desatualizada(monkeypatch):
    monkeypatch.setenv("DIREITO_ABERTO_DATA_REFERENCIA", "2026-11-02")
    resp = client.post("/api/v1/perguntar", json={"pergunta": "o SAC não me atende para cancelar"})
    assert _estado(resp) == "fonte_desatualizada_ou_indisponivel"


def test_conferencia_antiga_ou_ausente_e_fonte_desatualizada(corpus):
    v = validacao.avaliar(_resultados(corpus, "cdc-49"), date(2027, 12, 1))
    assert v["estado"] == "fonte_desatualizada_ou_indisponivel"
    sem_data = Resultado.de_artigo({**corpus["cdc-49"], "vigencia": {"status": "vigente"}}, 20.0)
    assert validacao.avaliar([sem_data], date(2026, 10, 19))["estado"] == "fonte_desatualizada_ou_indisponivel"


def test_mesmo_dispositivo_em_situacoes_diferentes_e_conflito(corpus):
    vigente = Resultado.de_artigo(corpus["cdc-49"], 20.0)
    antigo = Resultado.de_artigo({**corpus["cdc-49"], "id": "obsoleto-cdc-49",
                                  "vigencia": {"status": "revogada", "conferida_em": "2026-10-16"}}, 18.0)
    assert validacao.avaliar([vigente, antigo], date(2026, 10, 19))["estado"] == "conflito_de_fontes"
    # Incisos diferentes do mesmo artigo não conflitam.
    incisos = validacao.avaliar(_resultados(corpus, "cf-7", "cf-7-xiii"), date(2026, 10, 19))
    assert incisos["estado"] != "conflito_de_fontes"


def test_citacao_do_texto_gerado_sem_dispositivo_recuperado(corpus):
    artigos = _resultados(corpus, "cdc-18", "cdc-26")
    assert validacao.citacoes_sem_suporte("Pelo art. 18 e pelo art. 26 do CDC…", artigos) == []
    soltas = validacao.citacoes_sem_suporte("O art. 18 do CDC e o art. 51 garantem… Súmula 297.", artigos)
    assert soltas == ["art. 51", "Súmula 297"]
    v = validacao.avaliar(artigos, date(2026, 10, 19), texto_gerado="Conforme o art. 51 do CDC…")
    assert v["estado"] == "revisao_humana_recomendada"


def test_resposta_gerada_por_llm_passa_pela_verificacao(monkeypatch):
    # Desde a rodada 9.0, texto gerado que cita dispositivo não recuperado não é entregue: a API usa a resposta
    # extrativa e diz por quê (antes, o texto saía com um selo de "revisão recomendada").
    import app.main as main

    monkeypatch.setattr(main, "gerar_resposta", lambda *a, **k: "Pelo art. 999 da Lei, a loja deve trocar.")
    corpo = client.post("/api/v1/perguntar",
                        json={"pergunta": "A empresa não quer trocar meu notebook defeituoso"}).json()
    assert corpo["gerado_por_llm"] is False and "Pelo art. 999 da Lei, a loja deve trocar" not in corpo["resposta"]
    assert any(p["tipo"] == "dispositivo_nao_recuperado" and "art. 999" in p["detalhe"]
               for p in corpo["verificacao_do_texto"])
    assert corpo["politica"]["modo"] == "responder_com_ressalvas"
    assert any("não passou na verificação" in m for m in corpo["politica"]["motivos"])


def test_limiar_nao_se_aplica_ao_motor_nao_calibrado(corpus):
    fracos = _resultados(corpus, "cdc-49", score=0.82)  # similaridade de cosseno, outra escala
    assert not validacao.evidencia_insuficiente(fracos, calibrado=False)
    v = validacao.avaliar(fracos, date(2026, 10, 19), calibrado=False)
    assert v["estado"] == "fonte_localizada"
