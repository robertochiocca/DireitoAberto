"""O que o monitor tem a dizer sobre um dispositivo do corpus, para a API.

Enquanto uma versão nova de uma fonte estiver pendente de revisão, os dispositivos que ela afeta
aparecem como "em revisão" nas respostas — a base não os apresenta como validados até alguém
conferir. O registro é relido só quando o arquivo muda.
"""

from __future__ import annotations

import json
from pathlib import Path

from .registro import diretorio

_cache: dict = {"mtime": None, "por_id": {}}


def _carregar() -> dict[str, dict]:
    caminho = Path(diretorio()) / "registro.json"
    try:
        estado = caminho.stat()
        mtime = (estado.st_mtime_ns, estado.st_size)
    except OSError:
        return {}
    if _cache["mtime"] != mtime:
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
        _cache.update(mtime=mtime, por_id=por_id)
    return _cache["por_id"]


def revisao_do_monitor(dispositivo_id: str) -> dict | None:
    try:
        return _carregar().get(dispositivo_id)
    except (OSError, ValueError, KeyError):
        return None  # registro ilegível não derruba a API
