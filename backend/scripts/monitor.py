"""Monitor legislativo: acompanha páginas oficiais e põe mudanças em revisão.

    python scripts/monitor.py verificar                 # todas as fontes
    python scripts/monitor.py verificar --fonte cdc     # uma fonte
    python scripts/monitor.py verificar --fonte cdc --arquivo pagina.htm   # HTML salvo do navegador
    python scripts/monitor.py pendentes
    python scripts/monitor.py decidir --versao <v> --resultado sem_impacto|corpus_atualizado|rejeitada \\
        --responsavel "Nome" --nota "o que foi conferido"
    python scripts/monitor.py reverter --fonte cdc --responsavel "Nome"
    python scripts/monitor.py historico --fonte cdc
    python scripts/monitor.py fidelidade [--json saida.json]

Agendamento: rode `verificar` pelo agendador do servidor (cron, GitHub Actions…). O monitor não
publica nada sozinho: mudança de risco médio ou alto fica pendente até a decisão de uma pessoa.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.monitor import coleta
from app.monitor.fidelidade import verificar_corpus
from app.monitor.registro import DecisaoInvalida, Registro
from app.monitor.servico import _corpus, verificar


def cmd_verificar(args, registro: Registro) -> int:
    fontes = [registro.fonte(args.fonte)] if args.fonte else registro.fontes()
    if args.arquivo and len(fontes) != 1:
        print("--arquivo exige --fonte", file=sys.stderr)
        return 2
    baixar = (lambda _url: Path(args.arquivo).read_bytes()) if args.arquivo else coleta.baixar
    for i, fonte in enumerate(fontes):
        if i and not args.arquivo:
            time.sleep(coleta.INTERVALO_S)  # uma página por vez, com intervalo
        r = verificar(fonte, registro, baixar=baixar)
        registro.salvar()
        print(f"{fonte['id']:<14} {r['resultado']:<22} {r.get('versao', ''):<17} {r['detalhe']}")
    return 0


def cmd_pendentes(_args, registro: Registro) -> int:
    pendentes = registro.pendentes()
    if not pendentes:
        print("Nenhuma mudança pendente de revisão.")
    for v in pendentes:
        print(f"{v['fonte']:<14} {v['versao']}  {v['capturada_em']}  riscos={v['resumo_mudancas']}  "
              f"afetados={v['dispositivos_afetados']}  relatório={v['relatorio']}")
    return 0


def cmd_decidir(args, registro: Registro) -> int:
    try:
        v = registro.decidir(args.versao, args.resultado, args.responsavel, args.nota or "")
    except (DecisaoInvalida, KeyError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    registro.salvar()
    print(f"{v['fonte']} {v['versao']}: {v['estado']}")
    return 0


def cmd_reverter(args, registro: Registro) -> int:
    try:
        v = registro.reverter(args.fonte, args.responsavel, args.nota or "")
    except DecisaoInvalida as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    registro.salvar()
    print(f"{args.fonte}: versão aceita agora é {v['versao']} ({v['capturada_em']})")
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
    args = parser.parse_args()
    registro = Registro()
    comandos = {"verificar": cmd_verificar, "pendentes": cmd_pendentes, "decidir": cmd_decidir,
                "reverter": cmd_reverter, "historico": cmd_historico, "fidelidade": cmd_fidelidade}
    return comandos[args.comando](args, registro)


if __name__ == "__main__":
    raise SystemExit(main())
