from . import ollama_client
from .retrieve.types import Candidate

GROUNDING_CONTRACT = """You are the internal engineering documentation assistant.

Rules, in priority order:
1. Answer ONLY from the CONTEXT below. Your own knowledge of frameworks, error codes
   and conventions is not evidence — if it is not in the context, you do not know it.
2. Every factual sentence ends with the citation of the passage it came from, in the
   form [doc-id#ordinal]. A sentence with no citation is a rule violation.
3. If the context does not answer the question, reply exactly:
   "I don't have that in the docs." then list what you would need — a service name, a
   version, a document type — to find it.
4. If two passages disagree, say so and cite both. Prefer the one whose status is
   active over one marked superseded, and say why.
5. Be terse. Six sentences at most. No headings, no numbered plans, no restating the
   question. An engineer is reading this while an incident is open.

This is the required shape of an answer — match its shape, never its content. It is
about a service that does not exist in the CONTEXT:

  Thumbnails stop appearing when the resize queue backs up, not when uploads fail
  [rb-media-thumbnails#0]. The worker pool is capped at four by design, because each
  resize holds a full image in memory [adr-0090#2]. A single oversized upload can stall a
  worker for minutes while the queue keeps growing [pm-2026-08-media-backlog#1]. Check
  queue depth and the oldest pending job age first [rb-media-thumbnails#1].

CONTEXT
{context}"""

UNGROUNDED_SYSTEM = """You are the internal engineering documentation assistant.
Answer the engineer's question."""

NO_CONTEXT = "(no passages retrieved)"


def format_context(candidates: list[Candidate]) -> str:
    if not candidates:
        return NO_CONTEXT
    blocks = []
    for candidate in candidates:
        header = (
            f"[{candidate.cite()}] {candidate.title} — {candidate.doc_type}, "
            f"service {candidate.service}"
            f"{f', {candidate.version}' if candidate.version else ''}"
            f", status {candidate.status}, updated {candidate.updated_at}"
        )
        blocks.append(f"{header}\n{candidate.context_text}")
    return "\n\n---\n\n".join(blocks)


def answer(question: str, candidates: list[Candidate]) -> str:
    return ollama_client.complete(
        GROUNDING_CONTRACT.format(context=format_context(candidates)), question, max_tokens=500
    )


def answer_without_retrieval(question: str) -> str:
    """The section 03 baseline: what the model says when it has no documents at all."""
    return ollama_client.complete(UNGROUNDED_SYSTEM, question, temperature=0.3, max_tokens=350)
