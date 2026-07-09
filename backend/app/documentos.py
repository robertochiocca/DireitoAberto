"""Extração de texto de documentos enviados pelo cidadão (nota fiscal, contrato…).

Suporta .txt e .pdf. O texto extraído é combinado com a pergunta para
enriquecer a busca no corpus — nenhum documento é armazenado.
"""

from __future__ import annotations

import io

from pypdf import PdfReader

# Limite do trecho usado como contexto: evita estourar a consulta BM25/LLM.
LIMITE_CARACTERES = 4000

EXTENSOES_SUPORTADAS = (".txt", ".pdf")


class DocumentoInvalido(ValueError):
    pass


def extrair_texto(nome_arquivo: str, conteudo: bytes) -> str:
    nome = (nome_arquivo or "").lower()
    if nome.endswith(".txt"):
        texto = conteudo.decode("utf-8", errors="replace")
    elif nome.endswith(".pdf"):
        try:
            reader = PdfReader(io.BytesIO(conteudo))
            texto = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise DocumentoInvalido(f"Não consegui ler o PDF: {exc}") from exc
    else:
        raise DocumentoInvalido(
            f"Formato não suportado. Envie {' ou '.join(EXTENSOES_SUPORTADAS)}."
        )

    texto = " ".join(texto.split())
    if not texto:
        raise DocumentoInvalido("O documento não contém texto extraível.")
    return texto[:LIMITE_CARACTERES]
