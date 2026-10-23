"""Monitor legislativo: acompanha páginas oficiais e põe mudanças em revisão.

    python scripts/monitor.py verificar                 # todas as fontes (modo controlado)
    python scripts/monitor.py verificar --simular       # calcula tudo e não grava nada
    python scripts/monitor.py verificar --fonte cdc     # uma fonte
    python scripts/monitor.py verificar --fonte cdc --arquivo pagina.htm   # HTML salvo do navegador
    python scripts/monitor.py verificar --json resumo.json                 # resumo para máquina ("-": saída)
    python scripts/monitor.py pendentes
    python scripts/monitor.py decidir --versao <v> --resultado sem_impacto|corpus_atualizado|rejeitada \\
        --responsavel "Nome" --nota "o que foi conferido"
    python scripts/monitor.py reverter --fonte cdc --responsavel "Nome"
    python scripts/monitor.py historico --fonte cdc
    python scripts/monitor.py situacao                  # atualidade de cada fonte
    python scripts/monitor.py fidelidade [--json saida.json]

Códigos de saída de `verificar` (app/monitor/alertas.py): 0 nada a fazer; 1 há revisão humana
pendente; 2 a rodada ficou incompleta (falha de coleta, coleta suspeita ou erro interno).

Modo controlado: grava no registro do monitor (versões, relatórios, alertas), nunca no corpus — levar
uma versão aceita ao corpus é `scripts/corpus.py publicar`. Agendamento: .github/workflows/monitor.yml,
só manual até o mantenedor autorizar o agendamento. O monitor não publica nada sozinho: mudança de
risco médio ou alto fica pendente até a decisão de uma pessoa.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.monitor import alertas, coleta
from app.monitor.fidelidade import verificar_corpus
from app.monitor.registro import DecisaoInvalida, Registro, RegistroAlteradoPorOutroProcesso, RegistroOcupado
from app.monitor.servico import _corpus, verificar
from app.monitor.sinais import fonte_desatualizada, ultimo_sucesso


def _falha(erro: coleta.FalhaDeColeta):
    def falha(_url: str) -> bytes:
        raise erro

    return falha


def _obter(baixar, url: str):
    """Baixa fora da trava (a coleta leva segundos; a decisão humana não precisa esperar por ela)."""
    try:
        bruto = baixar(url)
    except coleta.FalhaDeColeta as exc:
        return _falha(exc), exc
    return (lambda _url: bruto), None


def cmd_verificar(args, registro: Registro) -> int:
    try:
        fontes = [registro.fonte(args.fonte)] if args.fonte else registro.fontes()
    except KeyError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2
    if args.arquivo and len(fontes) != 1:
        print("--arquivo exige --fonte", file=sys.stderr)
        return 2
    baixar = (lambda _url: Path(args.arquivo).read_bytes()) if args.arquivo else coleta.baixar
    resultados: dict[str, dict] = {}
    bloqueados: dict[str, str] = {}  # site → motivo: o portal pediu para parar, e não se insiste nesta rodada
    for i, fonte in enumerate(fontes):
        site = urlsplit(fonte["url"]).hostname or ""
        if site in bloqueados:
            obter = _falha(coleta.FalhaDeColeta(f"não consultada: {site} bloqueou a rodada ({bloqueados[site]})"))
        else:
            if i and not args.arquivo:
                time.sleep(coleta.INTERVALO_S)  # uma página por vez, com intervalo
            try:
                obter, falha = _obter(baixar, fonte["url"])
            except Exception as exc:  # arquivo ausente, URL inválida: a fonte falha, a rodada continua
                obter, falha = _falha(coleta.FalhaDeColeta(f"{type(exc).__name__}: {exc}"[:300])), None
            if falha is not None and falha.bloqueio:
                bloqueados[site] = str(falha)
        try:
            if args.simular:
                r = verificar(fonte, registro, baixar=obter, simular=True)
            else:
                with registro.travar():
                    registro.recarregar()  # uma decisão pode ter sido gravada enquanto a página baixava
                    r = verificar(fonte, registro, baixar=obter)
                    registro.salvar()
        except (RegistroOcupado, RegistroAlteradoPorOutroProcesso) as exc:
            r = {"resultado": "erro_interno", "detalhe": str(exc)}
        except Exception as exc:  # uma fonte com defeito não interrompe as outras
            traceback.print_exc(file=sys.stderr)
            r = {"resultado": "erro_interno", "detalhe": f"{type(exc).__name__}: {exc}"[:300]}
            if not args.simular:
                try:
                    with registro.travar():
                        registro.recarregar()
                        registro.registrar_verificacao(fonte["id"], "erro_interno", r["detalhe"])
                        registro.salvar()
                except (RegistroOcupado, RegistroAlteradoPorOutroProcesso) as erro_registro:
                    r["detalhe"] += f" (e o registro não pôde ser gravado: {erro_registro})"
        resultados[fonte["id"]] = r
        print(f"{fonte['id']:<14} {r['resultado']:<22} {r.get('versao', ''):<19} {r['detalhe']}")
        if args.simular and r.get("versao_calculada"):
            v = r["versao_calculada"]
            for e in v.get("eventos", []):
                print(f"{'':<14} evento: {e['tipo']} — artigos {', '.join(e['artigos'][:10])}"
                      + (f" (+{len(e['artigos']) - 10})" if len(e["artigos"]) > 10 else ""))
            if v.get("dispositivos_afetados"):
                print(f"{'':<14} afetados no corpus: {', '.join(v['dispositivos_afetados'])}")
    if not args.simular:
        registro.recarregar()
    desatualizadas = [d for f in fontes if (d := fonte_desatualizada(f["id"]))] if not args.simular else []
    resumo = alertas.resumir(resultados, registro.pendentes(), desatualizadas, simulacao=args.simular)
    if not args.simular:
        caminho = alertas.gravar(registro.base, resumo)
        print(f"\nalerta: {caminho}")
    if args.json:
        conteudo = json.dumps(resumo, ensure_ascii=False, indent=2) + "\n"
        if args.json == "-":
            sys.stdout.write(conteudo)
        else:
            Path(args.json).write_text(conteudo, encoding="utf-8")
    print(f"código de saída {resumo['codigo_de_saida']}: "
          + {0: "nada a fazer", 1: "há revisão humana pendente", 2: "rodada incompleta (ver falhas)"}[
              resumo["codigo_de_saida"]] + (" — simulação: nada foi gravado" if args.simular else ""))
    return resumo["codigo_de_saida"]


def cmd_pendentes(_args, registro: Registro) -> int:
    pendentes = registro.pendentes()
    if not pendentes:
        print("Nenhuma mudança pendente de revisão.")
    for v in pendentes:
        eventos = ", ".join(e["tipo"] for e in v.get("eventos", [])) or "—"
        print(f"{v['fonte']:<14} {v['versao']}  {v['capturada_em']}  eventos={eventos}  riscos={v['resumo_mudancas']}  "
              f"afetados={v['dispositivos_afetados']}  relatório={v['relatorio']}")
    return 0


def _gravando(registro: Registro, acao) -> int:
    try:
        with registro.travar():
            registro.recarregar()
            mensagem = acao()
            registro.salvar()
    except (DecisaoInvalida, KeyError, RegistroOcupado, RegistroAlteradoPorOutroProcesso) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    print(mensagem)
    return 0


def cmd_decidir(args, registro: Registro) -> int:
    def acao() -> str:
        v = registro.decidir(args.versao, args.resultado, args.responsavel, args.nota or "")
        return f"{v['fonte']} {v['versao']}: {v['estado']}"

    return _gravando(registro, acao)


def cmd_reverter(args, registro: Registro) -> int:
    def acao() -> str:
        v = registro.reverter(args.fonte, args.responsavel, args.nota or "")
        return f"{args.fonte}: versão aceita agora é {v['versao']} ({v['capturada_em']})"

    return _gravando(registro, acao)


def cmd_situacao(_args, registro: Registro) -> int:
    """Atualidade de cada fonte: última verificação, último sucesso e se está desatualizada."""
    for f in registro.fontes():
        ultima = registro.dados["verificacoes"].get(f["id"]) or {}
        atraso = fonte_desatualizada(f["id"])
        marca = "DESATUALIZADA" if atraso else "ok"
        print(f"{f['id']:<14} {marca:<14} último sucesso {ultimo_sucesso(registro.dados, f['id']) or '—':<26} "
              f"última verificação {ultima.get('em', '—')} ({ultima.get('resultado', '—')})")
    return 0


def cmd_historico(args, registro: Registro) -> int:
    aceita = registro.dados["aceitas"].get(args.fonte)
    for v in registro.versoes_da_fonte(args.fonte):
        marca = "*" if v["versao"] == aceita else " "
        print(f"{marca} {v['versao']}  {v['capturada_em']}  {v['estado']:<16} {v.get('resumo_mudancas') or ''}")
    for evento in registro.dados["diario"]:
        if evento["fonte"] == args.fonte:
            print(f"  {evento['em']}  {evento['acao']}  {evento['versao']}  por {evento['responsavel']}: {evento['nota']}")
    return 0


def cmd_fidelidade(args, registro: Registro) -> int:
    resultados = verificar_corpus(_corpus(), registro)
    for r in sorted(resultados, key=lambda x: x["cobertura"]):
        sintese = " (marcado como síntese)" if r["marcado_como_sintese"] else ""
        print(f"{r['id']:<22} {r['cobertura']:>6.1%}  {r['classe']:<14} {r['artigo']}{sintese}")
    contagem = Counter(r["classe"] for r in resultados)
    print(f"\n{len(resultados)} dispositivos conferidos: " + ", ".join(f"{k} {v}" for k, v in contagem.items()))
    if args.json:
        Path(args.json).write_text(json.dumps(resultados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="comando", required=True)
    p = sub.add_parser("verificar")
    p.add_argument("--fonte")
    p.add_argument("--arquivo", help="HTML salvo do navegador, no lugar de baixar a página")
    p.add_argument("--simular", action="store_true", help="calcula diferenças, eventos e afetados sem gravar nada")
    p.add_argument("--json", help="grava o resumo da rodada neste arquivo ('-' para a saída padrão)")
    sub.add_parser("pendentes")
    p = sub.add_parser("decidir")
    p.add_argument("--versao", required=True)
    p.add_argument("--resultado", required=True, choices=["sem_impacto", "corpus_atualizado", "rejeitada"])
    p.add_argument("--responsavel", required=True)
    p.add_argument("--nota")
    p = sub.add_parser("reverter")
    p.add_argument("--fonte", required=True)
    p.add_argument("--responsavel", required=True)
    p.add_argument("--nota")
    p = sub.add_parser("historico")
    p.add_argument("--fonte", required=True)
    p = sub.add_parser("fidelidade")
    p.add_argument("--json")
    sub.add_parser("situacao")
    args = parser.parse_args()
    registro = Registro()
    comandos = {"verificar": cmd_verificar, "pendentes": cmd_pendentes, "decidir": cmd_decidir,
                "reverter": cmd_reverter, "historico": cmd_historico, "fidelidade": cmd_fidelidade,
                "situacao": cmd_situacao}
    try:
        return comandos[args.comando](args, registro)
    except Exception:
        # 1 quer dizer "há revisão pendente"; um defeito do próprio monitor é rodada incompleta.
        traceback.print_exc(file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
