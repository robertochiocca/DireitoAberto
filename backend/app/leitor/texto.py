"""Unidades de texto citáveis: frases e títulos, cada uma presa à sua página.

Tudo o que o leitor afirma sai de uma `Unidade`, e o `trecho` de uma unidade
é sempre uma fatia literal do texto da página (com espaços normalizados). É
isso que permite conferir cada citação depois (`verificacao.py`).

Título é linha curta em maiúsculas ("SENTENÇA", "DOS PEDIDOS") e também o
que processos reais trazem fora desse padrão: o nome da peça sozinho na
linha em caixa mista ("Sentença"), espaçado letra a letra ("S E N T E N Ç A")
e o endereçamento que abre uma petição ("Excelentíssimo Senhor Juiz…",
"AO JUÍZO DA 1ª VARA…"). Qual título abre peça é decisão de `analise.py`.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .extracao import DocumentoExtraido, dobrar, eh_carimbo, linhas_repetidas, sem_acento

__all__ = ["Unidade", "chave_de_titulo", "eh_linha_de_juizo", "eh_titulo", "normalizar_espacos", "sem_acento",
           "unidades"]

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
# "Classe: Procedimento Comum", "Autora: Fulana", "Classe - Assunto: …", "Processo Digital nº: …" —
# campo de capa ou cabeçalho.
LINHA_ROTULADA = re.compile(r"^[A-Za-zÀ-ÿºª][A-Za-zÀ-ÿºª ./–-]{1,40}:\s+\S")
_LINHA_ROTULADA = LINHA_ROTULADA
# A linha de local e data que fecha a peça, nos formatos que os sistemas e os modelos usam:
# "Vila Ficta, 20 de fevereiro de 2026.", "São Paulo/SP, 20 de Setembro de 2026", "Cidade (UF), …",
# "Cidade – UF, …", "Cidade, em 20 de…", "Cidade, 20/09/2026." Sem ela, a peça "não fecha" e a
# seguinte pode ser engolida — e a data da peça passa a ser inferida.
RE_ASSINATURA = re.compile(
    r"^[A-ZÀ-Ý][\w' À-ÿ.-]{1,40}"
    r"(?:\s*[/–—-]\s*[A-Z]{2}|\s*\([A-Z]{2}\))?"
    r",\s*(?:em\s+)?"
    r"(?:\d{1,2}[º°o]?\s+de\s+[A-Za-zçÇ]+\s+de\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})\.?$"
)

# Nome de peça sozinho na linha (chave sem acento e em maiúsculas): é título em qualquer caixa.
_PECA_ISOLADA = re.compile(
    r"(SENTENCA|ACORDAO|DECISAO( INTERLOCUTORIA| MONOCRATICA| LIMINAR)?|DESPACHO|CERTIDAO|CONTESTACAO"
    r"|PETICAO INICIAL|REPLICA|MANIFESTACAO|EMENTA|RELATORIO|VOTO|RELATORIO E VOTO|LAUDO( PERICIAL)?"
    r"|CONTRA-?RRAZOES|RECURSO INOMINADO|APELACAO|EMBARGOS DE DECLARACAO|AUTUACAO"
    r"|(TERMO|ATA) DE AUDIENCIA( [A-Z ]{3,60})?)\s*:?"
)
# Linha de identificação do juízo no alto da página ("Juízo de Direito da 1ª Vara Cível…", "Comarca de…",
# "Poder Judiciário"), aplicada à chave do título: é cabeçalho, não corpo — e não pode grudar no título
# seguinte ("SENTENÇA") como se fosse a mesma frase.
RE_LINHA_DE_JUIZO = re.compile(
    r"^(PODER JUDICIARIO|REPUBLICA FEDERATIVA|ESTADO D[OEA] |TRIBUNAL|JUIZO|JUIZADO|VARA|COMARCA|FORO|CARTORIO"
    r"|SECRETARIA|TURMA|CAMARA|COLEGIO RECURSAL|GABINETE|SECAO|SUBSECAO|ORGAO JULGADOR|NUCLEO|CENTRAL DE)\b"
)
_CONECTIVO_FINAL_MISTO = re.compile(r"(?i)\b(de|da|do|das|dos|e|em|com|por|para|a|o|ao|na|no)$")


def eh_linha_de_juizo(linha: str) -> bool:
    """"Juízo de Direito da 1ª Vara Cível da Comarca de Vila Teste" — sem ponto final, curta."""
    return (len(linha) <= 200 and not linha.endswith((".", ",", ";", ":", "!", "?", "-"))
            and not _CONECTIVO_FINAL_MISTO.search(linha) and bool(RE_LINHA_DE_JUIZO.match(chave_de_titulo(linha))))


# Começo de título que nomeia peça — título repetido em várias páginas com esse começo não é cabeçalho.
NOME_DE_PECA = re.compile(
    r"^(SENTENCA|ACORDAO|DECISAO|DESPACHO|CERTIDAO|CONTESTACAO|PETICAO|REPLICA|MANIFESTACAO|EMENTA|RELATORIO"
    r"|VOTO|(TERMO|ATA) DE AUDIENCIA|LAUDO|CONTRA-?RRAZOES|RECURSO|RAZOES|APELACAO|AGRAVO|EMBARGOS|AUTUACAO"
    r"|MANDADO|ALEGACOES FINAIS|MEMORIAIS|CUMPRIMENTO DE SENTENCA|EXCECAO DE PRE|IMPUGNACAO|REQUERIMENTO)\b"
)
# Endereçamento ao juízo: abre petição mesmo sem título ("AO JUÍZO…", "EXMO. SR. DR. JUIZ…", "MM. JUIZ…").
# "JUÍZO DE DIREITO DA 2ª VARA" sem o "AO" é cabeçalho de sentença, não endereçamento.
RE_ENDERECAMENTO = re.compile(
    r"^(?:(?:AO\(A\)|A\(O\)|AOS?|A)\s+)?(?:EXCELENTISSIM|EXM[OA]\b|ILUSTRISSIM|EGREGI[OA]\b|COLEND[OA]\b"
    r"|MM\.?\s*JUIZ)|^(?:AO\(A\)|A\(O\)|AOS?|A)\s+(?:JUIZO|JUIZ|DOUT[OA])\b"
)
# Em caixa mista, só as formas que não aparecem no meio de um parágrafo comum.
_ENDERECAMENTO_MISTO = re.compile(
    r"^(?:(?:AO\(A\)|A\(O\)|AOS?|A)\s+)?(?:EXCELENTISSIM|EXM[OA]\b|ILUSTRISSIM|EGREGI[OA]\b|COLEND[OA]\b)"
    r"|^(?:AO\(A\)|AOS?|A)\s+JUIZO\s+D.*\b(VARA|JUIZADO|COMARCA|FORO|TURMA|TRIBUNAL|CAMARA)\b"
)


@dataclass(frozen=True)
class Unidade:
    pagina: int
    trecho: str
    titulo: bool = False  # linha de título (ex.: "SENTENÇA", "DOS PEDIDOS")


def normalizar_espacos(texto: str) -> str:
    return " ".join(texto.split())


def _espacada(linha: str) -> bool:
    tokens = linha.split()
    return len(tokens) >= 4 and all(len(t) == 1 for t in tokens)


def chave_de_titulo(linha: str) -> str:
    """Forma comparável de um título: sem acento, em maiúsculas, sem o espaçamento letra a letra."""
    chave = dobrar(unicodedata.normalize("NFC", linha)).upper().strip()
    return chave.replace(" ", "") if _espacada(chave) else chave


# Só vale montar a chave (custa) de linha que pode ser nome de peça ou endereçamento.
_TALVEZ_ENDERECAMENTO = re.compile(r"(?i)^\W*(a|à|ao|aos|exc|exm|il|eg|col|mm)")


def eh_titulo(linha: str) -> bool:
    """Cabeçalho de peça ou seção: linha curta quase toda em maiúsculas e sem ponto final,
    o nome de uma peça sozinho na linha (em qualquer caixa) ou o endereçamento de uma petição."""
    if len(linha) > 200:
        return False
    espacada = _espacada(linha)
    palavras = 1 if espacada else len(linha.split())
    if palavras <= 6 or _TALVEZ_ENDERECAMENTO.match(linha):
        chave = chave_de_titulo(linha)
        if _PECA_ISOLADA.fullmatch(chave) or (_ENDERECAMENTO_MISTO.match(chave) and not linha.endswith(".")):
            return True
    letras = _LETRAS.findall(linha)
    if len(letras) < 4 or palavras > 14 or linha.rstrip().endswith((".", ";", ",")):
        return False
    maiusculas = sum(1 for c in letras if c.isupper())
    return maiusculas / len(letras) >= 0.85


def _frases(paragrafo: str) -> list[str]:
    pedacos, inicio = [], 0
    for m in _FIM_DE_FRASE.finditer(paragrafo):
        # Só a última palavra interessa: olha uma janela curta antes do ponto. Copiar o trecho desde o
        # último corte a cada ponto ficava quadrático quando as abreviações se seguem ("Dr. Dr. Dr. …").
        anterior = paragrafo[max(inicio, m.start() - 60):m.start()].rsplit(None, 1)
        ultima = anterior[-1] if anterior else ""
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
# Linha rotulada a partir deste tamanho pode ter sido quebrada pela largura da página.
_LINHA_QUEBRADA = 60
# Termina título que continua na linha seguinte ("…DA COMARCA DE" / "VILA FICTA").
_CONECTIVO_FINAL = re.compile(r"\b(DE|DA|DO|DAS|DOS|E|EM|COM|POR|PARA|A|O|AO|NA|NO)$")


def repetidas(doc: DocumentoExtraido) -> set[str]:
    """Cabeçalhos e rodapés repetidos que saem do texto da peça.

    Título de peça e linha de local e data ficam, mesmo repetidos: três certidões
    seguidas têm o mesmo título "CERTIDÃO", e apagá-lo faria a manifestação
    seguinte cair dentro da peça anterior (fala de parte virando certidão).
    """
    return {
        linha for linha in linhas_repetidas(doc.paginas)
        if not (eh_titulo(linha) and NOME_DE_PECA.match(chave_de_titulo(linha))) and not RE_ASSINATURA.match(linha)
    }


def _fechador(paragrafo: list[str], saida: list[Unidade], pagina: int):
    """Função que despeja o parágrafo acumulado em `saida`, frase a frase."""

    def fechar() -> None:
        if paragrafo:
            saida.extend(Unidade(pagina, frase) for frase in _frases(" ".join(paragrafo)))
            paragrafo.clear()

    return fechar


def unidades(doc: DocumentoExtraido) -> list[Unidade]:
    """Quebra cada página com texto em títulos e frases, na ordem do documento."""
    saida: list[Unidade] = []
    cabecalhos = repetidas(doc)
    for pagina in doc.paginas:
        if not pagina.tem_texto:
            continue
        paragrafo: list[str] = []
        fechar = _fechador(paragrafo, saida, pagina.numero)
        rotulada_aberta = False  # linha rotulada longa, sem ponto final: a seguinte pode ser a quebra dela

        for linha in pagina.texto.split("\n"):
            linha = normalizar_espacos(linha)
            if not linha:
                continue
            if linha in cabecalhos or eh_carimbo(linha):
                # Carimbo de folha, tarja do sistema e rodapé repetido não são texto da peça. A frase
                # aberta termina aqui: juntar o que vem antes e depois da tarja daria um trecho que não
                # existe na página, e a citação seria descartada.
                fechar()
                continue
            # Linha que continua uma frase em aberto nunca é título, mesmo em maiúsculas.
            continuacao = bool(paragrafo) and not paragrafo[-1].endswith((".", ":", ";", "!", "?"))
            anterior = saida[-1] if saida and not paragrafo else None
            if rotulada_aberta and anterior is not None and linha[:1].islower():
                # "Ementa: Apelação cível. … Recurso" + "provido.": a linha rotulada quebrou no fim da página.
                saida[-1] = Unidade(pagina.numero, f"{anterior.trecho} {linha}")
                rotulada_aberta = not linha.endswith((".", ";", "!", "?"))
                continue
            rotulada_aberta = False
            if (not continuacao and eh_titulo(linha) and anterior is not None and anterior.titulo
                    and anterior.pagina == pagina.numero and _CONECTIVO_FINAL.search(anterior.trecho)):
                saida[-1] = Unidade(pagina.numero, f"{anterior.trecho} {linha}", titulo=True)
            elif not continuacao and eh_titulo(linha):
                fechar()
                saida.append(Unidade(pagina.numero, linha, titulo=True))
            elif not continuacao and _LINHA_ROTULADA.match(linha) and not linha.endswith((",", ";")):
                fechar()
                saida.append(Unidade(pagina.numero, linha))
                rotulada_aberta = len(linha) >= _LINHA_QUEBRADA and not linha.endswith((".", ":", "!", "?"))
            elif not continuacao and eh_linha_de_juizo(linha):
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
