"""Everything that happens BEFORE the vector search (lecture section 04)."""

import json
import re

from .. import ollama_client
from ..db import connect, to_vector_literal
from .types import Candidate, row_to_candidate

REWRITE_SYSTEM = """Rewrite the user's latest message as a standalone search query.
Resolve every pronoun and every implicit reference using the conversation history.
Keep the user's own technical vocabulary. Output the query only, on one line."""

MULTI_QUERY_SYSTEM = """You expand a search query into alternative phrasings for a
vector search over internal engineering documentation (ADRs, runbooks, API references,
incident postmortems).
Write {count} alternatives, one per line, no numbering. Each one must use different
vocabulary from the others — synonyms, the error-message wording, the architectural
wording. Do not answer the question."""

HYDE_SYSTEM = """You write a short passage that LOOKS like an excerpt from internal
engineering documentation answering the user's question. Invent plausible specifics —
service names, config keys, status codes. Accuracy does not matter: this passage is
only used as a vector search key. Maximum 90 words, no preamble."""

DECOMPOSE_SYSTEM = """Split the question into the minimum set of independent lookups
needed to answer it. If one lookup is enough, return exactly one line.
Output one self-contained sub-question per line, no numbering, maximum 4 lines."""

STEP_BACK_SYSTEM = """Write the more general question whose answer provides the
background needed to answer the user's specific question. One line, no preamble."""

SELF_QUERY_SYSTEM = """Extract metadata filters from the question for a document search.

Return ONLY a JSON object. Include a key ONLY if the question states that constraint
explicitly. Omitting a key is always safe; guessing one hides the answer.

  "service":        one of {services} — only if the question names it
  "doc_type":       one of {doc_types} — only if the question names the KIND of document
  "version":        one of {versions} — only if the question names a version
  "semantic_query": the question with the extracted constraints removed

"doc_type" is the trap. A question about a procedure is NOT a request for a runbook, and a
question about an outage is NOT a request for a postmortem. The answer may live in any
kind of document. Only set "doc_type" if the user asked for a document type by name.

Examples:
  "how does the v4 auth flow work?"
      -> {{"version": "v4", "semantic_query": "how does the auth flow work"}}
  "is there a runbook for draining the notify DLQ?"
      -> {{"service": "notify-svc", "doc_type": "runbook", "semantic_query": "draining the DLQ"}}
  "i rotated the db password and now nothing can connect"
      -> {{}}
  "how do I roll back a checkout deploy"
      -> {{"service": "checkout-svc", "semantic_query": "how do I roll back a deploy"}}
  "why is it 502ing?"
      -> {{}}

Today is {today}."""

FILTERED_SEARCH_SQL = """
SELECT c.id AS chunk_id, c.doc_id, c.ordinal, c.text,
       d.title, d.doc_type, d.service, d.version, d.status, d.updated_at,
       c.embedding <=> %(embedding)s::vector AS distance
FROM chunk c
JOIN document d ON d.id = c.doc_id
WHERE {predicates}
ORDER BY distance
LIMIT %(limit)s
"""

JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def _lines(text: str, limit: int) -> list[str]:
    cleaned = [
        re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip().strip('"')
        for line in text.splitlines()
    ]
    return [line for line in cleaned if line][:limit]


def rewrite(question: str, history: list[dict]) -> str:
    if not history:
        return question
    transcript = "\n".join(f"{turn['role']}: {turn['content']}" for turn in history[-6:])
    user = f"Conversation so far:\n{transcript}\n\nLatest message: {question}"
    return ollama_client.complete(REWRITE_SYSTEM, user, max_tokens=120).splitlines()[0].strip()


def multi_query(question: str, count: int = 2) -> list[str]:
    raw = ollama_client.complete(
        MULTI_QUERY_SYSTEM.format(count=count), question, temperature=0.4, max_tokens=160
    )
    return [question, *_lines(raw, count)]


def hyde(question: str) -> str:
    return ollama_client.complete(HYDE_SYSTEM, question, temperature=0.3, max_tokens=220)


