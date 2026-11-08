"""The two caches that pay for themselves in a retrieval pipeline (lecture section 07).

embedding cache — the same query text always produces the same vector. Persist it.
retrieval cache — identical questions arrive in bursts during an incident. Short TTL,
                  because the index changes underneath.
"""

import hashlib
import re
import time
from dataclasses import dataclass, field

from . import ollama_client
from .db import connect, to_vector_literal
from .retrieve.types import Candidate

WHITESPACE = re.compile(r"\s+")


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


embedding_stats = CacheStats()
retrieval_stats = CacheStats()


def _fingerprint(text: str) -> str:
    return hashlib.sha256(WHITESPACE.sub(" ", text.strip().lower()).encode()).hexdigest()


def embed_one_cached(text: str) -> list[float]:
    key = _fingerprint(text)
    with connect() as conn:
        row = conn.execute(
            "SELECT embedding::text AS embedding FROM embedding_cache WHERE text_hash = %s",
            (key,),
        ).fetchone()
        if row:
            embedding_stats.hits += 1
            return [float(value) for value in row["embedding"].strip("[]").split(",")]

        embedding_stats.misses += 1
        embedding = ollama_client.embed_one(text)
        conn.execute(
            """
            INSERT INTO embedding_cache (text_hash, embedding) VALUES (%s, %s::vector)
            ON CONFLICT (text_hash) DO NOTHING
            """,
            (key, to_vector_literal(embedding)),
        )
        conn.commit()
    return embedding


@dataclass
class _Entry:
    candidates: list[Candidate]
    expires_at: float


@dataclass
class RetrievalCache:
    ttl_seconds: float = 60.0
    entries: dict[str, _Entry] = field(default_factory=dict)

    def get(self, question: str) -> list[Candidate] | None:
        entry = self.entries.get(_fingerprint(question))
        if entry and entry.expires_at > time.monotonic():
            retrieval_stats.hits += 1
            return entry.candidates
        retrieval_stats.misses += 1
        return None

    def put(self, question: str, candidates: list[Candidate]) -> None:
        self.entries[_fingerprint(question)] = _Entry(
            candidates=candidates, expires_at=time.monotonic() + self.ttl_seconds
        )

    def invalidate_all(self) -> None:
        """Call this from the ingest path. A cache that outlives the index it
        summarises will serve confident answers from documents you deleted."""
        self.entries.clear()


retrieval_cache = RetrievalCache()
