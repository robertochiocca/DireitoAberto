"""A pergunta e o tempo: que data importa, o que se quer saber, e qual versão do dispositivo vale nela.

Cinco intenções, decididas por regras (sem modelo de linguagem):

- **atual** — "qual é a regra?" (padrão): vale a versão em vigor na data da consulta;
- **historica** — "qual era o prazo em 2015?", "em 10/04/2006": vale a versão em vigor naquela data;
- **mudanca** — "o que mudou?", "antes e depois da reforma": as versões e as alterações registradas;
- **revogacao** — "isso foi revogado?", "ainda vale?": a situação de vigência e a evidência dela;
- **fundamento** — "qual artigo diz isso?": os dispositivos e o texto oficial que sustentam a resposta.

Versões de um mesmo dispositivo (a entrada vigente e a redação anterior que aponta para ela em
`versao_de`, ou entradas com a mesma norma e os mesmos dispositivos) formam um grupo; dentro do grupo,
a versão aplicável à data de referência vem primeiro. Entre grupos, a ordem é a da busca: uma regra
revogada sem sucessora (ex.: art. 262 do CTB) continua onde a busca a pôs — às vezes "foi revogada"
é a resposta.

O que a base não sabe vira aviso, nunca palpite: a data de início de uma redação, quando só se conhece
o ano da lei que a deu, é tratada como incerta naquele ano.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .vigencia import data_br

MESES = ["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]


def _sem_acento(texto: str) -> str:
    from .leitor.texto import sem_acento

    return sem_acento(texto)


_DATA = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_MES_ANO = re.compile(r"\b(?:em|no mes de|desde|ate)?\s*(" + "|".join(MESES) + r")\s+de\s+(\d{4})\b")
_ANO = re.compile(r"\b(?:em|no ano de|de|ate|desde|antes de|depois de|na epoca de|no inicio de|no final de)\s+"
                  r"((?:19|20)\d{2})\b")
# "Decreto do SAC de 2022", "Lei 14.905 de 2024": o ano faz parte do nome da norma, não é data da pergunta.
_NOME_DE_NORMA = re.compile(r"\b(?:lei|decreto|emenda|resolucao|medida provisoria|codigo|sumula|portaria|"
                            r"instrucao normativa|n[o°º]\.?)(?:\s+[\w./-]+){0,3}\s*$")
_AGORA = re.compile(r"\b(hoje|atualmente|agora|atual|atuais|ainda|vigente|em vigor|nos dias de hoje)\b")
_PASSADO_VAGO = re.compile(r"\b(antigamente|na epoca|naquela epoca|antes da reforma|depois da reforma|"
                           r"lei antiga|regra antiga|redacao antiga|redacao original|texto original|antes da mudanca)\b")
_MUDANCA = re.compile(r"\b(o que mudou|mudou o que|mudanca|mudancas|diferenca|diferencas|antes e depois|"
                      r"comparar|comparacao|nova redacao|alterou|alteracao|alteracoes)\b")
_REVOGACAO = re.compile(r"\b(revogad[oa]s?|revogou|revogacao|ainda vale|ainda valem|continua valendo|"
                        r"continua em vigor|esta em vigor|estao em vigor|perdeu a validade|nao vale mais|caiu|"
                        r"derrubad[oa]|ainda (?:existe|existem|e|sao|fica|ficam|exige|exigem|e obrigatori[oa]))\b")
_FUNDAMENTO = re.compile(r"\b(qual artigo|que artigo|quais artigos|qual dispositivo|que dispositivo|base legal|"
                         r"fundamento|fundamentacao|onde esta escrito|qual lei diz|que lei diz|qual e a lei)\b")
_VERBO_PASSADO = re.compile(r"\b(era|eram|valia|valiam|vigorava|vigoravam|dizia|diziam|previa|previam|"
                            r"exigia|exigiam|podia|podiam|tinha|tinham)\b")


@dataclass
class ConsultaTemporal:
    intencao: str = "atual"
    data_referencia: date | None = None   # None: a data da consulta
    so_ano: bool = False                  # a pergunta deu só o ano, não o dia
    expressao: str | None = None          # o trecho da pergunta que fixou a data
    pede_esclarecimento: bool = False
    motivo: str | None = None

    def como_dict(self, hoje: date) -> dict:
        return {
            "intencao": self.intencao,
            "data_referencia": (self.data_referencia or hoje).isoformat(),
            "data_explicita": self.data_referencia is not None,
            "so_ano": self.so_ano,
            "expressao": self.expressao,
            "pede_esclarecimento": self.pede_esclarecimento,
            "motivo": self.motivo,
        }


def interpretar(pergunta: str, hoje: date) -> ConsultaTemporal:
    """Intenção e data de referência da pergunta. Datas no futuro e datas vagas não viram palpite."""
    texto = _sem_acento(pergunta.lower())
    consulta = ConsultaTemporal()

    if m := _DATA.search(texto):
        dia, mes, ano = (int(g) for g in m.groups())
        try:
            consulta.data_referencia, consulta.expressao = date(ano, mes, dia), m.group(0)
        except ValueError:
            consulta.pede_esclarecimento, consulta.motivo = True, f"a data {m.group(0)} não existe"
    elif m := _MES_ANO.search(texto):
        consulta.data_referencia = date(int(m.group(2)), MESES.index(m.group(1)) + 1, 1)
        consulta.expressao = m.group(0).strip()
    elif m := next((m for m in _ANO.finditer(texto) if not _NOME_DE_NORMA.search(texto[:m.start()])), None):
        consulta.data_referencia, consulta.so_ano = date(int(m.group(1)), 1, 1), True
        consulta.expressao = m.group(0).strip()

    if _MUDANCA.search(texto):
        consulta.intencao = "mudanca"
    elif _REVOGACAO.search(texto):
        consulta.intencao = "revogacao"
    elif consulta.data_referencia and consulta.data_referencia.year < hoje.year and not _AGORA.search(texto):
        consulta.intencao = "historica"
    elif _FUNDAMENTO.search(texto):
        consulta.intencao = "fundamento"

    if consulta.data_referencia and consulta.data_referencia > hoje:
        # Pergunta sobre o futuro: a base só sabe de normas já publicadas (em vacatio).
        consulta.intencao = "atual" if consulta.intencao == "historica" else consulta.intencao
    if consulta.intencao in ("atual", "fundamento") and not consulta.data_referencia and (
        (m := _PASSADO_VAGO.search(texto)) or _VERBO_PASSADO.search(texto) and _PASSADO_VAGO.search(texto)
    ):
        consulta.intencao = "historica"
        consulta.pede_esclarecimento = True
        consulta.expressao = m.group(0) if m else None
        consulta.motivo = ("a pergunta fala de uma época passada sem dizer a data; a resposta depende de quando "
                           "os fatos aconteceram")
    return consulta


def consulta_sem_tempo(pergunta: str, consulta: ConsultaTemporal) -> str:
    """A pergunta sem a expressão de data: "2018" não é palavra-chave de assunto (casaria com rótulos
    como "(c/ Lei nº 13.728/2018)" e traria lei de outro tema)."""
    texto = _DATA.sub(" ", pergunta)
    texto = re.sub(r"\b(?:em|no ano de|de|até|ate|desde|antes de|depois de)?\s*(?:19|20)\d{2}\b", " ", texto,
                   flags=re.IGNORECASE)
    return " ".join(texto.split()) or pergunta


# ------------------------------------------------------------------ janela de validade de uma versão

_ANO_EM_ATO = re.compile(r"(?:/|,\s*de\s+|\()((?:19|20)\d{2})\b")
# Ato normativo que muda a redação (lei, emenda, medida provisória, decreto) × decisão de tribunal ou
# resolução, que muda a aplicação sem mexer no texto.
_ATO_NORMATIVO = re.compile(r"^\s*(?:Lei|LC|Lei Complementar|EC|Emenda|Medida Provis|MP|Decreto)", re.IGNORECASE)


def _anos(atos: list[str]) -> list[int]:
    return sorted({int(ano) for a in atos for ano in _ANO_EM_ATO.findall(a)})


def anos_de_alteracao(resultado) -> list[int]:
    """Anos das mudanças de REDAÇÃO: as anotações da página oficial ("Redação dada pela Lei nº …, de 2017")
    quando a base tem o trecho oficial; senão, os atos normativos registrados na vigência."""
    da_pagina = [r["ato"] for t in getattr(resultado, "trechos_oficiais", []) or []
                 for r in t.get("relacoes", []) if r["tipo"] in ("redacao_dada_por", "incluido_por")]
    if da_pagina:
        return _anos(da_pagina)
    return _anos([a for a in resultado.vigencia.get("alterada_por") or [] if _ATO_NORMATIVO.match(a)])


def anos_de_entendimento(resultado) -> list[int]:
    """Anos de decisões de tribunal e resoluções registradas, que mudam a aplicação sem mudar o texto."""
    return _anos([a for a in resultado.vigencia.get("alterada_por") or [] if not _ATO_NORMATIVO.match(a)])


@dataclass
class Aplicabilidade:
    codigo: int            # 0 vale na data; 1 incerto; 2 não vale na data
    explicacao: str


def aplicabilidade(resultado, data: date, hoje: date) -> Aplicabilidade:
    """A versão (entrada do corpus) vale na data? Responde só com o que a base registra."""
    v = resultado.vigencia
    status = v.get("status", "nao_verificada")
    inicio = v.get("vigente_desde") or (v.get("entra_em_vigor_em") if status == "em_vacatio" else None)
    fim = v.get("vigente_ate")

    if status == "nao_verificada":
        return Aplicabilidade(1, "situação de vigência não verificada")
    if inicio and data < date.fromisoformat(inicio):
        return Aplicabilidade(2, f"esta redação só vale a partir de {data_br(inicio)}")
    if fim and data > date.fromisoformat(fim):
        return Aplicabilidade(2, f"esta redação valeu até {data_br(fim)}")
    if status in ("revogada", "inconstitucional", "redacao_anterior") or (fim and status == "vigente"):
        if fim:
            return Aplicabilidade(0, f"redação em vigor até {data_br(fim)}")
        # Redação antiga: valeu até a PRIMEIRA mudança registrada depois dela — de texto ou de aplicação
        # (a decisão do STF de 2011 mudou a união estável sem mudar a letra do art. 1.723).
        anos = sorted(set(anos_de_alteracao(resultado)) | set(anos_de_entendimento(resultado)))
        if anos and data.year < anos[0]:
            return Aplicabilidade(0, f"redação anterior à alteração de {anos[0]}")
        if anos and data.year == anos[0]:
            return Aplicabilidade(1, f"a alteração é de {anos[0]}: sem a data exata, não dá para saber qual redação valia")
        return Aplicabilidade(2 if data >= hoje or anos else 1, "redação que não vale mais")
    # Vigente (ou em vacatio já iniciada): vale hoje. No passado, a REDAÇÃO decide (a última alteração de
    # texto); decisão de tribunal ou resolução posterior à data só rebaixa "vale" para "incerto" — ela muda a
    # aplicação de uma parte do dispositivo, e a base não sabe se é a parte que a pergunta quer.
    anos = anos_de_alteracao(resultado)
    entendimentos = [a for a in anos_de_entendimento(resultado) if a > data.year]
    if data >= hoje or not anos:
        codigo = 0 if status == "vigente" or (inicio and data >= date.fromisoformat(inicio)) else 1
        if codigo == 0 and entendimentos and data < hoje:
            return Aplicabilidade(1, f"a redação é a mesma, mas a aplicação mudou em {entendimentos[0]} (decisão de "
                                     "tribunal ou resolução)")
        return Aplicabilidade(codigo, "redação em vigor" if status == "vigente" else "redação publicada")
    if data.year > anos[-1]:
        if entendimentos:
            return Aplicabilidade(1, f"redação em vigor desde a alteração de {anos[-1]}, mas a aplicação mudou em "
                                     f"{entendimentos[0]} (decisão de tribunal ou resolução)")
        return Aplicabilidade(0, f"redação em vigor desde a alteração de {anos[-1]}")
    if data.year == anos[-1]:
        return Aplicabilidade(1, f"o texto atual tem alteração de {anos[-1]}: sem a data exata, não dá para saber "
                                 "qual redação valia")
    posteriores = ", ".join(str(a) for a in anos if a > data.year)
    return Aplicabilidade(2, f"o texto atual tem alteração posterior a {data.year} ({posteriores}): a redação "
                             "daquela época pode ser outra")


# ------------------------------------------------------------------ ordenação por versão

def _chave_do_dispositivo(resultado, apontados: set[str]) -> str:
    if versao_de := getattr(resultado, "versao_de", None):
        return versao_de
    if resultado.id in apontados:  # a entrada vigente para a qual uma redação anterior aponta
        return resultado.id
    dispositivos = getattr(resultado, "dispositivos", None)
    norma = getattr(resultado, "norma", None)
    if norma and dispositivos:
        refs = sorted("|".join(f"{k}={v}" for k, v in sorted(d.items())) for d in dispositivos)
        return f"{norma}::{';'.join(refs)}"
    return resultado.id


_ORDEM_ATUAL = {"vigente": 0, "nao_verificada": 1, "em_vacatio": 2, "redacao_anterior": 3, "revogada": 3,
                "inconstitucional": 3}


@dataclass
class Analise:
    consulta: ConsultaTemporal
    resultados: list = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def ordenar(resultados: list, consulta: ConsultaTemporal, hoje: date) -> Analise:
    """Põe, em cada grupo de versões do mesmo dispositivo, a aplicável à data de referência primeiro."""
    data = consulta.data_referencia or hoje
    grupos: dict[str, list] = {}
    ordem: list[str] = []
    apontados = {v for r in resultados if (v := getattr(r, "versao_de", None))}
    for r in resultados:
        chave = _chave_do_dispositivo(r, apontados)
        if chave not in grupos:
            grupos[chave], ordem = [], [*ordem, chave]
        grupos[chave].append(r)

    avisos: list[str] = []
    saida: list = []
    for chave in ordem:
        grupo = grupos[chave]
        if consulta.intencao == "historica" or (consulta.data_referencia and consulta.data_referencia != hoje):
            grupo = sorted(grupo, key=lambda r: (aplicabilidade(r, data, hoje).codigo, -r.score))
        else:
            grupo = sorted(grupo, key=lambda r: (_ORDEM_ATUAL.get(r.vigencia.get("status", "nao_verificada"), 1),
                                                 -r.score))
        saida.extend(grupo)

    if consulta.pede_esclarecimento and consulta.motivo:
        avisos.append(f"Para responder com segurança, preciso saber a data: {consulta.motivo}.")
    if consulta.intencao == "historica" and consulta.data_referencia and saida:
        principal = saida[0]
        ap = aplicabilidade(principal, data, hoje)
        quando = data_br(data.isoformat()) if not consulta.so_ano else str(data.year)
        if ap.codigo == 2:
            avisos.append(f"Pergunta sobre {quando}: {principal.artigo} — {ap.explicacao}. A base não tem a "
                          "redação daquela época; confira o texto compilado (com as redações anteriores) na fonte "
                          "oficial.")
        else:
            avisos.append(f"Pergunta sobre {quando}: {principal.artigo} — {ap.explicacao}.")
        if entendimentos := [a for a in anos_de_entendimento(principal) if a > data.year]:
            avisos.append(f"Depois de {data.year} houve decisão de tribunal ou resolução registrada "
                          f"({', '.join(map(str, entendimentos))}) que mudou a aplicação do dispositivo.")
    return Analise(consulta, saida, avisos)


# ------------------------------------------------------------------ o que a resposta diz sobre o tempo

def _evidencia_de_revogacao(resultado) -> str | None:
    for trecho in getattr(resultado, "trechos_oficiais", []) or []:
        for anotacao in trecho.get("anotacoes", []):
            if re.match(r"\(\s*Revogad[oa]", anotacao, re.IGNORECASE):
                return f"anotação da página oficial no {trecho['dispositivo']}: {anotacao}"
    return None


def situacao(resultado, hoje: date) -> str:
    """Resposta a "foi revogado? ainda vale?" com a evidência que a base tem — e só ela."""
    v = resultado.vigencia
    conferida = f", conferida em {data_br(v['conferida_em'])}" if v.get("conferida_em") else ""
    status = v.get("status", "nao_verificada")
    alteracoes = ", ".join(v.get("alterada_por") or [])
    if status == "revogada":
        evidencia = _evidencia_de_revogacao(resultado)
        return (f"{resultado.artigo}: REVOGADO segundo a base{conferida}"
                + (f" ({alteracoes})" if alteracoes else "") + (f"; evidência: {evidencia}" if evidencia else "") + ".")
    if status == "inconstitucional":
        return (f"{resultado.artigo}: declarado INCONSTITUCIONAL{f' ({alteracoes})' if alteracoes else ''}"
                f" segundo a base{conferida} — não deve ser aplicado.")
    if status == "em_vacatio":
        return (f"{resultado.artigo}: publicado, mas ainda sem efeito; passa a valer em "
                f"{data_br(v.get('entra_em_vigor_em'))} segundo a base{conferida}.")
    if status == "vigente":
        return (f"{resultado.artigo}: em vigor segundo a base{conferida}; a base não registra revogação. Isso não "
                "é certidão de vigência: confirme na fonte oficial.")
    return (f"{resultado.artigo}: não foi possível verificar a situação de vigência na base — não trate como "
            "certamente em vigor nem como revogado.")


def alteracoes(resultado) -> str:
    """Resposta a "o que mudou?": as alterações registradas, com a fonte de cada informação."""
    v = resultado.vigencia
    registradas = list(v.get("alterada_por") or [])
    da_pagina = sorted({f"{r['ato']}" for t in getattr(resultado, "trechos_oficiais", []) or []
                        for r in t.get("relacoes", []) if r["tipo"] in ("redacao_dada_por", "incluido_por")})
    partes = []
    if registradas:
        partes.append(f"alterações registradas na base: {', '.join(registradas)}")
    if da_pagina:
        partes.append(f"anotadas na página oficial: {', '.join(da_pagina)}")
    if v.get("nota"):
        partes.append(f"nota: {v['nota'].rstrip('.')}")
    if not partes:
        return (f"{resultado.artigo}: a base não registra alteração. Isso não prova que o texto nunca mudou — "
                "confira o texto compilado na fonte oficial.")
    return f"{resultado.artigo}: " + "; ".join(partes) + ". A base guarda só a redação atual deste dispositivo."


def linhas_da_resposta(analise: Analise, hoje: date) -> list[str]:
    """O que a resposta precisa dizer antes dos artigos, conforme a intenção da pergunta."""
    linhas = list(analise.avisos)
    principais = analise.resultados[:2]
    if analise.consulta.intencao == "revogacao":
        linhas += [situacao(r, hoje) for r in principais]
    elif analise.consulta.intencao == "mudanca":
        versoes = [r for r in analise.resultados if getattr(r, "versao_de", None)]
        linhas += [alteracoes(r) for r in principais]
        if versoes:
            linhas.append("A base tem mais de uma redação deste dispositivo: compare-as abaixo, cada uma com a sua "
                          "situação de vigência.")
    elif analise.consulta.intencao == "fundamento" and principais:
        linhas.append("Dispositivos que sustentam a resposta, com o texto oficial transcrito quando a base o tem: "
                      + "; ".join(f"{r.lei}, {r.artigo}" for r in principais) + ".")
    return linhas
