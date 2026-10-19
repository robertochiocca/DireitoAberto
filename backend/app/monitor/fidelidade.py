"""O texto do corpus corresponde ao texto oficial vigente?

Para cada dispositivo do corpus cuja fonte é monitorada, compara o `texto` com os artigos que o
rótulo nomeia, na versão aceita da página oficial (sem a redação tachada). A medida é a fração das
sequências de 8 palavras do corpus que aparecem no texto oficial: 100% é transcrição literal; abaixo
disso, condensação ou divergência. Não diz se a condensação está correta — diz onde olhar.
"""

from __future__ import annotations

import re

from .artigos import dividir
from .impacto import artigos_do_rotulo, normalizar_url
from .registro import Registro

JANELA = 8
CLASSES = [(0.98, "literal"), (0.85, "quase_literal"), (0.35, "condensado"), (0.0, "divergente")]


_MARCADOR = re.compile(r"^(?:[a-z]|[ivxlc]+)$")  # "a)", "b)", "I -", "XIII -": marcadores de lista


def _palavras(texto: str) -> list[str]:
    """Palavras comparáveis. Marcadores de lista saem dos dois lados: condensar uma lista tirando
    "a)", "b)" não deve contar como divergência."""
    from ..leitor.texto import sem_acento

    return [p for p in re.findall(r"[a-z0-9]+", sem_acento(texto.lower())) if not _MARCADOR.match(p)]


def cobertura(trecho: str, referencia: str) -> float:
    palavras = _palavras(trecho)
    if len(palavras) < JANELA:
        return 1.0 if " ".join(palavras) in " ".join(_palavras(referencia)) else 0.0
    ref = " " + " ".join(_palavras(referencia)) + " "
    janelas = [" " + " ".join(palavras[i:i + JANELA]) + " " for i in range(len(palavras) - JANELA + 1)]
    return sum(1 for j in janelas if j in ref) / len(janelas)


def classe(fracao: float) -> str:
    return next(nome for minimo, nome in CLASSES if fracao >= minimo)


def verificar_corpus(corpus: list[dict], registro: Registro) -> list[dict]:
    fontes = {normalizar_url(f["url"]): f for f in registro.fontes()}
    resultados = []
    for art in corpus:
        fonte = fontes.get(normalizar_url(art.get("fonte", "")))
        if not fonte or not (aceita := registro.versao_aceita(fonte["id"])):
            continue
        texto_oficial = registro.ler_snapshot(fonte["id"], aceita["versao"])
        artigos = dividir(texto_oficial)
        pedidos = artigos_do_rotulo(art["artigo"])
        trechos = [t for k, t in artigos.items() if k.split("#")[0] in pedidos]
        referencia = " ".join(trechos) if trechos else texto_oficial
        fracao = cobertura(art["texto"], referencia)
        resultados.append({
            "id": art["id"],
            "artigo": art["artigo"],
            "fonte": fonte["id"],
            "versao_oficial": aceita["versao"],
            "comparado_com": "artigos nomeados" if trechos else "página inteira",
            "cobertura": round(fracao, 3),
            "classe": classe(fracao),
            "marcado_como_sintese": "síntese" in art["artigo"].lower(),
        })
    return resultados
