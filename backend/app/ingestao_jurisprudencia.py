"""Ingestão semiautomatizada de súmulas dos tribunais (STF, STJ, TST).

Os portais dos tribunais ficam atrás de WAF/anti-robô, então o fluxo aceita
duas entradas: a URL (quando acessível) ou um arquivo HTML salvo direto do
navegador ("Salvar página como…"). O parser extrai os enunciados e gera
esqueletos no formato do corpus, com `"revisado": false` — a revisão humana
(resumo em linguagem simples, tema, vigência) decide o que entra na base.

Uso via CLI: `python scripts/ingerir_jurisprudencia.py --tribunal stj --arquivo sumulas.html`.
"""

from __future__ import annotations

import re

from .ingestao import extrair_texto_html

TRIBUNAIS = {
    "stf": {
        "nome": "Supremo Tribunal Federal",
        "fonte": "https://portal.stf.jus.br/jurisprudencia/sumariosumulas.asp?base=26",
    },
    "stj": {
        "nome": "Superior Tribunal de Justiça",
        "fonte": "https://scon.stj.jus.br/SCON/sumstj/",
    },
    "tst": {
        "nome": "Tribunal Superior do Trabalho",
        "fonte": "https://jurisprudencia.tst.jus.br/",
    },
}

# Cabeçalhos aceitos: "Súmula Vinculante 25", "SÚMULA N. 479", "Súmula nº 443",
# e o formato do TST "SUM-443". Nº pode vir como º/°/o/. — portais variam.
_RE_SUMULA = re.compile(
    r"(?im)^\s*(?:S[ÚU]MULA(?P<vinculante>\s+VINCULANTE)?\s*(?:N\s*[º°oO.]*\s*)?|SUM-)(?P<numero>\d+)\b[.: -]*",
)


def extrair_sumulas(html: str) -> list[dict]:
    """Divide a página em enunciados: [{'numero': '479', 'vinculante': bool, 'texto': ...}]."""
    texto = extrair_texto_html(html)
    encontrados = list(_RE_SUMULA.finditer(texto))
    sumulas = []
    for i, m in enumerate(encontrados):
        fim = encontrados[i + 1].start() if i + 1 < len(encontrados) else len(texto)
        corpo = " ".join(texto[m.end():fim].split())
        if not corpo:
            continue
        sumulas.append(
            {
                "numero": m.group("numero"),
                "vinculante": m.group("vinculante") is not None,
                "texto": corpo,
            }
        )
    return sumulas


def gerar_esqueletos_jurisprudencia(
    html: str,
    tribunal: str,
    fonte: str | None = None,
    tema: str = "revisar",
    numeros: list[str] | None = None,
) -> list[dict]:
    """Gera entradas no formato do corpus (tipo=jurisprudencia), para revisão humana."""
    tribunal = tribunal.lower()
    if tribunal not in TRIBUNAIS:
        raise ValueError(f"Tribunal desconhecido: {tribunal!r}. Use: {', '.join(TRIBUNAIS)}.")
    info = TRIBUNAIS[tribunal]
    fonte = fonte or info["fonte"]

    esqueletos = []
    for s in extrair_sumulas(html):
        if numeros and s["numero"] not in numeros:
            continue
        vinculante = tribunal == "stf" and s["vinculante"]
        rotulo = "Súmula Vinculante" if vinculante else "Súmula"
        # Segue a convenção de ids do corpus: stf-sv25, stj-sumula479, tst-sumula338.
        sufixo = f"sv{s['numero']}" if vinculante else f"sumula{s['numero']}"
        esqueletos.append(
            {
                "id": f"{tribunal}-{sufixo}",
                "tipo": "jurisprudencia",
                "tribunal": tribunal.upper(),
                "lei": f"{rotulo} nº {s['numero']} do {info['nome']}",
                "artigo": f"{rotulo} {s['numero']}",
                "tema": tema,
                "texto": s["texto"],
                "resumo": "TODO: escrever resumo em linguagem simples (revisão humana)",
                "palavras_chave": [],
                "fonte": fonte,
                "revisado": False,
            }
        )
    return esqueletos
