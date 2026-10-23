"""Coleta de páginas oficiais e extração do texto vigente.

O HTML do Planalto muda a cada requisição (o anti-robô injeta tokens), mas o
texto não: o hash de integridade é calculado sobre o texto vigente
normalizado — sem script, sem estilo e sem a redação tachada (revogada) —,
nunca sobre o HTML bruto. Duas coletas seguidas da mesma página dão o mesmo
hash; foi conferido no CDC em 19/10/2026.

O portal fecha a conexão de clientes que não se apresentam como navegador;
o User-Agent abaixo é compatível e identifica o projeto. Não há robots.txt
(404 em 19/10/2026). Entre uma página e outra, `INTERVALO_S` segundos.

Falha passageira (rede, 429, 5xx) é repetida até `TENTATIVAS` vezes, com espera exponencial e um
pouco de acaso, respeitando o `Retry-After` do servidor. Bloqueio (403) e página inexistente (404)
não são repetidos: insistir contra a proteção do portal não é aceitável, e a falha fica registrada
para a próxima rodada. Falha de coleta nunca é mudança na norma.
"""

from __future__ import annotations

import random
import re
import time
from collections.abc import Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

from ..ingestao import extrair_texto_html, ler_html

USER_AGENT = (
    "Mozilla/5.0 (compatible; DireitoAberto-monitor/0.1; +https://github.com/robertochiocca/DireitoAberto)"
)
INTERVALO_S = 3.0
TIMEOUT_S = 60.0
TENTATIVAS = 3
ESPERA_BASE_S = 5.0
# Espera maior que esta (Retry-After longo) não é cumprida dentro da rodada: a fonte fica para a próxima.
ESPERA_MAXIMA_S = 120.0
_REPETIR_HTTP = {429, 500, 502, 503, 504}

_RE_CHARSET = re.compile(rb"""charset\s*=\s*["']?([A-Za-z0-9_-]+)""", re.IGNORECASE)
# "LEI Nº 8.078, DE 11 DE SETEMBRO DE 1990", "LEI Nº 9.784 , DE 29…" (espaço antes da vírgula), "LEI\nN\no\n5.869,
# DE…" (o "º" num <sup> em outra linha, CPC de 1973) e o título da Constituição.
_RE_TITULO = re.compile(
    r"^((?:LEI COMPLEMENTAR|LEI|DECRETO-LEI|DECRETO|EMENDA CONSTITUCIONAL|MEDIDA PROVISÓRIA)\s+N\s*[ºo°.]*\s*"
    r"[\d.]+\s*,?\s+DE\s+\d{1,2}[º°]?\s+DE\s+[A-ZÇ]+\s+DE\s+\d{4}"
    r"|CONSTITUIÇÃO DA REPÚBLICA FEDERATIVA DO BRASIL DE \d{4})",
    re.MULTILINE | re.IGNORECASE,
)
_RE_DOU = re.compile(r"DOU\s+de\s+(\d{1,2})\.(\d{1,2})\.(\d{4})", re.IGNORECASE)


class FalhaDeColeta(Exception):
    """A página não veio (rede, HTTP, bloqueio). Não é mudança na norma.

    `bloqueio` marca o portal dizendo para parar (403, ou espera pedida longa demais): quem roda várias
    fontes do mesmo site não insiste nas outras nesta rodada.
    """

    def __init__(self, mensagem: str, bloqueio: bool = False):
        super().__init__(mensagem)
        self.bloqueio = bloqueio


def espera_pedida(valor: str | None, agora: datetime | None = None) -> float | None:
    """Segundos pedidos no cabeçalho Retry-After (número ou data HTTP); None se ausente ou ilegível."""
    if not valor or not valor.strip():
        return None
    valor = valor.strip()
    if valor.isdigit():
        return float(valor)
    try:
        quando = parsedate_to_datetime(valor)
    except (TypeError, ValueError, IndexError):
        return None
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=timezone.utc)
    return max(0.0, (quando - (agora or datetime.now(timezone.utc))).total_seconds())


def mesmo_endereco(pedida: str, final: str) -> bool:
    """O redirecionamento ficou no mesmo site? Uma página de login, captcha ou erro em outro domínio não
    é a norma — e o texto dela não pode virar versão."""
    def host(url: str) -> str:
        return (urlsplit(url).hostname or "").lower().removeprefix("www.")

    return host(pedida) == host(final)


