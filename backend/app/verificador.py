"""Verificação do texto gerado pelo LLM contra as fontes recuperadas — regras determinísticas, sem pedir ao
modelo que avalie a si mesmo.

O que se confere:

- **citação literal** — trecho entre aspas (de 4 palavras ou mais) precisa estar, como está, num texto
  oficial transcrito (`trechos_oficiais`). Se só existe no resumo da base, é resumo citado como lei;
- **artigos e súmulas** — números citados precisam estar entre os dispositivos recuperados;
- **leis** — "Lei nº 13.105/2015" citada precisa ser a norma de algum dispositivo recuperado;
- **números com unidade** — prazos, percentuais, valores e quantidades ("30 dias", "25%", "R$ 600",
  "40 salários mínimos") precisam aparecer no contexto (texto oficial, texto da base, nota de vigência);
- **certeza** — "com certeza", "você vai ganhar", "é garantido": o sistema não promete resultado.

O resultado é uma lista de problemas; a política de resposta (`politica.py`) decide o que fazer com ela.
"""

from __future__ import annotations

import re
import unicodedata

from .validacao import citacoes_sem_suporte

_ASPAS = re.compile(r"[\"“«]([^\"”»]{12,}?)[\"”»]")
_LEI_CITADA = re.compile(
    r"\b(Lei(?:\s+Complementar)?|LC|Decreto(?:-Lei)?|Emenda\s+Constitucional|EC|Medida\s+Provis[óo]ria|MP)\s*"
    r"(?:n[ºo°.]*\s*)?(\d{1,2}(?:\.\d{3})+|\d{1,5})(?:\s*/\s*(\d{2,4})|,\s*de\s+[^,.;]*?(\d{4}))?", re.IGNORECASE)
_NUMERO_COM_UNIDADE = re.compile(
    r"(?:R\$\s*\d[\d.,]*|\b\d[\d.,]*\s*(?:%|por\s*cento|dias?(?:\s+[úu]teis)?|meses|m[êe]s|anos?|horas?|"
    r"sal[áa]rios?\s+m[íi]nimos?|vezes|pontos))", re.IGNORECASE)
_CERTEZA = re.compile(
    r"\b(com certeza|certamente|sem d[úu]vida|[ée] garantid[oa]|garanto|voc[êe] (?:vai|ir[áa]) ganhar|"
    r"vai ganhar a causa|tem direito garantido|[ée] certo que|n[ãa]o h[áa] como perder)\b", re.IGNORECASE)


_UNIDADES = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7,
             "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13, "quatorze": 14, "catorze": 14,
             "quinze": 15, "dezesseis": 16, "dezessete": 17, "dezoito": 18, "dezenove": 19}
_DEZENAS = {"vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50, "sessenta": 60, "setenta": 70,
            "oitenta": 80, "noventa": 90, "cem": 100}
_POR_EXTENSO = re.compile(r"\b(" + "|".join(_DEZENAS) + r")(?:\s+e\s+(" + "|".join(_UNIDADES) + r"))?\b|\b("
                          + "|".join(_UNIDADES) + r")\b")


def _plano(texto: str) -> str:
    """Minúsculas, sem acento, números por extenso em algarismos ("trinta dias" → "30 dias"), "%" unificado."""
    sem = unicodedata.normalize("NFKD", texto.lower())
    sem = "".join(c for c in sem if not unicodedata.combining(c))
    sem = re.sub(r"[–—]", "-", sem)

    def algarismos(m: re.Match) -> str:
        if m.group(3):
            return str(_UNIDADES[m.group(3)])
        return str(_DEZENAS[m.group(1)] + (_UNIDADES[m.group(2)] if m.group(2) else 0))

    sem = _POR_EXTENSO.sub(algarismos, sem).replace("por cento", "%")
    return re.sub(r"(\d) %", r"\1%", " ".join(re.findall(r"[a-z0-9%$]+(?:[.,]\d+)*", sem)))


