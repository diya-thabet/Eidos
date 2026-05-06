"""
Tests for Phase 8 (Phase 10.8): Health Score & History.

Tests the scoring algorithm and 2 API endpoints.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.analysis.health_score import compute_health_score
from app.main import app
from app.storage.database import get_db
from app.storage.models import (
    CoverageReport,
    Repo,
    RepoSnapshot,
    SnapshotStatus,
    Symbol,
)
from tests.conftest import create_tables, drop_tables, override_get_db

app.dependency_overrides[get_db] = override_get_db


# =======================================================================
# Unit tests: scoring algorithm
# =======================================================================


class TestComputeHealthScore:

    def test_perfect_score(self):
        metrics = {
            "avg_cyclomatic_complexity": 0,
            "max_cyclomatic_complexity": 0,
            "long_function_count": 0,
            "total_methods": 10,
            "error_count": 0,
            "warning_count": 0,
            "total_findings": 0,
            "clone_group_count": 0,
            "dead_function_count": 0,
            "undocumented_public_count": 0,
            "total_public_count": 10,
            "naming_violations": 0,
            "security_findings": 0,
            "dependency_issues": 0,
            "has_tests": True,
            "coverage_percent": 100.0,
        }
        score = compute_health_score(metrics)
        assert score.overall == 100.0
        assert score.grade == "A"

    def test_complexity_penalty(self):
        metrics = {
            "avg_cyclomatic_complexity": 15,
            "max_cyclomatic_complexity": 40,
            "long_function_count": 5,
            "total_methods": 10,
        }
        score = compute_health_score(metrics)
        cat = next(c for c in score.categories if c.category == "complexity")
        assert cat.score < 50

    def test_error_penalty(self):
        metrics = {"error_count": 20}
        score = compute_health_score(metrics)
        cat = next(c for c in score.categories if c.category == "design")
        assert cat.score == 0  # 20 * 5 = 100 penalty -> 0

    def test_grade_a(self):
        metrics = {"has_tests": True, "coverage_percent": 95}
        score = compute_health_score(metrics)
        assert score.overall >= 90
        assert score.grade == "A"

    def test_grade_f(self):
        metrics = {
            "avg_cyclomatic_complexity": 30,
            "max_cyclomatic_complexity": 80,
            "long_function_count": 50,
            "total_methods": 50,
            "error_count": 50,
            "clone_group_count": 20,
            "dead_function_count": 30,
            "security_findings": 10,
            "dependency_issues": 20,
        }
        score = compute_health_score(metrics)
        assert score.grade == "F"
        assert score.overall < 60

    def test_nine_categories(self):
        score = compute_health_score({})
        assert len(score.categories) == 9

    def test_weights_sum_100(self):
        score = compute_health_score({})
        total_weight = sum(c.weight for c in score.categories)
        assert total_weight == 100

    def test_coverage_helps_testing(self):
        no_tests = compute_health_score({"has_tests": False, "coverage_percent": 0})
        with_tests = compute_health_score({"has_tests": True, "coverage_percent": 80})
        cat_no = next(c for c in no_tests.categories if c.category == "testing")
        cat_yes = next(c for c in with_tests.categories if c.category == "testing")
        assert cat_yes.score > cat_no.score

    def test_empty_metrics(self):
        score = compute_health_score({})
        assert 0 <= score.overall <= 100
        assert score.grade in ("A", "B", "C", "D", "F")

    def test_security_heavily_penalized(self):
        metrics = {"security_findings": 5}
        score = compute_health_score(metrics)
        cat = next(c for c in score.categories if c.category == "security")
        assert cat.score <= 25  # 5 * 15 = 75 penalty


# =======================================================================
# API tests
# =======================================================================


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await drop_tables()
    await create_tables()
    async for db in override_get_db():
        db.add(Repo(id="r1", name="demo", url="https://example.com"))
        db.add(RepoSnapshot(
            id="s1", repo_id="r1", commit_sha="abc",
            status=SnapshotStatus.completed, file_count=3,
        ))
        db.add(RepoSnapshot(
            id="s2", repo_id="r1", commit_sha="def",
            status=SnapshotStatus.completed, file_count=5,
        ))
        # Some symbols
        db.add(Symbol(
            snapshot_id="s1", name="func_a", kind="method",
            fq_name="mod.func_a", file_path="main.py",
            start_line=1, end_line=10, cyclomatic_complexity=5,
        ))
        db.add(Symbol(
            snapshot_id="s1", name="func_b", kind="method",
            fq_name="mod.func_b", file_path="main.py",
            start_line=15, end_line=60, cyclomatic_complexity=12,
        ))
        db.add(CoverageReport(
            snapshot_id="s1", overall_percent=75.0,
            branch_percent=60.0, covered_lines=100,
            missing_lines=33, num_statements=133,
        ))
        await db.commit()
    yield
    await drop_tables()


@pytest_asyncio.fixture
async def client():
    with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as ac:
            yield ac


class TestGetHealthScore:

    @pytest.mark.asyncio
    async def test_compute_score(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/health-score")
        assert resp.status_code == 200
        data = resp.json()
        assert "overall" in data
        assert "grade" in data
        assert "categories" in data
        assert len(data["categories"]) == 9
        assert 0 <= data["overall"] <= 100

    @pytest.mark.asyncio
    async def test_persisted_on_second_call(self, client):
        await client.get("/repos/r1/snapshots/s1/health-score")
        # Second call should return persisted
        resp = await client.get("/repos/r1/snapshots/s1/health-score")
        assert resp.status_code == 200
        assert resp.json()["overall"] > 0

    @pytest.mark.asyncio
    async def test_recompute(self, client):
        await client.get("/repos/r1/snapshots/s1/health-score")
        resp = await client.get(
            "/repos/r1/snapshots/s1/health-score?recompute=true",
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_grade_present(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/health-score")
        assert resp.json()["grade"] in ("A", "B", "C", "D", "F")

    @pytest.mark.asyncio
    async def test_categories_have_fields(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/health-score")
        cat = resp.json()["categories"][0]
        for field in ["category", "score", "weight", "weighted_score", "details"]:
            assert field in cat

    @pytest.mark.asyncio
    async def test_404_unknown_snapshot(self, client):
        resp = await client.get("/repos/r1/snapshots/bad/health-score")
        assert resp.status_code == 404


class TestHealthHistory:

    @pytest.mark.asyncio
    async def test_empty_history(self, client):
        resp = await client.get("/repos/r1/health-history")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_history_after_compute(self, client):
        await client.get("/repos/r1/snapshots/s1/health-score")
        resp = await client.get("/repos/r1/health-history")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["snapshot_id"] == "s1"

    @pytest.mark.asyncio
    async def test_history_multiple(self, client):
        await client.get("/repos/r1/snapshots/s1/health-score")
        await client.get("/repos/r1/snapshots/s2/health-score")
        resp = await client.get("/repos/r1/health-history")
        assert len(resp.json()) == 2

    @pytest.mark.asyncio
    async def test_history_fields(self, client):
        await client.get("/repos/r1/snapshots/s1/health-score")
        item = (await client.get("/repos/r1/health-history")).json()[0]
        for field in ["snapshot_id", "overall", "grade", "total_findings", "computed_at"]:
            assert field in item

    @pytest.mark.asyncio
    async def test_history_limit(self, client):
        await client.get("/repos/r1/snapshots/s1/health-score")
        await client.get("/repos/r1/snapshots/s2/health-score")
        resp = await client.get("/repos/r1/health-history?limit=1")
        assert len(resp.json()) == 1
