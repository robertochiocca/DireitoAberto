"""Avaliação reproduzível do DireitoAberto: busca, abstenção, vigência, leitor e fidelidade.

    python scripts/avaliar.py                       # mede e mostra
    python scripts/avaliar.py --gravar              # grava docs/avaliacao/resultados.json e relatorio.md
    python scripts/avaliar.py --comparar            # compara com o resultados.json versionado

Cada bloco mede uma coisa, com o dado que existe para ela:

- **busca** — 86 perguntas com o dispositivo esperado (casos_busca + benchmark temporal) e 586
  julgamentos manuais de relevância: Recall@k e MRR medem se o certo aparece e em que posição;
  precisão e nDCG@4 usam os julgamentos (relevante = 2, tangencial = 1, ruído = 0). Separado em
  calibração (11 perguntas usadas para ajustar a busca) e validação (75 que não foram);
- **abstenção** — o limiar de evidência (app/validacao.py) nas perguntas fora do escopo
  (data/avaliacao/fora_do_escopo.json) e nas legítimas, também por conjunto;
- **vigência** — o benchmark de armadilha temporal (app/benchmark.py);
- **leitor** — o processo fictício contra o gabarito (data/exemplos);
- **fidelidade** — o texto do corpus contra a versão oficial aceita pelo monitor;
- **latência** — informativa (depende da máquina); não entra na comparação.

Não há medida de qualidade do texto gerado por LLM: sem chave de API neste ambiente, e com o modo
extrativo como padrão, o que se mede é a recuperação e o que o sistema afirma a partir dela.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import subprocess
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .benchmark import rodar_bm25
from .comparacao import carregar_conjuntos, carregar_julgamentos, perguntas_com_gabarito
from .retrieval import DATA_PATH, Retriever
from .validacao import LIMIAR_EVIDENCIA

RAIZ = Path(__file__).resolve().parent.parent
FORA_DO_ESCOPO = RAIZ / "data" / "avaliacao" / "fora_do_escopo.json"
EXEMPLOS = RAIZ / "data" / "exemplos"
SAIDA = RAIZ.parent / "docs" / "avaliacao"
GANHO = {"relevante": 2, "tangencial": 1, "ruido": 0}


# ---------------------------------------------------------------- métricas
def recall(ids: list[str], esperado: str, k: int) -> int:
    return int(esperado in ids[:k])


def reciproco(ids: list[str], esperado: str) -> float:
    return 1.0 / (ids.index(esperado) + 1) if esperado in ids else 0.0


def ndcg(ids: list[str], julgamentos: dict[str, str], k: int) -> float:
    """nDCG@k com ganho graduado; artigo não julgado conta como ruído (pior caso)."""
    dcg = sum(GANHO.get(julgamentos.get(a, "ruido"), 0) / math.log2(i + 2) for i, a in enumerate(ids[:k]))
    ideais = sorted((GANHO[r] for r in julgamentos.values()), reverse=True)[:k]
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideais))
    return dcg / idcg if idcg else 0.0


def precisao(ids: list[str], julgamentos: dict[str, str], aceitos: tuple[str, ...]) -> float:
    if not ids:
        return 0.0
    return sum(1 for a in ids if julgamentos.get(a) in aceitos) / len(ids)


def _media(valores: list[float]) -> float:
    return round(statistics.fmean(valores), 4) if valores else 0.0


# ---------------------------------------------------------------- blocos
def avaliar_busca(retriever: Retriever) -> dict:
    julgamentos = carregar_julgamentos()
    conjuntos = carregar_conjuntos()
    tema_de = {a["id"]: a["tema"] for a in retriever.artigos}
    linhas = []
    for pergunta, esperado in perguntas_com_gabarito():
        ranking = [r.id for r in retriever.buscar(pergunta, top_k=10)]
        api = [r.id for r in retriever.buscar(pergunta, top_k=4, adaptativo=True)]
        juizo = julgamentos.get(pergunta, {})
        linhas.append({
            "conjunto": conjuntos.get(pergunta, "sem_julgamento"),
            "tema": tema_de.get(esperado, "?"),
            "recall@1": recall(ranking, esperado, 1),
            "recall@3": recall(ranking, esperado, 3),
            "recall@10": recall(ranking, esperado, 10),
            "rr": reciproco(ranking, esperado),
            "ndcg@4": ndcg(ranking, juizo, 4),
            "precisao_relevante@4": precisao(ranking[:4], juizo, ("relevante",)),
            "precisao_util@4": precisao(ranking[:4], juizo, ("relevante", "tangencial")),
            "precisao_relevante_api": precisao(api, juizo, ("relevante",)),
            "precisao_util_api": precisao(api, juizo, ("relevante", "tangencial")),
            "artigos_api": len(api),
        })

    def agregar(grupo: list[dict]) -> dict:
        return {
            "perguntas": len(grupo),
            "recall@1": _media([x["recall@1"] for x in grupo]),
            "recall@3": _media([x["recall@3"] for x in grupo]),
            "recall@10": _media([x["recall@10"] for x in grupo]),
            "mrr@10": _media([x["rr"] for x in grupo]),
            "ndcg@4": _media([x["ndcg@4"] for x in grupo]),
            "precisao_relevante@4": _media([x["precisao_relevante@4"] for x in grupo]),
            "precisao_util@4": _media([x["precisao_util@4"] for x in grupo]),
            "precisao_relevante_api": _media([x["precisao_relevante_api"] for x in grupo]),
            "precisao_util_api": _media([x["precisao_util_api"] for x in grupo]),
            "artigos_por_resposta_api": _media([x["artigos_api"] for x in grupo]),
        }

    por_tema: dict[str, list[dict]] = defaultdict(list)
    for x in linhas:
        por_tema[x["tema"]].append(x)
    return {
        "geral": agregar(linhas),
        "calibracao": agregar([x for x in linhas if x["conjunto"] == "calibracao"]),
        "validacao": agregar([x for x in linhas if x["conjunto"] == "validacao"]),
        "por_tema": {
            tema: {k: v for k, v in agregar(g).items() if k in ("perguntas", "recall@1", "recall@3", "mrr@10")}
            for tema, g in sorted(por_tema.items())
        },
    }


def avaliar_abstencao(retriever: Retriever) -> dict:
    def nota(pergunta: str) -> float:
        r = retriever.buscar(pergunta, top_k=1)
        return r[0].score if r else 0.0

    conjuntos = carregar_conjuntos()
    dentro = [(conjuntos.get(q, "sem_julgamento"), q, nota(q)) for q, _ in perguntas_com_gabarito()]
    fora = [(c["conjunto"], c["pergunta"], nota(c["pergunta"]))
            for c in json.loads(FORA_DO_ESCOPO.read_text(encoding="utf-8"))["casos"]]

    def contar(grupo, conjunto: str) -> dict:
        sel = [(q, s) for c, q, s in grupo if c == conjunto]
        abst = [q for q, s in sel if s < LIMIAR_EVIDENCIA]
        return {"perguntas": len(sel), "abstencoes": len(abst)}

    return {
        "limiar": LIMIAR_EVIDENCIA,
        "fora_do_escopo": {c: contar(fora, c) for c in ("calibracao", "validacao")},
        "dentro_do_escopo": {c: contar(dentro, c) for c in ("calibracao", "validacao")},
        "fora_do_escopo_respondidas": sorted(q for _, q, s in fora if s >= LIMIAR_EVIDENCIA),
        "dentro_do_escopo_abstidas": sorted(q for _, q, s in dentro if s < LIMIAR_EVIDENCIA),
    }


def avaliar_vigencia() -> dict:
    m = rodar_bm25().para_json()["metricas"]
    return {chave: m[chave] for chave in ("casos", "cobertura", "recall_vigente", "contaminacao", "inversao",
                                          "resposta_contaminada") if chave in m} | {
        k: v for k, v in m.items() if k.startswith("alerta") or k.startswith("mitig")}


def avaliar_leitor() -> dict:
    from .leitor.analise import analisar
    from .leitor.extracao import extrair
    from .leitor.perguntas import responder

    gabarito = json.loads((EXEMPLOS / "processo-ficticio.gabarito.json").read_text(encoding="utf-8"))
    doc = extrair("processo-ficticio.pdf", (EXEMPLOS / "processo-ficticio.pdf").read_bytes())
    a = analisar(doc)

    def citacoes(obj):
        if isinstance(obj, dict):
            if {"pagina", "trecho", "verificada"} <= set(obj):
                yield obj
            for v in obj.values():
                yield from citacoes(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from citacoes(v)

    por_categoria = {}
    for categoria, esperados in gabarito["itens"].items():
        achados = 0
        for e in esperados:
            if categoria == "linha_do_tempo":
                achados += any(x["data"] == e["data"] and x["natureza"] == e["natureza"]
                               and x["citacoes"][0]["pagina"] == e["pagina"] for x in a[categoria])
            else:
                achados += any(e["contem"] in x["texto"] and x["citacoes"][0]["pagina"] == e["pagina"]
                               for x in a[categoria])
        por_categoria[categoria] = {"esperados": len(esperados), "encontrados": achados,
                                    "extraidos": len(a[categoria])}
    todas = list(citacoes(a))
    proibido = gabarito["nao_pode_afirmar"]
    afirmacoes_proibidas = int(bool(a["transito_em_julgado"])) + sum(
        1 for e in a["linha_do_tempo"]
        if e["data"] == proibido["evento_de_data_citada_em_condenacao"]["data"]
        and e["citacoes"][0]["pagina"] == proibido["evento_de_data_citada_em_condenacao"]["pagina"])
    perguntas_ok = 0
    for caso in gabarito["perguntas"]:
        r = responder(doc, a, caso["pergunta"])
        paginas = [c["pagina"] for it in r["itens"] for c in it["citacoes"]]
        if caso.get("abstencao"):
            ok = r["abstencao"]
        else:
            ok = (not r["abstencao"] and r["intencao"] == caso.get("intencao", r["intencao"])
                  and all(p in paginas for p in caso.get("paginas_esperadas", []))
                  and (paginas[:1] == [caso["primeira_pagina"]] if "primeira_pagina" in caso else True))
        perguntas_ok += ok
    return {
        "itens_por_categoria": por_categoria,
        "citacoes": {"total": len(todas), "verificadas": sum(1 for c in todas if c["verificada"])},
        "afirmacoes_proibidas": afirmacoes_proibidas,
        "perguntas": {"total": len(gabarito["perguntas"]), "comportamento_esperado": perguntas_ok},
    }


def avaliar_fidelidade() -> dict | None:
    from .monitor.fidelidade import verificar_corpus
    from .monitor.registro import DIR_PADRAO, Registro

    registro = Registro(DIR_PADRAO)
    if not registro.dados["aceitas"]:
        return None
    corpus = json.loads(DATA_PATH.read_text(encoding="utf-8"))["artigos"]
    resultados = verificar_corpus(corpus, registro)
    contagem: dict[str, int] = defaultdict(int)
    for r in resultados:
        contagem[r["classe"]] += 1
    return {"conferidos": len(resultados), "por_classe": dict(sorted(contagem.items())),
            "dispositivos_no_corpus": len(corpus)}


def medir_latencia(retriever: Retriever) -> dict:
    perguntas = [q for q, _ in perguntas_com_gabarito()]
    tempos = []
    for _ in range(3):
        for q in perguntas:
            ini = time.perf_counter()
            retriever.buscar(q, adaptativo=True)
            tempos.append((time.perf_counter() - ini) * 1000)
    tempos.sort()
    return {"busca_ms_mediana": round(statistics.median(tempos), 3),
            "busca_ms_p95": round(tempos[int(0.95 * len(tempos))], 3),
            "custo_llm_por_consulta": "zero no modo extrativo (padrão); com LLM, não medido (sem chave)"}


def _commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              cwd=RAIZ, timeout=5).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def rodar() -> dict:
    retriever = Retriever()
    return {
        "gerado_em": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "commit": _commit(),
        "corpus_sha256": hashlib.sha256(DATA_PATH.read_bytes()).hexdigest()[:16],
        "busca": avaliar_busca(retriever),
        "abstencao": avaliar_abstencao(retriever),
        "vigencia": avaliar_vigencia(),
        "leitor": avaliar_leitor(),
        "fidelidade": avaliar_fidelidade(),
        "latencia": medir_latencia(retriever),
    }


# ---------------------------------------------------------------- comparação com a linha de base
# Métricas que não podem cair (maior é melhor) e que não podem subir (menor é melhor).
MAIOR_MELHOR = [
    ("busca", "validacao", "recall@3"), ("busca", "validacao", "mrr@10"), ("busca", "validacao", "ndcg@4"),
    ("busca", "validacao", "precisao_relevante_api"), ("busca", "geral", "recall@3"), ("busca", "geral", "recall@1"),
    ("abstencao", "fora_do_escopo", "validacao", "abstencoes"),
    ("leitor", "citacoes", "verificadas"), ("leitor", "perguntas", "comportamento_esperado"),
]
MENOR_MELHOR = [
    ("abstencao", "dentro_do_escopo", "validacao", "abstencoes"),
    ("leitor", "afirmacoes_proibidas"),
]


def _pegar(d: dict, caminho: tuple) -> float | None:
    for chave in caminho:
        if not isinstance(d, dict) or chave not in d:
            return None
        d = d[chave]
    return d if isinstance(d, (int, float)) else None


def comparar(atual: dict, base: dict) -> list[str]:
    """Regressões do resultado atual em relação à linha de base (lista vazia = nenhuma)."""
    regressoes = []
    for caminho in MAIOR_MELHOR:
        a, b = _pegar(atual, caminho), _pegar(base, caminho)
        if a is not None and b is not None and a < b - 1e-9:
            regressoes.append(f"{'.'.join(caminho)}: {b} → {a}")
    for caminho in MENOR_MELHOR:
        a, b = _pegar(atual, caminho), _pegar(base, caminho)
        if a is not None and b is not None and a > b + 1e-9:
            regressoes.append(f"{'.'.join(caminho)}: {b} → {a}")
    for categoria, valores in (base.get("leitor", {}).get("itens_por_categoria") or {}).items():
        atual_cat = atual["leitor"]["itens_por_categoria"].get(categoria, {})
        if atual_cat.get("encontrados", 0) < valores["encontrados"]:
            regressoes.append(f"leitor.{categoria}: {valores['encontrados']} → {atual_cat.get('encontrados')}")
    return regressoes


def relatorio_md(r: dict) -> str:
    b, ab, lt = r["busca"], r["abstencao"], r["leitor"]

    def pct(x: float) -> str:
        return f"{100 * x:.1f}%"

    linhas = [
        "# Avaliação do DireitoAberto",
        "",
        f"> Gerado por `scripts/avaliar.py` em {r['gerado_em']} (commit `{r['commit']}`, corpus "
        f"`{r['corpus_sha256']}`). Os números abaixo são os do arquivo `resultados.json` ao lado.",
        "",
        "## Busca (BM25, o motor padrão)",
        "",
        "| Medida | Calibração | Validação | Geral |",
        "|---|---|---|---|",
    ]
    for chave, rotulo in [("perguntas", "Perguntas"), ("recall@1", "Recall@1"), ("recall@3", "Recall@3"),
                          ("recall@10", "Recall@10"), ("mrr@10", "MRR@10"), ("ndcg@4", "nDCG@4 (julgamento manual)"),
                          ("precisao_relevante@4", "Precisão@4 — só relevante"),
                          ("precisao_util@4", "Precisão@4 — relevante ou tangencial"),
                          ("precisao_relevante_api", "Precisão da resposta da API — só relevante"),
                          ("precisao_util_api", "Precisão da resposta da API — relevante ou tangencial"),
                          ("artigos_por_resposta_api", "Artigos por resposta da API")]:
        valores = [b[c][chave] for c in ("calibracao", "validacao", "geral")]
        if chave == "perguntas":
            celulas = [f"{v:g}" for v in valores]
        elif chave == "artigos_por_resposta_api":
            celulas = [f"{v:.2f}" for v in valores]
        else:
            celulas = [pct(v) for v in valores]
        linhas.append(f"| {rotulo} | " + " | ".join(celulas) + " |")
    linhas += ["", "Por tema do dispositivo esperado:", "", "| Tema | Perguntas | Recall@1 | Recall@3 | MRR@10 |",
               "|---|---|---|---|---|"]
    for tema, m in b["por_tema"].items():
        linhas.append(f"| {tema} | {m['perguntas']} | {pct(m['recall@1'])} | {pct(m['recall@3'])} | {pct(m['mrr@10'])} |")
    fc, fv = ab["fora_do_escopo"]["calibracao"], ab["fora_do_escopo"]["validacao"]
    dc, dv = ab["dentro_do_escopo"]["calibracao"], ab["dentro_do_escopo"]["validacao"]
    linhas += [
        "",
        f"## Abstenção (limiar de evidência {ab['limiar']})",
        "",
        "| | Calibração | Validação |",
        "|---|---|---|",
        f"| Fora do escopo: abstenção correta | {fc['abstencoes']}/{fc['perguntas']} | {fv['abstencoes']}/{fv['perguntas']} |",
        f"| Dentro do escopo: abstenção indevida | {dc['abstencoes']}/{dc['perguntas']} | {dv['abstencoes']}/{dv['perguntas']} |",
        "",
        "Fora do escopo e ainda respondidas: " + "; ".join(f"\"{q}\"" for q in ab["fora_do_escopo_respondidas"]) + ".",
        "",
        "Legítimas sem resposta (abstenção indevida): " + "; ".join(f"\"{q}\"" for q in ab["dentro_do_escopo_abstidas"]) + ".",
        "",
        "## Vigência (benchmark de armadilha temporal, top-3)",
        "",
        "| Medida | Resultado |",
        "|---|---|",
        *[f"| {rotulo} | {r['vigencia'][chave]['n']}/{r['vigencia']['casos']} ({r['vigencia'][chave]['pct']}%) |"
          for chave, rotulo in [("cobertura", "Dispositivo vigente no corpus"),
                                ("recall_vigente", "Vigente recuperado (quando existe)"),
                                ("contaminacao", "Texto de 2006 recuperado"),
                                ("inversao", "Texto de 2006 acima do vigente"),
                                ("resposta_contaminada", "Resposta cita o texto de 2006")] if chave in r["vigencia"]],
        *([f"| …com aviso de revogação, após rotular | {r['vigencia']['mitigacao_por_rotulo']['respostas_com_alerta']}/"
           f"{r['vigencia']['mitigacao_por_rotulo']['distratores_recuperados']} "
           f"({r['vigencia']['mitigacao_por_rotulo']['pct']}%) |"] if "mitigacao_por_rotulo" in r["vigencia"] else []),
        "",
        "## Leitor de processos (processo fictício × gabarito)",
        "",
        "| Categoria | Esperados | Encontrados | Extraídos |",
        "|---|---|---|---|",
    ]
    for categoria, m in lt["itens_por_categoria"].items():
        linhas.append(f"| {categoria} | {m['esperados']} | {m['encontrados']} | {m['extraidos']} |")
    linhas += [
        "",
        f"Citações conferidas na página: {lt['citacoes']['verificadas']}/{lt['citacoes']['total']}. "
        f"Afirmações proibidas pelo gabarito: {lt['afirmacoes_proibidas']}. "
        f"Perguntas com o comportamento esperado: {lt['perguntas']['comportamento_esperado']}/{lt['perguntas']['total']}.",
        "",
    ]
    if r["fidelidade"]:
        f = r["fidelidade"]
        linhas += ["## Fidelidade do corpus ao texto oficial vigente", "",
                   f"{f['conferidos']} de {f['dispositivos_no_corpus']} dispositivos conferidos (fontes monitoradas): "
                   + ", ".join(f"{k} {v}" for k, v in f["por_classe"].items()) + ".", ""]
    lat = r["latencia"]
    linhas += ["## Latência (informativa, depende da máquina)", "",
               f"Busca: mediana {lat['busca_ms_mediana']} ms, p95 {lat['busca_ms_p95']} ms. "
               f"Custo de LLM: {lat['custo_llm_por_consulta']}.", "",
               "## Limites", "",
               "- Gabaritos, julgamentos de relevância e o conjunto fora do escopo foram feitos pelo projeto, sem "
               "revisão de profissional do Direito.",
               "- O leitor foi medido num processo fictício escrito pelo próprio projeto, não em processos reais.",
               "- Não há medida da qualidade do texto gerado por LLM (sem chave de API neste ambiente).",
               "- Compreensão pelo usuário não foi medida: exige teste com pessoas.", ""]
    return "\n".join(linhas)
