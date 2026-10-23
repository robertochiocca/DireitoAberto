"""Extração de texto página a página, com registro do que NÃO foi lido.

O leitor só pode afirmar o que leu. Por isso a extração devolve, além do
texto, o estado de cada página e o motivo de cada página não lida:

- `lida`: há texto de verdade além de carimbo, cabeçalho e tarja do sistema;
- `possivelmente_digitalizada`: a página só tem carimbo de folha, cabeçalho
  repetido ou tarja de assinatura eletrônica — o conteúdo provavelmente está
  numa imagem. É o caso perigoso: há *algum* texto, e uma sentença digitalizada
  passaria por lida. O pouco texto que sobra continua citável;
- `sem_texto`: nenhum texto (digitalizada, em branco ou formato não reconhecido);
- `baixa_qualidade`: a extração saiu com caracteres ilegíveis (U+FFFD, `(cid:N)`,
  palavras sem vogal) — o texto não entra na análise;
- `falha`: o conteúdo da página está corrompido ou grande demais;
- `nao_processada`: além dos limites de páginas, de caracteres ou de tempo.

Este servidor não tem OCR. A palavra "digitalizada" só aparece quando a
página desenha uma imagem; sem imagem, o aviso é neutro (pode ser página em
branco ou arquivo com defeito) — fluxo corrompido não é chamado de digitalizado.

Limites (o arquivo vem de fora e pode ter sido feito para travar o servidor):
páginas processadas, páginas aceitas no arquivo, caracteres por página e no
total, tamanho do conteúdo de cada página e tempo de extração. Passar de um
limite de processamento não recusa o documento: as primeiras páginas são lidas
e as demais ficam `nao_processada`, com aviso.

Numeração: `numero` é a posição da página no arquivo (1, 2, 3…), que é o que o
visualizador usa. Processos têm também a folha carimbada ("fls. 37"), que pode
começar em outro número ou pular folhas; quando o carimbo é encontrado, vai
em `folha` — as citações mostram as duas.
"""

from __future__ import annotations

import hashlib
import itertools
import logging
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from ..documentos import DocumentoInvalido, abrir_pdf

logger = logging.getLogger(__name__)


def numero_do_ambiente(nome: str, padrao: float) -> float:
    try:
        return float(os.environ.get(nome, padrao))
    except ValueError:
        return padrao


# Páginas lidas por documento; as seguintes ficam "não processadas", com aviso.
LIMITE_PAGINAS = int(numero_do_ambiente("DIREITO_ABERTO_LEITOR_MAX_PAGINAS", 500))
# Acima disto o arquivo é recusado: nem vale abrir (um .txt de 20 MB pode ter 20 milhões de "páginas").
LIMITE_PAGINAS_ARQUIVO = int(numero_do_ambiente("DIREITO_ABERTO_LEITOR_MAX_PAGINAS_ARQUIVO", 5000))
# Teto de texto processado por documento (~ 1.500 páginas densas) e por página.
LIMITE_CARACTERES = 3_000_000
LIMITE_CARACTERES_PAGINA = 200_000
# Conteúdo (descomprimido) de uma página de PDF: um PDF de 4 KB pode descomprimir em
# megabytes de operadores de texto e prender a extração por segundos.
# 1 MB de operadores leva ~2,5 s no pypdf; página de texto comum tem de 5 a 50 KB.
LIMITE_CONTEUDO_PAGINA = 1_000_000
ORCAMENTO_EXTRACAO_S = numero_do_ambiente("DIREITO_ABERTO_LEITOR_ORCAMENTO_EXTRACAO_S", 30)

# Página com menos letras que isto, fora carimbo/cabeçalho/tarja, não conta como lida.
MIN_LETRAS = 15
# Proporção de caracteres ilegíveis a partir da qual a página não entra na análise.
LIMIAR_ILEGIVEL = 0.05

ESTADOS_COM_TEXTO = ("lida", "possivelmente_digitalizada")

