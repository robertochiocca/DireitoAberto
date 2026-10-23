"""Benchmark temporal v2: a versão certa do dispositivo para a data da pergunta.

Mede o mesmo caminho da API (`consulta.consultar`), em duas partes (ver data/avaliacao/temporal_v2.json):

1. **Armadilhas do v1, com versões ligadas.** A redação de 2006 de cada um dos 24 casos entra no índice
   como versão anterior da entrada vigente (`versao_de`), com a situação correta na data de referência:
   `redacao_anterior` quando a vigente já vale; `vigente`, com data final, quando a nova ainda está em
   vacatio (a jornada de 44 horas vale até 15/12/2026 — o v1 a chamava de revogada). Cada caso vira duas
   perguntas: a original ("atual") e "Em 10/04/2006, …" ("historica"). "Antes" é a ordem da busca, sem
   análise temporal (o comportamento até o ciclo anterior); "depois", a ordem da API.
2. **Perguntas sobre o corpus real**, com intenção, data e comportamento esperados.
"""

from __future__ import annotations

import json
import re
import tempfile
from datetime import date, timedelta
from pathlib import Path

from .benchmark import PREFIXO_DISTRATOR, carregar_casos
from .consulta import consultar
from .retrieval import DATA_PATH, Retriever
from .temporal import aplicabilidade, interpretar
from .vigencia import vigencia_efetiva

CAMINHO = Path(__file__).resolve().parent.parent / "data" / "avaliacao" / "temporal_v2.json"
DATA_HISTORICA = "10/04/2006"


def carregar() -> dict:
    return json.loads(CAMINHO.read_text(encoding="utf-8"))


def versao_antiga(caso: dict, sucessora: dict, hoje: date) -> dict:
    """A redação de 2006 do caso como versão anterior da entrada vigente, com a situação na data `hoje`."""
    vigencia_sucessora = vigencia_efetiva(sucessora.get("vigencia"), em=hoje)
    if vigencia_sucessora["status"] == "em_vacatio" and vigencia_sucessora.get("entra_em_vigor_em"):
        inicio = date.fromisoformat(vigencia_sucessora["entra_em_vigor_em"])
        vigencia = {"status": "vigente", "vigente_ate": (inicio - timedelta(days=1)).isoformat(),
                    "alterada_por": [caso["mudou_por"]], "nota": f"Vale até a nova redação começar. {caso['vigente']}",
                    "conferida_em": vigencia_sucessora.get("conferida_em")}
    else:
        vigencia = {"status": "redacao_anterior", "alterada_por": [caso["mudou_por"]],
                    "nota": f"Redação anterior. {caso['vigente']}", "conferida_em": "2026-10-16"}
    return {
        "id": f"{PREFIXO_DISTRATOR}{caso['id']}",
        "versao_de": caso["id_corpus"],
        "lei": f"{caso['dispositivo']} — redação de 2006",
        "artigo": caso["dispositivo"],
        "tema": caso["tema"],
        "texto": caso["obsoleto"],
        "resumo": caso["obsoleto"],
        "palavras_chave": caso["palavras_chave"],
        "fonte": "Livro do Cidadão, 3ª ed. (AGU/MJ, 2006) — paráfrase da redação da época",
        "texto_natureza": "resumo_explicativo",
        "vigencia": vigencia,
    }


def _indice_com_versoes(casos: list[dict], hoje: date) -> Retriever:
    dados = json.loads(Path(DATA_PATH).read_text(encoding="utf-8"))
    por_id = {a["id"]: a for a in dados["artigos"]}
    dados["artigos"] += [versao_antiga(c, por_id[c["id_corpus"]], hoje) for c in casos if c.get("id_corpus") in por_id]
    destino = Path(tempfile.mkdtemp(prefix="direitoaberto-temporal-")) / "versoes.json"
    destino.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    return Retriever(destino)


def _posicao(ids: list[str], alvo: str) -> int | None:
    return ids.index(alvo) + 1 if alvo in ids else None


def _pct(n: int, total: int) -> dict:
    return {"n": n, "total": total, "pct": round(100 * n / total, 1) if total else 0.0}


def _primeiro_da_dupla(ids: list[str], a: str, b: str) -> str | None:
    """Qual das duas versões aparece antes (ou a única presente)."""
    pa, pb = _posicao(ids, a), _posicao(ids, b)
    if pa is None and pb is None:
        return None
    if pb is None or (pa is not None and pa < pb):
        return a
    return b


