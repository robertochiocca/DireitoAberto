"""Divisão do texto de uma norma em artigos, para comparar versão com versão.

A chave de cada artigo é o número sem pontos ("1694"), com a letra quando
houver ("54-A"). Referências a artigos no meio do texto ("nos termos do
art. 18") não dividem: o título do artigo usa "Art." maiúsculo, e artigos de
outra lei citados entre aspas também não contam. O que vem antes do primeiro
artigo é o preâmbulo; o fecho ("Brasília, …") fica separado do último artigo.
"""

from __future__ import annotations

import re

_RE_ARTIGO = re.compile(
    r"(?<![\w.\"“'])Art\.\s*(\d{1,4}(?:\.\d{3})?)\s*(?:º|°|o(?=\W))?\s*(?:-\s*([A-Z]{1,2})\b)?"
)
_RE_FECHO = re.compile(r"\bBrasília,\s+\d{1,2}\s+de\s+[a-zç]+\s+de\s+\d{4}", re.IGNORECASE)


def chave(numero: str, letra: str | None = None) -> str:
    return numero.replace(".", "") + (f"-{letra.upper()}" if letra else "")


def dividir(texto: str) -> dict[str, str]:
    plano = " ".join(texto.split())
    fecho = None
    if (mf := list(_RE_FECHO.finditer(plano))):
        fecho = plano[mf[-1].start():]
        plano = plano[: mf[-1].start()]
    achados = list(_RE_ARTIGO.finditer(plano))
    artigos: dict[str, str] = {}
    if achados and achados[0].start() > 0:
        artigos["preambulo"] = plano[: achados[0].start()].strip()
    for i, m in enumerate(achados):
        fim = achados[i + 1].start() if i + 1 < len(achados) else len(plano)
        k = chave(m.group(1), m.group(2))
        base, n = k, 2
        while k in artigos:  # mesmo número repetido na página (ex.: dois livros do Código)
            k, n = f"{base}#{n}", n + 1
        artigos[k] = plano[m.start():fim].strip()
    if fecho:
        artigos["fecho"] = fecho
    return artigos
