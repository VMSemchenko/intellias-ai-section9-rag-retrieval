"""The hardened agent loop from lecture section 02, with section 04-06 retrieval
behind the search_docs tool.

Everything the minimal loop lacked is here and named:
  iteration ceiling, no-progress detection, bounded tool results, errors-as-data,
  a trimmed history window, and an explicit termination policy.
"""

import json
from dataclasses import dataclass, field

from . import ollama_client
from .db import connect
from .generate import GROUNDING_CONTRACT
from .pipeline import retrieve_result_side
from .retrieve import query_side
from .settings import settings

SYSTEM_PROMPT = """You are the internal engineering documentation assistant.

You work by looking things up. You have four tools and a hard budget of {max_iterations}
tool calls per question — spend them.

How to work:
  - Start with search_docs. Narrow it with the service and doc_type arguments once you
    know them; call list_services first if you are unsure what exists.
  - search_docs returns excerpts. When an excerpt looks like the answer but is cut off,
    or when it points at another document by id, call fetch_doc.
  - A question that mentions two things usually needs two searches. Do them.
  - Call escalate only when the docs genuinely do not cover the question.

Answer rules:
  - Answer only from what the tools returned. Cite every factual sentence as
    [doc-id#ordinal] or [doc-id].
  - If a document is marked superseded, say so and cite the active one.
  - If you never found it, say "I don't have that in the docs." and name what is missing.
  - Be terse. An engineer is reading this while an incident is open."""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": (
                "Semantic search over internal engineering documentation. Returns "
                "ranked excerpts with their document ids, status and last-updated date. "
                "Use natural language, not keywords."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What you are looking for, as a full question or statement.",
                    },
                    "service": {
                        "type": "string",
                        "description": "Restrict to one service. Omit if unknown — do not guess.",
                    },
                    "doc_type": {
                        "type": "string",
                        "enum": ["adr", "runbook", "api", "postmortem", "policy"],
                        "description": (
                            "Restrict to one document type. Set this ONLY if the user asked "
                            "for a kind of document by name. A question about a procedure is "
                            "not a request for a runbook, and a question about an outage is "
                            "not a request for a postmortem — the answer may be in any kind "
                            "of document. Omit it when in doubt, which is usually."
                        ),
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "1-8, default 5.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_doc",
            "description": (
                "Read one document in full by its id, e.g. 'adr-0042'. Use when an "
                "excerpt is truncated or references another document."
            ),
            "parameters": {
                "type": "object",
                "properties": {"doc_id": {"type": "string"}},
                "required": ["doc_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_services",
            "description": (
                "List every service, document type and version present in the corpus. "
                "Call this when you do not know what the corpus covers."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate",
            "description": (
                "Hand the question to a human owner. Terminal — the loop stops here."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string"},
                    "suggested_owner": {"type": "string"},
                },
                "required": ["reason"],
            },
        },
    },
]

MAX_EXCERPT_CHARS = 600
MAX_DOC_CHARS = 4000


@dataclass
class Step:
    iteration: int
    tool: str
    arguments: dict
    result_preview: str


@dataclass
class AgentRun:
    answer: str
    steps: list[Step] = field(default_factory=list)
    stopped_because: str = ""
    citations: list[str] = field(default_factory=list)


def search_docs(
    query: str,
    service: str | None = None,
    doc_type: str | None = None,
    max_results: int = 5,
    visible_to: str | None = None,
) -> dict:
    filters = {key: value for key, value in (("service", service), ("doc_type", doc_type)) if value}
    candidates, _ = retrieve_result_side(
        query,
        top_k=max(1, min(int(max_results or 5), 8)),
        filters_override=filters,
        visible_to=visible_to,
    )
    if not candidates:
        return {
            "results": [],
            "hint": "Nothing matched. Widen the query, drop the service filter, "
            "or call list_services to see what exists.",
        }
    return {
        "results": [
            {
                "cite": candidate.cite(),
                "doc_id": candidate.doc_id,
                "title": candidate.title,
                "doc_type": candidate.doc_type,
                "service": candidate.service,
                "version": candidate.version,
                "status": candidate.status,
                "updated_at": candidate.updated_at,
                "excerpt": candidate.context_text[:MAX_EXCERPT_CHARS],
            }
            for candidate in candidates
        ]
    }


