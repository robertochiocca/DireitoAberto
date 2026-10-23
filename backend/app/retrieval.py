"""Busca lexical (BM25) sobre o corpus de legislação.

Implementação em Python puro, sem dependências externas, para que o MVP
funcione em qualquer ambiente. A migração para busca semântica com
embeddings (ChromaDB/FAISS) está prevista no roadmap — a interface pública
(`Retriever.buscar`) foi desenhada para permitir a troca do motor sem
alterar a API.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .vigencia import VIGENCIA_PADRAO, vigencia_efetiva

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "legislacao.json"

STOPWORDS = {
    "a", "o", "e", "de", "da", "do", "das", "dos", "em", "no", "na", "nos",
    "nas", "um", "uma", "uns", "umas", "para", "pra", "por", "com", "sem",
    "que", "se", "ao", "aos", "as", "os", "me", "meu", "minha", "meus",
    "minhas", "seu", "sua", "seus", "suas", "ele", "ela", "eles", "elas",
    "eu", "nós", "foi", "ser", "é", "são", "está", "estão", "ter",
    "tem", "têm", "não", "sim", "mais", "menos", "muito", "já", "quando",
    "como", "qual", "quais", "onde", "quem", "isso", "isto", "essa", "esse",
    "ou", "mas", "também", "até", "após", "sobre", "entre", "pelo", "pela",
    "quer", "quero", "posso", "pode", "podem", "devo", "deve",
    # Contrações e demonstrativos. Raras no corpus, tinham IDF alto: "caí num
    # golpe do pix" casava "num" com "num mesmo contrato" e trazia a Lei do
    # Inquilinato.
    "num", "numa", "nuns", "numas", "dum", "duma", "duns", "dumas",
    "este", "aquele", "aquela", "aquilo", "neste", "nesta", "nesse", "nessa",
    "naquele", "naquela", "deste", "desta", "desse", "dessa", "daquele",
    "daquela", "disso", "disto", "nisso", "nisto", "dele", "dela", "nele",
    "nela", "lhe", "lhes", "você", "vocês", "pro", "pros",
}

# Vocabulário do cidadão -> vocabulário da lei. Aplicado só na consulta.
SINONIMOS: dict[str, list[str]] = {
    "notebook": ["produto", "durável"],
    "celular": ["produto", "durável"],
    "computador": ["produto", "durável"],
    "televisão": ["produto", "durável"],
    "geladeira": ["produto", "durável"],
    "quebrado": ["defeito", "vício"],
    "quebrou": ["defeito", "vício"],
    "estragado": ["defeito", "vício"],
    "estragou": ["defeito", "vício"],
    "defeituoso": ["defeito", "vício"],
    "trocar": ["substituição", "troca"],
    "devolver": ["devolução", "restituição"],
    "reembolso": ["devolução", "restituição"],
    "demitido": ["demissão", "rescisão", "despedida"],
    "demitida": ["demissão", "rescisão", "despedida"],
    "mandado": ["demissão", "rescisão"],
    "emprego": ["trabalho", "contrato"],
    "patrão": ["empregador"],
    "empresa": ["empregador", "fornecedor"],
    "loja": ["fornecedor"],
    "negativado": ["negativação", "cadastro", "inadimplente"],
    "negativaram": ["negativação", "cadastro", "inadimplente"],
    "sujo": ["negativação", "cadastro"],
    "serasa": ["negativação", "cadastro"],
    "spc": ["negativação", "cadastro"],
    "arrependi": ["arrependimento", "desistir"],
    "arrependimento": ["desistir", "sete", "dias"],
    "internet": ["arrependimento", "online", "compra"],
    "despejar": ["despejo", "desocupação"],
    "despejado": ["despejo", "desocupação"],
    "aumentar": ["reajuste", "aumento"],
    "aumentou": ["reajuste", "aumento"],
    "dono": ["locador"],
    "aluguel": ["locação", "locador", "locatário"],
    "advogado": ["juizado", "assistência"],
    "processar": ["juizado", "causa", "processo"],
    "blitz": ["trânsito", "multa"],
    "multado": ["multa", "infração", "autuação"],
    "carro": ["trânsito", "veículo"],
    "moto": ["trânsito", "veículo"],
    "cnh": ["trânsito", "penalidade", "pontos"],
    "injusta": ["defesa", "recurso"],
    "injusto": ["defesa", "recurso"],
    "pensão": ["alimentos", "alimentícia"],
    "alimentícia": ["alimentos", "pensão"],
    "divorciar": ["divórcio", "casamento"],
    "separar": ["divórcio", "separação"],
    "ex": ["cônjuge", "pensão"],
    "filho": ["guarda", "alimentos"],
    "filha": ["guarda", "alimentos"],
    "convênio": ["plano", "saúde", "operadora"],
    "negou": ["negativa", "cobertura", "indeferido"],
    "negaram": ["negativa", "cobertura", "indeferido"],
    "cirurgia": ["cobertura", "saúde", "urgência"],
    "exame": ["cobertura", "saúde"],
    "aposentadoria": ["inss", "benefício", "previdência"],
    "auxílio": ["inss", "benefício", "previdência"],
    "bpc": ["inss", "benefício", "loas"],
    "golpe": ["fraude", "estelionato"],
    "golpista": ["fraude", "estelionato"],
    "pix": ["fraude", "banco", "transferência", "med"],
    "clonaram": ["fraude", "golpe", "banco"],
    "voo": ["aéreo", "passageiro", "companhia"],
    "avião": ["aéreo", "passageiro", "voo"],
    "aéreo": ["voo", "passageiro"],
    "atrasou": ["atraso", "assistência"],
    "cancelaram": ["cancelamento", "reembolso"],
    "cancelou": ["cancelamento", "reembolso"],
    "mala": ["bagagem", "aéreo"],
    "síndico": ["condomínio", "condômino"],
    "condominial": ["condomínio", "cota"],
    "vizinho": ["condomínio", "sossego", "barulho"],
    "iptu": ["imposto", "tributo", "prefeitura"],
    "herança": ["inventário", "sucessão", "herdeiro"],
    "inventário": ["herança", "sucessão", "partilha"],
    "faleceu": ["herança", "inventário", "falecimento", "sucessão"],
    "morreu": ["herança", "inventário", "falecimento", "sucessão"],
    "testamento": ["herança", "sucessão"],
    "herdei": ["herança", "sucessão", "herdar"],
    "herdar": ["herança", "sucessão"],
    "companheira": ["companheiro", "união", "estável"],
}


def normalizar(texto: str) -> list[str]:
    """Minúsculas, sem acentos, sem stopwords e com plural simples reduzido."""
    sem_acento = unicodedata.normalize("NFKD", texto.lower())
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    tokens = re.findall(r"[a-z0-9]+", sem_acento)
    resultado = []
    for tok in tokens:
        if tok in _STOPWORDS_NORM or len(tok) <= 1:
            continue
        if len(tok) > 3 and tok.endswith("s"):
            tok = tok[:-1]
            # O plural de uma stopword vira a stopword: "pelos" → "pelo".
            if tok in _STOPWORDS_NORM:
                continue
        resultado.append(tok)
    return resultado


_STOPWORDS_NORM = {
    "".join(
        c
        for c in unicodedata.normalize("NFKD", w)
        if not unicodedata.combining(c)
    )
    for w in STOPWORDS
}

_SINONIMOS_NORM = {
    normalizar(chave)[0]: [t for alvo in alvos for t in normalizar(alvo)]
    for chave, alvos in SINONIMOS.items()
    if normalizar(chave)
}


@dataclass
class Resultado:
    id: str
    lei: str
    artigo: str
    tema: str
    texto: str
    resumo: str
    fonte: str
    score: float
    vigencia: dict = field(default_factory=lambda: dict(VIGENCIA_PADRAO))
    # Pendência de revisão registrada no corpus (motivo e evidência), ou None.
    revisao: dict | None = None
    # Proveniência (app/corpus/proveniencia.py): o que é o `texto` (transcrição consolidada, resumo,
    # interpretação, não conferido), os trechos oficiais transcritos da fonte e o que falta conferir.
    norma: str | None = None
    dispositivos: list[dict] = field(default_factory=list)
    # Redação anterior de outra entrada (o id da entrada vigente): as duas são versões do mesmo dispositivo.
    versao_de: str | None = None
    texto_natureza: str = "nao_conferido"
    trechos_oficiais: list[dict] = field(default_factory=list)
    lacunas: list[str] = field(default_factory=list)

    @classmethod
    def de_artigo(cls, art: dict, score: float) -> Resultado:
        """Constrói o resultado a partir da entrada do corpus (ponto único de verdade).

        A vigência sai como vale hoje (`vigencia_efetiva`), não como foi gravada:
        norma em vacatio cuja data de início já chegou aparece como vigente.
        """
        return cls(
            id=art["id"],
            lei=art["lei"],
            artigo=art["artigo"],
            tema=art["tema"],
            texto=art["texto"],
            resumo=art["resumo"],
            fonte=art["fonte"],
            score=round(score, 3),
            vigencia=vigencia_efetiva(art.get("vigencia")),
            revisao=art.get("revisao"),
            norma=art.get("norma"),
            dispositivos=art.get("dispositivos", []),
            versao_de=art.get("versao_de"),
            texto_natureza=art.get("texto_natureza", "nao_conferido"),
            trechos_oficiais=art.get("trechos_oficiais", []),
            lacunas=art.get("lacunas", []),
        )

    @property
    def em_vigor(self) -> bool:
        return self.vigencia.get("status") == "vigente"


class Retriever:
    """Índice BM25 sobre os artigos de lei do corpus."""

    K1 = 1.5
    B = 0.75
    # Palavras-chave descrevem o caso concreto melhor que o texto legal,
    # então entram no índice com peso maior.
    PESO_PALAVRAS_CHAVE = 3
    # Sinônimos ampliam o alcance, mas pesam menos que as palavras que o
    # cidadão de fato escreveu. Com peso cheio, um sinônimo solto bastava
    # para pôr lei de outro assunto na resposta: "o plano negou minha
    # cirurgia" expandia "negou" para "negativa" e trazia a Lei de Acesso à
    # Informação (pedido de informação negado). Em 86 perguntas com gabarito,
    # qualquer peso entre 0,5 e 0,7 mantém o artigo esperado no top-3 em
    # todas e põe mais artigos certos em 1º lugar; 0,6 fica no meio da faixa.
    PESO_SINONIMO = 0.6
    # Nem toda pergunta tem 4 artigos relevantes, e preencher as vagas com o que estiver mais perto traz
    # lei de outro assunto. Na busca adaptativa, o 1º sempre entra; depois dele, só quem tem ao menos 35%
    # da nota do 1º colocado. Escolhido em 22/10/2026 por validação cruzada agrupada (app/calibracao.py,
    # `scripts/avaliar.py --varrer`) com critério fixado antes: artigo do gabarito em 100% das respostas e
    # ≥ 95% dos relevantes julgados; maior precisão. Nas 86 perguntas, contra o mínimo de 2 artigos e corte
    # de 1/3 de antes: precisão (só relevante) 46,5% → 57,6%, relevantes julgados mantidos 98,1% → 96,3%,
    # gabarito 100% nos dois; estimativa fora da amostra 61,4%. O mínimo de 2 forçava um segundo artigo em
    # toda resposta, e 65 das 86 perguntas têm um só artigo relevante.
    MINIMO_ARTIGOS = 1
    CORTE_RELATIVO = 0.35

    def __init__(self, data_path: Path = DATA_PATH):
        raw = json.loads(Path(data_path).read_text(encoding="utf-8"))
        self.artigos = raw["artigos"]
        self._docs_tokens: list[list[str]] = []
        for art in self.artigos:
            tokens = normalizar(f"{art['lei']} {art['artigo']} {art['texto']} {art['resumo']}")
            tokens += self.PESO_PALAVRAS_CHAVE * [
                t for p in art.get("palavras_chave", []) for t in normalizar(p)
            ]
            self._docs_tokens.append(tokens)

        self._doc_freqs = [Counter(toks) for toks in self._docs_tokens]
        self._doc_lens = [len(toks) for toks in self._docs_tokens]
        self._avgdl = sum(self._doc_lens) / max(len(self._doc_lens), 1)
        self._idf: dict[str, float] = {}
        n = len(self._docs_tokens)
        df: Counter = Counter()
        for freqs in self._doc_freqs:
            df.update(freqs.keys())
        for termo, freq in df.items():
            self._idf[termo] = math.log(1 + (n - freq + 0.5) / (freq + 0.5))

    def _expandir_consulta(self, pergunta: str) -> dict[str, float]:
        """Termos da consulta e o peso de cada um, sem repetir termos.

        As palavras da pergunta pesam 1; os sinônimos, PESO_SINONIMO. Uma
        palavra que o cidadão escreveu mantém o peso cheio mesmo que também
        seja sinônimo de outra.

        A deduplicação importa: "dono" e "aluguel" expandem os dois para
        "locador", e sem ela esse termo pontuaria em dobro — bastaria um
        artigo citar muito o locador para superar o dispositivo que de fato
        responde à pergunta.
        """
        tokens = normalizar(pergunta)
        pesos = dict.fromkeys(tokens, 1.0)
        for tok in tokens:
            for sinonimo in _SINONIMOS_NORM.get(tok, []):
                pesos.setdefault(sinonimo, self.PESO_SINONIMO)
        return pesos

    # Texto do documento do cidadão entra na busca como expansão: os termos mais raros (maior IDF) dele, com
    # peso 0,3, abaixo do peso dos sinônimos. Antes o documento inteiro era somado à pergunta com peso cheio
    # e decidia sozinho o resultado (uma nota fiscal anexada trazia o CDC para "como funciona o habeas
    # corpus?" e desligava a abstenção).
    PESO_EXPANSAO = 0.3
    TERMOS_EXPANSAO = 25

    def _expansao(self, texto: str, ja: dict[str, float]) -> dict[str, float]:
        candidatos = {t for t in normalizar(texto) if t in self._idf and t not in ja}
        melhores = sorted(candidatos, key=lambda t: (-self._idf[t], t))[: self.TERMOS_EXPANSAO]
        return dict.fromkeys(melhores, self.PESO_EXPANSAO)

    def termos_casados(self, pergunta: str, art_id: str) -> list[str]:
        """Palavras da pergunta que o dispositivo contém, por si ou por um sinônimo do vocabulário do cidadão
        ("notebook" casa por "produto"): mede se a ligação com a pergunta é forte ou se é uma palavra solta."""
        i = next((n for n, a in enumerate(self.artigos) if a["id"] == art_id), None)
        if i is None:
            return []
        freqs = self._doc_freqs[i]
        return [t for t in dict.fromkeys(normalizar(pergunta))
                if t in freqs or any(s in freqs for s in _SINONIMOS_NORM.get(t, []))]

    def temas(self) -> list[str]:
        return sorted({art["tema"] for art in self.artigos})

    def buscar(
        self,
        pergunta: str,
        top_k: int = 4,
        score_minimo: float = 1.0,
        tema: str | None = None,
        adaptativo: bool = False,
        expansao: str | None = None,
    ) -> list[Resultado]:
        """Até `top_k` artigos; com `adaptativo`, menos quando os demais são fracos.

        A API usa a busca adaptativa. Benchmark e comparação medem com número
        fixo de resultados, para continuarem comparáveis entre si.
        """
        consulta = self._expandir_consulta(pergunta)
        if expansao:
            consulta.update(self._expansao(expansao, consulta))
        resultados = []
        for i, art in enumerate(self.artigos):
            if tema and art["tema"] != tema:
                continue
            freqs = self._doc_freqs[i]
            dl = self._doc_lens[i]
            score = 0.0
            for termo, peso in consulta.items():
                if termo not in freqs:
                    continue
                tf = freqs[termo]
                idf = self._idf.get(termo, 0.0)
                score += peso * idf * (tf * (self.K1 + 1)) / (
                    tf + self.K1 * (1 - self.B + self.B * dl / self._avgdl)
                )
            if score >= score_minimo:
                resultados.append(Resultado.de_artigo(art, score))
        resultados.sort(key=lambda r: r.score, reverse=True)
        resultados = resultados[:top_k]
        if adaptativo and resultados:
            piso = self.CORTE_RELATIVO * resultados[0].score
            resultados = [
                r for i, r in enumerate(resultados)
                if i < self.MINIMO_ARTIGOS or r.score >= piso
            ]
        return resultados
