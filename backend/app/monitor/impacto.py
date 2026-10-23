"""Que dispositivos do corpus uma mudança na fonte afeta, e os testes de busca ligados a eles."""

from __future__ import annotations

import re

from ..benchmark import carregar_casos
from ..comparacao import carregar_casos_busca


def normalizar_url(url: str) -> str:
    url = url.strip().lower().split("#")[0]
    url = re.sub(r"^https?://", "", url)
    return re.sub(r"^www\.", "", url).rstrip("/")


def artigos_do_rotulo(rotulo: str) -> set[str]:
    """Números de artigo citados no rótulo do corpus ("Arts. 20 a 27 (síntese)" → 20…27).

    Rótulo que não começa por "Art." ("Decreto 13.135/2026 (síntese)", "Súmula 479") não nomeia
    artigos: devolve vazio, e quem chama entende que a entrada cobre a norma inteira. A leitura é a de
    `corpus.dispositivos.interpretar_rotulo` — a versão anterior parava no primeiro artigo com letra
    ("Arts. 7º, 12-C, 22 e 24-A" virava só 7 e 12, e mudança no art. 22 não afetava a entrada).
    """
    from ..corpus.dispositivos import interpretar_rotulo

    return {ref.artigo for ref in interpretar_rotulo(rotulo)}


def dispositivos_afetados(corpus: list[dict], url: str, artigos_mudados: set[str]) -> list[str]:
    """Entradas do corpus da mesma fonte cujos artigos mudaram.

    Quando o rótulo não nomeia artigos (ex.: "Decreto 13.135/2026 (síntese)"), a entrada cobre a
    norma inteira e qualquer mudança a afeta. Artigo nomeado que sumiu da página aparece em
    `artigos_mudados` como ausente — e afeta a entrada.
    """
    alvo = normalizar_url(url)
    mudados = {a.split("#")[0] for a in artigos_mudados}
    afetados = []
    for art in corpus:
        if normalizar_url(art.get("fonte", "")) != alvo:
            continue
        nomeados = artigos_do_rotulo(art["artigo"])
        if not nomeados or nomeados & mudados:
            afetados.append(art["id"])
    return afetados


_RE_ATO = re.compile(
    r"\b(EC|Emenda Constitucional|LC|Lei Complementar|Decreto-Lei|DL|Decreto|MP|Medida Provisória|Lei)\s*"
    r"(?:n[ºo°.]*\s*)?(\d[\d.]*)",
    re.IGNORECASE,
)
_TIPO_DO_ATO = {"ec": "emenda constitucional", "emenda constitucional": "emenda constitucional",
                "lc": "lei complementar", "lei complementar": "lei complementar", "decreto-lei": "decreto-lei",
                "dl": "decreto-lei", "decreto": "decreto", "mp": "medida provisória",
                "medida provisória": "medida provisória", "lei": "lei"}


def ato_citado(texto: str) -> tuple[str, str] | None:
    """("lei", "13146") de "Lei 13.146/2015 (Estatuto…)"; None para decisão judicial, súmula, resolução."""
    m = _RE_ATO.match(texto.strip())
    if not m:
        return None
    return _TIPO_DO_ATO[m.group(1).lower()], m.group(2).replace(".", "")


def indice_de_dependencias(corpus: list[dict], fontes: list[dict], normas: list[dict] | None = None) -> dict[str, list[dict]]:
    """fonte monitorada → [{id, artigos (None = a norma inteira), via}] de cada entrada que depende dela.

    Três ligações, nesta ordem: a própria norma da entrada (campo `norma` ou a URL da fonte), com os
    artigos de `dispositivos`; os `dispositivos_adicionais` (artigo de outra norma usado no texto); e as
    normas de `vigencia.alterada_por` que são fontes monitoradas — mudança na página da norma alteradora
    pode desfazer ou refazer a alteração, então qualquer mudança nela afeta a entrada.
    """
    ids = {f["id"] for f in fontes}
    por_url = {normalizar_url(f["url"]): f["id"] for f in fontes}
    por_ato = {(n["tipo"], (n.get("numero") or "").replace(".", "")): n["id"]
               for n in normas or [] if n.get("numero") and n["id"] in ids}
    indice: dict[str, list[dict]] = {}

    def ligar(fonte_id: str, entrada: str, artigos: set[str] | None, via: str) -> None:
        for dep in indice.setdefault(fonte_id, []):
            if dep["id"] == entrada:
                dep["artigos"] = None if dep["artigos"] is None or artigos is None else dep["artigos"] | artigos
                if via not in dep["via"]:
                    dep["via"].append(via)
                return
        indice[fonte_id].append({"id": entrada, "artigos": None if artigos is None else set(artigos), "via": [via]})

    for art in corpus:
        propria = art.get("norma") if art.get("norma") in ids else por_url.get(normalizar_url(art.get("fonte", "")))
        if propria:
            artigos = {d["artigo"] for d in art.get("dispositivos", []) if d.get("artigo")} or artigos_do_rotulo(
                art.get("artigo", ""))
            ligar(propria, art["id"], artigos or None, "norma")
        for adicional in art.get("dispositivos_adicionais", []):
            if adicional.get("norma") in ids:
                ligar(adicional["norma"], art["id"], {adicional["artigo"]} if adicional.get("artigo") else None,
                      "dispositivo_adicional")
        for citada in (art.get("vigencia") or {}).get("alterada_por") or []:
            if (ato := ato_citado(citada)) and (fonte_id := por_ato.get(ato)) and fonte_id != propria:
                ligar(fonte_id, art["id"], None, "norma_alteradora")
    return indice


def afetados_pela_fonte(indice: dict[str, list[dict]], fonte_id: str, artigos_mudados: set[str],
                        norma_inteira: bool = False) -> list[str]:
    """Entradas afetadas por mudanças nos artigos da fonte (ou na página inteira, se `norma_inteira`)."""
    mudados = {a.split("#")[0] for a in artigos_mudados}
    return [dep["id"] for dep in indice.get(fonte_id, [])
            if norma_inteira or dep["artigos"] is None or dep["artigos"] & mudados]


def casos_de_regressao(ids: list[str]) -> list[tuple[str, str]]:
    casos = carregar_casos_busca() + [(c["pergunta"], c["id_corpus"]) for c in carregar_casos() if c["id_corpus"]]
    return [(pergunta, esperado) for pergunta, esperado in casos if esperado in ids]


def rodar_regressao(ids: list[str], retriever) -> list[dict]:
    """O dispositivo esperado continua no top-3 das perguntas que dependem dele?"""
    resultado = []
    for pergunta, esperado in casos_de_regressao(ids):
        encontrados = [r.id for r in retriever.buscar(pergunta, top_k=3)]
        resultado.append({"pergunta": pergunta, "esperado": esperado, "ok": esperado in encontrados})
    return resultado
