"""Verificação de uma fonte: coleta, comparação, impacto, relatório e registro.

Dois modos. No **controlado** (padrão), o resultado vai para o registro do monitor — versões, relatório,
fila de revisão —, mas NUNCA para o corpus: levar uma versão ao corpus é `scripts/corpus.py publicar`,
com decisão humana. Na **simulação** (`simular=True`), tudo é calculado e devolvido, e nada é gravado.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from ..retrieval import DATA_PATH, Retriever
from . import artigos as artigos_mod
from . import coleta, eventos, relatorio
from .comparar import TIPOS, Mudanca, coleta_suspeita, comparar, mudanca_da_pagina, normas_citadas
from .impacto import afetados_pela_fonte, indice_de_dependencias, rodar_regressao
from .registro import Registro, agora_iso

NORMAS_PATH = Path(DATA_PATH).parent / "normas.json"


def _corpus(caminho: Path = DATA_PATH) -> list[dict]:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))["artigos"]


def _normas() -> list[dict]:
    try:
        return json.loads(NORMAS_PATH.read_text(encoding="utf-8"))["normas"]
    except (OSError, ValueError, KeyError):
        return []


def _releitura(mudancas: list[Mudanca]) -> list[Mudanca]:
    """A página não mudou; mudou a leitura (o tachado por estilo deixou de contar como vigente)."""
    risco, explicacao = TIPOS["tachado_por_estilo_retirado"]
    return [Mudanca(**{**m.como_dict(), "tipo": "tachado_por_estilo_retirado", "risco": risco,
                       "explicacao": explicacao}) for m in mudancas]


def _outra_norma_na_primeira_captura(fonte_id: str, titulo: str | None) -> str | None:
    """Sem versão aceita para comparar o título, compara com o número da norma em data/normas.json."""
    numero = next((n.get("numero") for n in _normas() if n["id"] == fonte_id), None)
    if not numero or not titulo:
        return None
    if numero.replace(".", "") in re.findall(r"\d+", titulo.replace(".", "")):
        return None
    return (f"a página coletada traz o título \"{titulo}\", que não tem o número da norma ({numero}): provável página "
            "trocada ou redirecionada — nada foi registrado")


def verificar(
    fonte: dict,
    registro: Registro,
    baixar: Callable[[str], bytes] = coleta.baixar,
    retriever: Retriever | None = None,
    simular: bool = False,
) -> dict:
    """Verifica uma fonte e devolve o que aconteceu: {resultado, detalhe, versao?, estado?, eventos?, …}.

    Em simulação, devolve também `versao_calculada` (o registro que seria gravado) e `relatorio_md`.
    """

    def concluir(resultado: str, detalhe: str = "", **extra) -> dict:
        if not simular:
            registro.registrar_verificacao(fonte["id"], resultado, detalhe)
        return {"resultado": resultado, "detalhe": detalhe, **extra}

    try:
        bruto = baixar(fonte["url"])
    except coleta.FalhaDeColeta as exc:
        return concluir("falha_de_coleta", str(exc))

    texto, alertas_da_leitura = coleta.ler(bruto)
    hash_texto = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    novos = artigos_mod.dividir(texto)
    inclusivo = artigos_mod.dividir(coleta.texto_com_tachado(bruto))
    riscados = artigos_mod.tachados(novos, inclusivo)
    base = {
        "fonte": fonte["id"],
        "versao": hash_texto[:16],
        "hash_sha256": hash_texto,
        "url": fonte["url"],
        "capturada_em": agora_iso(),
        **coleta.metadados(texto),
        "artigos": len([k for k in novos if k not in ("preambulo", "fecho")]),
        "artigos_tachados": len(riscados),
        "leitura": coleta.LEITURA,
        "caracteres": len(texto),
    }
    aceita = registro.versao_aceita(fonte["id"])

    if alertas_da_leitura:
        # Marcação quebrada não é revogação: um riscado sem fim apagaria texto vigente.
        return concluir("coleta_suspeita", "leitura do texto riscado duvidosa: " + "; ".join(alertas_da_leitura))
    if base["artigos"] == 0 and not riscados:
        # Página de erro, aviso de manutenção ou codificação mal lida: nenhuma norma tem zero artigos, nem
        # vigentes nem riscados — diga a página o que disser sobre revogação.
        return concluir("coleta_suspeita",
                        "nenhum artigo reconhecido no texto (página de erro ou codificação não reconhecida?)")
    if motivo := (coleta.outro_ato(aceita.get("titulo"), base.get("titulo")) if aceita
                  else _outra_norma_na_primeira_captura(fonte["id"], base.get("titulo"))):
        return concluir("coleta_suspeita", motivo)
    # Revogação da norma inteira: a anotação no cabeçalho — antes de qualquer artigo, riscado ou não, numa
    # página que traz o título do ato — ou todos os artigos riscados. Só é mudança se a versão aceita ainda
    # não a mostrava.
    revogada_por = coleta.revogacao_da_norma(inclusivo.get("preambulo", "")) if base.get("titulo") else None
    base["pagina_indica_revogacao_total"] = bool(revogada_por) or (base["artigos"] == 0 and bool(riscados))
    revogacao_total = base["pagina_indica_revogacao_total"] and not (aceita or {}).get("pagina_indica_revogacao_total")
    if aceita and hash_texto == aceita["hash_sha256"]:
        return concluir("sem_mudanca", versao=aceita["versao"])

    mesmo_texto = [v for v in registro.versoes_da_fonte(fonte["id"]) if v["hash_sha256"] == hash_texto]
    ja = mesmo_texto[-1] if mesmo_texto else None
    if ja and (ja["estado"] == "pendente_revisao"
               or (ja["estado"] == "rejeitada" and ja.get("anterior") == (aceita or {}).get("versao"))):
        return concluir("versao_ja_registrada", ja["estado"], versao=ja["versao"], estado=ja["estado"])
    # Texto igual a uma versão que já foi aceita e deixou de ser (MP que caducou, reversão, correção da
    # página) — ou a um texto rejeitado que volta depois que outra versão foi aceita: é evento novo,
    # comparado com a versão aceita hoje, e vai para revisão.
    retorno = ja
    if retorno:
        base["versao"] = f"{base['versao']}-{len(mesmo_texto) + 1}"

    if aceita is None and not revogacao_total:
        versao = {**base, "estado": "linha_de_base", "anterior": None, "mudancas": [], "resumo_mudancas": {},
                  "eventos": eventos.derivar([], linha_de_base=True), "dispositivos_afetados": [], "regressao": [],
                  "relatorio": None, "decisao": None}
        if not simular:
            registro.registrar_versao(versao, texto)
        return concluir("linha_de_base", f"{base['artigos']} artigos", versao=base["versao"], estado="linha_de_base",
                        eventos=versao["eventos"], **({"versao_calculada": versao} if simular else {}))

    antigos = artigos_mod.dividir(registro.ler_snapshot(fonte["id"], aceita["versao"])) if aceita else {}
    # A versão aceita pode ter sido lida com uma leitura anterior (antes do riscado por estilo). Mudança da
    # página e mudança da leitura não se misturam: a página é comparada lida do mesmo jeito que a aceita, e o
    # que só a leitura nova muda aparece à parte, como "tachado por estilo retirado".
    leitura_aceita = (aceita or {}).get("leitura", 1)
    releitura = bool(aceita) and leitura_aceita < coleta.LEITURA
    if releitura:
        mesma_leitura = artigos_mod.dividir(coleta.texto_vigente(bruto, leitura=leitura_aceita))
        riscados_mesma_leitura = artigos_mod.tachados(mesma_leitura, inclusivo)
    else:
        mesma_leitura, riscados_mesma_leitura = novos, riscados
    if not revogacao_total and (motivo := coleta_suspeita(antigos, mesma_leitura, riscados_mesma_leitura)):
        return concluir("coleta_suspeita", motivo)

    lista = comparar(antigos, mesma_leitura, riscados_mesma_leitura) if aceita else []
    if releitura:
        reais = {m.artigo for m in lista}
        lista += [m for m in _releitura(comparar(mesma_leitura, novos)) if m.artigo not in reais]
    if revogacao_total:
        # A anotação de revogação no cabeçalho é a própria mudança da página: não vira outra no preâmbulo.
        lista = [m for m in lista if not (m.artigo == "preambulo" and "Revogad" in " ".join([m.trecho_novo or "",
                                                                                           *m.anotacoes_novas]))]
        lista.insert(0, mudanca_da_pagina("indicio_revogacao_total", trecho_novo=revogada_por or
                                          f"todos os {len(riscados)} artigos da página aparecem riscados",
                                          normas_citadas=normas_citadas([revogada_por] if revogada_por else [])))
    if retorno:
        lista.insert(0, mudanca_da_pagina("retorno_a_versao_anterior",
                                          trecho_novo=f"texto igual ao da versão {retorno['versao']}, capturada em "
                                                      f"{retorno['capturada_em']} (estado: {retorno['estado']})"))

    mudancas = [m.como_dict() for m in lista]
    riscos = Counter(m["risco"] for m in mudancas)
    relevantes = [m for m in mudancas if m["risco"] != "baixo"]
    indice = indice_de_dependencias(_corpus(), registro.fontes(), _normas())
    afetados = afetados_pela_fonte(indice, fonte["id"], {m["artigo"] for m in relevantes},
                                   norma_inteira=any(m["tipo"] == "indicio_revogacao_total" for m in relevantes))
    regressao = rodar_regressao(afetados, retriever or Retriever()) if afetados else []
    # Só risco baixo é aceito sem pessoa — e nunca um retorno a texto antigo, uma revogação ou a primeira
    # captura de uma página que já chega revogada.
    automatica = not relevantes and not retorno and aceita is not None
    versao = {
        **base,
        "estado": "aceita" if automatica else "pendente_revisao",
        "anterior": aceita["versao"] if aceita else None,
        "releitura": releitura,
        "leitura_anterior": leitura_aceita if releitura else None,
        "mudancas": mudancas,
        "resumo_mudancas": dict(riscos),
        "eventos": eventos.derivar(mudancas),
        "dispositivos_afetados": afetados,
        "regressao": regressao,
        "decisao": {"resultado": "aceita_automaticamente", "responsavel": "monitor (só mudanças de risco baixo)",
                    "em": agora_iso(), "nota": ""} if automatica else None,
    }
    nome_relatorio = f"relatorios/{base['capturada_em'][:10]}-{fonte['id']}-{base['versao']}.md"
    versao["relatorio"] = nome_relatorio
    texto_relatorio = relatorio.gerar(fonte, versao, aceita)
    resumo = {"versao": base["versao"], "estado": versao["estado"], "eventos": versao["eventos"],
              "dispositivos_afetados": afetados, "relatorio": nome_relatorio}
    if simular:
        return concluir("nova_versao", versao["estado"], **resumo, versao_calculada=versao, relatorio_md=texto_relatorio)
    caminho = registro.base / nome_relatorio
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(texto_relatorio, encoding="utf-8")
    registro.registrar_versao(versao, texto)
    return concluir("nova_versao", versao["estado"], **resumo)
