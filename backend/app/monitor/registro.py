"""Registro de versões das fontes monitoradas, com fila de revisão e reversão.

Arquivos (em `DIREITO_ABERTO_MONITOR_DIR`, padrão `backend/data/monitor/`):

- `fontes.json` — o que é monitorado (identificador, nome, URL, órgão emissor);
- `registro.json` — versões, ponteiro da versão aceita de cada fonte, últimas verificações e o
  diário de decisões;
- `snapshots/<fonte>/<versao>.txt.gz` — o texto vigente de cada versão (o que foi comparado);
- `relatorios/*.md` — o relatório de cada versão nova.

Estados de uma versão: `linha_de_base` (primeira captura, não revisada), `pendente_revisao`,
`aceita` (por pessoa, ou automaticamente quando todas as mudanças são de baixo risco),
`rejeitada` (falso positivo; a versão aceita não muda) e `superada` (aceita por pessoa depois que
uma versão mais nova já tinha sido aceita: a decisão fica registrada, o ponteiro não volta no tempo).
Reverter volta o ponteiro para a versão aceita anterior — o histórico nunca é apagado.

Concorrência: uma verificação agendada e uma decisão humana ao mesmo tempo perdiam uma das duas
escritas. Agora quem escreve segura uma trava exclusiva (`travar`, `fcntl.flock` num arquivo ao lado
do registro) e, ao gravar, confere o contador `revisao`: se outro processo gravou desde a leitura, a
gravação é recusada em vez de sobrescrever (`RegistroAlteradoPorOutroProcesso`).
"""

from __future__ import annotations

import contextlib
import gzip
import json
import os
import tempfile
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows: sem trava entre processos (o monitor roda em Linux)
    fcntl = None  # type: ignore[assignment]

DIR_PADRAO = Path(__file__).resolve().parent.parent.parent / "data" / "monitor"

ESTADOS_VALIDOS_PARA_BASE = ("linha_de_base", "aceita")
DECISOES = {
    "sem_impacto": "aceita",          # a mudança foi conferida e não exige mexer na base
    "corpus_atualizado": "aceita",    # a base foi atualizada de acordo com a mudança
    "rejeitada": "rejeitada",         # falso positivo (página com erro, coleta ruim)
}
# Resultados de verificação em que a página veio e foi lida: contam para a atualidade da fonte.
SUCESSO = ("sem_mudanca", "linha_de_base", "nova_versao", "versao_ja_registrada")
MAX_VERIFICACOES_POR_FONTE = 30
ESPERA_TRAVA_S = float(os.environ.get("DIREITO_ABERTO_MONITOR_TRAVA_S", 30))


def diretorio() -> Path:
    return Path(os.environ.get("DIREITO_ABERTO_MONITOR_DIR", DIR_PADRAO))


def agora_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class DecisaoInvalida(ValueError):
    pass


class RegistroOcupado(RuntimeError):
    """Outro processo (verificação ou decisão) está escrevendo no registro."""


class RegistroAlteradoPorOutroProcesso(RuntimeError):
    """O arquivo mudou no disco desde a leitura: gravar agora apagaria a escrita do outro processo."""


