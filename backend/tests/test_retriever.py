"""
Tests for the hybrid retriever.

Covers: vector search integration, symbol lookup (exact + partial),
call edge traversal, module summary retrieval, and context assembly.
"""

import json

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.indexing.embedder import HashEmbedder
from app.indexing.indexer import COLLECTION_NAME
from app.indexing.vector_store import InMemoryVectorStore, VectorRecord
from app.reasoning.models import Question, QuestionType
from app.reasoning.retriever import retrieve_context
from app.storage.models import Base, Edge, Repo, RepoSnapshot, SnapshotStatus, Summary, Symbol

TEST_DB_URL = "sqlite+aiosqlite://"
_engine = create_async_engine(TEST_DB_URL, echo=False)
_sm = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def _seed(db: AsyncSession):
    db.add(Repo(id="r1", name="test", url="https://example.com", default_branch="main"))
    db.add(RepoSnapshot(id="s1", repo_id="r1", commit_sha="abc", status=SnapshotStatus.completed))
    await db.flush()

    # Symbols
    s1 = Symbol(
        snapshot_id="s1",
        kind="class",
        name="UserService",
        fq_name="MyApp.UserService",
        file_path="UserService.cs",
        start_line=5,
        end_line=40,
        namespace="MyApp",
        modifiers="public",
    )
    db.add(s1)
    await db.flush()

    s2 = Symbol(
        snapshot_id="s1",
        kind="method",
        name="GetById",
        fq_name="MyApp.UserService.GetById",
        file_path="UserService.cs",
        start_line=10,
        end_line=18,
        namespace="MyApp",
        parent_fq_name="MyApp.UserService",
        modifiers="public",
        signature="public User GetById(int id)",
    )
    db.add(s2)
    await db.flush()

    s3 = Symbol(
        snapshot_id="s1",
        kind="method",
        name="Delete",
        fq_name="MyApp.UserService.Delete",
        file_path="UserService.cs",
        start_line=20,
        end_line=28,
        namespace="MyApp",
        parent_fq_name="MyApp.UserService",
        modifiers="public",
    )
    db.add(s3)
    await db.flush()

    # Edges
    db.add(
        Edge(
            snapshot_id="s1",
            source_fq_name="MyApp.UserService.Delete",
            target_fq_name="MyApp.UserService.GetById",
            edge_type="calls",
            file_path="UserService.cs",
            line=22,
        )
    )
    db.add(
        Edge(
            snapshot_id="s1",
            source_fq_name="MyApp.UserService",
            target_fq_name="MyApp.UserService.GetById",
            edge_type="contains",
            file_path="UserService.cs",
            line=10,
        )
    )

    # Module summary
    db.add(
        Summary(
            snapshot_id="s1",
            scope_type="module",
            scope_id="MyApp",
            summary_json=json.dumps(
                {
                    "name": "MyApp",
                    "purpose": "Main module",
                    "citations": [{"file_path": "UserService.cs"}],
                }
            ),
        )
    )
    await db.commit()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with _sm() as db:
        await _seed(db)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


class TestRetrieveContext:
    @pytest.mark.asyncio
    async def test_retrieves_symbol_exact_match(self):
        q = Question(
            text="What does UserService do?",
            snapshot_id="s1",
            question_type=QuestionType.COMPONENT,
            target_symbol="MyApp.UserService",
        )
        async with _sm() as db:
            ctx = await retrieve_context(db, q)
        assert len(ctx.symbols) == 1
        assert ctx.symbols[0]["fq_name"] == "MyApp.UserService"

    @pytest.mark.asyncio
    async def test_retrieves_symbol_partial_match(self):
        q = Question(
            text="What does GetById do?",
            snapshot_id="s1",
            question_type=QuestionType.COMPONENT,
            target_symbol="GetById",
        )
        async with _sm() as db:
            ctx = await retrieve_context(db, q)
        assert len(ctx.symbols) >= 1
        assert any(s["name"] == "GetById" for s in ctx.symbols)

    @pytest.mark.asyncio
    async def test_retrieves_call_edges_outbound(self):
        q = Question(
            text="What does Delete call?",
            snapshot_id="s1",
            question_type=QuestionType.FLOW,
            target_symbol="Delete",
        )
        async with _sm() as db:
            ctx = await retrieve_context(db, q)
        assert len(ctx.edges) >= 1
        assert any(e["target_fq_name"] == "MyApp.UserService.GetById" for e in ctx.edges)

    @pytest.mark.asyncio
    async def test_retrieves_call_edges_inbound(self):
        q = Question(
            text="What depends on GetById?",
            snapshot_id="s1",
            question_type=QuestionType.IMPACT,
            target_symbol="GetById",
        )
        async with _sm() as db:
            ctx = await retrieve_context(db, q)
        assert len(ctx.edges) >= 1

    @pytest.mark.asyncio
    async def test_architecture_includes_module_summaries(self):
        q = Question(
            text="How is the system structured?",
            snapshot_id="s1",
            question_type=QuestionType.ARCHITECTURE,
            target_symbol="",
        )
        async with _sm() as db:
            ctx = await retrieve_context(db, q)
        assert any(s.get("scope_type") == "module_summary" for s in ctx.summaries)

    @pytest.mark.asyncio
    async def test_graph_neighborhood_populated(self):
        q = Question(
            text="Flow of Delete",
            snapshot_id="s1",
            question_type=QuestionType.FLOW,
            target_symbol="Delete",
        )
        async with _sm() as db:
            ctx = await retrieve_context(db, q)
        assert len(ctx.graph_neighborhood) >= 1

    @pytest.mark.asyncio
    async def test_no_target_no_edges(self):
        q = Question(
            text="General question",
            snapshot_id="s1",
            question_type=QuestionType.GENERAL,
            target_symbol="",
        )
        async with _sm() as db:
            ctx = await retrieve_context(db, q)
        assert ctx.edges == []
        assert ctx.graph_neighborhood == []

    @pytest.mark.asyncio
    async def test_vector_search_with_store(self):
        embedder = HashEmbedder(size=32)
        store = InMemoryVectorStore()
        await store.ensure_collection(COLLECTION_NAME, 32)

        # Add a record
        vec = (await embedder.embed(["UserService class"]))[0]
        record = VectorRecord(
            id="v1",
            snapshot_id="s1",
            scope_type="symbol_summary",
            text="UserService class",
            refs=[{"file_path": "UserService.cs"}],
        )
        await store.upsert(COLLECTION_NAME, [record], [vec])

        q = Question(
            text="UserService",
            snapshot_id="s1",
            question_type=QuestionType.COMPONENT,
            target_symbol="MyApp.UserService",
        )
        async with _sm() as db:
            ctx = await retrieve_context(db, q, embedder=embedder, vector_store=store)
        assert len(ctx.summaries) >= 1
