"""Proveniência e integridade do corpus jurídico (data/legislacao.json).

    python scripts/corpus.py normas                     # refaz data/normas.json a partir das páginas oficiais
    python scripts/corpus.py extrair --responsavel "Nome" --motivo "por quê" [--incluir-linha-de-base]
        # recalcula trechos oficiais, natureza do texto e lacunas a partir das versões ACEITAS do monitor
        # e registra no histórico cada entrada que mudou. Fonte cuja versão aceita ainda é a linha de base
        # (primeira captura, não revisada por pessoa) fica de fora, a menos que se peça
    python scripts/corpus.py publicar --fonte cdc --versao <v> --responsavel "Nome" --motivo "por quê"
        # leva ao corpus uma versão do monitor DECIDIDA POR PESSOA: recalcula só as entradas que dependem
        # da fonte, confere os trechos, roda a regressão da busca e registra no histórico com a versão
    python scripts/corpus.py registrar --responsavel "Nome" --motivo "por quê" [--evidencia URL ...]
        # depois de editar legislacao.json à mão: registra no histórico o que mudou
    python scripts/corpus.py abrir-revisao --id cdc-18 --responsavel "Nome" --motivo "por quê" [--evidencia ...]
        # marca a entrada como em revisão (o texto não muda) — é o que a triagem de feedback usa
    python scripts/corpus.py verificar                  # integridade: selos, trechos, natureza; sai com 1 se falhar
    python scripts/corpus.py historico [--id cf-7-xiii]
    python scripts/corpus.py reverter --id cf-7-xiii --responsavel "Nome" --motivo "por quê"

Nenhuma alteração entra sem responsável e motivo, e o histórico guarda o selo (hash) anterior e o novo
de cada entrada. O monitor não altera o corpus: uma versão nova da fonte só chega aqui quando uma
pessoa a aceita (scripts/monitor.py decidir) e roda `publicar`. Quem escreve no corpus segura a trava
`data/.corpus.lock`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.corpus import normas as normas_mod
from app.corpus.proveniencia import (
    CAMPOS_DE_PROVENIENCIA,
    Fontes,
    carregar_historico,
    conferir_trechos,
    divergencias,
    proveniencia,
    registrar,
    selo,
    versao_anterior,
)
from app.monitor.impacto import rodar_regressao
from app.monitor.registro import Registro, RegistroAlteradoPorOutroProcesso, RegistroOcupado, trava_exclusiva
from app.retrieval import DATA_PATH, Retriever
from app.vigencia import hoje

DADOS = Path(DATA_PATH).parent
HISTORICO = DADOS / "corpus_historico.json"
LOJA = DADOS / "corpus_versoes"
NORMAS = DADOS / "normas.json"
SEM_COLETA = DADOS / "normas_sem_coleta.json"
TRAVA = DADOS / ".corpus.lock"


def _ler(caminho: Path) -> dict:
    return json.loads(caminho.read_text(encoding="utf-8"))


def _gravar(caminho: Path, dados: dict) -> None:
    """Escrita atômica (arquivo temporário + troca): a API lê o corpus enquanto ele é gravado."""
    with tempfile.NamedTemporaryFile("w", dir=caminho.parent, delete=False, encoding="utf-8", suffix=".tmp") as tmp:
        tmp.write(json.dumps(dados, ensure_ascii=False, indent=2) + "\n")
    mascara = os.umask(0)
    os.umask(mascara)
    os.chmod(tmp.name, 0o666 & ~mascara)
    Path(tmp.name).replace(caminho)


def _agora() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _fontes(registro: Registro) -> Fontes:
    sem_coleta = _ler(SEM_COLETA)["normas"] if SEM_COLETA.exists() else []
    return Fontes(registro, sem_coleta)


def cmd_normas(_args, registro: Registro) -> int:
    sem_coleta = _ler(SEM_COLETA)["normas"] if SEM_COLETA.exists() else []
    lista = normas_mod.montar(registro, sem_coleta)
    _gravar(NORMAS, {
        "sobre": ("Normas do corpus. As monitoradas têm tipo, número e data lidos da página oficial "
                  "(campo evidencia); as demais vêm de data/normas_sem_coleta.json. Gerado por scripts/corpus.py normas."),
        "normas": lista,
    })
    print(f"{len(lista)} normas em {NORMAS.name}")
    return 0


def fontes_da_entrada(art: dict, fontes: Fontes) -> set[str]:
    """Fontes monitoradas de que a entrada depende: a própria norma e as dos dispositivos adicionais."""
    propria = art.get("norma") if art.get("norma") in fontes.por_id else (fontes.da_url(art.get("fonte", "")) or {}).get("id")
    return {f for f in [propria, *(a.get("norma") for a in art.get("dispositivos_adicionais", []))] if f in fontes.por_id}


def _recalcular(art: dict, fontes: Fontes) -> None:
    for campo in CAMPOS_DE_PROVENIENCIA:
        art.pop(campo, None)
    art.update(proveniencia(art, fontes, hoje()))


def cmd_extrair(args, registro: Registro) -> int:
    with trava_exclusiva(TRAVA):
        dados = _ler(Path(DATA_PATH))
        fontes = _fontes(registro)
        # Versão aceita sem decisão de uma pessoa: a linha de base (primeira captura) e a aceita
        # automaticamente (só mudanças de risco baixo) — as mesmas que `publicar` recusa.
        nao_revisadas = {f for f in fontes.por_id
                         if (v := registro.versao_aceita(f)) is not None and registro.publicavel(v["versao"])}
        pulados: dict[str, set[str]] = {}
        for art in dados["artigos"]:
            if (base := fontes_da_entrada(art, fontes) & nao_revisadas) and not args.incluir_linha_de_base:
                pulados[art["id"]] = base
                continue
            _recalcular(art, fontes)
        historico = carregar_historico(HISTORICO)
        eventos = registrar(dados["artigos"], historico, LOJA, responsavel=args.responsavel,
                            motivo=args.motivo, em=_agora(), evidencia=args.evidencia)
        _gravar(Path(DATA_PATH), dados)
        _gravar(HISTORICO, historico)
    print(f"{len(eventos)} entradas registradas no histórico")
    if pulados:
        print(f"{len(pulados)} entradas não recalculadas: dependem de fonte cuja versão aceita não foi decidida por "
              f"pessoa ({', '.join(sorted(set().union(*pulados.values())))}). Revise a fonte (monitor.py decidir) "
              "ou rode com --incluir-linha-de-base para recalculá-las assim mesmo.")
    return 0


def cmd_publicar(args, registro: Registro) -> int:
    """Leva ao corpus uma versão do monitor aceita por pessoa — só as entradas que dependem da fonte."""
    def erro(mensagem: str) -> int:
        print(f"erro: {mensagem}", file=sys.stderr)
        return 1

    try:
        with registro.travar(), trava_exclusiva(TRAVA):
            registro.recarregar()
            try:
                v = registro.versao(args.versao)
            except KeyError:
                return erro(f"versão desconhecida: {args.versao}")
            if v["fonte"] != args.fonte:
                return erro(f"a versão {args.versao} é da fonte {v['fonte']}, não de {args.fonte}")
            if motivo := registro.publicavel(args.versao):
                return erro(motivo)
            dados = _ler(Path(DATA_PATH))
            historico = carregar_historico(HISTORICO)
            if soltas := divergencias(dados["artigos"], historico):
                return erro("o corpus tem alterações não registradas no histórico; registre-as antes "
                            f"(corpus.py registrar): {'; '.join(soltas[:5])}")
            fontes = _fontes(registro)
            alvo = [a for a in dados["artigos"] if args.fonte in fontes_da_entrada(a, fontes)]
            if not alvo:
                print(f"nenhuma entrada do corpus usa a fonte {args.fonte}: nada a publicar")
                return 0
            for art in alvo:
                _recalcular(art, fontes)
            problemas = conferir_trechos(alvo, fontes) + [
                f"{a['id']}: texto marcado como {a['texto_natureza']} sem trecho oficial que o sustente"
                for a in alvo if a.get("texto_natureza") in ("consolidado", "literal") and not a.get("trechos_oficiais")]
            if problemas:
                return erro("a conferência dos trechos falhou; nada foi gravado:\n  " + "\n  ".join(problemas))
            with tempfile.TemporaryDirectory() as pasta:
                provisorio = Path(pasta) / "legislacao.json"
                _gravar(provisorio, dados)
                regressao = rodar_regressao([a["id"] for a in alvo], Retriever(provisorio))
            falhas = [r for r in regressao if not r["ok"]]
            resultado = f"regressão {len(regressao) - len(falhas)}/{len(regressao)}"
            if falhas and not args.aceitar_falha_de_regressao:
                return erro(f"{resultado}; nada foi gravado. Perguntas que perderam o dispositivo esperado:\n  "
                            + "\n  ".join(f"{r['pergunta']!r} → {r['esperado']}" for r in falhas))
            eventos = registrar(dados["artigos"], historico, LOJA, responsavel=args.responsavel,
                                motivo=f"{args.motivo} [publicação da versão {args.versao} de {args.fonte} pelo monitor; "
                                       f"{resultado}" + ("; falhas aceitas pelo responsável" if falhas else "") + "]",
                                em=_agora(),
                                evidencia=[v["url"], f"monitor:{args.fonte}:{args.versao}", *filter(None, [v.get("relatorio")])])
            _gravar(Path(DATA_PATH), dados)
            _gravar(HISTORICO, historico)
            registro.anotar_publicacao(args.fonte, args.versao, args.responsavel,
                                       f"{len(eventos)} entradas alteradas de {len(alvo)} recalculadas; {resultado}")
            try:
                registro.salvar()
            except (OSError, RegistroAlteradoPorOutroProcesso) as exc:
                return erro(f"o corpus e o histórico do corpus FORAM gravados ({len(eventos)} entradas), mas a anotação "
                            f"da publicação no diário do monitor falhou: {exc}. Anote à mão ou rode de novo.")
    except (RegistroOcupado, RegistroAlteradoPorOutroProcesso) as exc:
        return erro(str(exc))
    for e in eventos:
        print(f"{e['id']:<18} {e['acao']}  [{', '.join(e['campos'])}]")
    print(f"{len(eventos)} entradas alteradas de {len(alvo)} recalculadas; {resultado}")
    return 0


def cmd_registrar(args, _registro: Registro) -> int:
    with trava_exclusiva(TRAVA):
        dados = _ler(Path(DATA_PATH))
        historico = carregar_historico(HISTORICO)
        eventos = registrar(dados["artigos"], historico, LOJA, responsavel=args.responsavel, motivo=args.motivo,
                            em=_agora(), evidencia=args.evidencia)
        _gravar(HISTORICO, historico)
    for e in eventos:
        print(f"{e['id']:<18} {e['acao']}")
    print(f"{len(eventos)} entradas registradas")
    return 0


def cmd_reverter(args, _registro: Registro) -> int:
    """Devolve a entrada ao conteúdo anterior à última alteração — e registra a reversão como alteração."""
    with trava_exclusiva(TRAVA):
        dados = _ler(Path(DATA_PATH))
        historico = carregar_historico(HISTORICO)
        anterior = versao_anterior(historico, LOJA, args.id)
        if anterior is None:
            print(f"erro: {args.id} não tem alteração registrada para reverter", file=sys.stderr)
            return 1
        dados["artigos"] = [anterior if a["id"] == args.id else a for a in dados["artigos"]]
        registrar(dados["artigos"], historico, LOJA, responsavel=args.responsavel,
                  motivo=f"reversão: {args.motivo}", em=_agora())
        _gravar(Path(DATA_PATH), dados)
        _gravar(HISTORICO, historico)
    print(f"{args.id}: revertida para o selo {selo(anterior)[:16]}")
    return 0


def cmd_abrir_revisao(args, _registro: Registro) -> int:
    """Marca a entrada como em revisão — a API passa a avisar — sem mudar o texto, e registra no histórico."""
    with trava_exclusiva(TRAVA):
        dados = _ler(Path(DATA_PATH))
        historico = carregar_historico(HISTORICO)
        if soltas := divergencias(dados["artigos"], historico):
            print(f"erro: o corpus tem alterações não registradas: {'; '.join(soltas[:5])}", file=sys.stderr)
            return 1
        art = next((a for a in dados["artigos"] if a["id"] == args.id), None)
        if art is None:
            print(f"erro: {args.id} não existe no corpus", file=sys.stderr)
            return 1
        aberta = art.get("revisao") if (art.get("revisao") or {}).get("estado") == "pendente" else None
        art["revisao"] = {
            "estado": "pendente",
            "motivo": f"{aberta['motivo']} | {args.motivo}" if aberta else args.motivo,
            "evidencia": [*(aberta or {}).get("evidencia", []), *args.evidencia],
            "aberta_em": (aberta or {}).get("aberta_em") or hoje().isoformat(),
        }
        registrar(dados["artigos"], historico, LOJA, responsavel=args.responsavel,
                  motivo=f"revisão aberta: {args.motivo}", em=_agora(), evidencia=args.evidencia)
        _gravar(Path(DATA_PATH), dados)
        _gravar(HISTORICO, historico)
    print(f"{args.id}: em revisão")
    return 0


def problemas_de_integridade(registro: Registro) -> list[str]:
    dados = _ler(Path(DATA_PATH))
    fontes = _fontes(registro)
    problemas = divergencias(dados["artigos"], carregar_historico(HISTORICO))
    problemas += conferir_trechos(dados["artigos"], fontes)
    for art in dados["artigos"]:
        if art.get("texto_natureza") in ("consolidado", "literal") and not art.get("trechos_oficiais"):
            problemas.append(f"{art['id']}: texto marcado como {art['texto_natureza']} sem trecho oficial que o sustente")
    return problemas


def cmd_verificar(_args, registro: Registro) -> int:
    problemas = problemas_de_integridade(registro)
    for p in problemas:
        print(f"✗ {p}")
    if not problemas:
        print("✓ corpus íntegro: selos conferem com o histórico e os trechos oficiais com as fontes")
    return 1 if problemas else 0


def cmd_historico(args, _registro: Registro) -> int:
    historico = carregar_historico(HISTORICO)
    for e in historico["eventos"]:
        if args.id and e["id"] != args.id:
            continue
        campos = f" [{', '.join(e['campos'])}]" if e["campos"] else ""
        print(f"{e['em']}  {e['id']:<18} {e['acao']:<9}{campos}  por {e['responsavel']}: {e['motivo']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("normas")
    for nome in ("extrair", "registrar"):
        p = sub.add_parser(nome)
        p.add_argument("--responsavel", required=True)
        p.add_argument("--motivo", required=True)
        p.add_argument("--evidencia", action="append", default=[])
        if nome == "extrair":
            p.add_argument("--incluir-linha-de-base", "--incluir-nao-revisadas", dest="incluir_linha_de_base",
                           action="store_true",
                           help="recalcula também entradas de fontes cuja versão aceita não foi decidida por pessoa "
                                "(linha de base ou aceita automaticamente)")
    p = sub.add_parser("publicar")
    p.add_argument("--fonte", required=True)
    p.add_argument("--versao", required=True)
    p.add_argument("--responsavel", required=True)
    p.add_argument("--motivo", required=True)
    p.add_argument("--aceitar-falha-de-regressao", action="store_true",
                   help="grava mesmo se a regressão da busca falhar (a falha fica registrada no histórico)")
    p = sub.add_parser("reverter")
    p.add_argument("--id", required=True)
    p.add_argument("--responsavel", required=True)
    p.add_argument("--motivo", required=True)
    p = sub.add_parser("abrir-revisao")
    p.add_argument("--id", required=True)
    p.add_argument("--responsavel", required=True)
    p.add_argument("--motivo", required=True)
    p.add_argument("--evidencia", action="append", default=[])
    sub.add_parser("verificar")
    p = sub.add_parser("historico")
    p.add_argument("--id")
    args = parser.parse_args(argv)
    comandos = {"normas": cmd_normas, "extrair": cmd_extrair, "registrar": cmd_registrar, "publicar": cmd_publicar,
                "abrir-revisao": cmd_abrir_revisao,
                "verificar": cmd_verificar, "historico": cmd_historico, "reverter": cmd_reverter}
    return comandos[args.comando](args, Registro())


if __name__ == "__main__":
    raise SystemExit(main())
