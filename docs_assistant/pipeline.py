"""The three fixed retrieval pipelines the lecture builds up, in order.

naive        section 03 — embed the question, take the top k
query_side   section 04 — rewrite, expand, extract filters, union the results
result_side  section 05 — retrieve wide, fuse by rank, rerank, diversify, expand, reorder
"""

from dataclasses import dataclass, field

from .retrieve import query_side, result_side
from .retrieve.naive import search as naive_search
from .retrieve.types import Candidate


@dataclass
class RetrievalTrace:
    mode: str
    standalone_query: str
    queries: list[str] = field(default_factory=list)
    filters: dict = field(default_factory=dict)
    candidates_considered: int = 0
    notes: list[str] = field(default_factory=list)


def retrieve_naive(question: str, top_k: int = 5) -> tuple[list[Candidate], RetrievalTrace]:
    candidates = naive_search(question, top_k=top_k)
    trace = RetrievalTrace(mode="naive", standalone_query=question, queries=[question])
    trace.candidates_considered = len(candidates)
    return candidates, trace


def retrieve_query_side(
    question: str,
    history: list[dict] | None = None,
    top_k: int = 5,
    visible_to: str | None = None,
) -> tuple[list[Candidate], RetrievalTrace]:
    standalone = query_side.rewrite(question, history or [])
    filters = query_side.extract_filters(standalone)
    semantic = filters.get("semantic_query") or standalone
    queries = query_side.multi_query(semantic)

    ranked_lists = query_side.search_many(
        queries, top_k=top_k, filters=filters, visible_to=visible_to
    )

    best_by_chunk: dict[int, Candidate] = {}
    for ranked in ranked_lists:
        for candidate in ranked:
            existing = best_by_chunk.get(candidate.chunk_id)
            if existing is None or candidate.distance < existing.distance:
                best_by_chunk[candidate.chunk_id] = candidate

    candidates = sorted(best_by_chunk.values(), key=lambda c: c.distance)
    trace = RetrievalTrace(
        mode="query_side",
        standalone_query=standalone,
        queries=queries,
        filters=filters,
        candidates_considered=len(best_by_chunk),
        notes=[
            f"{len(ranked_lists)} ranked lists, union + dedupe by best distance "
            "— rank fusion arrives in section 05"
        ],
    )
    return candidates[:top_k], trace


def retrieve_result_side(
    question: str,
    history: list[dict] | None = None,
    top_k: int = 5,
    fetch_depth: int = 16,
    visible_to: str | None = None,
    use_hyde: bool = False,
    filters_override: dict | None = None,
) -> tuple[list[Candidate], RetrievalTrace]:
    standalone = query_side.rewrite(question, history or [])
    filters = (
        dict(filters_override)
        if filters_override is not None
        else query_side.extract_filters(standalone)
    )
    semantic = filters.get("semantic_query") or standalone
    queries = query_side.multi_query(semantic)
    if use_hyde:
        queries.append(query_side.hyde(semantic))

    ranked_lists = query_side.search_many(
        queries, top_k=fetch_depth, filters=filters, visible_to=visible_to
    )

    fused = result_side.reciprocal_rank_fusion(ranked_lists)
    reranked = result_side.llm_rerank(semantic, fused[:fetch_depth], top_k=top_k * 2)
    diversified = result_side.maximal_marginal_relevance(reranked, top_k=top_k)
    expanded = result_side.parent_expand(diversified)
    ordered = result_side.reorder_for_attention(expanded)

    trace = RetrievalTrace(
        mode="result_side",
        standalone_query=standalone,
        queries=queries,
        filters=filters,
        candidates_considered=len(fused),
        notes=[
            f"fetched {len(fused)} unique chunks, reranked to {len(reranked)}, "
            f"diversified to {len(diversified)}, reordered for attention"
        ],
    )
    return ordered, trace
