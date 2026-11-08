from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

from .settings import settings

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS document (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    doc_type      TEXT NOT NULL,
    service       TEXT NOT NULL,
    version       TEXT,
    status        TEXT NOT NULL DEFAULT 'active',
    visibility    TEXT NOT NULL DEFAULT 'everyone',
    updated_at    DATE NOT NULL,
    body          TEXT NOT NULL,
    content_hash  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunk (
    id             BIGSERIAL PRIMARY KEY,
    doc_id         TEXT NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    ordinal        INTEGER NOT NULL,
    text           TEXT NOT NULL,
    context_prefix TEXT,
    embedding      vector(768),
    UNIQUE (doc_id, ordinal)
);

CREATE INDEX IF NOT EXISTS chunk_embedding_idx
    ON chunk USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS document_service_idx ON document (service);
CREATE INDEX IF NOT EXISTS document_type_idx ON document (doc_type);

CREATE TABLE IF NOT EXISTS embedding_cache (
    text_hash  TEXT PRIMARY KEY,
    embedding  vector(768) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        yield conn


def apply_schema() -> None:
    with connect() as conn:
        conn.execute(SCHEMA)
        conn.commit()


def reset() -> None:
    with connect() as conn:
        conn.execute("DROP TABLE IF EXISTS chunk, document, embedding_cache CASCADE")
        conn.commit()
    apply_schema()


def to_vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{value:.7f}" for value in embedding) + "]"


def count_rows() -> dict[str, int]:
    with connect() as conn:
        documents = conn.execute("SELECT count(*) AS n FROM document").fetchone()["n"]
        chunks = conn.execute("SELECT count(*) AS n FROM chunk").fetchone()["n"]
    return {"documents": documents, "chunks": chunks}
