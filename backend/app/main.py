"""FastAPI entrypoint. Run from backend/:  uvicorn app.main:app --reload --port 8000"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

import anthropic
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import llm, store
from .config import settings
from .retrieval import retrieve

log = logging.getLogger("constitutional_engine")

app = FastAPI(title="Constitutional Analysis Engine")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class AnalyzeRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=1000)
    candidate_pool_size: int = Field(default=15, ge=5, le=50)
    top_k_final: int = Field(default=4, ge=1, le=10)


SOURCE_FIELDS = ("chunk_id", "source", "provision", "subtopic", "title", "url", "clause_path",
                 "controlling_precedents", "rrf_score", "reranker_score")


def sse(event: str, data: Any) -> str:
    # JSON-encoding keeps newlines inside the payload, so Markdown survives SSE framing intact.
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def analysis_events(req: AnalyzeRequest) -> AsyncIterator[str]:
    try:
        yield sse("status", {"message": "Retrieving constitutional authorities…"})
        chunks, grounding = await asyncio.to_thread(retrieve, req.query, req.candidate_pool_size, req.top_k_final)
        yield sse("sources", {
            "grounding": grounding,
            "sources": [{k: c.get(k) for k in SOURCE_FIELDS} for c in chunks],
        })
        async for ev in llm.stream_analysis(req.query, chunks, grounding):
            yield sse(ev.pop("type"), ev)
        yield sse("done", {})
    except store.TableMissingError as e:
        yield sse("error", {"message": str(e)})
    except anthropic.AuthenticationError:
        yield sse("error", {"message": "Claude API authentication failed. Set ANTHROPIC_API_KEY or run `ant auth login`."})
    except anthropic.RateLimitError:
        yield sse("error", {"message": "Claude API rate limit hit. Try again shortly."})
    except anthropic.APIStatusError as e:
        log.exception("Claude API error")
        yield sse("error", {"message": f"Claude API error {e.status_code}."})
    except anthropic.APIConnectionError:
        yield sse("error", {"message": "Couldn't reach the Claude API."})
    except Exception:
        log.exception("analysis failed")
        yield sse("error", {"message": "Internal error while analyzing. Check the server log."})


@app.post("/api/analyze/stream")
async def analyze_stream(req: AnalyzeRequest) -> StreamingResponse:
    return StreamingResponse(
        analysis_events(req),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/stats")
async def stats() -> dict[str, Any]:
    return {"chunks": await asyncio.to_thread(store.count), "model": settings.model,
            "reranker_enabled": settings.reranker_enabled}


@app.get("/healthz")
async def health() -> dict[str, str]:
    return {"status": "ok"}
