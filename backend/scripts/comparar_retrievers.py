#!/usr/bin/env python3
"""Compara BM25, busca semântica e a fusão dos dois (RRF).

    python3 scripts/comparar_retrievers.py              # resumo
    python3 scripts/comparar_retrievers.py --casos      # + perguntas julgadas, lado a lado
    python3 scripts/comparar_retrievers.py --json comparacao.json

Mede se o artigo certo aparece (gabarito) e o que mais aparece junto (ruído,
por julgamento manual). Requer o retriever semântico: `pip install chromadb`;
o modelo multilingual-e5-small é baixado na primeira execução. Ver
app/comparacao.py.
"""

import argparse
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.comparacao import (  # noqa: E402
    TOP_K_PADRAO,
    carregar_conjuntos,
    carregar_julgamentos,
    comparar,
    perguntas_com_gabarito,
)
from app.retrieval import Retriever  # noqa: E402

VERDE, AMARELO, VERMELHO, CINZA, FIM = "\033[32m", "\033[33m", "\033[31m", "\033[90m", "\033[0m"
MARCA = {"relevante": f"{VERDE}✓{FIM}", "tangencial": f"{AMARELO}~{FIM}", "ruido": f"{VERMELHO}✗{FIM}"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--top-k", type=int, default=TOP_K_PADRAO)
    ap.add_argument("--json", help="Salva o relatório completo neste arquivo.")
    ap.add_argument("--casos", action="store_true",
                    help="Mostra as perguntas julgadas, motor a motor, com o rótulo de cada artigo.")
    args = ap.parse_args()

    bm25 = Retriever()
    try:
        from app.embeddings import EmbedderMultilingue
        from app.semantic import EmbeddingRetriever

        semantico = EmbeddingRetriever(embedder=EmbedderMultilingue())
    except Exception as exc:  # sem chromadb, sem modelo ou sem rede
        sys.exit(f"Retriever semântico indisponível ({exc}).\n"
                 "Instale com `pip install chromadb` e rode de novo (o modelo é baixado na 1ª vez).")

    buscadores = {
        "BM25": lambda q, k: [r.id for r in bm25.buscar(q, top_k=k)],
        # O que a API devolve: até top-k, menos quando os demais são fracos.
        "BM25 adaptativo": lambda q, k: [
            r.id for r in bm25.buscar(q, top_k=args.top_k, adaptativo=True)
        ],
        "semântico": lambda q, k: [r.id for r in semantico.buscar(q, top_k=k)],
    }
    tema = {a["id"]: a["tema"] for a in bm25.artigos}
    julgamentos = carregar_julgamentos()
    conjuntos = carregar_conjuntos()
    medicoes = comparar(buscadores, tema, top_k=args.top_k, julgamentos=julgamentos,
                       fundir=["BM25", "semântico"], conjuntos=conjuntos)
    n_conj = {c: sum(1 for v in conjuntos.values() if v == c) for c in ("calibracao", "validacao")}

    n = medicoes[0].perguntas
    print(f"\n{'COMPARAÇÃO DE MOTORES DE BUSCA':^78}")
    print(f"{CINZA}{f'top-{args.top_k} · {n} perguntas com gabarito · {len(julgamentos)} julgadas à mão':^78}{FIM}\n")

    # Tabela principal: julgamento da VALIDAÇÃO, a medida fora da amostra.
    val = lambda m: m.julgados_por_conjunto.get("validacao", {})  # noqa: E731
    cab = f"  {'':<17}{'artigos':>8}{'certo no top-3':>15}{'certo em 1º':>13}{'extras de':>12}"
    cab += f"{'relev.':>9}{'tang.':>8}{'ruído':>10}{'ms/busca':>10}"
    print(cab)
    rotulo_val = f"── validação ({n_conj['validacao']} perguntas) ──"
    print(f"  {'':<17}{'(média)':>8}{'':>15}{'':>13}{'outra área':>12}  {CINZA}{rotulo_val:>25}{FIM}")
    melhor_top3 = max(m.esperado_top3 for m in medicoes)
    menor_ruido = min(val(m).get("ruido", 0) for m in medicoes)
    for m in medicoes:
        v = val(m)
        vagas = sum(v.values())
        cor3 = VERDE if m.esperado_top3 == melhor_top3 else VERMELHO
        corr = VERDE if v.get("ruido", 0) == menor_ruido else AMARELO
        ms = f"{m.ms_por_pergunta:.1f}" if m.ms_por_pergunta is not None else "—"
        print(f"  {m.motor:<17}{m.media_resultados:>8.2f}{cor3}{m.esperado_top3:>10}/{n:<4}{FIM}{m.primeiro_lugar:>8}/{n:<4}"
              f"{m.outro_tema_pct:>10.0f}% "
              f"{v.get('relevante', 0):>8}{v.get('tangencial', 0):>8}"
              f"{corr}{v.get('ruido', 0):>6}/{vagas:<3}{FIM}{ms:>10}")

    # Ruído na calibração × validação: se o ganho da busca adaptativa se sustenta fora da amostra.
    print(f"\n  {CINZA}Ruído julgado, calibração × validação:{FIM}")
    rot_cal = f"calibração ({n_conj['calibracao']})"
    rot_val = f"validação ({n_conj['validacao']})"
    print(f"  {'':<17}{rot_cal:>18}{rot_val:>20}")
    for m in medicoes:
        cel = []
        for c in ("calibracao", "validacao"):
            cont = m.julgados_por_conjunto.get(c, {})
            vagas = sum(cont.values())
            pct = 100 * cont.get("ruido", 0) / vagas if vagas else 0
            cel.append(f"{cont.get('ruido', 0):>4}/{vagas:<4} {pct:>3.0f}%")
        print(f"  {m.motor:<17}{cel[0]:>18}{cel[1]:>20}")

    perdidos = {m.motor: [] for m in medicoes}
    for m in medicoes:
        for q, esperado in perguntas_com_gabarito():
            if esperado not in m.resultados[q][:3]:
                perdidos[m.motor].append((q, esperado))
    if any(perdidos.values()):
        print(f"\n{CINZA}  Artigo certo fora do top-3:{FIM}")
        for motor, lst in perdidos.items():
            for q, esperado in lst:
                print(f"    {motor:<17} {esperado:<14} ← {q}")

    if args.casos:
        for q, rotulos in julgamentos.items():
            print(f"\n  {q}")
            for m in medicoes:
                itens = [f"{MARCA.get(rotulos.get(a), '?')} {a}" for a in m.resultados[q]]
                print(f"    {CINZA}{m.motor:<16}{FIM} " + "   ".join(itens))

    nao_julgados = sorted({x for m in medicoes for x in m.nao_julgados})
    if nao_julgados:
        print(f"\n{AMARELO}  Resultados ainda sem julgamento (rotule em data/relevancia_julgada.json):{FIM}")
        for q, aid in nao_julgados:
            print(f"    {aid:<16} ← {q}")

    print(f"\n{CINZA}  Ruído = artigos de outro assunto no top-{args.top_k}, julgados à mão "
          f"(relevante / tangencial / ruído).\n  'Extras de outra área' é só uma aproximação: "
          f"compara a área de cada resultado com a do artigo esperado.{FIM}\n")

    if args.json:
        Path(args.json).write_text(
            json.dumps({"top_k": args.top_k, "motores": [m.para_json() for m in medicoes]},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  relatório salvo em {args.json}\n")


if __name__ == "__main__":
    main()
