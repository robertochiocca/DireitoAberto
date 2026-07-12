#!/usr/bin/env python3
"""Extrai súmulas de STF/STJ/TST e gera esqueletos para o corpus.

Os portais dos tribunais costumam bloquear robôs; por isso o script aceita
tanto uma URL quanto um arquivo HTML salvo do navegador:

    # a partir de um arquivo salvo ("Salvar página como…")
    python scripts/ingerir_jurisprudencia.py --tribunal stj \
        --arquivo sumulas-stj.html --numeros 297 385 > novas_sumulas.json

    # a partir da URL (quando o portal permitir)
    python scripts/ingerir_jurisprudencia.py --tribunal stf --url <página>

A saída é JSON no formato de `data/legislacao.json`, com `"revisado": false`
e resumo marcado como TODO — a revisão humana decide o que entra na base.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.ingestao_jurisprudencia import TRIBUNAIS, gerar_esqueletos_jurisprudencia  # noqa: E402

# Navegadores reais passam pelos WAFs dos portais; um UA de script, não.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def _carregar_html(args: argparse.Namespace) -> str:
    if args.arquivo:
        return Path(args.arquivo).read_text(encoding="utf-8", errors="replace")
    import httpx

    url = args.url or TRIBUNAIS[args.tribunal]["fonte"]
    resp = httpx.get(
        url, timeout=60, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    )
    resp.raise_for_status()
    return resp.content.decode(resp.encoding or "utf-8", errors="replace")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tribunal", required=True, choices=sorted(TRIBUNAIS))
    origem = ap.add_mutually_exclusive_group()
    origem.add_argument("--url", help="URL da página de súmulas (default: portal do tribunal)")
    origem.add_argument("--arquivo", help="Arquivo HTML salvo do navegador")
    ap.add_argument("--tema", default="revisar", help="Área temática (default: revisar)")
    ap.add_argument("--numeros", nargs="*", default=None,
                    help="Números de súmulas a extrair (default: todas)")
    args = ap.parse_args()

    html = _carregar_html(args)
    esqueletos = gerar_esqueletos_jurisprudencia(
        html, args.tribunal, fonte=args.url, tema=args.tema, numeros=args.numeros
    )
    if not esqueletos:
        print(
            "Nenhuma súmula encontrada. Se a URL foi bloqueada pelo portal, salve a "
            "página no navegador e use --arquivo.",
            file=sys.stderr,
        )
        sys.exit(1)
    json.dump(esqueletos, sys.stdout, ensure_ascii=False, indent=2)
    print(file=sys.stdout)


if __name__ == "__main__":
    main()
