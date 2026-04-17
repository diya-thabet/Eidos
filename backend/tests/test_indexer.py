"""
Tests for the indexing orchestrator (end-to-end).

Covers: full pipeline from graph to DB summaries + vector store,
summary persistence, vector record creation, and stats reporting.
"""

import json

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.analysis.csharp_parser import parse_file
from app.analysis.graph_builder import build_graph
from app.indexing.embedder import HashEmbedder
from app.indexing.indexer import run_indexing
from app.indexing.summarizer import StubSummariser
from app.indexing.vector_store import InMemoryVectorStore
from app.storage.models import Base, Summary

TEST_DB_URL = "sqlite+aiosqlite://"
_engine = create_async_engine(TEST_DB_URL, echo=False)
_sessionmaker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


SERVICE_CODE = b"""\
using System;

namespace TestApp.Services
{
    public class UserService
    {
        public User GetById(int id) { return null; }
        public void Delete(int id) { GetById(id); }
    }
}
"""

MODEL_CODE = b"""\
namespace TestApp.Models
{
    public class User
    {
        public int Id { get; set; }
        public string Name { get; set; }
    }
}
"""


def _build_graph():
    return build_graph(
        [
            parse_file(SERVICE_CODE, "Services/UserService.cs"),
            parse_file(MODEL_CODE, "Models/User.cs"),
        ]
    )


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


class TestRunIndexing:
    @pytest.mark.asyncio
    async def test_returns_stats(self):
        graph = _build_graph()
        vector_store = InMemoryVectorStore()

        async with _sessionmaker() as db:
            stats = await run_indexing(
                db,
                "snap-idx-01",
                graph,
                summariser=StubSummariser(),
                embedder=HashEmbedder(size=32),
                vector_store=vector_store,
            )
            await db.commit()

        assert stats["symbol_summaries"] > 0
        assert stats["module_summaries"] > 0
        assert stats["file_summaries"] > 0
        assert stats["vectors_stored"] > 0

    @pytest.mark.asyncio
    async def test_persists_summaries_to_db(self):
        graph = _build_graph()

        async with _sessionmaker() as db:
            await run_indexing(
                db,
                "snap-idx-02",
                graph,
                summariser=StubSummariser(),
                embedder=HashEmbedder(size=32),
                vector_store=InMemoryVectorStore(),
            )
            await db.commit()

            result = await db.execute(select(Summary).where(Summary.snapshot_id == "snap-idx-02"))
            summaries = result.scalars().all()
            assert len(summaries) > 0

    @pytest.mark.asyncio
    async def test_summary_scope_types(self):
        graph = _build_graph()

        async with _sessionmaker() as db:
            await run_indexing(
                db,
                "snap-idx-03",
                graph,
                summariser=StubSummariser(),
                embedder=HashEmbedder(size=32),
                vector_store=InMemoryVectorStore(),
            )
            await db.commit()

            result = await db.execute(select(Summary).where(Summary.snapshot_id == "snap-idx-03"))
            summaries = result.scalars().all()
            scope_types = {s.scope_type for s in summaries}
            assert "symbol" in scope_types
            assert "module" in scope_types
            assert "file" in scope_types

    @pytest.mark.asyncio
    async def test_summary_json_is_valid(self):
        graph = _build_graph()

        async with _sessionmaker() as db:
            await run_indexing(
                db,
                "snap-idx-04",
                graph,
                summariser=StubSummariser(),
                embedder=HashEmbedder(size=32),
                vector_store=InMemoryVectorStore(),
            )
            await db.commit()

            result = await db.execute(select(Summary).where(Summary.snapshot_id == "snap-idx-04"))
            summaries = result.scalars().all()
            for s in summaries:
                data = json.loads(s.summary_json)
                assert isinstance(data, dict)
                assert "purpose" in data

    @pytest.mark.asyncio
    async def test_symbol_summary_has_citations(self):
        graph = _build_graph()

        async with _sessionmaker() as db:
            await run_indexing(
                db,
                "snap-idx-05",
                graph,
                summariser=StubSummariser(),
                embedder=HashEmbedder(size=32),
                vector_store=InMemoryVectorStore(),
            )
            await db.commit()

            result = await db.execute(
                select(Summary).where(
                    Summary.snapshot_id == "snap-idx-05",
                    Summary.scope_type == "symbol",
                )
            )
            for s in result.scalars().all():
                data = json.loads(s.summary_json)
                assert len(data.get("citations", [])) >= 1

    @pytest.mark.asyncio
    async def test_vectors_stored_in_vector_store(self):
        graph = _build_graph()
        vector_store = InMemoryVectorStore()

        async with _sessionmaker() as db:
            stats = await run_indexing(
                db,
                "snap-idx-06",
                graph,
                summariser=StubSummariser(),
                embedder=HashEmbedder(size=32),
                vector_store=vector_store,
            )
            await db.commit()

        from app.indexing.indexer import COLLECTION_NAME

        assert vector_store.count(COLLECTION_NAME) == stats["vectors_stored"]

    @pytest.mark.asyncio
    async def test_vector_search_returns_results(self):
        graph = _build_graph()
        vector_store = InMemoryVectorStore()
        embedder = HashEmbedder(size=32)

        async with _sessionmaker() as db:
            await run_indexing(
                db,
                "snap-idx-07",
                graph,
                summariser=StubSummariser(),
                embedder=embedder,
                vector_store=vector_store,
            )
            await db.commit()

        from app.indexing.indexer import COLLECTION_NAME

        query_vec = (await embedder.embed(["UserService"]))[0]
        results = await vector_store.search(COLLECTION_NAME, query_vec, limit=5)
        assert len(results) > 0
        assert all(r.score is not None for r in results)

    @pytest.mark.asyncio
    async def test_empty_graph_produces_no_summaries(self):
        graph = build_graph([])

        async with _sessionmaker() as db:
            stats = await run_indexing(
                db,
                "snap-idx-08",
                graph,
                summariser=StubSummariser(),
                embedder=HashEmbedder(size=32),
                vector_store=InMemoryVectorStore(),
            )
            await db.commit()

        assert stats["symbol_summaries"] == 0
        assert stats["module_summaries"] == 0
        assert stats["file_summaries"] == 0
