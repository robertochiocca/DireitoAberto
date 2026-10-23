"""Medição do leitor no conjunto adversarial (data/exemplos/adversariais).

    python -m app.leitor.avaliacao

Cada documento tem um gabarito escrito à mão com `verificacoes` declarativas
(peças esperadas, decisão que vale, trânsito certificado ou não, estado das
páginas, inconsistências, prazos, respostas a perguntas…). Esta função roda o
leitor em cada documento e conta quantas verificações passam. Além das do
gabarito, todo documento ganha uma verificação implícita: toda citação da
análise tem de existir, literalmente, na página citada — conferida aqui de
novo, de forma independente de `verificacao.py`.

As funções do leitor podem ser trocadas (`funcoes=`), para medir a versão
anterior do código com a mesma régua. Uma versão que recusa o documento
(`DocumentoInvalido`) reprova todas as verificações dele.

Limite desta medida: os documentos e os gabaritos foram escritos pelo próprio
projeto para reproduzir falhas conhecidas. Passar aqui mostra que essas falhas
foram corrigidas; não mede o leitor em processos reais.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from .texto import sem_acento

CONJUNTO = Path(__file__).resolve().parent.parent.parent / "data" / "exemplos" / "adversariais"

# Nomes de peça no resumo antigo ("Resultado da sentença (...)"), para medir versões sem `decisao_principal`.
_TIPO_POR_NOME = {"sentença": "sentenca", "acórdão": "acordao", "decisão": "decisao"}
_RE_RESULTADO_RESUMO = re.compile(r"^Resultado d[ao] (\w+) \(.*?\): (.+?) — ")
_ASPAS = str.maketrans({"“": '"', "”": '"', "«": '"', "»": '"', "‘": "'", "’": "'"})


def _simples(texto: str) -> str:
    return sem_acento(texto).lower()


def _citacoes(objeto: Any) -> Iterator[dict]:
    if isinstance(objeto, dict):
        if {"pagina", "trecho", "verificada"} <= set(objeto):
            yield objeto
        for valor in objeto.values():
            yield from _citacoes(valor)
    elif isinstance(objeto, list):
        for valor in objeto:
            yield from _citacoes(valor)


def _na_pagina(doc: Any, pagina: int, trecho: str) -> bool:
    """Conferência independente: o trecho está, literalmente (a menos de espaços), na página."""
    alvo = doc.pagina(pagina)
    if alvo is None or alvo.estado not in ("lida", "possivelmente_digitalizada"):
        return False
    normal = " ".join(trecho.translate(_ASPAS).split())
    return bool(normal) and normal in " ".join(alvo.texto.translate(_ASPAS).split())


def _decisao_principal(a: dict) -> dict | None:
    if "decisao_principal" in a:
        d = a["decisao_principal"]
        return {"tipo": d.get("tipo"), "pagina": d.get("pagina"), "resultado": d.get("resultado")} if d else None
    for frase in a.get("resumo", []):  # versão anterior: só o texto do resumo diz qual foi a decisão
        if m := _RE_RESULTADO_RESUMO.match(frase["texto"]):
            pagina = frase["citacoes"][0]["pagina"] if frase.get("citacoes") else None
            return {"tipo": _TIPO_POR_NOME.get(m.group(1).lower()), "pagina": pagina, "resultado": m.group(2).lower()}
    return None


def _textos_de_aviso(a: dict) -> list[str]:
    return [_simples(t) for t in a.get("avisos", [])] + [_simples(p["texto"]) for p in a.get("pendencias", [])]


def _verificar(v: dict, doc: Any, a: dict, responder: Callable) -> tuple[bool, str]:
    tipo = v["tipo"]
    esperado: Any = v.get("esperado")
    pecas = [(p["tipo"], p["pagina_inicial"]) for p in a.get("pecas", [])]
    if tipo == "pecas":
        return pecas == [tuple(p) for p in esperado], f"peças {pecas} == {esperado}"
    if tipo == "pecas_contem":
        return all(tuple(p) in pecas for p in esperado), f"peças {pecas} contêm {esperado}"
    if tipo == "peca_ausente":
        return all(t != esperado for t, _ in pecas), f"nenhuma peça do tipo {esperado}"
    if tipo == "peca_origem":
        ok = any(p["pagina_inicial"] == v["pagina"] and p["origem"] == esperado for p in a.get("pecas", []))
        return ok, f"peça na p. {v['pagina']} com origem {esperado}"
    if tipo == "sem_origem":
        origens = {p["origem"] for p in a.get("pecas", [])}
        return not (origens & set(esperado)), f"nenhuma peça de origem {esperado} (há {sorted(origens)})"
    if tipo == "numero_processo":
        return any(n["numero"] == esperado for n in a.get("numeros_processo", [])), f"número {esperado}"
    if tipo == "parte":
        ok = any(p.get("papel") == v["papel"] and p.get("nome") == v["nome"] for p in a.get("partes", []))
        return ok, f"parte {v['papel']}: {v['nome']}"
    if tipo == "decisao_principal":
        obtida = _decisao_principal(a)
        if esperado is None:
            return obtida is None or obtida.get("resultado") is None, f"nenhum resultado afirmado (obtido: {obtida})"
        ok = obtida is not None and all(obtida.get(k) == valor for k, valor in esperado.items())
        return ok, f"decisão principal {esperado} (obtida: {obtida})"
    if tipo == "transito_certificado":
        certificado = bool(a.get("transito_em_julgado"))
        return certificado == esperado, f"trânsito certificado = {esperado} (obtido: {certificado})"
    if tipo == "estado_pagina":
        pagina = doc.pagina(v["pagina"])
        estado = pagina.estado if pagina else None
        return estado == esperado, f"p. {v['pagina']} = {esperado} (obtido: {estado})"
    if tipo == "leitura_completa":
        completa = a.get("documento", {}).get("leitura_completa")
        return completa == esperado, f"leitura_completa = {esperado} (obtido: {completa})"
    if tipo == "aviso_contem":
        return any(_simples(esperado) in t for t in _textos_de_aviso(a)), f"aviso com «{esperado}»"
    if tipo == "inconsistencia":
        tipos = [i.get("tipo") for i in a.get("inconsistencias", [])]
        return esperado in tipos, f"inconsistência {esperado} (obtidas: {tipos})"
    if tipo in ("item_presente", "item_ausente"):
        achou = any(v["contem"] in it["texto"] and ("pagina" not in v or it["citacoes"][0]["pagina"] == v["pagina"])
                    for it in a.get(v["categoria"], []))
        return achou == (tipo == "item_presente"), f"{tipo} em {v['categoria']}: «{v['contem']}»"
    if tipo == "nenhum_item_com_natureza":
        ok = not any(it.get("natureza") == esperado for it in a.get(v["categoria"], []))
        return ok, f"nenhum item {esperado} em {v['categoria']}"
    if tipo == "prazo":
        ok = any(
            it["citacoes"][0]["pagina"] == v["pagina"] and v["contem"] in it["texto"]
            and v.get("duracao_contem", "") in it.get("duracao", "")
            and _simples(v.get("tipo_de_prazo_contem", "")) in _simples(it.get("tipo_de_prazo", ""))
            for it in a.get("prazos", [])
        )
        return ok, f"prazo na p. {v['pagina']} «{v['contem']}» {v.get('duracao_contem', '')} {v.get('tipo_de_prazo_contem', '')}"
    if tipo == "prazo_ausente":
        ok = not any(v["duracao_contem"] in it.get("duracao", "") for it in a.get("prazos", []))
        return ok, f"nenhum prazo «{v['duracao_contem']}»"
    if tipo == "resumo_nao_contem":
        return not any(esperado in f["texto"] for f in a.get("resumo", [])), f"resumo sem «{esperado}»"
    if tipo == "resposta":
        r = responder(doc, a, v["pergunta"])
        texto = _simples(r["resposta"])
        falhas = [f"falta «{c}»" for c in v.get("contem", []) if _simples(c) not in texto]
        falhas += [f"não devia ter «{c}»" for c in v.get("nao_contem", []) if _simples(c) in texto]
        if "nao_comeca_com" in v and r["resposta"].lstrip().startswith(v["nao_comeca_com"]):
            falhas.append(f"começa com «{v['nao_comeca_com']}»")
        if "abstencao" in v and r["abstencao"] != v["abstencao"]:
            falhas.append(f"abstenção = {r['abstencao']}")
        return not falhas, f"resposta a «{v['pergunta']}»" + (f": {'; '.join(falhas)}" if falhas else "")
    raise ValueError(f"Verificação desconhecida: {tipo}")


def _extrair(extrair: Callable, nome: str, conteudo: bytes, parametros: dict) -> Any:
    if not parametros:
        return extrair(nome, conteudo)
    try:
        return extrair(nome, conteudo, **parametros)
    except TypeError:  # versão sem esses parâmetros: roda com os limites dela
        return extrair(nome, conteudo)


def avaliar_conjunto(diretorio: Path = CONJUNTO, funcoes: tuple[Callable, Callable, Callable] | None = None) -> dict:
    """Roda o leitor em cada documento do conjunto e confere o gabarito. Devolve números por documento."""
    if funcoes is None:
        from .analise import analisar
        from .extracao import extrair
        from .perguntas import responder

        funcoes = (extrair, analisar, responder)
    extrair_f, analisar_f, responder_f = funcoes
    documentos: dict[str, dict] = {}
    citacoes_total = citacoes_ok = 0
    for caminho in sorted(diretorio.glob("*.gabarito.json")):
        gabarito = json.loads(caminho.read_text(encoding="utf-8"))
        nome = gabarito["arquivo"].removesuffix(".pdf")
        verificacoes = gabarito["verificacoes"]
        inicio = time.perf_counter()
        resultado: dict[str, Any] = {"verificacoes": len(verificacoes) + 1, "aprovadas": 0, "falhas": [], "erro": None}
        try:
            doc = _extrair(extrair_f, gabarito["arquivo"], (diretorio / gabarito["arquivo"]).read_bytes(),
                           gabarito.get("parametros", {}))
            a = analisar_f(doc)
        except Exception as exc:  # documento recusado ou erro: reprova tudo, com o motivo
            resultado["erro"] = f"{type(exc).__name__}: {exc}"[:300]
            resultado["falhas"] = ["documento não foi analisado"]
            resultado["tempo_s"] = round(time.perf_counter() - inicio, 3)
            documentos[nome] = resultado
            continue
        citacoes = list(_citacoes(a))
        conferidas = sum(1 for c in citacoes if c["verificada"] and _na_pagina(doc, c["pagina"], c["trecho"]))
        citacoes_total += len(citacoes)
        citacoes_ok += conferidas
        checagens = [(conferidas == len(citacoes) and not a.get("controle", {}).get("citacoes_descartadas"),
                      f"citações conferidas ({conferidas}/{len(citacoes)})")]
        for v in verificacoes:
            try:
                checagens.append(_verificar(v, doc, a, responder_f))
            except Exception as exc:
                checagens.append((False, f"{v['tipo']}: erro {type(exc).__name__}: {exc}"[:300]))
        resultado["aprovadas"] = sum(1 for ok, _ in checagens if ok)
        resultado["falhas"] = [descricao for ok, descricao in checagens if not ok]
        resultado["tempo_s"] = round(time.perf_counter() - inicio, 3)
        documentos[nome] = resultado
    total = sum(d["verificacoes"] for d in documentos.values())
    aprovadas = sum(d["aprovadas"] for d in documentos.values())
    return {
        "documentos": documentos,
        "total": {
            "documentos": len(documentos),
            "documentos_sem_falha": sum(1 for d in documentos.values() if not d["falhas"]),
            "verificacoes": total,
            "aprovadas": aprovadas,
            "taxa": round(aprovadas / total, 4) if total else None,
        },
        "citacoes": {"total": citacoes_total, "verificadas": citacoes_ok},
    }


if __name__ == "__main__":
    print(json.dumps(avaliar_conjunto(), ensure_ascii=False, indent=1))
