"""Recuperação temporal (app/temporal.py, app/consulta.py, app/avaliacao_temporal.py). Sem rede."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.avaliacao_temporal import avaliar_versoes
from app.main import app
from app.retrieval import Resultado
from app.temporal import (
    alteracoes,
    aplicabilidade,
    consulta_sem_tempo,
    interpretar,
    ordenar,
    situacao,
)
from app.vigencia import vigencia_efetiva

HOJE = date(2026, 10, 21)
client = TestClient(app)


def _r(id_, status="vigente", score=5.0, **vigencia):
    art = {"id": id_, "lei": "Lei X", "artigo": f"Art. {id_}", "tema": "t", "texto": "t", "resumo": "r",
           "fonte": "https://www.planalto.gov.br/x.htm", "norma": "x", "dispositivos": [{"artigo": "1"}],
           "vigencia": {"status": status, "conferida_em": "2026-10-16", **vigencia}}
    return Resultado.de_artigo(art, score)


# ---------------------------------------------------------------- intenção e data
@pytest.mark.parametrize("pergunta, intencao, data, so_ano, esclarecer", [
    ("Qual é a regra atual da jornada?", "atual", None, False, False),
    ("Qual era o prazo em 2015?", "historica", date(2015, 1, 1), True, False),
    ("Em 10/04/2006, qual era a jornada?", "historica", date(2006, 4, 10), False, False),
    ("Como era a regra em março de 2019?", "historica", date(2019, 3, 1), False, False),
    ("Isso foi revogado?", "revogacao", None, False, False),
    ("O carro ainda fica apreendido 30 dias?", "revogacao", None, False, False),
    ("O que mudou na lei do inquilinato?", "mudanca", None, False, False),
    ("Qual artigo garante a gratuidade?", "fundamento", None, False, False),
    ("Antigamente, como era a guarda?", "historica", None, False, True),
    ("Em 31/02/2020 qual era a regra?", "atual", None, False, True),        # data que não existe
    ("O decreto do SAC de 2022 foi revogado?", "revogacao", None, False, False),  # ano do nome da norma
    ("A partir de janeiro de 2027, quantas horas?", "atual", date(2027, 1, 1), False, False),  # futuro
])
def test_intencao_e_data_da_pergunta(pergunta, intencao, data, so_ano, esclarecer):
    c = interpretar(pergunta, HOJE)
    assert (c.intencao, c.data_referencia, c.so_ano, c.pede_esclarecimento) == (intencao, data, so_ano, esclarecer)


def test_ano_da_pergunta_sai_da_busca():
    # "2018" casaria com rótulos como "(c/ Lei nº 13.728/2018)" e traria lei de outro assunto.
    c = interpretar("Qual era o prazo do juizado em 2018?", HOJE)
    assert "2018" not in consulta_sem_tempo("Qual era o prazo do juizado em 2018?", c)


# ---------------------------------------------------------------- aplicabilidade de uma versão
def test_resolucao_posterior_nao_apaga_a_incerteza_da_redacao():
    # CF, art. 226, § 6º: redação da EC 66/2010; a Resolução CNJ 571/2024 mudou um procedimento. Em 2010, a
    # resposta honesta é "incerto" (mesmo ano da emenda), não "não se aplica".
    atual = _r("cf-226", alterada_por=["EC 66/2010", "Res. CNJ 571/2024"])
    assert aplicabilidade(atual, date(2010, 1, 1), HOJE).codigo == 1


def test_redacao_alterada_depois_da_data_nao_e_dada_como_aplicavel():
    atual = _r("a", alterada_por=["Lei 14.905/2024"])
    assert aplicabilidade(atual, date(2020, 3, 15), HOJE).codigo == 2
    assert aplicabilidade(atual, date(2025, 1, 1), HOJE).codigo == 0
    assert aplicabilidade(atual, date(2024, 6, 1), HOJE).codigo == 1  # mesmo ano: depende do dia


def test_decisao_de_tribunal_tambem_muda_a_aplicacao():
    # A letra do art. 1.723 é a mesma desde 2002; a decisão do STF de 2011 mudou a aplicação. Em 2006, o texto
    # atual não é "aplicável" sem ressalva: fica incerto, e a redação anterior (antes da decisão) vale.
    atual = _r("cc-1723", alterada_por=["STF, ADI 4.277 e ADPF 132 (2011)"])
    ap = aplicabilidade(atual, date(2006, 4, 10), HOJE)
    assert ap.codigo == 1 and "2011" in ap.explicacao
    assert aplicabilidade(atual, date(2015, 1, 1), HOJE).codigo == 0
    antiga = _r("velha", status="redacao_anterior", alterada_por=["STF, ADI 4.277 e ADPF 132 (2011)"])
    assert aplicabilidade(antiga, date(2006, 4, 10), HOJE).codigo == 0


def test_situacao_nao_verificada_e_sempre_incerta():
    assert aplicabilidade(_r("x", status="nao_verificada"), HOJE, HOJE).codigo == 1


def test_redacao_com_data_final_vira_anterior_quando_a_data_passa():
    # A jornada de 44 horas vale até a etapa da EC 141/2026 (16/12/2026).
    v = {"status": "vigente", "vigente_ate": "2026-12-15", "conferida_em": "2026-10-19"}
    assert vigencia_efetiva(v, em=date(2026, 12, 15))["status"] == "vigente"
    depois = vigencia_efetiva(v, em=date(2026, 12, 16))
    assert depois["status"] == "redacao_anterior" and depois["status_registrado"] == "vigente"


# ---------------------------------------------------------------- ordenação por versão
def test_versao_aplicavel_vem_primeiro_dentro_do_grupo():
    vigente = _r("cf-6", score=4.0, alterada_por=["EC 64/2010", "EC 90/2015"])
    antiga = Resultado.de_artigo({"id": "cf-6-2006", "versao_de": "cf-6", "lei": "CF", "artigo": "Art. 6º",
                                  "tema": "t", "texto": "t", "resumo": "r", "fonte": "x",
                                  "vigencia": {"status": "redacao_anterior", "alterada_por": ["EC 64/2010"],
                                               "conferida_em": "2026-10-16"}}, 9.0)
    # Mesmo grupo (versao_de aponta para cf-6): hoje, a vigente primeiro, apesar da nota menor.
    atual = ordenar([antiga, vigente], interpretar("quais são os direitos sociais?", HOJE), HOJE)
    assert [r.id for r in atual.resultados] == ["cf-6", "cf-6-2006"]
    # Em 2006, a redação anterior primeiro.
    passado = ordenar([antiga, vigente], interpretar("Em 10/04/2006, quais eram os direitos sociais?", HOJE), HOJE)
    assert passado.resultados[0].id == "cf-6-2006" and passado.avisos


def test_revogado_sem_sucessora_fica_onde_a_busca_pos():
    # Art. 262 do CTB: revogado, sem nova redação. "Foi revogado" é a resposta: não desce.
    revogado = _r("ctb-262", status="revogada", score=9.0, alterada_por=["Lei 13.281/2016"])
    revogado.dispositivos = [{"artigo": "262"}]
    outro = _r("ctb-257", score=5.0)
    outro.dispositivos = [{"artigo": "257"}]
    analise = ordenar([revogado, outro], interpretar("o carro fica apreendido 30 dias?", HOJE), HOJE)
    assert [r.id for r in analise.resultados] == ["ctb-262", "ctb-257"]


# ---------------------------------------------------------------- o que a resposta afirma
def test_situacao_e_alteracoes_so_dizem_o_que_a_base_registra():
    assert "REVOGADO" in situacao(_r("x", status="revogada", alterada_por=["Lei 13.281/2016"]), HOJE)
    vigente = situacao(_r("y"), HOJE)
    assert "não registra revogação" in vigente and "não é certidão" in vigente
    assert "não foi possível verificar" in situacao(_r("z", status="nao_verificada"), HOJE)
    sem_registro = alteracoes(_r("w"))
    assert "não registra alteração" in sem_registro and "não prova" in sem_registro


def test_api_devolve_a_analise_temporal():
    r = client.post("/api/v1/perguntar", json={"pergunta": "Em 2010 o divórcio exigia separação prévia?"}).json()
    assert r["temporal"]["intencao"] == "historica" and r["temporal"]["data_referencia"] == "2010-01-01"
    assert r["temporal"]["avisos"] and r["temporal"]["avisos"][0].startswith("Pergunta sobre 2010")
    assert r["resposta"].startswith("⚑ Pergunta sobre 2010")
    vaga = client.post("/api/v1/perguntar", json={"pergunta": "Antigamente, como era a guarda dos filhos?"}).json()
    assert vaga["temporal"]["pede_esclarecimento"] is True


# ---------------------------------------------------------------- benchmark v2 (porta de regressão)
def test_benchmark_temporal_v2_versao_certa_primeiro():
    r = avaliar_versoes(HOJE)
    assert r["atual"]["versao_certa_primeiro_depois"]["pct"] == 100.0
    assert r["historica"]["versao_certa_primeiro_depois"]["pct"] >= 95.0
    assert r["historica"]["versao_certa_primeiro_ou_incerteza_declarada"]["pct"] == 100.0
    # A melhora é da análise temporal, não do índice: a ordem crua da busca erra muito mais.
    assert r["atual"]["versao_certa_primeiro_antes"]["pct"] < 70.0
