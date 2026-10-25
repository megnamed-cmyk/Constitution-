import hashlib
import math
import os
import re
import tempfile

# Settings are read at import time, so point the DB at a temp dir before importing app.*
os.environ["CE_DB_PATH"] = tempfile.mkdtemp(prefix="ce-test-db-")

import pytest  # noqa: E402

from app import embeddings  # noqa: E402

_WORD = re.compile(r"[a-z]+")


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


class HashEmbedder:
    """Deterministic bag-of-words hashing embedder: stands in for BGE offline."""

    dim = 64

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for t in _tokens(text):
            v[int(hashlib.md5(t.encode()).hexdigest(), 16) % self.dim] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def embed_passages(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


class OverlapReranker:
    def score(self, query, passages):
        q = set(_tokens(query))
        return [len(q & set(_tokens(p))) / (len(q) or 1) for p in passages]


@pytest.fixture(scope="session", autouse=True)
def fake_models():
    embeddings.set_models(HashEmbedder(), OverlapReranker())
