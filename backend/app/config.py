"""Runtime settings, read once from environment variables (prefix CE_)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    db_path: Path = field(default_factory=lambda: Path(os.getenv("CE_DB_PATH", BACKEND_DIR / "data" / "constitutional_db")))
    table_name: str = os.getenv("CE_TABLE", "constitutional_chunks")

    embed_model: str = os.getenv("CE_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
    rerank_model: str = os.getenv("CE_RERANK_MODEL", "BAAI/bge-reranker-base")
    reranker_enabled: bool = _bool("CE_RERANKER_ENABLED", True)

    model: str = os.getenv("CE_MODEL", "claude-opus-5-5")
    effort: str = os.getenv("CE_EFFORT", "medium")
    max_tokens: int = int(os.getenv("CE_MAX_TOKENS", "16000"))

    allowed_origins: tuple[str, ...] = tuple(
        o.strip() for o in os.getenv("CE_ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o.strip()
    )


settings = Settings()
