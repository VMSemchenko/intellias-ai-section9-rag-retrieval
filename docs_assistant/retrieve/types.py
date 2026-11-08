from dataclasses import dataclass, field


@dataclass
class Candidate:
    chunk_id: int
    doc_id: str
    title: str
    doc_type: str
    service: str
    version: str | None
    status: str
    updated_at: str
    ordinal: int
    text: str
    distance: float
    rerank_score: float | None = None
    fused_score: float | None = None
    expanded_text: str | None = None
    source_queries: list[str] = field(default_factory=list)

    @property
    def context_text(self) -> str:
        return self.expanded_text or self.text

    def cite(self) -> str:
        return f"{self.doc_id}#{self.ordinal}"


def row_to_candidate(row: dict) -> Candidate:
    return Candidate(
        chunk_id=row["chunk_id"],
        doc_id=row["doc_id"],
        title=row["title"],
        doc_type=row["doc_type"],
        service=row["service"],
        version=row["version"],
        status=row["status"],
        updated_at=str(row["updated_at"]),
        ordinal=row["ordinal"],
        text=row["text"],
        distance=float(row["distance"]),
    )
