"""
Tests for the review orchestrator.

Covers: end-to-end review pipeline with DB symbols/edges,
symbol mapping, heuristic findings, impact analysis,
risk scoring, LLM summary (mocked), and edge cases.
"""

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.reasoning.llm_client import StubLLMClient
from app.reviews.models import FindingCategory
from app.reviews.reviewer import review_diff
from app.storage.models import Base, Edge, Repo, RepoSnapshot, SnapshotStatus, Symbol

TEST_DB_URL = "sqlite+aiosqlite://"
_engine = create_async_engine(TEST_DB_URL, echo=False)
_sm = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

REVIEW_DIFF = """\
diff --git a/Services/UserService.cs b/Services/UserService.cs
--- a/Services/UserService.cs
+++ b/Services/UserService.cs
@@ -10,7 +10,7 @@ public class UserService
     public User GetById(int id)
     {
-        if (id <= 0) throw new ArgumentNullException(nameof(id));
+        // validation removed for performance
         return _repo.Find(id);
     }
"""

SIDE_EFFECT_DIFF = """\
diff --git a/Services/OrderService.cs b/Services/OrderService.cs
--- a/Services/OrderService.cs
+++ b/Services/OrderService.cs
@@ -15,3 +15,5 @@ public class OrderService
     public void Process(int orderId)
     {
+        await _db.SaveChangesAsync();
+        await _notifier.SendAsync(orderId);
     }
"""


async def _seed(db: AsyncSession):
    db.add(Repo(id="r-rv", name="test", url="https://example.com", default_branch="main"))
    db.add(
        RepoSnapshot(id="s-rv", repo_id="r-rv", commit_sha="abc", status=SnapshotStatus.completed)
    )
    await db.flush()

    # UserService class and methods
    db.add(
        Symbol(
            snapshot_id="s-rv",
            kind="class",
            name="UserService",
            fq_name="MyApp.UserService",
            file_path="Services/UserService.cs",
            start_line=1,
            end_line=30,
            namespace="MyApp",
        )
    )
    db.add(
        Symbol(
            snapshot_id="s-rv",
            kind="method",
            name="GetById",
            fq_name="MyApp.UserService.GetById",
            file_path="Services/UserService.cs",
            start_line=10,
            end_line=16,
            namespace="MyApp",
            parent_fq_name="MyApp.UserService",
        )
    )
    await db.flush()

    # Callers of GetById
    db.add(
        Symbol(
            snapshot_id="s-rv",
            kind="method",
            name="Delete",
            fq_name="MyApp.UserService.Delete",
            file_path="Services/UserService.cs",
            start_line=20,
            end_line=25,
            namespace="MyApp",
        )
    )
    db.add(
        Symbol(
            snapshot_id="s-rv",
            kind="method",
            name="HandleRequest",
            fq_name="MyApp.Controller.HandleRequest",
            file_path="Controllers/UserController.cs",
            start_line=5,
            end_line=15,
            namespace="MyApp",
        )
    )
    await db.flush()

    db.add(
        Edge(
            snapshot_id="s-rv",
            source_fq_name="MyApp.UserService.Delete",
            target_fq_name="MyApp.UserService.GetById",
            edge_type="calls",
            file_path="Services/UserService.cs",
            line=22,
        )
    )
    db.add(
        Edge(
            snapshot_id="s-rv",
            source_fq_name="MyApp.Controller.HandleRequest",
            target_fq_name="MyApp.UserService.GetById",
            edge_type="calls",
            file_path="Controllers/UserController.cs",
            line=10,
        )
    )

    # OrderService
    db.add(
        Symbol(
            snapshot_id="s-rv",
            kind="method",
            name="Process",
            fq_name="MyApp.OrderService.Process",
            file_path="Services/OrderService.cs",
            start_line=15,
            end_line=20,
            namespace="MyApp",
        )
    )
    await db.flush()
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