@contextlib.contextmanager
def trava_exclusiva(caminho: Path, espera_s: float = ESPERA_TRAVA_S) -> Iterator[None]:
    """Trava exclusiva entre processos num arquivo (`fcntl.flock`); `RegistroOcupado` depois de `espera_s`."""
    if fcntl is None:
        yield
        return
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "a+") as arquivo:
        prazo = time.monotonic() + espera_s
        while True:
            try:
                fcntl.flock(arquivo, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= prazo:
                    raise RegistroOcupado(f"outro processo está escrevendo ({caminho.name}); tente de novo em instantes"
                                          ) from None
                time.sleep(0.2)
        try:
            yield
        finally:
            fcntl.flock(arquivo, fcntl.LOCK_UN)


def _modo_de_arquivo() -> int:
    """0644 com a umask usual: o arquivo temporário nasce 0600 e o registro ficava ilegível para o
    serviço da API rodando com outro usuário."""
    mascara = os.umask(0)
    os.umask(mascara)
    return 0o666 & ~mascara


class Registro:
    def __init__(self, base: Path | None = None):
        self.base = Path(base or diretorio())
        self.caminho = self.base / "registro.json"
        self._profundidade_trava = 0
        self.recarregar()

    def recarregar(self) -> None:
        if self.caminho.exists():
            self.dados = json.loads(self.caminho.read_text(encoding="utf-8"))
        else:
            self.dados = {"aceitas": {}, "versoes": [], "verificacoes": {}, "diario": []}
        self._revisao = self.dados.get("revisao", 0)

    @contextlib.contextmanager
    def travar(self, espera_s: float | None = None) -> Iterator[Registro]:
        """Trava exclusiva entre processos; reentrante no mesmo objeto. Espera até `espera_s` segundos."""
        if self._profundidade_trava:
            self._profundidade_trava += 1
            try:
                yield self
            finally:
                self._profundidade_trava -= 1
            return
        with trava_exclusiva(self.base / ".registro.lock", ESPERA_TRAVA_S if espera_s is None else espera_s):
            self._profundidade_trava = 1
            try:
                yield self
            finally:
                self._profundidade_trava = 0

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
    def _revisao_no_disco(self) -> int:
        if not self.caminho.exists():
            return 0
        return json.loads(self.caminho.read_text(encoding="utf-8")).get("revisao", 0)

    def salvar(self) -> None:
        with self.travar():
            if (no_disco := self._revisao_no_disco()) != self._revisao:
                raise RegistroAlteradoPorOutroProcesso(
                    f"o registro foi gravado por outro processo (revisão {no_disco}; esta cópia leu a {self._revisao}). "
                    "Nada foi gravado: rode o comando de novo.")
            self.dados["revisao"] = self._revisao + 1
            # Escrita atômica: a API pode estar lendo o arquivo enquanto o monitor grava.
            with tempfile.NamedTemporaryFile("w", dir=self.base, delete=False, encoding="utf-8", suffix=".tmp") as tmp:
                json.dump(self.dados, tmp, ensure_ascii=False, indent=2)
                tmp.write("\n")
            os.chmod(tmp.name, _modo_de_arquivo())
            Path(tmp.name).replace(self.caminho)
            self._revisao += 1

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
        """Última verificação da fonte, com a data do último sucesso, e um diário curto por fonte."""
        momento = agora_iso()
        anterior = self.dados["verificacoes"].get(fonte_id) or {}
        ultimo_sucesso = momento if resultado in SUCESSO else (
            anterior.get("ultimo_sucesso_em") or (anterior.get("em") if anterior.get("resultado") in SUCESSO else None))
        self.dados["verificacoes"][fonte_id] = {"em": momento, "resultado": resultado, "detalhe": detalhe,
                                                "ultimo_sucesso_em": ultimo_sucesso}
        diario = self.dados.setdefault("historico_verificacoes", {}).setdefault(fonte_id, [])
        diario.append({"em": momento, "resultado": resultado})
        del diario[:-MAX_VERIFICACOES_POR_FONTE]

    def registrar_versao(self, registro_versao: dict, texto: str) -> None:
        self.gravar_snapshot(registro_versao["fonte"], registro_versao["versao"], texto)
        self.dados["versoes"].append(registro_versao)
        if registro_versao["estado"] in ESTADOS_VALIDOS_PARA_BASE:
            self.dados["aceitas"][registro_versao["fonte"]] = registro_versao["versao"]

    def _anotar(self, acao: str, fonte_id: str, versao: str, responsavel: str, nota: str = "") -> None:
        self.dados["diario"].append({"em": agora_iso(), "acao": acao, "fonte": fonte_id, "versao": versao,
                                     "responsavel": responsavel, "nota": nota})

    def decidir(self, versao: str, resultado: str, responsavel: str, nota: str = "") -> dict:
        """Revisão humana de uma versão pendente — ou confirmação de uma aceita automaticamente.

        Aceitar uma versão mais velha que a aceita hoje (decisões fora de ordem) só registra a decisão,
        com o estado `superada`: o ponteiro não volta para um texto anterior ao que já vale.
        """
        if resultado not in DECISOES:
            raise DecisaoInvalida(f"resultado deve ser um de: {', '.join(DECISOES)}")
        if not responsavel.strip():
            raise DecisaoInvalida("informe quem revisou (responsavel)")
        v = self.versao(versao)
        automatica = v["estado"] == "aceita" and (v.get("decisao") or {}).get("resultado") == "aceita_automaticamente"
        if v["estado"] != "pendente_revisao" and not automatica:
            raise DecisaoInvalida(f"a versão {versao} não está pendente (estado: {v['estado']})")
        decisao = {"resultado": resultado, "responsavel": responsavel, "em": agora_iso(), "nota": nota}
        if automatica:
            if DECISOES[resultado] != "aceita":
                raise DecisaoInvalida("versão aceita automaticamente só pode ser confirmada aqui; para desfazê-la, "
                                      "use reverter")
            v["decisao"] = {**decisao, "confirma": "aceita_automaticamente"}
            self._anotar(f"confirmacao:{resultado}", v["fonte"], versao, responsavel, nota)
            return v
        estado = DECISOES[resultado]
        atual = self.versao_aceita(v["fonte"])
        if estado == "aceita" and atual and atual["versao"] != versao and self._ordem(atual) > self._ordem(v):
            estado = "superada"
            decisao["nota"] = (f"{nota} — " if nota else "") + (
                f"a versão {atual['versao']}, capturada depois, já estava aceita; o ponteiro não mudou")
        v["estado"] = estado
        v["decisao"] = decisao
        if estado == "aceita":
            self.dados["aceitas"][v["fonte"]] = versao
        self._anotar(f"decisao:{resultado}" + (":superada" if estado == "superada" else ""), v["fonte"], versao,
                     responsavel, decisao["nota"])
        return v

    def _ordem(self, v: dict) -> tuple[str, int]:
        """Ordem de captura: a data e, no mesmo segundo, a posição no registro (as versões só são acrescentadas)."""
        return v["capturada_em"], next(i for i, x in enumerate(self.dados["versoes"]) if x is v)

    def publicavel(self, versao: str) -> str | None:
        """Motivo para NÃO levar a versão ao corpus, ou None: só a versão aceita hoje e decidida por pessoa."""
        v = self.versao(versao)
        decisao = v.get("decisao") or {}
        if self.dados["aceitas"].get(v["fonte"]) != versao:
            return (f"a versão {versao} não é a aceita hoje para {v['fonte']} "
                    f"(aceita: {self.dados['aceitas'].get(v['fonte'])}; estado desta: {v['estado']})")
        if decisao.get("resultado") not in ("sem_impacto", "corpus_atualizado"):
            quem = decisao.get("resultado") or v["estado"]
            return (f"a versão {versao} não foi decidida por uma pessoa ({quem}); revise com "
                    "`scripts/monitor.py decidir` antes de publicar")
        return None

    def anotar_publicacao(self, fonte_id: str, versao: str, responsavel: str, nota: str) -> None:
        self._anotar("publicacao_no_corpus", fonte_id, versao, responsavel, nota)

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