def avaliar_versoes(hoje: date) -> dict:
    casos = [c for c in carregar_casos() if c.get("id_corpus")]
    retriever = _indice_com_versoes(casos, hoje)
    por_id = {a["id"]: a for a in retriever.artigos}
    resultados = []
    for caso in casos:
        antiga, atual = f"{PREFIXO_DISTRATOR}{caso['id']}", caso["id_corpus"]
        # A que vale hoje: a vigente, salvo quando ela ainda está em vacatio (então é a antiga).
        vale_hoje = antiga if vigencia_efetiva(por_id[antiga]["vigencia"], em=hoje)["status"] == "vigente" else atual
        # Em 2006 valia a redação antiga — e também a entrada do corpus quando ela mesma descreve a regra que
        # deixou de valer depois (art. 262 do CTB, revogado em 2016; art. 1.790 do CC, inconstitucional em 2017).
        status_atual = vigencia_efetiva(por_id[atual]["vigencia"], em=hoje)["status"]
        validas_2006 = {antiga} | ({atual} if status_atual in ("revogada", "inconstitucional", "redacao_anterior") else set())
        for variante, pergunta in (("atual", caso["pergunta"]),
                                   ("historica", f"Em {DATA_HISTORICA}, {caso['pergunta'][0].lower()}{caso['pergunta'][1:]}")):
            antes = [r.id for r in retriever.buscar(re.sub(r"^Em \d\d/\d\d/\d{4}, ", "", pergunta), adaptativo=True)]
            consulta = consultar(retriever, pergunta, hoje)
            depois = [r.id for r in consulta.artigos]
            certas = {vale_hoje} if variante == "atual" else validas_2006
            primeira = next((r for r in consulta.artigos if r.id in (antiga, atual)), None)
            incerta_declarada = (variante == "historica" and primeira is not None and consulta.avisos != []
                                 and aplicabilidade(primeira, date(2006, 4, 10), hoje).codigo == 1)
            resultados.append({
                "caso": caso["id"], "variante": variante, "certas": sorted(certas),
                "as_duas_recuperadas": antiga in depois and atual in depois,
                "certa_primeiro_antes": _primeiro_da_dupla(antes, antiga, atual) in certas,
                "certa_primeiro_depois": _primeiro_da_dupla(depois, antiga, atual) in certas,
                "certa_ou_incerteza_declarada": _primeiro_da_dupla(depois, antiga, atual) in certas or incerta_declarada,
                "certa_recuperada": bool(certas & set(depois)),
                "aviso_temporal": bool(consulta.avisos) if variante == "historica" else None,
            })

    def medir(variante: str) -> dict:
        grupo = [r for r in resultados if r["variante"] == variante]
        duplas = [r for r in grupo if r["as_duas_recuperadas"]]
        return {
            "perguntas": len(grupo),
            "com_as_duas_versoes": len(duplas),
            "versao_certa_primeiro_antes": _pct(sum(r["certa_primeiro_antes"] for r in duplas), len(duplas)),
            "versao_certa_primeiro_depois": _pct(sum(r["certa_primeiro_depois"] for r in duplas), len(duplas)),
            "versao_certa_primeiro_ou_incerteza_declarada": _pct(
                sum(r["certa_ou_incerteza_declarada"] for r in duplas), len(duplas)),
            "versao_certa_recuperada": _pct(sum(r["certa_recuperada"] for r in grupo), len(grupo)),
            **({"com_aviso_temporal": _pct(sum(bool(r["aviso_temporal"]) for r in grupo), len(grupo))}
               if variante == "historica" else {}),
        }

    return {"atual": medir("atual"), "historica": medir("historica"), "casos": resultados}


_APLICABILIDADE = {0: "aplicavel", 1: "incerta", 2: "nao_aplicavel"}


def avaliar_perguntas(hoje: date, retriever: Retriever | None = None) -> dict:
    retriever = retriever or Retriever()
    dados = carregar()
    resultados = []
    for p in dados["perguntas"]:
        consulta = consultar(retriever, p["pergunta"], hoje)
        ids = [r.id for r in consulta.artigos]
        antes = [r.id for r in retriever.buscar(p["pergunta"], adaptativo=True)]
        t = interpretar(p["pergunta"], hoje)
        data_obtida = t.data_referencia.isoformat() if t.data_referencia else None
        if data_obtida and t.so_ano:
            data_obtida = data_obtida[:4]
        principal = next((r for r in consulta.artigos if r.id in p["aceitos"]), None)
        item = {
            "id": p["id"],
            "intencao_ok": t.intencao == p["intencao"],
            "data_ok": data_obtida == p.get("data"),
            "esclarecimento_ok": t.pede_esclarecimento == p["esclarecer"],
            "aceito_no_topo_antes": bool(antes) and antes[0] in p["aceitos"],
            "aceito_no_topo_depois": bool(ids) and ids[0] in p["aceitos"],
            "aceito_recuperado": principal is not None,
            "obtido": {"intencao": t.intencao, "data": data_obtida, "esclarecer": t.pede_esclarecimento, "ids": ids},
        }
        if "situacao" in p:
            item["situacao_ok"] = principal is not None and principal.vigencia.get("status") == p["situacao"]
        if "aplicabilidade" in p and principal is not None:
            obtida = _APLICABILIDADE[aplicabilidade(principal, t.data_referencia or hoje, hoje).codigo]
            esperadas = {"nao_aplicavel_ou_incerta": {"nao_aplicavel", "incerta"}}.get(p["aplicabilidade"],
                                                                                    {p["aplicabilidade"]})
            item["aplicabilidade_ok"] = obtida in esperadas
            item["obtido"]["aplicabilidade"] = obtida
        resultados.append(item)

    def taxa(chave: str) -> dict:
        com = [r for r in resultados if chave in r]
        return _pct(sum(bool(r[chave]) for r in com), len(com))

    return {
        "perguntas": len(resultados),
        "intencao": taxa("intencao_ok"),
        "data_de_referencia": taxa("data_ok"),
        "pedido_de_esclarecimento": taxa("esclarecimento_ok"),
        "aceito_no_topo_antes": taxa("aceito_no_topo_antes"),
        "aceito_no_topo_depois": taxa("aceito_no_topo_depois"),
        "aceito_recuperado": taxa("aceito_recuperado"),
        "situacao_de_vigencia": taxa("situacao_ok"),
        "aplicabilidade_na_data": taxa("aplicabilidade_ok"),
        "falhas": [r for r in resultados if not all(v for k, v in r.items() if k.endswith("_ok"))],
    }


def rodar(hoje: date | None = None) -> dict:
    hoje = hoje or date.fromisoformat(carregar()["data_de_referencia"])
    return {"data_de_referencia": hoje.isoformat(), "versoes": avaliar_versoes(hoje),
            "perguntas_do_corpus": avaliar_perguntas(hoje)}
