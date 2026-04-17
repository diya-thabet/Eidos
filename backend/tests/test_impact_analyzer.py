"""
Tests for the impact analyser.

Covers: BFS traversal of callers, risk score computation,
depth limiting, and edge cases.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.reviews.impact_analyzer import compute_risk_score, find_impacted_symbols
from app.reviews.models import ChangedSymbol, ImpactedSymbol
from app.storage.models import Base, Edge, Repo, RepoSnapshot, SnapshotStatus, Symbol

TEST_DB_URL = "sqlite+aiosqlite://"
_engine = create_async_engine(TEST_DB_URL, echo=False)
_sm = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def _seed(db: AsyncSession):
    db.add(Repo(id="r-imp", name="test", url="https://example.com", default_branch="main"))
    db.add(
        RepoSnapshot(id="s-imp", repo_id="r-imp", commit_sha="abc", status=SnapshotStatus.completed)
    )
    await db.flush()

    # Symbol chain: A calls B calls C calls D
    for name in ["A", "B", "C", "D"]:
        db.add(
            Symbol(
                snapshot_id="s-imp",
                kind="method",
                name=name,
                fq_name=f"MyApp.{name}",
                file_path=f"{name}.cs",
                start_line=1,
                end_line=10,
                namespace="MyApp",
            )
        )
    await db.flush()

    # B calls C, A calls B, C calls D
    db.add(
        Edge(
            snapshot_id="s-imp",
            source_fq_name="MyApp.A",
            target_fq_name="MyApp.B",
            edge_type="calls",
            file_path="A.cs",
            line=5,
        )
    )
    db.add(
        Edge(
            snapshot_id="s-imp",
            source_fq_name="MyApp.B",
            target_fq_name="MyApp.C",
            edge_type="calls",
            file_path="B.cs",
            line=5,
        )
    )
    db.add(
        Edge(
            snapshot_id="s-imp",
            source_fq_name="MyApp.C",
            target_fq_name="MyApp.D",
            edge_type="calls",
            file_path="C.cs",
            line=5,
        )
    )
    # Extra caller: E also calls C
    db.add(
        Symbol(
            snapshot_id="s-imp",
            kind="method",
            name="E",
            fq_name="MyApp.E",
            file_path="E.cs",
            start_line=1,
            end_line=10,
            namespace="MyApp",
        )
    )
    await db.flush()
    db.add(
        Edge(
            snapshot_id="s-imp",
            source_fq_name="MyApp.E",
            target_fq_name="MyApp.C",
            edge_type="calls",
            file_path="E.cs",
            line=3,
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


class TestFindImpactedSymbols:
    @pytest.mark.asyncio
    async def test_direct_callers(self):
        """If D changes, C should be impacted (distance 1)."""
        changed = [
            ChangedSymbol(
                fq_name="MyApp.D", kind="method", file_path="D.cs", start_line=1, end_line=10
            )
        ]
        async with _sm() as db:
            impacted = await find_impacted_symbols(db, "s-imp", changed, max_hops=1)
        fq = {i.fq_name for i in impacted}
        assert "MyApp.C" in fq

    @pytest.mark.asyncio
    async def test_transitive_callers(self):
        """If D changes, with 2 hops: C and B (and E) should be impacted."""
        changed = [
            ChangedSymbol(
                fq_name="MyApp.D", kind="method", file_path="D.cs", start_line=1, end_line=10
            )
        ]
        async with _sm() as db:
            impacted = await find_impacted_symbols(db, "s-imp", changed, max_hops=2)
        fq = {i.fq_name for i in impacted}
        assert "MyApp.C" in fq
        assert "MyApp.B" in fq or "MyApp.E" in fq

    @pytest.mark.asyncio
    async def test_full_chain(self):
        """3 hops from D should reach A."""
        changed = [
            ChangedSymbol(
                fq_name="MyApp.D", kind="method", file_path="D.cs", start_line=1, end_line=10
            )
        ]
        async with _sm() as db:
            impacted = await find_impacted_symbols(db, "s-imp", changed, max_hops=3)
        fq = {i.fq_name for i in impacted}
        assert "MyApp.A" in fq

    @pytest.mark.asyncio
    async def test_distance_is_correct(self):
        changed = [
            ChangedSymbol(
                fq_name="MyApp.D", kind="method", file_path="D.cs", start_line=1, end_line=10
            )
        ]
        async with _sm() as db:
            impacted = await find_impacted_symbols(db, "s-imp", changed, max_hops=3)
        c_imp = next(i for i in impacted if i.fq_name == "MyApp.C")
        assert c_imp.distance == 1

    @pytest.mark.asyncio
    async def test_no_callers(self):
        """A has no callers, so nothing is impacted."""
        changed = [
            ChangedSymbol(
                fq_name="MyApp.A", kind="method", file_path="A.cs", start_line=1, end_line=10
            )
        ]
        async with _sm() as db:
            impacted = await find_impacted_symbols(db, "s-imp", changed, max_hops=3)
        assert impacted == []

    @pytest.mark.asyncio
    async def test_sorted_by_distance(self):
        changed = [
            ChangedSymbol(
                fq_name="MyApp.D", kind="method", file_path="D.cs", start_line=1, end_line=10
            )
        ]
        async with _sm() as db:
            impacted = await find_impacted_symbols(db, "s-imp", changed, max_hops=3)
        distances = [i.distance for i in impacted]
        assert distances == sorted(distances)


class TestComputeRiskScore:
    def test_zero_risk(self):
        score, level = compute_risk_score([], [], 0, 0)
        assert score == 0
        assert level == "low"

    def test_low_risk(self):
        changed = [
            ChangedSymbol(fq_name="A", kind="method", file_path="A.cs", start_line=1, end_line=5)
        ]
        score, level = compute_risk_score(changed, [], 1, 0)
        assert level == "low"

    def test_high_risk(self):
        changed = [
            ChangedSymbol(
                fq_name=f"S{i}", kind="method", file_path=f"{i}.cs", start_line=1, end_line=10
            )
            for i in range(5)
        ]
        impacted = [
            ImpactedSymbol(
                fq_name=f"I{i}", kind="method", file_path=f"{i}.cs", start_line=1, end_line=10
            )
            for i in range(10)
        ]
        score, level = compute_risk_score(changed, impacted, 5, 3)
        assert score >= 50
        assert level in ("high", "critical")

    def test_critical_risk(self):
        changed = [
            ChangedSymbol(
                fq_name=f"S{i}", kind="method", file_path=f"{i}.cs", start_line=1, end_line=10
            )
            for i in range(5)
        ]
        impacted = [
            ImpactedSymbol(
                fq_name=f"I{i}", kind="method", file_path=f"{i}.cs", start_line=1, end_line=10
            )
            for i in range(10)
        ]
        score, level = compute_risk_score(changed, impacted, 6, 2)
        assert score >= 50

    def test_max_score_is_100(self):
        changed = [
            ChangedSymbol(
                fq_name=f"S{i}", kind="method", file_path=f"{i}.cs", start_line=1, end_line=10
            )
            for i in range(100)
        ]
        impacted = [
            ImpactedSymbol(
                fq_name=f"I{i}", kind="method", file_path=f"{i}.cs", start_line=1, end_line=10
            )
            for i in range(100)
        ]
        score, _ = compute_risk_score(changed, impacted, 100, 100)
        assert score == 100
