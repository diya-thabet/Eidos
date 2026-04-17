"""
Tests for the evaluation runner (orchestrator).

Covers: full snapshot evaluation, persistence, empty data,
doc evaluation, review evaluation.
"""

import json

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.guardrails.models import EvalSeverity
from app.guardrails.runner import evaluate_answer, run_snapshot_evaluation
from app.storage.models import (
    Base,
    Edge,
    GeneratedDoc,
    Repo,
    RepoSnapshot,
    Review,
    SnapshotStatus,
    Symbol,
)

TEST_DB_URL = "sqlite+aiosqlite://"
_engine = create_async_engine(TEST_DB_URL, echo=False)
_sm = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def _seed(db: AsyncSession) -> None:
    db.add(
        Repo(
            id="r-ev",
            name="test",
            url="https://example.com",
            default_branch="main",
        )
    )
    db.add(
        RepoSnapshot(
            id="s-ev",
            repo_id="r-ev",
            commit_sha="abc",
            status=SnapshotStatus.completed,
        )
    )
    await db.flush()

    db.add(
        Symbol(
            snapshot_id="s-ev",
            kind="class",
            name="Foo",
            fq_name="MyApp.Foo",
            file_path="Foo.cs",
            start_line=1,
            end_line=30,
            namespace="MyApp",
        )
    )
    db.add(
        Symbol(
            snapshot_id="s-ev",
            kind="method",
            name="DoWork",
            fq_name="MyApp.Foo.DoWork",
            file_path="Foo.cs",
            start_line=10,
            end_line=20,
            namespace="MyApp",
            parent_fq_name="MyApp.Foo",
        )
    )
    await db.flush()

    db.add(
        Edge(
            snapshot_id="s-ev",
            source_fq_name="MyApp.Foo.DoWork",
            target_fq_name="MyApp.Foo",
            edge_type="contains",
            file_path="Foo.cs",
        )
    )

    db.add(
        GeneratedDoc(
            snapshot_id="s-ev",
            doc_type="readme",
            title="README",
            markdown="# README\n`MyApp.Foo` is a class in `Foo.cs`.",
            scope_id="",
        )
    )

    db.add(
        Review(
            snapshot_id="s-ev",
            diff_summary="1 file changed",
            risk_score=30,
            risk_level="medium",
            report_json=json.dumps(
                {
                    "findings": [
                        {
                            "category": "test",
                            "severity": "medium",
                            "title": "test finding",
                            "file_path": "Foo.cs",
                            "symbol_fq_name": "MyApp.Foo",
                        }
                    ],
                    "changed_symbols": [
                        {"fq_name": "MyApp.Foo"},
                    ],
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


class TestRunSnapshotEvaluation:
    @pytest.mark.asyncio
    async def test_returns_report(self):
        async with _sm() as db:
            report = await run_snapshot_evaluation(db, "s-ev")
        assert report.snapshot_id == "s-ev"
        assert report.scope == "snapshot"
        assert len(report.checks) > 0

    @pytest.mark.asyncio
    async def test_has_overall_score(self):
        async with _sm() as db:
            report = await run_snapshot_evaluation(db, "s-ev")
        assert 0.0 <= report.overall_score <= 1.0

    @pytest.mark.asyncio
    async def test_symbol_coverage_check(self):
        async with _sm() as db:
            report = await run_snapshot_evaluation(db, "s-ev")
        names = [c.name for c in report.checks]
        assert "symbol_coverage" in names

    @pytest.mark.asyncio
    async def test_docs_evaluated(self):
        async with _sm() as db:
            report = await run_snapshot_evaluation(db, "s-ev")
        names = [c.name for c in report.checks]
        assert "docs_exist" in names
        assert "doc_types_present" in names

    @pytest.mark.asyncio
    async def test_reviews_evaluated(self):
        async with _sm() as db:
            report = await run_snapshot_evaluation(db, "s-ev")
        names = [c.name for c in report.checks]
        assert "review_precision" in names

    @pytest.mark.asyncio
    async def test_persisted_to_db(self):
        async with _sm() as db:
            await run_snapshot_evaluation(db, "s-ev")
        async with _sm() as db:
            from sqlalchemy import select

            from app.storage.models import Evaluation

            result = await db.execute(select(Evaluation).where(Evaluation.snapshot_id == "s-ev"))
            evals = result.scalars().all()
            assert len(evals) >= 1
            assert evals[0].overall_score > 0


class TestEmptySnapshot:
    @pytest.mark.asyncio
    async def test_empty_snapshot(self):
        async with _sm() as db:
            db.add(
                RepoSnapshot(
                    id="s-empty",
                    repo_id="r-ev",
                    commit_sha="000",
                    status=SnapshotStatus.completed,
                )
            )
            await db.commit()
            report = await run_snapshot_evaluation(db, "s-empty")
        assert report.overall_severity == EvalSeverity.FAIL
        names = [c.name for c in report.checks]
        assert "symbol_coverage" in names


class TestEvaluateAnswer:
    @pytest.mark.asyncio
    async def test_clean_answer(self):
        report = await evaluate_answer(
            known_symbols={"MyApp.Foo"},
            known_files={"Foo.cs"},
            known_edges={("MyApp.Foo.DoWork", "MyApp.Foo")},
            answer_text="`MyApp.Foo` is a class.",
            citations=[{"file_path": "Foo.cs"}],
            expected_symbols=["MyApp.Foo"],
        )
        assert report.overall_score > 0.5

    @pytest.mark.asyncio
    async def test_hallucinated_answer(self):
        report = await evaluate_answer(
            known_symbols={"MyApp.Foo"},
            known_files={"Foo.cs"},
            known_edges=set(),
            answer_text="`Ghost.Service` calls `Phantom.Repo`",
            citations=[],
            expected_symbols=["MyApp.Foo"],
        )
        assert report.overall_score < 0.7

    @pytest.mark.asyncio
    async def test_output_safety_checked(self):
        report = await evaluate_answer(
            known_symbols=set(),
            known_files=set(),
            known_edges=set(),
            answer_text="Contact admin@corp.com for help",
            citations=[],
            expected_symbols=[],
        )
        names = [c.name for c in report.checks]
        assert "output_safety" in names
