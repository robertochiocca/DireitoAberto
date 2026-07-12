"""Embeddings multilíngues de qualidade para PT-BR (multilingual-e5-small).

Roda o modelo em ONNX com `onnxruntime` + `tokenizers` (dependências que o
ChromaDB já instala) — sem PyTorch. Os pesos (~130 MB) são baixados do
Hugging Face na primeira execução e ficam em cache local.

O e5 é assimétrico: consultas usam o prefixo "query: " e documentos,
"passage: " — por isso o retriever calcula os vetores por aqui em vez de
usar a embedding function padrão do Chroma.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

REPO = "https://huggingface.co/Xenova/multilingual-e5-small/resolve/main"
ARQUIVOS = {
    "model_quantized.onnx": f"{REPO}/onnx/model_quantized.onnx",
    "tokenizer.json": f"{REPO}/tokenizer.json",
}
CACHE_DIR = Path(
    os.environ.get(
        "DIREITO_ABERTO_MODELOS_DIR",
        Path.home() / ".cache" / "direitoaberto" / "multilingual-e5-small",
    )
)
MAX_TOKENS = 512
LOTE = 16


def _baixar_modelo() -> None:
    import httpx

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for nome, url in ARQUIVOS.items():
        destino = CACHE_DIR / nome
        if destino.exists():
            continue
        logger.info("Baixando %s (primeira execução)…", nome)
        with httpx.stream("GET", url, timeout=300, follow_redirects=True) as resp:
            resp.raise_for_status()
            temporario = destino.with_suffix(".part")
            with open(temporario, "wb") as f:
                for pedaco in resp.iter_bytes():
                    f.write(pedaco)
            temporario.rename(destino)


class EmbedderMultilingue:
    """Vetores L2-normalizados do multilingual-e5-small (dim. 384)."""

    def __init__(self) -> None:
        import numpy as np  # dependência do onnxruntime
        import onnxruntime as ort
        from tokenizers import Tokenizer

        _baixar_modelo()
        self._np = np
        self._tokenizer = Tokenizer.from_file(str(CACHE_DIR / "tokenizer.json"))
        self._tokenizer.enable_truncation(MAX_TOKENS)
        self._sessao = ort.InferenceSession(
            str(CACHE_DIR / "model_quantized.onnx"), providers=["CPUExecutionProvider"]
        )
        self._entradas = {e.name for e in self._sessao.get_inputs()}

    def _lote(self, textos: list[str]):
        np = self._np
        codificados = self._tokenizer.encode_batch(textos)
        maior = max(len(e.ids) for e in codificados)
        ids = np.zeros((len(textos), maior), dtype=np.int64)
        mascara = np.zeros((len(textos), maior), dtype=np.int64)
        for i, e in enumerate(codificados):
            ids[i, : len(e.ids)] = e.ids
            mascara[i, : len(e.ids)] = e.attention_mask

        entradas = {"input_ids": ids, "attention_mask": mascara}
        if "token_type_ids" in self._entradas:
            entradas["token_type_ids"] = np.zeros_like(ids)
        (estados,) = self._sessao.run(None, entradas)  # (lote, tokens, 384)

        # mean pooling sobre os tokens válidos + normalização L2
        pesos = mascara[:, :, None].astype(np.float32)
        vetores = (estados * pesos).sum(axis=1) / pesos.sum(axis=1).clip(min=1e-9)
        normas = np.linalg.norm(vetores, axis=1, keepdims=True).clip(min=1e-9)
        return vetores / normas

    def _embed(self, textos: list[str], prefixo: str):
        np = self._np
        com_prefixo = [f"{prefixo}{t}" for t in textos]
        partes = [
            self._lote(com_prefixo[i : i + LOTE]) for i in range(0, len(com_prefixo), LOTE)
        ]
        return np.concatenate(partes, axis=0)

    def embed_documentos(self, textos: list[str]) -> list[list[float]]:
        return self._embed(textos, "passage: ").tolist()

    def embed_consulta(self, texto: str) -> list[float]:
        return self._embed([texto], "query: ")[0].tolist()
