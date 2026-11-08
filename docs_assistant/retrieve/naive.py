from .. import ollama_client
from ..db import connect, to_vector_literal
from .types import Candidate, row_to_candidate

SEARCH_SQL = """
SELECT c.id AS chunk_id, c.doc_id, c.ordinal, c.text,
       d.title, d.doc_type, d.service, d.version, d.status, d.updated_at,
       c.embedding <=> %(embedding)s::vector AS distance
FROM chunk c
JOIN document d ON d.id = c.doc_id
WHERE d.visibility = 'everyone'
ORDER BY distance
LIMIT %(limit)s
"""


def search(query: str, top_k: int = 5) -> list[Candidate]:
    embedding = ollama_client.embed_one(query)
    with connect() as conn:
        rows = conn.execute(
            SEARCH_SQL,
            {"embedding": to_vector_literal(embedding), "limit": top_k},
        ).fetchall()
    return [row_to_candidate(row) for row in rows]


def rank_of_document(query: str, doc_id: str, depth: int = 50) -> int | None:
    """Where does the document that actually answers the question land?
    Used in section 05 to show that top-k is a guess."""
    for position, candidate in enumerate(search(query, top_k=depth), start=1):
        if candidate.doc_id == doc_id:
            return position
    return None
