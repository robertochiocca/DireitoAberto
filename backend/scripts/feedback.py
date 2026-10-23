"""Triagem humana do feedback de quem usa (app/feedback.py).

    python scripts/feedback.py listar [--estado novo] [--limite 50]
    python scripts/feedback.py resumo                   # o que está na fila, por dispositivo e categoria
    python scripts/feedback.py triar --id 12 --resultado procedente|improcedente|duplicado \\
        --responsavel "Nome" --nota "o que foi conferido" [--abrir-revisao]

Feedback não muda nada sozinho: nem o texto da base, nem a vigência, nem a confiança. `--abrir-revisao`
(só com resultado procedente) marca a entrada do corpus como **em revisão** — a resposta passa a avisar
que o dispositivo está sendo conferido — e registra isso no histórico do corpus, com o responsável e a
nota. Corrigir o texto continua sendo edição + `scripts/corpus.py registrar`, por pessoa.

Usa o banco configurado em DIREITO_ABERTO_DATABASE_URL, como a API.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select

from app.db import Feedback, SessionLocal, agora, init_db
from app.feedback import CATEGORIAS, ESTADOS


def cmd_listar(args) -> int:
    with SessionLocal() as db:
        consulta = select(Feedback).order_by(Feedback.criado_em.desc()).limit(args.limite)
        if args.estado:
            consulta = consulta.where(Feedback.estado == args.estado)
        for f in db.scalars(consulta):
            comentario = (f.comentario or "—")[:120]
            print(f"#{f.id:<5} {f.criado_em:%Y-%m-%d}  {f.estado:<12} {f.dispositivo_id:<18} {f.categoria:<28} {comentario}")
    return 0


def cmd_resumo(_args) -> int:
    with SessionLocal() as db:
        novos = db.scalars(select(Feedback).where(Feedback.estado == "novo")).all()
    if not novos:
        print("Nenhum feedback na fila.")
        return 0
    contagem = Counter((f.dispositivo_id, f.categoria) for f in novos)
    print("Fila de triagem (só prioriza: nenhuma contagem muda a base sozinha)")
    for (dispositivo, categoria), n in contagem.most_common():
        print(f"{n:>4}  {dispositivo:<18} {CATEGORIAS.get(categoria, categoria)}")
    return 0


def cmd_triar(args) -> int:
    if args.abrir_revisao and args.resultado != "procedente":
        print("erro: --abrir-revisao só com resultado procedente", file=sys.stderr)
        return 1
    if not args.responsavel.strip() or not args.nota.strip():
        print("erro: informe o responsável e a nota da triagem", file=sys.stderr)
        return 1
    with SessionLocal() as db:
        f = db.get(Feedback, args.id)
        if f is None:
            print(f"erro: feedback #{args.id} não existe", file=sys.stderr)
            return 1
        if f.estado != "novo":
            print(f"erro: feedback #{args.id} já foi triado ({f.estado})", file=sys.stderr)
            return 1
        if args.abrir_revisao:
            import corpus as corpus_cli  # scripts/corpus.py: trava, histórico e responsável

            motivo = (f"feedback #{f.id} ({CATEGORIAS.get(f.categoria, f.categoria)}) considerado procedente na "
                      f"triagem: {args.nota}")
            codigo = corpus_cli.main(["abrir-revisao", "--id", f.dispositivo_id, "--responsavel", args.responsavel,
                                      "--motivo", motivo, "--evidencia", f"feedback:{f.id}"])
            if codigo:
                return codigo  # a triagem não é gravada se a revisão não abriu
        f.estado, f.triado_em, f.triado_por, f.nota_da_triagem = args.resultado, agora(), args.responsavel, args.nota
        db.commit()
        print(f"feedback #{f.id}: {f.estado}" + (" — entrada marcada em revisão no corpus" if args.abrir_revisao else ""))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="comando", required=True)
    p = sub.add_parser("listar")
    p.add_argument("--estado", choices=ESTADOS)
    p.add_argument("--limite", type=int, default=50)
    sub.add_parser("resumo")
    p = sub.add_parser("triar")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--resultado", required=True, choices=[e for e in ESTADOS if e != "novo"])
    p.add_argument("--responsavel", required=True)
    p.add_argument("--nota", required=True)
    p.add_argument("--abrir-revisao", action="store_true")
    args = parser.parse_args(argv)
    init_db()
    return {"listar": cmd_listar, "resumo": cmd_resumo, "triar": cmd_triar}[args.comando](args)


if __name__ == "__main__":
    raise SystemExit(main())
