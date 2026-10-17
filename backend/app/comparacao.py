"""Comparação de motores de busca: BM25, semântico e a fusão dos dois.

Duas perguntas diferentes, medidas de formas diferentes:

* **O artigo certo aparece?** Nas perguntas com gabarito
  (`data/casos_busca.json` mais as do benchmark temporal), conta se o
  dispositivo esperado está entre os 3 primeiros e se está em 1º lugar.
* **O que mais aparece junto?** É o ruído — e o gabarito não o mede, porque
  só conhece um artigo certo por pergunta. Ele é medido de dois jeitos:
  - por aproximação, em todas as perguntas: a fração dos resultados extras
    que são de outra área temática que a do artigo esperado;
  - por julgamento manual (`data/relevancia_julgada.json`), nas perguntas
    julgadas: cada artigo do top-k rotulado como relevante, tangencial ou
    ruído. É a medida que vale; a aproximação só mostra a tendência.

A fusão usa Reciprocal Rank Fusion (RRF), que combina as listas pela posição,
sem depender da escala de nota de cada motor — o BM25 dá dezenas de pontos e
o semântico dá similaridade de cosseno perto de 0,8.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .benchmark import carregar_casos

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CASOS_BUSCA_PATH = DATA_DIR / "casos_busca.json"
JULGAMENTOS_PATH = DATA_DIR / "relevancia_julgada.json"

ROTULOS = ("relevante", "tangencial", "ruido")
TOP_K_PADRAO = 4          # o que a API devolve por pergunta
PROFUNDIDADE_FUSAO = 20   # quantos resultados de cada motor entram na fusão
K_RRF = 60                # constante usual do RRF

# Recebe a pergunta e quantos resultados quer; devolve ids em ordem.
Buscador = Callable[[str, int], list[str]]


def carregar_casos_busca(caminho: Path = CASOS_BUSCA_PATH) -> list[tuple[str, str]]:
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return [(c["pergunta"], c["esperado"]) for c in dados["casos"]]


def perguntas_com_gabarito() -> list[tuple[str, str]]:
    """Casos de busca mais as perguntas do benchmark temporal cobertas pelo corpus."""
    bench = [(c["pergunta"], c["id_corpus"]) for c in carregar_casos() if c["id_corpus"]]
    return carregar_casos_busca() + bench


def carregar_julgamentos(caminho: Path = JULGAMENTOS_PATH) -> dict[str, dict[str, str]]:
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return {p["pergunta"]: p["julgamentos"] for p in dados["perguntas"]}


def fundir_rrf(listas: list[list[str]], top: int = TOP_K_PADRAO, k: int = K_RRF) -> list[str]:
    """Reciprocal Rank Fusion: soma 1/(k + posição) de cada lista."""
    pontos: dict[str, float] = {}
    for lista in listas:
        for pos, aid in enumerate(lista, 1):
            pontos[aid] = pontos.get(aid, 0.0) + 1.0 / (k + pos)
    return [aid for aid, _ in sorted(pontos.items(), key=lambda x: -x[1])][:top]


@dataclass
class Medicao:
    motor: str
    perguntas: int = 0
    esperado_top3: int = 0
    primeiro_lugar: int = 0
    extras: int = 0
    extras_outro_tema: int = 0
    ms_por_pergunta: float | None = None
    julgados: Counter = field(default_factory=Counter)
    nao_julgados: list[tuple[str, str]] = field(default_factory=list)
    resultados: dict[str, list[str]] = field(default_factory=dict)

    @property
    def vagas_julgadas(self) -> int:
        return sum(self.julgados.values())

    @property
    def outro_tema_pct(self) -> float:
        return 100.0 * self.extras_outro_tema / self.extras if self.extras else 0.0

    def para_json(self) -> dict:
        return {
            "motor": self.motor,
            "perguntas": self.perguntas,
            "esperado_top3": self.esperado_top3,
            "primeiro_lugar": self.primeiro_lugar,
            "extras_outro_tema_pct": round(self.outro_tema_pct, 1),
            "ms_por_pergunta": self.ms_por_pergunta,
            "julgados": {r: self.julgados.get(r, 0) for r in ROTULOS},
            "nao_julgados": [list(x) for x in self.nao_julgados],
            "resultados": self.resultados,
        }


def comparar(
    buscadores: dict[str, Buscador],
    tema_por_id: dict[str, str],
    top_k: int = TOP_K_PADRAO,
    perguntas: list[tuple[str, str]] | None = None,
    julgamentos: dict[str, dict[str, str]] | None = None,
) -> list[Medicao]:
    """Roda cada motor nas perguntas; com dois ou mais, acrescenta a fusão RRF."""
    perguntas = perguntas if perguntas is not None else perguntas_com_gabarito()
    julgamentos = julgamentos if julgamentos is not None else carregar_julgamentos()
    # As perguntas julgadas entram mesmo que não estejam no gabarito.
    sem_gabarito = [(q, None) for q in julgamentos if q not in {p for p, _ in perguntas}]

    listas: dict[str, dict[str, list[str]]] = {nome: {} for nome in buscadores}
    tempos: dict[str, float] = {nome: 0.0 for nome in buscadores}
    for q, _ in perguntas + sem_gabarito:
        for nome, buscar in buscadores.items():
            t0 = time.perf_counter()
            listas[nome][q] = buscar(q, PROFUNDIDADE_FUSAO)
            tempos[nome] += time.perf_counter() - t0

    finais = {nome: {q: lst[:top_k] for q, lst in por_q.items()} for nome, por_q in listas.items()}
    if len(buscadores) >= 2:
        finais["híbrido (RRF)"] = {
            q: fundir_rrf([listas[n][q] for n in buscadores], top=top_k)
            for q, _ in perguntas + sem_gabarito
        }

    n_buscas = len(perguntas) + len(sem_gabarito)
    medicoes = []
    for nome, por_q in finais.items():
        m = Medicao(motor=nome, perguntas=len(perguntas), resultados=por_q)
        if nome in tempos:
            m.ms_por_pergunta = round(1000 * tempos[nome] / n_buscas, 2)
        for q, esperado in perguntas:
            res = por_q[q]
            m.esperado_top3 += esperado in res[:3]
            m.primeiro_lugar += res[:1] == [esperado]
            for aid in res:
                if aid != esperado:
                    m.extras += 1
                    m.extras_outro_tema += tema_por_id.get(aid) != tema_por_id.get(esperado)
        for q, rotulos in julgamentos.items():
            for aid in por_q[q]:
                if aid in rotulos:
                    m.julgados[rotulos[aid]] += 1
                else:
                    m.nao_julgados.append((q, aid))
        medicoes.append(m)
    return medicoes
