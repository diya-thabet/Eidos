"""
Tests for the documentation orchestrator.

Covers: full pipeline (fetch + generate + persist), single doc generation,
LLM enrichment (mocked), empty data handling.
"""

import json
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.docgen.models import DocType
from app.docgen.orchestrator import generate_all_docs, generate_single_doc
from app.reasoning.llm_client import StubLLMClient
from app.storage.models import (
    Base,
    Edge,
    GeneratedDoc,
    Repo,
    RepoSnapshot,
    SnapshotStatus,
    Summary,
    Symbol,
)

TEST_DB_URL = "sqlite+aiosqlite://"
_engine = create_async_engine(TEST_DB_URL, echo=False)
_sm = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def _seed(db: AsyncSession):
    db.add(
        Repo(
            id="r-doc",
            name="test",
            url="https://example.com",
            default_branch="main",
        )
    )
    db.add(
        RepoSnapshot(
            id="s-doc",
            repo_id="r-doc",
            commit_sha="abc",
            status=SnapshotStatus.completed,
        )
    )
    await db.flush()

    db.add(
        Symbol(
            snapshot_id="s-doc",
            kind="class",
            name="Foo",
            fq_name="MyApp.Foo",
            file_path="Foo.cs",
            start_line=1,
            end_line=40,
            namespace="MyApp",
            modifiers="public",
            signature="public class Foo",
        )
    )
    db.add(
        Symbol(
            snapshot_id="s-doc",
            kind="method",
            name="DoWork",
            fq_name="MyApp.Foo.DoWork",
            file_path="Foo.cs",
            start_line=10,
            end_line=25,
            namespace="MyApp",
            parent_fq_name="MyApp.Foo",
            modifiers="public",
            signature="public void DoWork()",
        )
    )
    db.add(
        Symbol(
            snapshot_id="s-doc",
            kind="class",
            name="FooController",
            fq_name="MyApp.Controllers.FooController",
            file_path="FooController.cs",
            start_line=1,
            end_line=20,
            namespace="MyApp.Controllers",
            modifiers="public",
        )
    )
    db.add(
        Symbol(
            snapshot_id="s-doc",
            kind="method",
            name="Get",
            fq_name="MyApp.Controllers.FooController.Get",
            file_path="FooController.cs",
            start_line=5,
            end_line=12,
            namespace="MyApp.Controllers",
            parent_fq_name="MyApp.Controllers.FooController",
            modifiers="public",
        )
    )
    await db.flush()

    db.add(
        Edge(
            snapshot_id="s-doc",
            source_fq_name="MyApp.Controllers.FooController.Get",
            target_fq_name="MyApp.Foo.DoWork",
            edge_type="calls",
            file_path="FooController.cs",
            line=8,
        )
    )

    db.add(
        Summary(
            snapshot_id="s-doc",
            scope_type="module",
            scope_id="MyApp",
            summary_json=json.dumps({"purpose": "Core domain."}),
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


class TestGenerateAllDocs:
    @pytest.mark.asyncio
    async def test_generates_multiple_docs(self):
        async with _sm() as db:
            results = await generate_all_docs(db, "s-doc")
        # README + Architecture + 2 modules + flow(s) + Runbook
        assert len(results) >= 4

    @pytest.mark.asyncio
    async def test_docs_have_markdown(self):
        async with _sm() as db:
            results = await generate_all_docs(db, "s-doc")
        for r in results:
            assert "markdown" in r
            assert len(r["markdown"]) > 0

    @pytest.mark.asyncio
    async def test_docs_persisted(self):
        async with _sm() as db:
            await generate_all_docs(db, "s-doc")

        async with _sm() as db:
            from sqlalchemy import select

            result = await db.execute(
                select(GeneratedDoc).where(GeneratedDoc.snapshot_id == "s-doc")
            )
            docs = result.scalars().all()
            assert len(docs) >= 4

    @pytest.mark.asyncio
    async def test_readme_included(self):
        async with _sm() as db:
            results = await generate_all_docs(db, "s-doc")
        types = [r["doc_type"] for r in results]
        assert "readme" in types

    @pytest.mark.asyncio
    async def test_architecture_included(self):
        async with _sm() as db:
            results = await generate_all_docs(db, "s-doc")
        types = [r["doc_type"] for r in results]
        assert "architecture" in types

    @pytest.mark.asyncio
    async def test_module_docs_included(self):
        async with _sm() as db:
            results = await generate_all_docs(db, "s-doc")
        types = [r["doc_type"] for r in results]
        assert "module" in types

    @pytest.mark.asyncio
    async def test_runbook_included(self):
        async with _sm() as db:
            results = await generate_all_docs(db, "s-doc")
        types = [r["doc_type"] for r in results]
        assert "runbook" in types

    @pytest.mark.asyncio
    async def test_with_stub_llm(self):
        stub = StubLLMClient()
        async with _sm() as db:
            results = await generate_all_docs(db, "s-doc", llm=stub)
        assert len(results) >= 4
        # Stub should not produce narrative
        for r in results:
            assert r.get("llm_narrative", "") == ""

    @pytest.mark.asyncio
    async def test_with_mock_llm(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = "LLM narrative text."
        mock_llm.__class__ = type("RealLLM", (), {})

        async with _sm() as db:
            results = await generate_all_docs(db, "s-doc", llm=mock_llm)
        assert any(r.get("llm_narrative") for r in results)


class TestGenerateSingleDoc:
    @pytest.mark.asyncio
    async def test_readme(self):
        async with _sm() as db:
            result = await generate_single_doc(db, "s-doc", DocType.README)
        assert result["doc_type"] == "readme"
        assert "# README" in result["markdown"]

    @pytest.mark.asyncio
    async def test_architecture(self):
        async with _sm() as db:
            result = await generate_single_doc(db, "s-doc", DocType.ARCHITECTURE)
        assert result["doc_type"] == "architecture"

    @pytest.mark.asyncio
    async def test_module(self):
        async with _sm() as db:
            result = await generate_single_doc(db, "s-doc", DocType.MODULE, scope_id="MyApp")
        assert result["doc_type"] == "module"
        assert "MyApp" in result["markdown"]

    @pytest.mark.asyncio
    async def test_module_not_found(self):
        async with _sm() as db:
            result = await generate_single_doc(db, "s-doc", DocType.MODULE, scope_id="Nonexistent")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_flow(self):
        async with _sm() as db:
            result = await generate_single_doc(
                db,
                "s-doc",
                DocType.FLOW,
                scope_id="MyApp.Controllers.FooController.Get",
            )
        assert result["doc_type"] == "flow"
        assert "DoWork" in result["markdown"]

    @pytest.mark.asyncio
    async def test_runbook(self):
        async with _sm() as db:
            result = await generate_single_doc(db, "s-doc", DocType.RUNBOOK)
        assert result["doc_type"] == "runbook"


class TestEmptySnapshot:
    @pytest.mark.asyncio
    async def test_empty_snapshot_generates_docs(self):
        """A snapshot with no symbols should still produce docs."""
        async with _sm() as db:
            # Create empty snapshot
            db.add(
                RepoSnapshot(
                    id="s-empty",
                    repo_id="r-doc",
                    commit_sha="000",
                    status=SnapshotStatus.completed,
                )
            )
            await db.commit()
            results = await generate_all_docs(db, "s-empty")
        # At least README + Architecture + Runbook
        assert len(results) >= 3
        for r in results:
            assert len(r["markdown"]) > 0
