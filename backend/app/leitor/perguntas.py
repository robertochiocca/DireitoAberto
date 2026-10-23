"""Perguntas sobre o documento enviado, respondidas só com o próprio documento.

As respostas são extrativas: cada item é uma frase do documento, com página
e folha, e a frase de abertura só organiza o que foi encontrado. Quando não
há trecho que sustente uma resposta, o leitor diz que não encontrou — não
completa com conhecimento geral nem com suposição sobre o caso.

As perguntas mais comuns (o que aconteceu, o juiz decidiu, o que a outra
parte alega, quais obrigações, prazos, o que confirmar) são reconhecidas e
respondidas a partir da análise estruturada; as demais caem na busca por
trechos (BM25 sobre as frases do documento).
"""

from __future__ import annotations

import math
import re
from collections import Counter

from ..retrieval import normalizar
from .analise import RESSALVA_PRAZO, data_br
from .extracao import DocumentoExtraido
from .glossario import TERMOS
from .texto import sem_acento, unidades
from .verificacao import citar

# (intenção, padrão sem acento e em minúsculas). A ordem decide empates.
_INTENCOES = [
    ("explicar_decisao", r"(explique|explica|explicar|como se eu|simples|nao entend).*(decis|senten|juiz|acordao)"),
    ("paginas", r"(quais?|em que|que) (paginas?|folhas?)|onde aparece|onde esta"),
    ("prazos", r"\bprazo|ate quando|quantos dias|\bvence\b"),
    ("transito", r"transit|definitiv|coisa julgada|ainda (cabe|da para) recorr|ainda cabe recurso"),
    ("resultado", r"\b(ganhei|perdi|venci|ganhou|perdeu|venceu|ganhamos|perdemos|vencemos|vencedor)\b"
                  r"|ganho de causa|\bresultado\b"),
    ("decisoes", r"\bjuiz|\bjuiza|decis|sentenc|decidi|julg|acordao"),
    ("alegacoes", r"outra parte|\balega|contest|defesa|argument|o que (o|a) (reu|re|autor|autora)"),
    ("obrigacoes", r"obriga|tenho que|preciso (pagar|fazer|cumprir)|\bdevo\b|condena|determin"),
    ("recursos", r"recurso|recorrer|apelar|apelacao"),
    ("partes", r"quem (sao|e)|\bpartes\b"),
    ("pendencias", r"confirmar|pendente|\bfalta|nao foi lid|o que (ainda )?(preciso|devo) (saber|verificar)"),
    ("resumo", r"o que aconteceu|resum|do que se trata|sobre o que|entender o processo"),
]
_PADROES = [(nome, re.compile(p)) for nome, p in _INTENCOES]

# Palavras da pergunta que não dizem o que procurar no documento.
_GENERICAS = set(normalizar(
    "pagina paginas folha folhas aparece aparecem onde esta estao informacao processo documento "
    "texto quais qual que em essa esse isso trecho fala diz falar mencionado mencionada houve teve "
    "existe existiu algum alguma"
))

# Verbo da pergunta → substantivo do processo ("posso recorrer?" × "recurso inominado").
_EQUIVALENTES = {
    "recorrer": ["recurso"], "recorro": ["recurso"], "apelar": ["apelacao", "recurso"],
    "pagar": ["pagamento", "condenar", "condeno"], "contestar": ["contestacao"],
    "citado": ["citacao", "citada"], "citada": ["citacao", "citado"], "intimado": ["intimacao", "intimada"],
    "decidiu": ["decisao", "julgo"], "julgou": ["julgo", "sentenca"], "ganhei": ["procedente"],
    "perdi": ["improcedente"], "acordo": ["conciliacao", "homologo"],
}


def _grupos(pergunta: str) -> list[set[str]]:
    """Cada palavra da pergunta com os seus equivalentes; um grupo casa se qualquer um casar."""
    termos = dict.fromkeys(t for t in normalizar(pergunta) if t not in _GENERICAS)
    return [{t, *_EQUIVALENTES.get(t, [])} for t in termos]


def _termos(pergunta: str) -> set[str]:
    return set().union(*_grupos(pergunta)) if _grupos(pergunta) else set()


