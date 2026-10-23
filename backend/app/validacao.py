"""Estado de validação de cada resposta, por verificações determinísticas.

O estado descreve a evidência que sustenta a resposta; não é certificação jurídica, garantia de
resultado nem parecer. Nenhuma das verificações é uma nota dada pelo próprio modelo de linguagem:

- **força da evidência** — a nota BM25 do 1º colocado contra um limiar calibrado (abaixo dele, a
  base não tem o assunto e a API se abstém);
- **fonte oficial** — cada dispositivo aponta para um domínio oficial;
- **texto conferido** — o texto do corpus confere com a versão aceita da página oficial (monitor
  legislativo, `app/monitor/fidelidade.py`);
- **vigência** — situação na data da consulta; dispositivo fora de vigor pede cuidado;
- **atualidade** — conferência de vigência com mais de `VALIDADE_CONFERENCIA_DIAS` dias, ou norma
  cuja data de início chegou sem a base ter registrado a revisão;
- **revisão pendente** — no corpus ou no monitor;
- **conflito aparente** — o mesmo dispositivo (mesma lei, mesmo rótulo) com redações em situações de
  vigência diferentes, como a redação antiga e a nova lado a lado (a armadilha temporal);
- **citações do texto gerado** — artigo ou súmula citado pelo LLM que não está entre os recuperados.
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .monitor.fidelidade import verificar_corpus
from .monitor.impacto import artigos_do_rotulo
from .monitor.registro import Registro, diretorio
from .monitor.sinais import fonte_desatualizada
from .retrieval import DATA_PATH

# Abaixo desta nota BM25 do 1º colocado, a evidência é insuficiente e a API não responde com
# dispositivos. Calibrado em scripts/avaliar.py com a regra "o maior limiar sem nenhuma abstenção
# indevida nas 11 perguntas de calibração": 6,0 abstém 8 de 13 perguntas fora do escopo da
# calibração. Na validação (75 dentro e 13 fora do escopo, que não participaram da escolha): 8 de 13
# abstenções corretas e 3 de 75 indevidas. O limiar fica logo abaixo da pergunta legítima mais fraca
# da calibração (6,04) — é frágil, e por isso é medido a cada rodada da avaliação.
LIMIAR_EVIDENCIA = 6.0
VALIDADE_CONFERENCIA_DIAS = 180

DOMINIOS_OFICIAIS = (".gov.br", ".jus.br", ".leg.br", ".mp.br")

ESTADOS = {
    "fonte_e_versao_verificadas": "Fonte e versão verificadas",
    "evidencia_suficiente": "Evidência suficiente para explicação informativa",
    "fonte_localizada": "Fonte localizada",
    "revisao_humana_recomendada": "Revisão humana recomendada",
    "conflito_de_fontes": "Conflito de fontes",
    "fonte_desatualizada_ou_indisponivel": "Fonte desatualizada ou indisponível",
    "evidencia_insuficiente": "Evidência insuficiente",
}
AVISO = ("Estes estados descrevem a evidência encontrada pela base. Não são certificação jurídica, "
         "garantia de resultado nem parecer profissional.")

_RE_ARTIGO_CITADO = re.compile(r"\bart(?:igo)?s?\.?\s*(\d{1,4}(?:\.\d{3})?)\s*[º°o]?(?:-([A-Z]))?", re.IGNORECASE)
_RE_SUMULA_CITADA = re.compile(r"\bs[úu]mula(?:\s+vinculante)?\s*(?:n[ºo°.]*\s*)?(\d{1,4})", re.IGNORECASE)

_cache_fidelidade: dict[str, Any] = {"chave": None, "por_id": {}}


def fidelidade_por_id() -> dict[str, dict]:
    """Classe de fidelidade de cada dispositivo, recalculada só quando o registro do monitor muda."""
    caminho = Path(diretorio()) / "registro.json"
    try:
        estado = caminho.stat()
    except OSError:
        return {}
    chave = f"{caminho}:{estado.st_mtime_ns}:{estado.st_size}"
    if _cache_fidelidade["chave"] != chave:
        corpus = json.loads(Path(DATA_PATH).read_text(encoding="utf-8"))["artigos"]
        resultados = verificar_corpus(corpus, Registro(caminho.parent))
        _cache_fidelidade.update(chave=chave, por_id={r["id"]: r for r in resultados})
    return _cache_fidelidade["por_id"]


def evidencia_insuficiente(artigos, calibrado: bool = True) -> bool:
    if not artigos:
        return True
    return calibrado and artigos[0].score < LIMIAR_EVIDENCIA


def _oficial(url: str) -> bool:
    host = re.sub(r"^https?://", "", url or "").split("/")[0].lower()
    return any(host.endswith(d) for d in DOMINIOS_OFICIAIS)


def _numero_sumula(rotulo: str) -> str | None:
    m = re.search(r"s[úu]mula(?:\s+vinculante)?\s*(\d+)", rotulo, re.IGNORECASE)
    return m.group(1) if m else None


def citacoes_sem_suporte(texto: str, artigos) -> list[str]:
    """Artigos e súmulas citados no texto gerado que não estão entre os dispositivos recuperados."""
    artigos_ok = set().union(*(artigos_do_rotulo(a.artigo) for a in artigos)) if artigos else set()
    sumulas_ok = {n for a in artigos if (n := _numero_sumula(a.artigo))}
    soltos = []
    for numero, letra in _RE_ARTIGO_CITADO.findall(texto):
        chave = numero.replace(".", "") + (f"-{letra.upper()}" if letra else "")
        if chave not in artigos_ok:
            soltos.append(f"art. {numero}{'-' + letra if letra else ''}")
    soltos += [f"Súmula {n}" for n in _RE_SUMULA_CITADA.findall(texto) if n not in sumulas_ok]
    return list(dict.fromkeys(soltos))


def _conflitos(artigos) -> list[str]:
    """O mesmo dispositivo em situações de vigência diferentes. Incisos diferentes do mesmo artigo
    (cf-7 × cf-7-xiii) não conflitam: o rótulo é diferente."""

    def chave(texto: str) -> str:
        return " ".join(re.sub(r"\(.*?\)", " ", texto).lower().split())

    por_dispositivo: dict[tuple[str, str], set[str]] = {}
    for a in artigos:
        por_dispositivo.setdefault((chave(a.lei), chave(a.artigo)), set()).add(a.vigencia.get("status", "nao_verificada"))
    return [f"{a} — {b}" for (a, b), situacoes in por_dispositivo.items() if len(situacoes) > 1]


def avaliar(artigos, hoje: date, texto_gerado: str | None = None, calibrado: bool = True,
            abstencao: bool = False) -> dict:
    verificacoes: list[dict] = []

    def verificar(nome: str, ok: bool | None, detalhe: str) -> None:
        verificacoes.append({"nome": nome, "ok": ok, "detalhe": detalhe})

    if abstencao or not artigos:
        nota = artigos[0].score if artigos else 0.0
        verificar("forca_da_evidencia", False,
                  f"melhor nota {nota:.1f}, abaixo do limiar {LIMIAR_EVIDENCIA:.1f}: a base não parece ter o assunto"
                  if artigos else "nenhum dispositivo encontrado")
        return {"estado": "evidencia_insuficiente", "rotulo": ESTADOS["evidencia_insuficiente"],
                "verificacoes": verificacoes, "aviso": AVISO}

    if calibrado:
        verificar("forca_da_evidencia", True,
                  f"melhor nota {artigos[0].score:.1f} (limiar {LIMIAR_EVIDENCIA:.1f})")
    else:
        verificar("forca_da_evidencia", None, "limiar não calibrado para o motor de busca em uso")

    nao_oficiais = [a.id for a in artigos if not _oficial(a.fonte)]
    verificar("fonte_oficial", not nao_oficiais,
              "todos os dispositivos apontam para fonte oficial" if not nao_oficiais
              else f"sem fonte oficial: {', '.join(nao_oficiais)}")

    fidelidade = fidelidade_por_id()
    conferidos = [a.id for a in artigos if fidelidade.get(a.id, {}).get("classe") in ("literal", "quase_literal")]
    verificar("texto_conferido", len(conferidos) == len(artigos),
              f"{len(conferidos)} de {len(artigos)} com texto conferido contra a versão oficial vigente"
              + ("" if conferidos else " (fonte não monitorada, ou texto condensado ou parafraseado)"))

    nao_verificados = [a.id for a in artigos if a.vigencia.get("status", "nao_verificada") == "nao_verificada"]
    fora_de_vigor = [a.id for a in artigos
                     if a.vigencia.get("status", "nao_verificada") not in ("vigente", "nao_verificada")]
    verificar("vigencia", not fora_de_vigor and not nao_verificados,
              "todos em vigor na data da consulta" if not fora_de_vigor and not nao_verificados
              else "; ".join(filter(None, [
                  f"fora de vigor hoje: {', '.join(fora_de_vigor)} — a resposta precisa dizer o que vale agora"
                  if fora_de_vigor else "",
                  f"situação de vigência não verificada: {', '.join(nao_verificados)}" if nao_verificados else "",
              ])))

    limite = (hoje - timedelta(days=VALIDADE_CONFERENCIA_DIAS)).isoformat()
    velhos = [a.id for a in artigos if (a.vigencia.get("conferida_em") or "0000") < limite]
    sem_revisao = [a.id for a in artigos if a.vigencia.get("status_registrado")]
    # A página oficial da norma não é conferida pelo monitor há mais do que o limite: a base não sabe se ela
    # mudou nesse meio-tempo.
    fontes_paradas = {n: d for a in artigos if (n := getattr(a, "norma", None)) and (d := fonte_desatualizada(n))}
    sem_monitor = [a.id for a in artigos if getattr(a, "norma", None) in fontes_paradas]
    verificar("atualidade", not velhos and not sem_revisao and not sem_monitor,
              f"vigência conferida há menos de {VALIDADE_CONFERENCIA_DIAS} dias e fontes conferidas pelo monitor"
              if not velhos and not sem_revisao and not sem_monitor
              else "; ".join(filter(None, [
                  f"conferência antiga: {', '.join(velhos)}" if velhos else "",
                  f"data de início chegou sem revisão registrada: {', '.join(sem_revisao)}" if sem_revisao else "",
                  "fonte oficial sem conferência recente do monitor: "
                  + "; ".join(f"{n} ({d['motivo']})" for n, d in fontes_paradas.items()) if sem_monitor else "",
              ])))

    em_revisao = [a.id for a in artigos if a.revisao and a.revisao.get("estado") == "pendente"]
    verificar("revisao_pendente", not em_revisao,
              "nenhum dispositivo em revisão" if not em_revisao else f"em revisão: {', '.join(em_revisao)}")

    conflitos = _conflitos(artigos)
    verificar("conflito", not conflitos,
              "nenhum conflito aparente" if not conflitos
              else f"o mesmo dispositivo aparece em situações de vigência diferentes: {'; '.join(conflitos)}")

    soltas: list[str] = []
    if texto_gerado is not None:
        soltas = citacoes_sem_suporte(texto_gerado, artigos)
        verificar("citacoes_do_texto_gerado", not soltas,
                  "toda citação do texto gerado está entre os dispositivos recuperados" if not soltas
                  else f"citações sem dispositivo recuperado: {', '.join(soltas)}")

    if velhos or sem_revisao or sem_monitor:
        estado = "fonte_desatualizada_ou_indisponivel"
    elif conflitos:
        estado = "conflito_de_fontes"
    elif em_revisao or fora_de_vigor or nao_verificados or soltas:
        estado = "revisao_humana_recomendada"
    elif calibrado and conferidos and len(conferidos) == len(artigos) and not nao_oficiais:
        estado = "fonte_e_versao_verificadas"
    elif calibrado and not nao_oficiais:
        estado = "evidencia_suficiente"
    else:
        estado = "fonte_localizada"
    return {"estado": estado, "rotulo": ESTADOS[estado], "verificacoes": verificacoes, "aviso": AVISO}
