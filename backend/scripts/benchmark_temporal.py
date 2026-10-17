#!/usr/bin/env python3
"""Roda o benchmark de armadilha temporal e imprime o relatório.

    python3 scripts/benchmark_temporal.py                    # BM25 (padrão)
    python3 scripts/benchmark_temporal.py --retriever semantico
    python3 scripts/benchmark_temporal.py --top-k 5 --json resultado.json

Mede se o sistema responde com a redação vigente quando a fonte desatualizada
(Livro do Cidadão, 2006) também está no índice. Ver app/benchmark.py.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.benchmark import (  # noqa: E402
    TOP_K_PADRAO, _indice_contaminado, _indice_mitigado, carregar_casos, rodar,
)
from app.retrieval import Retriever  # noqa: E402

VERDE, AMARELO, VERMELHO, CINZA, FIM = "\033[32m", "\033[33m", "\033[31m", "\033[90m", "\033[0m"


def _cor(pct: float, inverter: bool = False) -> str:
    """Verde = bom. Em contaminação e inversão, menos é melhor (inverter=True)."""
    bom, ruim = (pct <= 25, pct >= 60) if inverter else (pct >= 75, pct <= 40)
    return VERDE if bom else (VERMELHO if ruim else AMARELO)


def _linha(rotulo: str, n: int, base: int, pct: float, inverter: bool = False) -> str:
    barra = "█" * round(pct / 5) + "·" * (20 - round(pct / 5))
    return (f"  {rotulo:<34} {n:>2}/{base:<2}  {_cor(pct, inverter)}{barra} "
            f"{pct:>5.1f}%{FIM}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--retriever", default="bm25", choices=["bm25", "semantico"])
    ap.add_argument("--top-k", type=int, default=TOP_K_PADRAO)
    ap.add_argument("--json", help="Salva o relatório completo neste arquivo.")
    ap.add_argument("--casos", action="store_true", help="Mostra a tabela caso a caso.")
    args = ap.parse_args()

    casos = carregar_casos()
    contaminado_path = _indice_contaminado(casos)
    mitigado_path = _indice_mitigado(casos)

    if args.retriever == "semantico":
        from app.embeddings import EmbedderMultilingue
        from app.semantic import EmbeddingRetriever

        embedder = EmbedderMultilingue()
        limpo = EmbeddingRetriever(embedder=embedder)
        contaminado = EmbeddingRetriever(contaminado_path, embedder=embedder)
        mitigado = EmbeddingRetriever(mitigado_path, embedder=embedder)
    else:
        limpo = Retriever()
        contaminado = Retriever(contaminado_path)
        mitigado = Retriever(mitigado_path)

    rel = rodar(limpo, contaminado, casos=casos, top_k=args.top_k,
                nome_retriever=args.retriever, mitigado=mitigado)

    print(f"\n{'BENCHMARK DE ARMADILHA TEMPORAL':^72}")
    print(f"{CINZA}{'dispositivos cuja redação mudou depois de 10/04/2006':^72}{FIM}\n")
    print(f"  retriever: {rel.retriever} · top-{rel.top_k} · corpus: "
          f"{len(limpo.artigos)} dispositivos · distratores: {len(casos)}\n")

    print(f"{CINZA}  ÍNDICE LIMPO — o corpus atual responde a essas perguntas?{FIM}")
    print(_linha("dispositivo vigente no corpus", rel.cobertos, rel.total, rel.cobertura_pct))
    print(_linha("recuperado no top-k", rel.vigentes_recuperados, rel.cobertos,
                 rel.recall_vigente_pct))

    print(f"\n{CINZA}  ÍNDICE CONTAMINADO — + os 24 textos de 2006, sem marca de "
          f"obsolescência{FIM}")
    print(_linha("texto de 2006 recuperado", rel.distratores_recuperados, rel.total,
                 rel.contaminacao_pct, inverter=True))
    print(_linha("texto de 2006 acima do vigente", rel.inversoes, rel.cobertos,
                 rel.inversao_pct, inverter=True))
    print(_linha("resposta final cita o texto de 2006", rel.respostas_contaminadas,
                 rel.total, rel.resposta_contaminada_pct, inverter=True))

    if rel.com_mitigacao:
        print(f"\n{CINZA}  MITIGAÇÃO — mesmos textos de 2006, agora com rótulo "
              f"de vigência{FIM}")
        print(_linha("ainda recuperados", rel.distratores_rotulados_recuperados,
                     rel.total, rel._pct(rel.distratores_rotulados_recuperados, rel.total),
                     inverter=True))
        print(_linha("com aviso de revogação na resposta", rel.respostas_alertadas,
                     rel.distratores_rotulados_recuperados, rel.alerta_pct))

    if args.casos:
        print(f"\n{CINZA}  {'caso':<26}{'disp.':<23}{'vigente':<10}{'2006':<7}"
              f"{'inversão':<10}alerta{FIM}")
        for c in rel.casos:
            vig = f"#{c.posicao_vigente}" if c.posicao_vigente else ("—" if c.coberto else "n/ corpus")
            dis = f"#{c.posicao_distrator}" if c.posicao_distrator else "—"
            inv = "sim" if c.inversao else "não"
            ale = f"{VERDE}sim{FIM}" if c.resposta_alertada else ("—" if not rel.com_mitigacao else f"{VERMELHO}não{FIM}")
            print(f"  {c.id:<26}{c.dispositivo[:22]:<23}{vig:<10}{dis:<7}{inv:<10}{ale}")

    print(f"\n{CINZA}  Leitura: 'contaminação' alta com cobertura baixa significa que a "
          f"única\n  fonte disponível para a pergunta é a desatualizada — o sistema "
          f"responde\n  com confiança uma regra que não vale mais.{FIM}\n")

    if args.json:
        Path(args.json).write_text(
            json.dumps(rel.para_json(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  relatório salvo em {args.json}\n")


if __name__ == "__main__":
    main()