_RESULTADOS = {
    "procedente": "o juiz aceitou o pedido principal de quem entrou com a ação.",
    "parcialmente procedente": "o juiz aceitou só uma parte dos pedidos de quem entrou com a ação; "
                               "o resto foi negado.",
    "improcedente": "o juiz negou os pedidos de quem entrou com a ação.",
    "misto": "o juiz decidiu de forma diferente o pedido de quem entrou com a ação e o pedido da outra "
                       "parte (pedido contraposto ou reconvenção); leia o dispositivo para ver o que foi aceito e o "
                       "que foi negado.",
    "extinção do processo": "o processo foi encerrado; é preciso ver no texto se houve decisão sobre "
                            "quem tem razão ou se ele acabou por motivo processual.",
    "homologação de acordo": "o juiz aprovou um acordo entre as partes, que passa a valer como decisão.",
    "recurso provido": "o tribunal aceitou o recurso de quem recorreu: a decisão anterior foi modificada ou "
                       "anulada, no todo ou em parte. Veja no trecho o que mudou.",
    "recurso parcialmente provido": "o tribunal aceitou só uma parte do recurso: parte da decisão anterior mudou e "
                                    "parte ficou como estava.",
    "recurso não provido": "o tribunal negou o recurso: a decisão anterior foi mantida.",
    "recurso não conhecido": "o tribunal não chegou a analisar o pedido do recurso (por exemplo, por falta de um "
                             "requisito formal); confirme com advogado o efeito disso.",
    "embargos de declaração acolhidos": "a decisão aceitou os embargos de declaração e corrigiu ou completou a "
                                        "decisão anterior; veja no trecho o que mudou.",
    "embargos de declaração acolhidos em parte": "a decisão aceitou em parte os embargos de declaração; veja no "
                                                 "trecho o que mudou na decisão anterior.",
}

# Quem "ganhou" depende do papel de quem pergunta, e o documento não diz quem pergunta.
_PAPEL = {
    "recurso": "Recurso provido favorece quem recorreu; recurso não provido favorece a outra parte. Veja no trecho "
               "quem recorreu.",
    "causa": "Procedente favorece quem entrou com a ação naquilo que foi aceito; improcedente favorece a parte "
             "processada.",
}

AVISO_GERAL = (
    "Respostas montadas só com trechos do documento enviado. Isto é informação, não aconselhamento: "
    "confirme com advogado ou com a Defensoria Pública antes de decidir qualquer coisa."
)


def classificar(pergunta: str) -> str:
    texto = sem_acento(pergunta.lower())
    for nome, padrao in _PADROES:
        if padrao.search(texto):
            return nome
    return "busca"


def _resposta(intencao: str, texto: str, itens: list[dict], abstencao: bool = False, **extra) -> dict:
    return {"intencao": intencao, "resposta": texto, "itens": itens, "abstencao": abstencao, **extra}


def _pela_pergunta(itens: list[dict], pergunta: str) -> list[dict]:
    """Mesma lista, com os itens que mais compartilham palavras com a pergunta primeiro."""
    termos = _termos(pergunta)
    if not termos:
        return itens
    return sorted(itens, key=lambda it: -len(termos & set(normalizar(it["texto"]))))


# ---------------------------------------------------------------- busca por trechos
def buscar_trechos(doc: DocumentoExtraido, pergunta: str, limite: int = 5) -> list[dict]:
    """BM25 sobre as frases do documento; só devolve frases que casam o suficiente."""
    grupos = _grupos(pergunta)
    if not grupos:
        return []
    lista = unidades(doc)  # títulos entram: "TERMO DE AUDIÊNCIA" diz onde está a audiência
    tokens = [normalizar(u.trecho) for u in lista]
    if not lista:
        return []
    media = sum(map(len, tokens)) / len(tokens) or 1
    df = Counter(t for toks in tokens for t in set(toks))
    n = len(lista)
    resultados = []
    for u, toks in zip(lista, tokens, strict=True):
        freq = Counter(toks)
        casados = {t for grupo in grupos for t in grupo if t in freq}
        grupos_casados = sum(1 for grupo in grupos if grupo & casados)
        # Exige casar a maior parte do que foi perguntado: uma palavra solta
        # em comum não é resposta.
        if grupos_casados < max(1, math.ceil(len(grupos) * 0.5)):
            continue
        nota = sum(
            math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            * freq[t] * 2.5 / (freq[t] + 1.5 * (0.25 + 0.75 * len(toks) / media))
            for t in casados
        )
        resultados.append((nota, u))
    resultados.sort(key=lambda r: -r[0])
    saida = []
    for _, u in resultados[:limite]:
        citacao = citar(doc, u.pagina, u.trecho)
        if citacao.verificada:
            saida.append({"texto": u.trecho, "natureza": "trecho", "citacoes": [citacao.como_dict()]})
    return saida


