"""LanceDB storage: one table of constitutional chunks with a vector column and a full-text index."""
from __future__ import annotations

import threading
from typing import Any, Iterable, Sequence

import lancedb
import pyarrow as pa
from lancedb.index import FTS
from pydantic import BaseModel, Field

from .config import settings
from .embeddings import get_embedder


class Chunk(BaseModel):
    """One retrievable unit. `text` is what gets embedded and indexed."""

    chunk_id: str
    source: str  # "constitution" | "conan" | "seed"
    tier: int = Field(ge=1, le=3)  # 1 = constitutional text, 2 = doctrinal analysis, 3 = background
    clause_path: str  # machine path, e.g. USConst.Art1.Sec9.Cl2
    provision: str  # human label, e.g. "Article I > Section 9 > Clause 2"
    subtopic: str
    title: str = ""
    url: str = ""
    controlling_precedents: list[str] = Field(default_factory=list)
    doctrine_tags: list[str] = Field(default_factory=list)
    text: str


def _schema(dim: int) -> pa.Schema:
    return pa.schema(
        [
            pa.field("chunk_id", pa.string()),
            pa.field("source", pa.string()),
            pa.field("tier", pa.int32()),
            pa.field("clause_path", pa.string()),
            pa.field("provision", pa.string()),
            pa.field("subtopic", pa.string()),
            pa.field("title", pa.string()),
            pa.field("url", pa.string()),
            pa.field("controlling_precedents", pa.list_(pa.string())),
            pa.field("doctrine_tags", pa.list_(pa.string())),
            pa.field("text", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), dim)),
        ]
    )


class TableMissingError(RuntimeError):
    pass


_lock = threading.Lock()
_table: Any = None


def _db():
    settings.db_path.mkdir(parents=True, exist_ok=True)
    return lancedb.connect(str(settings.db_path))


def has_table(db) -> bool:
    return settings.table_name in db.list_tables().tables


def drop_table() -> None:
    global _table
    db = _db()
    with _lock:
        if has_table(db):
            db.drop_table(settings.table_name)
        _table = None


def get_table():
    global _table
    with _lock:
        if _table is None:
            db = _db()
            if not has_table(db):
                raise TableMissingError(
                    "No corpus found. Run `python -m ingest seed` (offline demo) or "
                    "`python -m ingest constitution conan` from backend/."
                )
            _table = db.open_table(settings.table_name)
        return _table


def upsert_chunks(chunks: Sequence[Chunk], batch_size: int = 256) -> int:
    """Embed and upsert chunks by chunk_id, then rebuild the FTS index."""
    global _table
    if not chunks:
        return 0
    embedder = get_embedder()
    db = _db()
    with _lock:
        if has_table(db):
            tbl = db.open_table(settings.table_name)
        else:
            tbl = db.create_table(settings.table_name, schema=_schema(embedder.dim))

        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors = embedder.embed_passages([c.text for c in batch])
            rows = [{**c.model_dump(), "vector": v} for c, v in zip(batch, vectors)]
            (
                tbl.merge_insert("chunk_id")
                .when_matched_update_all()
                .when_not_matched_insert_all()
                .execute(rows)
            )
        tbl.create_index("text", config=FTS(), replace=True)
        _table = tbl
    return len(chunks)


_RESULT_FIELDS = tuple(Chunk.model_fields)


def _clean(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: r[k] for k in _RESULT_FIELDS if k in r} for r in rows]


def dense_search(query: str, limit: int) -> list[dict[str, Any]]:
    vec = get_embedder().embed_query(query)
    return _clean(get_table().search(vec, vector_column_name="vector").limit(limit).to_list())


def sparse_search(query: str, limit: int) -> list[dict[str, Any]]:
    try:
        return _clean(get_table().search(query, query_type="fts").limit(limit).to_list())
    except ValueError:
        # Tantivy-style query syntax errors (e.g. stray quotes or colons) shouldn't sink the request.
        return []


def count() -> int:
    try:
        return get_table().count_rows()
    except TableMissingError:
        return 0