# Carimbo de folha: "fls. 37", "Fl. 37", "folha 37" sozinho na linha. Referências
# no meio do texto ("conforme fls. 15") apontam para outra folha e não contam.
RE_CARIMBO_FOLHA = re.compile(r"(?im)^\s*(?:fls?\.|folhas?)\s*(\d{1,6})\s*$")
# Tarjas e rodapés dos sistemas (assinatura eletrônica, conferência, paginação):
# não são texto da peça e não provam que a página foi lida.
# Padrões estreitos de propósito: "o contrato foi assinado digitalmente pelas partes em 10/01/2026",
# "o código de verificação do boleto" e "para conferir o original, a autora juntou…" são conteúdo.
# Sem ".*": com ele, uma linha longa com várias "assinado digitalmente por" levava a regex a
# retroceder de forma quadrática (112 mil caracteres, 10 s). As janelas são limitadas.
RE_CARIMBO_SISTEMA = re.compile(
    r"(?i)^(documento )?assinad[oa] (digital|eletronica)mente"
    r"|assinad[oa] (digital|eletronica)mente por [^\n]{0,200}?"
    r"(\d{2}/\d{2}/\d{4}[^\n]{0,12}?\d{1,2}[:h]\d{2}|protocolad|11\.?419|2\.?200|icp-?brasil)"
    r"|para conferir (o original|a autenticidade)[^\n]{0,60}?\b(acess|site\b|endereco eletronico|https?:|www\.)"
    r"|^este documento (e|foi) (copia|assinado|gerado)"
    r"|^codigo (de verificacao|verificador)\b|\bcodigo (de verificacao|verificador)\s*(:|n[o°º]\.?)?\s*[a-z0-9-]*\d[a-z0-9-]{3,}"
    r"|^num\.?\s*\d+\s*-\s*pag\.?\s*\d+"
    r"|^pagina\s+\d+\s+(de|/)\s+\d+$|^\d+\s*/\s*\d+$"
)
# Tarja ou carimbo é linha curta: acima disto, a linha é texto (e a regex não roda nela).
LIMITE_LINHA_CARIMBO = 400
# Linha repetida mais longa que isto não é cabeçalho nem rodapé.
LIMITE_LINHA_REPETIDA = 300
_RE_HIFENIZACAO = re.compile(r"(\w)-\n(\w)")
_RE_ILEGIVEL = re.compile(r"[�\x00-\x08\x0b\x0c\x0e-\x1f\x7f-]|\(cid:\d+\)")
_RE_PALAVRA = re.compile(r"\b[^\W\d_]{5,}\b")
_RE_SEM_VOGAL = re.compile(r"\b[b-df-hj-np-tv-zç]{5,}\b", re.IGNORECASE)
_RE_LETRA = re.compile(r"[^\W\d_]")


def sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c))


# Letra acentuada → letra base, um caractere por um: o texto "dobrado" tem o mesmo comprimento
# do original (as posições de um casamento valem nos dois) e sai bem mais rápido que o NFKD.
_TABELA_DOBRA = {
    i: base for i in range(0x80, 0x2B0)
    if (base := unicodedata.normalize("NFKD", chr(i))[:1]) != chr(i) and base.isascii() and base.isalpha()
}


def dobrar(texto: str) -> str:
    """Sem acento e em minúsculas, preservando o comprimento (para regex sobre texto de processo)."""
    return texto.translate(_TABELA_DOBRA).lower()


@dataclass
class Pagina:
    numero: int                # posição no arquivo, a partir de 1
    texto: str                 # texto extraído, linhas preservadas
    estado: str = "lida"       # ver o docstring do módulo
    folha: str | None = None   # carimbo de folha do processo, quando houver
    truncada: bool = False     # passou do limite de caracteres: só o começo foi lido

    @property
    def tem_texto(self) -> bool:
        return self.estado in ESTADOS_COM_TEXTO


