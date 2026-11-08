"""Retrieval as a decision instead of a step (lecture section 06).

Two mechanics, both bounded:
  grade_and_requery — retrieve, grade the batch, rewrite and retry if it is thin
  route             — decide up front how much retrieval this question deserves
"""

import json
import re
from dataclasses import dataclass, field

from .. import ollama_client
from ..pipeline import retrieve_result_side
from .types import Candidate

GRADE_SYSTEM = """You judge whether a set of retrieved passages is enough to answer a
question.

Set "sufficient": true if a careful engineer could write a useful, cited answer from these
passages — even a partial one that names the cause or points at the right procedure. It
does not have to be complete or elegant.

Set "sufficient": false only when the passages genuinely do not contain the answer: they
are about a different subject, or they describe the symptom without any cause, procedure
or decision.

When it is false, "next_query" must search for the SAME thing in different words — the
underlying mechanism, the component named in the passages, the decision record. Do not
change the subject, and do not ask for logs, dashboards or live data: this is a
documentation search, not an investigation.

Examples:
  Q: "why is checkout erroring with nothing in our logs?"
  Passages describe an edge gateway mapping failures onto a generic error.
  -> {"sufficient": true, "missing": "", "next_query": ""}

  Q: "who owns catalog?"
  Passages are all about how the catalog search index is rebuilt.
  -> {"sufficient": false, "missing": "the owning team",
      "next_query": "service ownership table escalation contacts"}

  Q: "why is it 502ing?"
  Passages list 502 triage steps but never say what causes it.
  -> {"sufficient": false, "missing": "the root cause",
      "next_query": "outbound connection pool saturation upstream timeout"}

Return ONLY JSON:
{"sufficient": true|false, "missing": "<one short phrase>", "next_query": "<query or empty>"}"""

ROUTE_SYSTEM = """Classify how much documentation retrieval a question needs.

Assume the documentation covers internal engineering: architecture decisions, runbooks,
API references, incident postmortems and platform policies. Almost every real question
needs retrieval — "none" is only for questions that are not about the documentation at all.

  none     greetings, small talk, or a question about the assistant itself
  one_shot one fact that lives in one document — a lookup
  full     needs paraphrasing, metadata filtering or reranking to find the right document
  agentic  needs several dependent lookups, where the second depends on the first

Examples:
  "hi, what can you do?"                                    -> none
  "what python version do we target"                        -> one_shot
  "how long do we keep webhook delivery records"            -> one_shot
  "why is it 502ing?"                                       -> full
  "checkout is erroring and our dashboards look fine"       -> full
  "which services use the v3 auth flow, and who owns them?" -> agentic

Return ONLY JSON: {"route": "none|one_shot|full|agentic", "why": "<8 words max>"}"""

JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class Attempt:
    query: str
    candidates: list[Candidate]
    sufficient: bool
    missing: str


@dataclass
class AgenticResult:
    candidates: list[Candidate]
    attempts: list[Attempt] = field(default_factory=list)
    stopped_because: str = ""


def _parse_object(raw: str) -> dict:
    match = JSON_OBJECT.search(raw)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def grade(question: str, candidates: list[Candidate]) -> dict:
    if not candidates:
        return {"sufficient": False, "missing": "nothing was retrieved", "next_query": question}
    passages = "\n\n".join(
        f"[{candidate.cite()}] {candidate.context_text[:500]}" for candidate in candidates
    )
    parsed = _parse_object(
        ollama_client.complete(
            GRADE_SYSTEM, f"Question: {question}\n\nPassages:\n{passages}", max_tokens=200
        )
    )
    return {
        "sufficient": bool(parsed.get("sufficient", True)),
        "missing": str(parsed.get("missing", "")),
        "next_query": str(parsed.get("next_query", "")),
    }


def route(question: str) -> dict:
    parsed = _parse_object(ollama_client.complete(ROUTE_SYSTEM, question, max_tokens=120))
    chosen = parsed.get("route")
    if chosen not in {"none", "one_shot", "full", "agentic"}:
        chosen = "full"
    return {"route": chosen, "why": str(parsed.get("why", ""))}


def grade_and_requery(
    question: str,
    top_k: int = 5,
    max_attempts: int = 3,
    visible_to: str | None = None,
) -> AgenticResult:
    result = AgenticResult(candidates=[])
    query = question

    for attempt_number in range(1, max_attempts + 1):
        candidates, _ = retrieve_result_side(
            query, top_k=top_k, visible_to=visible_to
        )
        verdict = grade(question, candidates)
        result.attempts.append(
            Attempt(
                query=query,
                candidates=candidates,
                sufficient=verdict["sufficient"],
                missing=verdict["missing"],
            )
        )
        result.candidates = _merge(result.candidates, candidates, top_k)

        if verdict["sufficient"]:
            result.stopped_because = f"graded sufficient on attempt {attempt_number}"
            return result

        next_query = verdict["next_query"].strip()
        if not next_query or next_query == query:
            result.stopped_because = "grader could not propose a different query"
            return result
        query = next_query

    result.stopped_because = f"hit the {max_attempts}-attempt ceiling"
    return result


def _merge(
    kept: list[Candidate], fresh: list[Candidate], top_k: int
) -> list[Candidate]:
    by_id = {candidate.chunk_id: candidate for candidate in kept}
    for candidate in fresh:
        by_id.setdefault(candidate.chunk_id, candidate)
    ranked = sorted(
        by_id.values(),
        key=lambda c: (-(c.rerank_score or 0.0), c.distance),
    )
    return ranked[: top_k * 2]
