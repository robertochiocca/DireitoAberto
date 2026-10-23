"""Resumo de uma rodada do monitor, código de saída e arquivos de alerta.

Códigos de saída de `scripts/monitor.py verificar` (o agendador usa para avisar alguém):

- 0 — nada a fazer: nenhuma falha e nenhuma versão esperando revisão;
- 1 — há versão pendente de revisão humana (nova ou antiga na fila);
- 2 — a rodada ficou incompleta: falha de coleta, coleta suspeita ou erro interno em alguma fonte.

Cada rodada em modo controlado grava um JSON em `data/monitor/alertas/` (os `MAX_ALERTAS` mais
recentes ficam; os mais velhos saem). O alerta não contém texto de norma nem dado pessoal: fonte,
versão, eventos, dispositivos afetados e o motivo de cada falha.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .registro import agora_iso

MAX_ALERTAS = 90
FALHAS = ("falha_de_coleta", "coleta_suspeita", "erro_interno")


def resumir(resultados: dict[str, dict], pendentes_na_fila: list[dict], desatualizadas: list[dict],
            simulacao: bool) -> dict:
    novas = [{"fonte": f, **{k: r.get(k) for k in ("versao", "estado", "eventos", "dispositivos_afetados", "relatorio")}}
             for f, r in resultados.items() if r["resultado"] == "nova_versao"]
    falhas = [{"fonte": f, "resultado": r["resultado"], "detalhe": r["detalhe"]}
              for f, r in resultados.items() if r["resultado"] in FALHAS]
    codigo = 2 if falhas else 1 if pendentes_na_fila or any(n["estado"] == "pendente_revisao" for n in novas) else 0
    return {
        "em": agora_iso(),
        "modo": "simulacao" if simulacao else "controlado",
        "codigo_de_saida": codigo,
        "contagem": dict(Counter(r["resultado"] for r in resultados.values())),
        "novas_versoes": novas,
        "falhas": falhas,
        "pendentes_na_fila": [{k: v.get(k) for k in ("fonte", "versao", "capturada_em", "relatorio")}
                              for v in pendentes_na_fila],
        "fontes_desatualizadas": desatualizadas,
    }


def gravar(base: Path, resumo: dict) -> Path:
    pasta = base / "alertas"
    pasta.mkdir(parents=True, exist_ok=True)
    nome = resumo["em"].replace(":", "").replace("-", "").replace("+0000", "Z")
    caminho = pasta / f"{nome}.json"
    n = 2
    while caminho.exists():  # duas rodadas no mesmo segundo
        caminho, n = pasta / f"{nome}-{n}.json", n + 1
    caminho.write_text(json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for velho in sorted(pasta.glob("*.json"), key=_ordem)[:-MAX_ALERTAS]:
        velho.unlink()
    return caminho


def _ordem(caminho: Path) -> tuple[str, int]:
    """"…Z.json" é o primeiro do segundo; "…Z-2.json", o segundo ("-" vem antes de "." na ordem do texto)."""
    nome, _, n = caminho.stem.partition("Z-")
    return nome, int(n) if n.isdigit() else 1
