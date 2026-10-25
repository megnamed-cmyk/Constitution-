"""Embedding and reranking models, loaded lazily on first use.

We embed ourselves instead of using LanceDB's embedding registry because BGE
models expect an instruction prefix on *queries* but not on *passages*; the
registry applies one function to both, which quietly lowers recall.
"""
from __future__ import annotations

import threading
from typing import Protocol, Sequence

from .config import settings

BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder(Protocol):
    dim: int

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class Reranker(Protocol):
    def score(self, query: str, passages: Sequence[str]) -> list[float]: ...


def _device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class BGEEmbedder:
    def __init__(self, model_name: str = settings.embed_model):
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name, device=_device())
        self.dim = self._model.get_sentence_embedding_dimension()

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        vecs = self._model.encode(list(texts), batch_size=32, normalize_embeddings=True, show_progress_bar=len(texts) > 200)
        return vecs.tolist()

    def embed_query(self, text: str) -> list[float]:
        return self._model.encode(BGE_QUERY_PREFIX + text, normalize_embeddings=True).tolist()


class CrossEncoderReranker:
    def __init__(self, model_name: str = settings.rerank_model):
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(model_name, max_length=512, device=_device())

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        if not passages:
            return []
        scores = self._model.predict([[query, p] for p in passages], batch_size=16, show_progress_bar=False)
        return [float(s) for s in scores]


_lock = threading.Lock()
_embedder: Embedder | None = None
_reranker: Reranker | None = None


def get_embedder() -> Embedder:
    global _embedder
    with _lock:
        if _embedder is None:
            _embedder = BGEEmbedder()
        return _embedder


def get_reranker() -> Reranker | None:
    """Returns None when reranking is disabled via CE_RERANKER_ENABLED=false."""
    global _reranker
    if not settings.reranker_enabled:
        return None
    with _lock:
        if _reranker is None:
            _reranker = CrossEncoderReranker()
        return _reranker


def set_models(embedder: Embedder | None = None, reranker: Reranker | None = None) -> None:
    """Inject models (used by tests and offline demos)."""
    global _embedder, _reranker
    with _lock:
        if embedder is not None:
            _embedder = embedder
        if reranker is not None:
            _reranker = reranker