def _numero_no_contexto(trecho: str, tokens: list[str]) -> bool:
    """O número aparece no contexto com a mesma unidade por perto ("40 salários mínimos" casa com "40 vezes o
    salário mínimo"; "25%" com "25 por cento")."""
    partes = _plano(trecho).split()
    if not partes:
        return True
    numero = partes[0] if partes[0] != "r$" else (partes[1] if len(partes) > 1 else "")
    numero = numero.rstrip("%").split(",")[0].replace(".", "")
    unidade = next((p for p in partes[1:] if not p[0].isdigit()), "%" if "%" in trecho else "")[:4]
    for i, tok in enumerate(tokens):
        if tok.rstrip("%").split(",")[0].replace(".", "") != numero:
            continue
        vizinhos = " ".join(tokens[max(0, i - 1):i + 5])
        if not unidade or unidade in vizinhos or (unidade == "%" and tok.endswith("%")):
            return True
    return False


def _contexto(artigos) -> tuple[str, str]:
    """(texto oficial transcrito, todo o contexto: oficial + texto da base + resumo + nota)."""
    oficial = " ".join(t.get("contexto", "") + " " + t["texto"] for a in artigos
                       for t in (getattr(a, "trechos_oficiais", None) or []))
    base = " ".join(f"{a.texto} {a.resumo} {a.vigencia.get('nota') or ''} {a.lei} {a.artigo}" for a in artigos)
    return oficial, f"{oficial} {base}"


def verificar(texto: str, artigos) -> list[dict]:
    """Problemas do texto gerado: [{tipo, detalhe}]. Lista vazia: nada a apontar."""
    problemas: list[dict] = []
    oficial, contexto = _contexto(artigos)
    oficial_plano, contexto_plano = _plano(oficial), _plano(contexto)

    for citacao in _ASPAS.findall(texto):
        if len(citacao.split()) < 4:
            continue
        plano = _plano(citacao.strip(" .,;:"))
        if plano and plano in oficial_plano:
            continue
        if plano and plano in contexto_plano:
            problemas.append({"tipo": "resumo_citado_como_lei",
                              "detalhe": f"o trecho entre aspas vem do resumo da base, não do texto oficial: “{citacao[:120]}”"})
        else:
            problemas.append({"tipo": "citacao_sem_fonte",
                              "detalhe": f"o trecho entre aspas não está no texto oficial recuperado: “{citacao[:120]}”"})

    for solta in citacoes_sem_suporte(texto, artigos):
        problemas.append({"tipo": "dispositivo_nao_recuperado", "detalhe": f"cita {solta}, que não está entre os recuperados"})

    normas = _plano(" ".join(f"{a.lei} {getattr(a, 'norma', '') or ''} " + " ".join(
        t["dispositivo"] for t in getattr(a, "trechos_oficiais", None) or []) for a in artigos))
    for tipo, numero, ano1, ano2 in _LEI_CITADA.findall(texto):
        alvo = numero.replace(".", "")
        if alvo not in normas.replace(".", "") and numero not in normas:
            ano = ano1 or ano2
            problemas.append({"tipo": "norma_nao_recuperada",
                              "detalhe": f"cita {tipo} {numero}{'/' + ano if ano else ''}, que não é norma de nenhum "
                                         "dispositivo recuperado"})

    tokens = contexto_plano.split()
    for numero in dict.fromkeys(m.group(0) for m in _NUMERO_COM_UNIDADE.finditer(texto)):
        if not _numero_no_contexto(numero, tokens):
            problemas.append({"tipo": "numero_sem_fonte",
                              "detalhe": f"“{numero.strip()}” não aparece no texto oficial, no texto da base nem nas notas"})

    for certeza in dict.fromkeys(m.group(0) for m in _CERTEZA.finditer(texto)):
        problemas.append({"tipo": "linguagem_de_certeza",
                          "detalhe": f"“{certeza}”: a resposta não pode prometer resultado"})
    return problemas
