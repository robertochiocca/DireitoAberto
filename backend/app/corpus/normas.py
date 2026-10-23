"""Registro das normas do corpus: identidade (tipo, número, data), órgão emissor e fonte oficial.

Tipo, número e data saem do título que a própria página oficial traz ("LEI Nº 8.078, DE 11 DE
SETEMBRO DE 1990"); a data de publicação, da nota "não substitui o publicado no DOU de …"; para a
Constituição, que não tem título nesse formato, da data do fecho ("Brasília, 5 de outubro de 1988").
Nada é digitado à mão: o que a página não informa fica `null`.

A URN segue a regra do padrão LexML (urn:lex:br:federal:<tipo>:<data>;<número>), montada a partir
desses dados; não foi conferida no portal LexML — por isso `urn_conferida: false`.
"""

from __future__ import annotations

import re

from ..monitor.artigos import dividir
from ..monitor.registro import Registro

MESES = {m: i for i, m in enumerate(
    ["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
     "novembro", "dezembro"], start=1)}

_TITULO = re.compile(
    r"^(?P<tipo>LEI COMPLEMENTAR|LEI|DECRETO-LEI|DECRETO|EMENDA CONSTITUCIONAL|MEDIDA PROVISÓRIA)\s+N[ºo°.]*\s*"
    r"(?P<numero>[\d.]+),?\s+DE\s+(?P<dia>\d{1,2})[º°]?\s+DE\s+(?P<mes>[A-ZÇ]+)\s+DE\s+(?P<ano>\d{4})",
    re.IGNORECASE,
)
_FECHO = re.compile(r"Brasília,\s+(?P<dia>\d{1,2})\s+de\s+(?P<mes>[a-zç]+)\s+de\s+(?P<ano>\d{4})", re.IGNORECASE)
TIPOS_LEXML = {
    "lei": "lei", "lei complementar": "lei.complementar", "decreto-lei": "decreto.lei", "decreto": "decreto",
    "emenda constitucional": "emenda.constitucional", "medida provisoria": "medida.provisoria",
    "constituicao": "constituicao",
}


def _sem_acento(texto: str) -> str:
    from ..leitor.texto import sem_acento

    return sem_acento(texto)


def _data(dia: str, mes: str, ano: str) -> str | None:
    numero_mes = MESES.get(_sem_acento(mes.lower()))
    return f"{int(ano):04d}-{numero_mes:02d}-{int(dia):02d}" if numero_mes else None


def identidade(fonte: dict, versao: dict, texto: str) -> dict:
    """Tipo, número e data da norma conforme a página oficial; `evidencia` diz de onde saiu cada dado."""
    if fonte.get("tipo") == "constituicao":
        fecho = _FECHO.search(dividir(texto).get("fecho", "") or "")
        return {
            "tipo": "constituicao", "numero": None,
            "data": _data(*fecho.group("dia", "mes", "ano")) if fecho else None,
            "evidencia": "data do fecho da página oficial" if fecho else "data não encontrada na página",
        }
    titulo = _TITULO.search(versao.get("titulo") or "")
    if not titulo:
        return {"tipo": fonte.get("tipo"), "numero": None, "data": None,
                "evidencia": "título da página oficial não reconhecido: tipo e data não verificados"}
    return {
        "tipo": _sem_acento(titulo.group("tipo").lower()),
        "numero": titulo.group("numero"),
        "data": _data(*titulo.group("dia", "mes", "ano")),
        "evidencia": f"título da página oficial: {versao['titulo']}",
    }


def urn_lexml(tipo: str | None, data: str | None, numero: str | None) -> str | None:
    lexml = TIPOS_LEXML.get(tipo or "")
    if not lexml or not data:
        return None
    return f"urn:lex:br:federal:{lexml}:{data};{(numero or data[:4]).replace('.', '')}"


def montar(registro: Registro, manuais: list[dict]) -> list[dict]:
    """Normas das fontes monitoradas (dados da página) mais as fontes sem coleta automática."""
    normas = []
    for fonte in registro.fontes():
        versao = registro.versao_aceita(fonte["id"])
        if versao is None:
            continue
        ident = identidade(fonte, versao, registro.ler_snapshot(fonte["id"], versao["versao"]))
        normas.append({
            "id": fonte["id"],
            "nome": fonte["nome"],
            **{k: ident[k] for k in ("tipo", "numero", "data")},
            "publicado_no_dou": versao.get("publicado_no_dou"),
            "jurisdicao": "federal",
            "orgao_emissor": fonte["orgao_emissor"],
            "fonte_oficial": fonte["url"],
            "fonte_monitorada": True,
            "urn_lexml": urn_lexml(ident["tipo"], ident["data"], ident["numero"]),
            "urn_conferida": False,
            "evidencia": ident["evidencia"],
            "versao_de_referencia": versao["versao"],
        })
    return normas + manuais
