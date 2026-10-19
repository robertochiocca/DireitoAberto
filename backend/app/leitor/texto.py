"""Unidades de texto citáveis: frases e títulos, cada uma presa à sua página.

Tudo o que o leitor afirma sai de uma `Unidade`, e o `trecho` de uma unidade
é sempre uma fatia literal do texto da página (com espaços normalizados). É
isso que permite conferir cada citação depois (`verificacao.py`).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .extracao import RE_CARIMBO_FOLHA, DocumentoExtraido

# Abreviações que terminam em ponto sem terminar a frase.
_ABREVIACOES = {
    "art", "arts", "fls", "fl", "ltda", "dr", "dra", "sr", "sra", "srs", "exmo", "exma", "n", "nº",
    "no", "num", "p", "pp", "pág", "inc", "al", "cf", "obs", "ex", "etc", "proc", "res", "min",
    "des", "rel", "s.a", "sa", "me", "epp", "cia", "av", "r", "id", "v", "vs", "c", "c/c", "ed",
    "oab", "cpf", "cnpj", "rg", "tel", "prof", "profa", "eng", "adv", "doc", "docs",
}
_FIM_DE_FRASE = re.compile(r"(?<=[.!?;:])\s+")
_MARCADOR_DE_LISTA = re.compile(r"^(?:[a-z]\)|[IVX]+\s*[-–—]|\d+[.)]\s)")
_LETRAS = re.compile(r"[A-Za-zÀ-ÿ]")
# "Classe: Procedimento Comum", "Autora: Fulana" — campo de capa ou cabeçalho.
_LINHA_ROTULADA = re.compile(r"^[A-Za-zÀ-ÿº ]{2,30}:\s+\S")


@dataclass(frozen=True)
class Unidade:
    pagina: int
    trecho: str
    titulo: bool = False  # linha de título (ex.: "SENTENÇA", "DOS PEDIDOS")


def sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def normalizar_espacos(texto: str) -> str:
    return " ".join(texto.split())


def eh_titulo(linha: str) -> bool:
    """Linha curta, quase toda em maiúsculas e sem ponto final: cabeçalho de peça ou seção."""
    letras = _LETRAS.findall(linha)
    if len(letras) < 4 or len(linha.split()) > 14 or linha.rstrip().endswith((".", ";", ",")):
        return False
    maiusculas = sum(1 for c in letras if c.isupper())
    return maiusculas / len(letras) >= 0.85


def _frases(paragrafo: str) -> list[str]:
    pedacos, inicio = [], 0
    for m in _FIM_DE_FRASE.finditer(paragrafo):
        anterior = paragrafo[inicio:m.start()]
        ultima = anterior.split()[-1] if anterior.split() else ""
        palavra = ultima.rstrip(".!?;:").lower()
        seguinte = paragrafo[m.end():m.end() + 3]
        if ultima.endswith(".") and (palavra in _ABREVIACOES or (len(palavra) == 1 and palavra.isalpha())):
            continue  # "art. 18", "S. Paulo" — mas "fls. 9." encerra a frase
        if ultima.endswith(":") and not (_MARCADOR_DE_LISTA.match(seguinte) or seguinte[:1].isupper()):
            continue
        if not (seguinte[:1].isupper() or seguinte[:1].isdigit() or _MARCADOR_DE_LISTA.match(seguinte)
                or seguinte[:1] in "\"“(«"):
            continue
        pedacos.append(paragrafo[inicio:m.start()].strip())
        inicio = m.end()
    pedacos.append(paragrafo[inicio:].strip())
    return [p for p in pedacos if p]


# Linha mais curta que isto não é linha quebrada no meio do parágrafo: fecha o
# parágrafo (assinaturas, "Processo nº…", últimas linhas).
_LINHA_CURTA = 45
# Termina título que continua na linha seguinte ("…DA COMARCA DE" / "VILA FICTA").
_CONECTIVO_FINAL = re.compile(r"\b(DE|DA|DO|DAS|DOS|E|EM|COM|POR|PARA|A|O|AO|NA|NO)$")


def _repetidas(doc: DocumentoExtraido) -> set[str]:
    """Linhas que se repetem em muitas páginas: cabeçalho e rodapé, não conteúdo."""
    com_texto = [p for p in doc.paginas if p.tem_texto]
    if len(com_texto) < 3:
        return set()
    contagem: dict[str, int] = {}
    for pagina in com_texto:
        for linha in {normalizar_espacos(linha) for linha in pagina.texto.split("\n")}:
            contagem[linha] = contagem.get(linha, 0) + 1
    minimo = max(3, len(com_texto) // 2)
    return {linha for linha, n in contagem.items() if n >= minimo and linha}


def _fechador(paragrafo: list[str], saida: list[Unidade], pagina: int):
    """Função que despeja o parágrafo acumulado em `saida`, frase a frase."""

    def fechar() -> None:
        if paragrafo:
            saida.extend(Unidade(pagina, frase) for frase in _frases(" ".join(paragrafo)))
            paragrafo.clear()

    return fechar


def unidades(doc: DocumentoExtraido) -> list[Unidade]:
    """Quebra cada página lida em títulos e frases, na ordem do documento."""
    saida: list[Unidade] = []
    repetidas = _repetidas(doc)
    for pagina in doc.paginas:
        if not pagina.tem_texto:
            continue
        paragrafo: list[str] = []
        fechar = _fechador(paragrafo, saida, pagina.numero)

        for linha in pagina.texto.split("\n"):
            linha = normalizar_espacos(linha)
            if not linha or RE_CARIMBO_FOLHA.fullmatch(linha) or linha in repetidas:
                continue  # carimbo de folha e rodapé repetido não são texto da peça
            # Linha que continua uma frase em aberto nunca é título, mesmo em maiúsculas.
            continuacao = bool(paragrafo) and not paragrafo[-1].endswith((".", ":", ";", "!", "?"))
            anterior = saida[-1] if saida and not paragrafo else None
            if (not continuacao and eh_titulo(linha) and anterior is not None and anterior.titulo
                    and anterior.pagina == pagina.numero and _CONECTIVO_FINAL.search(anterior.trecho)):
                saida[-1] = Unidade(pagina.numero, f"{anterior.trecho} {linha}", titulo=True)
            elif not continuacao and eh_titulo(linha):
                fechar()
                saida.append(Unidade(pagina.numero, linha, titulo=True))
            elif not continuacao and _LINHA_ROTULADA.match(linha) and not linha.endswith((",", ";")):
                fechar()
                saida.append(Unidade(pagina.numero, linha))
            elif _MARCADOR_DE_LISTA.match(linha):
                fechar()  # item de lista começa nova frase
                paragrafo.append(linha)
            else:
                paragrafo.append(linha)
            if paragrafo and len(linha) < _LINHA_CURTA and not linha.endswith((",", "-")):
                fechar()
        fechar()
    return saida
