"""Comparação de duas versões de uma norma, artigo por artigo, com classificação conservadora.

Princípios (docs/monitor-legislativo.md):

- mudança só de forma (espaço, pontuação, maiúsculas) não é mudança de norma;
- anotação que só ajuda a navegar ("Vide" um decreto, "Regulamento", "Mensagem de veto") não muda o
  dispositivo; anotação com efeito jurídico possível (inconstitucionalidade, suspensão, vigência,
  produção de efeitos, veto, remissão a lei nova) vai para revisão mesmo com o texto igual;
- texto que muda com anotação de norma alteradora é *indício* de alteração legislativa — a
  confirmação é no Diário Oficial;
- texto que muda sem norma indicada pode ser retificação, republicação ou correção editorial;
- artigo que some da página NÃO é revogação: pode ser erro da página ou da coleta. Artigo que a página
  passa a mostrar riscado é indício (o Planalto risca a redação revogada), e vai para revisão;
- se a página inteira encolheu demais e o que sumiu não está riscado, a coleta é suspeita e nenhuma
  mudança é inferida.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field

from .artigos import base

# tipo → (risco, explicação para quem revisa)
TIPOS = {
    "formatacao": ("baixo", "Só mudou pontuação, espaço ou maiúsculas: o texto do dispositivo é o mesmo."),
    "anotacao_editorial": ("baixo", "Mudou só uma anotação de navegação do Planalto (\"Vide\" um decreto ou "
                                    "regulamento, \"Regulamento\", \"Mensagem de veto\"); o texto do dispositivo é o "
                                    "mesmo."),
    "anotacao_de_vigencia": ("medio", "A página passou a anotar vigência, produção de efeitos, veto ou promulgação de "
                                      "partes vetadas. A data a partir da qual o dispositivo vale pode ter mudado: "
                                      "confira no Diário Oficial."),
    "remissao_a_norma_nova": ("medio", "A página passou a remeter (\"Vide\") a uma lei, medida provisória ou emenda "
                                       "que não citava. Outra norma pode afetar o dispositivo sem mudar o texto dele: "
                                       "confira."),
    "anotacao_de_controle_constitucional": ("alto", "A página passou a anotar decisão de controle de "
                                                    "constitucionalidade (inconstitucionalidade, suspensão, ADI, ADC, "
                                                    "ADPF). A validade do dispositivo pode ter mudado mesmo com o texto "
                                                    "igual: confira a decisão antes de qualquer mudança na base."),
    "norma_nova_citada": ("medio", "A página passou a citar uma norma que alterou ou incluiu o dispositivo, mas o "
                                   "texto vigente extraído é o mesmo. Confira se a redação mudou de fato."),
    "indicio_alteracao_legislativa": ("alto", "O texto mudou e a página indica a norma que o alterou. Confirme no "
                                              "Diário Oficial e atualize a base."),
    "indicio_revogacao": ("alto", "A página passou a marcar o dispositivo como revogado. Confirme a norma revogadora "
                                  "no Diário Oficial antes de qualquer mudança na base."),
    "artigo_tachado_na_pagina": ("alto", "O dispositivo passou a aparecer só riscado na página — é como o Planalto "
                                         "marca redação revogada ou substituída —, sem texto vigente no lugar. Confirme "
                                         "no Diário Oficial antes de qualquer mudança na base."),
    "texto_alterado_sem_norma_indicada": ("alto", "O texto mudou sem anotação de norma alteradora: pode ser "
                                                  "retificação, republicação ou correção editorial. Confira no DOU."),
    "indicio_inclusao": ("medio", "Dispositivo novo, com anotação de inclusão por outra norma."),
    "artigo_novo_na_pagina": ("medio", "Dispositivo novo na página, sem anotação de origem."),
    "artigo_ausente_na_pagina": ("alto", "O dispositivo não aparece mais na página. Isso NÃO significa revogação: "
                                         "pode ser erro da página ou da coleta. Confira antes de qualquer conclusão."),
    # A página não mudou: o monitor passou a ler como riscado o estilo "line-through" (leitura 2, 22/10/2026).
    "tachado_por_estilo_retirado": ("medio", "A página não mudou: o monitor passou a reconhecer o texto riscado por "
                                             "estilo (CSS) e deixou de contá-lo como vigente. Confira na página que o "
                                             "trecho retirado aparece mesmo riscado."),
    # Mudanças da página inteira (artigo "norma").
    "indicio_revogacao_total": ("alto", "A página passou a indicar a revogação da norma inteira (anotação no cabeçalho "
                                        "ou todos os artigos riscados). Confirme a norma revogadora e a data em que a "
                                        "revogação produz efeito no Diário Oficial; até a revisão, nada muda na base."),
    "retorno_a_versao_anterior": ("medio", "A página voltou a um texto já registrado antes (por exemplo, medida "
                                           "provisória que perdeu a validade, republicação ou correção da página). "
                                           "Confira qual texto vale e desde quando."),
}
PAGINA = "norma"  # chave das mudanças que valem para a página inteira

_PALAVRAS_ANOTACAO = (
    r"Redação dada|Incluíd|Acrescid|Revogad|Renumerad|Vide\b|Vigência|Regulamento|Produção de efeito|"
    r"Promulgação|Declarad|Suspens|inconstitucional|Mensagem de veto|Vetad"
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


# Categoria de uma anotação nova, da que mais pesa para a que menos pesa.
_CATEGORIAS = (
    ("revogacao", re.compile(r"Revogad", re.IGNORECASE)),
    ("controle", re.compile(r"inconstitucional|Suspens|\b(?:ADI|ADC|ADPF|ADO)\b|Resolução do Senado", re.IGNORECASE)),
    ("alteradora", re.compile(r"Redação dada|Incluíd|Acrescid|Renumerad", re.IGNORECASE)),
    ("vigencia", re.compile(r"Vigência|Produção de efeito|Promulgação|Vetad", re.IGNORECASE)),
    # "Vide" uma norma com força de lei (lei, lei complementar, decreto-lei, MP, emenda); "Vide" decreto é
    # regulamento, e regulamento não muda lei.
    ("remissao", re.compile(r"\bVide\b.*\b(?:Lei|Medida Provisória|Emenda Constitucional)\b", re.IGNORECASE)),
)
_TIPO_COM_TEXTO_IGUAL = {"revogacao": "indicio_revogacao", "controle": "anotacao_de_controle_constitucional",
                         "alteradora": "norma_nova_citada", "vigencia": "anotacao_de_vigencia",
                         "remissao": "remissao_a_norma_nova"}
_TIPO_COM_TEXTO_DIFERENTE = {"revogacao": "indicio_revogacao", "alteradora": "indicio_alteracao_legislativa",
                             "controle": "anotacao_de_controle_constitucional"}


def categoria(anotacao: str) -> str:
    for nome, regex in _CATEGORIAS:
        if regex.search(anotacao):
            return nome
    return "navegacao"


@dataclass
class Mudanca:
    artigo: str
    tipo: str
    risco: str
    explicacao: str
    trecho_anterior: str | None = None
    trecho_novo: str | None = None
    normas_citadas: list[str] = field(default_factory=list)
    anotacoes_novas: list[str] = field(default_factory=list)

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


def mudanca_da_pagina(tipo: str, **extra) -> Mudanca:
    return _mudanca(PAGINA, tipo, **extra)


def _pela_categoria(tabela: dict[str, str], categorias: set[str], padrao: str) -> str:
    for nome, _ in _CATEGORIAS:
        if nome in categorias and nome in tabela:
            return tabela[nome]
    return padrao


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
    vistas = _anotacoes(antigo)
    novas = [x for x in _anotacoes(novo) if x not in vistas]
    categorias = {categoria(x) for x in novas}
    extra = {"trecho_anterior": anterior, "trecho_novo": atual, "normas_citadas": normas_citadas(novas),
             "anotacoes_novas": novas}
    if _alfanumerico(_sem_anotacoes(antigo)) == _alfanumerico(_sem_anotacoes(novo)):
        # Texto igual: só a anotação de navegação é editorial; o resto tem efeito jurídico possível.
        return _mudanca(artigo, _pela_categoria(_TIPO_COM_TEXTO_IGUAL, categorias, "anotacao_editorial"), **extra)
    return _mudanca(artigo, _pela_categoria(_TIPO_COM_TEXTO_DIFERENTE, categorias, "texto_alterado_sem_norma_indicada"),
                    **extra)


def coleta_suspeita(antigos: dict[str, str], novos: dict[str, str], tachados: Iterable[str] = ()) -> str | None:
    """Motivo para desconfiar da coleta (página de erro, bloqueio, corte), ou None.

    Artigo que a página passou a mostrar riscado conta como presente: a página não foi cortada, ela marca
    uma revogação — que vai para revisão, não para o lixo. Só conta o riscado **novo**, de artigo que existia
    na versão aceita: os riscados de sempre (a CLT tem quase 200) não podem completar uma página cortada.
    """
    anteriores = [k for k in antigos if k not in ("preambulo", "fecho")]
    atuais = [k for k in novos if k not in ("preambulo", "fecho")]
    presentes = {base(k) for k in atuais}
    existiam = {base(k) for k in anteriores}
    todos_riscados = [k for k in dict.fromkeys(tachados) if k not in presentes]
    riscados = [k for k in todos_riscados if k in existiam]
    if not atuais and not todos_riscados:
        return "nenhum artigo na página coletada"
    if anteriores and len(atuais) + len(riscados) < MINIMO_ARTIGOS * len(anteriores):
        return (f"a página coletada tem {len(atuais)} artigos (e {len(riscados)} que passaram a aparecer riscados); "
                f"a versão aceita tinha {len(anteriores)}. Provável página de erro, bloqueio ou corte — nenhuma mudança "
                "foi inferida.")
    return None


def _revogacoes_finais(texto: str, ja_existiam: list[str]) -> tuple[str, list[str]]:
    """Separa as anotações de revogação NOVAS do fim do texto: (o resto, as anotações, na ordem)."""
    resto, finais = texto.rstrip(), list[str]()
    while True:
        achadas = list(_RE_ANOTACAO.finditer(resto))
        if not achadas or achadas[-1].end() != len(resto):
            break
        anotacao = " ".join(achadas[-1].group(0).split())
        if categoria(anotacao) != "revogacao" or anotacao in ja_existiam:
            break
        finais.insert(0, anotacao)
        resto = resto[:achadas[-1].start()].rstrip()
    return resto, finais


def _revogacoes_reatribuidas(antigos: dict[str, str], novos: dict[str, str],
                             riscados: set[str]) -> tuple[dict[str, str], dict[str, str]]:
    """Rótulo riscado: em `<strike>Art. 3º …</strike> (Revogado pela Lei …)`, o "(Revogado …)" fica no texto
    vigente sem o "Art. 3º" e cola no artigo anterior. Devolve (novos corrigidos, {artigo: anotação}).

    Só mexe quando há prova na página: os artigos que sumiram logo depois de k aparecem riscados. Então as
    anotações de revogação novas no fim de k saem de k (k é classificado pelo que sobra — uma alteração de
    redação em k continua sendo alteração, não revogação) e, se houver uma para cada artigo riscado, cada
    uma vai para o seu. Se k fica só com o rótulo, a revogação é do próprio k e nada muda.
    """
    corrigidos = dict(novos)
    revogados: dict[str, str] = {}
    # O preâmbulo entra como "artigo anterior": com o art. 1º riscado, a anotação dele cola no preâmbulo.
    ordem = [k for k in antigos if k != "fecho"]
    i = 0
    while i < len(ordem):
        k, j = ordem[i], i + 1
        while j < len(ordem) and ordem[j] not in novos and ordem[j] != "preambulo":
            j += 1
        ausentes = ordem[i + 1:j]
        if k in novos and ausentes and all(base(a) in riscados for a in ausentes):
            resto, finais = _revogacoes_finais(novos[k], _anotacoes(antigos[k]))
            if finais and len(_alfanumerico(_sem_anotacoes(resto)).split()) > 2:
                corrigidos[k] = resto
                if len(finais) == len(ausentes):
                    revogados.update(zip(ausentes, finais, strict=True))
        i = j
    return corrigidos, revogados


def comparar(antigos: dict[str, str], novos: dict[str, str], tachados: Iterable[str] = ()) -> list[Mudanca]:
    riscados = set(tachados)
    novos, revogados = _revogacoes_reatribuidas(antigos, novos, riscados)
    mudancas = []
    for artigo in list(dict.fromkeys([*antigos, *novos])):
        if artigo in revogados:
            m: Mudanca | None = _mudanca(artigo, "indicio_revogacao", trecho_anterior=antigos[artigo][:420],
                                         trecho_novo=revogados[artigo], normas_citadas=normas_citadas([revogados[artigo]]),
                                         anotacoes_novas=[revogados[artigo]])
        elif artigo not in novos and base(artigo) in riscados and artigo not in ("preambulo", "fecho"):
            m = _mudanca(artigo, "artigo_tachado_na_pagina", trecho_anterior=antigos[artigo][:420])
        else:
            m = classificar(artigo, antigos.get(artigo), novos.get(artigo))
        if m is not None:
            mudancas.append(m)
    return mudancas
