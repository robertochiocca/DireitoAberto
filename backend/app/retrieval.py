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

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "legislacao.json"

STOPWORDS = {
    "a", "o", "e", "de", "da", "do", "das", "dos", "em", "no", "na", "nos",
    "nas", "um", "uma", "uns", "umas", "para", "pra", "por", "com", "sem",
    "que", "se", "ao", "aos", "as", "os", "me", "meu", "minha", "meus",
    "minhas", "seu", "sua", "seus", "suas", "ele", "ela", "eles", "elas",
    "eu", "nós", "nos", "foi", "ser", "é", "são", "está", "estão", "ter",
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


VIGENCIA_PADRAO = {
    "status": "vigente",
    "entra_em_vigor_em": None,
    "alterada_por": [],
    "nota": None,
    "conferida_em": None,
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

    @classmethod
    def de_artigo(cls, art: dict, score: float) -> "Resultado":
        """Constrói o resultado a partir da entrada do corpus (ponto único de verdade)."""
        return cls(
            id=art["id"],
            lei=art["lei"],
            artigo=art["artigo"],
            tema=art["tema"],
            texto=art["texto"],
            resumo=art["resumo"],
            fonte=art["fonte"],
            score=round(score, 3),
            vigencia={**VIGENCIA_PADRAO, **art.get("vigencia", {})},
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

    def temas(self) -> list[str]:
        return sorted({art["tema"] for art in self.artigos})

    def buscar(
        self,
        pergunta: str,
        top_k: int = 4,
        score_minimo: float = 1.0,
        tema: str | None = None,
    ) -> list[Resultado]:
        consulta = self._expandir_consulta(pergunta)
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
        return resultados[:top_k]
