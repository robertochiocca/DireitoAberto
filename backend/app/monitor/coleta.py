"""Coleta de páginas oficiais e extração do texto vigente.

O HTML do Planalto muda a cada requisição (o anti-robô injeta tokens), mas o
texto não: o hash de integridade é calculado sobre o texto vigente
normalizado — sem script, sem estilo e sem a redação tachada (revogada) —,
nunca sobre o HTML bruto. Duas coletas seguidas da mesma página dão o mesmo
hash; foi conferido no CDC em 19/10/2026.

O portal fecha a conexão de clientes que não se apresentam como navegador;
o User-Agent abaixo é compatível e identifica o projeto. Não há robots.txt
(404 em 19/10/2026). Entre uma página e outra, `INTERVALO_S` segundos.
"""

from __future__ import annotations

import re

from ..ingestao import extrair_texto_html

USER_AGENT = (
    "Mozilla/5.0 (compatible; DireitoAberto-monitor/0.1; +https://github.com/robertochiocca/DireitoAberto)"
)
INTERVALO_S = 3.0
TIMEOUT_S = 60.0

_RE_CHARSET = re.compile(rb"""charset\s*=\s*["']?([A-Za-z0-9_-]+)""", re.IGNORECASE)
_RE_TITULO = re.compile(
    r"^((?:LEI COMPLEMENTAR|LEI|DECRETO-LEI|DECRETO|EMENDA CONSTITUCIONAL|MEDIDA PROVISÓRIA)\s+N[ºo°.]*\s*"
    r"[\d.]+,?\s+DE\s+\d{1,2}[º°]?\s+DE\s+[A-ZÇ]+\s+DE\s+\d{4})",
    re.MULTILINE | re.IGNORECASE,
)
_RE_DOU = re.compile(r"DOU\s+de\s+(\d{1,2})\.(\d{1,2})\.(\d{4})", re.IGNORECASE)


class FalhaDeColeta(Exception):
    """A página não veio (rede, HTTP, bloqueio). Não é mudança na norma."""


def baixar(url: str) -> bytes:
    import httpx

    try:
        resposta = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_S, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise FalhaDeColeta(f"{type(exc).__name__}: sem resposta do servidor") from exc
    if resposta.status_code != 200:
        raise FalhaDeColeta(f"HTTP {resposta.status_code}")
    return resposta.content


def decodificar(bruto: bytes) -> str:
    """Usa o charset declarado na página; sem ele, UTF-8 e, por fim, Windows-1252 (o comum no Planalto)."""
    declarado = _RE_CHARSET.search(bruto[:4096])
    candidatos = [declarado.group(1).decode()] if declarado else []
    for codificacao in [*candidatos, "utf-8", "cp1252"]:
        try:
            return bruto.decode(codificacao)
        except (LookupError, UnicodeDecodeError):
            continue
    return bruto.decode("cp1252", errors="replace")


def texto_vigente(bruto: bytes) -> str:
    return extrair_texto_html(decodificar(bruto))


def metadados(texto: str) -> dict:
    """Título do ato e data do DOU que a própria página informa ("não substitui o publicado no DOU de…")."""
    titulo = _RE_TITULO.search(texto[:3000])  # o título fica no topo; mais abaixo são anotações
    dou = _RE_DOU.search(texto)
    publicado = None
    if dou:
        dia, mes, ano = (int(g) for g in dou.groups())
        publicado = f"{ano:04d}-{mes:02d}-{dia:02d}"
    return {
        "titulo": " ".join(titulo.group(1).split()) if titulo else None,
        "publicado_no_dou": publicado,
    }
