"""Shared ingestion helpers: polite cached HTTP, provision parsing, paragraph chunking."""
from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

import httpx

from app.config import BACKEND_DIR

CACHE_DIR = BACKEND_DIR / "data" / "cache"
USER_AGENT = "constitutional-engine/1.0 (educational research; respectful crawler)"

ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50}


def roman_to_int(s: str) -> int:
    total, prev = 0, 0
    for ch in reversed(s.upper()):
        v = ROMAN[ch]
        total += -v if v < prev else v
        prev = max(prev, v)
    return total


def int_to_roman(n: int) -> str:
    out = []
    for v, sym in ((50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out.append(sym)
            n -= v
    return "".join(out)


class Fetcher:
    """GET with an on-disk cache and a fixed delay between network requests."""

    def __init__(self, delay: float = 0.5, use_cache: bool = True):
        self.delay = delay
        self.use_cache = use_cache
        self._client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True)
        self._last = 0.0
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def get(self, url: str) -> str:
        path = CACHE_DIR / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".html")
        if self.use_cache and path.exists():
            return path.read_text(encoding="utf-8")
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        for attempt in range(4):
            try:
                resp = self._client.get(url)
                self._last = time.monotonic()
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError("retryable", request=resp.request, response=resp)
                resp.raise_for_status()
                break
            except (httpx.TransportError, httpx.HTTPStatusError) as e:
                retryable = isinstance(e, httpx.TransportError) or e.response.status_code >= 429
                if attempt == 3 or not retryable:
                    raise
                time.sleep(2 ** (attempt + 1))
        path.write_text(resp.text, encoding="utf-8")
        return resp.text


# CONAN essay ids look like "ArtI.S9.C2.1", "artI-S9-C2-1-2", "Amdt14.S1.8.1.2", "Intro.1" ...
_ESSAY_ID = re.compile(
    r"^(?:(?P<art>art)(?P<artnum>[IVX]+)|(?P<amdt>amdt)(?P<amdtnum>\d+))"
    r"(?:[.\-]S(?P<sec>\d+))?(?:[.\-]C(?P<cl>\d+))?",
    re.IGNORECASE,
)


def provision_from_essay_id(essay_id: str) -> tuple[str, str]:
    """Map a CONAN essay id to (clause_path, human provision label)."""
    m = _ESSAY_ID.match(essay_id)
    if not m:
        return f"USConst.Other.{essay_id}", "Constitution (general)"
    if m["art"]:
        n = roman_to_int(m["artnum"])
        path, label = [f"USConst.Art{n}"], [f"Article {m['artnum'].upper()}"]
    else:
        n = int(m["amdtnum"])
        path, label = [f"USConst.Amend{n}"], [f"Amendment {int_to_roman(n)}"]
    if m["sec"]:
        path.append(f"Sec{m['sec']}")
        label.append(f"Section {m['sec']}")
    if m["cl"]:
        path.append(f"Cl{m['cl']}")
        label.append(f"Clause {m['cl']}")
    return ".".join(path), " > ".join(label)


def chunk_paragraphs(paragraphs: list[str], target_words: int = 320, overlap: int = 1) -> list[str]:
    """Greedy-pack paragraphs into ~target_words chunks, carrying `overlap` trailing paragraphs forward."""
    chunks: list[str] = []
    cur: list[str] = []
    words = fresh = 0  # fresh = paragraphs in `cur` not yet emitted in any chunk
    for p in paragraphs:
        n = len(p.split())
        if fresh and words + n > target_words:
            chunks.append("\n\n".join(cur))
            cur = cur[-overlap:] if overlap else []
            words, fresh = sum(len(x.split()) for x in cur), 0
        cur.append(p)
        words += n
        fresh += 1
    if fresh:
        chunks.append("\n\n".join(cur))
    return chunks


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
