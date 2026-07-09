#!/usr/bin/env python3
"""Baixa uma lei do Planalto e gera esqueletos de artigos para o corpus.

Exemplos:
    python scripts/ingerir_planalto.py \
        --url https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm \
        --lei "Código de Defesa do Consumidor — Lei nº 8.078/1990" \
        --tema consumidor --artigos 18 26 49 > novos_artigos.json

A saída é JSON no formato de `data/legislacao.json`, com `"revisado": false`
e resumo marcado como TODO — a revisão humana decide o que entra na base.
"""

import argparse
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.ingestao import gerar_esqueletos  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", required=True, help="URL da lei no Planalto")
    ap.add_argument("--lei", required=True, help='Nome oficial (ex.: "Lei nº 8.078/1990")')
    ap.add_argument("--tema", default="revisar", help="Área temática (default: revisar)")
    ap.add_argument("--artigos", nargs="*", default=None,
                    help="Números de artigos a extrair (default: todos)")
    args = ap.parse_args()

    resp = httpx.get(args.url, timeout=60, follow_redirects=True)
    resp.raise_for_status()
    # Páginas antigas do Planalto usam windows-1252 sem declarar direito.
    html = resp.content.decode(resp.encoding or "windows-1252", errors="replace")

    esqueletos = gerar_esqueletos(html, args.lei, args.url, args.tema, args.artigos)
    if not esqueletos:
        print("Nenhum artigo encontrado — confira a URL e os números.", file=sys.stderr)
        sys.exit(1)
    json.dump(esqueletos, sys.stdout, ensure_ascii=False, indent=2)
    print(file=sys.stdout)


if __name__ == "__main__":
    main()
