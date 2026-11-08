"""Everything that happens AFTER the vector search returns candidates (lecture section 05)."""

import math
import re
from concurrent.futures import ThreadPoolExecutor

from .. import ollama_client
from ..db import connect
from .types import Candidate

RERANK_SYSTEM = """You score how well ONE passage answers ONE question.

Scoring scale:
   0-2  unrelated, or the same topic but answers a different question
   3-5  useful background, does not answer the question
   6-8  contains part of the answer
  9-10  contains the answer directly

Judge the passage on what it says, not on whether it repeats the question's words. A
passage that uses completely different vocabulary can still be a 10.

Reply with the number only. No explanation, no punctuation, no other text."""

COMPRESS_SYSTEM = """Copy out ONLY the sentences from the passage that help answer the
question, verbatim and in their original order. Drop everything else.
If no sentence helps, output exactly: NONE"""

FIRST_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def reciprocal_rank_fusion(
    ranked_lists: list[list[Candidate]], k: int = 60
) -> list[Candidate]:
    """Merge several ranked lists by RANK, not by score — distances produced by
    different queries are not on a comparable scale."""
    merged: dict[int, Candidate] = {}
    scores: dict[int, float] = {}

    for ranked in ranked_lists:
        for rank, candidate in enumerate(ranked, start=1):
            scores[candidate.chunk_id] = scores.get(candidate.chunk_id, 0.0) + 1.0 / (
                k + rank
            )
            if candidate.chunk_id in merged:
                merged[candidate.chunk_id].source_queries.extend(candidate.source_queries)
            else:
                merged[candidate.chunk_id] = candidate

    for chunk_id, score in scores.items():
        merged[chunk_id].fused_score = score
    return sorted(merged.values(), key=lambda c: -c.fused_score)


def llm_rerank(
    query: str, candidates: list[Candidate], top_k: int = 5, concurrency: int = 4
) -> list[Candidate]:
    """Pointwise: one call per candidate, one number back.

    Asking a 7B model to score eight passages in a single JSON array returns all-zero
    batches often enough to be useless, and an all-zero batch silently destroys the
    ordering the fusion step produced. One passage per call is more calls and a far more
    reliable signal — and the calls are independent, so they run concurrently.
    """
    def score(candidate: Candidate) -> None:
        raw = ollama_client.complete(
            RERANK_SYSTEM,
            f"Question: {query}\n\nPassage:\n{candidate.context_text[:900]}",
            max_tokens=8,
        )
        candidate.rerank_score = _parse_score(raw)

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        list(pool.map(score, candidates))

    if _is_degenerate(candidates):
        return candidates[:top_k]

    # Fused score breaks ties, so a reranker that cannot separate two passages leaves the
    # fusion order intact instead of shuffling it.
    return sorted(
        candidates,
        key=lambda c: (-(c.rerank_score or 0.0), -(c.fused_score or 0.0), c.distance),
    )[:top_k]


def _parse_score(raw: str) -> float:
    match = FIRST_NUMBER.search(raw)
    if not match:
        return 0.0
    return max(0.0, min(10.0, float(match.group(0))))


def _is_degenerate(candidates: list[Candidate]) -> bool:
    """Every passage scored the same means the reranker told us nothing. Keep the order we
    already had rather than letting a flat signal reshuffle it."""
    scores = {candidate.rerank_score for candidate in candidates}
    return len(scores) <= 1


def maximal_marginal_relevance(
    candidates: list[Candidate], top_k: int = 5, diversity: float = 0.3
) -> list[Candidate]:
    """Five chunks from the same document are not five sources."""
    if not candidates:
        return []
    vectors = _load_embeddings([c.chunk_id for c in candidates])
    selected: list[Candidate] = [candidates[0]]
    remaining = candidates[1:]

    while remaining and len(selected) < top_k:
        best_candidate, best_value = None, -math.inf
        for candidate in remaining:
            relevance = _relevance(candidate)
            redundancy = max(
                _cosine(vectors[candidate.chunk_id], vectors[chosen.chunk_id])
                for chosen in selected
            )
            value = (1 - diversity) * relevance - diversity * redundancy
            if value > best_value:
                best_candidate, best_value = candidate, value
        selected.append(best_candidate)
        remaining.remove(best_candidate)

    return selected


def _relevance(candidate: Candidate) -> float:
    """Once a reranker has scored a candidate, its score is the better relevance signal —
    diversifying on cosine distance would undo the reranking you just paid for."""
    if candidate.rerank_score is not None:
        return candidate.rerank_score / 10.0
    return 1.0 - candidate.distance


def _load_embeddings(chunk_ids: list[int]) -> dict[int, list[float]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, embedding::text AS embedding FROM chunk WHERE id = ANY(%s)",
            (chunk_ids,),
        ).fetchall()
    return {
        row["id"]: [float(value) for value in row["embedding"].strip("[]").split(",")]
        for row in rows
    }


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


def parent_expand(candidates: list[Candidate], window: int = 1) -> list[Candidate]:
    """Retrieve on small chunks (precise), send the surrounding section (complete)."""
    with connect() as conn:
        for candidate in candidates:
            rows = conn.execute(
                """
                SELECT text FROM chunk
                WHERE doc_id = %s AND ordinal BETWEEN %s AND %s
                ORDER BY ordinal
                """,
                (candidate.doc_id, candidate.ordinal - window, candidate.ordinal + window),
            ).fetchall()
            candidate.expanded_text = "\n\n".join(row["text"] for row in rows)
    return candidates


def reorder_for_attention(candidates: list[Candidate]) -> list[Candidate]:
    """Lost in the middle: models attend to the head and tail of a long context.
    Best first, second-best last, weakest buried in the middle."""
    head = candidates[0::2]
    tail = candidates[1::2][::-1]
    return head + tail


def compress(query: str, candidates: list[Candidate]) -> list[Candidate]:
    kept: list[Candidate] = []
    for candidate in candidates:
        extracted = ollama_client.complete(
            COMPRESS_SYSTEM,
            f"Question: {query}\n\nPassage:\n{candidate.context_text[:1600]}",
            max_tokens=320,
        )
        if extracted.strip().upper().startswith("NONE"):
            continue
        candidate.expanded_text = extracted.strip()
        kept.append(candidate)
    return kept or candidates
