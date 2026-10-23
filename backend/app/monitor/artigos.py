"""Divisão do texto de uma norma em artigos, para comparar versão com versão.

A chave de cada artigo é o número sem pontos ("1694"), com a letra quando
houver ("54-A"). Referências a artigos no meio do texto ("nos termos do
art. 18") não dividem: o título do artigo usa "Art." maiúsculo, e artigos de
outra lei citados entre aspas também não contam. O que vem antes do primeiro
artigo é o preâmbulo; o fecho ("Brasília, …") fica separado do último artigo.
"""

from __future__ import annotations

import re

# A letra de artigo acrescido vem colada ao número ("Art. 58-A", "Art. 4º-A"). Com espaço em volta do
# hífen é o travessão do título seguido da primeira palavra do caput: "Art. 58 - A duração normal…" é o
# art. 58 da CLT, não o 58-A (erro corrigido em 21/10/2026: 176 artigos da CLT e 33 da Lei 6.015
# ganhavam letra que não têm).
_RE_ARTIGO = re.compile(
    r"(?<![\w.\"“'])Art\.\s*(\d{1,4}(?:\.\d{3})?)(?:\s*(?:º|°|o(?=\W)))?(?:-([A-Z]{1,2})\b)?"
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
    # Sem nenhum artigo vigente (página de erro, ou norma inteira riscada), tudo antes do fecho é preâmbulo:
    # é no cabeçalho que a página anota "Revogada pela Lei …".
    inicio = achados[0].start() if achados else len(plano)
    if inicio > 0 and plano[:inicio].strip():
        artigos["preambulo"] = plano[:inicio].strip()
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


def base(chave_artigo: str) -> str:
    """A chave sem o marcador de repetição na página ("6#2" → "6")."""
    return chave_artigo.split("#")[0]


def tachados(vigentes: dict[str, str], com_tachado: dict[str, str]) -> list[str]:
    """Artigos que a página só mostra riscados: estão no texto com o tachado e não no vigente.

    Artigo com a redação antiga riscada e a nova logo depois aparece nos dois e não conta. Na ordem da
    página. Limite: com numeração repetida (o ADCT na página da Constituição), um artigo riscado de uma
    parte e vigente na outra não é percebido.
    """
    presentes = {base(k) for k in vigentes}
    vistos: list[str] = []
    for k in com_tachado:
        b = base(k)
        if k not in ("preambulo", "fecho") and b not in presentes and b not in vistos:
            vistos.append(b)
    return vistos
