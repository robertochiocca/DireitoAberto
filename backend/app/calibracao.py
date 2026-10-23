"""Escolha do corte da busca adaptativa por validação cruzada agrupada, com critério fixado antes.

Critério (fixado antes de olhar os números): entre as configurações que mantêm o artigo do gabarito em
100% das respostas e pelo menos 95% dos artigos julgados "relevante", a de maior precisão (só relevante);
empate → maior precisão útil (relevante ou tangencial) → menos artigos por resposta.

Validação cruzada em 5 dobras agrupadas pelo artigo do gabarito: perguntas parecidas sobre o mesmo
dispositivo ficam na mesma dobra, para a escolha não "ver" a paráfrase da pergunta que vai medir. Cada
dobra escolhe a configuração nas outras quatro e é medida com ela; a média das dobras é a estimativa
honesta do desempenho. A configuração final é a que o critério escolhe com todas as perguntas.

Todas as configurações do grade só removem artigos do top-4 da busca: nenhum artigo novo, sem julgamento,
entra na conta (o conjunto julgado é o top-4 da configuração original).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from .comparacao import carregar_julgamentos
from .retrieval import Retriever

MINIMOS = (1, 2)
CORTES = (0.25, 0.30, 1 / 3, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70)
DOBRAS = 5
RECALL_MINIMO = 0.95


@dataclass(frozen=True)
class Config:
    minimo: int
    corte: float

    def nome(self) -> str:
        return f"mínimo {self.minimo}, corte {self.corte:.3f}"


def _aplicar(ranking: list[tuple[str, float]], cfg: Config) -> list[str]:
    if not ranking:
        return []
    piso = cfg.corte * ranking[0][1]
    return [i for n, (i, s) in enumerate(ranking) if n < cfg.minimo or s >= piso]


def _medir(perguntas: list[dict], cfg: Config) -> dict:
    prel, putil, tamanhos = [], [], []
    gabarito = rel_total = rel_mantidos = 0
    for p in perguntas:
        ids = _aplicar(p["ranking"], cfg)
        juizo = p["juizo"]
        prel.append(sum(juizo.get(i) == "relevante" for i in ids) / len(ids) if ids else 0.0)
        putil.append(sum(juizo.get(i) in ("relevante", "tangencial") for i in ids) / len(ids) if ids else 0.0)
        tamanhos.append(len(ids))
        gabarito += p["esperado"] in ids
        relevantes = [i for i, j in juizo.items() if j == "relevante" and i in dict(p["ranking"])]
        rel_total += len(relevantes)
        rel_mantidos += sum(i in ids for i in relevantes)
    n = len(perguntas)
    return {
        "perguntas": n,
        "precisao_relevante": round(statistics.fmean(prel), 4) if n else 0.0,
        "precisao_util": round(statistics.fmean(putil), 4) if n else 0.0,
        "gabarito_mantido": round(gabarito / n, 4) if n else 0.0,
        "recall_relevantes_julgados": round(rel_mantidos / rel_total, 4) if rel_total else 1.0,
        "artigos_por_resposta": round(statistics.fmean(tamanhos), 3) if n else 0.0,
    }


def _escolher(perguntas: list[dict]) -> Config:
    candidatos = []
    for minimo in MINIMOS:
        for corte in CORTES:
            cfg = Config(minimo, corte)
            m = _medir(perguntas, cfg)
            if m["gabarito_mantido"] == 1.0 and m["recall_relevantes_julgados"] >= RECALL_MINIMO:
                candidatos.append((m["precisao_relevante"], m["precisao_util"], -m["artigos_por_resposta"], cfg))
    if not candidatos:
        return Config(2, 1 / 3)  # a configuração anterior, se nada cumpre o critério
    return max(candidatos, key=lambda c: c[:3])[3]


def _perguntas(retriever: Retriever) -> list[dict]:
    from .comparacao import perguntas_com_gabarito

    julgamentos = carregar_julgamentos()
    saida = []
    for pergunta, esperado in perguntas_com_gabarito():
        ranking = [(r.id, r.score) for r in retriever.buscar(pergunta, top_k=4)]
        saida.append({"pergunta": pergunta, "esperado": esperado, "ranking": ranking,
                      "juizo": julgamentos.get(pergunta, {})})
    return saida


def dobras(perguntas: list[dict]) -> list[list[dict]]:
    """Dobras agrupadas pelo artigo do gabarito, distribuídas em ordem alfabética (determinístico)."""
    ids = sorted({p["esperado"] for p in perguntas})
    dobra_de = {i: n % DOBRAS for n, i in enumerate(ids)}
    return [[p for p in perguntas if dobra_de[p["esperado"]] == d] for d in range(DOBRAS)]


def validar(retriever: Retriever | None = None) -> dict:
    retriever = retriever or Retriever()
    perguntas = _perguntas(retriever)
    partes = dobras(perguntas)
    por_dobra = []
    for d, teste in enumerate(partes):
        treino = [p for k, parte in enumerate(partes) if k != d for p in parte]
        cfg = _escolher(treino)
        por_dobra.append({"dobra": d, "escolhida": cfg.nome(), **_medir(teste, cfg)})
    # Estimativa da validação cruzada: média ponderada pelo tamanho das dobras.
    total = sum(x["perguntas"] for x in por_dobra)
    estimativa = {k: round(sum(x[k] * x["perguntas"] for x in por_dobra) / total, 4)
                  for k in ("precisao_relevante", "precisao_util", "gabarito_mantido", "recall_relevantes_julgados",
                            "artigos_por_resposta")}
    final = _escolher(perguntas)
    anterior = Config(2, 1 / 3)
    return {
        "criterio": (f"gabarito em 100% das respostas e ≥ {RECALL_MINIMO:.0%} dos relevantes julgados; "
                     "maior precisão (só relevante)"),
        "dobras": por_dobra,
        "estimativa_validacao_cruzada": estimativa,
        "configuracao_final": final.nome(),
        "final_em_todas": _medir(perguntas, final),
        "anterior_em_todas": _medir(perguntas, anterior),
        "minimo": final.minimo,
        "corte": final.corte,
    }
