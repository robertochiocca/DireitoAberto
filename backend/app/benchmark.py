"""Benchmark de armadilha temporal.

Mede o erro que mais compromete um RAG jurídico: não o de *não achar* o
dispositivo, mas o de achar a redação **errada no tempo**. O dataset
(`data/benchmark_temporal.json`) reúne 24 dispositivos cuja redação mudou
depois de 10/04/2006 — data em que o texto do Livro do Cidadão (AGU/MJ),
publicação oficial e gratuita do governo, parou.

O experimento roda em dois índices:

* **limpo** — o corpus atual do projeto. Mede *cobertura*: para quantas dessas
  perguntas temos a redação vigente, e ela é recuperada?
* **contaminado** — o corpus mais os 24 textos de 2006, indexados como um RAG
  ingênuo os indexaria: sem nenhuma marca de obsolescência. Mede o *dano*:
  com que frequência a fonte velha é recuperada e, pior, vence a vigente.

A escolha metodológica mais sensível é dar aos distratores as mesmas
palavras-chave curadas que o corpus dá aos seus dispositivos. Sem isso, eles
seriam penalizados de graça pelo peso que o BM25 atribui às palavras-chave, e
o resultado seria otimista demais. O benchmark adota o pior caso.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from .llm import resposta_extrativa
from .retrieval import DATA_PATH, Retriever

BENCHMARK_PATH = Path(__file__).resolve().parent.parent / "data" / "benchmark_temporal.json"
PREFIXO_DISTRATOR = "obsoleto-"
FONTE_DISTRATOR = "Livro do Cidadão, 3ª ed. (AGU/MJ, 2006) — texto desatualizado"
TOP_K_PADRAO = 3


def carregar_casos(caminho: Path = BENCHMARK_PATH) -> list[dict]:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))["casos"]


def distrator_de(caso: dict, rotulado: bool = False) -> dict:
    """Converte o caso na entrada que um RAG teria ao indexar a fonte de 2006.

    Com `rotulado=False`, o distrator entra SEM marca de obsolescência — é esse
    o ponto do experimento: simular quem indexou o PDF sem saber que envelheceu.
    Com `rotulado=True`, ele entra como o corpus do projeto o registraria, com
    `status: revogada` — o braço que mede o valor da camada de vigência.
    """
    vigencia = (
        {
            "status": "revogada",
            "entra_em_vigor_em": None,
            "alterada_por": [caso["mudou_por"]],
            "nota": f"Redação anterior. {caso['vigente']}",
            "conferida_em": "2026-10-16",
        }
        if rotulado
        else {
            "status": "vigente",
            "entra_em_vigor_em": None,
            "alterada_por": [],
            "nota": None,
            "conferida_em": None,
        }
    )
    return {
        "id": f"{PREFIXO_DISTRATOR}{caso['id']}",
        "lei": f"{caso['dispositivo']} — redação de 2006",
        "artigo": caso["dispositivo"],
        "tema": caso["tema"],
        "texto": caso["obsoleto"],
        "resumo": caso["obsoleto"],
        "palavras_chave": caso["palavras_chave"],
        "fonte": FONTE_DISTRATOR,
        "vigencia": vigencia,
    }


def _indice_com_distratores(
    casos: list[dict], rotulado: bool = False, corpus: Path = DATA_PATH
) -> Path:
    """Escreve um corpus temporário = corpus atual + textos de 2006."""
    dados = json.loads(Path(corpus).read_text(encoding="utf-8"))
    dados["artigos"] = dados["artigos"] + [distrator_de(c, rotulado) for c in casos]
    nome = "mitigado.json" if rotulado else "contaminado.json"
    destino = Path(tempfile.mkdtemp(prefix="direitoaberto-bench-")) / nome
    destino.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    return destino


def _indice_contaminado(casos: list[dict], corpus: Path = DATA_PATH) -> Path:
    return _indice_com_distratores(casos, rotulado=False, corpus=corpus)


def _indice_mitigado(casos: list[dict], corpus: Path = DATA_PATH) -> Path:
    return _indice_com_distratores(casos, rotulado=True, corpus=corpus)


@dataclass
class ResultadoCaso:
    id: str
    pergunta: str
    dispositivo: str
    coberto: bool
    posicao_vigente: int | None       # índice limpo; None = não recuperado
    posicao_distrator: int | None     # índice contaminado
    posicao_vigente_contaminado: int | None
    inversao: bool                    # distrator acima do vigente
    resposta_contaminada: bool        # o texto de 2006 entra na resposta final
    distrator_rotulado_recuperado: bool = False  # braço mitigado
    resposta_alertada: bool = False              # e a resposta avisa que é revogado

    @property
    def vigente_recuperado(self) -> bool:
        return self.posicao_vigente is not None


@dataclass
class Relatorio:
    retriever: str
    top_k: int
    total: int
    cobertos: int
    vigentes_recuperados: int
    distratores_recuperados: int
    inversoes: int
    respostas_contaminadas: int
    casos: list[ResultadoCaso]
    distratores_rotulados_recuperados: int = 0
    respostas_alertadas: int = 0
    com_mitigacao: bool = False

    def _pct(self, n: int, base: int) -> float:
        return round(100 * n / base, 1) if base else 0.0

    @property
    def cobertura_pct(self) -> float:
        return self._pct(self.cobertos, self.total)

    @property
    def recall_vigente_pct(self) -> float:
        return self._pct(self.vigentes_recuperados, self.cobertos)

    @property
    def contaminacao_pct(self) -> float:
        return self._pct(self.distratores_recuperados, self.total)

    @property
    def inversao_pct(self) -> float:
        return self._pct(self.inversoes, self.cobertos)

    @property
    def resposta_contaminada_pct(self) -> float:
        return self._pct(self.respostas_contaminadas, self.total)

    @property
    def alerta_pct(self) -> float:
        """Entre as respostas que citam o texto de 2006 rotulado, quantas avisam."""
        return self._pct(self.respostas_alertadas, self.distratores_rotulados_recuperados)

    def para_json(self) -> dict:
        return {
            "retriever": self.retriever,
            "top_k": self.top_k,
            "metricas": {
                "casos": self.total,
                "cobertura": {"n": self.cobertos, "pct": self.cobertura_pct},
                "recall_vigente": {"n": self.vigentes_recuperados, "pct": self.recall_vigente_pct},
                "contaminacao": {"n": self.distratores_recuperados, "pct": self.contaminacao_pct},
                "inversao": {"n": self.inversoes, "pct": self.inversao_pct},
                "resposta_contaminada": {
                    "n": self.respostas_contaminadas,
                    "pct": self.resposta_contaminada_pct,
                },
                **(
                    {
                        "mitigacao_por_rotulo": {
                            "distratores_recuperados": self.distratores_rotulados_recuperados,
                            "respostas_com_alerta": self.respostas_alertadas,
                            "pct": self.alerta_pct,
                        }
                    }
                    if self.com_mitigacao
                    else {}
                ),
            },
            "casos": [asdict(c) for c in self.casos],
        }


def _posicao(resultados, id_alvo: str) -> int | None:
    for i, r in enumerate(resultados, start=1):
        if r.id == id_alvo:
            return i
    return None


def rodar(
    limpo,
    contaminado,
    casos: list[dict] | None = None,
    top_k: int = TOP_K_PADRAO,
    nome_retriever: str = "bm25",
    mitigado=None,
) -> Relatorio:
    """Roda o benchmark nos índices e devolve o relatório.

    `mitigado` é opcional: um terceiro índice em que os textos de 2006 entram
    rotulados como revogados, para medir se o rótulo de vigência basta para
    neutralizar o dano.
    """
    casos = casos if casos is not None else carregar_casos()
    resultados: list[ResultadoCaso] = []

    for caso in casos:
        id_corpus = caso.get("id_corpus")
        id_distrator = f"{PREFIXO_DISTRATOR}{caso['id']}"

        achados_limpo = limpo.buscar(caso["pergunta"], top_k=top_k)
        achados_contaminado = contaminado.buscar(caso["pergunta"], top_k=top_k)

        pos_vigente = _posicao(achados_limpo, id_corpus) if id_corpus else None
        pos_distrator = _posicao(achados_contaminado, id_distrator)
        pos_vigente_cont = _posicao(achados_contaminado, id_corpus) if id_corpus else None

        inversao = bool(
            pos_distrator
            and (pos_vigente_cont is None or pos_distrator < pos_vigente_cont)
            and id_corpus
        )
        # A resposta extrativa cita os dispositivos recuperados: se o texto de
        # 2006 aparece nela, o cidadão lê a regra revogada como se valesse.
        texto_resposta = resposta_extrativa(caso["pergunta"], achados_contaminado)
        contaminada = caso["obsoleto"][:60] in texto_resposta

        rotulado_recuperado = alertada = False
        if mitigado is not None:
            achados_mitigado = mitigado.buscar(caso["pergunta"], top_k=top_k)
            rotulado_recuperado = _posicao(achados_mitigado, id_distrator) is not None
            if rotulado_recuperado:
                texto_mitigado = resposta_extrativa(caso["pergunta"], achados_mitigado)
                alertada = "REVOGADO" in texto_mitigado

        resultados.append(
            ResultadoCaso(
                id=caso["id"],
                pergunta=caso["pergunta"],
                dispositivo=caso["dispositivo"],
                coberto=bool(id_corpus),
                posicao_vigente=pos_vigente,
                posicao_distrator=pos_distrator,
                posicao_vigente_contaminado=pos_vigente_cont,
                inversao=inversao,
                resposta_contaminada=contaminada,
                distrator_rotulado_recuperado=rotulado_recuperado,
                resposta_alertada=alertada,
            )
        )

    return Relatorio(
        retriever=nome_retriever,
        top_k=top_k,
        total=len(resultados),
        cobertos=sum(r.coberto for r in resultados),
        vigentes_recuperados=sum(r.vigente_recuperado for r in resultados),
        distratores_recuperados=sum(r.posicao_distrator is not None for r in resultados),
        inversoes=sum(r.inversao for r in resultados),
        respostas_contaminadas=sum(r.resposta_contaminada for r in resultados),
        casos=resultados,
        distratores_rotulados_recuperados=sum(
            r.distrator_rotulado_recuperado for r in resultados
        ),
        respostas_alertadas=sum(r.resposta_alertada for r in resultados),
        com_mitigacao=mitigado is not None,
    )


def rodar_bm25(top_k: int = TOP_K_PADRAO, casos: list[dict] | None = None) -> Relatorio:
    """Atalho: monta os três índices BM25 e roda o benchmark completo."""
    casos = casos if casos is not None else carregar_casos()
    return rodar(
        Retriever(),
        Retriever(_indice_contaminado(casos)),
        casos=casos,
        top_k=top_k,
        nome_retriever="bm25",
        mitigado=Retriever(_indice_mitigado(casos)),
    )
