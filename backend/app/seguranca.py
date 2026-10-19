"""Proteções transversais da API: limitação de requisições, CORS e cabeçalhos.

Limitação de requisições
------------------------
Janela deslizante em memória, por chave (endereço do cliente, ou e-mail no
login). Atende a um processo único — o deploy atual (um worker no Render).
Com vários workers ou réplicas, cada um conta separado e o limite efetivo se
multiplica; aí a contagem precisa ir para um armazenamento compartilhado
(Redis, por exemplo). Está documentado em docs/security-audit.md.

Atrás de proxy (Render, Vercel), a conexão chega do proxy, e todos os
usuários dividiriam o mesmo limite. `DIREITO_ABERTO_PROXIES_CONFIAVEIS=N` faz
a API usar o N-ésimo endereço da direita para a esquerda no X-Forwarded-For —
cada proxy confiável acrescenta um à direita, e o que o cliente escreve à
esquerda (falsificável) é ignorado. Com N errado para mais, o cliente escolhe
o próprio endereço; com N errado para menos, um grupo de usuários divide o
limite. O número certo depende da cadeia de proxies do deploy e não foi
verificado em produção (docs/security-audit.md).

Variáveis de ambiente:

- `DIREITO_ABERTO_LIMITES=0` desliga a limitação (só para testes de carga).
- `DIREITO_ABERTO_PERGUNTAS_POR_MINUTO`: limite de perguntas por endereço (30).
- `DIREITO_ABERTO_CORS_ORIGENS`: origens permitidas, separadas por vírgula.
  Padrão: o Next.js em desenvolvimento. Nenhum dos frontends do projeto
  precisa de CORS em produção (o estático é servido pela própria API e o Next
  repassa /api pelo servidor); `*` libera tudo, por decisão explícita.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import HTTPException, Request

ORIGENS_PADRAO = ("http://localhost:3000", "http://127.0.0.1:3000")


def origens_cors() -> list[str]:
    bruto = os.environ.get("DIREITO_ABERTO_CORS_ORIGENS")
    if bruto is None:
        return list(ORIGENS_PADRAO)
    return [o.strip() for o in bruto.split(",") if o.strip()]


CABECALHOS_SEGURANCA = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # Nenhuma página do projeto precisa ser exibida dentro de outro site.
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "frame-ancestors 'none'",
}


class LimitadorDeRequisicoes:
    """Até `maximo` eventos por `janela_s` segundos para cada chave."""

    # Teto de chaves acompanhadas: um ataque com muitos endereços não pode
    # fazer o dicionário crescer sem limite.
    MAX_CHAVES = 50_000

    def __init__(self, relogio: Callable[[], float] = time.monotonic) -> None:
        self._eventos: dict[str, deque[float]] = {}
        self._trava = threading.Lock()
        self._relogio = relogio

    def registrar(self, chave: str, maximo: int, janela_s: float) -> float | None:
        """Conta um evento. Devolve None se cabe no limite, ou os segundos de espera."""
        agora = self._relogio()
        with self._trava:
            eventos = self._eventos.get(chave)
            if eventos is None:
                if len(self._eventos) >= self.MAX_CHAVES:
                    self._podar(agora, janela_s)
                eventos = self._eventos.setdefault(chave, deque())
            while eventos and agora - eventos[0] >= janela_s:
                eventos.popleft()
            if len(eventos) >= maximo:
                return max(janela_s - (agora - eventos[0]), 0.0)
            eventos.append(agora)
            return None

    def _podar(self, agora: float, janela_s: float) -> None:
        vazias = [c for c, ev in self._eventos.items() if not ev or agora - ev[-1] >= janela_s]
        for chave in vazias:
            del self._eventos[chave]
        if len(self._eventos) >= self.MAX_CHAVES:  # todas ativas: descarta as mais antigas
            for chave in sorted(self._eventos, key=lambda c: self._eventos[c][-1])[: self.MAX_CHAVES // 10]:
                del self._eventos[chave]

    def resetar(self) -> None:
        with self._trava:
            self._eventos.clear()


limitador = LimitadorDeRequisicoes()

# (máximo, janela em segundos) por grupo de rotas.
LIMITES = {
    "auth": (10, 60.0),           # login e registro, por endereço
    "auth-email": (5, 300.0),     # tentativas de login por conta, de qualquer endereço
    "perguntar": (int(os.environ.get("DIREITO_ABERTO_PERGUNTAS_POR_MINUTO", 30)), 60.0),
    "documento": (10, 60.0),
}


def _ativo() -> bool:
    return os.environ.get("DIREITO_ABERTO_LIMITES", "1") != "0"


def endereco_do_cliente(request: Request) -> str:
    saltos = int(os.environ.get("DIREITO_ABERTO_PROXIES_CONFIAVEIS", 0))
    if saltos > 0:
        cadeia = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
        if len(cadeia) >= saltos:
            return cadeia[-saltos]
    return request.client.host if request.client else "desconhecido"


def verificar_limite(grupo: str, chave: str) -> None:
    """Levanta 429 com Retry-After quando a chave estourou o limite do grupo."""
    if not _ativo():
        return
    maximo, janela = LIMITES[grupo]
    espera = limitador.registrar(f"{grupo}:{chave}", maximo, janela)
    if espera is not None:
        raise HTTPException(
            status_code=429,
            detail="Muitas requisições. Aguarde um pouco e tente de novo.",
            headers={"Retry-After": str(max(1, round(espera)))},
        )


def limitar(grupo: str) -> Callable[[Request], None]:
    """Dependência do FastAPI que limita o grupo de rotas por endereço do cliente."""

    def dependencia(request: Request) -> None:
        verificar_limite(grupo, endereco_do_cliente(request))

    return dependencia
