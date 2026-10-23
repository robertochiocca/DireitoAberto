"""Avaliação reproduzível (ver app/avaliacao.py).

    python scripts/avaliar.py              # mede e imprime o relatório
    python scripts/avaliar.py --gravar     # grava docs/avaliacao/resultados.json e relatorio.md
    python scripts/avaliar.py --comparar   # sai com código 1 se alguma métrica piorou em relação ao versionado
    python scripts/avaliar.py --varrer     # refaz a escolha do corte da busca adaptativa (validação cruzada)

Fluxo para mudar a busca, o corpus ou o leitor: rode --comparar antes e depois; se a mudança melhora
algo e piora outra coisa de propósito, explique no commit e regrave a linha de base com --gravar.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.avaliacao import SAIDA, comparar, relatorio_md, rodar


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gravar", action="store_true")
    parser.add_argument("--comparar", action="store_true")
    parser.add_argument("--varrer", action="store_true")
    args = parser.parse_args()
    if args.varrer:
        from app.calibracao import validar

        print(json.dumps(validar(), ensure_ascii=False, indent=2))
        return 0
    resultado = rodar()
    print(relatorio_md(resultado))
    if args.comparar:
        base = json.loads((SAIDA / "resultados.json").read_text(encoding="utf-8"))
        regressoes = comparar(resultado, base)
        if regressoes:
            print("\nREGRESSÕES em relação à linha de base:\n" + "\n".join(f"- {r}" for r in regressoes))
            return 1
        print("\nNenhuma regressão em relação à linha de base.")
    if args.gravar:
        SAIDA.mkdir(parents=True, exist_ok=True)
        (SAIDA / "resultados.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n",
                                                encoding="utf-8")
        (SAIDA / "relatorio.md").write_text(relatorio_md(resultado), encoding="utf-8")
        print(f"\nGravado em {SAIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
