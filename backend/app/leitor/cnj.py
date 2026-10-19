"""Número único de processo (Resolução CNJ nº 65/2008): NNNNNNN-DD.AAAA.J.TR.OOOO.

DD é o dígito verificador (ISO 7064, módulo 97): o número inteiro, com DD no
fim, deixa resto 1 na divisão por 97. Validar evita apresentar como número do
processo uma sequência que só tem o formato — erro de digitação, OCR ruim ou
número de outro documento.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

RE_CNJ = re.compile(r"\b(\d{7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})\b")

SEGMENTOS = {
    "1": "Supremo Tribunal Federal",
    "2": "Conselho Nacional de Justiça",
    "3": "Superior Tribunal de Justiça",
    "4": "Justiça Federal",
    "5": "Justiça do Trabalho",
    "6": "Justiça Eleitoral",
    "7": "Justiça Militar da União",
    "8": "Justiça Estadual",
    "9": "Justiça Militar Estadual",
}

# Na Justiça Estadual, TR identifica o tribunal do estado.
TRIBUNAIS_ESTADUAIS = {
    "01": "AC", "02": "AL", "03": "AP", "04": "AM", "05": "BA", "06": "CE", "07": "DF",
    "08": "ES", "09": "GO", "10": "MA", "11": "MT", "12": "MS", "13": "MG", "14": "PA",
    "15": "PB", "16": "PR", "17": "PE", "18": "PI", "19": "RJ", "20": "RN", "21": "RS",
    "22": "RO", "23": "RR", "24": "SC", "25": "SE", "26": "SP", "27": "TO",
}


@dataclass(frozen=True)
class NumeroProcesso:
    numero: str
    valido: bool
    ano: str
    segmento: str | None
    tribunal: str | None


def digito_verificador(sequencial: str, ano: str, segmento: str, tribunal: str, origem: str) -> str:
    resto = int(f"{sequencial}{ano}{segmento}{tribunal}{origem}00") % 97
    return f"{98 - resto:02d}"


def interpretar(numero: str) -> NumeroProcesso | None:
    m = RE_CNJ.fullmatch(numero.strip())
    if not m:
        return None
    seq, dv, ano, j, tr, origem = m.groups()
    valido = int(f"{seq}{ano}{j}{tr}{origem}{dv}") % 97 == 1
    tribunal = None
    if j == "8" and tr in TRIBUNAIS_ESTADUAIS:
        tribunal = f"Tribunal de Justiça — {TRIBUNAIS_ESTADUAIS[tr]}"
    return NumeroProcesso(m.group(0), valido, ano, SEGMENTOS.get(j), tribunal)


def encontrar(texto: str) -> list[str]:
    return [m.group(0) for m in RE_CNJ.finditer(texto)]