def fetch_doc(doc_id: str, visible_to: str | None = None) -> dict:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT id, title, doc_type, service, version, status, visibility,
                   updated_at, body
            FROM document WHERE id = %s
            """,
            (doc_id.strip().lower(),),
        ).fetchone()
    if not row:
        return {"error": "no_such_document", "doc_id": doc_id, "hint": "Use search_docs to find valid ids."}
    if visible_to is not None and row["visibility"] not in ("everyone", visible_to):
        return {"error": "not_authorised", "doc_id": doc_id}
    return {
        "doc_id": row["id"],
        "title": row["title"],
        "doc_type": row["doc_type"],
        "service": row["service"],
        "version": row["version"],
        "status": row["status"],
        "updated_at": str(row["updated_at"]),
        "body": row["body"][:MAX_DOC_CHARS],
    }


def list_services(**_) -> dict:
    return query_side.known_facets()


def escalate(reason: str, suggested_owner: str = "platform-team") -> dict:
    return {
        "escalated": True,
        "reason": reason,
        "owner": suggested_owner,
        "message": f"Handing this to {suggested_owner}: {reason}",
    }


TOOL_IMPLEMENTATIONS = {
    "search_docs": search_docs,
    "fetch_doc": fetch_doc,
    "list_services": list_services,
    "escalate": escalate,
}


def run(
    question: str,
    max_iterations: int | None = None,
    visible_to: str | None = None,
) -> AgentRun:
    ceiling = max_iterations or settings.max_agent_iterations
    system = SYSTEM_PROMPT.format(max_iterations=ceiling)
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]
    run_result = AgentRun(answer="")
    seen_calls: set[str] = set()

    for iteration in range(1, ceiling + 1):
        response = ollama_client.chat_with_tools(messages, TOOL_SCHEMAS)
        message = response["message"]
        calls = getattr(message, "tool_calls", None) or []
        messages.append(
            {
                "role": "assistant",
                "content": message["content"] or "",
                **({"tool_calls": calls} if calls else {}),
            }
        )

        if not calls:
            run_result.answer = (message["content"] or "").strip()
            run_result.stopped_because = f"model answered on iteration {iteration}"
            break

        for call in calls:
            name = call["function"]["name"]
            arguments = _coerce_arguments(call["function"]["arguments"])
            fingerprint = f"{name}:{json.dumps(arguments, sort_keys=True)}"

            if fingerprint in seen_calls:
                payload = {
                    "error": "repeated_call",
                    "hint": "You already made this exact call. Change the query, "
                    "drop a filter, or answer with what you have.",
                }
            elif name not in TOOL_IMPLEMENTATIONS:
                payload = {"error": "no_such_tool", "available": list(TOOL_IMPLEMENTATIONS)}
            else:
                seen_calls.add(fingerprint)
                payload = _invoke(name, arguments, visible_to)

            messages.append(
                {"role": "tool", "name": name, "content": json.dumps(payload)[:6000]}
            )
            run_result.steps.append(
                Step(
                    iteration=iteration,
                    tool=name,
                    arguments=arguments,
                    result_preview=json.dumps(payload)[:180],
                )
            )

            if name == "escalate" and payload.get("escalated"):
                run_result.answer = payload["message"]
                run_result.stopped_because = "escalated"
                return run_result
    else:
        run_result.stopped_because = f"hit the {ceiling}-iteration ceiling"
        run_result.answer = _forced_answer(question, messages)

    run_result.citations = _collect_citations(run_result.answer)
    return run_result


def _invoke(name: str, arguments: dict, visible_to: str | None) -> dict:
    """Tool failures come back as data, not exceptions — the model can only recover
    from something it can read."""
    try:
        if name in ("search_docs", "fetch_doc"):
            return TOOL_IMPLEMENTATIONS[name](visible_to=visible_to, **arguments)
        return TOOL_IMPLEMENTATIONS[name](**arguments)
    except TypeError as error:
        return {"error": "bad_arguments", "detail": str(error)}
    except Exception as error:  # noqa: BLE001 — surface anything as a readable result
        return {"error": type(error).__name__, "detail": str(error)[:300]}


def _coerce_arguments(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _forced_answer(question: str, messages: list[dict]) -> str:
    """Hitting the ceiling is not an error the user should see. Answer from whatever
    the tools did return."""
    gathered = "\n\n".join(
        message["content"] for message in messages if message.get("role") == "tool"
    )
    if not gathered.strip():
        return "I don't have that in the docs."
    return ollama_client.complete(
        GROUNDING_CONTRACT.format(context=gathered[:8000]), question, max_tokens=500
    )


def _collect_citations(answer: str) -> list[str]:
    import re

    return sorted(set(re.findall(r"\[([a-z0-9-]+(?:#\d+)?)\]", answer)))
