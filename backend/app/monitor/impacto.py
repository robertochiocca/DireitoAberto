"""Que dispositivos do corpus uma mudança na fonte afeta, e os testes de busca ligados a eles."""

from __future__ import annotations

import re

from ..benchmark import carregar_casos
from ..comparacao import carregar_casos_busca
from .artigos import chave


def normalizar_url(url: str) -> str:
    url = url.strip().lower().split("#")[0]
    url = re.sub(r"^https?://", "", url)
    return re.sub(r"^www\.", "", url).rstrip("/")


def artigos_do_rotulo(rotulo: str) -> set[str]:
    """Números de artigo citados no rótulo do corpus ("Arts. 20 a 27 (síntese)" → 20…27).

    Rótulo que não começa por "Art." ("Decreto 13.135/2026 (síntese)", "Súmula 479") não nomeia
    artigos: devolve vazio, e quem chama entende que a entrada cobre a norma inteira.
    """
    if not re.match(r"\s*arts?\.", rotulo, re.IGNORECASE):
        return set()
    # Corta parágrafos, incisos e observações: "Art. 7º, XIII e XV" é só o art. 7º.
    parte = re.split(r"§|caput|\(|\b[IVXLC]+\b", rotulo)[0]
    numeros: set[str] = set()
    for ini, fim in re.findall(r"(\d{1,4})\s*[º°]?\s+a\s+(\d{1,4})", parte):
        numeros.update(str(n) for n in range(int(ini), int(fim) + 1))
    for numero, letra in re.findall(r"(\d{1,4}(?:\.\d{3})?)\s*[º°]?(?:-([A-Z]))?", parte):
        numeros.add(chave(numero, letra or None))
    return numeros


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