@dataclass
class DocumentoExtraido:
    nome: str
    hash_sha256: str
    paginas: list[Pagina]
    avisos: list[str] = field(default_factory=list)
    # Texto de cada página já normalizado para conferir citações (verificacao.py).
    cache_comparavel: dict[int, str] = field(default_factory=dict, repr=False, compare=False)

    @property
    def total_paginas(self) -> int:
        return len(self.paginas)

    def paginas_por_estado(self, estado: str) -> list[int]:
        return [p.numero for p in self.paginas if p.estado == estado]

    @property
    def leitura_completa(self) -> bool:
        return all(p.estado == "lida" and not p.truncada for p in self.paginas)

    def pagina(self, numero: int) -> Pagina | None:
        if 1 <= numero <= len(self.paginas):
            return self.paginas[numero - 1]
        return None


def faixas(numeros: list[int], limite: int = 12) -> str:
    """[1, 2, 3, 5, 9, 10] → "1 a 3, 5, 9 e 10". Agrupa para o aviso não listar 500 mil páginas."""
    return faixas_de_intervalos([(n, n) for n in numeros], limite)


def faixas_de_intervalos(intervalos: list[tuple[int, int]], limite: int = 12) -> str:
    """[(3, 8), (10, 39)] → "3 a 8 e 10 a 39". Trabalha com as pontas dos intervalos, sem expandi-los:
    "fls. 1" seguida de "fls. 999999" é um intervalo só, não um milhão de números na memória."""
    grupos: list[tuple[int, int]] = []
    for a, b in sorted(intervalos):
        if grupos and a <= grupos[-1][1] + 1:
            grupos[-1] = (grupos[-1][0], max(b, grupos[-1][1]))
        else:
            grupos.append((a, b))
    # Faixa de 3 ou mais vira "a a b"; de 1 ou 2, os números soltos.
    total = sum(1 if b - a >= 2 else b - a + 1 for a, b in grupos)
    partes: list[str] = []
    for a, b in grupos:
        if len(partes) >= limite:
            break
        if b - a >= 2:
            partes.append(f"{a} a {b}")
        else:
            partes.extend(str(n) for n in range(a, b + 1))
    if total > limite:
        partes = [*partes[:limite], f"mais {total - limite} trecho(s)"]
    return partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " e " + partes[-1]


def _paginas(numeros: list[int], singular: str = "Página", plural: str = "Páginas") -> str:
    return f"{singular if len(numeros) == 1 else plural} {faixas(numeros)}"


def _limpar(texto: str) -> str:
    """Junta palavras hifenizadas na quebra de linha e tira espaços sobrando.

    Normaliza em NFC: alguns PDFs trazem "ç" como "c" + cedilha; com tudo em NFC, a
    comparação sem acento (`dobrar`) vale para o texto inteiro.
    """
    texto = _RE_HIFENIZACAO.sub(r"\1\2", unicodedata.normalize("NFC", texto).replace("\r", ""))
    linhas = [" ".join(linha.split()) for linha in texto.split("\n")]
    return "\n".join(linha for linha in linhas if linha)


def _folha(texto: str) -> str | None:
    """Carimbo de folha: o último "fls. N" isolado da página (carimbos ficam na margem)."""
    candidatos = RE_CARIMBO_FOLHA.findall(texto)
    return candidatos[-1] if candidatos else None


def eh_carimbo(linha: str) -> bool:
    """Carimbo de folha ou tarja do sistema: aparece na página, mas não é texto da peça."""
    if len(linha) > LIMITE_LINHA_CARIMBO:
        return False
    return bool(RE_CARIMBO_FOLHA.fullmatch(linha) or RE_CARIMBO_SISTEMA.search(dobrar(linha)))