def decompose(question: str) -> list[str]:
    return _lines(ollama_client.complete(DECOMPOSE_SYSTEM, question, max_tokens=160), 4) or [question]


def step_back(question: str) -> str:
    return ollama_client.complete(STEP_BACK_SYSTEM, question, max_tokens=100).splitlines()[0].strip()


def known_facets() -> dict[str, list[str]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT array_agg(DISTINCT service)  AS services,
                   array_agg(DISTINCT doc_type) AS doc_types,
                   array_agg(DISTINCT version)  AS versions
            FROM document
            """
        ).fetchone()
    return {
        "services": sorted(rows["services"] or []),
        "doc_types": sorted(rows["doc_types"] or []),
        "versions": sorted(v for v in (rows["versions"] or []) if v),
    }


def extract_filters(question: str, today: str = "2026-09-01") -> dict:
    facets = known_facets()
    system = SELF_QUERY_SYSTEM.format(
        services=json.dumps(facets["services"]),
        doc_types=json.dumps(facets["doc_types"]),
        versions=json.dumps(facets["versions"]),
        today=today,
    )
    raw = ollama_client.complete(system, question, max_tokens=200)
    match = JSON_OBJECT.search(raw)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}

    allowed = {"service", "doc_type", "version", "semantic_query"}
    filters = {
        key: value
        for key, value in parsed.items()
        if key in allowed and isinstance(value, str) and value.strip()
    }
    for key, valid in (
        ("service", facets["services"]),
        ("doc_type", facets["doc_types"]),
        ("version", facets["versions"]),
    ):
        if key in filters and filters[key] not in valid:
            del filters[key]
    return filters


def filtered_search(
    query: str,
    filters: dict | None = None,
    top_k: int = 5,
    visible_to: str | None = None,
    include_restricted: bool = False,
) -> list[Candidate]:
    """`visible_to=None` means "the caller belongs to no privileged group", so only
    documents marked `everyone` are searchable. It does NOT mean "no filter".

    That distinction is the whole bug class. The obvious implementation — add a visibility
    predicate only when a group was supplied — makes the *default* path the unrestricted
    one, so every call site that forgets the argument silently searches restricted
    documents. Access control has to fail closed; `include_restricted` is the explicit,
    greppable escape hatch for seeding and debugging.
    """
    filters = dict(filters or {})
    filters.pop("semantic_query", None)

    predicates = ["TRUE"]
    params: dict = {
        "embedding": to_vector_literal(ollama_client.embed_one(query)),
        "limit": top_k,
    }
    for key in ("service", "doc_type", "version", "status"):
        if key in filters:
            predicates.append(f"d.{key} = %({key})s")
            params[key] = filters[key]

    if not include_restricted:
        if visible_to is None:
            predicates.append("d.visibility = 'everyone'")
        else:
            predicates.append("d.visibility IN ('everyone', %(visible_to)s)")
            params["visible_to"] = visible_to

    sql = FILTERED_SEARCH_SQL.format(predicates=" AND ".join(predicates))
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [row_to_candidate(row) for row in rows]


def search_many(
    queries: list[str],
    top_k: int = 10,
    filters: dict | None = None,
    visible_to: str | None = None,
) -> list[list[Candidate]]:
    """One ranked list per query, plus one filtered list per query when filters exist.

    The filtered list is an EXTRA list, never a replacement. Filters here are extracted by
    a language model from free text, and a model that invents `doc_type: postmortem` for a
    question whose answer is in a runbook will hide that runbook completely. Adding the
    filtered results as another list means a good filter promotes the right document and a
    bad filter costs nothing but a query. Permission filters are the exception — those are
    passed through as a real constraint on every list, because there recall is not the
    property you are protecting."""
    results: list[list[Candidate]] = []
    real_filters = {
        key: value
        for key, value in (filters or {}).items()
        if key in ("service", "doc_type", "version")
    }

    for query in queries:
        for applied in ({}, real_filters) if real_filters else ({},):
            candidates = filtered_search(
                query, filters=applied, top_k=top_k, visible_to=visible_to
            )
            for candidate in candidates:
                candidate.source_queries = [query]
            results.append(candidates)
    return results
