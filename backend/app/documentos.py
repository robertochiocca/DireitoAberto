"""Extração de texto de documentos enviados pelo cidadão (nota fiscal, contrato…).

Suporta .txt e .pdf. O texto extraído é combinado com a pergunta para
enriquecer a busca no corpus — nenhum documento é armazenado.

Limites (todo arquivo vem de fora e pode ter sido feito para derrubar o
servidor): tamanho lido em blocos, nunca o arquivo inteiro de uma vez;
número de páginas; e mensagens de erro que não repassam detalhes internos do
leitor de PDF.
"""

from __future__ import annotations

import io
import logging
import os

from pypdf import PdfReader

logger = logging.getLogger(__name__)

# Limite do trecho usado como contexto: evita estourar a consulta BM25/LLM.
LIMITE_CARACTERES = 4000

LIMITE_BYTES = int(float(os.environ.get("DIREITO_ABERTO_UPLOAD_MAX_MB", 5)) * 1024 * 1024)
LIMITE_PAGINAS = int(os.environ.get("DIREITO_ABERTO_UPLOAD_MAX_PAGINAS", 300))

EXTENSOES_SUPORTADAS = (".txt", ".pdf")

_BLOCO = 64 * 1024


class DocumentoInvalido(ValueError):
    pass


class DocumentoGrandeDemais(DocumentoInvalido):
    pass


async def ler_upload_limitado(arquivo, limite: int = LIMITE_BYTES) -> bytes:
    """Lê o upload em blocos e para assim que passar do limite.

    `await arquivo.read()` sem tamanho carregaria o arquivo inteiro na
    memória antes de qualquer verificação.
    """
    partes, total = [], 0
    while bloco := await arquivo.read(_BLOCO):
        total += len(bloco)
        if total > limite:
            raise DocumentoGrandeDemais(
                f"Arquivo maior que {limite // (1024 * 1024)} MB."
            )
        partes.append(bloco)
    return b"".join(partes)


def abrir_pdf(conteudo: bytes, limite_paginas: int = LIMITE_PAGINAS) -> PdfReader:
    """Abre o PDF com as verificações comuns; erros viram `DocumentoInvalido`."""
    try:
        reader = PdfReader(io.BytesIO(conteudo))
        if reader.is_encrypted:
            raise DocumentoInvalido(
                "O PDF está protegido por senha. Salve uma cópia sem senha e envie de novo."
            )
        paginas = len(reader.pages)
    except DocumentoInvalido:
        raise
    except Exception as exc:
        # O detalhe vai ao log, não ao cliente: mensagens do leitor de PDF
        # expõem a estrutura interna do arquivo e da biblioteca.
        logger.info("PDF ilegível (%s).", type(exc).__name__)
        raise DocumentoInvalido(
            "Não consegui ler o PDF: o arquivo parece corrompido ou fora do padrão."
        ) from exc
    if paginas > limite_paginas:
        raise DocumentoInvalido(
            f"O PDF tem {paginas} páginas; o limite é {limite_paginas}. "
            "Envie só as partes que interessam."
        )
    return reader


def extrair_texto(nome_arquivo: str, conteudo: bytes) -> str:
    nome = (nome_arquivo or "").lower()
    if nome.endswith(".txt"):
        texto = conteudo.decode("utf-8", errors="replace")
    elif nome.endswith(".pdf"):
        reader = abrir_pdf(conteudo)
        try:
            texto = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            logger.info("Falha ao extrair texto do PDF (%s).", type(exc).__name__)
            raise DocumentoInvalido(
                "Não consegui extrair o texto do PDF: o arquivo parece corrompido."
            ) from exc
    else:
        raise DocumentoInvalido(
            f"Formato não suportado. Envie {' ou '.join(EXTENSOES_SUPORTADAS)}."
        )

    texto = " ".join(texto.split())
    if not texto:
        raise DocumentoInvalido("O documento não contém texto extraível.")
    return texto[:LIMITE_CARACTERES]
