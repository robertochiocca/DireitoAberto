"""Testes do avaliador (app/avaliacao.py) e portão de regressão contra a linha de base versionada."""

import json
import math

import pytest

from app import avaliacao


def test_recall_e_reciproco():
    ranking = ["a", "b", "c"]
    assert avaliacao.recall(ranking, "b", 1) == 0 and avaliacao.recall(ranking, "b", 2) == 1
    assert avaliacao.reciproco(ranking, "c") == pytest.approx(1 / 3)
    assert avaliacao.reciproco(ranking, "z") == 0.0


def test_ndcg_com_ganho_graduado():
    juizo = {"a": "relevante", "b": "tangencial", "c": "ruido"}
    assert avaliacao.ndcg(["a", "b", "c"], juizo, 3) == pytest.approx(1.0)  # ordem ideal
    invertido = (0 + 1 / math.log2(3) + 2 / math.log2(4)) / (2 + 1 / math.log2(3))
    assert avaliacao.ndcg(["c", "b", "a"], juizo, 3) == pytest.approx(invertido)
    assert avaliacao.ndcg(["x", "a"], juizo, 2) < avaliacao.ndcg(["a", "x"], juizo, 2)  # não julgado = ruído


def test_precisao():
    juizo = {"a": "relevante", "b": "tangencial", "c": "ruido"}
    assert avaliacao.precisao(["a", "b", "c", "d"], juizo, ("relevante",)) == 0.25
    assert avaliacao.precisao(["a", "b"], juizo, ("relevante", "tangencial")) == 1.0
    assert avaliacao.precisao([], juizo, ("relevante",)) == 0.0


def test_comparar_aponta_regressao_e_aceita_melhora():
    base = {"busca": {"validacao": {"recall@3": 1.0}}, "leitor": {"afirmacoes_proibidas": 0,
                                                                   "itens_por_categoria": {}}}
    pior = {"busca": {"validacao": {"recall@3": 0.98}}, "leitor": {"afirmacoes_proibidas": 1,
                                                                    "itens_por_categoria": {}}}
    assert len(avaliacao.comparar(pior, base)) == 2
    assert avaliacao.comparar(base, base) == []


def test_nenhuma_regressao_em_relacao_a_linha_de_base():
    """Portão: se a busca, o corpus, a abstenção ou o leitor pioram, este teste falha.

    Mudança que piora uma métrica de propósito tem de vir com a linha de base regravada
    (`python scripts/avaliar.py --gravar`) e a justificativa no commit.
    """
    base = json.loads((avaliacao.SAIDA / "resultados.json").read_text(encoding="utf-8"))
    atual = avaliacao.rodar()
    assert avaliacao.comparar(atual, base) == []
    assert atual["leitor"]["citacoes"]["verificadas"] == atual["leitor"]["citacoes"]["total"]
