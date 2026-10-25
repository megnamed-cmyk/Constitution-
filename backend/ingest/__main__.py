"""Ingestion CLI. Run from backend/:

    python -m ingest seed                      # 4 hand-written demo chunks (no network)
    python -m ingest constitution              # full text, one chunk per clause
    python -m ingest conan --limit 50          # Constitution Annotated essays
    python -m ingest conan --prefix amdt14     # only 14th Amendment essays
    python -m ingest reset                     # drop the table
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app import store
from app.config import BACKEND_DIR

from . import conan, constitution
from .common import Fetcher

SEED_FILE = BACKEND_DIR / "data" / "seed.jsonl"


def _seed() -> int:
    rows = [store.Chunk(**json.loads(l)) for l in SEED_FILE.read_text().splitlines() if l.strip()]
    return store.upsert_chunks(rows)


def _conan(args: argparse.Namespace) -> int:
    total, batch = 0, []
    for chunk in conan.load(Fetcher(delay=args.delay, use_cache=not args.no_cache), limit=args.limit, prefix=args.prefix):
        batch.append(chunk)
        if len(batch) >= 200:
            total += store.upsert_chunks(batch)
            print(f"  … {total} CONAN chunks", file=sys.stderr)
            batch = []
    return total + store.upsert_chunks(batch)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m ingest")
    p.add_argument("command", choices=["seed", "constitution", "conan", "reset"], nargs="+")
    p.add_argument("--constitution-file", type=Path, help="Saved .html/.txt of the Constitution instead of fetching")
    p.add_argument("--limit", type=int, help="Max CONAN essays")
    p.add_argument("--prefix", help="Only CONAN essay ids starting with this (e.g. amdt14, artII-S2)")
    p.add_argument("--delay", type=float, default=0.5, help="Seconds between network requests")
    p.add_argument("--no-cache", action="store_true")
    args = p.parse_args(argv)

    for cmd in args.command:
        if cmd == "reset":
            store.drop_table()
            print("table dropped")
        elif cmd == "seed":
            print(f"seed: {_seed()} chunks")
        elif cmd == "constitution":
            chunks = constitution.load(from_file=args.constitution_file,
                                       fetcher=Fetcher(delay=args.delay, use_cache=not args.no_cache))
            print(f"constitution: {store.upsert_chunks(chunks)} clauses")
        elif cmd == "conan":
            print(f"conan: {_conan(args)} chunks")
    print(f"table now holds {store.count()} chunks")


if __name__ == "__main__":
    main()
