import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import ollama_client
from .db import connect, to_vector_literal
from .settings import CORPUS_DIR

FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)

CONTEXT_PREFIX_SYSTEM = """You situate a document excerpt inside its parent document.
Write ONE short sentence (max 25 words) naming the service, the document, and what
this excerpt is about, so the sentence alone is enough to judge relevance.
Output the sentence only — no preamble, no quotes."""


@dataclass
class ParsedDocument:
    id: str
    title: str
    doc_type: str
    service: str
    version: str | None
    status: str
    visibility: str
    updated_at: str
    body: str

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.body.encode()).hexdigest()[:16]


@dataclass
class PendingChunk:
    document: ParsedDocument
    ordinal: int
    text: str
    context_prefix: str | None = None
    embedding: list[float] | None = None

    @property
    def embedding_input(self) -> str:
        return f"{self.context_prefix}\n\n{self.text}" if self.context_prefix else self.text


def parse(path: Path) -> ParsedDocument:
    match = FRONTMATTER.match(path.read_text())
    if not match:
        raise ValueError(f"{path.name} has no frontmatter block")
    meta = yaml.safe_load(match.group(1))
    return ParsedDocument(
        id=meta["id"],
        title=meta["title"],
        doc_type=meta["doc_type"],
        service=meta["service"],
        version=meta.get("version"),
        status=meta.get("status", "active"),
        visibility=meta.get("visibility", "everyone"),
        updated_at=str(meta["updated_at"]),
        body=match.group(2).strip(),
    )


def load_corpus(corpus_dir: Path = CORPUS_DIR) -> list[ParsedDocument]:
    return [parse(path) for path in sorted(corpus_dir.glob("*.md"))]


def split_into_chunks(body: str) -> list[str]:
    """Paragraph-boundary split. Chunking strategy is the data foundations session's topic — this is
    deliberately the simplest thing that works, so the lecture can focus on what happens
    after the chunks exist."""
    paragraphs = [block.strip() for block in body.split("\n\n") if block.strip()]
    chunks: list[str] = []
    buffer = ""
    for paragraph in paragraphs:
        candidate = f"{buffer}\n\n{paragraph}".strip()
        if len(candidate) > 900 and buffer:
            chunks.append(buffer)
            buffer = paragraph
        else:
            buffer = candidate
    if buffer:
        chunks.append(buffer)
    return chunks


def build_context_prefix(document: ParsedDocument, chunk: str) -> str:
    user = (
        f"Document: {document.title} ({document.id}, {document.doc_type}, "
        f"service {document.service})\n\nExcerpt:\n{chunk[:1200]}"
    )
    return ollama_client.complete(CONTEXT_PREFIX_SYSTEM, user, max_tokens=80).splitlines()[0][:300]


def changed_documents(documents: list[ParsedDocument]) -> tuple[list[ParsedDocument], int]:
    """Content-hash comparison, so re-seeding only re-embeds what actually changed."""
    with connect() as conn:
        stored = {
            row["id"]: row["content_hash"]
            for row in conn.execute("SELECT id, content_hash FROM document").fetchall()
        }
    changed = [
        document
        for document in documents
        if stored.get(document.id) != document.content_hash
    ]
    return changed, len(documents) - len(changed)


def ingest(
    documents: list[ParsedDocument],
    contextual: bool = True,
    concurrency: int = 4,
    embed_batch_size: int = 16,
    on_progress=None,
) -> dict[str, int]:
    """Four phases. Splitting the LLM phase from the embedding phase keeps each model
    resident instead of alternating between them once per document."""
    changed, skipped = changed_documents(documents)
    if not changed:
        return {"documents": 0, "chunks": 0, "skipped": skipped}

    pending = [
        PendingChunk(document=document, ordinal=ordinal, text=text)
        for document in changed
        for ordinal, text in enumerate(split_into_chunks(document.body))
    ]

    if contextual:
        _attach_context_prefixes(pending, concurrency, on_progress)
    _attach_embeddings(pending, embed_batch_size, on_progress)
    _write(changed, pending)

    return {"documents": len(changed), "chunks": len(pending), "skipped": skipped}


def _attach_context_prefixes(
    pending: list[PendingChunk], concurrency: int, on_progress
) -> None:
    def build(item: PendingChunk) -> PendingChunk:
        item.context_prefix = build_context_prefix(item.document, item.text)
        return item

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        for done, _ in enumerate(pool.map(build, pending), start=1):
            if on_progress:
                on_progress("context", done, len(pending))


def _attach_embeddings(
    pending: list[PendingChunk], batch_size: int, on_progress
) -> None:
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        for item, embedding in zip(batch, ollama_client.embed([i.embedding_input for i in batch])):
            item.embedding = embedding
        if on_progress:
            on_progress("embed", min(start + batch_size, len(pending)), len(pending))


def _write(documents: list[ParsedDocument], pending: list[PendingChunk]) -> None:
    with connect() as conn:
        for document in documents:
            conn.execute(
                """
                INSERT INTO document (id, title, doc_type, service, version, status,
                                      visibility, updated_at, body, content_hash)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title, doc_type = EXCLUDED.doc_type,
                    service = EXCLUDED.service, version = EXCLUDED.version,
                    status = EXCLUDED.status, visibility = EXCLUDED.visibility,
                    updated_at = EXCLUDED.updated_at, body = EXCLUDED.body,
                    content_hash = EXCLUDED.content_hash
                """,
                (
                    document.id,
                    document.title,
                    document.doc_type,
                    document.service,
                    document.version,
                    document.status,
                    document.visibility,
                    document.updated_at,
                    document.body,
                    document.content_hash,
                ),
            )
            conn.execute("DELETE FROM chunk WHERE doc_id = %s", (document.id,))

        for item in pending:
            conn.execute(
                """
                INSERT INTO chunk (doc_id, ordinal, text, context_prefix, embedding)
                VALUES (%s, %s, %s, %s, %s::vector)
                """,
                (
                    item.document.id,
                    item.ordinal,
                    item.text,
                    item.context_prefix,
                    to_vector_literal(item.embedding),
                ),
            )
        conn.commit()
