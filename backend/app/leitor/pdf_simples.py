"""Gerador mínimo de PDF com texto, sem dependências.

Serve para produzir o processo fictício de demonstração e os PDFs dos testes
— documentos sintéticos cujo conteúdo é conhecido, para medir o leitor. Não é
um gerador de uso geral: uma fonte (Helvetica), quebra de linha simples e
texto em Windows-1252 (cobre o português).

Cada página é uma lista de linhas; uma linha que começa com "#" sai em
negrito e maior (título de peça). `None` no lugar da lista gera uma página
sem nenhum texto — imita a folha em branco ou ilegível, que o leitor tem de
reportar em vez de fingir que leu.

Dois recursos existem só para o conjunto adversarial (data/exemplos/adversariais):

- `Digitalizada([...])` desenha uma imagem ocupando a página e, por cima, as
  linhas dadas (a tarja de assinatura eletrônica que os sistemas carimbam em
  cópias digitalizadas). O carimbo de folha do rodapé continua valendo. É o
  caso perigoso: há algum texto na página, mas o conteúdo está na imagem.
- uma linha que começa com "!" é desenhada com uma fonte que o PDF não define,
  o que faz a extração devolver caracteres ilegíveis — imita fonte sem tabela
  de caracteres, comum em PDFs mal gerados.
"""

from __future__ import annotations

import textwrap
import zlib
from dataclasses import dataclass

LARGURA, ALTURA = 595, 842  # A4 em pontos
MARGEM_X, TOPO = 60, 790
COLUNAS = 88


@dataclass(frozen=True)
class Digitalizada:
    """Página-imagem, com linhas opcionais de texto por cima (tarja do sistema)."""

    linhas: tuple[str, ...] = ()


Pagina = list[str] | Digitalizada | None


def _escapar(texto: str) -> bytes:
    bruto = texto.encode("cp1252", errors="replace")
    return bruto.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _texto(linhas: list[str] | tuple[str, ...], topo: int = TOPO) -> list[bytes]:
    partes = [b"BT", b"14 TL", f"{MARGEM_X} {topo} Td".encode()]
    for linha in linhas:
        if linha.startswith("#"):
            partes += [b"/F2 12 Tf", b"(" + _escapar(linha.lstrip("# ")) + b") '", b"/F1 10.5 Tf"]
            continue
        # "/F9" não existe nos recursos da página: a extração não tem como mapear os caracteres.
        partes.append(b"/F9 10.5 Tf" if linha.startswith("!") else b"/F1 10.5 Tf")
        for pedaco in textwrap.wrap(linha.lstrip("!"), COLUNAS) or [""]:
            partes.append(b"(" + _escapar(pedaco) + b") '")
    partes.append(b"ET")
    return partes


def _conteudo_pagina(linhas: Pagina, rodape: str | None) -> bytes:
    if linhas is None:
        # Folha sem texto: só um retângulo cinza, nenhum operador de texto.
        return b"0.85 g 70 120 455 600 re f 0 g"
    if isinstance(linhas, Digitalizada):
        partes = [b"q 475 0 0 700 60 70 cm /Im1 Do Q"]
        if linhas.linhas:
            partes += _texto(linhas.linhas, topo=60)
    else:
        partes = _texto(linhas)
    if rodape:
        partes += [b"BT /F1 9 Tf", f"{LARGURA - 140} {ALTURA - 30} Td".encode(),
                   b"(" + _escapar(rodape) + b") Tj ET"]
    return b"\n".join(partes)


def _imagem() -> bytes:
    """Imagem cinza 32x32 com ruído determinístico (o PDF gerado é sempre o mesmo)."""
    pixels = bytes((i * 73 + (i // 32) * 151) % 256 for i in range(32 * 32))
    comprimido = zlib.compress(pixels, 9)
    return (b"<< /Type /XObject /Subtype /Image /Width 32 /Height 32 /ColorSpace /DeviceGray "
            b"/BitsPerComponent 8 /Filter /FlateDecode /Length %d >>\nstream\n" % len(comprimido)
            + comprimido + b"\nendstream")


def gerar_pdf(paginas: list[Pagina], rodapes: list[str | None] | None = None) -> bytes:
    """Monta o PDF. `rodapes[i]` é o carimbo de folha da página i (ex.: "fls. 12")."""
    rodapes = rodapes or [None] * len(paginas)
    objetos: list[bytes] = []

    def novo(corpo: bytes) -> int:
        objetos.append(corpo)
        return len(objetos)

    fonte = novo(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    negrito = novo(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    imagem = novo(_imagem()) if any(isinstance(p, Digitalizada) for p in paginas) else None
    raiz_paginas = novo(b"")  # preenchido depois que as páginas existirem
    ids_paginas = []
    for linhas, rodape in zip(paginas, rodapes, strict=True):
        conteudo = _conteudo_pagina(linhas, rodape)
        fluxo = novo(b"<< /Length %d >>\nstream\n" % len(conteudo) + conteudo + b"\nendstream")
        xobjeto = b" /XObject << /Im1 %d 0 R >>" % imagem if imagem and isinstance(linhas, Digitalizada) else b""
        ids_paginas.append(novo(
            b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] "
            b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >>%s >> /Contents %d 0 R >>"
            % (raiz_paginas, LARGURA, ALTURA, fonte, negrito, xobjeto, fluxo)
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
