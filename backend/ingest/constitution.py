"""Parse the full text of the Constitution into one chunk per clause.

Works on the page's *text order* rather than CSS selectors: it walks block-level
lines and tracks Article / Section / Amendment headings with a small state
machine, so it tolerates markup changes and also accepts a saved .txt/.html file.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup

from app.store import Chunk

from .common import Fetcher, int_to_roman, roman_to_int

DEFAULT_URL = "https://constitution.congress.gov/constitution/"

_ARTICLE = re.compile(r"^Article\s+([IVX]+)\.?$", re.I)
_AMEND = re.compile(r"^Amendment\s+([IVXL]+|\d+)\.?$", re.I)
_SECTION = re.compile(r"^Section\.?\s+(\d+)\.?\s*(.*)$", re.I)
_BLOCKS = ["h1", "h2", "h3", "h4", "h5", "p", "li"]


def html_to_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    root = soup.find("main") or soup.body or soup
    lines = []
    for el in root.find_all(_BLOCKS):
        if el.find(_BLOCKS):  # skip containers; their children are visited on their own
            continue
        text = " ".join(el.get_text(" ", strip=True).split())
        if text:
            lines.append(text)
    return lines


@dataclass
class _Unit:
    kind: str  # "preamble" | "article" | "amendment"
    num: int
    section: int | None = None
    paragraphs: list[str] = field(default_factory=list)


def parse_lines(lines: list[str]) -> list[_Unit]:
    units: list[_Unit] = []
    cur: _Unit | None = None
    started = False
    for line in lines:
        if not started:
            if line.startswith("We the People"):
                started = True
                cur = _Unit("preamble", 0, paragraphs=[line])
                units.append(cur)
            continue
        if m := _ARTICLE.match(line):
            cur = _Unit("article", roman_to_int(m[1]))
            units.append(cur)
        elif m := _AMEND.match(line):
            raw = m[1]
            cur = _Unit("amendment", int(raw) if raw.isdigit() else roman_to_int(raw))
            units.append(cur)
        elif cur and cur.kind != "preamble" and (m := _SECTION.match(line)):
            cur = _Unit(cur.kind, cur.num, int(m[1]))
            units.append(cur)
            if m[2]:
                cur.paragraphs.append(m[2])
        elif cur and len(line.split()) >= 4:
            cur.paragraphs.append(line)
    return [u for u in units if u.paragraphs]


def units_to_chunks(units: list[_Unit], url: str = DEFAULT_URL) -> list[Chunk]:
    chunks = []
    for u in units:
        if u.kind == "preamble":
            base_path, base_label = "USConst.Preamble", "Preamble"
        elif u.kind == "article":
            base_path, base_label = f"USConst.Art{u.num}", f"Article {int_to_roman(u.num)}"
        else:
            base_path, base_label = f"USConst.Amend{u.num}", f"Amendment {int_to_roman(u.num)}"
        if u.section is not None:
            base_path += f".Sec{u.section}"
            base_label += f" > Section {u.section}"
        multi = len(u.paragraphs) > 1
        for i, para in enumerate(u.paragraphs, start=1):
            path = f"{base_path}.Cl{i}" if multi else base_path
            label = f"{base_label} > Clause {i}" if multi else base_label
            chunks.append(Chunk(
                chunk_id=f"const_{path.lower().replace('.', '_')}",
                source="constitution",
                tier=1,
                clause_path=path,
                provision=label,
                subtopic="Constitutional text",
                title=label,
                url=url,
                doctrine_tags=[],
                text=f"[CONTEXT: {label}] {para}",
            ))
    return chunks


def load(url: str = DEFAULT_URL, from_file: Path | None = None, fetcher: Fetcher | None = None) -> list[Chunk]:
    if from_file:
        raw = from_file.read_text(encoding="utf-8")
        lines = html_to_lines(raw) if from_file.suffix.lower() in {".html", ".htm"} else [
            " ".join(l.split()) for l in raw.splitlines() if l.strip()
        ]
    else:
        lines = html_to_lines((fetcher or Fetcher()).get(url))
    chunks = units_to_chunks(parse_lines(lines), url)
    if len(chunks) < 50:
        raise RuntimeError(
            f"Parsed only {len(chunks)} clauses from {from_file or url}; the page layout may have changed. "
            "Save the Constitution text to a file and pass --constitution-file."
        )
    return chunks