def baixar(url: str, *, tentativas: int = TENTATIVAS, dormir: Callable[[float], None] = time.sleep,
           get: Callable | None = None) -> bytes:
    import httpx

    get = get or httpx.get
    motivo = ""
    for tentativa in range(1, tentativas + 1):
        espera = None
        try:
            resposta = get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_S, follow_redirects=True)
        except httpx.HTTPError as exc:
            motivo = f"{type(exc).__name__}: sem resposta do servidor"
        else:
            if resposta.status_code == 200:
                final = str(resposta.url)
                if not mesmo_endereco(url, final):
                    raise FalhaDeColeta(f"a página foi redirecionada para outro site ({urlsplit(final).hostname}): "
                                        "não é a página da norma")
                return resposta.content
            motivo = f"HTTP {resposta.status_code}"
            if resposta.status_code not in _REPETIR_HTTP:
                raise FalhaDeColeta(motivo, bloqueio=resposta.status_code in (401, 403))
            espera = espera_pedida(resposta.headers.get("Retry-After"))
        if tentativa == tentativas:
            break
        if espera is None:
            espera = ESPERA_BASE_S * 2 ** (tentativa - 1) + random.uniform(0, 1)
        if espera > ESPERA_MAXIMA_S:
            raise FalhaDeColeta(f"{motivo}; o servidor pediu {espera:.0f} s de espera — a fonte fica para a próxima rodada",
                                bloqueio=True)
        dormir(espera)
    raise FalhaDeColeta(f"{motivo} (depois de {tentativas} tentativas)")


_BOMS = ((b"\xef\xbb\xbf", "utf-8-sig"), (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be"))


def decodificar(bruto: bytes) -> str:
    """Marca de ordem de bytes (BOM) primeiro; depois o charset declarado na página; sem ele, UTF-8 e, por
    fim, Windows-1252 (o comum no Planalto). A página da Lei Maria da Penha vem em UTF-16 com BOM: lida
    como Windows-1252, virava texto sem nenhum artigo (coleta de 21/10/2026)."""
    for bom, codificacao in _BOMS:
        if bruto.startswith(bom):
            return bruto[len(bom):].decode(codificacao.replace("-sig", ""), errors="replace")
    declarado = _RE_CHARSET.search(bruto[:4096])
    candidatos = [declarado.group(1).decode()] if declarado else []
    for codificacao in [*candidatos, "utf-8", "cp1252"]:
        try:
            return bruto.decode(codificacao)
        except (LookupError, UnicodeDecodeError):
            continue
    return bruto.decode("cp1252", errors="replace")


# Versão da leitura do texto vigente, gravada em cada versão registrada. 1: só as tags <strike>/<del>
# eram tachado; 2 (22/10/2026): também o estilo "text-decoration: line-through".
LEITURA = 2


def texto_vigente(bruto: bytes, leitura: int = LEITURA) -> str:
    return extrair_texto_html(decodificar(bruto), riscado_por_estilo=leitura >= 2)


def ler(bruto: bytes) -> tuple[str, list[str]]:
    """Texto vigente (leitura atual) e os alertas da leitura do riscado por estilo (elemento sem fim, ou que
    engole texto demais) — sinal de marcação quebrada, não de revogação."""
    return ler_html(decodificar(bruto))


def texto_com_tachado(bruto: bytes) -> str:
    """O texto da página inclusive com o que ela risca — para saber que artigos foram tachados."""
    return extrair_texto_html(decodificar(bruto), incluir_tachado=True)


# "Revogada pela Lei nº 13.105, de 2015" (CPC de 1973) e "(Revogado pela Lei nº 14.133, de 2021)" (Lei 8.666):
# é assim que o cabeçalho da página do Planalto marca a norma inteira revogada (conferido em 22/10/2026).
# Nas 34 fontes monitoradas, nenhum cabeçalho tem essa anotação.
_RE_REVOGACAO_DA_NORMA = re.compile(
    r"Revogad[oa]\s+pel[oa]\s+((?:Lei Complementar|Lei|Decreto-Lei|Decreto|Medida Provisória|Emenda Constitucional)"
    r"\s+n[ºo°.]*\s*[\d.]+(?:,\s*de\s*(?:\d{1,2}\.\d{1,2}\.)?\d{4})?)",
    re.IGNORECASE,
)
_CABECALHO = 2000


def revogacao_da_norma(preambulo: str) -> str | None:
    """A norma revogadora anotada no cabeçalho da página (antes do art. 1º), ou None.

    É indício, não conclusão: a revogação e a data em que produz efeito se confirmam no Diário Oficial.
    """
    m = _RE_REVOGACAO_DA_NORMA.search(preambulo[:_CABECALHO])
    return " ".join(m.group(0).split()) if m else None


def outro_ato(titulo_aceito: str | None, titulo_novo: str | None) -> str | None:
    """Motivo para desconfiar quando a página traz o título de outro ato (número ou data diferentes)."""
    if not titulo_aceito or not titulo_novo:
        return None
    def numeros(titulo: str) -> list[str]:
        return re.findall(r"\d+", titulo.replace(".", ""))

    if numeros(titulo_aceito) == numeros(titulo_novo):
        return None
    return (f"a página coletada traz o título \"{titulo_novo}\", e a versão aceita, \"{titulo_aceito}\": "
            "provável página trocada ou redirecionada — nenhuma mudança foi inferida")


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
