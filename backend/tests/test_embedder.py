"""
Tests for the embedder interface and implementations.

Covers: HashEmbedder determinism, vector size, normalisation,
OpenAI fallback, factory function.
"""

import pytest

from app.indexing.embedder import DEFAULT_VECTOR_SIZE, HashEmbedder, OpenAIEmbedder, create_embedder


class TestHashEmbedder:
    @pytest.mark.asyncio
    async def test_produces_correct_size(self):
        emb = HashEmbedder(size=128)
        vectors = await emb.embed(["hello world"])
        assert len(vectors) == 1
        assert len(vectors[0]) == 128

    @pytest.mark.asyncio
    async def test_default_size(self):
        emb = HashEmbedder()
        assert emb.vector_size == DEFAULT_VECTOR_SIZE
        vectors = await emb.embed(["test"])
        assert len(vectors[0]) == DEFAULT_VECTOR_SIZE

    @pytest.mark.asyncio
    async def test_deterministic(self):
        emb = HashEmbedder()
        v1 = await emb.embed(["same text"])
        v2 = await emb.embed(["same text"])
        assert v1 == v2

    @pytest.mark.asyncio
    async def test_different_texts_produce_different_vectors(self):
        emb = HashEmbedder()
        v = await emb.embed(["text a", "text b"])
        assert v[0] != v[1]

    @pytest.mark.asyncio
    async def test_batch_embedding(self):
        emb = HashEmbedder()
        texts = [f"text {i}" for i in range(10)]
        vectors = await emb.embed(texts)
        assert len(vectors) == 10
        assert all(len(v) == DEFAULT_VECTOR_SIZE for v in vectors)

    @pytest.mark.asyncio
    async def test_normalised_to_unit_length(self):
        emb = HashEmbedder()
        vectors = await emb.embed(["test normalisation"])
        v = vectors[0]
        norm = sum(x * x for x in v) ** 0.5
        assert abs(norm - 1.0) < 1e-5

    @pytest.mark.asyncio
    async def test_empty_text(self):
        emb = HashEmbedder()
        vectors = await emb.embed([""])
        assert len(vectors) == 1
        assert len(vectors[0]) == DEFAULT_VECTOR_SIZE

    @pytest.mark.asyncio
    async def test_empty_list(self):
        emb = HashEmbedder()
        vectors = await emb.embed([])
        assert vectors == []


class TestOpenAIEmbedder:
    @pytest.mark.asyncio
    async def test_fallback_produces_vectors(self):
        """OpenAI embedder without key falls back to hash embedder."""
        emb = OpenAIEmbedder(api_key="")
        vectors = await emb.embed(["test"])
        assert len(vectors) == 1
        assert len(vectors[0]) == emb.vector_size

    def test_vector_size(self):
        emb = OpenAIEmbedder()
        assert emb.vector_size == 1536


class TestFactory:
    def test_no_key_returns_hash(self):
        emb = create_embedder("")
        assert isinstance(emb, HashEmbedder)

    def test_with_key_returns_openai(self):
        emb = create_embedder("sk-test")
        assert isinstance(emb, OpenAIEmbedder)
