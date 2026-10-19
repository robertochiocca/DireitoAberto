"""Verificação de uma fonte: coleta, comparação, impacto, relatório e registro."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from ..retrieval import DATA_PATH, Retriever
from . import artigos as artigos_mod
from . import coleta, relatorio
from .comparar import coleta_suspeita, comparar
from .impacto import dispositivos_afetados, rodar_regressao
from .registro import Registro, agora_iso


def _corpus(caminho: Path = DATA_PATH) -> list[dict]:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))["artigos"]


def verificar(
    fonte: dict,
    registro: Registro,
    baixar: Callable[[str], bytes] = coleta.baixar,
    retriever: Retriever | None = None,
) -> dict:
    """Verifica uma fonte e devolve o que aconteceu: {resultado, detalhe, versao?}."""
    try:
        bruto = baixar(fonte["url"])
    except coleta.FalhaDeColeta as exc:
        registro.registrar_verificacao(fonte["id"], "falha_de_coleta", str(exc))
        return {"resultado": "falha_de_coleta", "detalhe": str(exc)}

    texto = coleta.texto_vigente(bruto)
    hash_texto = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    numero = hash_texto[:16]
    novos = artigos_mod.dividir(texto)
    base = {
        "fonte": fonte["id"],
        "versao": numero,
        "hash_sha256": hash_texto,
        "url": fonte["url"],
        "capturada_em": agora_iso(),
        **coleta.metadados(texto),
        "artigos": len([k for k in novos if k not in ("preambulo", "fecho")]),
        "caracteres": len(texto),
    }

    aceita = registro.versao_aceita(fonte["id"])
    if aceita is None:
        registro.registrar_versao({**base, "estado": "linha_de_base", "anterior": None, "mudancas": [],
                                   "resumo_mudancas": {}, "dispositivos_afetados": [], "regressao": [],
                                   "relatorio": None, "decisao": None}, texto)
        registro.registrar_verificacao(fonte["id"], "linha_de_base", "primeira captura; não revisada")
        return {"resultado": "linha_de_base", "detalhe": f"{base['artigos']} artigos", "versao": numero}

    if numero == aceita["versao"]:
        registro.registrar_verificacao(fonte["id"], "sem_mudanca")
        return {"resultado": "sem_mudanca", "detalhe": "", "versao": numero}
    try:
        ja = registro.versao(numero)
        registro.registrar_verificacao(fonte["id"], "versao_ja_registrada", ja["estado"])
        return {"resultado": "versao_ja_registrada", "detalhe": ja["estado"], "versao": numero}
    except KeyError:
        pass

    antigos = artigos_mod.dividir(registro.ler_snapshot(fonte["id"], aceita["versao"]))
    if motivo := coleta_suspeita(antigos, novos):
        registro.registrar_verificacao(fonte["id"], "coleta_suspeita", motivo)
        return {"resultado": "coleta_suspeita", "detalhe": motivo}

    mudancas = [m.como_dict() for m in comparar(antigos, novos)]
    riscos = Counter(m["risco"] for m in mudancas)
    mudados = {m["artigo"] for m in mudancas if m["risco"] != "baixo"}
    afetados = dispositivos_afetados(_corpus(), fonte["url"], mudados) if mudados else []
    regressao = rodar_regressao(afetados, retriever or Retriever()) if afetados else []
    so_baixo = not riscos.get("alto") and not riscos.get("medio")
    versao = {
        **base,
        "estado": "aceita" if so_baixo else "pendente_revisao",
        "anterior": aceita["versao"],
        "mudancas": mudancas,
        "resumo_mudancas": dict(riscos),
        "dispositivos_afetados": afetados,
        "regressao": regressao,
        "decisao": {"resultado": "aceita_automaticamente", "responsavel": "monitor (só mudanças de risco baixo)",
                    "em": agora_iso(), "nota": ""} if so_baixo else None,
    }
    nome_relatorio = f"relatorios/{base['capturada_em'][:10]}-{fonte['id']}-{numero}.md"
    versao["relatorio"] = nome_relatorio
    caminho = registro.base / nome_relatorio
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(relatorio.gerar(fonte, versao, aceita), encoding="utf-8")
    registro.registrar_versao(versao, texto)
    registro.registrar_verificacao(fonte["id"], "nova_versao", versao["estado"])
    return {"resultado": "nova_versao", "detalhe": versao["estado"], "versao": numero}