def linhas_repetidas(paginas: list[Pagina]) -> set[str]:
    """Linhas que se repetem em muitas páginas: cabeçalho e rodapé, não conteúdo.

    Conta todas as páginas com texto (inclusive as possivelmente digitalizadas,
    cujo texto é justamente a tarja repetida). O resultado é o mesmo na extração
    e quando o documento é reconstruído do banco, porque o texto guardado é o mesmo.
    """
    com_texto = [p for p in paginas if p.texto]
    if len(com_texto) < 3:
        return set()
    contagem: dict[str, int] = {}
    for pagina in com_texto:
        for linha in {" ".join(linha.split()) for linha in pagina.texto.split("\n")
                      if len(linha) <= LIMITE_LINHA_REPETIDA}:
            contagem[linha] = contagem.get(linha, 0) + 1
    minimo = max(3, len(com_texto) // 2)
    return {linha for linha, n in contagem.items() if n >= minimo and linha}


def proporcao_ilegivel(texto: str) -> float:
    """Caracteres ilegíveis sobre caracteres visíveis; palavras sem vogal contam como ilegíveis."""
    visiveis = len(texto) - texto.count(" ") - texto.count("\n")
    if visiveis <= 0:
        return 0.0
    ruins = sum(len(m.group(0)) for m in _RE_ILEGIVEL.finditer(texto))
    palavras = _RE_PALAVRA.findall(texto)
    sem_vogal = _RE_SEM_VOGAL.findall(texto)
    if len(sem_vogal) >= 5 and len(sem_vogal) >= 0.3 * len(palavras):
        ruins += sum(len(p) for p in sem_vogal)
    return ruins / visiveis


# ---------------------------------------------------------------- PDF
def _tamanho_declarado(pagina: Any) -> int:
    """Soma dos /Length dos fluxos de conteúdo (o que o arquivo diz ter, antes de descomprimir)."""
    try:
        conteudo = pagina.get("/Contents")
        if conteudo is None:
            return 0
        conteudo = conteudo.get_object()
        fluxos = conteudo if isinstance(conteudo, list) else [conteudo]
        total = 0
        for fluxo in fluxos:
            fluxo = fluxo.get_object()
            tamanho = fluxo.get("/Length", 0)
            declarado = int(tamanho.get_object() if hasattr(tamanho, "get_object") else tamanho)
            # Sem /Length (ou com /Length errado), vale o tamanho bruto do fluxo ainda codificado.
            total += max(declarado, len(getattr(fluxo, "_data", b"") or b""))
        return total
    except Exception:
        return 0


_RE_DO = re.compile(rb"/([^\s/\[\]()<>{}%]+)\s+Do\b")


def _desenha_imagem(recursos: Any, dados: bytes, profundidade: int = 0) -> bool:
    """A página (ou um formulário dentro dela) desenha alguma imagem?"""
    if re.search(rb"\bBI\b[\s\S]{1,200}?\bID\b", dados):
        return True  # imagem embutida no próprio conteúdo
    nomes = set(_RE_DO.findall(dados))
    if not nomes or recursos is None:
        return False
    try:
        xobjetos = recursos.get_object().get("/XObject")
        xobjetos = xobjetos.get_object() if xobjetos is not None else {}
        for nome in nomes:
            obj = xobjetos.get("/" + nome.decode("latin-1"))
            if obj is None:
                continue
            obj = obj.get_object()
            if obj.get("/Subtype") == "/Image":
                return True
            if obj.get("/Subtype") == "/Form" and profundidade < 2 and \
                    _desenha_imagem(obj.get("/Resources"), obj.get_data(), profundidade + 1):
                return True
    except Exception:
        return False
    return False


def _ler_pagina_pdf(pagina: Any) -> tuple[str | None, bool, str | None]:
    """(texto ou None, desenha imagem?, problema). Problema: corrompida · grande · erro."""
    try:
        conteudo = pagina.get_contents()
        dados = conteudo.get_data() if conteudo is not None else b""
    except Exception as exc:
        logger.info("Conteúdo ilegível na página (%s).", type(exc).__name__)
        return None, False, "corrompida"
    if not dados and _tamanho_declarado(pagina) > 0:
        return None, False, "corrompida"  # havia conteúdo, mas não descomprimiu
    if len(dados) > LIMITE_CONTEUDO_PAGINA:
        return None, False, "grande"
    try:
        texto = pagina.extract_text() or ""
    except Exception as exc:  # página corrompida não derruba o documento inteiro
        logger.info("Falha ao extrair a página (%s).", type(exc).__name__)
        return None, False, "erro"
    # Só importa saber da imagem quando há pouco texto (é o que decide o aviso).
    imagem = len(texto) < 2000 and _desenha_imagem(pagina.get("/Resources"), dados)
    return texto, imagem, None


# ---------------------------------------------------------------- TXT
def _decodificar_txt(conteudo: bytes) -> tuple[str, str | None]:
    try:
        return conteudo.decode("utf-8-sig"), None
    except UnicodeDecodeError:
        return conteudo.decode("cp1252", errors="replace"), (
            "O arquivo .txt não está em UTF-8; foi lido como Windows-1252 (o padrão antigo do Windows). "
            "Confira acentos e símbolos nos trechos citados."
        )


# ---------------------------------------------------------------- extração
def extrair(
    nome: str,
    conteudo: bytes,
    *,
    limite_paginas: int | None = None,
    limite_caracteres: int | None = None,
    orcamento_s: float | None = None,
) -> DocumentoExtraido:
    """Extrai o documento página a página. Erros de formato viram `DocumentoInvalido`."""
    limite_paginas = LIMITE_PAGINAS if limite_paginas is None else limite_paginas
    limite_caracteres = LIMITE_CARACTERES if limite_caracteres is None else limite_caracteres
    orcamento_s = ORCAMENTO_EXTRACAO_S if orcamento_s is None else orcamento_s
    nome_min = (nome or "").lower()
    avisos: list[str] = []
    imagens: set[int] = set()
    problemas: dict[str, list[int]] = {}
    cortes: dict[str, list[int]] = {}

    if nome_min.endswith(".pdf"):
        reader = abrir_pdf(conteudo, limite_paginas=LIMITE_PAGINAS_ARQUIVO)
        total_paginas = len(reader.pages)

        def ler(i: int) -> tuple[str | None, bool, str | None]:
            return _ler_pagina_pdf(reader.pages[i])
    elif nome_min.endswith(".txt"):
        texto_txt, aviso = _decodificar_txt(conteudo)
        if aviso:
            avisos.append(aviso)
        # Em texto puro, a quebra de página é o caractere form feed. Conta antes de
        # dividir: dividir 20 milhões de form feeds já esgotaria a memória.
        total_paginas = texto_txt.count("\f") + 1
        if total_paginas > LIMITE_PAGINAS_ARQUIVO:
            raise DocumentoInvalido(
                f"O arquivo tem {total_paginas} páginas (separadas por form feed); o limite é "
                f"{LIMITE_PAGINAS_ARQUIVO}. Envie só as partes que interessam."
            )
        partes_txt = texto_txt.split("\f", limite_paginas)

        def ler(i: int) -> tuple[str | None, bool, str | None]:
            return partes_txt[i], False, None
    else:
        raise DocumentoInvalido("Formato não suportado. Envie .pdf ou .txt.")

    paginas: list[Pagina] = []
    total = 0
    prazo = time.monotonic() + orcamento_s
    for i in range(total_paginas):
        numero = i + 1
        motivo = ("paginas" if i >= limite_paginas else "caracteres" if total >= limite_caracteres
                  else "tempo" if i > 0 and time.monotonic() > prazo else None)  # a 1ª página sempre é lida
        if motivo:
            cortes.setdefault(motivo, []).append(numero)
            paginas.append(Pagina(numero, "", "nao_processada"))
            continue
        bruto, imagem, problema = ler(i)
        if bruto is None:
            problemas.setdefault(problema or "erro", []).append(numero)
            paginas.append(Pagina(numero, "", "falha"))
            continue
        if imagem:
            imagens.add(numero)
        cabe = min(LIMITE_CARACTERES_PAGINA, limite_caracteres - total)
        texto = _limpar(bruto[: 2 * cabe + 1000])  # limpar só encolhe: não precisa limpar o que vai ser cortado
        truncada = len(texto) > cabe
        if truncada:
            texto = _cortar(texto, cabe)
        total += len(texto)
        paginas.append(Pagina(numero, texto, "lida" if texto else "sem_texto", _folha(texto), truncada))

    # A classificação também tem prazo (metade do orçamento, além dele): antes ela rodava depois
    # do laço, sem limite, e uma linha patológica prendia a extração por mais de um minuto.
    if cortadas := _classificar(paginas, prazo + orcamento_s / 2):
        cortes.setdefault("tempo", []).extend(cortadas)
    if not any(p.estado == "lida" for p in paginas):
        raise DocumentoInvalido(_sem_texto_legivel(paginas, imagens))
    avisos += _avisos(paginas, imagens, problemas, cortes, limite_paginas)
    return DocumentoExtraido(
        nome=nome,
        hash_sha256=hashlib.sha256(conteudo).hexdigest(),
        paginas=paginas,
        avisos=avisos,
    )


def _cortar(texto: str, cabe: int) -> str:
    """Corta a página no limite: na última quebra de linha, se ela estiver perto do corte; senão
    no último espaço. Cortar sempre na última quebra fazia a página "título + uma linha enorme"
    perder tudo menos o título — e ser recusada como se fosse digitalizada."""
    corte = texto[:cabe]
    quebra = corte.rfind("\n")
    if quebra > 0 and quebra >= cabe - 2000:
        return corte[:quebra]
    espaco = corte.rfind(" ")
    return corte[:espaco] if espaco > 0 and espaco >= cabe - 200 else corte


def _residuo(texto: str, repetidas: set[str]) -> str:
    return "\n".join(linha for linha in texto.split("\n")
                     if linha and linha not in repetidas and not eh_carimbo(linha))


def _tem_letras(texto: str, minimo: int) -> bool:
    """Ao menos `minimo` letras — sem montar a lista de todas as letras da página."""
    return sum(1 for _ in itertools.islice(_RE_LETRA.finditer(texto), minimo)) >= minimo


def _classificar(paginas: list[Pagina], prazo: float | None = None) -> list[int]:
    """Rebaixa páginas "lidas" que só têm carimbo/cabeçalho/tarja ou texto ilegível.

    Devolve as páginas que ficaram sem classificar porque o prazo acabou: elas viram
    `nao_processada` (sem texto), como as que a extração não chegou a ler. A 1ª página
    sempre é classificada.
    """
    repetidas = linhas_repetidas(paginas)
    cortadas = []
    for pagina in paginas:
        if pagina.estado != "lida":
            continue
        if prazo is not None and pagina.numero > 1 and time.monotonic() > prazo:
            pagina.texto, pagina.estado, pagina.folha, pagina.truncada = "", "nao_processada", None, False
            cortadas.append(pagina.numero)
            continue
        if proporcao_ilegivel(pagina.texto) >= LIMIAR_ILEGIVEL:
            pagina.estado = "baixa_qualidade"
        elif not _tem_letras(_residuo(pagina.texto, repetidas), MIN_LETRAS):
            pagina.estado = "possivelmente_digitalizada"
    return cortadas


def _sem_texto_legivel(paginas: list[Pagina], imagens: set[int]) -> str:
    if any(p.estado == "baixa_qualidade" for p in paginas):
        return ("A extração do texto saiu ilegível (caracteres que não puderam ser reconhecidos). O arquivo pode ter "
                "fontes sem tabela de caracteres, estar com defeito ou não ser texto — tente exportá-lo de novo.")
    if imagens:
        return ("Não encontrei texto no documento além de carimbos: ele parece digitalizado como imagem, e este "
                "servidor ainda não faz OCR — tente um PDF com texto selecionável.")
    return ("Não encontrei texto no documento. Se ele foi digitalizado como imagem, este "
            "servidor ainda não faz OCR — tente um PDF com texto selecionável.")


def _avisos(paginas: list[Pagina], imagens: set[int], problemas: dict[str, list[int]],
            cortes: dict[str, list[int]], limite_paginas: int) -> list[str]:
    avisos = []
    por_estado: dict[str, list[int]] = {}
    for p in paginas:
        por_estado.setdefault(p.estado, []).append(p.numero)
    vazias = por_estado.get("sem_texto", [])
    if com_imagem := [n for n in vazias if n in imagens]:
        avisos.append(
            f"{_paginas(com_imagem)} sem texto: há imagem na página — provavelmente digitalizada(s). Este servidor "
            "não faz OCR, então o conteúdo NÃO foi lido e não entra no resumo."
        )
    if sem_imagem := [n for n in vazias if n not in imagens]:
        avisos.append(
            f"{_paginas(sem_imagem)} sem texto extraível — pode ser página em branco, imagem digitalizada ou "
            "formato que o leitor não reconhece. Este servidor não faz OCR: se houver conteúdo, ele NÃO foi lido."
        )
    talvez = por_estado.get("possivelmente_digitalizada", [])
    if com_imagem := [n for n in talvez if n in imagens]:
        avisos.append(
            f"{_paginas(com_imagem)}: só há carimbo, cabeçalho ou tarja do sistema como texto, e a página tem "
            "imagem — provavelmente é folha digitalizada (pode ser uma decisão ou certidão). Este servidor não faz "
            "OCR: o conteúdo da imagem NÃO foi lido."
        )
    if sem_imagem := [n for n in talvez if n not in imagens]:
        avisos.append(
            f"{_paginas(sem_imagem)}: quase nenhum texto além de carimbo, cabeçalho ou tarja do sistema — pode ser "
            "folha em branco ou digitalizada. Confira no original: se houver conteúdo, ele NÃO foi lido (este "
            "servidor não faz OCR)."
        )
    if ilegiveis := por_estado.get("baixa_qualidade", []):
        avisos.append(
            f"{_paginas(ilegiveis)}: a extração saiu com caracteres ilegíveis (fonte sem tabela de caracteres ou "
            "arquivo com defeito). O texto não foi usado na análise; confira no original."
        )
    poucos = [p.numero for p in paginas if p.estado == "lida" and _RE_ILEGIVEL.search(p.texto)]
    if poucos:
        avisos.append(f"{_paginas(poucos)} têm caracteres que não puderam ser reconhecidos; confira os trechos "
                      "citados com o original.")
    if corrompidas := problemas.get("corrompida", []):
        avisos.append(f"{_paginas(corrompidas)}: o conteúdo da página está corrompido ou fora do padrão; não foi lido.")
    if grandes := problemas.get("grande", []):
        avisos.append(f"{_paginas(grandes)}: conteúdo grande demais para este servidor; não foi lido.")
    if falhas := problemas.get("erro", []):
        avisos.append(f"{_paginas(falhas)}: falha ao extrair o texto; conteúdo não lido.")
    if truncadas := [p.numero for p in paginas if p.truncada]:
        avisos.append(
            f"{_paginas(truncadas)}: texto longo demais para uma página; só o começo foi lido. Em .txt, separe as "
            "páginas com o caractere de quebra de página (form feed)."
        )
    motivos = {"paginas": f"o leitor processa até {limite_paginas} páginas",
               "caracteres": "o texto passou do limite de caracteres", "tempo": "a extração passou do limite de tempo"}
    for motivo, numeros in cortes.items():
        avisos.append(f"O documento passou do limite de processamento ({motivos[motivo]}): "
                      f"{_paginas(numeros, 'a página', 'as páginas')} não foram lidas.")
    return avisos
