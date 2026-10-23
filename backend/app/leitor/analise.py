"""Leitura estruturada de um processo judicial, sem modelo de linguagem.

Tudo aqui é determinístico e rastreável: cada item é uma frase do próprio
documento, com página e folha, e a sua *natureza* diz de onde veio —
alegação de uma parte não é fato comprovado, pedido não é direito
reconhecido, decisão de primeira instância não é decisão definitiva.

A natureza sai do tipo de peça em que a frase está (petição → alegação;
sentença → decisão; certidão → fato registrado). Por isso o primeiro passo
é dividir o documento em peças pelos títulos ("SENTENÇA", "CERTIDÃO"…). Título
não é peça em qualquer lugar: subtítulo de petição ("DECISÃO AGRAVADA",
"MANDADO DE SEGURANÇA", "CERTIDÃO DE NASCIMENTO") e cabeçalho de acórdão
("APELAÇÃO CÍVEL Nº…") não abrem peça, e título do juízo ou do cartório no
meio de uma petição também não — senão bastaria a uma parte escrever
"CERTIDÃO" para forjar um trânsito em julgado. Quando o documento não tem
títulos reconhecíveis, as frases ficam como "trecho do documento", sem
natureza presumida.

Peça do juízo ou do cartório que começa logo depois de uma petição sem a linha
de local e data é "não confirmada": pode ser a parte continuando a petição na
página seguinte. Ela não entra no resultado nem no trânsito em julgado, e a
dúvida segue até a próxima peça de parte (avisada, nunca engolida em silêncio).

A decisão que vale é escolhida pela data — só a da linha de local e data, a do
julgamento ou a do termo; a primeira data do corpo nunca vence a instância — e
pela instância, não pela posição no arquivo. Não entram no resultado da causa:
decisão sobre embargos de declaração rejeitados, decisão sobre agravo (contra
decisão do meio do processo) e decisão da fase de cumprimento ou de execução.
Embargos ACOLHIDOS depois da decisão mudam o resultado (quando o trecho diz
como) ou o deixam incerto. Quando as datas não permitem ordenar decisões com
resultados diferentes, ou duas sentenças divergem sem decisão de tribunal entre
elas, o leitor diz que não dá para determinar — não escolhe. Acórdão cujo
resultado não foi entendido é dito como tal — o leitor não cai de volta na
sentença. Trânsito em julgado só conta se vier de certidão própria (no alto da
página, não depois de petição aberta), sem outro número de processo, que
afirme o trânsito (sem negá-lo nem tratá-lo como futuro) e seja posterior a
uma decisão final com data confiável.

Recursos: tudo o que percorre o documento é linear e tem teto (listas, partes,
peças, números, divergências, faixas de folhas sem expandir); as fases que
montam listas param no orçamento de tempo, com aviso.

O resumo executivo e as orientações são montados por regras a partir desses
itens e marcados como interpretação; nunca afirmam o que não foi localizado.
Prazos são mostrados, nunca calculados.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from . import cnj
from .extracao import RE_CARIMBO_FOLHA, DocumentoExtraido, dobrar, faixas, faixas_de_intervalos, numero_do_ambiente
from .glossario import termos_presentes
from .texto import (
    LINHA_ROTULADA,
    RE_ASSINATURA,
    RE_ENDERECAMENTO,
    Unidade,
    chave_de_titulo,
    eh_linha_de_juizo,
    sem_acento,
    unidades,
)
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
    "inconsistencia": "Possível inconsistência entre trechos do documento — confira as citações",
    "nao_localizado": "Informação não localizada nos documentos enviados",
    "orientacao_geral": "Orientação geral — não é aconselhamento sobre o seu caso",
}

# Tempo máximo para montar as listas de itens; o que passar disso fica de fora, com aviso.
ORCAMENTO_ANALISE_S = numero_do_ambiente("DIREITO_ABERTO_LEITOR_ORCAMENTO_ANALISE_S", 30)
# Itens por lista (alegações, prazos…). Um processo de 300 páginas pode ter 10 mil frases
# com data; a lista inteira não cabe na tela nem no banco. A contagem total vai em `contagens`.
LIMITE_ITENS_POR_CATEGORIA = 200
LIMITE_PENDENCIAS_NO_RESUMO = 5
LIMITE_INCONSISTENCIAS = 30
# Tetos das demais listas da saída (a contagem total vai em `contagens`). Sem eles, um .txt de
# 100 KB com 4 mil linhas "Autora: …" virava 4 mil partes, cada uma citada e comparada com as outras.
LIMITE_PARTES = 50
LIMITE_PECAS = 500
LIMITE_NUMEROS = 20
LIMITE_TRANSITO = 20
LIMITE_DIVERGENCIAS = 3          # pares de decisões finais divergentes descritos, por tipo de decisão
LIMITE_NOMES_POR_PAPEL = 5       # nomes diferentes guardados por papel (só 4 aparecem)
LIMITE_VALORES_POR_ROTULO = 5
LIMITE_TITULOS_RECUSADOS = 5
LIMITE_DECISOES_NAO_USADAS = 10
# Trecho de um item: frase acima disto (página sem pontuação, por exemplo) é citada pelo começo.
LIMITE_TRECHO = 1500

# tipo → (rótulo, origem, padrão do título, sem acento e em maiúsculas). A ordem decide.
_PECAS = [
    ("autuacao", "Autuação", "cartorio", r"^(TERMO DE )?AUTUACAO|^CAPA DO PROCESSO"),
    ("peticao_inicial", "Petição inicial", "parte", r"^PETICAO INICIAL"),
    ("contestacao", "Contestação", "parte", r"^CONTESTACAO"),
    ("replica", "Réplica", "parte", r"^REPLICA|^IMPUGNACAO A CONTESTACAO"),
    ("contrarrazoes", "Contrarrazões", "parte", r"^CONTRA-?RRAZOES"),
    ("recurso", "Recurso", "parte",
     r"^(RECURSO|RAZOES (DE|DO) RECURSO|RAZOES DE APELACAO|APELACAO|AGRAVO|EMBARGOS DE DECLARACAO)"),
    ("manifestacao", "Manifestação de parte", "parte",
     r"^(MANIFESTACAO|PETICAO|ALEGACOES FINAIS|MEMORIAIS|CUMPRIMENTO DE SENTENCA|EXCECAO DE PRE-?\s?EXECUTIVIDADE"
     r"|IMPUGNACAO AO CUMPRIMENTO|EMBARGOS A EXECUCAO|EMBARGOS DO DEVEDOR|REQUERIMENTO)"),
    ("sentenca", "Sentença", "juizo", r"^SENTENCA"),
    ("acordao", "Acórdão", "juizo", r"^(ACORDAO|EMENTA|VOTO|RELATORIO E VOTO)\b"),
    ("decisao_monocratica", "Decisão monocrática (relator)", "juizo", r"^DECISAO MONOCRATICA"),
    ("decisao", "Decisão", "juizo", r"^DECISAO"),
    ("despacho", "Despacho", "juizo", r"^DESPACHO"),
    ("audiencia", "Termo de audiência", "cartorio", r"^(TERMO|ATA) DE AUDIENCIA"),
    ("documento_juntado", "Documento juntado", "prova",
     r"^CERTIDAO DE (NASCIMENTO|CASAMENTO|OBITO|INTEIRO TEOR|MATRICULA|REGISTRO|DIVORCIO|UNIAO)"),
    ("certidao", "Certidão", "cartorio", r"^CERTIDAO"),
    ("mandado", "Mandado", "cartorio", r"^MANDADO"),
    ("laudo", "Laudo", "prova", r"^LAUDO"),
]
_PADROES_PECAS = [(tipo, rotulo, origem, re.compile(p)) for tipo, rotulo, origem, p in _PECAS]
# Títulos que parecem peça e não são: subtítulo que nomeia outra decisão, nome da ação,
# cabeçalho numerado de recurso no tribunal ("APELAÇÃO CÍVEL Nº 0000000-…").
_NAO_E_PECA = re.compile(
    r"^(DECISAO|SENTENCA|ACORDAO|DESPACHO)S? (AGRAVAD|RECORRID|EMBARGAD|IMPUGNAD|ATACAD|APELAD|ANTERIOR"
    r"|PROFERID|DE ORIGEM|DO JUIZO|DE PRIMEIR|DE 1)"
    r"|^MANDADO DE (SEGURANCA|INJUNCAO)"
    r"|^(APELACAO|AGRAVO|RECURSO|EMBARGOS|PROCESSO|ACAO|REMESSA|REEXAME)\b.*(\bN[O°]?\.?\s*\d|\d{7}-\d{2}\.\d{4})"
)
# Partes do acórdão: não abrem outro acórdão enquanto o atual não terminou.
_PARTE_DO_ACORDAO = re.compile(r"^(ACORDAO|EMENTA|VOTO|RELATORIO)\b")
# Voto e relatório vêm DEPOIS da data no acórdão do TJSP ("ACÓRDÃO … São Paulo, 20 de setembro de
# 2026." e, na página seguinte, "VOTO Nº …"): continuam o mesmo acórdão mesmo depois da data.
_PARTE_DO_VOTO = re.compile(r"^(VOTO|RELATORIO E VOTO|DECLARACAO DE VOTO|RELATORIO)\b")
# Cabeçalho de recurso no tribunal ("APELAÇÃO CÍVEL", com o número na linha seguinte): sem corpo
# antes do título do acórdão, é o cabeçalho dele, não a peça da parte.
_TITULO_DE_RECURSO_NO_TRIBUNAL = re.compile(r"^(APELACAO|AGRAVO|RECURSO|EMBARGOS|REMESSA|REEXAME)\b")
# Seção de relatório ("RELATÓRIO", "I – RELATÓRIO"): narra o processo, não decide. Termina no
# "É o relatório. Decido." — sem isso, sentença sem outros subtítulos perderia o dispositivo.
_SECAO_RELATORIO = re.compile(r"^(?:[IVX]+|\d+)?\s*[-–—.)]?\s*(?:DO |O )?RELATORIO\b(?! E VOTO)")
_FIM_DO_RELATORIO = re.compile(
    r"\b(e o (breve |sucinto |necessario |essencial )?(relatorio|relato)|eis o (breve )?relatorio|relatei"
    r"|e o que (importa|cumpria|cabia|interessa|havia a) relatar|decido|passo a (decidir|fundamentar|analisar|julgar))\b"
    r"|^((sucinta|brevemente|sucintamente) )?relatad[oa]s?\b"
)
# "…pelo MM. Juiz foi proferida a seguinte sentença:" — no Juizado, a sentença sai no termo.
_RE_SENTENCA_EM_AUDIENCIA = re.compile(r"\b(proferi|prolat|passou a proferir)\w*\b.{0,60}\bsentenca\s*:$")
# Linha de identificação ("Processo nº…", "Autos nº…") não é corpo de peça.
_RE_LINHA_DE_PROCESSO = re.compile(r"^(Processo|Autos|Proc\.)\s*(n[º°o.]|:)|^(N[º°o]\.?|N[uú]mero)\s*:?\s*\d",
                                   re.IGNORECASE)
_LINHA_ROTULADA = LINHA_ROTULADA
# Ementa antes do título do acórdão ("Ementa: Apelação cível. Consumidor. …"): é do acórdão, não corpo de petição.
_RE_EMENTA = re.compile(r"^EMENTA\b")

_MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7,
    "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}
_RE_DATA_NUM = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_RE_DATA_EXT = re.compile(r"\b(\d{1,2})[º°o]? de ([a-z]+) de (\d{4})\b")
_RE_DATA_AOS = re.compile(r"\baos (\d{1,2}) dias do mes de ([a-z]+) de (\d{4})\b")

# Aplicados ao texto "dobrado" (sem acento, minúsculo, mesmo comprimento do original).
_RE_DISPOSITIVO = re.compile(
    r"\b(julgo|condeno|condenar|defiro|indefiro|homologo|extingo|concedo|rejeito|acolho|declaro|antecipo|revogo"
    r"|mantenho|acordam|(dar|negar|deram|negaram|nego|dou|da-se|nega-se|dando|negando)(-lhe)?( parcial)? provimento"
    r"|(des|im)?provid[oa]s?|nao conhe(co|cer|ceram|cido)|voto pelo (nao )?(provimento|desprovimento|improvimento))\b"
)
_RE_DETERMINACAO = re.compile(
    r"\b(devera|deverao|fica(m)? obrigad|sob pena|determino|condeno|condenar|cumpra|designo|"
    r"cite-se|intime-se|intimem-se|expeca-se|providencie|apresentara|apresentarao|manifeste-se|manifestem-se"
    r"|junte-se|comprove|comprovem|especifiquem|recolha|emende|regularize|digam?|pague|venham|voltem|aguarde-se"
    r"|arquive-se|arquivem-se|certifique-se|cumpra-se|publique-se)\b"
)
_RE_RECURSO = re.compile(
    r"\b(recurso inominado|recurso ordinario|recurso especial|recurso extraordinario|apelacao|"
    r"agravo de instrumento|agravo interno|embargos de declaracao|recorrer)\b"
)
_RE_TRANSITO = re.compile(r"transit\w* em julgado")
# "ainda não transitou", "não houve o trânsito", "sem o trânsito": a certidão NEGA o trânsito.
# A negação tem de reger o "transit…" diretamente: "não havendo recurso, transitou em julgado" e
# "decorrido o prazo sem recurso, transitou" certificam o trânsito (antes eram lidos como negação).
_RE_TRANSITO_NEGADO = re.compile(
    r"\b(nao|nem)\s+(houve|ha|ocorreu|consta|se\s+operou|se\s+verificou)?\s*(o\s+|ainda\s+)?transit"
    r"|\bsem\s+(o\s+)?transit"
)
# "após o trânsito, arquivem-se", "aguarde-se o trânsito", "quando transitar": fala do futuro, não certifica.
_RE_TRANSITO_FUTURO = re.compile(
    r"\b(antes|depois|apos|ate|aguard\w*(-se)?|quando)\s+(d[oa]\s+|o\s+|a\s+)?transit"
    r"|\bse\s+transit|\btransitar(a|em|ao)?\b"
)
# Data do julgamento declarada numa linha própria ("Julgado em 20/09/2026", "Data do julgamento: …",
# "Sessão de julgamento de 20 de…"). Só no começo de uma frase curta: no meio do texto, "julgado em"
# costuma ser de precedente citado ("REsp 123, julgado em 10/03/2020").
_RE_DATA_DE_JULGAMENTO = re.compile(
    r"^\W*(julgad[oa] em|data d[oa] (julgamento|sessao)|sessao (virtual |de julgamento )?(de|do dia|realizada em))\b"
)
# Decisão da fase de cumprimento ou da execução: não diz quem tinha razão na causa.
_RE_FASE_DE_CUMPRIMENTO = re.compile(
    r"\b(extingo|julgo extint[oa]|declaro extint[oa]|extint[oa])\b.{0,40}?\b(cumprimento|execucao|fase executiva)"
    r"|\bart(igo)?\.?\s*924\b|impugnacao ao cumprimento|embargos (a|do) execu|embargos do devedor"
)
# Agravo (de instrumento, interno, regimental): recurso contra decisão do meio do processo.
_RE_AGRAVO = re.compile(r"\bagravo\b")
_RE_SOBRE_AGRAVO = re.compile(r"(trata-se|cuida-se|cuidam os autos)\s+de\s+(recurso de\s+)?agravo|^agravo\b")
# Embargos acolhidos só para esclarecer, sem mudar o resultado.
_RE_SEM_EFEITO_MODIFICATIVO = re.compile(
    r"\bsem (atribuir |conferir |dar )?(efeitos? )?(infringentes?|modificativos?)\b|\bsem efeito modificativo"
    r"|\bmantid[oa]s? (integralmente |no mais |no merito )?(a sentenca|o acordao|a decisao|o resultado)"
    r"|\bmantendo(-se)? (integralmente |no mais )?(a sentenca|o acordao|a decisao|o resultado)"
    r"|sem (alteracao|alterar|modificacao|modificar) (do |o )?(resultado|dispositivo|julgado)"
)
_RE_REF_FOLHA = re.compile(r"\bfls?\.\s*(\d{1,6})\b", re.IGNORECASE)
_RE_PARTE_ROTULADA = re.compile(
    r"^(Autora?|Ré|Réu|Requerente|Requerid[oa]|Reclamante|Reclamad[oa]|Exequente|Executad[oa]|"
    r"Apelante|Apelad[oa]|Recorrente|Recorrid[oa]|Impetrante|Impetrad[oa]|Agravante|Agravad[oa]|"
    r"Embargante|Embargad[oa]|Interessad[oa]|Polo ativo|Polo passivo)\s*:\s*(.{3,160})$"
)
_RE_EM_FACE_DE = re.compile(r"\bem face de ([A-ZÀ-Ý][A-ZÀ-Ý0-9 .&'-]{3,120}?)(?:,|\s+pel[oa]s?\s|\s+com\s|$)")
_RE_ROTULO = re.compile(r"^(Classe|Assunto|Assuntos|Juízo|Órgão julgador|Vara|Comarca|Valor da causa)\s*:\s*(.+)$")
# Rótulo que deveria ter um valor só no processo. Classe, juízo e órgão julgador mudam
# legitimamente no recurso (a capa do acórdão traz "Apelação Cível", a câmara…).
_ROTULOS_UNICOS = {"valor_da_causa"}
# Separador de campos numa mesma linha de cabeçalho ("Processo nº … - Autora: … - Ré: …").
_RE_SEPARADOR = re.compile(r"\s+[-–—|]\s+")
_RE_ASPAS = re.compile(r"\"[^\"]*(\"|$)|“[^”]*(”|$)|«[^»]*(»|$)")

# Prazos. O número é o que vem logo depois de "prazo", "em", "dentro de" ou "até" —
# não o primeiro número da frase ("às 14 horas, … no prazo de 15 dias").
_NUM_EXTENSO = (r"(?:um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez|onze|doze|treze|quatorze|catorze"
                r"|quinze|dezesseis|dezessete|dezoito|dezenove|vinte|trinta|quarenta|cinquenta|sessenta|noventa"
                r"|cento e vinte|cento e oitenta|cem)(?:\s+e\s+(?:um|uma|dois|duas|tres|quatro|cinco|seis|sete"
                r"|oito|nove))?")
# "15 (quinze) dias", "quinze (15) dias", "15 dias úteis".
_DURACAO = (rf"(?P<d>\b(?:\d{{1,4}}|{_NUM_EXTENSO})\s*(?:\((?:[a-z ]{{2,30}}|\d{{1,4}})\))?\s*"
            r"(?:dias?|horas?|meses|mes|anos?)(?:\s+uteis|\s+corridos)?\b)")
_RE_DURACAO = re.compile(_DURACAO)
_RE_DURACAO_COLADA = re.compile(r"\s{1,3}" + _DURACAO)  # logo depois de "em", "dentro de", "até"
# "Concedo 15 (quinze) dias de prazo para…": a duração vem antes da palavra "prazo".
_RE_DURACAO_DE_PRAZO = re.compile(_DURACAO + r"\s+de\s+prazo\b")
_RE_GATILHO_PRAZO = re.compile(r"\bprazo\b|\bdentro de\b|\bate\b|\bem\b")
_RE_PRAZO_LEGAL = re.compile(r"\bprazo legal\b")
_RE_PRAZO_DECORRIDO = re.compile(
    r"\b(decorreu|decorreram|escoou|transcorreu|transcorreram|esgotou|expirou|findou)\b.{0,60}\bprazo"
    r"|\bprazo\b.{0,60}\b(decorreu|escoou|transcorreu|esgotou|expirou|findou)\b"
)
_RE_DECURSO_CERTIFICADO = re.compile(r"\b(decurso|decorrido|transcorrido|escoado|esgotado|in albis)\b")

RESSALVA_PRAZO = (
    "A contagem efetiva do prazo depende de quando a parte foi intimada, de a contagem ser em dias "
    "úteis ou corridos e de feriados e suspensões. Confirme com advogado ou com a Defensoria Pública."
)

_PAPEIS = {
    "autor": "autor(a)", "autora": "autor(a)", "ré": "ré(u)", "réu": "ré(u)",
    "requerente": "requerente", "requerido": "requerido(a)", "requerida": "requerido(a)",
}
_ARTIGO = {"sentenca": "a", "decisao": "a", "decisao_monocratica": "a", "acordao": "o"}
_NIVEL = {"sentenca": 1, "decisao": 2, "decisao_monocratica": 2, "acordao": 3}
_FINAIS = ("sentenca", "acordao", "decisao_monocratica", "decisao")


@dataclass
class Peca:
    tipo: str
    rotulo: str
    origem: str  # parte · juizo · cartorio · prova · indefinida
    titulo: Unidade | None
    unidades: list[Unidade] = field(default_factory=list)
    secoes: dict[int, str] = field(default_factory=dict)  # índice da unidade → título da seção
    no_topo: bool = True       # começou no topo de uma página (ou no início do documento)
    fechada: bool = False      # já teve a linha "Cidade, dd de mês de aaaa"
    data_padrao: str | None = None  # sentença em audiência: a data é a do termo
    data_padrao_confiavel: bool = False
    corpo: bool = False        # já teve frase que não é título nem cabeçalho
    # Peça do juízo ou do cartório que começa logo depois de uma peça de parte que não terminou
    # (sem a linha de local e data): pode ser continuação da petição — inclusive texto escrito pela
    # parte para parecer certidão ou sentença. Não entra no resultado nem no trânsito em julgado.
    duvidosa: bool = False
    motivo_duvida: str = ""
    # Unidades depois de um título desconhecido no alto da página, depois de peça do juízo ou do
    # cartório já fechada: não são dessa peça (natureza "trecho", sem presumir).
    soltas: set[int] = field(default_factory=set)

    @property
    def pagina_inicial(self) -> int:
        return (self.titulo or self.unidades[0]).pagina

    @property
    def pagina_final(self) -> int:
        return self.unidades[-1].pagina if self.unidades else self.pagina_inicial


# ---------------------------------------------------------------- texto
_dobrar = dobrar  # sem acento e minúsculo, com o MESMO comprimento: as posições valem para o original


def _sem_citacao(texto: str) -> str:
    """Tira trechos entre aspas: o dispositivo de outra decisão citado no relatório não é decisão."""
    return _RE_ASPAS.sub(" ", texto)


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
    comparavel = dobrar(trecho)
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
def _tipo_do_titulo(chave: str) -> tuple[str, str, str] | None:
    if _NAO_E_PECA.search(chave):
        return None
    for tipo, rotulo, origem, padrao in _PADROES_PECAS:
        if padrao.search(chave):
            return tipo, rotulo, origem
    return None


def _eh_cabecalho(unidade: Unidade) -> bool:
    """Título, campo rotulado, "Processo nº…" ou identificação do juízo ("Juízo de Direito da 1ª
    Vara…", "Comarca de…"): o que vem antes do corpo da peça na página."""
    trecho = unidade.trecho
    if unidade.titulo or _LINHA_ROTULADA.match(trecho) or _RE_LINHA_DE_PROCESSO.match(trecho):
        return True
    return bool(cnj.RE_CNJ.fullmatch(trecho.strip(" .:;"))) or eh_linha_de_juizo(trecho)


@dataclass
class _Abertura:
    tipo: tuple[str, str, str]
    absorver: bool = False  # a peça atual é só o cabeçalho ("APELAÇÃO CÍVEL" + número) da nova


@dataclass
class _Recusa:
    """Título do juízo ou do cartório que não abriu peça: dito ao usuário, não engolido em silêncio."""
    unidade: Unidade
    dentro_de: str


# Começo de decisão: depois do título repetido no alto da página, indica decisão NOVA, não cabeçalho corrido.
_RE_COMECO_DE_DECISAO = re.compile(r"^(vistos\b|trata-se\b|cuida-se\b|relatorio\b|dispensad[oa] o relatorio)")


def _abre_peca(unidade: Unidade, atual: Peca, ja_tem_inicial: bool, no_topo: bool,
               seguinte: Unidade | None = None) -> _Abertura | None:
    """O título abre uma peça nova? Devolve a abertura ou None (é seção da peça atual)."""
    chave = chave_de_titulo(unidade.trecho)
    tipo = _tipo_do_titulo(chave)
    if tipo is None:
        if not RE_ENDERECAMENTO.match(chave):
            return None
        # Endereçamento ao juízo: petição sem título próprio. Logo depois do título
        # "PETIÇÃO INICIAL" ele é só a primeira linha da mesma petição.
        if atual.origem == "parte" and len(atual.unidades) <= 3 and not atual.fechada:
            return None
        ao_tribunal = re.match(r"^(?:\S+\s+)?(EGREGI|COLEND)", chave)
        return _Abertura(("manifestacao", "Manifestação de parte", "parte") if ja_tem_inicial or ao_tribunal else (
            "peticao_inicial", "Petição inicial", "parte"))
    novo, _, origem = tipo
    if atual.tipo == "sem_titulo":
        return _Abertura(tipo)
    if novo == "acordao" and atual.tipo == "acordao" and (not atual.fechada or _PARTE_DO_VOTO.match(chave)):
        return None  # EMENTA, ACÓRDÃO, VOTO: partes do mesmo acórdão (o voto pode vir depois da data)
    if (novo == atual.tipo and no_topo and not atual.fechada and atual.titulo is not None
            and chave == chave_de_titulo(atual.titulo.trecho)
            and not (seguinte is not None and _RE_COMECO_DE_DECISAO.match(_dobrar(seguinte.trecho)))):
        return None  # o mesmo título no topo de cada página: cabeçalho corrido da peça (se não começa outra)
    if origem == "parte":
        # Petição nova. Se o título estiver errado, o pior caso é ler texto do juízo como alegação.
        return _Abertura(tipo)
    if atual.origem == "parte":
        if (origem == "juizo" and not atual.corpo and atual.titulo is not None
                and atual.titulo.pagina == unidade.pagina
                and _TITULO_DE_RECURSO_NO_TRIBUNAL.match(chave_de_titulo(atual.titulo.trecho))):
            # "APELAÇÃO CÍVEL" / número / partes / "Ementa: …" e logo o "ACÓRDÃO": era o cabeçalho dele.
            return _Abertura(tipo, absorver=True)
        # Título do juízo ou do cartório dentro de uma petição só abre peça no topo de uma página:
        # no meio dela é citação, subtítulo ou tentativa de forjar certidão ou sentença.
        if not no_topo:
            return None
        if novo == "acordao" and not atual.fechada and _PARTE_DO_ACORDAO.match(chave):
            return None  # "EMENTA" de jurisprudência citada pela parte
        return _Abertura(tipo)
    if novo == "acordao" and not chave.startswith("ACORDAO") and not atual.fechada:
        return None  # "EMENTA"/"VOTO" dentro de sentença ou decisão que não terminou: precedente citado
    return _Abertura(tipo) if no_topo or atual.fechada else None


def _recusa_relevante(unidade: Unidade, atual: Peca) -> _Recusa | None:
    """Título de decisão ou certidão que ficou dentro de outra peça (não as partes do acórdão nem o
    cabeçalho corrido): vale avisar, porque pode ser uma decisão de verdade colada na peça anterior."""
    chave = chave_de_titulo(unidade.trecho)
    tipo = _tipo_do_titulo(chave)
    if tipo is None or tipo[2] not in ("juizo", "cartorio") or atual.tipo == "sem_titulo":
        return None
    if tipo[0] == "acordao" and not chave.startswith("ACORDAO"):
        return None  # EMENTA/VOTO/RELATÓRIO citados ou partes do acórdão
    if tipo[0] == atual.tipo and atual.titulo is not None and chave == chave_de_titulo(atual.titulo.trecho):
        return None  # cabeçalho corrido
    return _Recusa(unidade, atual.rotulo)


def segmentar(lista: list[Unidade], recusas: list[_Recusa] | None = None) -> list[Peca]:
    pecas: list[Peca] = []
    atual = Peca("sem_titulo", "Trecho sem peça identificada", "indefinida", None)
    secao = ""
    pagina, corpo_na_pagina = 0, False
    ja_tem_inicial = False
    solta = False  # depois de título desconhecido no alto da página, após peça do juízo/cartório fechada
    for posicao, unidade in enumerate(lista):
        if unidade.pagina != pagina:
            pagina, corpo_na_pagina = unidade.pagina, False
        if unidade.titulo:
            seguinte = lista[posicao + 1] if posicao + 1 < len(lista) else None
            abertura = _abre_peca(unidade, atual, ja_tem_inicial, not corpo_na_pagina, seguinte)
            if abertura:
                tipo = abertura.tipo
                if abertura.absorver:
                    # A "peça de parte" era só cabeçalho: título e linhas vão para a peça nova.
                    cabecalho = ([atual.titulo] if atual.titulo else []) + atual.unidades
                    no_topo, anterior = atual.no_topo, (pecas[-1] if pecas else None)
                    duvidosa, motivo = atual.duvidosa, atual.motivo_duvida
                else:
                    no_topo = not corpo_na_pagina or atual.tipo == "sem_titulo"
                    # O cabeçalho que veio antes do título, na mesma página, é da peça nova.
                    cabecalho = [u for u in atual.unidades if u.pagina == unidade.pagina] if (
                        not corpo_na_pagina and (atual.titulo is None or atual.titulo.pagina != unidade.pagina)) else []
                    if cabecalho:
                        del atual.unidades[-len(cabecalho):]
                        atual.soltas = {i for i in atual.soltas if i < len(atual.unidades)}
                    if atual.unidades or atual.titulo:
                        pecas.append(atual)
                    anterior = atual if atual.tipo != "sem_titulo" else None
                    duvidosa, motivo = False, ""
                if tipo[2] in ("juizo", "cartorio") and anterior is not None and not duvidosa:
                    if anterior.origem == "parte" and not anterior.fechada:
                        duvidosa = True
                        motivo = (f"começa logo depois de uma peça que não terminou ({anterior.rotulo.lower()} da p. "
                                  f"{anterior.pagina_inicial}, sem a linha de local e data): pode ser continuação de "
                                  "uma peça de parte")
                    elif anterior.duvidosa:
                        # A dúvida segue até a próxima peça de parte: fechar a certidão forjada com uma linha de
                        # data não pode bastar para a "sentença" da página seguinte passar por peça do juízo.
                        duvidosa = True
                        motivo = (f"vem logo depois de outra peça não confirmada ({anterior.rotulo.lower()} da p. "
                                  f"{anterior.pagina_inicial}): pode ser continuação de uma peça de parte")
                atual = Peca(*tipo, titulo=unidade, no_topo=no_topo, duvidosa=duvidosa, motivo_duvida=motivo)
                ja_tem_inicial = ja_tem_inicial or tipo[0] == "peticao_inicial"
                for u in cabecalho:
                    atual.secoes[len(atual.unidades)] = ""
                    atual.unidades.append(u)
                secao = ""
                solta = False
                continue
            chave = chave_de_titulo(unidade.trecho)
            if recusas is not None and (recusa := _recusa_relevante(unidade, atual)) is not None:
                recusas.append(recusa)
            if (not corpo_na_pagina and atual.fechada and atual.origem in ("juizo", "cartorio")
                    and _tipo_do_titulo(chave) is None and not RE_ENDERECAMENTO.match(chave)
                    and not (atual.tipo == "acordao" and _PARTE_DO_VOTO.match(chave))):
                solta = True  # "CUMPRIMENTO DE…", "REQUERIMENTO…" no alto da página seguinte à certidão
            elif atual.tipo == "acordao" and _PARTE_DO_VOTO.match(chave):
                solta = False
            if not RE_ENDERECAMENTO.match(chave):  # o endereçamento não é seção
                secao = unidade.trecho
        elif not _eh_cabecalho(unidade):
            corpo_na_pagina = True
            if not _RE_EMENTA.match(chave_de_titulo(secao)):
                atual.corpo = True  # a ementa antes do título do acórdão não é corpo da "peça" de cabeçalho
        if (not unidade.titulo and not atual.corpo and atual.origem == "parte" and atual.titulo is not None
                and _TITULO_DE_RECURSO_NO_TRIBUNAL.match(chave_de_titulo(atual.titulo.trecho))
                and _RE_EMENTA.match(chave_de_titulo(unidade.trecho[:8])) and _LINHA_ROTULADA.match(unidade.trecho)):
            secao = "EMENTA"  # "Ementa: …" em caixa mista sob "APELAÇÃO CÍVEL": a ementa do acórdão que vem
        if RE_ASSINATURA.match(unidade.trecho) and not solta:
            atual.fechada = True
        if solta:
            atual.soltas.add(len(atual.unidades))
        atual.secoes[len(atual.unidades)] = secao
        atual.unidades.append(unidade)
        if secao and not unidade.titulo and _SECAO_RELATORIO.match(chave_de_titulo(secao)) \
                and _FIM_DO_RELATORIO.search(_dobrar(unidade.trecho)):
            secao = ""
        if atual.tipo == "audiencia" and _RE_SENTENCA_EM_AUDIENCIA.search(_dobrar(unidade.trecho)):
            # O que segue no termo é a fala do juiz: a sentença.
            pecas.append(atual)
            data, fonte = _data_e_fonte(atual)
            atual = Peca("sentenca", "Sentença (proferida em audiência)", "juizo", titulo=unidade, no_topo=False,
                         data_padrao=data, data_padrao_confiavel=fonte in _FONTES_CONFIAVEIS,
                         duvidosa=atual.duvidosa, motivo_duvida=atual.motivo_duvida)
            secao = ""
    if atual.unidades or atual.titulo:
        pecas.append(atual)
    return pecas


# De onde veio a data da peça. Só as confiáveis ordenam decisões; a inferida (primeira data do
# corpo) costuma ser a de um fato narrado, e nunca vence a instância.
_FONTES_CONFIAVEIS = ("assinatura", "julgamento", "audiencia")


def _data_e_fonte(peca: Peca) -> tuple[str | None, str | None]:
    """Data da peça e de onde ela veio: a linha "Cidade, dd de mês de aaaa" ("assinatura"), a data do
    julgamento declarada ("julgamento"), a do termo de audiência ("audiencia") ou, em ato do juízo ou
    do cartório, na falta delas, a primeira data do corpo ("inferida"). Em peça de parte, sem a linha
    de assinatura não há como saber — a primeira data costuma ser a dos fatos."""
    for i in range(len(peca.unidades) - 1, -1, -1):
        unidade = peca.unidades[i]
        if i not in peca.soltas and RE_ASSINATURA.match(unidade.trecho) and (datas := datas_em(unidade.trecho)):
            return datas[0], "assinatura"
    for i, unidade in enumerate(peca.unidades):
        if i in peca.soltas or len(unidade.trecho) > 120:
            continue
        if (m := _RE_DATA_DE_JULGAMENTO.match(_dobrar(unidade.trecho))) and (datas := datas_em(unidade.trecho[m.end():])):
            return datas[0], "julgamento"
    if peca.data_padrao:
        return peca.data_padrao, "audiencia" if peca.data_padrao_confiavel else "inferida"
    if peca.tipo == "audiencia" and peca.unidades and _RE_DATA_AOS.search(_dobrar(peca.unidades[0].trecho)):
        return datas_em(peca.unidades[0].trecho)[0], "audiencia"
    if peca.origem in ("juizo", "cartorio"):
        for i, unidade in enumerate(peca.unidades):
            if i not in peca.soltas and (datas := datas_em(unidade.trecho)):
                return datas[0], "inferida"
    return None, None


def data_da_peca(peca: Peca) -> str | None:
    """Data da peça (ver `_data_e_fonte`)."""
    return _data_e_fonte(peca)[0]


# ---------------------------------------------------------------- natureza
def _em_secao_de_pedidos(peca: Peca, indice: int) -> bool:
    secao = sem_acento(peca.secoes.get(indice, "")).upper()
    return "PEDIDO" in secao or "REQUERIMENTO" in secao


# "Requer…", "Diante do exposto, requer…" e, com o sujeito, "A autora requer…", "O exequente pede…".
_RE_PEDIDO = re.compile(
    r"((diante do|ante o|pelo|por todo o) exposto,?\s*)?((a|o|as|os)\s+[a-z]+(\s+[a-z]+)?\s+)?(requer|requerem|pede|pedem|postula"
    r"|postulam)\b")


def _eh_pedido(peca: Peca, indice: int, unidade: Unidade) -> bool:
    if peca.origem != "parte" or RE_ASSINATURA.match(unidade.trecho):
        return False
    if unidade.trecho.endswith(":"):
        return False  # "Diante do exposto, requer:" só introduz a lista
    inicio = sem_acento(unidade.trecho[:60]).lower()
    if _RE_PEDIDO.match(inicio):
        return True
    return _em_secao_de_pedidos(peca, indice) and bool(re.match(r"^[a-z]\)|^[ivx]+\s*[-–—]", inicio))


def natureza(peca: Peca, indice: int, unidade: Unidade, presumir: bool = False) -> str:
    """Natureza da frase pela peça em que está. Em peça duvidosa (pode ser continuação de petição) e
    depois de título desconhecido, a natureza não é presumida ("trecho") — salvo com `presumir`,
    usado só para descrever, como não confirmada, a decisão que a peça duvidosa traria."""
    if not presumir and (peca.duvidosa or indice in peca.soltas):
        return "trecho"
    if peca.origem == "parte":
        return "pedido" if _eh_pedido(peca, indice, unidade) else "alegacao"
    if peca.origem == "juizo":
        if _SECAO_RELATORIO.match(chave_de_titulo(peca.secoes.get(indice, ""))):
            return "fundamento_judicial"  # o relatório narra o processo; não decide nada
        texto = _dobrar(_sem_citacao(unidade.trecho))
        if _RE_DISPOSITIVO.search(texto):
            return "decisao_judicial"
        if _RE_DETERMINACAO.search(texto):
            return "ato_judicial"
        return "fundamento_judicial"
    if peca.origem == "cartorio":
        return "fato_registrado"
    if peca.origem == "prova":
        return "documento_de_prova"
    return "trecho"


# ---------------------------------------------------------------- resultado das decisões
# "ACOLHO EM PARTE os pedidos", "REJEITO os pedidos iniciais" (sem "julgo").
_RE_PEDIDOS_ACOLHIDOS = re.compile(r"\bacolho,?\s+(integralmente\s+)?(o|os)\s+pedidos?\b")
_RE_PEDIDOS_ACOLHIDOS_EM_PARTE = re.compile(
    r"\bacolho,?\s+(em parte|parcialmente)\b|\bacolho\s+(o|os)\s+pedidos?\b.{0,40}\b(em parte|parcialmente)\b")
_RE_PEDIDOS_REJEITADOS = re.compile(r"\b(rejeito|nao acolho|desacolho),?\s+(integralmente\s+)?(o|os)\s+pedidos?\b")
# "PROCEDENTE o pedido, com exceção dos danos morais, que rejeito": procedência em parte.
_RE_EXCECAO = re.compile(
    r"\bcom (a )?exce[cç][aã]o d|\bexceto (o|a|os|as|quanto)\b|\bsalvo (o|a|os|as|quanto)\b|\bressalvad[oa]s?\b"
    r"|\bque rejeito\b|\brejeitando\b|\bafastando o pedido\b|\bindefiro o pedido\b|\bnao acolho o pedido\b")


def resultado_de_sentenca(texto: str) -> str | None:
    """Resultado de um dispositivo de sentença ("JULGO PROCEDENTE EM PARTE…"), em texto dobrado."""
    parcial = re.search(r"parcial(mente)? procedentes?|procedentes? em parte|procedencia parcial", texto) or \
        _RE_PEDIDOS_ACOLHIDOS_EM_PARTE.search(texto)
    improcedente = re.search(r"\bimprocedentes?\b", texto) or _RE_PEDIDOS_REJEITADOS.search(texto)
    procedente = re.search(r"\bprocedentes?\b", texto) or _RE_PEDIDOS_ACOLHIDOS.search(texto)  # \b: não casa
    # dentro de "improcedente"
    if procedente and improcedente:
        return "misto" if re.search(r"contraposto|reconven", texto) else "parcialmente procedente"
    if parcial:
        return "parcialmente procedente"
    if improcedente:
        return "improcedente"
    if procedente:
        return "parcialmente procedente" if _RE_EXCECAO.search(texto) else "procedente"
    if re.search(r"\bhomologo\b", texto):
        return "homologação de acordo"
    if re.search(r"\bextingo\b|\bjulgo extint|\bdeclaro extint", texto):
        return "extinção do processo"
    return None


_DAR = r"(dar|deu|deram|dou|da-se|dando|dao|dado|dar-lhes?|dou-lhes?|deram-lhes?|dando-lhes?)"
_NEGAR = r"(negar|negou|negaram|nego|negam|nega-se|negando|negado|negar-lhes?|nego-lhes?|negaram-lhes?|negando-lhes?)"


def resultado_de_recurso(texto: str) -> str | None:
    """Resultado de acórdão ou decisão de relator ("ACORDAM … em dar provimento"), em texto dobrado."""
    if re.search(r"\bnao conhe(co|cer|ceram|cido|ceu)\b", texto):
        return "recurso não conhecido"
    if re.search(rf"{_DAR} parcial provimento|parcialmente provid|provimento parcial|provid[oa]s? em parte", texto):
        return "recurso parcialmente provido"
    if re.search(rf"{_NEGAR} provimento|\b(des|im)provid[oa]s?\b|\bnao provid|voto pelo (nao provimento|desprovimento"
                 r"|improvimento)|\bmantid[ao] a sentenca", texto):
        return "recurso não provido"
    if re.search(rf"{_DAR} provimento|\bprovid[oa]s?\b|voto pelo provimento", texto):
        return "recurso provido"
    return None


# O que vem depois do verbo aplicado aos embargos ("ACOLHO os embargos … para julgar IMPROCEDENTE o
# pedido") é a consequência, não o resultado dos embargos.
_RE_CONSEQUENCIA_DOS_EMBARGOS = re.compile(r"\bpara\b|\be,?\s+(julgo|reformo|condeno|declaro)\b|,\s*(julgando|reformando)\b")


def _resultado_de_embargos(texto: str) -> str | None:
    """Resultado de decisão sobre embargos de declaração, pelo verbo aplicado a eles (antes do "para…")."""
    cabeca = _RE_CONSEQUENCIA_DOS_EMBARGOS.split(texto, maxsplit=1)[0]
    if re.search(r"\bnao conhe", cabeca):
        return "embargos de declaração não conhecidos"
    if re.search(r"parcial|em parte", cabeca):
        return "embargos de declaração acolhidos em parte"
    if re.search(r"\b(improcedentes?|rejeito|rejeitam|rejeitar|nao acolho|desacolho)\b|" + _NEGAR + " provimento", cabeca):
        return "embargos de declaração rejeitados"
    if re.search(r"\b(procedentes?|acolho|acolhem|acolher|acolhidos)\b|" + _DAR + " provimento", cabeca):
        return "embargos de declaração acolhidos"
    return None


def _consequencia_dos_embargos(texto: str) -> str | None:
    """"…para julgar IMPROCEDENTE o pedido" → "improcedente"."""
    partes = _RE_CONSEQUENCIA_DOS_EMBARGOS.split(texto, maxsplit=1)
    if len(partes) < 2 or not re.search(r"\bjulg", texto[len(partes[0]):]):
        return None
    return resultado_de_sentenca(texto[len(partes[0]):])


def _sobre_embargos(peca: Peca) -> bool:
    """Decisão que julga embargos de declaração (e não a causa)."""
    inicio = " ".join(_dobrar(u.trecho) for u in peca.unidades[:3])
    return bool(re.search(r"(trata-se de|opost|interpost)\w*.{0,40}embargos de declaracao|embargos de declaracao"
                          r".{0,40}(opost|interpost)", inicio))


@dataclass
class _Resultado:
    resultado: str | None
    consequencia: str | None = None  # "para julgar improcedente o pedido" num acórdão
    embargos: bool = False


def _resultado(peca: Peca, unidade: Unidade, embargos_da_peca: bool) -> _Resultado | None:
    texto = _dobrar(_sem_citacao(unidade.trecho))
    if not _RE_DISPOSITIVO.search(texto):
        return None
    if embargos_da_peca or re.search(r"embargos (de declaracao|declaratorios)", texto):
        if re.search(r"\b(julgo|rejeito|acolho|nao acolho|desacolho|conheco|nao conheco|acordam)\b|provimento", texto):
            return _Resultado(_resultado_de_embargos(texto), _consequencia_dos_embargos(texto), embargos=True)
        return None
    if peca.tipo in ("acordao", "decisao_monocratica", "decisao"):
        if recurso := resultado_de_recurso(texto):
            depois = texto.split("para julgar", 1)[1] if "para julgar" in texto else ""
            return _Resultado(recurso, resultado_de_sentenca(depois) if depois else None)
        if peca.tipo == "acordao" and re.search(r"\bjulg(aram|am)\b", texto):
            return _Resultado(resultado_de_sentenca(texto))
        return None
    if peca.tipo == "sentenca" and (re.search(r"\b(julgo|homologo|extingo)\b", texto)
                                    or _RE_PEDIDOS_ACOLHIDOS.search(texto) or _RE_PEDIDOS_REJEITADOS.search(texto)
                                    or _RE_PEDIDOS_ACOLHIDOS_EM_PARTE.search(texto)):
        return _Resultado(resultado_de_sentenca(texto))
    return None


def _resultado_da_sentenca(candidatos: list[tuple[Unidade, _Resultado]]) -> str | None:
    """Junta os capítulos do dispositivo: "JULGO PROCEDENTE o pedido de restituição." e, em outra
    frase, "JULGO IMPROCEDENTE o pedido de danos morais." dão procedência EM PARTE — não procedência."""
    resultados = {r.resultado for _, r in candidatos if r.resultado}
    if "misto" in resultados:
        return "misto"
    if "parcialmente procedente" in resultados or {"procedente", "improcedente"} <= resultados:
        textos = " ".join(_dobrar(u.trecho) for u, _ in candidatos)
        if {"procedente", "improcedente"} <= resultados and re.search(r"contraposto|reconven", textos):
            return "misto"
        return "parcialmente procedente"
    return candidatos[0][1].resultado if candidatos else None


@dataclass
class _Final:
    """Decisão que pode encerrar o processo ou o recurso, com o dispositivo principal."""

    peca: Peca
    ordem: int
    data: str | None
    principal: Unidade | None
    resultado: _Resultado | None
    embargos: bool
    data_confiavel: bool = False
    # Decisão que não é o resultado da causa: "agravo" (recurso contra decisão do meio do processo,
    # como uma liminar) ou "cumprimento" (fase de cobrança ou execução).
    colateral: str | None = None

    @property
    def nao_confirmada(self) -> bool:
        return self.peca.duvidosa

    @property
    def conta(self) -> bool:
        """Entra na escolha do resultado da causa."""
        return not (self.embargos or self.colateral or self.nao_confirmada)


def _colateral(peca: Peca, principal: Unidade | None, resultado: _Resultado | None) -> str | None:
    texto = _dobrar(principal.trecho) if principal else ""
    if peca.tipo in ("acordao", "decisao_monocratica", "decisao"):
        inicio = " ".join(_dobrar(u.trecho) for u in peca.unidades[:4])
        if _RE_AGRAVO.search(texto) or _RE_SOBRE_AGRAVO.search(inicio):
            return "agravo"
    if _RE_FASE_DE_CUMPRIMENTO.search(texto):
        return "cumprimento"
    return None


def _decisoes_finais(pecas: list[Peca]) -> tuple[list[_Final], dict[int, _Resultado]]:
    """Decisões finais e o resultado de cada frase de dispositivo delas (por id da unidade)."""
    finais = []
    por_unidade: dict[int, _Resultado] = {}
    for ordem, peca in enumerate(pecas):
        if peca.tipo not in _FINAIS:
            continue
        embargos = peca.tipo != "acordao" and _sobre_embargos(peca)
        candidatos = [(u, r) for i, u in enumerate(peca.unidades)
                      if natureza(peca, i, u, presumir=True) == "decisao_judicial"
                      and (r := _resultado(peca, u, embargos)) and r.resultado]
        # No acórdão, o "ACORDAM…" é o dispositivo; a ementa e o voto vêm depois na preferência.
        candidatos.sort(key=lambda c: 0 if re.search(r"\bacordam\b", _dobrar(c[0].trecho)) else 1)
        principal, resultado = candidatos[0] if candidatos else (None, None)
        if resultado is not None and peca.tipo == "sentenca" and not resultado.embargos:
            nao_embargos = [(u, r) for u, r in candidatos if not r.embargos]
            resultado = _Resultado(_resultado_da_sentenca(nao_embargos), resultado.consequencia)
        elif resultado is not None and resultado.consequencia is None:
            # "ACORDAM… dar provimento" e, no voto, "…para julgar improcedente": junta os dois.
            resultado = _Resultado(resultado.resultado, next(
                (r.consequencia for _, r in candidatos if r.consequencia and r.resultado == resultado.resultado),
                None), resultado.embargos)
        if peca.tipo == "decisao" and not (resultado and resultado.resultado and resultado.resultado.startswith("recurso")):
            continue  # decisão interlocutória: não encerra nada
        if peca.tipo == "decisao_monocratica" and not resultado:
            continue  # liminar do relator, por exemplo
        if not peca.duvidosa:
            por_unidade.update((id(u), r) for u, r in candidatos)
        data, fonte = _data_e_fonte(peca)
        finais.append(_Final(peca, ordem, data, principal, resultado, embargos or bool(resultado and resultado.embargos),
                             data_confiavel=fonte in _FONTES_CONFIAVEIS,
                             colateral=_colateral(peca, principal, resultado)))
    return finais, por_unidade


@dataclass
class _Escolha:
    """A decisão que governa e por quê. `incerta`: o arquivo não permite afirmar o resultado final."""

    final: _Final | None
    criterio: str = ""
    incerta: bool = False
    motivo: str = ""
    envolvidas: list[_Final] = field(default_factory=list)  # as decisões que deixam a escolha incerta


def _rotulo_final(f: _Final) -> str:
    quando = f" de {data_br(f.data)}" if f.data and f.data_confiavel else ""
    resultado = f" ({f.resultado.resultado.upper()})" if f.resultado and f.resultado.resultado else ""
    return f"{_ARTIGO.get(f.peca.tipo, 'a')} {f.peca.rotulo.lower()} da p. {f.peca.pagina_inicial}{quando}{resultado}"


def _mesmo_resultado(a: _Final, b: _Final) -> bool:
    ra, rb = a.resultado, b.resultado
    return bool(ra and rb) and (ra.resultado, ra.consequencia) == (rb.resultado, rb.consequencia)  # type: ignore[union-attr]


def _depois(a: _Final, b: _Final) -> bool:
    """`a` é posterior a `b`? Pelas datas confiáveis, quando as duas têm; senão, pela posição no arquivo."""
    if a.data_confiavel and b.data_confiavel and a.data and b.data and a.data != b.data:
        return a.data > b.data
    return a.ordem > b.ordem


def _que_vale(finais: list[_Final]) -> _Escolha:
    """A decisão que governa. Pela data, quando TODAS têm data confiável (linha de local e data, data do
    julgamento ou do termo); senão pela instância e, empatada a instância, pela posição — mas, se uma
    decisão de mesma instância com outro resultado não puder ser ordenada, ou se uma data confiável
    contradisser a instância, o leitor diz que não dá para determinar em vez de escolher.
    Embargos de declaração ACOLHIDOS depois dela mudam ou podem mudar o resultado."""
    candidatas = [f for f in finais if f.conta]
    if not candidatas:
        return _Escolha(None)
    if len(candidatas) == 1:
        escolha = _Escolha(candidatas[0], "única decisão final localizada")
    elif all(f.data_confiavel and f.data for f in candidatas):
        melhor = max(candidatas, key=lambda f: (f.data or "", _NIVEL[f.peca.tipo], f.ordem))
        escolha = _Escolha(melhor, "a mais recente pela data")
        # Mesma data e mesma instância, resultado diferente: a data não ordena — não escolhe pela posição.
        empatadas = [f for f in candidatas if f is not melhor and f.data == melhor.data
                     and _NIVEL[f.peca.tipo] == _NIVEL[melhor.peca.tipo] and not _mesmo_resultado(f, melhor)]
        if empatadas:
            escolha.incerta = True
            escolha.envolvidas = [melhor, *empatadas[:3]]
            escolha.motivo = ("há mais de uma decisão final com a mesma data e resultados diferentes: "
                              + "; ".join(map(_rotulo_final, escolha.envolvidas)))
    else:
        melhor = max(candidatas, key=lambda f: (_NIVEL[f.peca.tipo], f.ordem))
        conflitantes = [
            f for f in candidatas if f is not melhor and not _mesmo_resultado(f, melhor) and (
                _NIVEL[f.peca.tipo] == _NIVEL[melhor.peca.tipo]
                or (f.data_confiavel and melhor.data_confiavel and (f.data or "") > (melhor.data or "")))
        ]
        escolha = _Escolha(melhor, "nem todas as decisões têm data confiável: escolhida pela instância e, depois, "
                                   "pela posição no arquivo")
        if conflitantes:
            escolha.incerta = True
            escolha.envolvidas = [melhor, *conflitantes[:3]]
            escolha.motivo = ("há mais de uma decisão final com resultados diferentes e as datas no arquivo não "
                              "permitem saber qual é a mais recente: " + "; ".join(map(_rotulo_final, escolha.envolvidas)))
    vale = escolha.final
    assert vale is not None
    if not escolha.incerta and vale.peca.tipo == "sentenca":
        # Duas sentenças de mérito com resultados diferentes e nenhuma decisão de tribunal entre elas que
        # explique a mudança (anulação e nova sentença): pode ser peça de outro processo, texto inserido
        # numa petição ou erro — escolher a mais recente seria afirmar o que o arquivo não sustenta.
        datadas = all(f.data_confiavel and f.data for f in candidatas)

        def chave(f: _Final) -> tuple:
            return (f.data or "", f.ordem) if datadas else ("", f.ordem)

        corte = max((chave(g) for g in candidatas if _NIVEL[g.peca.tipo] > 1 and chave(g) < chave(vale)), default=None)
        rivais = [f for f in candidatas if f is not vale and f.peca.tipo == "sentenca" and not _mesmo_resultado(f, vale)
                  and (corte is None or chave(f) > corte)]
        if rivais:
            escolha = _Escolha(vale, escolha.criterio, True,
                               "há sentenças com resultados diferentes e nenhuma decisão de tribunal entre elas que "
                               "explique a mudança (pode ser sentença anulada e refeita, peça de outro processo ou "
                               "texto inserido no arquivo): " + "; ".join(map(_rotulo_final, [vale, *rivais[:3]])),
                               [vale, *rivais[:3]])
    acolhidos = [f for f in finais if f.embargos and not f.nao_confirmada and f.resultado and f.resultado.resultado
                 and "acolhidos" in f.resultado.resultado and _depois(f, vale)]
    if acolhidos and not escolha.incerta:
        embargos = max(acolhidos, key=lambda f: f.ordem)
        texto = _dobrar(embargos.principal.trecho) if embargos.principal else ""
        if _RE_SEM_EFEITO_MODIFICATIVO.search(texto):
            escolha.criterio += "; embargos de declaração acolhidos depois dela, sem mudar o resultado"
        elif embargos.resultado and embargos.resultado.consequencia and \
                embargos.resultado.resultado == "embargos de declaração acolhidos":
            return _Escolha(embargos, f"embargos de declaração acolhidos depois d{_rotulo_final(vale)} mudaram o "
                                      "resultado, pelo trecho")
        else:
            return _Escolha(vale, escolha.criterio, True,
                            f"depois d{_rotulo_final(vale)}, a decisão da p. {embargos.peca.pagina_inicial} acolheu "
                            "embargos de declaração, que podem ter mudado o resultado — o trecho não diz claramente "
                            "como ficou", [vale, embargos])
    return escolha


def _instancia(peca: Peca, resultado: _Resultado | None = None) -> str:
    if peca.tipo == "acordao":
        return "tribunal (colegiado)"
    if peca.tipo == "decisao_monocratica":
        return "tribunal (decisão individual do relator)"
    if peca.tipo == "decisao" and resultado and resultado.resultado and resultado.resultado.startswith("recurso"):
        return "decisão individual sobre recurso"
    return "primeira instância"


# ---------------------------------------------------------------- prazos
def prazos_em(texto: str) -> list[str]:
    """Durações de prazo da frase, como estão escritas e na ordem em que aparecem, presas à palavra
    "prazo" (ou "em", "dentro de", "até", ou "N dias de prazo")."""
    dobrado = _dobrar(texto)
    trechos: set[tuple[int, int]] = set()
    for gatilho in _RE_GATILHO_PRAZO.finditer(dobrado):
        inicio = gatilho.end()
        if gatilho.group(0) == "prazo":
            # Janela limitada: buscar até o fim da frase a cada "prazo" ficaria quadrático.
            m = _RE_DURACAO.search(dobrado, inicio, inicio + 140)
            if m is None or m.start("d") - inicio > 80:
                continue
        elif (m := _RE_DURACAO_COLADA.match(dobrado, inicio)) is None:
            continue
        entre = dobrado[inicio:m.start("d")]
        if "." in entre.replace("art.", "") or ";" in entre or re.search(r"\bas\s*$", entre):
            continue
        trechos.add((m.start("d"), m.end("d")))
    for m in _RE_DURACAO_DE_PRAZO.finditer(dobrado):
        trechos.add((m.start("d"), m.end("d")))
    if trechos:
        # Uma duração dentro de outra ("15 (quinze) dias" e "quinze) dias") conta uma vez só.
        ordenados = sorted(trechos, key=lambda t: (t[0], -t[1]))
        saida, fim = [], -1
        for a, b in ordenados:
            if a >= fim:
                saida.append(texto[a:b])
                fim = b
        return saida
    if m := _RE_PRAZO_LEGAL.search(dobrado):
        return [texto[m.start():m.end()]]
    return []


def prazo_em(texto: str) -> str | None:
    """A primeira duração de prazo da frase (ver `prazos_em`)."""
    prazos = prazos_em(texto)
    return prazos[0] if prazos else None


def _tipo_de_prazo(nat: str, peca: Peca, texto: str) -> str:
    dobrado = _dobrar(texto)
    if _RE_PRAZO_DECORRIDO.search(dobrado) or (peca.origem == "cartorio" and _RE_DECURSO_CERTIFICADO.search(dobrado)):
        return "prazo que o documento diz já ter decorrido — não está correndo"
    if nat == "pedido":
        return "prazo pedido por uma parte — não está correndo"
    if nat == "fundamento_judicial":
        return "prazo citado na fundamentação — não é ordem de cumprimento"
    if nat == "trecho":
        return "prazo mencionado no documento"  # peça não identificada ou não confirmada: sem presumir
    if peca.origem == "juizo":
        return "prazo fixado em ato do juiz"
    if peca.origem == "cartorio":
        return "prazo informado em certidão ou ata"
    if peca.origem == "parte":
        return "prazo mencionado por uma parte"
    return "prazo mencionado no documento"


# Prazos que podem estar correndo contra alguém (os demais são citações).
PRAZOS_EM_CURSO = ("prazo fixado em ato do juiz", "prazo informado em certidão ou ata")


# ---------------------------------------------------------------- análise
def _cortar_trecho(trecho: str) -> str:
    """Começo da frase, até `LIMITE_TRECHO` caracteres, cortado num espaço (continua citável: é
    uma fatia literal da página). Frase maior que isso é página sem pontuação, não frase de verdade."""
    if len(trecho) <= LIMITE_TRECHO:
        return trecho
    corte = trecho[:LIMITE_TRECHO]
    espaco = corte.rfind(" ")
    return corte[:espaco] if espaco > LIMITE_TRECHO // 2 else corte


def _texto_do_item(trecho: str) -> str:
    return trecho if len(trecho) <= LIMITE_TRECHO else _cortar_trecho(trecho) + " […]"


def _rotulo_de(peca: Peca | None, indice: int | None = None) -> str | None:
    if peca is None or (indice is not None and indice in peca.soltas):
        return None
    return f"{peca.rotulo} (não confirmada)" if peca.duvidosa else peca.rotulo


class _Montador:
    def __init__(self, doc: DocumentoExtraido):
        self.doc = doc
        self.descartadas = 0  # citações que não conferiram (deve ser sempre 0)

    def citacao(self, unidade: Unidade) -> dict | None:
        citacao = citar(self.doc, unidade.pagina, _cortar_trecho(unidade.trecho))
        if not citacao.verificada:  # defesa: o leitor nunca apresenta citação que não confere
            self.descartadas += 1
            return None
        return citacao.como_dict()

    def item(self, unidade: Unidade, nat: str, peca: Peca | None, indice: int | None = None, **extra) -> dict | None:
        if (citacao := self.citacao(unidade)) is None:
            return None
        return {
            "texto": _texto_do_item(unidade.trecho),
            "natureza": nat,
            "peca": _rotulo_de(peca, indice),
            "citacoes": [citacao],
            **extra,
        }


class _Lista:
    """Lista com teto: guarda os primeiros itens e conta todos."""

    def __init__(self, limite: int | None = None):
        self.itens: list[dict] = []
        self.total = 0
        self.limite = LIMITE_ITENS_POR_CATEGORIA if limite is None else limite

    def cabe(self) -> bool:
        self.total += 1
        return len(self.itens) < self.limite

    def add(self, item: dict | None) -> None:
        if item is not None:
            self.itens.append(item)


class _Relogio:
    """Orçamento de tempo das fases que percorrem o documento (identificação, partes, itens, folhas).
    A segmentação e a escolha da decisão que vale não param no meio: são lineares, limitadas pelos
    tetos da extração, e uma escolha feita sobre metade do documento poderia apontar como vigente uma
    decisão já reformada."""

    def __init__(self, limite: float):
        self.limite = limite
        self.parou_na_pagina: int | None = None

    def passou(self, k: int, pagina: int) -> bool:
        if self.parou_na_pagina is not None:
            return True
        if k % 200 == 0 and time.monotonic() > self.limite:
            self.parou_na_pagina = pagina
            return True
        return False


def _resumo_trecho(texto: str, limite: int = 220) -> str:
    return texto if len(texto) <= limite else texto[: limite - 1].rsplit(" ", 1)[0] + "…"


def _linhas_brutas(doc: DocumentoExtraido) -> list[tuple[int, str]]:
    """Linhas de cada página com texto, ANTES de tirar cabeçalho repetido e títulos de peça:
    o número do processo e as partes às vezes só aparecem no cabeçalho de cada página."""
    return [(p.numero, " ".join(linha.split())) for p in doc.paginas if p.tem_texto
            for linha in p.texto.split("\n") if linha.strip()]


def _segmentos(linha: str) -> list[str]:
    return [s for s in _RE_SEPARADOR.split(linha) if s] if _RE_SEPARADOR.search(linha) else [linha]


@dataclass
class _Identificacao:
    numeros: dict[str, dict]
    total_numeros: int
    principal: str | None  # o número que mais aparece no arquivo
    rotulos: dict[str, dict]
    valores: dict[str, dict[str, tuple[str, dict]]]  # rótulo → valor normalizado → (valor, citação)


def _identificacao(doc: DocumentoExtraido, por_unidade: list, brutas: list[tuple[int, str]],
                   relogio: _Relogio) -> _Identificacao:
    numeros: dict[str, dict] = {}
    vezes: dict[str, int] = {}
    rotulos: dict[str, dict] = {}
    valores: dict[str, dict[str, tuple[str, dict]]] = {}

    def rotulo(pagina: int, trecho: str, mr: re.Match) -> None:
        # A citação só é feita para o que vai aparecer: o 1º valor de cada rótulo e poucos diferentes.
        chave = sem_acento(mr.group(1)).lower().replace(" ", "_")
        valor = mr.group(2).strip()
        normal = " ".join(sem_acento(valor).lower().rstrip(".").split())
        distintos = valores.setdefault(chave, {})
        if normal in distintos or len(distintos) >= LIMITE_VALORES_POR_ROTULO:
            return
        citacao = citar(doc, pagina, trecho).como_dict()
        distintos[normal] = (valor, citacao)
        rotulos.setdefault(chave, {"rotulo": mr.group(1), "valor": valor, "citacoes": [citacao]})

    for k, (_peca, _, u) in enumerate(por_unidade):
        if relogio.passou(k, u.pagina):
            break
        if mr := _RE_ROTULO.match(u.trecho):
            rotulo(u.pagina, u.trecho, mr)
    for k, (pagina, linha) in enumerate(brutas):
        if relogio.passou(k, pagina):
            break
        for numero in cnj.encontrar(linha):
            vezes[numero] = vezes.get(numero, 0) + 1
            if numero not in numeros and len(numeros) < LIMITE_NUMEROS:
                info = cnj.interpretar(numero)
                numeros[numero] = {
                    "numero": numero,
                    "digito_verificador_valido": bool(info and info.valido),
                    "segmento": info.segmento if info else None,
                    "tribunal": info.tribunal if info else None,
                    "citacoes": [citar(doc, pagina, linha).como_dict()],
                }
        for segmento in _segmentos(linha):
            if mr := _RE_ROTULO.match(segmento):
                rotulo(pagina, segmento, mr)
    ordem = {n: i for i, n in enumerate(vezes)}
    principal = max(vezes, key=lambda n: (vezes[n], -ordem[n])) if vezes else None
    return _Identificacao(numeros, len(vezes), principal, rotulos, valores)


_IGNORADAS_NO_NOME = {"ltda", "sa", "me", "epp", "da", "de", "do", "dos", "das"}


def _tokens_do_nome(nome: str) -> frozenset[str]:
    return frozenset(re.findall(r"\w+", sem_acento(nome).lower())) - _IGNORADAS_NO_NOME


def _mesmo_nome(a: str, b: str) -> bool:
    """"Loja Teste Ltda." e "Loja Teste Comércio Ltda." são a mesma parte; "Maria" e "Mariana", não."""
    ta, tb = _tokens_do_nome(a), _tokens_do_nome(b)
    return bool(ta and tb) and (ta <= tb or tb <= ta)


def _partes(m: _Montador, por_unidade: list, brutas: list[tuple[int, str]],
            relogio: _Relogio) -> tuple[list[dict], int, list[tuple[str, str, int, str]]]:
    """Partes (com teto), total de partes distintas e todo rótulo de parte (papel, nome, página, trecho),
    sem citação: só os poucos nomes que aparecerem numa inconsistência são citados."""
    partes: list[dict] = []
    vistos: set[str] = set()
    rotuladas: list[tuple[str, str, int, str]] = []

    def nova(papel: str, nome: str, u: Unidade, nat: str, peca: Peca | None, como: str, indice: int | None = None):
        nome = nome.strip().rstrip(",;")
        chave = sem_acento(nome).lower().strip(" .")
        if chave in vistos or len(chave) < 3:
            return
        vistos.add(chave)
        if len(partes) < LIMITE_PARTES and (
                item := m.item(u, nat, peca, indice, papel=papel, nome=nome, identificada_por=como)):
            partes.append(item)

    def nat_da_peca(peca: Peca, indice: int) -> str:
        if peca.duvidosa or indice in peca.soltas:
            return "trecho"
        return {"parte": "alegacao", "cartorio": "fato_registrado", "juizo": "ato_processual"}.get(peca.origem, "trecho")

    for k, (peca, i, u) in enumerate(por_unidade):
        if relogio.passou(k, u.pagina):
            break
        if mp := _RE_PARTE_ROTULADA.match(u.trecho):
            nova(_PAPEIS.get(mp.group(1).lower(), mp.group(1).lower()), mp.group(2), u, nat_da_peca(peca, i), peca,
                 "rótulo no documento", i)
    for k, (peca, i, u) in enumerate(por_unidade):
        if relogio.passou(k, u.pagina):
            break
        if peca.tipo == "peticao_inicial" and not peca.duvidosa and (mf := _RE_EM_FACE_DE.search(u.trecho)):
            nova("ré(u)", mf.group(1), u, "alegacao", peca, "\"em face de\" na petição inicial", i)
    for k, (pagina, linha) in enumerate(brutas):
        if relogio.passou(k, pagina):
            break
        for segmento in _segmentos(linha):
            if mp := _RE_PARTE_ROTULADA.match(segmento):
                papel = _PAPEIS.get(mp.group(1).lower(), mp.group(1).lower())
                rotuladas.append((papel, mp.group(2).strip().rstrip(",;"), pagina, segmento))
                nova(papel, mp.group(2), Unidade(pagina, segmento), "trecho", None,
                     "linha de cabeçalho ou de título do documento")
    return partes, len(vistos), rotuladas


def _transito(m: _Montador, pecas: list[Peca], escolha: _Escolha,
              principal: str | None) -> tuple[list, list, list, int]:
    """Certidões de trânsito: as confiáveis, as que não dá para confirmar, as inconsistências e o total.

    Só é confiável a certidão que (1) afirma o trânsito, sem negá-lo nem tratá-lo como futuro; (2) é
    peça própria, no alto de uma página, e não vem logo depois de uma petição sem fechamento (que a
    parte poderia continuar com "CERTIDÃO"); (3) não cita outro número de processo; (4) é posterior
    à decisão final que vale — que tem de existir, ter data confiável e não ser incerta."""
    confiaveis: list[dict] = []
    nao_confirmadas: list[dict] = []
    inconsistencias: list[dict] = []
    total = 0
    vale = escolha.final
    data_decisao = vale.data if vale is not None and vale.data_confiavel else None
    # Escolha incerta: a certidão ainda pode ser comparada com a MAIS ANTIGA das decisões que podem valer
    # (anterior a todas, ela é anterior a qualquer uma que valha).
    referencia = vale
    if escolha.incerta and escolha.envolvidas and all(f.data_confiavel and f.data for f in escolha.envolvidas):
        referencia = min(escolha.envolvidas, key=lambda f: f.data or "")
    data_referencia = referencia.data if referencia is not None and referencia.data_confiavel else None
    for peca in pecas:
        if peca.tipo != "certidao":
            continue
        outros = sorted({n for i, u in enumerate(peca.unidades) if i not in peca.soltas
                         for n in cnj.encontrar(u.trecho) if n != principal}) if principal else []
        for indice, u in enumerate(peca.unidades):
            if indice in peca.soltas:
                continue
            texto = _dobrar(u.trecho)
            if not _RE_TRANSITO.search(texto):
                continue
            total += 1
            datas = datas_em(u.trecho)
            data = datas[-1] if datas else data_da_peca(peca)
            motivo = None
            if _RE_TRANSITO_NEGADO.search(texto):
                motivo = "a certidão diz que a decisão ainda NÃO transitou em julgado"
            elif _RE_TRANSITO_FUTURO.search(texto):
                motivo = ("a certidão fala do trânsito em julgado como condição ou acontecimento futuro, sem "
                          "certificá-lo")
            elif peca.duvidosa:
                motivo = f"a certidão {peca.motivo_duvida}; não dá para ter certeza de que é do cartório"
            elif not peca.no_topo:
                motivo = "a certidão não começa em página própria: não dá para ter certeza de que é uma peça do cartório"
            elif outros:
                motivo = (f"a certidão cita outro número de processo ({', '.join(outros[:2])}), diferente do número "
                          f"principal do arquivo ({principal}): pode ser de outro processo")
            elif vale is None:
                motivo = ("não localizei no arquivo a decisão final a que a certidão se refere: não dá para conferir "
                          "se ela é deste processo nem se é posterior à decisão")
            elif escolha.incerta and data is not None and data_referencia is not None and referencia is not vale \
                    and data < data_referencia:
                motivo = (f"a certidão é de {data_br(data)}, ANTERIOR a todas as decisões finais que podem valer (a mais "
                          f"antiga: {referencia.peca.rotulo.lower()} de {data_br(data_referencia)})")  # type: ignore[union-attr]
            elif escolha.incerta:
                motivo = ("não foi possível determinar qual decisão final vale: não dá para conferir a que decisão a "
                          "certidão se refere")
            elif data_decisao is None:
                motivo = ("a decisão final não tem data confiável no arquivo (linha de local e data): não dá para "
                          "conferir se a certidão é posterior a ela")
            elif data is None:
                motivo = "a certidão não tem data: não dá para conferir se é posterior à decisão final"
            elif data < data_decisao:
                motivo = (f"a certidão é de {data_br(data)}, ANTERIOR à decisão final mais recente "
                          f"({vale.peca.rotulo.lower()} de {data_br(data_decisao)})")
            destino = confiaveis if motivo is None else nao_confirmadas
            if len(destino) >= LIMITE_TRANSITO:
                continue
            nat = "trecho" if peca.duvidosa else "fato_registrado"
            item = m.item(u, nat, peca, indice, data=data, **({"motivo": motivo} if motivo else {}))
            if item is None:
                continue
            destino.append(item)
            if motivo and "ANTERIOR" in motivo and referencia is not None and len(inconsistencias) < LIMITE_DIVERGENCIAS:
                citacoes = item["citacoes"] + (_citacao_do_final(m, referencia))
                inconsistencias.append(_inconsistencia(
                    "transito_antes_da_decisao",
                    f"A certidão de trânsito em julgado (p. {u.pagina}) tem data anterior à decisão final "
                    f"({referencia.peca.rotulo.lower()} de {data_br(data_referencia or '')}, p. "
                    f"{referencia.peca.pagina_inicial}). "
                    "Pelo arquivo, não dá para afirmar que a decisão é definitiva.", citacoes))
    return confiaveis, nao_confirmadas, inconsistencias, total


def _citacao_do_final(m: _Montador, final: _Final) -> list[dict]:
    unidade = final.principal or final.peca.titulo
    if unidade is None:
        return []
    citacao = m.citacao(unidade)
    return [citacao] if citacao else []


def _inconsistencia(tipo: str, texto: str, citacoes: list[dict]) -> dict:
    return {"tipo": tipo, "texto": texto, "natureza": "inconsistencia", "citacoes": citacoes}


def _inconsistencias(doc: DocumentoExtraido, m: _Montador, finais: list[_Final], rotuladas: list,
                     valores: dict) -> list[dict]:
    saida: list[dict] = []
    # Decisões finais do mesmo tipo com resultados diferentes. Agrupa por resultado (a 1ª decisão de cada
    # um) e descreve poucos pares: comparar todos os pares e citar cada um era quadrático (2 mil
    # sentenças alternadas: 84 s e 1,1 GB).
    por_tipo: dict[str, dict[str | None, _Final]] = {}
    for f in finais:
        if f.conta and f.resultado and f.resultado.resultado:
            por_tipo.setdefault(f.peca.tipo, {}).setdefault(f.resultado.resultado, f)
    for representantes in por_tipo.values():
        distintos = list(representantes.values())
        primeira = distintos[0]
        for outra in distintos[1:1 + LIMITE_DIVERGENCIAS]:
            a, b = (primeira, outra) if primeira.ordem < outra.ordem else (outra, primeira)
            saida.append(_inconsistencia(
                "decisoes_finais_divergentes",
                f"Há duas decisões do mesmo tipo com resultados diferentes: {a.peca.rotulo.lower()} da p. "
                f"{a.peca.pagina_inicial} ({(a.resultado.resultado or '').upper()}) e {b.peca.rotulo.lower()} da p. "  # type: ignore[union-attr]
                f"{b.peca.pagina_inicial} ({(b.resultado.resultado or '').upper()}). Pode ser decisão anulada e "  # type: ignore[union-attr]
                "refeita, peça de outro processo no mesmo arquivo ou erro — confira.",
                _citacao_do_final(m, a) + _citacao_do_final(m, b)))
    # Nomes diferentes para o mesmo papel: índice por conjunto de palavras do nome; cada nome novo é
    # comparado só com os poucos já guardados (antes, com todos: 4 mil nomes, 52 s).
    por_papel: dict[str, list[tuple[str, frozenset[str], int, str]]] = {}
    vistos: dict[str, set[frozenset[str]]] = {}
    for papel, nome, pagina, trecho in rotuladas:
        tokens = _tokens_do_nome(nome)
        ja = vistos.setdefault(papel, set())
        if not tokens or tokens in ja:
            continue
        ja.add(tokens)
        lista = por_papel.setdefault(papel, [])
        if len(lista) < LIMITE_NOMES_POR_PAPEL and not any(tokens <= t or t <= tokens for _, t, _, _ in lista):
            lista.append((nome, tokens, pagina, trecho))
    for papel, nomes in por_papel.items():
        if len(nomes) > 1:
            citados = [(nome, c) for nome, _, pagina, trecho in nomes[:4] if (c := m.citacao(Unidade(pagina, trecho)))]
            if len(citados) < 2:
                continue
            descricao = " e ".join(f"«{nome}» (p. {c['pagina']})" for nome, c in citados)
            saida.append(_inconsistencia(
                "nomes_divergentes",
                f"O documento traz nomes diferentes para {papel}: {descricao}. Podem ser pessoas diferentes no "
                "mesmo polo ou erro de digitação — confira.", [c for _, c in citados]))
    # Valores diferentes para o mesmo campo da capa.
    for chave, distintos_valores in valores.items():
        if chave in _ROTULOS_UNICOS and len(distintos_valores) > 1:
            itens = list(distintos_valores.values())[:4]
            rotulo = chave.replace("_", " ")
            descricao = " e ".join(f"«{valor}» (p. {c['pagina']})" for valor, c in itens)
            saida.append(_inconsistencia(
                "valores_divergentes", f"O campo \"{rotulo}\" aparece com valores diferentes: {descricao}. Pode ter "
                "sido corrigido no curso do processo ou ser erro — confira.", [c for _, c in itens]))
    saida += _folhas_ausentes(doc)
    return saida[:LIMITE_INCONSISTENCIAS]


def _folhas_ausentes(doc: DocumentoExtraido) -> list[dict]:
    """Saltos na numeração das folhas carimbadas: folhas que não estão no arquivo, em faixas.
    As faixas ficam como (primeira, última): "fls. 1" seguida de "fls. 999999" não vira um milhão de
    números na memória (antes: 40 páginas, 2,7 KB, 849 MB)."""
    carimbadas = [(p.numero, int(p.folha)) for p in doc.paginas if p.folha and p.folha.isdigit()]
    faltam: list[tuple[int, int]] = []
    fora_de_ordem: list[tuple[int, int, int, int]] = []
    for (pag_a, fl_a), (pag_b, fl_b) in zip(carimbadas, carimbadas[1:], strict=False):
        sem_carimbo = pag_b - pag_a - 1  # páginas do arquivo entre as duas, sem carimbo legível
        if fl_b <= fl_a:
            fora_de_ordem.append((pag_a, fl_a, pag_b, fl_b))
        elif fl_b - fl_a - 1 > sem_carimbo:
            faltam.append((fl_a + 1 + sem_carimbo, fl_b - 1))  # aproximação: as primeiras seriam as sem carimbo
    saida = []
    citacoes: list[dict] = []
    for pagina in doc.paginas:
        if pagina.folha and pagina.tem_texto and len(citacoes) < 6:
            carimbos = list(RE_CARIMBO_FOLHA.finditer(pagina.texto))
            if carimbos and (c := citar(doc, pagina.numero, carimbos[-1].group(0).strip())).verificada:
                citacoes.append(c.como_dict())
    if faltam:
        saida.append(_inconsistencia(
            "folhas_ausentes",
            f"A numeração das folhas salta: as fls. {faixas_de_intervalos(faltam)} não estão no arquivo enviado (ou "
            "estão sem carimbo legível). O que estiver nelas não foi lido.", citacoes))
    if fora_de_ordem:
        pag_a, fl_a, pag_b, fl_b = fora_de_ordem[0]
        saida.append(_inconsistencia(
            "folhas_fora_de_ordem",
            f"A numeração das folhas volta ou se repete: a p. {pag_a} tem fls. {fl_a} e a p. {pag_b} tem fls. {fl_b}"
            f"{f' (e mais {len(fora_de_ordem) - 1} caso(s))' if len(fora_de_ordem) > 1 else ''}. O arquivo pode "
            "misturar documentos ou estar fora de ordem.", citacoes))
    return saida


_MOTIVO_COLATERAL = {
    "agravo": "não é o resultado da causa: decide um agravo, recurso contra uma decisão tomada no meio do processo "
              "(por exemplo, uma liminar)",
    "cumprimento": "não é o resultado da causa: é da fase de cumprimento de sentença ou da execução (cobrança, "
                   "pagamento, extinção da cobrança)",
}


def _decisoes_nao_usadas(m: _Montador, finais: list[_Final]) -> list[dict]:
    """Decisões que existem no arquivo mas não entram no resultado da causa, e por quê."""
    saida: list[dict] = []
    for f in finais:
        if not (f.colateral or f.nao_confirmada) or len(saida) >= LIMITE_DECISOES_NAO_USADAS:
            continue
        motivo = (f"{f.peca.motivo_duvida}: não dá para ter certeza de que é peça do juízo" if f.nao_confirmada
                  else _MOTIVO_COLATERAL[f.colateral or ""])
        saida.append({
            "tipo": f.peca.tipo,
            "rotulo": f.peca.rotulo,
            "pagina": f.peca.pagina_inicial,
            "data": f.data if f.data_confiavel else None,
            # Decisão não confirmada (pode ser texto de parte): o resultado dela não é repetido.
            "resultado": None if f.nao_confirmada else (f.resultado.resultado if f.resultado else None),
            "colateral": f.colateral,
            "nao_confirmada": f.nao_confirmada,
            "motivo": motivo,
            "natureza": "trecho" if f.nao_confirmada else "decisao_judicial",
            "citacoes": [] if f.nao_confirmada else _citacao_do_final(m, f),
        })
    return saida


def _avisos_de_segmentacao(pecas: list[Peca], recusas: list[_Recusa]) -> list[str]:
    avisos = []
    if recusas:
        lista = ", ".join(f"«{r.unidade.trecho[:60]}» (p. {r.unidade.pagina})" for r in recusas[:LIMITE_TITULOS_RECUSADOS])
        resto = f" e mais {len(recusas) - LIMITE_TITULOS_RECUSADOS}" if len(recusas) > LIMITE_TITULOS_RECUSADOS else ""
        avisos.append(
            f"Títulos de decisão ou de certidão que apareceram no meio de outra peça e não foram tratados como peça "
            f"própria: {lista}{resto}. Podem ser citação, subtítulo ou texto escrito por uma parte; se algum for mesmo "
            "uma decisão ou certidão, o resumo não a considerou — confira no original.")
    duvidosas = [p for p in pecas if p.duvidosa and (p.tipo in _FINAIS or p.tipo == "certidao")]
    for peca in duvidosas[:3]:
        avisos.append(
            f"{_ARTIGO.get(peca.tipo, 'a').upper()} {peca.rotulo.lower()} da p. {peca.pagina_inicial} {peca.motivo_duvida}. "
            "Não dá para ter certeza de que é peça do juízo ou do cartório, e ela não foi usada no resultado nem no "
            "trânsito em julgado — confira no original.")
    if len(duvidosas) > 3:
        avisos.append(f"Há mais {len(duvidosas) - 3} peça(s) do juízo ou do cartório nas mesmas condições.")
    return avisos


def analisar(doc: DocumentoExtraido, *, orcamento_s: float | None = None) -> dict:
    orcamento_s = ORCAMENTO_ANALISE_S if orcamento_s is None else orcamento_s
    relogio = _Relogio(time.monotonic() + orcamento_s)
    lista = unidades(doc)
    recusas: list[_Recusa] = []
    pecas = segmentar(lista, recusas)
    m = _Montador(doc)
    por_unidade: list[tuple[Peca, int, Unidade]] = [
        (peca, i, u) for peca in pecas for i, u in enumerate(peca.unidades)
    ]
    brutas = _linhas_brutas(doc)
    ident = _identificacao(doc, por_unidade, brutas, relogio)
    partes, total_partes, rotuladas = _partes(m, por_unidade, brutas, relogio)

    finais, resultado_por_unidade = _decisoes_finais(pecas)
    escolha = _que_vale(finais)
    vale = escolha.final
    datas = {id(peca): _data_e_fonte(peca) for peca in pecas}

    # --- peças
    pecas_saida: list[dict] = []
    total_pecas = 0
    for peca in pecas:
        if peca.tipo == "sem_titulo":
            continue
        total_pecas += 1
        if len(pecas_saida) >= LIMITE_PECAS:
            continue
        citacao = m.citacao(peca.titulo) if peca.titulo else None
        data, fonte = datas[id(peca)]
        saida_peca = {
            "tipo": peca.tipo,
            "rotulo": peca.rotulo,
            "origem": peca.origem,
            "pagina_inicial": peca.pagina_inicial,
            "pagina_final": peca.pagina_final,
            "data": data,
            "data_confirmada": fonte in _FONTES_CONFIAVEIS,
            "citacoes": [citacao] if citacao else [],
        }
        if peca.duvidosa:
            saida_peca.update(nao_confirmada=True, motivo=peca.motivo_duvida)
        pecas_saida.append(saida_peca)

    # --- itens por categoria (com teto e orçamento de tempo)
    categorias = ("alegacoes", "pedidos", "decisoes", "obrigacoes_e_determinacoes", "prazos", "recursos")
    listas = {c: _Lista() for c in categorias}
    eventos: list[tuple[str, int, int, Peca, int, Unidade, str, str, str]] = []
    for k, (peca, i, u) in enumerate(por_unidade):
        if relogio.passou(k, u.pagina):
            break
        if u.titulo:
            continue
        nat = natureza(peca, i, u)
        dobrado = _dobrar(u.trecho)
        if nat == "pedido" and listas["pedidos"].cabe():
            listas["pedidos"].add(m.item(u, nat, peca, i))
        elif (nat == "alegacao" and len(u.trecho) >= 40 and not RE_ASSINATURA.match(u.trecho)
              and not RE_ENDERECAMENTO.match(chave_de_titulo(u.trecho)) and listas["alegacoes"].cabe()):
            listas["alegacoes"].add(m.item(u, nat, peca, i, secao=peca.secoes.get(i) or None))
        if nat == "decisao_judicial" and listas["decisoes"].cabe():
            r = resultado_por_unidade.get(id(u))
            listas["decisoes"].add(m.item(
                u, nat, peca, i, resultado=r.resultado if r else None, instancia=_instancia(peca, r),
                peca_tipo=peca.tipo, peca_pagina=peca.pagina_inicial, peca_data=datas[id(peca)][0],
                sobre_embargos=bool(r and r.embargos)))
        if peca.origem in ("juizo", "cartorio") and nat != "trecho" and _RE_DETERMINACAO.search(dobrado) \
                and listas["obrigacoes_e_determinacoes"].cabe():
            listas["obrigacoes_e_determinacoes"].add(m.item(u, nat, peca, i))
        if (duracoes := prazos_em(u.trecho)) and listas["prazos"].cabe():
            extra = {"duracoes": duracoes} if len(duracoes) > 1 else {}
            listas["prazos"].add(m.item(u, nat, peca, i, duracao=duracoes[0],
                                        tipo_de_prazo=_tipo_de_prazo(nat, peca, u.trecho), ressalva=RESSALVA_PRAZO,
                                        **extra))
        if (peca.tipo in ("recurso", "contrarrazoes") or _RE_RECURSO.search(dobrado)) and listas["recursos"].cabe():
            listas["recursos"].add(m.item(u, nat, peca, i))
        # Linha do tempo: datas de peças e datas de acontecimentos (narrados por
        # uma parte, certificados, designados pelo juiz). Data citada dentro de
        # condenação ou fundamentação ("correção desde 10/01") não é evento.
        assinatura = bool(RE_ASSINATURA.match(u.trecho))
        if assinatura or nat not in ("decisao_judicial", "fundamento_judicial"):
            for iso in datas_em(u.trecho):
                propria = assinatura and nat != "trecho"
                evento = peca.rotulo if propria else _resumo_trecho(u.trecho)
                eventos.append((iso, u.pagina, k, peca, i, u, "ato_processual" if propria else nat, evento, u.trecho))

    # Linha do tempo: ordena tudo, tira repetição e só então cita os primeiros.
    linha_do_tempo: list[dict] = []
    vistos_eventos: set[tuple] = set()
    total_eventos = 0
    for iso, pagina, _k, peca, i, u, nat_evento, evento, texto in sorted(eventos, key=lambda e: (e[0], e[1], e[2])):
        if (iso, pagina, texto) in vistos_eventos:
            continue
        vistos_eventos.add((iso, pagina, texto))
        total_eventos += 1
        if len(linha_do_tempo) < LIMITE_ITENS_POR_CATEGORIA and (it := m.item(u, nat_evento, peca, i, data=iso,
                                                                                evento=evento)):
            linha_do_tempo.append(it)

    transito, transito_nao_confirmado, inconsistencias_transito, total_transito = _transito(
        m, pecas, escolha, ident.principal)

    # --- folhas citadas e não enviadas
    folhas_presentes = {p.folha for p in doc.paginas if p.folha}
    faltantes: dict[str, dict] = {}
    if folhas_presentes:
        for k, (_peca, _, u) in enumerate(por_unidade):
            if relogio.passou(k, u.pagina) or len(faltantes) >= LIMITE_ITENS_POR_CATEGORIA:
                break
            for ref in _RE_REF_FOLHA.findall(u.trecho):
                if ref not in folhas_presentes and ref not in faltantes and len(faltantes) < LIMITE_ITENS_POR_CATEGORIA:
                    if citacao := m.citacao(u):
                        faltantes[ref] = {"folha": ref, "citacoes": [citacao]}

    inconsistencias = (inconsistencias_transito + _inconsistencias(doc, m, finais, rotuladas, ident.valores))[
        :LIMITE_INCONSISTENCIAS]
    contagens = {c: {"total": listas[c].total, "exibidos": len(listas[c].itens)} for c in categorias}
    contagens["linha_do_tempo"] = {"total": total_eventos, "exibidos": len(linha_do_tempo)}
    contagens["partes"] = {"total": total_partes, "exibidos": len(partes)}
    contagens["pecas"] = {"total": total_pecas, "exibidos": len(pecas_saida)}
    contagens["numeros_processo"] = {"total": ident.total_numeros, "exibidos": len(ident.numeros)}
    contagens["transito_em_julgado"] = {"total": total_transito,
                                        "exibidos": len(transito) + len(transito_nao_confirmado)}
    tem_decisao_final = vale is not None
    analise: dict[str, Any] = {
        "documento": {
            "nome": doc.nome,
            "hash_sha256": doc.hash_sha256,
            "total_paginas": doc.total_paginas,
            "paginas_lidas": doc.paginas_por_estado("lida"),
            "paginas_sem_texto": doc.paginas_por_estado("sem_texto"),
            "paginas_possivelmente_digitalizadas": doc.paginas_por_estado("possivelmente_digitalizada"),
            "paginas_baixa_qualidade": doc.paginas_por_estado("baixa_qualidade"),
            "paginas_com_falha": doc.paginas_por_estado("falha"),
            "paginas_nao_processadas": doc.paginas_por_estado("nao_processada"),
            "paginas_truncadas": [p.numero for p in doc.paginas if p.truncada],
            "leitura_completa": doc.leitura_completa,
            "analise_completa": relogio.parou_na_pagina is None,
            "folhas": {str(p.numero): p.folha for p in doc.paginas if p.folha},
        },
        "avisos": list(doc.avisos),
        "numeros_processo": list(ident.numeros.values()),
        "identificacao": ident.rotulos,
        "partes": partes,
        "pecas": pecas_saida,
        "linha_do_tempo": linha_do_tempo,
        **{c: listas[c].itens for c in categorias},
        "decisao_principal": _decisao_principal(m, escolha, finais),
        "decisoes_nao_usadas": _decisoes_nao_usadas(m, finais),
        "transito_em_julgado": transito,
        "transito_nao_confirmado": transito_nao_confirmado,
        "inconsistencias": inconsistencias,
        "folhas_citadas_nao_enviadas": list(faltantes.values()),
        "contagens": contagens,
        "glossario": termos_presentes([(p.numero, p.texto) for p in doc.paginas if p.tem_texto]),
        "naturezas": NATUREZAS,
    }
    analise["avisos"] += _avisos_de_segmentacao(pecas, recusas)
    if relogio.parou_na_pagina is not None:
        analise["avisos"].append(
            f"A análise passou do limite de tempo ({orcamento_s:g} s) e parou na página {relogio.parou_na_pagina}: "
            "o que vem depois não entrou nas listas de partes, alegações, decisões, prazos e linha do tempo."
        )
    cortadas = [c for c, v in contagens.items() if v["total"] > v["exibidos"]]
    if cortadas and relogio.parou_na_pagina is None:
        analise["avisos"].append(
            "Algumas listas foram limitadas para caber na tela: "
            + ", ".join(f"{c.replace('_', ' ')} ({contagens[c]['exibidos']} de {contagens[c]['total']})" for c in cortadas)
            + ". Use as perguntas para buscar trechos específicos."
        )
    if ident.total_numeros > 1:
        analise["avisos"].append(
            "O documento cita mais de um número de processo. Pode haver processos relacionados ou "
            "documentos de processos diferentes no mesmo arquivo."
        )
    if any(not n["digito_verificador_valido"] for n in ident.numeros.values()):
        analise["avisos"].append(
            "Um número de processo encontrado não passa na conferência do dígito verificador "
            "(Resolução CNJ nº 65/2008): pode haver erro de digitação ou de leitura."
        )
    if not pecas_saida:
        analise["avisos"].append(
            "Não reconheci títulos de peças processuais (petição, sentença, certidão…). Os trechos "
            "aparecem sem natureza presumida: não dá para saber se são alegação, fato ou decisão."
        )
    analise["pendencias"] = _pendencias(analise, tem_decisao_final)
    analise["resumo"] = _resumo(analise, m, finais, escolha)
    analise["proximos_passos"] = _proximos_passos(analise, tem_decisao_final)
    analise["perguntas_para_advogado"] = _perguntas(analise, tem_decisao_final)
    analise["controle"] = {"citacoes_descartadas": m.descartadas}
    return analise


def _final_como_dict(m: _Montador, f: _Final) -> dict:
    return {
        "tipo": f.peca.tipo,
        "rotulo": f.peca.rotulo,
        "pagina": f.peca.pagina_inicial,
        "data": f.data if f.data_confiavel else None,
        "resultado": f.resultado.resultado if f.resultado else None,
        "consequencia": f.resultado.consequencia if f.resultado else None,
        "sobre_embargos": f.embargos,
        "texto": _texto_do_item(f.principal.trecho) if f.principal else None,
        "citacoes": _citacao_do_final(m, f),
    }


def _decisao_principal(m: _Montador, escolha: _Escolha, finais: list[_Final]) -> dict | None:
    vale = escolha.final
    if vale is None:
        return None
    resultado = vale.resultado
    return {
        "tipo": vale.peca.tipo,
        "rotulo": vale.peca.rotulo,
        "pagina": vale.peca.pagina_inicial,
        # Data inferida do corpo (a primeira data citada) não é apresentada como data da decisão.
        "data": vale.data if vale.data_confiavel else None,
        "data_confirmada": vale.data_confiavel,
        "instancia": _instancia(vale.peca, resultado),
        # Incerta: o leitor não afirma resultado nenhum; o da peça escolhida fica em `resultado_da_peca`.
        "resultado": None if escolha.incerta else (resultado.resultado if resultado else None),
        "resultado_da_peca": resultado.resultado if resultado else None,
        "consequencia": None if escolha.incerta else (resultado.consequencia if resultado else None),
        "sobre_embargos": vale.embargos,
        "texto": _texto_do_item(vale.principal.trecho) if vale.principal else None,
        "criterio": escolha.criterio,
        "incerta": escolha.incerta,
        "motivo_incerteza": escolha.motivo or None,
        "decisoes_envolvidas": [_final_como_dict(m, f) for f in escolha.envolvidas],
        "decisoes_finais": len([f for f in finais if f.conta]),
        "natureza": "interpretacao",
        "citacoes": _citacao_do_final(m, vale),
    }


def _pendencia(texto: str, citacoes: list[dict] | None = None, nat: str = "nao_localizado") -> dict:
    return {"texto": texto, "natureza": nat, "citacoes": citacoes or []}


def _nao_usadas_em_texto(a: dict) -> str:
    """Frase sobre as decisões que existem mas não decidem a causa (agravo, cumprimento, não confirmadas)."""
    partes = []
    for d in a.get("decisoes_nao_usadas", [])[:3]:
        resultado = f", {d['resultado'].upper()}" if d.get("resultado") else ""
        partes.append(f"{_ARTIGO.get(d['tipo'], 'a')} {d['rotulo'].lower()} da p. {d['pagina']}{resultado}, que {d['motivo']}")
    return ("Há " + "; ".join(partes) + ".") if partes else ""


def _pendencias(a: dict, tem_decisao_final: bool) -> list[dict]:
    """Em ordem de importância: o resumo mostra só as primeiras."""
    saida = []
    dp = a["decisao_principal"]
    if not tem_decisao_final:
        nota = _nao_usadas_em_texto(a)
        saida.append(_pendencia(
            "Não localizei sentença nem acórdão: o processo pode não ter sido julgado ainda, ou a "
            "decisão não está entre os documentos enviados." + (f" {nota}" if nota else ""),
            [c for d in a.get("decisoes_nao_usadas", [])[:3] for c in d["citacoes"]]
        ))
    elif dp and dp.get("incerta"):
        saida.append(_pendencia(
            f"Não consegui determinar com segurança o resultado final: {dp['motivo_incerteza']}. Não escolhi um "
            "resultado: leia os trechos citados e confirme no processo original qual decisão vale.",
            [c for d in dp.get("decisoes_envolvidas", []) for c in d["citacoes"]] or dp["citacoes"]))
    elif dp and not dp["resultado"]:
        saida.append(_pendencia(
            f"Localizei {_ARTIGO.get(dp['tipo'], 'a')} {dp['rotulo'].lower()} da p. {dp['pagina']}, mas não consegui "
            "identificar o resultado no texto. Leia o dispositivo: ele pode ter mudado decisões anteriores.",
            dp["citacoes"]))
    if tem_decisao_final and not a["transito_em_julgado"]:
        saida.append(_pendencia(
            "Não localizei certidão de trânsito em julgado. Pelo que foi enviado, não dá para afirmar "
            "que a decisão é definitiva: ela pode ainda estar sujeita a recurso."
        ))
    for aviso in a["avisos"]:
        saida.append(_pendencia(aviso))
    for inconsistencia in a["inconsistencias"]:
        saida.append(_pendencia(inconsistencia["texto"], inconsistencia["citacoes"], "inconsistencia"))
    if faltas := a["folhas_citadas_nao_enviadas"]:
        folhas = sorted({int(f["folha"]) for f in faltas})
        saida.append(_pendencia(
            f"O processo menciona {'a fl.' if len(folhas) == 1 else 'as fls.'} {faixas(folhas)}, que não "
            f"{'está' if len(folhas) == 1 else 'estão'} no arquivo enviado.",
            [c for f in faltas[:10] for c in f["citacoes"]]))
    if not a["numeros_processo"]:
        saida.append(_pendencia("Não localizei o número do processo."))
    if not a["partes"]:
        saida.append(_pendencia("Não identifiquei as partes do processo."))
    return saida


def _cit(itens: list[dict]) -> list[dict]:
    return [c for it in itens for c in it["citacoes"]]


def _resumo(a: dict, m: _Montador, finais: list[_Final], escolha: _Escolha) -> list[dict]:
    """Resumo executivo por regras. Cada frase cita de onde saiu; o que falta é dito."""
    frases: list[dict] = []
    vale = escolha.final

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
        # Data de peça do juízo só quando confirmada (linha de local e data, data do julgamento ou do
        # termo): a primeira data do corpo costuma ser a de um fato narrado.
        lista = ", ".join(
            f"{p['rotulo'].lower()}{' (não confirmada)' if p.get('nao_confirmada') else ''} (p. {p['pagina_inicial']}"
            f"{', ' + data_br(p['data']) if p['data'] and (p.get('data_confirmada', True) or p['origem'] != 'juizo') else ''})"
            for p in a["pecas"][:15]
        )
        resto = f" e mais {len(a['pecas']) - 15}" if len(a["pecas"]) > 15 else ""
        frase(f"Peças identificadas, na ordem do arquivo: {lista}{resto}.", [])
    dp = a["decisao_principal"]
    if dp and dp.get("incerta"):
        pass  # a 1ª pendência (sempre no resumo) diz que não dá para determinar o resultado, e por quê
    elif dp and dp["resultado"]:
        artigo = _ARTIGO.get(dp["tipo"], "a")
        quando = f", {data_br(dp['data'])}" if dp["data"] else ""
        depois = f" (pelo trecho, para julgar {dp['consequencia'].upper()})" if dp.get("consequencia") else ""
        frase(f"Resultado d{artigo} {dp['rotulo'].lower()} ({dp['instancia']}{quando}): {dp['resultado'].upper()}"
              f"{depois} — «{_resumo_trecho(dp['texto'] or '', 200)}»", dp["citacoes"])
        if dp.get("sobre_embargos") and vale is not None:
            anterior = next((f for f in reversed(finais) if f.conta and f.ordem < vale.ordem), None)
            frase("Essa decisão julgou embargos de declaração"
                  + (f" contra {_rotulo_final(anterior)}" if anterior else "")
                  + " e, pelo trecho, mudou o resultado. Confira no original.",
                  _citacao_do_final(m, anterior) if anterior else [])
        dispositivo = [d for d in a["decisoes"] if d["peca_pagina"] == dp["pagina"] and d["texto"] != dp["texto"]]
        # No acórdão, frase com resultado de recurso diferente do "ACORDAM" é voto vencido ou anterior ao
        # julgamento: não é item do dispositivo — é mencionada à parte.
        divergentes = [d for d in dispositivo if (d.get("resultado") or "").startswith("recurso")
                       and d.get("resultado") != dp.get("resultado_da_peca", dp["resultado"])
                       and re.search(r"\bacordam\b", _dobrar(dp["texto"] or ""))]
        dispositivo = [d for d in dispositivo if d not in divergentes]
        if dispositivo:
            frase("Itens do dispositivo: " + " ".join(f"«{_resumo_trecho(d['texto'], 160)}»" for d in dispositivo[:4]),
                  _cit(dispositivo[:4]), "decisao_judicial")
        if divergentes:
            frase(f"{_ARTIGO.get(dp['tipo'], 'a').upper()} {dp['rotulo'].lower()} também traz voto com resultado "
                  f"diferente ({divergentes[0]['resultado'].upper()}), provavelmente voto vencido; o resultado acima é o "
                  "do «ACORDAM» — confira no trecho.", _cit(divergentes[:1]))
    elif dp:
        frase(f"Há {_ARTIGO.get(dp['tipo'], 'a')} {dp['rotulo'].lower()} na p. {dp['pagina']}, mas não identifiquei o "
              "resultado dele(a) no texto — não uso decisões anteriores no lugar.", dp["citacoes"])
    elif a["decisoes"]:
        ultima = a["decisoes"][-1]
        frase(f"Decisão mais recente localizada ({(ultima['peca'] or 'trecho').lower()}): "
              f"«{_resumo_trecho(ultima['texto'], 200)}»", ultima["citacoes"])
    if vale is not None:
        anteriores = [f for f in finais if f is not vale and f.conta and f.resultado]
        if dp and dp["decisoes_finais"] > 1 and not dp.get("incerta"):
            frase(f"Há {dp['decisoes_finais']} decisões finais no arquivo; considerei a que vale pela regra: "
                  f"{dp['criterio']}. As outras podem ter sido modificadas por ela.",
                  [c for f in anteriores[:3] for c in _citacao_do_final(m, f)])
        envolvidas = {id(f) for f in escolha.envolvidas}
        embargos = [f for f in finais if f.embargos and f is not vale and id(f) not in envolvidas and not f.nao_confirmada
                    and f.resultado and f.resultado.resultado]
        for f in embargos[:2]:
            resultado = (f.resultado.resultado or "") if f.resultado else ""
            if "acolhidos" in resultado:
                nota = ("Pelo trecho, os embargos não mudaram o resultado." if f.principal and
                        _RE_SEM_EFEITO_MODIFICATIVO.search(_dobrar(f.principal.trecho)) else
                        "Embargos acolhidos podem ter modificado a decisão: leia o trecho.")
                frase(f"Decisão sobre embargos de declaração (p. {f.peca.pagina_inicial}): {resultado.upper()}. {nota}",
                      _citacao_do_final(m, f))
            else:
                frase(f"Decisão sobre embargos de declaração (p. {f.peca.pagina_inicial}): {resultado.upper()}. "
                      "Ela não é o resultado da causa.", _citacao_do_final(m, f))
    for d in [d for d in a.get("decisoes_nao_usadas", []) if d["colateral"]][:3]:
        resultado = f": {d['resultado'].upper()}" if d.get("resultado") else ""
        frase(f"Decisão sobre {'agravo' if d['colateral'] == 'agravo' else 'a fase de cumprimento'} "
              f"({d['rotulo'].lower()}, p. {d['pagina']}){resultado}. Ela {d['motivo']}.", d["citacoes"])
    if a["transito_em_julgado"]:
        frase("Há certidão de trânsito em julgado: a decisão foi certificada como definitiva.",
              _cit(a["transito_em_julgado"][:1]), "fato_registrado")
    elif negadas := [t for t in a["transito_nao_confirmado"] if "NÃO transitou" in t.get("motivo", "")]:
        frase(f"Uma certidão (p. {negadas[0]['citacoes'][0]['pagina']}) informa que a decisão ainda NÃO tinha "
              "transitado em julgado na data dela.", negadas[0]["citacoes"], "fato_registrado")
    pendencias = a["pendencias"]
    frases.extend(pendencias[:LIMITE_PENDENCIAS_NO_RESUMO])
    if len(pendencias) > LIMITE_PENDENCIAS_NO_RESUMO:
        frase(f"Há mais {len(pendencias) - LIMITE_PENDENCIAS_NO_RESUMO} pendência(s) na lista completa de "
              "pendências.", [], "nao_localizado")
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
    if a["inconsistencias"]:
        passo("O documento tem informações que não batem entre si (veja as pendências). Confira no processo "
              "original, pela consulta processual do tribunal, antes de tirar conclusões.")
    if not tem_decisao_final:
        passo("Acompanhe o andamento pela consulta processual do tribunal, com o número do processo.")
    passo("Leve as perguntas abaixo à Defensoria Pública (gratuita) ou a um advogado.")
    return passos


def _perguntas(a: dict, tem_decisao_final: bool) -> list[str]:
    perguntas = []
    for prazo in [p for p in a["prazos"] if p["tipo_de_prazo"] in PRAZOS_EM_CURSO][:4]:
        c = prazo["citacoes"][0]
        perguntas.append(f"O prazo mencionado na página {c['pagina']} («{prazo['duracao']}») se aplica a mim? "
                         "Quando ele começou e quando termina?")
    if tem_decisao_final and not a["transito_em_julgado"]:
        perguntas.append("A decisão já transitou em julgado ou ainda cabe recurso? Vale a pena recorrer?")
    if any(re.search(r"\bindefiro\b", d["texto"], re.IGNORECASE) for d in a["decisoes"]):
        perguntas.append("Por que um dos pedidos foi indeferido, e essa decisão ainda pode ser revista?")
    if faltas := a["folhas_citadas_nao_enviadas"]:
        folhas = sorted({int(f["folha"]) for f in faltas})
        perguntas.append(f"O que está nas fls. {faixas(folhas, limite=6)}, citadas no processo e ausentes do arquivo?")
    nao_lidas = (a["documento"]["paginas_sem_texto"] + a["documento"].get("paginas_possivelmente_digitalizadas", [])
                 + a["documento"].get("paginas_baixa_qualidade", []))
    if nao_lidas:
        perguntas.append(f"O que dizem as páginas {faixas(nao_lidas, limite=6)}, que não puderam ser lidas "
                         "automaticamente?")
    if a["inconsistencias"]:
        perguntas.append("O documento tem informações que não batem entre si (decisões, datas, nomes ou folhas). "
                         "Qual é a versão correta?")
    perguntas.append("Quais são os próximos passos do processo e o que eu preciso fazer agora?")
    return perguntas