# ---------------------------------------------------------------- respostas
def _sem_resultado(intencao: str, o_que: str) -> dict:
    return _resposta(
        intencao,
        f"Não localizei {o_que} no documento enviado. Isso não quer dizer que não exista: a peça pode "
        "não estar no arquivo ou estar numa página que não pôde ser lida.",
        [],
        abstencao=True,
    )


def _decisao_principal(a: dict) -> dict | None:
    """A decisão que vale, como a análise escolheu. Análises guardadas pela versão anterior
    (sem `decisao_principal`) usam a regra antiga: a última sentença ou acórdão do arquivo."""
    if "decisao_principal" in a:
        return a["decisao_principal"]
    finais = [p for p in a["pecas"] if p["tipo"] in ("sentenca", "acordao")]
    if not finais:
        return None
    ultima = finais[-1]
    d = next((d for d in a["decisoes"] if d["peca_pagina"] == ultima["pagina_inicial"] and d.get("resultado")), None)
    return {"tipo": ultima["tipo"], "rotulo": ultima["rotulo"], "pagina": ultima["pagina_inicial"],
            "data": ultima["data"], "instancia": d["instancia"] if d else "", "resultado": d["resultado"] if d else None,
            "consequencia": None, "texto": d["texto"] if d else None, "citacoes": d["citacoes"] if d else [],
            "criterio": "", "decisoes_finais": len(finais), "incerta": False}


def _dispositivo(a: dict, dp: dict) -> list[dict]:
    return [d for d in a["decisoes"] if d["peca_pagina"] == dp["pagina"]]


def _descricao(dp: dict) -> str:
    """"o acórdão de 20/09/2026 (tribunal (colegiado)), com resultado RECURSO PROVIDO"."""
    artigo = "o" if dp["tipo"] == "acordao" else "a"
    quando = f" de {data_br(dp['data'])}" if dp.get("data") else ""
    depois = f" (pelo trecho, para julgar {dp['consequencia'].upper()})" if dp.get("consequencia") else ""
    return f"{artigo} {dp['rotulo'].lower()}{quando}, com resultado {dp['resultado'].upper()}{depois}"


def _artigo(tipo: str) -> str:
    return "o" if tipo == "acordao" else "a"


def _incerta(a: dict, dp: dict, intencao: str, abertura: str = "") -> dict:
    """O arquivo não permite afirmar o resultado final: diz por quê e mostra as decisões, sem escolher."""
    envolvidas = dp.get("decisoes_envolvidas") or []
    itens = [{"texto": d["texto"], "natureza": "decisao_judicial", "peca": d["rotulo"], "citacoes": d["citacoes"]}
             for d in envolvidas if d.get("texto") and d.get("citacoes")]
    texto = (f"{abertura}Não consegui determinar com segurança qual é o resultado final: {dp['motivo_incerteza']}. "
             "Não escolhi um resultado: leia os trechos abaixo e confirme no processo original (ou com advogado ou "
             f"a Defensoria Pública) qual decisão vale.{_nota_nao_usadas(a)}{_nota_transito(a)}")
    return _resposta(intencao, texto, itens or _dispositivo(a, dp))


def _nota_nao_usadas(a: dict) -> str:
    """Decisões que existem mas não decidem a causa (agravo, cumprimento) ou não puderam ser confirmadas."""
    notas = []
    for d in a.get("decisoes_nao_usadas", [])[:3]:
        if d.get("nao_confirmada"):
            notas.append(f"{_artigo(d['tipo'])} {d['rotulo'].lower()} da p. {d['pagina']} não foi considerada: "
                         f"{d['motivo']}")
        else:
            resultado = f" ({d['resultado'].upper()})" if d.get("resultado") else ""
            notas.append(f"{_artigo(d['tipo'])} {d['rotulo'].lower()} da p. {d['pagina']}{resultado} {d['motivo']}")
    return (" Atenção: " + "; ".join(notas) + ".") if notas else ""


