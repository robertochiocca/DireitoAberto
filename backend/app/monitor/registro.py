"""Registro de versões das fontes monitoradas, com fila de revisão e reversão.

Arquivos (em `DIREITO_ABERTO_MONITOR_DIR`, padrão `backend/data/monitor/`):

- `fontes.json` — o que é monitorado (identificador, nome, URL, órgão emissor);
- `registro.json` — versões, ponteiro da versão aceita de cada fonte, últimas verificações e o
  diário de decisões;
- `snapshots/<fonte>/<versao>.txt.gz` — o texto vigente de cada versão (o que foi comparado);
- `relatorios/*.md` — o relatório de cada versão nova.

Estados de uma versão: `linha_de_base` (primeira captura, não revisada), `pendente_revisao`,
`aceita` (por pessoa, ou automaticamente quando todas as mudanças são de baixo risco) e
`rejeitada` (falso positivo; a versão aceita não muda). Reverter volta o ponteiro para a versão
aceita anterior — o histórico nunca é apagado.
"""

from __future__ import annotations

import gzip
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DIR_PADRAO = Path(__file__).resolve().parent.parent.parent / "data" / "monitor"

ESTADOS_VALIDOS_PARA_BASE = ("linha_de_base", "aceita")
DECISOES = {
    "sem_impacto": "aceita",          # a mudança foi conferida e não exige mexer na base
    "corpus_atualizado": "aceita",    # a base foi atualizada de acordo com a mudança
    "rejeitada": "rejeitada",         # falso positivo (página com erro, coleta ruim)
}
MAX_VERIFICACOES_NO_DIARIO = 200


def diretorio() -> Path:
    return Path(os.environ.get("DIREITO_ABERTO_MONITOR_DIR", DIR_PADRAO))


def agora_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class DecisaoInvalida(ValueError):
    pass


class Registro:
    def __init__(self, base: Path | None = None):
        self.base = Path(base or diretorio())
        self.caminho = self.base / "registro.json"
        if self.caminho.exists():
            self.dados = json.loads(self.caminho.read_text(encoding="utf-8"))
        else:
            self.dados = {"aceitas": {}, "versoes": [], "verificacoes": {}, "diario": []}

    # ------------------------------------------------------------ fontes
    def fontes(self) -> list[dict]:
        caminho = self.base / "fontes.json"
        if not caminho.exists():
            return []
        return json.loads(caminho.read_text(encoding="utf-8"))["fontes"]

    def fonte(self, fonte_id: str) -> dict:
        for f in self.fontes():
            if f["id"] == fonte_id:
                return f
        raise KeyError(f"fonte desconhecida: {fonte_id}")

    # ------------------------------------------------------------ persistência
    def salvar(self) -> None:
        self.base.mkdir(parents=True, exist_ok=True)
        # Escrita atômica: a API pode estar lendo o arquivo enquanto o monitor grava.
        with tempfile.NamedTemporaryFile("w", dir=self.base, delete=False, encoding="utf-8", suffix=".tmp") as tmp:
            json.dump(self.dados, tmp, ensure_ascii=False, indent=2)
            tmp.write("\n")
        Path(tmp.name).replace(self.caminho)

    def caminho_snapshot(self, fonte_id: str, versao: str) -> Path:
        return self.base / "snapshots" / fonte_id / f"{versao}.txt.gz"

    def gravar_snapshot(self, fonte_id: str, versao: str, texto: str) -> None:
        caminho = self.caminho_snapshot(fonte_id, versao)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        # mtime=0: o mesmo texto gera sempre o mesmo arquivo (diffs limpos no git).
        with open(caminho, "wb") as bruto, gzip.GzipFile(fileobj=bruto, mode="wb", mtime=0) as gz:
            gz.write(texto.encode("utf-8"))

    def ler_snapshot(self, fonte_id: str, versao: str) -> str:
        with gzip.open(self.caminho_snapshot(fonte_id, versao), "rt", encoding="utf-8") as gz:
            return gz.read()

    # ------------------------------------------------------------ consultas
    def versao(self, versao: str) -> dict:
        for v in self.dados["versoes"]:
            if v["versao"] == versao:
                return v
        raise KeyError(f"versão desconhecida: {versao}")

    def versao_aceita(self, fonte_id: str) -> dict | None:
        atual = self.dados["aceitas"].get(fonte_id)
        return self.versao(atual) if atual else None

    def versoes_da_fonte(self, fonte_id: str) -> list[dict]:
        return [v for v in self.dados["versoes"] if v["fonte"] == fonte_id]

    def pendentes(self) -> list[dict]:
        return [v for v in self.dados["versoes"] if v["estado"] == "pendente_revisao"]

    # ------------------------------------------------------------ escrita
    def registrar_verificacao(self, fonte_id: str, resultado: str, detalhe: str = "") -> None:
        self.dados["verificacoes"][fonte_id] = {"em": agora_iso(), "resultado": resultado, "detalhe": detalhe}

    def registrar_versao(self, registro_versao: dict, texto: str) -> None:
        self.gravar_snapshot(registro_versao["fonte"], registro_versao["versao"], texto)
        self.dados["versoes"].append(registro_versao)
        if registro_versao["estado"] in ESTADOS_VALIDOS_PARA_BASE:
            self.dados["aceitas"][registro_versao["fonte"]] = registro_versao["versao"]

    def _anotar(self, acao: str, fonte_id: str, versao: str, responsavel: str, nota: str = "") -> None:
        self.dados["diario"].append({"em": agora_iso(), "acao": acao, "fonte": fonte_id, "versao": versao,
                                     "responsavel": responsavel, "nota": nota})

    def decidir(self, versao: str, resultado: str, responsavel: str, nota: str = "") -> dict:
        """Revisão humana de uma versão pendente."""
        if resultado not in DECISOES:
            raise DecisaoInvalida(f"resultado deve ser um de: {', '.join(DECISOES)}")
        if not responsavel.strip():
            raise DecisaoInvalida("informe quem revisou (responsavel)")
        v = self.versao(versao)
        if v["estado"] != "pendente_revisao":
            raise DecisaoInvalida(f"a versão {versao} não está pendente (estado: {v['estado']})")
        v["estado"] = DECISOES[resultado]
        v["decisao"] = {"resultado": resultado, "responsavel": responsavel, "em": agora_iso(), "nota": nota}
        if v["estado"] == "aceita":
            self.dados["aceitas"][v["fonte"]] = versao
        self._anotar(f"decisao:{resultado}", v["fonte"], versao, responsavel, nota)
        return v

    def reverter(self, fonte_id: str, responsavel: str, nota: str = "") -> dict:
        """Volta a versão aceita da fonte para a anterior a ela. Nada é apagado."""
        atual = self.versao_aceita(fonte_id)
        if atual is None or not atual.get("anterior"):
            raise DecisaoInvalida(f"não há versão anterior aceita para {fonte_id}")
        anterior = self.versao(atual["anterior"])
        self.dados["aceitas"][fonte_id] = anterior["versao"]
        self._anotar("reversao", fonte_id, anterior["versao"], responsavel,
                     nota or f"revertida a versão {atual['versao']}")
        return anterior