class TestReviewDiff:
    @pytest.mark.asyncio
    async def test_basic_review(self):
        async with _sm() as db:
            report = await review_diff(db, "s-rv", REVIEW_DIFF)
        assert report.snapshot_id == "s-rv"
        assert len(report.files_changed) == 1
        assert "Services/UserService.cs" in report.files_changed

    @pytest.mark.asyncio
    async def test_changed_symbols_detected(self):
        async with _sm() as db:
            report = await review_diff(db, "s-rv", REVIEW_DIFF)
        fq = {cs.fq_name for cs in report.changed_symbols}
        assert "MyApp.UserService.GetById" in fq

    @pytest.mark.asyncio
    async def test_heuristic_findings(self):
        async with _sm() as db:
            report = await review_diff(db, "s-rv", REVIEW_DIFF)
        assert len(report.findings) >= 1
        categories = {f.category for f in report.findings}
        assert (
            FindingCategory.REMOVED_VALIDATION in categories
            or FindingCategory.REMOVED_NULL_CHECK in categories
        )

    @pytest.mark.asyncio
    async def test_impact_analysis(self):
        async with _sm() as db:
            report = await review_diff(db, "s-rv", REVIEW_DIFF)
        impacted_fq = {imp.fq_name for imp in report.impacted_symbols}
        # GetById has 2 callers: Delete and HandleRequest
        assert (
            "MyApp.UserService.Delete" in impacted_fq
            or "MyApp.Controller.HandleRequest" in impacted_fq
        )

    @pytest.mark.asyncio
    async def test_risk_score(self):
        async with _sm() as db:
            report = await review_diff(db, "s-rv", REVIEW_DIFF)
        assert report.risk_score >= 0
        assert report.risk_level in ("low", "medium", "high", "critical")

    @pytest.mark.asyncio
    async def test_diff_summary(self):
        async with _sm() as db:
            report = await review_diff(db, "s-rv", REVIEW_DIFF)
        assert "1 file(s) changed" in report.diff_summary

    @pytest.mark.asyncio
    async def test_side_effect_findings(self):
        async with _sm() as db:
            report = await review_diff(db, "s-rv", SIDE_EFFECT_DIFF)
        categories = {f.category for f in report.findings}
        assert FindingCategory.NEW_SIDE_EFFECT in categories

    @pytest.mark.asyncio
    async def test_empty_diff(self):
        async with _sm() as db:
            report = await review_diff(db, "s-rv", "")
        assert report.files_changed == []
        assert report.findings == []

    @pytest.mark.asyncio
    async def test_with_stub_llm(self):
        stub = StubLLMClient()
        async with _sm() as db:
            report = await review_diff(db, "s-rv", REVIEW_DIFF, llm=stub)
        assert report.llm_summary == ""  # Stub doesn't generate

    @pytest.mark.asyncio
    async def test_with_mock_llm(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = "This PR removes a critical validation."
        mock_llm.__class__ = type("RealLLM", (), {})

        async with _sm() as db:
            report = await review_diff(db, "s-rv", REVIEW_DIFF, llm=mock_llm)
        assert "critical validation" in report.llm_summary.lower()

    @pytest.mark.asyncio
    async def test_llm_failure_graceful(self):
        mock_llm = AsyncMock()
        mock_llm.chat.side_effect = Exception("timeout")
        mock_llm.__class__ = type("RealLLM", (), {})

        async with _sm() as db:
            report = await review_diff(db, "s-rv", REVIEW_DIFF, llm=mock_llm)
        assert report.llm_summary == ""  # Failed gracefully


class TestMultiFileDiff:
    @pytest.mark.asyncio
    async def test_review_multi_file(self):
        multi = REVIEW_DIFF + "\n" + SIDE_EFFECT_DIFF
        async with _sm() as db:
            report = await review_diff(db, "s-rv", multi)
        assert len(report.files_changed) == 2
        assert len(report.findings) >= 2
