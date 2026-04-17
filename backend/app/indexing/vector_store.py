"""
Vector store abstraction layer.

Provides a clean interface for storing and retrieving embeddings.
The concrete implementation talks to Qdrant, but can be swapped
for pgvector or an in-memory store for testing.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class VectorRecord:
    """A single record stored in the vector DB."""

    id: str
    snapshot_id: str
    scope_type: str  # symbol_summary | module_summary | file_summary
    text: str  # the text that was embedded
    refs: list[dict] = field(default_factory=list)  # [{path, start_line, end_line, symbol_fq_name}]
    metadata: dict = field(default_factory=dict)


@dataclass
class SearchResult:
    """A single search result from vector similarity search."""

    record: VectorRecord
    score: float


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------


class VectorStore(ABC):
    """Protocol for vector storage backends."""

    @abstractmethod
    async def ensure_collection(self, name: str, vector_size: int) -> None:
        """Create collection if it doesn't exist."""
        ...

    @abstractmethod
    async def upsert(
        self, collection: str, records: list[VectorRecord], vectors: list[list[float]]
    ) -> int:
        """Insert or update records with their embedding vectors. Returns count."""
        ...

    @abstractmethod
    async def search(
        self,
        collection: str,
        query_vector: list[float],
        limit: int = 10,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        """Search for similar records. Returns sorted by score descending."""
        ...

    @abstractmethod
    async def delete_by_snapshot(self, collection: str, snapshot_id: str) -> int:
        """Delete all records for a snapshot. Returns count deleted."""
        ...


# ---------------------------------------------------------------------------
# In-memory implementation (for testing and when no vector DB is available)
# ---------------------------------------------------------------------------


class InMemoryVectorStore(VectorStore):
    """
    In-memory vector store for testing and development.

    Uses brute-force cosine similarity.  Not suitable for production
    but provides the same interface for integration tests.
    """

    def __init__(self):
        self._collections: dict[str, dict[str, tuple[VectorRecord, list[float]]]] = {}

    async def ensure_collection(self, name: str, vector_size: int) -> None:
        if name not in self._collections:
            self._collections[name] = {}

    async def upsert(
        self, collection: str, records: list[VectorRecord], vectors: list[list[float]]
    ) -> int:
        coll = self._collections.setdefault(collection, {})
        for record, vector in zip(records, vectors):
            coll[record.id] = (record, vector)
        return len(records)

    async def search(
        self,
        collection: str,
        query_vector: list[float],
        limit: int = 10,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        coll = self._collections.get(collection, {})
        scored: list[tuple[float, VectorRecord]] = []
        for record, vector in coll.values():
            if filters:
                if "snapshot_id" in filters and record.snapshot_id != filters["snapshot_id"]:
                    continue
                if "scope_type" in filters and record.scope_type != filters["scope_type"]:
                    continue
            score = _cosine_similarity(query_vector, vector)
            scored.append((score, record))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [SearchResult(record=r, score=s) for s, r in scored[:limit]]

    async def delete_by_snapshot(self, collection: str, snapshot_id: str) -> int:
        coll = self._collections.get(collection, {})
        to_delete = [rid for rid, (rec, _) in coll.items() if rec.snapshot_id == snapshot_id]
        for rid in to_delete:
            del coll[rid]
        return len(to_delete)

    def count(self, collection: str) -> int:
        """Helper for tests: return the number of records."""
        return len(self._collections.get(collection, {}))


# ---------------------------------------------------------------------------
# Qdrant implementation (placeholder -- activated when qdrant_client is available)
# ---------------------------------------------------------------------------


class QdrantVectorStore(VectorStore):
    """
    Qdrant-backed vector store.

    Requires ``qdrant-client`` and a running Qdrant instance.
    This is the production implementation.
    """

    def __init__(self, url: str = "http://localhost:6333"):
        self._url = url
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from qdrant_client import QdrantClient

                self._client = QdrantClient(url=self._url)
            except ImportError:
                raise RuntimeError("qdrant-client is required for QdrantVectorStore")
        return self._client

    async def ensure_collection(self, name: str, vector_size: int) -> None:
        from qdrant_client.models import Distance, VectorParams

        client = self._get_client()
        collections = [c.name for c in client.get_collections().collections]
        if name not in collections:
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
            logger.info("Created Qdrant collection '%s' (size=%d)", name, vector_size)

    async def upsert(
        self, collection: str, records: list[VectorRecord], vectors: list[list[float]]
    ) -> int:
        from qdrant_client.models import PointStruct

        client = self._get_client()
        points = [
            PointStruct(
                id=rec.id,
                vector=vec,
                payload={
                    "snapshot_id": rec.snapshot_id,
                    "scope_type": rec.scope_type,
                    "text": rec.text,
                    "refs": rec.refs,
                    **rec.metadata,
                },
            )
            for rec, vec in zip(records, vectors)
        ]
        client.upsert(collection_name=collection, points=points)
        return len(points)

    async def search(
        self,
        collection: str,
        query_vector: list[float],
        limit: int = 10,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        client = self._get_client()

        qdrant_filter = None
        if filters:
            conditions = []
            for key, val in filters.items():
                conditions.append(FieldCondition(key=key, match=MatchValue(value=val)))
            qdrant_filter = Filter(must=conditions)

        results = client.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=limit,
            query_filter=qdrant_filter,
        )

        return [
            SearchResult(
                record=VectorRecord(
                    id=str(hit.id),
                    snapshot_id=hit.payload.get("snapshot_id", ""),
                    scope_type=hit.payload.get("scope_type", ""),
                    text=hit.payload.get("text", ""),
                    refs=hit.payload.get("refs", []),
                ),
                score=hit.score,
            )
            for hit in results
        ]

    async def delete_by_snapshot(self, collection: str, snapshot_id: str) -> int:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        client = self._get_client()
        client.delete(
            collection_name=collection,
            points_selector=Filter(
                must=[FieldCondition(key="snapshot_id", match=MatchValue(value=snapshot_id))]
            ),
        )
        return -1  # Qdrant doesn't return count


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
