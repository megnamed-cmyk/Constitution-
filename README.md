# Constitutional Analysis Engine

Ask a constitutional-law question; get a structured, cited analysis.

```
question ─┬─ dense search (BGE-small embeddings) ─┐
          └─ full-text search (LanceDB FTS) ──────┴─ RRF fusion ─ cross-encoder rerank ─ top-k
                                                                                          │
              React UI  ◀── SSE: status / sources / delta / done ── Claude (streaming) ◀──┘
```

**Corpus**
- **Constitution text**: one chunk per clause, scraped from constitution.congress.gov (tier 1).
- **Constitution Annotated (CONAN)**: the Congressional Research Service's essays on doctrine and precedent, chunked at about 320 words, with case names pulled from italics (tier 2).
- **Seed**: 4 hand-written demo chunks, so you can try it offline.

## Setup

```bash
# Backend (Python 3.10+)
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
#   CPU-only machine? Install torch first to skip ~2 GB of CUDA wheels:
#   pip install torch --index-url https://download.pytorch.org/whl/cpu

export ANTHROPIC_API_KEY=sk-ant-...      # or: ant auth login

cd backend
python -m ingest seed                     # instant demo corpus
python -m ingest constitution             # full text, one chunk per clause
python -m ingest conan --prefix amdt14    # try one amendment's essays first…
python -m ingest conan                    # …then everything (slow; polite 0.5 s delay, cached)
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend && npm install && npm run dev  # http://localhost:5173 (proxies /api → :8000)
```

On first query the BGE models (about 130 MB for embeddings, about 1.1 GB for the reranker) download from Hugging Face. Set `CE_RERANKER_ENABLED=false` to skip the reranker. Other settings are listed in `.env.example`.

If the site layout changes and `ingest constitution` parses fewer than 50 clauses, save the Constitution page (or its plain text) and run `python -m ingest constitution --constitution-file saved.html`.

## Tests

```bash
cd backend && pip install -r requirements-dev.txt && pytest
cd frontend && npm run build
```

The tests swap in a hashing embedder and a word-overlap reranker, so they run offline in about 2 s. They exercise LanceDB, RRF, the parsers, and the SSE round trip.

## Layout

| Path | What |
|---|---|
| `backend/app/main.py` | FastAPI app, SSE endpoint, error mapping |
| `backend/app/retrieval.py` | RRF, rerank, **`assess_grounding`** |
| `backend/app/llm.py` | System prompt, context formatting, Claude streaming |
| `backend/app/store.py` | LanceDB schema, upsert, dense and FTS search |
| `backend/app/embeddings.py` | Lazy BGE embedder and cross-encoder |
| `backend/ingest/` | Constitution and CONAN scrapers, chunking, CLI |
| `frontend/src/` | Stream hook, analyzer UI, citations, sources panel |

## Grounding check

Before Claude answers, `assess_grounding()` in `backend/app/retrieval.py` rates how well the retrieved passages match the question. The verdict appears above the answer and changes Claude's instructions:

| Verdict | When (reranker on) | Claude is told to… |
|---|---|---|
| **grounded** | best passage scores ≥ 0.45 | answer from the sources and cite them |
| **weak** | best passage scores 0.15–0.45 | say up front that support is thin |
| **none** | best passage scores < 0.15 | say the corpus doesn't cover it; give a brief, labeled general answer |

With the reranker off, a passage that both the meaning-based search and the keyword search found counts as grounded; anything else is weak.

These are "balanced" defaults. Tune `GROUNDED_MIN` and `WEAK_MIN` once the real corpus is loaded: raise them for a more cautious tool, lower them for fewer warnings.

---
Educational tool, not legal advice.
