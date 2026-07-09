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
from dataclasses import dataclass
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


class Retriever:
    """Índice BM25 sobre os artigos de lei do corpus."""

    K1 = 1.5
    B = 0.75
    # Palavras-chave descrevem o caso concreto melhor que o texto legal,
    # então entram no índice com peso maior.
    PESO_PALAVRAS_CHAVE = 3

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

    def _expandir_consulta(self, pergunta: str) -> list[str]:
        tokens = normalizar(pergunta)
        expandidos = list(tokens)
        for tok in tokens:
            expandidos.extend(_SINONIMOS_NORM.get(tok, []))
        return expandidos

    def buscar(self, pergunta: str, top_k: int = 4, score_minimo: float = 1.0) -> list[Resultado]:
        consulta = self._expandir_consulta(pergunta)
        resultados = []
        for i, art in enumerate(self.artigos):
            freqs = self._doc_freqs[i]
            dl = self._doc_lens[i]
            score = 0.0
            for termo in consulta:
                if termo not in freqs:
                    continue
                tf = freqs[termo]
                idf = self._idf.get(termo, 0.0)
                score += idf * (tf * (self.K1 + 1)) / (
                    tf + self.K1 * (1 - self.B + self.B * dl / self._avgdl)
                )
            if score >= score_minimo:
                resultados.append(
                    Resultado(
                        id=art["id"],
                        lei=art["lei"],
                        artigo=art["artigo"],
                        tema=art["tema"],
                        texto=art["texto"],
                        resumo=art["resumo"],
                        fonte=art["fonte"],
                        score=round(score, 3),
                    )
                )
        resultados.sort(key=lambda r: r.score, reverse=True)
        return resultados[:top_k]
