"""Proveniência de cada dispositivo do corpus: texto oficial, natureza do texto curado, lacunas.

Quatro naturezas de texto, que a API e as interfaces nunca confundem:

- **literal** — transcrição conferida com a publicação oficial do ato (o DOU). O corpus ainda não tem
  nenhuma: a fonte conferida é a página do Planalto, que é texto atualizado pela Casa Civil;
- **consolidado** — a redação resultante das alterações, transcrita da página oficial e conferida com
  ela na data da coleta. É o que os trechos oficiais (`trechos_oficiais`) guardam;
- **resumo_explicativo** — simplificação redigida pelo projeto;
- **interpretacao_juridica** — texto que incorpora entendimento de tribunal ou análise jurídica.

O campo `texto` de cada entrada (o que a busca indexa) recebe uma dessas naturezas — ou
`nao_conferido`, quando não há texto oficial para comparar. Só ganha "consolidado" o texto que cobre o
trecho oficial palavra por palavra (98% das sequências de 8 palavras, a mesma medida de
`monitor/fidelidade.py`). O resto nunca é apresentado como transcrição.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from ..monitor.artigos import dividir
from ..monitor.fidelidade import cobertura
from ..monitor.impacto import normalizar_url
from ..monitor.registro import Registro
from .dispositivos import (
    DispositivoAmbiguo,
    DispositivoNaoEncontrado,
    Ref,
    enunciado_do_caput,
    enunciado_do_paragrafo,
    interpretar_rotulo,
    limpar,
    localizar,
    normalizar_pontuacao,
    repeticoes,
)

NATUREZAS = {
    "literal": "Texto oficial literal — transcrição conferida com a publicação oficial",
    "consolidado": "Texto consolidado — redação atualizada, transcrita da fonte oficial na data indicada",
    "resumo_explicativo": "Resumo explicativo redigido pelo DireitoAberto — não é transcrição da lei",
    "interpretacao_juridica": "Interpretação jurídica — inclui entendimento de tribunal ou análise, sujeita a contexto",
    "nao_conferido": "Texto não conferido com a fonte oficial — pode ser transcrição ou síntese",
}
LIMIAR_TRANSCRICAO = 0.98
METODO = "extração automática do snapshot do monitor (texto vigente da página, sem a redação tachada)"

# Texto curado que traz entendimento de tribunal ou de órgão regulador, além da letra da lei.
_INTERPRETACAO = re.compile(
    r"\b(?:STF|STJ|TST|Supremo|Superior Tribunal|S[úu]mula|Tema\s+\d|ADI|ADPF|ADC|RE\s+\d|"
    r"interpreta[çc][ãa]o|entendimento|jurisprud[êe]ncia|Resolu[çc][ãa]o|decidiu|declarou|"
    r"ANS|ANAC|ANATEL|ANEEL|BCB|Banco Central|CNJ|RN\s*\d|Portaria|Instru[çc][ãa]o\s+Normativa)\b"
)
_ALTERACAO = re.compile(
    r"\((?P<tipo>Reda[çc][ãa]o\s+dada|Inclu[íi]d[oa]|Acrescid[oa]|Acrescentad[oa]|Revogad[oa]|Renumerad[oa]|Vide)"
    r"\s*(?:pel[oa]s?|Pel[oa])?\s*(?P<ato>[^()]*?(?:n[ºo°]\s*[\d.]+[^()]*?)?)\)",
    re.IGNORECASE,
)
_TIPOS_DE_RELACAO = {
    "redacao dada": "redacao_dada_por", "incluido": "incluido_por", "incluida": "incluido_por",
    "acrescido": "incluido_por", "acrescida": "incluido_por", "acrescentado": "incluido_por",
    "acrescentada": "incluido_por", "revogado": "revogado_por", "revogada": "revogado_por",
    "renumerado": "renumerado_por", "renumerada": "renumerado_por", "vide": "vide",
}


def sha256(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _sem_acento(texto: str) -> str:
    from ..leitor.texto import sem_acento

    return sem_acento(texto)


def relacoes(anotacoes: list[str]) -> list[dict]:
    """Relações de alteração que a própria página anota ("(Redação dada pela Lei nº 13.484, de 2017)")."""
    saida: list[dict] = []
    for anotacao in anotacoes:
        m = _ALTERACAO.match(anotacao)
        if not m:
            continue
        tipo = _TIPOS_DE_RELACAO.get(" ".join(_sem_acento(m.group("tipo").lower()).split()))
        ato = " ".join(m.group("ato").split()).strip(" ,.")
        if tipo and ato and (item := {"tipo": tipo, "ato": ato}) not in saida:
            saida.append(item)
    return saida


def corpo_principal(texto: str, fonte: dict) -> str:
    """O trecho da página que é o texto da norma, quando a fonte declara onde ele começa ou termina.

    A página da Constituição traz o ADCT depois do texto permanente, e a da CLT começa pelo decreto-lei
    que a aprova — os dois com numeração de artigos própria. Sem a delimitação, "art. 6º" seria ambíguo.
    """
    regra = fonte.get("corpo_principal") or {}
    plano = " ".join(texto.split())
    if (inicio := regra.get("comeca_em")) and (i := plano.find(inicio)) >= 0:
        plano = plano[i:]
    if (fim := regra.get("termina_em")) and (j := plano.find(fim)) >= 0:
        plano = plano[:j]
    return plano


class Fontes:
    """Snapshots aceitos do monitor, divididos em artigos (com cache por fonte), e as normas sem coleta."""

    def __init__(self, registro: Registro, sem_coleta: list[dict] | None = None):
        self.registro = registro
        self.sem_coleta = {normalizar_url(n["fonte_oficial"]): n for n in sem_coleta or []}
        self.por_url = {normalizar_url(f["url"]): f for f in registro.fontes()}
        self.por_id = {f["id"]: f for f in registro.fontes()}
        self._cache: dict[tuple[str, str], dict[str, str]] = {}

    def da_url(self, url: str) -> dict | None:
        return self.por_url.get(normalizar_url(url or ""))

    def artigos_da_versao(self, fonte_id: str, versao: str) -> dict[str, str]:
        if (fonte_id, versao) not in self._cache:
            texto = self.registro.ler_snapshot(fonte_id, versao)
            self._cache[(fonte_id, versao)] = dividir(corpo_principal(texto, self.por_id[fonte_id]))
        return self._cache[(fonte_id, versao)]

    def artigos(self, fonte_id: str) -> tuple[dict, dict[str, str]] | None:
        versao = self.registro.versao_aceita(fonte_id)
        if versao is None:
            return None
        return versao, self.artigos_da_versao(fonte_id, versao["versao"])


# Artigo de outra lei transcrito na página porque esta norma o altera ("Art. 48. Caberão embargos … (NR)").
_CITACAO_DE_OUTRA_LEI = re.compile(r"\(NR\)|\.{6,}|”")


def _escolher(artigos: dict[str, str], chave: str) -> tuple[str | None, str | None, str | None]:
    """(texto, alerta, lacuna) do artigo na página.

    Mais de uma ocorrência do mesmo número:
    - em sequência ("Art. 12. … Art. 12. … (Redação dada …)") é a redação antiga sem tachado ao lado da
      nova: não se escolhe;
    - em lugares distantes, a que não é transcrição de outra lei alterada pela norma é o texto principal.
    """
    chaves = list(artigos)
    posicoes = [i for i, k in enumerate(chaves) if k.split("#")[0] == chave]
    if not posicoes:
        return None, None, "artigo não encontrado na página oficial"
    if len(posicoes) == 1:
        return artigos[chaves[posicoes[0]]], None, None
    if any(b - a == 1 for a, b in zip(posicoes, posicoes[1:], strict=False)):
        return None, None, (f"o artigo aparece {len(posicoes)} vezes em sequência na página oficial (redação antiga "
                            "sem tachado ao lado da nova?) — trecho não extraído; exige revisão humana")
    proprios = [i for i in posicoes if not _CITACAO_DE_OUTRA_LEI.search(artigos[chaves[i]])]
    if len(proprios) == 1:
        return (artigos[chaves[proprios[0]]],
                "o mesmo número aparece na página em artigo de outra lei transcrito (alteração feita por esta "
                "norma); usado o do texto principal", None)
    return None, None, (f"o artigo aparece {len(posicoes)} vezes na página oficial — trecho não extraído; "
                        "exige revisão humana")


def _trecho(ref: Ref, artigos: dict[str, str], fonte: dict, versao: dict, hoje: date) -> tuple[dict | None, str | None]:
    texto_artigo, alerta, lacuna = _escolher(artigos, ref.artigo)
    if texto_artigo is None:
        return None, f"{ref.rotulo()}: {lacuna}"
    alertas = [alerta] if alerta else []
    try:
        bruto = localizar(texto_artigo, ref)
    except (DispositivoNaoEncontrado, DispositivoAmbiguo) as exc:
        return None, f"{exc} — trecho não extraído; exige revisão humana"
    if repetidos := repeticoes(bruto):
        return None, (f"{ref.rotulo()}: dispositivos repetidos no trecho ({', '.join(repetidos)}) — redação antiga "
                      "sem tachado? Trecho não extraído; exige revisão humana")
    limpo = limpar(bruto)
    trecho: dict[str, Any] = {
        "dispositivo": ref.rotulo(),
        "ref": ref.como_dict(),
        "tipo": "consolidado",
        "texto": limpo.texto,
        "hash_sha256": sha256(limpo.texto),
        "fonte": fonte["url"],
        "fonte_id": fonte["id"],
        "versao_fonte": versao["versao"],
        "hash_fonte": versao["hash_sha256"],
        "coletado_em": versao["capturada_em"],
        "conferido_em": hoje.isoformat(),
        "metodo": METODO,
        "anotacoes": limpo.anotacoes,
        "relacoes": relacoes(limpo.anotacoes),
        **({"descartado": limpo.descartado} if limpo.descartado else {}),
        "revisao_humana": None,
    }
    if ref.inciso:
        # Inciso sozinho não se entende sem o enunciado: o do caput ("São direitos dos trabalhadores…:") e,
        # se o inciso é de um parágrafo, também o do parágrafo ("§ 3º Em três anos:").
        contexto = limpar(enunciado_do_caput(texto_artigo)).texto
        if ref.paragrafo not in (None, "caput"):
            contexto += " […] " + limpar(enunciado_do_paragrafo(texto_artigo, ref.paragrafo)).texto
        trecho["contexto"] = contexto
    if alertas:
        trecho["alertas"] = alertas
    return trecho, None


_NUMERO_DE_LEI = re.compile(r"\b(?:Lei|LC|Lei Complementar|Decreto|Decreto-Lei|EC|Emenda Constitucional)\s*"
                            r"(?:n[ºo°.]*\s*)?(\d{1,2}(?:\.\d{3})*|\d+)\s*(?:/|,\s*de\s+)(\d{4})", re.IGNORECASE)


def _numeros(texto: str) -> set[tuple[str, str]]:
    return {(n.replace(".", ""), ano) for n, ano in _NUMERO_DE_LEI.findall(texto)}


def _outras_normas(art: dict, trechos: list[dict], nome_da_norma: str) -> list[str]:
    """Normas citadas na entrada além da principal, sem trecho oficial que as cubra.

    Lei que só alterou o dispositivo ("(c/ Lei nº 11.313/2006)" no art. 61 da Lei 9.099) não é lacuna:
    a redação que ela deu já está no texto consolidado, e a anotação da página o confirma.
    """
    incorporadas = {n for t in trechos for r in t.get("relacoes", []) for n in _numeros(r["ato"])}
    propria = _numeros(nome_da_norma)
    lacunas = []
    for citada in re.findall(r"\(c/\s*([^)]*)\)", art.get("lei", "") + " " + art.get("artigo", "")):
        numeros = _numeros(citada)
        if numeros and numeros <= incorporadas:
            continue
        lacunas.append(f"norma também citada ({citada.strip()}) sem trecho oficial transcrito")
    soltas = _numeros(art.get("texto", "")) - incorporadas - propria - {
        n for c in re.findall(r"\(c/\s*([^)]*)\)", art.get("lei", "")) for n in _numeros(c)}
    for numero, ano in sorted(soltas):
        lacunas.append(f"o texto da base menciona a norma nº {numero}/{ano}, sem trecho oficial na entrada")
    return lacunas


def _comparavel(texto: str) -> str:
    """Forma de comparar transcrições: espaços, travessões, aspas e ordinais unificados — só isso."""
    t = normalizar_pontuacao(texto)
    t = re.sub(r"[–—]", "-", t)
    t = re.sub(r"[“”«»]", '"', t)
    t = re.sub(r"(\d)\s*[º°o](?=[\s.,;:)-]|$)", r"\1º", t)
    return t


def transcricao_exata(texto: str, referencia: str) -> bool:
    """Cada frase do texto curado está, como está, no texto oficial (só a pontuação final pode variar)."""
    oficial = _comparavel(referencia)
    frases = [f.strip().rstrip(".;:,") for f in re.split(r"(?<=[.;:])\s+", _comparavel(texto))]
    return all(f in oficial for f in frases if f)


def classificar(texto: str, trechos: list[dict], sem_trecho: bool, jurisprudencia: bool = False
                ) -> tuple[str, float | None]:
    """Natureza do texto curado e a cobertura medida contra os trechos oficiais (ou None).

    "consolidado" exige todos os dispositivos com trecho oficial e cada frase do texto curado igual a um
    pedaço do texto oficial — a cobertura por janelas de 8 palavras não basta: deixava passar "e" trocado
    por vírgula e um parágrafo inteiro omitido (CF, art. 6º, na revisão de 22/10/2026).
    """
    fracao = None
    if trechos:
        referencia = " ".join(t.get("contexto", "") + " " + t["texto"] for t in trechos)
        fracao = round(cobertura(texto, referencia), 3)
        if not sem_trecho and transcricao_exata(texto, referencia):
            return "consolidado", fracao
    if jurisprudencia or _INTERPRETACAO.search(texto):
        # Súmula é, por natureza, o entendimento consolidado de um tribunal.
        return "interpretacao_juridica", fracao
    if fracao is not None:
        return "resumo_explicativo", fracao
    return "nao_conferido", fracao


_ARTIGO_CITADO = re.compile(r"\bart(?:igo)?s?\.?\s*(\d{1,4}(?:\.\d{3})?)\s*[º°o]?(?:-([A-Z])\b)?", re.IGNORECASE)
_ATO_DE_ALTERACAO = re.compile(r"(?:/|,\s*de\s+)((?:19|20)\d{2})")
ANO_ALTERACAO_RECENTE = 2016


def _artigos_citados_sem_trecho(texto: str, trechos: list[dict]) -> list[str]:
    com_trecho = {t["ref"]["artigo"] for t in trechos}
    citados = {n.replace(".", "") + (f"-{letra.upper()}" if letra else "") for n, letra in _ARTIGO_CITADO.findall(texto)}
    return sorted(citados - com_trecho, key=lambda a: (len(a), a))


def alteracoes_nao_registradas(art: dict, trechos: list[dict]) -> list[str]:
    """Alterações recentes que a página oficial anota e o bloco de vigência da base não registra.

    Só atos de 2016 em diante: o bloco de vigência foi escrito para as mudanças que um texto antigo
    erraria, não para toda a história do dispositivo. Pegou, na primeira rodada, a LC 236/2026 no CTN e a
    EC 114/2021 na CF, que a base não registrava.
    """
    v = art.get("vigencia") or {}
    registrado = " ".join(v.get("alterada_por") or []) + " " + (v.get("nota") or "")
    numeros_registrados = {n for n, _ in _numeros(registrado)}
    alertas = []
    for t in trechos:
        for r in t.get("relacoes", []):
            if r["tipo"] not in ("redacao_dada_por", "incluido_por", "revogado_por"):
                continue
            for numero, ano in _numeros(r["ato"]):
                if int(ano) >= ANO_ALTERACAO_RECENTE and numero not in numeros_registrados:
                    alerta = f"{r['ato']} ({t['dispositivo']})"
                    if alerta not in alertas:
                        alertas.append(alerta)
    return alertas


def proveniencia(art: dict, fontes: Fontes, hoje: date) -> dict:
    """Bloco de proveniência de uma entrada: trechos oficiais, natureza do texto e lacunas."""
    lacunas: list[str] = []
    trechos: list[dict] = []
    fonte = fontes.da_url(art.get("fonte", ""))
    manual = fontes.sem_coleta.get(normalizar_url(art.get("fonte", "")))
    refs = interpretar_rotulo(art.get("artigo", ""))
    if fonte is None:
        acesso = (manual or {}).get("acesso_a_fonte") or {}
        detalhe = f" ({acesso['resultado']}: {acesso['detalhe']}, em {acesso['verificado_em']})" if acesso else ""
        lacunas.append(f"fonte sem coleta automática{detalhe}: o texto não foi conferido com a fonte oficial")
    elif not refs:
        lacunas.append("o rótulo não nomeia artigos (norma inteira ou súmula): trecho oficial não extraído")
    elif (dados := fontes.artigos(fonte["id"])) is None:
        lacunas.append(f"a fonte {fonte['id']} ainda não tem versão aceita no monitor")
    else:
        versao, artigos = dados
        for ref in refs:
            trecho, lacuna = _trecho(ref, artigos, fonte, versao, hoje)
            if trecho:
                trechos.append(trecho)
            if lacuna:
                lacunas.append(lacuna)
    principais = list(trechos)
    # Dispositivos que o texto da base também usa, nomeados à mão (de outra norma ou do mesmo diploma):
    # entram como trechos oficiais, para que nada do texto curado fique sem fonte.
    for adicional in art.get("dispositivos_adicionais", []):
        outra = fontes.por_id.get(adicional["norma"])
        dados_outra = fontes.artigos(adicional["norma"]) if outra else None
        ref = Ref(**{k: v for k, v in adicional.items() if k != "norma"})
        if outra is None or dados_outra is None:
            lacunas.append(f"{adicional['norma']} {ref.rotulo()}: fonte sem versão aceita no monitor")
            continue
        trecho, lacuna = _trecho(ref, dados_outra[1], outra, dados_outra[0], hoje)
        if trecho and adicional["norma"] != (fonte or {}).get("id"):
            # Dispositivo de outra norma: o rótulo diz de qual ("Código de Processo Civil, art. 733").
            nome = outra["nome"].split(" — ")[0]
            trechos.append({**trecho, "norma": adicional["norma"], "dispositivo": f"{nome}, {trecho['dispositivo']}"})
        elif trecho:
            trechos.append(trecho)
        if lacuna:
            lacunas.append(f"{adicional['norma']}: {lacuna}")
    lacunas += _outras_normas(art, trechos, (fonte or {}).get("nome", "") + " " + art.get("lei", ""))
    if fonte is not None and refs:
        for artigo in _artigos_citados_sem_trecho(art["texto"], trechos):
            lacunas.append(f"o texto da base cita o art. {artigo}, sem trecho oficial na entrada")
    if "síntese" in art.get("artigo", "").lower():
        lacunas.append("a entrada é uma síntese de vários dispositivos")

    natureza, fracao = classificar(art["texto"], trechos, sem_trecho=not refs or len(principais) < len(refs),
                                   jurisprudencia=art.get("tipo") == "jurisprudencia")
    return {
        "norma": fonte["id"] if fonte else (manual or {}).get("id"),
        "dispositivos": [r.como_dict() for r in refs],
        "texto_natureza": natureza,
        "texto_cobertura_oficial": fracao,
        "trechos_oficiais": trechos,
        "lacunas": lacunas,
        "vigencia_alertas": [f"a página oficial anota alteração por {a}, que o bloco de vigência da base não registra"
                             for a in alteracoes_nao_registradas(art, trechos)],
    }


# ------------------------------------------------------------------ selos e histórico

CAMPOS_DE_PROVENIENCIA = ("norma", "dispositivos", "texto_natureza", "texto_cobertura_oficial", "trechos_oficiais",
                          "lacunas", "vigencia_alertas")


def canonico(art: dict) -> str:
    return json.dumps(art, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def selo(art: dict) -> str:
    """Hash da entrada inteira: qualquer mudança de texto, vigência ou fonte muda o selo."""
    return sha256(canonico(art))


def carregar_historico(caminho: Path) -> dict:
    if caminho.exists():
        return json.loads(caminho.read_text(encoding="utf-8"))
    return {"selos": {}, "eventos": []}


def campos_alterados(antes: dict | None, depois: dict | None) -> list[str]:
    antes, depois = antes or {}, depois or {}
    return sorted(k for k in set(antes) | set(depois) if antes.get(k) != depois.get(k))


def divergencias(corpus: list[dict], historico: dict) -> list[str]:
    """Entradas cujo conteúdo não corresponde ao último selo registrado (edição sem histórico)."""
    problemas = []
    ids = set()
    for art in corpus:
        ids.add(art["id"])
        registrado = historico["selos"].get(art["id"])
        if registrado is None:
            problemas.append(f"{art['id']}: entrada sem registro no histórico")
        elif registrado["selo"] != selo(art):
            problemas.append(f"{art['id']}: conteúdo mudou sem registro no histórico")
    for removido in set(historico["selos"]) - ids:
        if historico["selos"][removido].get("estado") != "removida":
            problemas.append(f"{removido}: entrada removida sem registro no histórico")
    return problemas


def guardar_versao(loja: Path, art: dict) -> str:
    """Guarda a entrada com o nome do próprio selo (endereçamento por conteúdo); devolve o selo."""
    import gzip

    s = selo(art)
    caminho = loja / f"{s}.json.gz"
    if not caminho.exists():
        loja.mkdir(parents=True, exist_ok=True)
        with open(caminho, "wb") as bruto, gzip.GzipFile(fileobj=bruto, mode="wb", mtime=0) as gz:
            gz.write(canonico(art).encode("utf-8"))
    return s


def ler_versao(loja: Path, s: str) -> dict | None:
    import gzip

    caminho = loja / f"{s}.json.gz"
    if not caminho.exists():
        return None
    with gzip.open(caminho, "rt", encoding="utf-8") as gz:
        return json.loads(gz.read())


def registrar(corpus: list[dict], historico: dict, loja: Path, *, responsavel: str, motivo: str, em: str,
              evidencia: list[str] | None = None) -> list[dict]:
    """Anota no histórico cada entrada nova, alterada ou removida desde o último selo.

    A versão anterior e a nova ficam na loja (endereçadas pelo selo): o evento diz quais campos mudaram
    e permite reverter.
    """
    if not responsavel.strip() or not motivo.strip():
        raise ValueError("informe o responsável e o motivo da alteração")
    eventos = []
    atuais = {a["id"]: a for a in corpus}
    for id_, art in atuais.items():
        novo = guardar_versao(loja, art)
        anterior = historico["selos"].get(id_)
        if anterior and anterior["selo"] == novo and anterior.get("estado") != "removida":
            continue
        versao_anterior = ler_versao(loja, anterior["selo"]) if anterior else None
        eventos.append({
            "em": em,
            "id": id_,
            "acao": "criada" if anterior is None else "alterada",
            "campos": campos_alterados(versao_anterior, art) if anterior else [],
            "selo_anterior": anterior["selo"] if anterior else None,
            "selo_novo": novo,
            "responsavel": responsavel,
            "motivo": motivo,
            "evidencia": evidencia or [],
        })
        historico["selos"][id_] = {"selo": novo, "em": em}
    for id_ in set(historico["selos"]) - set(atuais):
        if historico["selos"][id_].get("estado") == "removida":
            continue
        eventos.append({"em": em, "id": id_, "acao": "removida", "campos": [],
                        "selo_anterior": historico["selos"][id_]["selo"], "selo_novo": None,
                        "responsavel": responsavel, "motivo": motivo, "evidencia": evidencia or []})
        historico["selos"][id_] = {**historico["selos"][id_], "estado": "removida", "em": em}
    historico["eventos"].extend(eventos)
    return eventos


def versao_anterior(historico: dict, loja: Path, id_: str) -> dict | None:
    """O conteúdo da entrada antes da última alteração registrada (para reverter)."""
    eventos = [e for e in historico["eventos"] if e["id"] == id_ and e["acao"] == "alterada"]
    if not eventos:
        return None
    return ler_versao(loja, eventos[-1]["selo_anterior"])


# ------------------------------------------------------------------ conferência

def conferir_trechos(corpus: list[dict], fontes: Fontes) -> list[str]:
    """Cada trecho oficial confere com a versão da fonte que ele cita?

    Três verificações independentes: o hash do texto; o hash do snapshot; e, refazendo a extração
    naquela versão, o mesmo texto — cujos pedaços entre as anotações retiradas estão, um a um, na
    página. Nenhuma palavra do trecho pode ter vindo de outro lugar.
    """
    problemas = []
    for art in corpus:
        for t in art.get("trechos_oficiais", []):
            nome = f"{art['id']} {t['dispositivo']}"
            if sha256(t["texto"]) != t["hash_sha256"]:
                problemas.append(f"{nome}: texto não confere com o hash registrado")
                continue
            try:
                snapshot = fontes.registro.ler_snapshot(t["fonte_id"], t["versao_fonte"])
            except FileNotFoundError:
                problemas.append(f"{nome}: snapshot {t['versao_fonte']} ausente")
                continue
            if sha256(snapshot) != t["hash_fonte"]:
                problemas.append(f"{nome}: snapshot não confere com o hash da fonte")
                continue
            ref = Ref(**t["ref"])
            artigos = fontes.artigos_da_versao(t["fonte_id"], t["versao_fonte"])
            texto_artigo, _, lacuna = _escolher(artigos, ref.artigo)
            if texto_artigo is None:
                problemas.append(f"{nome}: {lacuna}")
                continue
            limpo = limpar(localizar(texto_artigo, ref))
            if limpo.texto != t["texto"]:
                problemas.append(f"{nome}: a extração refeita na mesma versão dá outro texto")
                continue
            plano = normalizar_pontuacao(snapshot)
            if faltando := [s for s in limpo.segmentos if s not in plano]:
                problemas.append(f"{nome}: pedaço do trecho não está na página: {faltando[0][:80]!r}")
    return problemas
