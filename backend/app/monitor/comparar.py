"""Comparação de duas versões de uma norma, artigo por artigo, com classificação conservadora.

Princípios (docs/monitor-legislativo.md):

- mudança só de forma (espaço, pontuação, maiúsculas) não é mudança de norma;
- mudança só nas anotações editoriais do Planalto ("Vide", "Vigência") não muda o dispositivo;
- texto que muda com anotação de norma alteradora é *indício* de alteração legislativa — a
  confirmação é no Diário Oficial;
- texto que muda sem norma indicada pode ser retificação, republicação ou correção editorial;
- artigo que some da página NÃO é revogação: pode ser erro da página ou da coleta;
- se a página inteira encolheu demais, a coleta é suspeita e nenhuma mudança é inferida.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import asdict, dataclass, field

# tipo → (risco, explicação para quem revisa)
TIPOS = {
    "formatacao": ("baixo", "Só mudou pontuação, espaço ou maiúsculas: o texto do dispositivo é o mesmo."),
    "anotacao_editorial": ("baixo", "Mudou só uma anotação editorial do Planalto (ex.: \"Vide\", \"Vigência\"); "
                                    "o texto do dispositivo é o mesmo."),
    "norma_nova_citada": ("medio", "A página passou a citar uma norma que alterou ou incluiu o dispositivo, mas o "
                                   "texto vigente extraído é o mesmo. Confira se a redação mudou de fato."),
    "indicio_alteracao_legislativa": ("alto", "O texto mudou e a página indica a norma que o alterou. Confirme no "
                                              "Diário Oficial e atualize a base."),
    "indicio_revogacao": ("alto", "A página passou a marcar o dispositivo como revogado. Confirme a norma revogadora "
                                  "no Diário Oficial antes de qualquer mudança na base."),
    "texto_alterado_sem_norma_indicada": ("alto", "O texto mudou sem anotação de norma alteradora: pode ser "
                                                  "retificação, republicação ou correção editorial. Confira no DOU."),
    "indicio_inclusao": ("medio", "Dispositivo novo, com anotação de inclusão por outra norma."),
    "artigo_novo_na_pagina": ("medio", "Dispositivo novo na página, sem anotação de origem."),
    "artigo_ausente_na_pagina": ("alto", "O dispositivo não aparece mais na página. Isso NÃO significa revogação: "
                                         "pode ser erro da página ou da coleta. Confira antes de qualquer conclusão."),
}

_PALAVRAS_ANOTACAO = (
    r"Redação dada|Incluíd|Acrescid|Revogad|Renumerad|Vide\b|Vigência|Regulamento|Produção de efeito|"
    r"Promulgação|Declarad|Suspens|Mensagem de veto|Vetad"
)
_RE_ANOTACAO = re.compile(r"\((?:[^()]|\([^()]*\))*?(?:" + _PALAVRAS_ANOTACAO + r")(?:[^()]|\([^()]*\))*\)",
                          re.IGNORECASE)
_RE_NORMA = re.compile(
    r"(Emenda Constitucional|Lei Complementar|Medida Provisória|Decreto-Lei|Decreto|Lei)\s+n[ºo°.]*\s*([\d.]+)"
    r"(?:,\s*de\s*(?:\d{1,2}\.\d{1,2}\.)?(\d{4}))?",
    re.IGNORECASE,
)
# Fração mínima de artigos da versão anterior que a nova precisa ter para a coleta valer.
MINIMO_ARTIGOS = 0.8


@dataclass
class Mudanca:
    artigo: str
    tipo: str
    risco: str
    explicacao: str
    trecho_anterior: str | None = None
    trecho_novo: str | None = None
    normas_citadas: list[str] = field(default_factory=list)

    def como_dict(self) -> dict:
        return asdict(self)


def _alfanumerico(texto: str) -> str:
    return " ".join(re.findall(r"\w+", texto.lower()))


def _sem_anotacoes(texto: str) -> str:
    return _RE_ANOTACAO.sub(" ", texto)


def _anotacoes(texto: str) -> list[str]:
    return [" ".join(a.split()) for a in _RE_ANOTACAO.findall(texto)]


def normas_citadas(anotacoes: list[str]) -> list[str]:
    vistas: list[str] = []
    for anotacao in anotacoes:
        for tipo, numero, ano in _RE_NORMA.findall(anotacao):
            rotulo = f"{tipo} nº {numero}" + (f"/{ano}" if ano else "")
            if rotulo not in vistas:
                vistas.append(rotulo)
    return vistas


def trechos_diferentes(antigo: str, novo: str, contexto: int = 6, limite: int = 420) -> tuple[str, str]:
    """O pedaço que mudou em cada versão, com algumas palavras de contexto."""
    a, b = antigo.split(), novo.split()
    blocos = [op for op in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes() if op[0] != "equal"]
    if not blocos:
        return "", ""
    i1, i2 = blocos[0][1], blocos[-1][2]
    j1, j2 = blocos[0][3], blocos[-1][4]

    def recorte(palavras: list[str], ini: int, fim: int) -> str:
        texto = " ".join(palavras[max(0, ini - contexto): fim + contexto])
        prefixo = "… " if ini - contexto > 0 else ""
        sufixo = " …" if fim + contexto < len(palavras) else ""
        texto = texto if len(texto) <= limite else texto[:limite].rsplit(" ", 1)[0] + " …"
        return prefixo + texto + sufixo

    return recorte(a, i1, i2), recorte(b, j1, j2)


def _mudanca(artigo: str, tipo: str, **extra) -> Mudanca:
    risco, explicacao = TIPOS[tipo]
    return Mudanca(artigo=artigo, tipo=tipo, risco=risco, explicacao=explicacao, **extra)


def classificar(artigo: str, antigo: str | None, novo: str | None) -> Mudanca | None:
    if antigo is None and novo is None:
        return None
    if antigo is None:
        assert novo is not None
        anot = _anotacoes(novo)
        incluido = any(re.search(r"Incluíd|Acrescid", x, re.IGNORECASE) for x in anot)
        return _mudanca(artigo, "indicio_inclusao" if incluido else "artigo_novo_na_pagina",
                        trecho_novo=novo[:420], normas_citadas=normas_citadas(anot))
    if novo is None:
        return _mudanca(artigo, "artigo_ausente_na_pagina", trecho_anterior=antigo[:420])
    if antigo == novo:
        return None
    anterior, atual = trechos_diferentes(antigo, novo)
    if _alfanumerico(antigo) == _alfanumerico(novo):
        return _mudanca(artigo, "formatacao", trecho_anterior=anterior, trecho_novo=atual)
    novas = [x for x in _anotacoes(novo) if x not in _anotacoes(antigo)]
    revogacao = any(re.search(r"Revogad", x, re.IGNORECASE) for x in novas)
    alteradora = any(re.search(r"Redação dada|Incluíd|Acrescid|Renumerad", x, re.IGNORECASE) for x in novas)
    if _alfanumerico(_sem_anotacoes(antigo)) == _alfanumerico(_sem_anotacoes(novo)):
        # Só "Vide", "Vigência", "Regulamento"… é editorial; norma alteradora nova, não.
        tipo = "indicio_revogacao" if revogacao else "norma_nova_citada" if alteradora else "anotacao_editorial"
        return _mudanca(artigo, tipo, trecho_anterior=anterior, trecho_novo=atual,
                        normas_citadas=normas_citadas(novas))
    if revogacao:
        tipo = "indicio_revogacao"
    elif alteradora:
        tipo = "indicio_alteracao_legislativa"
    else:
        tipo = "texto_alterado_sem_norma_indicada"
    return _mudanca(artigo, tipo, trecho_anterior=anterior, trecho_novo=atual, normas_citadas=normas_citadas(novas))


def coleta_suspeita(antigos: dict[str, str], novos: dict[str, str]) -> str | None:
    """Motivo para desconfiar da coleta (página de erro, bloqueio, corte), ou None."""
    anteriores = [k for k in antigos if k not in ("preambulo", "fecho")]
    atuais = [k for k in novos if k not in ("preambulo", "fecho")]
    if not atuais:
        return "nenhum artigo na página coletada"
    if anteriores and len(atuais) < MINIMO_ARTIGOS * len(anteriores):
        return (f"a página coletada tem {len(atuais)} artigos; a versão aceita tinha {len(anteriores)}. "
                "Provável página de erro, bloqueio ou corte — nenhuma mudança foi inferida.")
    return None


def comparar(antigos: dict[str, str], novos: dict[str, str]) -> list[Mudanca]:
    mudancas = []
    for artigo in list(dict.fromkeys([*antigos, *novos])):
        if (m := classificar(artigo, antigos.get(artigo), novos.get(artigo))) is not None:
            mudancas.append(m)
    return mudancas