def _nota_inconsistencia(a: dict) -> str:
    if any(i.get("tipo") == "decisoes_finais_divergentes" for i in a.get("inconsistencias", [])):
        return (" Atenção: o arquivo tem decisões finais com resultados diferentes — confira qual vale (veja as "
                "pendências).")
    return ""


def _nota_transito(a: dict) -> str:
    if a["transito_em_julgado"]:
        return " Há certidão de trânsito em julgado: a decisão foi certificada como definitiva."
    return (" Não localizei certidão de trânsito em julgado: pelo que foi enviado, a decisão ainda pode "
            "ser alterada por recurso.")


def responder(doc: DocumentoExtraido, a: dict, pergunta: str) -> dict:
    intencao = classificar(pergunta)
    resposta = _responder(doc, a, pergunta, intencao)
    avisos = list(a["avisos"])
    if a["documento"].get("analise_completa") is False:
        avisos.insert(0, "A análise do documento parou antes do fim (limite de tempo): a resposta pode estar "
                         "faltando informação.")
    if not a["documento"]["leitura_completa"]:
        avisos.insert(0, "A leitura do documento não foi completa: a resposta pode estar faltando "
                         "informação das páginas não lidas.")
    return {"pergunta": pergunta, **resposta, "avisos": avisos, "aviso_geral": AVISO_GERAL}


