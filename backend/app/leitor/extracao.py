"""Extração de texto página a página, com registro do que NÃO foi lido.

O leitor só pode afirmar o que leu. Por isso a extração devolve, além do
texto, o estado de cada página (lida, sem texto, falha) e se o documento foi
cortado por limite. Páginas digitalizadas (imagem, sem camada de texto)
aparecem como "sem texto": este servidor não tem OCR, e o leitor diz isso em
vez de tratá-las como vazias.

Numeração: `numero` é a posição da página no PDF (1, 2, 3…), que é o que o
visualizador usa. Processos têm também a folha carimbada ("fls. 37"), que pode
começar em outro número ou pular folhas; quando o carimbo é encontrado, vai
em `folha` — as citações mostram as duas.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field

from ..documentos import DocumentoInvalido, abrir_pdf

logger = logging.getLogger(__name__)

# Teto de texto processado por documento (~ 1.500 páginas densas). Além disso,
# as páginas seguintes ficam como "não processadas" e o leitor avisa.
LIMITE_CARACTERES = 3_000_000

# Carimbo de folha: "fls. 37", "Fl. 37", "folha 37" sozinho na linha. Referências
# no meio do texto ("conforme fls. 15") apontam para outra folha e não contam.
RE_CARIMBO_FOLHA = re.compile(r"(?im)^\s*(?:fls?\.|folhas?)\s*(\d{1,6})\s*$")
_RE_HIFENIZACAO = re.compile(r"(\w)-\n(\w)")


@dataclass
class Pagina:
    numero: int                # posição no PDF, a partir de 1
    texto: str                 # texto extraído, linhas preservadas
    estado: str = "lida"       # lida · sem_texto · falha · nao_processada
    folha: str | None = None   # carimbo de folha do processo, quando houver

    @property
    def tem_texto(self) -> bool:
        return self.estado == "lida"


@dataclass
class DocumentoExtraido:
    nome: str
    hash_sha256: str
    paginas: list[Pagina]
    avisos: list[str] = field(default_factory=list)

    @property
    def total_paginas(self) -> int:
        return len(self.paginas)

    def paginas_por_estado(self, estado: str) -> list[int]:
        return [p.numero for p in self.paginas if p.estado == estado]

    @property
    def leitura_completa(self) -> bool:
        return all(p.estado == "lida" for p in self.paginas)

    def pagina(self, numero: int) -> Pagina | None:
        if 1 <= numero <= len(self.paginas):
            return self.paginas[numero - 1]
        return None


def _limpar(texto: str) -> str:
    """Junta palavras hifenizadas na quebra de linha e tira espaços sobrando."""
    texto = _RE_HIFENIZACAO.sub(r"\1\2", texto.replace("\r", ""))
    linhas = [" ".join(linha.split()) for linha in texto.split("\n")]
    return "\n".join(linha for linha in linhas if linha)


def _folha(texto: str) -> str | None:
    """Carimbo de folha: o último "fls. N" isolado da página (carimbos ficam na margem)."""
    candidatos = RE_CARIMBO_FOLHA.findall(texto)
    return candidatos[-1] if candidatos else None


def _avisos(paginas: list[Pagina]) -> list[str]:
    avisos = []
    sem_texto = [p.numero for p in paginas if p.estado == "sem_texto"]
    falhas = [p.numero for p in paginas if p.estado == "falha"]
    cortadas = [p.numero for p in paginas if p.estado == "nao_processada"]
    if sem_texto:
        avisos.append(
            f"{_lista(sem_texto, 'Página', 'Páginas')} sem texto legível — provavelmente "
            "digitalizada(s) como imagem. Este servidor não faz OCR, então o conteúdo delas "
            "NÃO foi lido e não entra no resumo."
        )
    if falhas:
        avisos.append(f"{_lista(falhas, 'Página', 'Páginas')}: falha ao extrair o texto; conteúdo não lido.")
    if cortadas:
        avisos.append(
            f"O documento passou do limite de processamento: {_lista(cortadas, 'a página', 'as páginas')} "
            "não foram lidas."
        )
    return avisos


def _lista(numeros: list[int], singular: str, plural: str) -> str:
    if len(numeros) == 1:
        return f"{singular} {numeros[0]}"
    return f"{plural} {', '.join(map(str, numeros[:-1]))} e {numeros[-1]}"


def extrair(nome: str, conteudo: bytes) -> DocumentoExtraido:
    """Extrai o documento página a página. Erros de formato viram `DocumentoInvalido`."""
    nome_min = (nome or "").lower()
    textos: list[str | None]
    if nome_min.endswith(".pdf"):
        reader = abrir_pdf(conteudo)
        textos = []
        for i, pagina in enumerate(reader.pages, 1):
            try:
                textos.append(pagina.extract_text() or "")
            except Exception as exc:  # página corrompida não derruba o documento inteiro
                logger.info("Falha ao extrair a página %d (%s).", i, type(exc).__name__)
                textos.append(None)
    elif nome_min.endswith(".txt"):
        # Em texto puro, a quebra de página é o caractere form feed.
        textos = [*conteudo.decode("utf-8", errors="replace").split("\f")]
    else:
        raise DocumentoInvalido("Formato não suportado. Envie .pdf ou .txt.")

    paginas, total = [], 0
    for numero, bruto in enumerate(textos, 1):
        if bruto is None:
            paginas.append(Pagina(numero, "", "falha"))
            continue
        texto = _limpar(bruto)
        if total >= LIMITE_CARACTERES:
            paginas.append(Pagina(numero, "", "nao_processada"))
            continue
        total += len(texto)
        paginas.append(Pagina(numero, texto, "lida" if texto else "sem_texto", _folha(texto)))

    if not any(p.tem_texto for p in paginas):
        raise DocumentoInvalido(
            "Não encontrei texto no documento. Se ele foi digitalizado como imagem, este "
            "servidor ainda não faz OCR — tente um PDF com texto selecionável."
        )
    return DocumentoExtraido(
        nome=nome,
        hash_sha256=hashlib.sha256(conteudo).hexdigest(),
        paginas=paginas,
        avisos=_avisos(paginas),
    )
