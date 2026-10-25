"""Crawl Constitution Annotated (CONAN) essays from constitution.congress.gov and chunk them.

Discovery is URL-pattern based: walk /browse/ pages breadth-first and collect any
link shaped like /browse/essay/<essay-id>/<ALDE_xxxxx>/. That survives changes to
how the browse tree is nested. Precedents are taken from italicized text
(<i>/<em>), which is how CONAN typesets case names, instead of free-text regex.
"""
from __future__ import annotations

import re
from collections import deque
from typing import Iterator
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.store import Chunk

from .common import Fetcher, chunk_paragraphs, provision_from_essay_id, slug

BASE = "https://constitution.congress.gov"
BROWSE_ROOT = f"{BASE}/browse/"
_ESSAY_HREF = re.compile(r"^/browse/essay/(?P<eid>[^/]+)/(?P<alde>ALDE_\d+)/?$")
_CASE = re.compile(r"\bv\.\s|^(Ex parte|In re)\s", re.I)


def discover_essays(fetcher: Fetcher, max_browse_pages: int = 2000) -> Iterator[tuple[str, str]]:
    """Yield (essay_id, url) for each essay reachable from the browse tree."""
    seen_pages, seen_essays = {BROWSE_ROOT}, set()
    queue = deque([BROWSE_ROOT])
    while queue and len(seen_pages) <= max_browse_pages:
        page = queue.popleft()
        soup = BeautifulSoup(fetcher.get(page), "lxml")
        for a in soup.find_all("a", href=True):
            url = urljoin(page, a["href"]).split("#")[0].split("?")[0]
            parsed = urlparse(url)
            if parsed.netloc and parsed.netloc != urlparse(BASE).netloc:
                continue
            if m := _ESSAY_HREF.match(parsed.path):
                if m["alde"] not in seen_essays:
                    seen_essays.add(m["alde"])
                    yield m["eid"], url
            elif parsed.path.startswith("/browse/") and "/essay/" not in parsed.path and url not in seen_pages:
                seen_pages.add(url)
                queue.append(url)


def _case_names(soup: BeautifulSoup) -> list[str]:
    names: dict[str, None] = {}
    for el in soup.find_all(["i", "em"]):
        text = " ".join(el.get_text(" ", strip=True).split()).strip(" ,;.")
        if 6 <= len(text) <= 120 and _CASE.search(text):
            names.setdefault(text, None)
    return list(names)


def parse_essay(html: str, essay_id: str, url: str) -> list[Chunk]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript", "sup"]):
        tag.decompose()
    root = soup.find("main") or soup.body or soup
    title_el = root.find("h1")
    title = " ".join(title_el.get_text(" ", strip=True).split()) if title_el else essay_id

    all_cases = _case_names(root)
    # Footnotes hold citations: keep them for precedent extraction (above) but not as passage text.
    for fn in root.find_all(attrs={"class": re.compile("footnote", re.I)}) + root.find_all(id=re.compile("footnote", re.I)):
        fn.decompose()
    paragraphs = [" ".join(p.get_text(" ", strip=True).split()) for p in root.find_all("p")]
    paragraphs = [p for p in paragraphs if len(p.split()) >= 12]
    if not paragraphs:
        return []

    clause_path, provision = provision_from_essay_id(essay_id)
    alde = url.rstrip("/").rsplit("/", 1)[-1]
    chunks = []
    for i, body in enumerate(chunk_paragraphs(paragraphs), start=1):
        mentioned = [c for c in all_cases if c.split(" v. ")[0][:25] in body] or all_cases[:3]
        chunks.append(Chunk(
            chunk_id=f"conan_{alde.lower()}_{i}",
            source="conan",
            tier=2,
            clause_path=f"{clause_path}.Essay.{essay_id}",
            provision=provision,
            subtopic=title,
            title=title,
            url=url,
            controlling_precedents=mentioned[:8],
            doctrine_tags=[slug(title)[:60]],
            text=f"[CONTEXT: {provision} > {title}]\n\n{body}",
        ))
    return chunks


def load(fetcher: Fetcher | None = None, limit: int | None = None, prefix: str | None = None) -> Iterator[Chunk]:
    """Yield chunks essay by essay. `prefix` filters essay ids (e.g. "amdt14" or "artI-S9")."""
    fetcher = fetcher or Fetcher()
    n = 0
    for essay_id, url in discover_essays(fetcher):
        if prefix and not essay_id.lower().startswith(prefix.lower()):
            continue
        yield from parse_essay(fetcher.get(url), essay_id, url)
        n += 1
        if limit and n >= limit:
            return