def _responder(doc: DocumentoExtraido, a: dict, pergunta: str, intencao: str) -> dict:
    if intencao == "resumo":
        itens = [f for f in a["resumo"] if f["natureza"] != "nao_localizado"]
        return _resposta(intencao, "Resumo do que o documento mostra, com a página de cada informação:",
                         itens + a["linha_do_tempo"][-6:])

    if intencao == "transito":
        if a["transito_em_julgado"]:
            pagina = a["transito_em_julgado"][0]["citacoes"][0]["pagina"]
            return _resposta(intencao, f"Há certidão de trânsito em julgado (p. {pagina}): a decisão foi certificada "
                                       "como definitiva.", a["transito_em_julgado"])
        nao_confirmadas = a.get("transito_nao_confirmado", [])
        texto = ("Não localizei certidão de trânsito em julgado que possa ser confirmada: pelo que foi enviado, não dá "
                 "para afirmar que a decisão é definitiva; ela pode ainda estar sujeita a recurso.")
        if nao_confirmadas:
            texto += f" Há menção a trânsito em julgado que não confirmei: {nao_confirmadas[0]['motivo']}."
        return _resposta(intencao, texto, nao_confirmadas, abstencao=not nao_confirmadas)

    if intencao == "resultado":
        dp = _decisao_principal(a)
        if dp is None:
            resposta = _sem_resultado(intencao, "sentença nem acórdão com o resultado do processo")
            resposta["resposta"] += _nota_nao_usadas(a)
            return resposta
        artigo = "o" if dp["tipo"] == "acordao" else "a"
        if dp.get("incerta"):
            return _incerta(a, dp, intencao)
        if not dp["resultado"]:
            return _resposta(intencao, f"Localizei {artigo} {dp['rotulo'].lower()} da p. {dp['pagina']}, mas não "
                                       "consegui identificar o resultado no texto. Leia o dispositivo — decisões "
                                       "anteriores podem ter sido modificadas por ela.", _dispositivo(a, dp))
        papel = _PAPEL["recurso" if dp["resultado"].startswith("recurso") else "causa"]
        texto = (f"O resultado localizado é {_descricao(dp)}: {_RESULTADOS.get(dp['resultado'], '')} Quem "
                 f"\"ganhou\" depende de qual parte você é, e o documento não diz isso. {papel}"
                 f"{_nota_inconsistencia(a)}{_nota_nao_usadas(a)}{_nota_transito(a)}")
        return _resposta(intencao, texto, _dispositivo(a, dp))

    if intencao in ("decisoes", "explicar_decisao"):
        if not a["decisoes"]:
            return _sem_resultado(intencao, "decisão do juiz (sentença, decisão ou acórdão)")
        dp = _decisao_principal(a)
        if dp and dp.get("incerta"):
            abertura = "" if intencao == "explicar_decisao" else f"Localizei {len(a['decisoes'])} trecho(s) de decisão do juiz. "
            return _incerta(a, dp, intencao, abertura)
        dispositivo = _dispositivo(a, dp) if dp else []
        if intencao == "explicar_decisao" and dp and dp["resultado"]:
            explicacao = _RESULTADOS.get(dp["resultado"], "")
            glossario = [
                {"termo": termo, "explicacao": explicacao_termo}
                for termo, (padrao, explicacao_termo) in TERMOS.items()
                if any(re.search(padrao, sem_acento(d["texto"]), re.IGNORECASE) for d in dispositivo)
            ]
            texto = (f"Em palavras simples: {_descricao(dp)} — {explicacao}{_nota_inconsistencia(a)}"
                     f"{_nota_nao_usadas(a)}{_nota_transito(a)}")
            return _resposta(intencao, texto, dispositivo, glossario=glossario)
        texto = f"Localizei {len(a['decisoes'])} trecho(s) de decisão do juiz."
        if dp and dp["resultado"]:
            texto += f" A decisão final que vale, pelo arquivo, é {_descricao(dp)}.{_nota_inconsistencia(a)}" \
                     f"{_nota_nao_usadas(a)}{_nota_transito(a)}"
        elif not dp:
            texto += _nota_nao_usadas(a)
        elif dp:
            texto += (f" Há {'o' if dp['tipo'] == 'acordao' else 'a'} {dp['rotulo'].lower()} da p. {dp['pagina']}, mas "
                      "não identifiquei o resultado no texto.")
        return _resposta(intencao, texto, a["decisoes"])

    if intencao == "alegacoes":
        if not a["alegacoes"]:
            return _sem_resultado(intencao, "alegações das partes")
        por_peca: dict[str, int] = {}
        for it in a["alegacoes"]:
            por_peca[it["peca"]] = por_peca.get(it["peca"], 0) + 1
        resumo = ", ".join(f"{n} na {peca.lower()}" for peca, n in por_peca.items())
        return _resposta(intencao, f"Alegações encontradas ({resumo}). Alegação é a versão de uma parte, "
                                   "não um fato comprovado.", _pela_pergunta(a["alegacoes"], pergunta))

    if intencao == "obrigacoes":
        if not a["obrigacoes_e_determinacoes"]:
            return _sem_resultado(intencao, "obrigação ou determinação do juiz")
        return _resposta(intencao, "Obrigações e determinações que aparecem em atos do juiz e em certidões:",
                         _pela_pergunta(a["obrigacoes_e_determinacoes"], pergunta))

    if intencao == "prazos":
        if not a["prazos"]:
            return _sem_resultado(intencao, "menção a prazo")
        return _resposta(intencao, "Prazos mencionados no documento — nenhum foi calculado. " + RESSALVA_PRAZO,
                         _pela_pergunta(a["prazos"], pergunta))

    if intencao == "recursos":
        if not a["recursos"]:
            return _sem_resultado(intencao, "recurso ou menção a recurso")
        return _resposta(intencao, f"Menções a recurso no documento.{_nota_transito(a)}", a["recursos"])

    if intencao == "partes":
        if not a["partes"]:
            return _sem_resultado(intencao, "a identificação das partes")
        return _resposta(intencao, "Partes identificadas no documento:", a["partes"])

    if intencao == "pendencias":
        return _resposta(intencao, "O que ainda precisa ser confirmado. Abaixo, perguntas para levar a "
                                   "advogado ou à Defensoria Pública.",
                         a["pendencias"], perguntas=a["perguntas_para_advogado"])

    trechos = buscar_trechos(doc, pergunta)
    if not trechos:
        if intencao == "paginas":
            return _resposta(intencao, "Diga qual informação você procura (por exemplo: \"em quais páginas "
                                       "aparece a audiência?\"). Toda resposta já traz a página de cada trecho.",
                             [], abstencao=True)
        return _sem_resultado(intencao, "trecho que responda a essa pergunta")
    paginas = sorted({c["pagina"] for t in trechos for c in t["citacoes"]})
    return _resposta(intencao, f"Trechos do documento relacionados à pergunta (páginas "
                               f"{', '.join(map(str, paginas))}):", trechos)
