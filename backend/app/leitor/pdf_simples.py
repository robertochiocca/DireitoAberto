"""Gerador mínimo de PDF com texto, sem dependências.

Serve para produzir o processo fictício de demonstração e os PDFs dos testes
— documentos sintéticos cujo conteúdo é conhecido, para medir o leitor. Não é
um gerador de uso geral: uma fonte (Helvetica), quebra de linha simples e
texto em Windows-1252 (cobre o português).

Cada página é uma lista de linhas; uma linha que começa com "#" sai em
negrito e maior (título de peça). `None` no lugar da lista gera uma página
sem nenhum texto — imita a folha digitalizada, que o leitor tem de reportar
como ilegível em vez de fingir que leu.
"""

from __future__ import annotations

import textwrap

LARGURA, ALTURA = 595, 842  # A4 em pontos
MARGEM_X, TOPO = 60, 790
COLUNAS = 88


def _escapar(texto: str) -> bytes:
    bruto = texto.encode("cp1252", errors="replace")
    return bruto.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _conteudo_pagina(linhas: list[str] | None, rodape: str | None) -> bytes:
    if linhas is None:
        # Folha "digitalizada": só um retângulo cinza, nenhum operador de texto.
        return b"0.85 g 70 120 455 600 re f 0 g"
    partes = [b"BT", b"14 TL", f"{MARGEM_X} {TOPO} Td".encode()]
    for linha in linhas:
        if linha.startswith("#"):
            partes += [b"/F2 12 Tf", b"(" + _escapar(linha.lstrip("# ")) + b") '", b"/F1 10.5 Tf"]
            continue
        partes.append(b"/F1 10.5 Tf")
        for pedaco in textwrap.wrap(linha, COLUNAS) or [""]:
            partes.append(b"(" + _escapar(pedaco) + b") '")
    partes.append(b"ET")
    if rodape:
        partes += [b"BT /F1 9 Tf", f"{LARGURA - 140} {ALTURA - 30} Td".encode(),
                   b"(" + _escapar(rodape) + b") Tj ET"]
    return b"\n".join(partes)


def gerar_pdf(paginas: list[list[str] | None], rodapes: list[str | None] | None = None) -> bytes:
    """Monta o PDF. `rodapes[i]` é o carimbo de folha da página i (ex.: "fls. 12")."""
    rodapes = rodapes or [None] * len(paginas)
    objetos: list[bytes] = []

    def novo(corpo: bytes) -> int:
        objetos.append(corpo)
        return len(objetos)

    fonte = novo(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    negrito = novo(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    raiz_paginas = novo(b"")  # preenchido depois que as páginas existirem
    ids_paginas = []
    for linhas, rodape in zip(paginas, rodapes, strict=True):
        conteudo = _conteudo_pagina(linhas, rodape)
        fluxo = novo(b"<< /Length %d >>\nstream\n" % len(conteudo) + conteudo + b"\nendstream")
        ids_paginas.append(novo(
            b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] "
            b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> /Contents %d 0 R >>"
            % (raiz_paginas, LARGURA, ALTURA, fonte, negrito, fluxo)
        ))
    filhos = b" ".join(b"%d 0 R" % i for i in ids_paginas)
    objetos[raiz_paginas - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (filhos, len(ids_paginas))
    catalogo = novo(b"<< /Type /Catalog /Pages %d 0 R >>" % raiz_paginas)

    saida = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    posicoes = []
    for numero, corpo in enumerate(objetos, 1):
        posicoes.append(len(saida))
        saida += b"%d 0 obj\n" % numero + corpo + b"\nendobj\n"
    xref = len(saida)
    saida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    for pos in posicoes:
        saida += b"%010d 00000 n \n" % pos
    saida += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objetos) + 1, catalogo, xref
    )
    return bytes(saida)
