"""Ingestão semiautomatizada de leis do Planalto.

As páginas do Planalto são HTML antigo e irregular, então a ingestão é
**semiautomatizada por desenho**: o parser extrai os artigos e gera
esqueletos no formato do corpus (`legislacao.json`); um humano revisa,
escreve o resumo em linguagem simples e escolhe o que entra — essa é a
camada de revisão jurídica do projeto.

Uso via CLI: `python scripts/ingerir_planalto.py --url <página> --lei "Nome da Lei"`.
"""

from __future__ import annotations

import re
import unicodedata
from html.parser import HTMLParser


class _ExtratorTexto(HTMLParser):
    """Converte o HTML do Planalto em texto corrido, ignorando scripts/estilos."""

    _IGNORAR = {"script", "style", "head"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._partes: list[str] = []
        self._ignorando = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._IGNORAR:
            self._ignorando += 1
        elif tag in ("p", "br", "div", "tr"):
            self._partes.append("\n")

    def handle_endtag(self, tag):
        if tag in self._IGNORAR and self._ignorando:
            self._ignorando -= 1

    def handle_data(self, data):
        if not self._ignorando:
            self._partes.append(data)

    def texto(self) -> str:
        bruto = "".join(self._partes)
        linhas = [" ".join(l.split()) for l in bruto.splitlines()]
        return "\n".join(l for l in linhas if l)


# "Art. 1º", "Art. 2 o" (Planalto usa <sup>o</sup>), "Art. 10.", "Art. 1.694."
_RE_ARTIGO = re.compile(r"(?m)^\s*Art\.?\s*(\d+(?:\.\d+)*)\s*[ºo°.]?", re.IGNORECASE)


def extrair_texto_html(html: str) -> str:
    parser = _ExtratorTexto()
    parser.feed(html)
    return parser.texto()


def extrair_artigos(html: str) -> list[dict]:
    """Divide o texto da lei em artigos: [{'numero': '18', 'texto': '...'}]."""
    texto = extrair_texto_html(html)
    encontrados = list(_RE_ARTIGO.finditer(texto))
    artigos = []
    for i, m in enumerate(encontrados):
        fim = encontrados[i + 1].start() if i + 1 < len(encontrados) else len(texto)
        corpo = " ".join(texto[m.start():fim].split())
        # Texto revogado aparece como "(Revogado)" logo após o caput.
        artigos.append({"numero": m.group(1), "texto": corpo})
    return artigos


def _slug(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto.lower())
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", sem_acento).strip("-")


def gerar_esqueletos(
    html: str, lei: str, fonte: str, tema: str = "revisar", numeros: list[str] | None = None
) -> list[dict]:
    """Gera entradas no formato do corpus, prontas para revisão humana."""
    esqueletos = []
    for art in extrair_artigos(html):
        if numeros and art["numero"] not in numeros:
            continue
        esqueletos.append(
            {
                "id": f"{_slug(lei)}-{art['numero'].replace('.', '')}",
                "lei": lei,
                "artigo": f"Art. {art['numero']}",
                "tema": tema,
                "texto": art["texto"],
                "resumo": "TODO: escrever resumo em linguagem simples (revisão humana)",
                "palavras_chave": [],
                "fonte": fonte,
                "revisado": False,
            }
        )
    return esqueletos
