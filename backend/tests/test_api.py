import json

import pytest
from fastapi.testclient import TestClient

from app import llm, main
from ingest.__main__ import main as ingest_main


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        fields = dict(line.split(": ", 1) for line in block.split("\n"))
        events.append((fields["event"], json.loads(fields["data"])))
    return events


@pytest.fixture(scope="module", autouse=True)
def seeded():
    ingest_main(["reset", "seed"])


def test_stream_roundtrip(monkeypatch):
    seen = {}

    async def fake_stream(query, chunks, grounding):
        seen["chunks"], seen["grounding"] = chunks, grounding
        yield {"type": "status", "message": "thinking"}
        yield {"type": "delta", "text": "## Provisions\n\n"}
        yield {"type": "delta", "text": " Article I [1]"}

    monkeypatch.setattr(llm, "stream_analysis", fake_stream)
    client = TestClient(main.app)
    resp = client.post("/api/analyze/stream", json={"query": "Can the president suspend habeas corpus?", "top_k_final": 2})
    assert resp.status_code == 200
    events = parse_sse(resp.text)
    kinds = [e for e, _ in events]
    assert kinds == ["status", "sources", "status", "delta", "delta", "done"]

    sources = events[1][1]["sources"]
    assert sources[0]["chunk_id"] == "seed_art1_sec9_habeas"
    assert len(sources) == 2
    # Markdown newlines and leading spaces survive SSE framing
    text = "".join(d["text"] for e, d in events if e == "delta")
    assert text == "## Provisions\n\n Article I [1]"


def test_missing_corpus_reports_error(monkeypatch):
    from app import store

    def boom(*a, **k):
        raise store.TableMissingError("No corpus found.")

    monkeypatch.setattr(main, "retrieve", boom)
    events = parse_sse(TestClient(main.app).post("/api/analyze/stream", json={"query": "anything"}).text)
    assert events[-1] == ("error", {"message": "No corpus found."})


def test_prompt_includes_documents_and_grounding_note():
    chunks = [{"source": "seed", "provision": "Amendment X", "subtopic": "Police power",
               "clause_path": "USConst.Amend10", "controlling_precedents": [], "text": "Reserved powers."}]
    prompt = llm.build_user_prompt("Q?", chunks, "weak")
    assert '<document index="1"' in prompt and "Reserved powers." in prompt
    assert "weakly related" in prompt and prompt.rstrip().endswith("</question>")


def test_validation():
    assert TestClient(main.app).post("/api/analyze/stream", json={"query": "x"}).status_code == 422
