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

_RE_RISCADO = re.compile(r"text-decoration(?:-line)?\s*:[^;\"']*line-through", re.IGNORECASE)
# Elementos sem conteúdo: nunca ficam "abertos".
_VAZIOS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
# Fechamento implícito (o HTML do Planalto raramente fecha <p>, <td>, <li>): tag que abre → (o que ela fecha,
# o que impede de fechar — um contêiner aberto depois dele).
_FECHA_IMPLICITO = {
    **{t: ({"p"}, {"table", "td", "th", "li"}) for t in
       ("p", "div", "table", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote")},
    "li": ({"li"}, {"ul", "ol"}),
    "td": ({"td", "th"}, {"table"}),
    "th": ({"td", "th"}, {"table"}),
    "tr": ({"tr", "td", "th"}, {"table"}),
}
# Um elemento riscado por estilo que engole mais que isto é provável erro de marcação (elemento sem fim),
# não redação revogada: nas 36 páginas reais conferidas em 22/10/2026, o maior engolia 798 caracteres.
MAX_ENGOLIDO_POR_RISCADO = 20_000


class _ExtratorTexto(HTMLParser):
    """Converte o HTML do Planalto em texto corrido, ignorando scripts/estilos.

    Também ignora o texto tachado: nas páginas compiladas do Planalto, é assim que aparece a redação
    revogada, logo antes da vigente (a Constituição tem centenas). Lido como texto, ele virava um segundo
    "Art. 6º" com a redação antiga. O tachado vem de duas formas: as tags `<strike>`/`<del>` e o estilo
    `text-decoration: line-through` (a página da Lei 8.666/1993 risca assim a redação do art. 3º; a do
    CPC de 1973, títulos inteiros; 16 das 34 páginas monitoradas usam o estilo — conferido em 22/10/2026).
    Com `incluir_tachado`, o tachado entra no texto: o monitor compara as duas leituras para saber que
    artigos a página risca. `riscado_por_estilo=False` reproduz a leitura anterior a 22/10/2026, que só
    reconhecia as tags — o monitor a usa para separar mudança da página de mudança da leitura.

    O riscado por estilo acompanha uma pilha dos elementos abertos: fecha com a própria tag, com a tag de
    um ancestral ou pelo fechamento implícito do HTML; elemento vazio (`<br>`, `<img>`) nunca abre. Um
    riscado que não fecha até o fim, ou que engole texto demais, entra em `alertas` — quem lê decide (o
    monitor trata como coleta suspeita).
    """

    _IGNORAR = {"script", "style", "head"}
    _TACHADO = {"strike", "del"}

    def __init__(self, incluir_tachado: bool = False, riscado_por_estilo: bool = True) -> None:
        super().__init__(convert_charrefs=True)
        self._partes: list[str] = []
        self._ignorando = 0
        self._incluir_tachado = incluir_tachado
        self._riscado_por_estilo = riscado_por_estilo
        # Elementos abertos: [tag, riscado por estilo?, caracteres engolidos].
        self._abertos: list[list] = []
        self.alertas: list[str] = []

    def _fechar_de(self, i: int) -> None:
        for tag, riscado, engolidos in self._abertos[i:]:
            if riscado:
                self._ignorando -= 1
                if engolidos > MAX_ENGOLIDO_POR_RISCADO:
                    self.alertas.append(f"elemento <{tag}> riscado por estilo engoliu {engolidos} caracteres")
        del self._abertos[i:]

    def _fechar_implicito(self, tag: str) -> None:
        if tag not in _FECHA_IMPLICITO:
            return
        alvos, barreiras = _FECHA_IMPLICITO[tag]
        for i in range(len(self._abertos) - 1, -1, -1):
            nome = self._abertos[i][0]
            if nome in barreiras:
                return
            if nome in alvos:
                self._fechar_de(i)
                return

    def handle_starttag(self, tag, attrs):
        if tag not in _VAZIOS:
            self._fechar_implicito(tag)
        riscado = False
        if tag in self._IGNORAR or (tag in self._TACHADO and not self._incluir_tachado):
            self._ignorando += 1
        elif (tag not in _VAZIOS and self._riscado_por_estilo and not self._incluir_tachado
              and _RE_RISCADO.search(dict(attrs).get("style") or "")):
            riscado = True
            self._ignorando += 1
        if tag in ("p", "br", "div", "tr") and not (tag in self._IGNORAR or tag in self._TACHADO):
            self._partes.append("\n")
        if tag not in _VAZIOS:
            self._abertos.append([tag, riscado, 0])

    def handle_startendtag(self, tag, attrs):
        # "<br/>", "<p/>": abre e fecha na hora.
        self.handle_starttag(tag, attrs)
        if tag not in _VAZIOS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self._abertos) - 1, -1, -1):
            if self._abertos[i][0] == tag:
                self._fechar_de(i)
                break
        if (tag in self._IGNORAR or (tag in self._TACHADO and not self._incluir_tachado)) and self._ignorando:
            self._ignorando -= 1

    def handle_data(self, data):
        if not self._ignorando:
            self._partes.append(data)
            return
        for aberto in self._abertos:
            if aberto[1]:
                aberto[2] += len(data)

    def texto(self) -> str:
        abertos = [a[0] for a in self._abertos if a[1]]
        if abertos:
            self.alertas.append(f"elemento riscado por estilo sem fim até o fim da página: <{abertos[0]}>")
        bruto = "".join(self._partes)
        linhas = [" ".join(linha.split()) for linha in bruto.splitlines()]
        return "\n".join(linha for linha in linhas if linha)


# "Art. 1º", "Art. 2 o" (Planalto usa <sup>o</sup>), "Art. 10.", "Art. 1.694."
_RE_ARTIGO = re.compile(r"(?m)^\s*Art\.?\s*(\d+(?:\.\d+)*)\s*[ºo°.]?", re.IGNORECASE)


def ler_html(html: str, incluir_tachado: bool = False, riscado_por_estilo: bool = True) -> tuple[str, list[str]]:
    """(texto, alertas da leitura do riscado por estilo)."""
    parser = _ExtratorTexto(incluir_tachado, riscado_por_estilo)
    parser.feed(html)
    texto = parser.texto()
    return texto, parser.alertas


def extrair_texto_html(html: str, incluir_tachado: bool = False, riscado_por_estilo: bool = True) -> str:
    return ler_html(html, incluir_tachado, riscado_por_estilo)[0]


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
