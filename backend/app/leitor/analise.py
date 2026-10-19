"""Leitura estruturada de um processo judicial, sem modelo de linguagem.

Tudo aqui é determinístico e rastreável: cada item é uma frase do próprio
documento, com página e folha, e a sua *natureza* diz de onde veio —
alegação de uma parte não é fato comprovado, pedido não é direito
reconhecido, decisão de primeira instância não é decisão definitiva.

A natureza sai do tipo de peça em que a frase está (petição → alegação;
sentença → decisão; certidão → fato registrado). Por isso o primeiro passo
é dividir o documento em peças pelos títulos ("SENTENÇA", "CERTIDÃO"…).
Quando o documento não tem títulos reconhecíveis, as frases ficam como
"trecho do documento", sem natureza presumida.

O resumo executivo e as orientações são montados por regras a partir desses
itens e marcados como interpretação; nunca afirmam o que não foi localizado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from . import cnj
from .extracao import DocumentoExtraido
from .glossario import termos_presentes
from .texto import Unidade, sem_acento, unidades
from .verificacao import citar

NATUREZAS = {
    "alegacao": "Alegação de uma parte — não é fato comprovado",
    "pedido": "Pedido de uma parte — não é direito reconhecido",
    "decisao_judicial": "Decisão judicial",
    "fundamento_judicial": "Fundamentação de decisão judicial",
    "ato_judicial": "Ato do juiz para o andamento do processo",
    "fato_registrado": "Fato registrado por servidor da Justiça (certidão, ata, autuação)",
    "documento_de_prova": "Documento de prova",
    "ato_processual": "Peça ou ato do processo",
    "trecho": "Trecho do documento, sem peça identificada",
    "interpretacao": "Interpretação assistida pelo DireitoAberto — confira as citações",
    "nao_localizado": "Informação não localizada nos documentos enviados",
    "orientacao_geral": "Orientação geral — não é aconselhamento sobre o seu caso",
}

# tipo → (rótulo, origem, padrão do título, sem acento e em maiúsculas)
_PECAS = [
    ("autuacao", "Autuação", "cartorio", r"^(TERMO DE )?AUTUACAO|^CAPA DO PROCESSO"),
    ("peticao_inicial", "Petição inicial", "parte", r"^PETICAO INICIAL"),
    ("contestacao", "Contestação", "parte", r"^CONTESTACAO"),
    ("replica", "Réplica", "parte", r"^REPLICA|^IMPUGNACAO A CONTESTACAO"),
    ("contrarrazoes", "Contrarrazões", "parte", r"^CONTRA-?RRAZOES"),
    ("recurso", "Recurso", "parte",
     r"^(RECURSO|RAZOES (DE|DO) RECURSO|APELACAO|AGRAVO|EMBARGOS DE DECLARACAO)"),
    ("manifestacao", "Manifestação de parte", "parte", r"^(MANIFESTACAO|PETICAO|ALEGACOES FINAIS|MEMORIAIS)"),
    ("sentenca", "Sentença", "juizo", r"^SENTENCA"),
    ("acordao", "Acórdão", "juizo", r"^ACORDAO"),
    ("decisao", "Decisão", "juizo", r"^DECISAO"),
    ("despacho", "Despacho", "juizo", r"^DESPACHO"),
    ("audiencia", "Termo de audiência", "cartorio", r"^(TERMO|ATA) DE AUDIENCIA"),
    ("certidao", "Certidão", "cartorio", r"^CERTIDAO"),
    ("mandado", "Mandado", "cartorio", r"^MANDADO"),
    ("laudo", "Laudo", "prova", r"^LAUDO"),
]
_PADROES_PECAS = [(tipo, rotulo, origem, re.compile(p)) for tipo, rotulo, origem, p in _PECAS]

_MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7,
    "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}
_RE_DATA_NUM = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_RE_DATA_EXT = re.compile(r"\b(\d{1,2})[º°o]? de ([a-z]+) de (\d{4})\b")
_RE_DATA_AOS = re.compile(r"\baos (\d{1,2}) dias do mes de ([a-z]+) de (\d{4})\b")
# "Vila Ficta, 20 de fevereiro de 2026." — a linha de local e data que fecha a peça.
_RE_ASSINATURA = re.compile(r"^[A-ZÀ-Ý][\w' À-ÿ-]{1,40}, \d{1,2}[º°]? de [a-zç]+ de \d{4}\.?$")

_RE_DISPOSITIVO = re.compile(
    r"\b(julgo|condeno|condenar|defiro|indefiro|homologo|extingo|concedo|nego provimento|"
    r"dou provimento|dou parcial provimento|rejeito|acolho|declaro|antecipo|revogo|mantenho)\b",
    re.IGNORECASE,
)
_RE_DETERMINACAO = re.compile(
    r"\b(deverá|deverão|fica(m)? obrigad|sob pena|determino|condeno|condenar|cumpra|designo|"
    r"cite-se|intime-se|intimem-se|expeça-se|providencie|apresentará|apresentar[áa]o)\b",
    re.IGNORECASE,
)
_RE_PRAZO_CONTEXTO = re.compile(r"\bprazo\b|\b(em|dentro de|até)\s+\d+\s*\(", re.IGNORECASE)
_RE_DURACAO = re.compile(
    r"\b(\d{1,4})\s*(?:\(([a-zà-ú ]{2,30})\))?\s*(dias?|horas?|meses|m[eê]s|anos?)(\s+úteis|\s+corridos)?",
    re.IGNORECASE,
)
_RE_RECURSO = re.compile(
    r"\b(recurso inominado|recurso ordinário|recurso especial|recurso extraordinário|apelação|"
    r"agravo de instrumento|agravo interno|embargos de declaração|recorrer)\b",
    re.IGNORECASE,
)
_RE_TRANSITO = re.compile(r"transit\w* em julgado", re.IGNORECASE)
_RE_REF_FOLHA = re.compile(r"\bfls?\.\s*(\d{1,6})\b", re.IGNORECASE)
_RE_PARTE_ROTULADA = re.compile(
    r"^(Autora?|Ré|Réu|Requerente|Requerid[oa]|Reclamante|Reclamad[oa]|Exequente|Executad[oa]|"
    r"Apelante|Apelad[oa]|Recorrente|Recorrid[oa]|Impetrante|Impetrad[oa]|Agravante|Agravad[oa]|"
    r"Embargante|Embargad[oa]|Interessad[oa]|Polo ativo|Polo passivo)\s*:\s*(.{3,160})$"
)
_RE_EM_FACE_DE = re.compile(r"\bem face de ([A-ZÀ-Ý][A-ZÀ-Ý0-9 .&'-]{3,120}?)(?:,|\s+pel[oa]s?\s|\s+com\s|$)")
_RE_ROTULO = re.compile(r"^(Classe|Assunto|Assuntos|Juízo|Órgão julgador|Vara|Comarca|Valor da causa)\s*:\s*(.+)$")
_RE_RESULTADO = [
    ("parcialmente procedente", re.compile(r"parcialmente procedente", re.IGNORECASE)),
    ("improcedente", re.compile(r"\bimprocedente", re.IGNORECASE)),
    ("procedente", re.compile(r"\bprocedente", re.IGNORECASE)),
    ("extinção do processo", re.compile(r"\bextingo\b", re.IGNORECASE)),
    ("homologação de acordo", re.compile(r"\bhomologo\b", re.IGNORECASE)),
]

RESSALVA_PRAZO = (
    "A contagem efetiva do prazo depende de quando a parte foi intimada, de a contagem ser em dias "
    "úteis ou corridos e de feriados e suspensões. Confirme com advogado ou com a Defensoria Pública."
)

_PAPEIS = {
    "autor": "autor(a)", "autora": "autor(a)", "ré": "ré(u)", "réu": "ré(u)",
    "requerente": "requerente", "requerido": "requerido(a)", "requerida": "requerido(a)",
}


@dataclass
class Peca:
    tipo: str
    rotulo: str
    origem: str  # parte · juizo · cartorio · prova · indefinida
    titulo: Unidade | None
    unidades: list[Unidade] = field(default_factory=list)
    secoes: dict[int, str] = field(default_factory=dict)  # índice da unidade → título da seção

    @property
    def pagina_inicial(self) -> int:
        return (self.titulo or self.unidades[0]).pagina

    @property
    def pagina_final(self) -> int:
        return self.unidades[-1].pagina if self.unidades else self.pagina_inicial


# ---------------------------------------------------------------- datas
def _data_iso(dia: str, mes: int, ano: str) -> str | None:
    try:
        return date(int(ano), mes, int(dia)).isoformat()
    except ValueError:
        return None


def datas_em(trecho: str) -> list[str]:
    """Datas citadas na frase, em ISO, na ordem em que aparecem."""
    achadas: list[tuple[int, str]] = []
    for m in _RE_DATA_NUM.finditer(trecho):
        if iso := _data_iso(m.group(1), int(m.group(2)), m.group(3)):
            achadas.append((m.start(), iso))
    comparavel = sem_acento(trecho.lower())
    for regex in (_RE_DATA_EXT, _RE_DATA_AOS):
        for m in regex.finditer(comparavel):
            mes = _MESES.get(m.group(2))
            if mes and (iso := _data_iso(m.group(1), mes, m.group(3))):
                achadas.append((m.start(), iso))
    return [iso for _, iso in sorted(achadas)]


def data_br(iso: str) -> str:
    ano, mes, dia = iso.split("-")
    return f"{dia}/{mes}/{ano}"


# ---------------------------------------------------------------- segmentação
def _tipo_do_titulo(titulo: str) -> tuple[str, str, str] | None:
    chave = sem_acento(titulo).upper().strip()
    for tipo, rotulo, origem, padrao in _PADROES_PECAS:
        if padrao.search(chave):
            return tipo, rotulo, origem
    return None


def segmentar(lista: list[Unidade]) -> list[Peca]:
    pecas: list[Peca] = []
    atual = Peca("sem_titulo", "Trecho sem peça identificada", "indefinida", None)
    secao = ""
    for unidade in lista:
        if unidade.titulo:
            tipo = _tipo_do_titulo(unidade.trecho)
            abertura = sem_acento(unidade.trecho).upper().startswith("EXCELENTISSIM")
            if abertura and not tipo and (atual.origem != "parte" or len(atual.unidades) > 3):
                # Petição sem título próprio: começa no endereçamento ao juiz.
                ja_tem_inicial = any(p.tipo == "peticao_inicial" for p in pecas + [atual])
                tipo = ("manifestacao", "Manifestação de parte", "parte") if ja_tem_inicial else (
                    "peticao_inicial", "Petição inicial", "parte")
            if tipo:
                if atual.unidades or atual.titulo:
                    pecas.append(atual)
                atual = Peca(*tipo, titulo=unidade)
                secao = ""
                continue
            if not abertura:  # o endereçamento ao juiz não é seção
                secao = unidade.trecho
        atual.secoes[len(atual.unidades)] = secao
        atual.unidades.append(unidade)
    if atual.unidades or atual.titulo:
        pecas.append(atual)
    return pecas


def _assinatura(unidade: Unidade) -> bool:
    return bool(_RE_ASSINATURA.match(unidade.trecho))


def data_da_peca(peca: Peca) -> str | None:
    """Data da peça: a linha "Cidade, dd de mês de aaaa"; em ato do juízo ou do
    cartório, na falta dela, a primeira data. Em peça de parte, sem a linha de
    assinatura não há como saber — a primeira data costuma ser a dos fatos."""
    for unidade in reversed(peca.unidades):
        if _assinatura(unidade) and (datas := datas_em(unidade.trecho)):
            return datas[0]
    if peca.origem in ("juizo", "cartorio"):
        for unidade in peca.unidades:
            if datas := datas_em(unidade.trecho):
                return datas[0]
    return None


# ---------------------------------------------------------------- natureza
def _em_secao_de_pedidos(peca: Peca, indice: int) -> bool:
    secao = sem_acento(peca.secoes.get(indice, "")).upper()
    return "PEDIDO" in secao or "REQUERIMENTO" in secao


def _eh_pedido(peca: Peca, indice: int, unidade: Unidade) -> bool:
    if peca.origem != "parte" or _assinatura(unidade):
        return False
    if unidade.trecho.endswith(":"):
        return False  # "Diante do exposto, requer:" só introduz a lista
    inicio = sem_acento(unidade.trecho[:40]).lower()
    if re.match(r"(diante do exposto,?\s*)?(requer|pede|postula)\b", inicio):
        return True
    return _em_secao_de_pedidos(peca, indice) and bool(re.match(r"^[a-z]\)|^[ivx]+\s*[-–—]", inicio))


def natureza(peca: Peca, indice: int, unidade: Unidade) -> str:
    if peca.origem == "parte":
        return "pedido" if _eh_pedido(peca, indice, unidade) else "alegacao"
    if peca.origem == "juizo":
        if _RE_DISPOSITIVO.search(unidade.trecho):
            return "decisao_judicial"
        if _RE_DETERMINACAO.search(unidade.trecho):
            return "ato_judicial"
        return "fundamento_judicial"
    if peca.origem == "cartorio":
        return "fato_registrado"
    if peca.origem == "prova":
        return "documento_de_prova"
    return "trecho"


# ---------------------------------------------------------------- análise
class _Montador:
    def __init__(self, doc: DocumentoExtraido):
        self.doc = doc
        self.descartadas = 0  # citações que não conferiram (deve ser sempre 0)

    def item(self, unidade: Unidade, nat: str, peca: Peca | None, **extra) -> dict | None:
        citacao = citar(self.doc, unidade.pagina, unidade.trecho)
        if not citacao.verificada:  # defesa: o leitor nunca apresenta citação que não confere
            self.descartadas += 1
            return None
        return {
            "texto": unidade.trecho,
            "natureza": nat,
            "peca": peca.rotulo if peca else None,
            "citacoes": [citacao.como_dict()],
            **extra,
        }


def _resumo_trecho(texto: str, limite: int = 220) -> str:
    return texto if len(texto) <= limite else texto[: limite - 1].rsplit(" ", 1)[0] + "…"


def analisar(doc: DocumentoExtraido) -> dict:
    lista = unidades(doc)
    pecas = segmentar(lista)
    m = _Montador(doc)
    por_unidade: list[tuple[Peca, int, Unidade]] = [
        (peca, i, u) for peca in pecas for i, u in enumerate(peca.unidades)
    ]

    # --- identificação do processo
    numeros: dict[str, dict] = {}
    rotulos: dict[str, dict] = {}
    for _peca, _, u in por_unidade:
        for numero in cnj.encontrar(u.trecho):
            if numero not in numeros:
                info = cnj.interpretar(numero)
                numeros[numero] = {
                    "numero": numero,
                    "digito_verificador_valido": bool(info and info.valido),
                    "segmento": info.segmento if info else None,
                    "tribunal": info.tribunal if info else None,
                    "citacoes": [citar(doc, u.pagina, u.trecho).como_dict()],
                }
        if mr := _RE_ROTULO.match(u.trecho):
            chave = sem_acento(mr.group(1)).lower().replace(" ", "_")
            rotulos.setdefault(chave, {
                "rotulo": mr.group(1), "valor": mr.group(2).strip(),
                "citacoes": [citar(doc, u.pagina, u.trecho).como_dict()],
            })

    # --- partes
    partes: list[dict] = []
    vistos: set[str] = set()

    def nova_parte(papel: str, nome: str, u: Unidade, peca: Peca, como: str) -> None:
        nome = nome.strip().rstrip(",;")
        chave = sem_acento(nome).lower().strip(" .")
        if chave in vistos or len(chave) < 3:
            return
        vistos.add(chave)
        if item := m.item(u, natureza(peca, 0, u) if peca.origem != "cartorio" else "fato_registrado",
                          peca, papel=papel, nome=nome, identificada_por=como):
            partes.append(item)

    for peca, _, u in por_unidade:
        if mp := _RE_PARTE_ROTULADA.match(u.trecho):
            papel = _PAPEIS.get(mp.group(1).lower(), mp.group(1).lower())
            nova_parte(papel, mp.group(2), u, peca, "rótulo no documento")
    for peca, _, u in por_unidade:
        if peca.tipo == "peticao_inicial" and (mf := _RE_EM_FACE_DE.search(u.trecho)):
            nova_parte("ré(u)", mf.group(1), u, peca, "\"em face de\" na petição inicial")

    # --- peças
    pecas_saida = []
    for peca in pecas:
        if peca.tipo == "sem_titulo":
            continue
        quando = data_da_peca(peca)
        citacao = citar(doc, peca.titulo.pagina, peca.titulo.trecho) if peca.titulo else None
        pecas_saida.append({
            "tipo": peca.tipo,
            "rotulo": peca.rotulo,
            "origem": peca.origem,
            "pagina_inicial": peca.pagina_inicial,
            "pagina_final": peca.pagina_final,
            "data": quando,
            "citacoes": [citacao.como_dict()] if citacao else [],
        })

    # --- itens por categoria
    alegacoes, pedidos, decisoes, determinacoes, prazos, recursos, transito = [], [], [], [], [], [], []
    linha_do_tempo: list[dict] = []
    for peca, i, u in por_unidade:
        if u.titulo:
            continue
        nat = natureza(peca, i, u)
        texto_sem_acento = sem_acento(u.trecho).upper()
        if nat == "pedido":
            if it := m.item(u, nat, peca):
                pedidos.append(it)
        elif nat == "alegacao" and len(u.trecho) >= 40 and not _assinatura(u) \
                and not texto_sem_acento.startswith("EXCELENTISSIM"):
            if it := m.item(u, nat, peca, secao=peca.secoes.get(i) or None):
                alegacoes.append(it)
        if nat == "decisao_judicial":
            resultado = None
            if peca.tipo in ("sentenca", "acordao") and re.search(r"\bjulgo\b", u.trecho, re.IGNORECASE):
                resultado = next((r for r, rx in _RE_RESULTADO if rx.search(u.trecho)), None)
            if it := m.item(u, nat, peca, resultado=resultado, instancia=_instancia(peca),
                            peca_pagina=peca.pagina_inicial, peca_data=data_da_peca(peca)):
                decisoes.append(it)
        if peca.origem in ("juizo", "cartorio") and _RE_DETERMINACAO.search(u.trecho):
            if it := m.item(u, nat, peca):
                determinacoes.append(it)
        if _RE_PRAZO_CONTEXTO.search(u.trecho) and (md := _RE_DURACAO.search(u.trecho)):
            if it := m.item(u, nat, peca, duracao=md.group(0), tipo_de_prazo=_tipo_de_prazo(nat, peca),
                            ressalva=RESSALVA_PRAZO):
                prazos.append(it)
        if peca.tipo in ("recurso", "contrarrazoes") or _RE_RECURSO.search(u.trecho):
            if it := m.item(u, nat, peca):
                recursos.append(it)
        if peca.origem == "cartorio" and _RE_TRANSITO.search(u.trecho):
            if it := m.item(u, "fato_registrado", peca):
                transito.append(it)
        # Linha do tempo: datas de peças e datas de acontecimentos (narrados por
        # uma parte, certificados, designados pelo juiz). Data citada dentro de
        # condenação ou fundamentação ("correção desde 10/01") não é evento.
        if _assinatura(u) or nat not in ("decisao_judicial", "fundamento_judicial"):
            for iso in datas_em(u.trecho):
                evento = peca.rotulo if _assinatura(u) else _resumo_trecho(u.trecho)
                nat_evento = "ato_processual" if _assinatura(u) else nat
                if it := m.item(u, nat_evento, peca, data=iso, evento=evento):
                    linha_do_tempo.append(it)
    linha_do_tempo = _sem_repeticao(sorted(linha_do_tempo, key=lambda e: (e["data"], e["citacoes"][0]["pagina"])))

    # --- folhas citadas e não enviadas
    folhas_presentes = {p.folha for p in doc.paginas if p.folha}
    faltantes: dict[str, dict] = {}
    if folhas_presentes:
        for _peca, _, u in por_unidade:
            for ref in _RE_REF_FOLHA.findall(u.trecho):
                if ref not in folhas_presentes and ref not in faltantes:
                    faltantes[ref] = {"folha": ref, "citacoes": [citar(doc, u.pagina, u.trecho).como_dict()]}

    tem_decisao_final = any(p.tipo in ("sentenca", "acordao") for p in pecas)
    analise: dict[str, Any] = {
        "documento": {
            "nome": doc.nome,
            "hash_sha256": doc.hash_sha256,
            "total_paginas": doc.total_paginas,
            "paginas_lidas": doc.paginas_por_estado("lida"),
            "paginas_sem_texto": doc.paginas_por_estado("sem_texto"),
            "paginas_com_falha": doc.paginas_por_estado("falha"),
            "paginas_nao_processadas": doc.paginas_por_estado("nao_processada"),
            "leitura_completa": doc.leitura_completa,
            "folhas": {str(p.numero): p.folha for p in doc.paginas if p.folha},
        },
        "avisos": list(doc.avisos),
        "numeros_processo": list(numeros.values()),
        "identificacao": rotulos,
        "partes": partes,
        "pecas": pecas_saida,
        "linha_do_tempo": linha_do_tempo,
        "alegacoes": alegacoes,
        "pedidos": pedidos,
        "decisoes": decisoes,
        "obrigacoes_e_determinacoes": determinacoes,
        "prazos": prazos,
        "recursos": recursos,
        "transito_em_julgado": transito,
        "folhas_citadas_nao_enviadas": list(faltantes.values()),
        "glossario": termos_presentes([(p.numero, p.texto) for p in doc.paginas if p.tem_texto]),
        "naturezas": NATUREZAS,
    }
    analise["pendencias"] = _pendencias(analise, tem_decisao_final)
    analise["resumo"] = _resumo(analise, doc)
    analise["proximos_passos"] = _proximos_passos(analise, tem_decisao_final)
    analise["perguntas_para_advogado"] = _perguntas(analise, tem_decisao_final)
    if len(numeros) > 1:
        analise["avisos"].append(
            "O documento cita mais de um número de processo. Pode haver processos relacionados ou "
            "documentos de processos diferentes no mesmo arquivo."
        )
    if any(not n["digito_verificador_valido"] for n in numeros.values()):
        analise["avisos"].append(
            "Um número de processo encontrado não passa na conferência do dígito verificador "
            "(Resolução CNJ nº 65/2008): pode haver erro de digitação ou de leitura."
        )
    if not pecas_saida:
        analise["avisos"].append(
            "Não reconheci títulos de peças processuais (petição, sentença, certidão…). Os trechos "
            "aparecem sem natureza presumida: não dá para saber se são alegação, fato ou decisão."
        )
    analise["controle"] = {"citacoes_descartadas": m.descartadas}
    return analise


def _instancia(peca: Peca) -> str:
    return "tribunal (colegiado)" if peca.tipo == "acordao" else "primeira instância"


# Prazos que podem estar correndo contra alguém (os demais são citações).
PRAZOS_EM_CURSO = ("prazo fixado em ato do juiz", "prazo informado em certidão ou ata")


def _tipo_de_prazo(nat: str, peca: Peca) -> str:
    if nat == "pedido":
        return "prazo pedido por uma parte — não está correndo"
    if nat == "fundamento_judicial":
        return "prazo citado na fundamentação — não é ordem de cumprimento"
    if peca.origem == "juizo":
        return "prazo fixado em ato do juiz"
    if peca.origem == "cartorio":
        return "prazo informado em certidão ou ata"
    if peca.origem == "parte":
        return "prazo mencionado por uma parte"
    return "prazo mencionado no documento"


def _sem_repeticao(eventos: list[dict]) -> list[dict]:
    vistos, saida = set(), []
    for e in eventos:
        chave = (e["data"], e["citacoes"][0]["pagina"], e["texto"])
        if chave not in vistos:
            vistos.add(chave)
            saida.append(e)
    return saida


def _pendencia(texto: str, citacoes: list[dict] | None = None) -> dict:
    return {"texto": texto, "natureza": "nao_localizado", "citacoes": citacoes or []}


def _pendencias(a: dict, tem_decisao_final: bool) -> list[dict]:
    saida = []
    if not a["numeros_processo"]:
        saida.append(_pendencia("Não localizei o número do processo."))
    if not a["partes"]:
        saida.append(_pendencia("Não identifiquei as partes do processo."))
    if not tem_decisao_final:
        saida.append(_pendencia(
            "Não localizei sentença nem acórdão: o processo pode não ter sido julgado ainda, ou a "
            "decisão não está entre os documentos enviados."
        ))
    elif not a["transito_em_julgado"]:
        saida.append(_pendencia(
            "Não localizei certidão de trânsito em julgado. Pelo que foi enviado, não dá para afirmar "
            "que a decisão é definitiva: ela pode ainda estar sujeita a recurso."
        ))
    for falta in a["folhas_citadas_nao_enviadas"]:
        saida.append(_pendencia(
            f"O processo menciona as fls. {falta['folha']}, que não estão no arquivo enviado.",
            falta["citacoes"],
        ))
    for aviso in a["avisos"]:
        saida.append(_pendencia(aviso))
    return saida


def _cit(itens: list[dict]) -> list[dict]:
    return [c for it in itens for c in it["citacoes"]]


def _resumo(a: dict, doc: DocumentoExtraido) -> list[dict]:
    """Resumo executivo por regras. Cada frase cita de onde saiu; o que falta é dito."""
    frases: list[dict] = []

    def frase(texto: str, citacoes: list[dict], nat: str = "interpretacao") -> None:
        frases.append({"texto": texto, "natureza": nat, "citacoes": citacoes})

    classe = a["identificacao"].get("classe")
    numero = next(iter(a["numeros_processo"]), None)
    if classe or numero:
        partes_txt = []
        if classe:
            partes_txt.append(f"um processo da classe \"{classe['valor']}\"")
        if numero:
            ok = "dígito verificador confere" if numero["digito_verificador_valido"] else \
                "dígito verificador NÃO confere"
            onde = numero["tribunal"] or numero["segmento"]
            partes_txt.append(f"número {numero['numero']} ({ok}{'; ' + onde if onde else ''})")
        frase("O documento é " + ", ".join(partes_txt) + ".",
              (classe["citacoes"] if classe else []) + (numero["citacoes"] if numero else []))
    if a["partes"]:
        nomes = "; ".join(f"{p['nome']} ({p['papel']})" for p in a["partes"][:4])
        frase(f"Partes identificadas: {nomes}.", _cit(a["partes"][:4]))
    if a["pedidos"]:
        primeiros = a["pedidos"][:3]
        frase("Pedidos feitos pelas partes (pedido não é direito reconhecido): "
              + " ".join(f"«{_resumo_trecho(p['texto'], 160)}»" for p in primeiros), _cit(primeiros))
    if a["pecas"]:
        lista = ", ".join(
            f"{p['rotulo'].lower()} (p. {p['pagina_inicial']}{', ' + data_br(p['data']) if p['data'] else ''})"
            for p in a["pecas"]
        )
        frase(f"Peças identificadas, na ordem do arquivo: {lista}.", [])
    finais = [p for p in a["pecas"] if p["tipo"] in ("sentenca", "acordao")]
    dispositivo = [d for d in a["decisoes"] if finais and d["peca_pagina"] == finais[-1]["pagina_inicial"]]
    principal = next((d for d in dispositivo if d.get("resultado")), None)
    if principal:
        quando = f", {data_br(principal['peca_data'])}" if principal["peca_data"] else ""
        frase(f"Resultado da {principal['peca'].lower()} ({principal['instancia']}{quando}): "
              f"{principal['resultado'].upper()} — «{_resumo_trecho(principal['texto'], 200)}»",
              principal["citacoes"])
        demais = [d for d in dispositivo if d is not principal]
        if demais:
            frase("Itens do dispositivo: " + " ".join(f"«{_resumo_trecho(d['texto'], 160)}»" for d in demais),
                  _cit(demais), "decisao_judicial")
    elif a["decisoes"]:
        ultima = a["decisoes"][-1]
        frase(f"Decisão mais recente localizada ({ultima['peca'].lower()}): "
              f"«{_resumo_trecho(ultima['texto'], 200)}»", ultima["citacoes"])
    if a["transito_em_julgado"]:
        frase("Há certidão de trânsito em julgado: a decisão foi certificada como definitiva.",
              _cit(a["transito_em_julgado"][:1]), "fato_registrado")
    for pendencia in a["pendencias"]:
        frases.append(pendencia)
    return frases


def _proximos_passos(a: dict, tem_decisao_final: bool) -> list[dict]:
    passos = []

    def passo(texto: str) -> None:
        passos.append({"texto": texto, "natureza": "orientacao_geral", "citacoes": []})

    if tem_decisao_final and not a["transito_em_julgado"]:
        passo("Se você é parte, confirme logo com advogado ou Defensoria se ainda cabe recurso e até "
              "quando: prazos de recurso costumam ser curtos e contam a partir da intimação.")
    if any(re.search(r"\b(condeno|condenar)\b", d["texto"], re.IGNORECASE) for d in a["decisoes"]):
        passo("Quando a condenação ao pagamento se torna definitiva e não é cumprida voluntariamente, "
              "a cobrança costuma seguir na fase de cumprimento de sentença.")
    if a["prazos"]:
        passo("Os prazos listados foram encontrados no texto; nenhum foi calculado. Peça a quem acompanha "
              "o processo a data exata em que cada um termina.")
    if not tem_decisao_final:
        passo("Acompanhe o andamento pela consulta processual do tribunal, com o número do processo.")
    passo("Leve as perguntas abaixo à Defensoria Pública (gratuita) ou a um advogado.")
    return passos


def _perguntas(a: dict, tem_decisao_final: bool) -> list[str]:
    perguntas = []
    for prazo in [p for p in a["prazos"] if p["tipo_de_prazo"] in PRAZOS_EM_CURSO][:4]:
        c = prazo["citacoes"][0]
        perguntas.append(f"O prazo de {prazo['duracao']} mencionado na página {c['pagina']} se aplica a mim? "
                         "Quando ele começou e quando termina?")
    if tem_decisao_final and not a["transito_em_julgado"]:
        perguntas.append("A decisão já transitou em julgado ou ainda cabe recurso? Vale a pena recorrer?")
    if any(re.search(r"\bindefiro\b", d["texto"], re.IGNORECASE) for d in a["decisoes"]):
        perguntas.append("Por que um dos pedidos foi indeferido, e essa decisão ainda pode ser revista?")
    for falta in a["folhas_citadas_nao_enviadas"][:3]:
        perguntas.append(f"O que está nas fls. {falta['folha']}, citadas no processo e ausentes do arquivo?")
    if a["documento"]["paginas_sem_texto"]:
        paginas = ", ".join(map(str, a["documento"]["paginas_sem_texto"]))
        perguntas.append(f"O que dizem as páginas {paginas}, que não puderam ser lidas automaticamente?")
    perguntas.append("Quais são os próximos passos do processo e o que eu preciso fazer agora?")
    return perguntas
