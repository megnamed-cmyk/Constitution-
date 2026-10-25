"""Claude streaming analysis over retrieved constitutional context."""
from __future__ import annotations

from typing import Any, AsyncIterator

import anthropic

from .config import settings
from .retrieval import Grounding

SYSTEM_PROMPT = """You are a constitutional law analyst. You explain how U.S. constitutional text, structure, and Supreme Court doctrine apply to a question. You are an educational tool, not a lawyer, and your output is not legal advice.

How to work:
- Ground the analysis in the retrieved documents. Cite them inline as [1], [2], etc., matching their index. When you rely on doctrine or a case that is not in the retrieved documents, say so plainly (e.g. "not in the retrieved sources").
- Keep three layers distinct: the constitutional text itself, later amendments that modify it, and judge-made tests (tiers of scrutiny, multi-factor balancing). Say which layer each point comes from.
- If the question rests on a false or contested premise, don't adopt it. State the governing standard, then evaluate the scenario under it.
- Where doctrine is unsettled or the Justices are split, present the competing positions rather than picking one as settled law.
- Never invent case names, citations, holdings, or vote counts. If you aren't sure of a citation, describe the holding without one.

Format the answer in Markdown with these sections:
## Constitutional Provisions Engaged
## Controlling Tests & Standards of Review
## Precedential Application
## Conclusion
"""

_GROUNDING_NOTES: dict[Grounding, str] = {
    "grounded": "",
    "weak": (
        "NOTE: Retrieval found only weakly related documents. Open the answer with one sentence "
        "saying the retrieved support is thin, and lean on general doctrine where needed, labeled as such."
    ),
    "none": (
        "NOTE: Retrieval found nothing relevant in the corpus. Open the answer by saying the corpus "
        "doesn't cover this question, then give a brief general-doctrine answer clearly labeled as "
        "not drawn from retrieved sources."
    ),
}


def format_context(chunks: list[dict[str, Any]]) -> str:
    blocks = []
    for i, c in enumerate(chunks, start=1):
        precedents = ", ".join(c.get("controlling_precedents") or []) or "none listed"
        blocks.append(
            f'<document index="{i}" source="{c["source"]}" provision="{c["provision"]}">\n'
            f"Subtopic: {c['subtopic']}\n"
            f"Path: {c['clause_path']}\n"
            f"Precedents mentioned: {precedents}\n\n"
            f"{c['text']}\n"
            f"</document>"
        )
    return "\n\n".join(blocks)


def build_user_prompt(query: str, chunks: list[dict[str, Any]], grounding: Grounding) -> str:
    parts = [f"<retrieved_documents>\n{format_context(chunks)}\n</retrieved_documents>"]
    note = _GROUNDING_NOTES[grounding]
    if note:
        parts.append(note)
    parts.append(f"<question>\n{query}\n</question>")
    return "\n\n".join(parts)


_client: anthropic.AsyncAnthropic | None = None


def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic()
    return _client


async def stream_analysis(query: str, chunks: list[dict[str, Any]], grounding: Grounding) -> AsyncIterator[dict[str, Any]]:
    """Yields events: {"type": "status"|"delta"|"refusal", ...}. API errors propagate to the caller."""
    async with get_client().beta.messages.stream(
        model=settings.model,
        max_tokens=settings.max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_prompt(query, chunks, grounding)}],
        thinking={"type": "adaptive"},
        output_config={"effort": settings.effort},
        # Re-run on Anthropic's recommended fallback model if a safety classifier declines.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    ) as stream:
        async for event in stream:
            if event.type == "content_block_start" and event.content_block.type == "thinking":
                yield {"type": "status", "message": "Reasoning through the doctrine…"}
            elif event.type == "content_block_delta" and event.delta.type == "text_delta":
                yield {"type": "delta", "text": event.delta.text}
        final = await stream.get_final_message()
        if final.stop_reason == "refusal":
            yield {"type": "refusal", "message": "The model declined to answer this request."}
        elif final.stop_reason == "max_tokens":
            yield {"type": "status", "message": "Answer truncated at the token limit."}
