"""Hybrid retrieval: dense + full-text search fused with RRF, then optional cross-encoder reranking."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal

from . import store
from .embeddings import get_reranker

Grounding = Literal["grounded", "weak", "none"]


def compute_rrf(*ranked_lists: list[dict[str, Any]], k: int = 60) -> list[dict[str, Any]]:
    """Reciprocal Rank Fusion over any number of ranked result lists, keyed by chunk_id."""
    scores: dict[str, float] = defaultdict(float)
    docs: dict[str, dict[str, Any]] = {}
    for hits in ranked_lists:
        for rank, doc in enumerate(hits, start=1):
            cid = doc["chunk_id"]
            scores[cid] += 1.0 / (k + rank)
            docs.setdefault(cid, doc)
    fused = []
    for cid in sorted(scores, key=scores.__getitem__, reverse=True):
        fused.append({**docs[cid], "rrf_score": scores[cid]})
    return fused


def hybrid_search(query: str, pool_size: int = 15) -> list[dict[str, Any]]:
    return compute_rrf(store.dense_search(query, pool_size), store.sparse_search(query, pool_size))


def rerank(query: str, candidates: list[dict[str, Any]], top_n: int) -> list[dict[str, Any]]:
    reranker = get_reranker()
    if reranker is None or not candidates:
        return candidates[:top_n]
    scores = reranker.score(query, [c["text"] for c in candidates])
    scored = [{**c, "reranker_score": s} for c, s in zip(candidates, scores)]
    return sorted(scored, key=lambda c: c["reranker_score"], reverse=True)[:top_n]


# "Balanced" cutoffs on the cross-encoder's 0..1 relevance score: one clearly
# relevant passage is enough to ground an answer; anything below WEAK_MIN is noise.
GROUNDED_MIN = 0.45
WEAK_MIN = 0.15


def assess_grounding(chunks: list[dict[str, Any]], rrf_k: int = 60) -> Grounding:
    """Decide how well the retrieved chunks support an answer.

    Each chunk carries `rrf_score` (always) and `reranker_score` (only when the
    cross-encoder ran; bge-reranker-base yields roughly 0..1 after sigmoid).
    The result changes the instructions Claude gets in llm.build_user_prompt:
      "grounded" -> answer from the retrieved context
      "weak"     -> answer, but flag that retrieved support is thin
      "none"     -> say the corpus doesn't cover it; general doctrine only, clearly labeled
    """
    if not chunks:
        return "none"

    scores = [c["reranker_score"] for c in chunks if c.get("reranker_score") is not None]
    if scores:
        top = max(scores)
        if top >= GROUNDED_MIN:
            return "grounded"
        return "weak" if top >= WEAK_MIN else "none"

    # Reranker off: RRF scores are only relative ranks, so use agreement instead.
    # A chunk found by both dense and keyword search scores at least 2/(k+pool),
    # which beats the best possible single-list score of 1/(k+1).
    if any(c.get("rrf_score", 0.0) > 1.0 / (rrf_k + 1) for c in chunks):
        return "grounded"
    return "weak"


def retrieve(query: str, pool_size: int, top_k: int) -> tuple[list[dict[str, Any]], Grounding]:
    chunks = rerank(query, hybrid_search(query, pool_size), top_k)
    return chunks, assess_grounding(chunks)
