"""O que o monitor tem a dizer sobre um dispositivo do corpus e sobre as fontes, para a API.

Enquanto uma versão nova de uma fonte estiver pendente de revisão, os dispositivos que ela afeta
aparecem como "em revisão" nas respostas — a base não os apresenta como validados até alguém
conferir. Fonte monitorada sem verificação bem-sucedida há mais de `dias_limite()` dias aparece como
desatualizada: a base não sabe se a página oficial mudou nesse meio-tempo. O registro é relido só
quando o arquivo muda.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .registro import SUCESSO, diretorio

DIAS_SEM_VERIFICACAO_PADRAO = 30
_cache: dict = {"chave": None, "por_id": {}, "dados": {}}


def dias_limite() -> int:
    return int(os.environ.get("DIREITO_ABERTO_MONITOR_DIAS_SEM_VERIFICACAO", DIAS_SEM_VERIFICACAO_PADRAO))


def _carregar() -> tuple[dict[str, dict], dict]:
    caminho = Path(diretorio()) / "registro.json"
    try:
        estado = caminho.stat()
    except OSError:
        return {}, {}
    chave = (str(caminho), estado.st_mtime_ns, estado.st_size)
    if _cache["chave"] != chave:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        por_id: dict[str, dict] = {}
        for v in dados.get("versoes", []):
            if v.get("estado") != "pendente_revisao":
                continue
            for dispositivo in v.get("dispositivos_afetados", []):
                por_id[dispositivo] = {
                    "estado": "pendente",
                    "motivo": (
                        f"o monitor detectou mudança na página oficial desta norma em {v['capturada_em'][:10]}, "
                        "ainda não revisada. Até a revisão, confira o texto na fonte oficial."
                    ),
                    "evidencia": [v["url"], f"monitor: versão {v['versao']}"],
                    "aberta_em": v["capturada_em"][:10],
                }
        _cache.update(chave=chave, por_id=por_id, dados=dados)
    return _cache["por_id"], _cache["dados"]


def revisao_do_monitor(dispositivo_id: str) -> dict | None:
    try:
        return _carregar()[0].get(dispositivo_id)
    except (OSError, ValueError, KeyError):
        return None  # registro ilegível não derruba a API


def ultimo_sucesso(dados: dict, fonte_id: str) -> str | None:
    """Data da última verificação em que a página veio e foi lida (ou da captura da versão aceita)."""
    verificacao = (dados.get("verificacoes") or {}).get(fonte_id) or {}
    candidatos = [verificacao.get("ultimo_sucesso_em")]
    if verificacao.get("resultado") in SUCESSO:
        candidatos.append(verificacao.get("em"))
    aceita = (dados.get("aceitas") or {}).get(fonte_id)
    for v in dados.get("versoes", []):
        if v.get("versao") == aceita:
            candidatos.append(v.get("capturada_em"))
    datas = [c for c in candidatos if c]
    return max(datas) if datas else None


_fontes: dict = {"chave": None, "ids": frozenset()}


def _monitoradas() -> frozenset[str]:
    """Ids de data/monitor/fontes.json (relido só quando o arquivo muda)."""
    caminho = Path(diretorio()) / "fontes.json"
    try:
        estado = caminho.stat()
    except OSError:
        return frozenset()
    chave = (str(caminho), estado.st_mtime_ns, estado.st_size)
    if _fontes["chave"] != chave:
        _fontes.update(chave=chave, ids=frozenset(f["id"] for f in json.loads(caminho.read_text(encoding="utf-8"))["fontes"]))
    return _fontes["ids"]


def fonte_desatualizada(fonte_id: str, agora: datetime | None = None) -> dict | None:
    """Sinal de atualidade de uma fonte monitorada, ou None se ela está em dia (ou não é monitorada).

    Fonte que está em fontes.json e nunca foi conferida com sucesso também é desatualizada: a base não
    tem a página dela.
    """
    try:
        _, dados = _carregar()
        monitoradas = _monitoradas()
    except (OSError, ValueError, KeyError):
        return None
    if (fonte_id not in monitoradas and fonte_id not in (dados.get("aceitas") or {})
            and fonte_id not in (dados.get("verificacoes") or {})):
        return None
    limite = dias_limite()
    momento = agora or datetime.now(timezone.utc)
    ultima = ultimo_sucesso(dados, fonte_id)
    dias = None if ultima is None else (momento - datetime.fromisoformat(ultima)).days
    if dias is not None and dias <= limite:
        return None
    verificacao = (dados.get("verificacoes") or {}).get(fonte_id) or {}
    return {
        "fonte": fonte_id,
        "ultima_verificacao_com_sucesso": ultima,
        "dias_sem_verificacao": dias,
        "limite_dias": limite,
        "ultimo_resultado": verificacao.get("resultado"),
        "motivo": (f"a página oficial não é conferida pelo monitor há {dias} dias (limite: {limite})"
                   if dias is not None else "a página oficial nunca foi conferida com sucesso pelo monitor"),
    }
