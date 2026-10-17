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
    TOP_K_PADRAO, carregar_julgamentos, comparar, perguntas_com_gabarito,
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
        "semântico": lambda q, k: [r.id for r in semantico.buscar(q, top_k=k)],
    }
    tema = {a["id"]: a["tema"] for a in bm25.artigos}
    julgamentos = carregar_julgamentos()
    medicoes = comparar(buscadores, tema, top_k=args.top_k, julgamentos=julgamentos)

    n = medicoes[0].perguntas
    print(f"\n{'COMPARAÇÃO DE MOTORES DE BUSCA':^78}")
    print(f"{CINZA}{f'top-{args.top_k} · {n} perguntas com gabarito · {len(julgamentos)} julgadas à mão':^78}{FIM}\n")

    cab = f"  {'':<15}{'certo no top-3':>15}{'certo em 1º':>13}{'extras de':>12}"
    cab += f"{'relev.':>9}{'tang.':>8}{'ruído':>8}{'ms/busca':>10}"
    print(cab)
    print(f"  {'':<15}{'':>15}{'':>13}{'outra área':>12}{CINZA}{'── julgamento manual ──':>25}{FIM}")
    melhor_top3 = max(m.esperado_top3 for m in medicoes)
    menor_ruido = min(m.julgados["ruido"] for m in medicoes)
    for m in medicoes:
        cor3 = VERDE if m.esperado_top3 == melhor_top3 else VERMELHO
        corr = VERDE if m.julgados["ruido"] == menor_ruido else AMARELO
        ms = f"{m.ms_por_pergunta:.1f}" if m.ms_por_pergunta is not None else "—"
        vagas = m.vagas_julgadas
        print(f"  {m.motor:<15}{cor3}{m.esperado_top3:>10}/{n:<4}{FIM}{m.primeiro_lugar:>8}/{n:<4}"
              f"{m.outro_tema_pct:>10.0f}% "
              f"{m.julgados['relevante']:>8}{m.julgados['tangencial']:>8}"
              f"{corr}{m.julgados['ruido']:>5}/{vagas:<2}{FIM}{ms:>10}")

    perdidos = {m.motor: [] for m in medicoes}
    for m in medicoes:
        for q, esperado in perguntas_com_gabarito():
            if esperado not in m.resultados[q][:3]:
                perdidos[m.motor].append((q, esperado))
    if any(perdidos.values()):
        print(f"\n{CINZA}  Artigo certo fora do top-3:{FIM}")
        for motor, lst in perdidos.items():
            for q, esperado in lst:
                print(f"    {motor:<15} {esperado:<14} ← {q}")

    if args.casos:
        for q, rotulos in julgamentos.items():
            print(f"\n  {q}")
            for m in medicoes:
                itens = [f"{MARCA.get(rotulos.get(a), '?')} {a}" for a in m.resultados[q]]
                print(f"    {CINZA}{m.motor:<14}{FIM} " + "   ".join(itens))

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
