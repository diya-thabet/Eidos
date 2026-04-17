"""
Tests for the vector store interface and in-memory implementation.

Covers: collection creation, upsert, search with cosine similarity,
filtering, deletion, and edge cases.
"""

import pytest

from app.indexing.vector_store import InMemoryVectorStore, VectorRecord, _cosine_similarity


@pytest.fixture
def store():
    return InMemoryVectorStore()


class TestInMemoryVectorStore:
    @pytest.mark.asyncio
    async def test_ensure_collection(self, store):
        await store.ensure_collection("test", 4)
        assert "test" in store._collections

    @pytest.mark.asyncio
    async def test_ensure_collection_idempotent(self, store):
        await store.ensure_collection("test", 4)
        await store.ensure_collection("test", 4)
        assert "test" in store._collections

    @pytest.mark.asyncio
    async def test_upsert_and_count(self, store):
        await store.ensure_collection("test", 4)
        records = [
            VectorRecord(id="r1", snapshot_id="s1", scope_type="symbol_summary", text="hello"),
            VectorRecord(id="r2", snapshot_id="s1", scope_type="module_summary", text="world"),
        ]
        vectors = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]
        count = await store.upsert("test", records, vectors)
        assert count == 2
        assert store.count("test") == 2

    @pytest.mark.asyncio
    async def test_search_returns_sorted_by_score(self, store):
        await store.ensure_collection("test", 4)
        records = [
            VectorRecord(
                id="r1", snapshot_id="s1", scope_type="symbol_summary", text="exact match"
            ),
            VectorRecord(id="r2", snapshot_id="s1", scope_type="symbol_summary", text="different"),
        ]
        vectors = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]
        await store.upsert("test", records, vectors)

        # Search with query close to r1
        results = await store.search("test", [1.0, 0.0, 0.0, 0.0], limit=2)
        assert len(results) == 2
        assert results[0].record.id == "r1"
        assert results[0].score > results[1].score

    @pytest.mark.asyncio
    async def test_search_with_limit(self, store):
        await store.ensure_collection("test", 4)
        records = [
            VectorRecord(id=f"r{i}", snapshot_id="s1", scope_type="symbol_summary", text=f"t{i}")
            for i in range(10)
        ]
        vectors = [[float(i == j) for j in range(4)] for i in range(10)]
        await store.upsert("test", records, vectors)

        results = await store.search("test", [1.0, 0.0, 0.0, 0.0], limit=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_search_with_snapshot_filter(self, store):
        await store.ensure_collection("test", 4)
        records = [
            VectorRecord(id="r1", snapshot_id="s1", scope_type="symbol_summary", text="a"),
            VectorRecord(id="r2", snapshot_id="s2", scope_type="symbol_summary", text="b"),
        ]
        vectors = [[1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]]
        await store.upsert("test", records, vectors)

        results = await store.search("test", [1.0, 0.0, 0.0, 0.0], filters={"snapshot_id": "s1"})
        assert len(results) == 1
        assert results[0].record.snapshot_id == "s1"

    @pytest.mark.asyncio
    async def test_search_with_scope_type_filter(self, store):
        await store.ensure_collection("test", 4)
        records = [
            VectorRecord(id="r1", snapshot_id="s1", scope_type="symbol_summary", text="a"),
            VectorRecord(id="r2", snapshot_id="s1", scope_type="module_summary", text="b"),
        ]
        vectors = [[1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]]
        await store.upsert("test", records, vectors)

        results = await store.search(
            "test", [1.0, 0.0, 0.0, 0.0], filters={"scope_type": "module_summary"}
        )
        assert len(results) == 1
        assert results[0].record.scope_type == "module_summary"

    @pytest.mark.asyncio
    async def test_delete_by_snapshot(self, store):
        await store.ensure_collection("test", 4)
        records = [
            VectorRecord(id="r1", snapshot_id="s1", scope_type="symbol_summary", text="a"),
            VectorRecord(id="r2", snapshot_id="s2", scope_type="symbol_summary", text="b"),
            VectorRecord(id="r3", snapshot_id="s1", scope_type="module_summary", text="c"),
        ]
        vectors = [[1.0, 0.0, 0.0, 0.0]] * 3
        await store.upsert("test", records, vectors)

        deleted = await store.delete_by_snapshot("test", "s1")
        assert deleted == 2
        assert store.count("test") == 1

    @pytest.mark.asyncio
    async def test_search_empty_collection(self, store):
        await store.ensure_collection("test", 4)
        results = await store.search("test", [1.0, 0.0, 0.0, 0.0])
        assert results == []

    @pytest.mark.asyncio
    async def test_upsert_overwrite(self, store):
        await store.ensure_collection("test", 4)
        r = VectorRecord(id="r1", snapshot_id="s1", scope_type="symbol_summary", text="v1")
        await store.upsert("test", [r], [[1.0, 0.0, 0.0, 0.0]])

        r2 = VectorRecord(id="r1", snapshot_id="s1", scope_type="symbol_summary", text="v2")
        await store.upsert("test", [r2], [[0.0, 1.0, 0.0, 0.0]])

        assert store.count("test") == 1
        results = await store.search("test", [0.0, 1.0, 0.0, 0.0])
        assert results[0].record.text == "v2"


class TestCosineSimilarity:
    def test_identical_vectors(self):
        assert abs(_cosine_similarity([1, 0, 0], [1, 0, 0]) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        assert abs(_cosine_similarity([1, 0, 0], [0, 1, 0])) < 1e-6

    def test_opposite_vectors(self):
        assert abs(_cosine_similarity([1, 0], [-1, 0]) + 1.0) < 1e-6

    def test_empty_vectors(self):
        assert _cosine_similarity([], []) == 0.0

    def test_zero_vector(self):
        assert _cosine_similarity([0, 0], [1, 1]) == 0.0
