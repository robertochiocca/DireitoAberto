"""Conferência de citações contra o texto da página citada.

Uma citação só é apresentada se o trecho existe, literalmente, na página que
ela aponta — com tolerância apenas a espaços, quebras de linha e hifenização
de fim de linha (já desfeita na extração). Diferença de uma letra reprova.

Isso vale para o que o próprio leitor extrai (defesa contra erro de código)
e, principalmente, para qualquer texto gerado por modelo de linguagem: o
modelo pode parafrasear, mas a citação entre aspas tem de estar lá.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .extracao import DocumentoExtraido
from .texto import normalizar_espacos

# Aspas que um modelo (ou uma pessoa) pode usar ao citar.
_ASPAS = str.maketrans({"“": '"', "”": '"', "«": '"', "»": '"', "‘": "'", "’": "'"})


def _comparavel(texto: str) -> str:
    return normalizar_espacos(texto.translate(_ASPAS))


@dataclass(frozen=True)
class Citacao:
    pagina: int
    trecho: str
    folha: str | None = None
    verificada: bool = False

    def como_dict(self) -> dict:
        return {
            "pagina": self.pagina,
            "folha": self.folha,
            "trecho": self.trecho,
            "verificada": self.verificada,
        }


def _pagina_comparavel(doc: DocumentoExtraido, pagina: int, texto: str) -> str:
    """Texto da página já normalizado, calculado uma vez por documento.

    Normalizar a página inteira a cada citação deixava a análise quadrática: uma
    página de 120 mil caracteres com mil frases levava 28 s só nisso.
    """
    comparavel = doc.cache_comparavel.get(pagina)
    if comparavel is None:
        comparavel = doc.cache_comparavel[pagina] = _comparavel(texto)
    return comparavel


def trecho_na_pagina(doc: DocumentoExtraido, pagina: int, trecho: str) -> bool:
    alvo = doc.pagina(pagina)
    if alvo is None or not alvo.tem_texto or not trecho.strip():
        return False
    return _comparavel(trecho) in _pagina_comparavel(doc, pagina, alvo.texto)


def citar(doc: DocumentoExtraido, pagina: int, trecho: str) -> Citacao:
    """Cria a citação já conferida; `verificada=False` se o trecho não está na página."""
    alvo = doc.pagina(pagina)
    return Citacao(
        pagina=pagina,
        trecho=trecho,
        folha=alvo.folha if alvo else None,
        verificada=trecho_na_pagina(doc, pagina, trecho),
    )


_RE_CITACAO_GERADA = re.compile(r"\[p\.\s*(\d+)\]\s*[\"“«]([^\"”»]{8,600})[\"”»]")


def conferir_texto_gerado(doc: DocumentoExtraido, texto: str) -> list[Citacao]:
    """Extrai e confere as citações no formato `[p. N] "trecho"` de um texto gerado."""
    return [citar(doc, int(p), t) for p, t in _RE_CITACAO_GERADA.findall(texto)]
