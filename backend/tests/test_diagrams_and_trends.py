"""
Tests for Mermaid diagram generation and health score trend API.

Covers:
- Class diagram generation (symbols, edges, members, filtering)
- Module diagram generation (namespaces, cross-namespace deps)
- Health score trend (improving/degrading/stable/insufficient data)
- Edge cases: empty snapshots, unknown diagram types
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.storage.database import get_db
from app.storage.models import (
    Edge,
    Evaluation,
    Repo,
    RepoSnapshot,
    SnapshotStatus,
    Symbol,
)
from tests.conftest import create_tables, drop_tables, override_get_db, test_sessionmaker

app.dependency_overrides[get_db] = override_get_db


async def _seed() -> None:
    async with test_sessionmaker() as db:
        repo = Repo(id="r-diag", name="diagram-test", url="https://example.com/diag")
        db.add(repo)

        snap = RepoSnapshot(
            id="s-diag", repo_id="r-diag", commit_sha="aaa", status=SnapshotStatus.completed
        )
        db.add(snap)
        await db.flush()

        # Classes
        db.add(Symbol(
            snapshot_id="s-diag", kind="class", name="OrderService",
            fq_name="App.OrderService", file_path="Order.cs",
            start_line=1, end_line=50, namespace="App", modifiers="public",
        ))
        db.add(Symbol(
            snapshot_id="s-diag", kind="interface", name="IOrderService",
            fq_name="App.IOrderService", file_path="Order.cs",
            start_line=1, end_line=10, namespace="App", modifiers="public",
        ))
        db.add(Symbol(
            snapshot_id="s-diag", kind="class", name="UserRepo",
            fq_name="Data.UserRepo", file_path="User.cs",
            start_line=1, end_line=30, namespace="Data", modifiers="public",
        ))
        # Methods
        db.add(Symbol(
            snapshot_id="s-diag", kind="method", name="PlaceOrder",
            fq_name="App.OrderService.PlaceOrder", file_path="Order.cs",
            start_line=10, end_line=20, namespace="App",
            parent_fq_name="App.OrderService", modifiers="public",
            signature="PlaceOrder(Order o)", return_type="void",
        ))
        await db.flush()

        # Edges
        db.add(Edge(
            snapshot_id="s-diag", source_fq_name="App.OrderService",
            target_fq_name="App.IOrderService", edge_type="implements",
        ))
        db.add(Edge(
            snapshot_id="s-diag", source_fq_name="App.OrderService.PlaceOrder",
            target_fq_name="Data.UserRepo", edge_type="calls",
        ))

        # Second snapshot with evaluation for trend testing
        snap2 = RepoSnapshot(
            id="s-diag2", repo_id="r-diag", commit_sha="bbb", status=SnapshotStatus.completed
        )
        db.add(snap2)
        await db.flush()

        # Evaluations
        checks_good = [
            {"name": "c1", "passed": True, "score": 0.9, "category": "docs",
             "severity": "low", "message": "ok", "details": {}},
            {"name": "c2", "passed": True, "score": 0.8, "category": "quality",
             "severity": "low", "message": "ok", "details": {}},
        ]
        checks_bad = [
            {"name": "c1", "passed": False, "score": 0.3, "category": "docs",
             "severity": "high", "message": "fail", "details": {}},
            {"name": "c2", "passed": True, "score": 0.5, "category": "quality",
             "severity": "medium", "message": "ok", "details": {}},
        ]

        db.add(Evaluation(
            snapshot_id="s-diag", scope="snapshot", overall_score=0.5,
            overall_severity="medium", checks_json=json.dumps(checks_bad), summary="mediocre",
        ))
        db.add(Evaluation(
            snapshot_id="s-diag2", scope="snapshot", overall_score=0.85,
            overall_severity="low", checks_json=json.dumps(checks_good), summary="great",
        ))

        await db.commit()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await drop_tables()
    await create_tables()
    await _seed()
    yield
    await drop_tables()


@pytest_asyncio.fixture
async def client():
    with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


# ===================================================================
# Class Diagram
# ===================================================================


class TestClassDiagram:
    @pytest.mark.asyncio
    async def test_class_diagram_returns_mermaid(self, client: AsyncClient):
        resp = await client.get("/repos/r-diag/snapshots/s-diag/diagram?diagram_type=class")
        assert resp.status_code == 200
        data = resp.json()
        assert data["diagram_type"] == "class"
        assert "classDiagram" in data["mermaid"]
        assert data["node_count"] >= 1

    @pytest.mark.asyncio
    async def test_class_diagram_contains_classes(self, client: AsyncClient):
        resp = await client.get("/repos/r-diag/snapshots/s-diag/diagram?diagram_type=class")
        mermaid = resp.json()["mermaid"]
        assert "App_OrderService" in mermaid
        assert "App_IOrderService" in mermaid

    @pytest.mark.asyncio
    async def test_class_diagram_shows_interface_stereotype(self, client: AsyncClient):
        resp = await client.get("/repos/r-diag/snapshots/s-diag/diagram?diagram_type=class")
        assert "<<interface>>" in resp.json()["mermaid"]

    @pytest.mark.asyncio
    async def test_class_diagram_shows_implements_edge(self, client: AsyncClient):
        resp = await client.get("/repos/r-diag/snapshots/s-diag/diagram?diagram_type=class")
        mermaid = resp.json()["mermaid"]
        assert "<|.." in mermaid  # implements arrow

    @pytest.mark.asyncio
    async def test_class_diagram_shows_members(self, client: AsyncClient):
        resp = await client.get("/repos/r-diag/snapshots/s-diag/diagram?diagram_type=class")
        mermaid = resp.json()["mermaid"]
        assert "PlaceOrder" in mermaid

    @pytest.mark.asyncio
    async def test_class_diagram_filter_by_namespace(self, client: AsyncClient):
        resp = await client.get(
            "/repos/r-diag/snapshots/s-diag/diagram?diagram_type=class&namespace=Data"
        )
        data = resp.json()
        assert data["node_count"] == 1
        assert "Data_UserRepo" in data["mermaid"]
        assert "App_OrderService" not in data["mermaid"]

    @pytest.mark.asyncio
    async def test_class_diagram_filter_by_file(self, client: AsyncClient):
        resp = await client.get(
            "/repos/r-diag/snapshots/s-diag/diagram?diagram_type=class&file_path=Order.cs"
        )
        data = resp.json()
        assert "Data_UserRepo" not in data["mermaid"]

    @pytest.mark.asyncio
    async def test_class_diagram_max_nodes(self, client: AsyncClient):
        resp = await client.get(
            "/repos/r-diag/snapshots/s-diag/diagram?diagram_type=class&max_nodes=1"
        )
        assert resp.json()["node_count"] == 1


# ===================================================================
# Module Diagram
# ===================================================================


class TestModuleDiagram:
    @pytest.mark.asyncio
    async def test_module_diagram_returns_mermaid(self, client: AsyncClient):
        resp = await client.get("/repos/r-diag/snapshots/s-diag/diagram?diagram_type=module")
        assert resp.status_code == 200
        data = resp.json()
        assert data["diagram_type"] == "module"
        assert "graph LR" in data["mermaid"]

    @pytest.mark.asyncio
    async def test_module_diagram_contains_namespaces(self, client: AsyncClient):
        resp = await client.get("/repos/r-diag/snapshots/s-diag/diagram?diagram_type=module")
        mermaid = resp.json()["mermaid"]
        assert "App" in mermaid
        assert "Data" in mermaid

    @pytest.mark.asyncio
    async def test_module_diagram_shows_dependencies(self, client: AsyncClient):
        resp = await client.get("/repos/r-diag/snapshots/s-diag/diagram?diagram_type=module")
        mermaid = resp.json()["mermaid"]
        assert "-->" in mermaid  # dependency arrow

    @pytest.mark.asyncio
    async def test_module_diagram_filter_namespace(self, client: AsyncClient):
        resp = await client.get(
            "/repos/r-diag/snapshots/s-diag/diagram?diagram_type=module&namespace=App"
        )
        data = resp.json()
        assert data["node_count"] >= 1

    @pytest.mark.asyncio
    async def test_unknown_diagram_type(self, client: AsyncClient):
        resp = await client.get(
            "/repos/r-diag/snapshots/s-diag/diagram?diagram_type=unknown"
        )
        assert resp.status_code == 200
        assert resp.json()["node_count"] == 0

    @pytest.mark.asyncio
    async def test_diagram_response_structure(self, client: AsyncClient):
        resp = await client.get("/repos/r-diag/snapshots/s-diag/diagram")
        data = resp.json()
        assert "snapshot_id" in data
        assert "diagram_type" in data
        assert "mermaid" in data
        assert "node_count" in data
        assert "edge_count" in data


# ===================================================================
# Health Trend
# ===================================================================


class TestHealthTrend:
    @pytest.mark.asyncio
    async def test_trend_returns_data_points(self, client: AsyncClient):
        resp = await client.get("/repos/r-diag/health/trend")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data_points"]) == 2

    @pytest.mark.asyncio
    async def test_trend_shows_improving(self, client: AsyncClient):
        resp = await client.get("/repos/r-diag/health/trend")
        data = resp.json()
        assert data["trend"] == "improving"
        assert data["score_change"] is not None
        assert data["score_change"] > 0

    @pytest.mark.asyncio
    async def test_trend_latest_score(self, client: AsyncClient):
        resp = await client.get("/repos/r-diag/health/trend")
        data = resp.json()
        assert data["latest_score"] == 0.85

    @pytest.mark.asyncio
    async def test_trend_data_point_structure(self, client: AsyncClient):
        resp = await client.get("/repos/r-diag/health/trend")
        point = resp.json()["data_points"][0]
        assert "snapshot_id" in point
        assert "overall_score" in point
        assert "overall_severity" in point
        assert "check_count" in point
        assert "passed_count" in point
        assert "created_at" in point

    @pytest.mark.asyncio
    async def test_trend_insufficient_data(self, client: AsyncClient):
        """Repo with no evaluations should return insufficient_data."""
        async with test_sessionmaker() as db:
            db.add(Repo(id="r-empty", name="empty", url="https://example.com/empty"))
            await db.commit()

        resp = await client.get("/repos/r-empty/health/trend")
        assert resp.status_code == 200
        data = resp.json()
        assert data["trend"] == "insufficient_data"
        assert data["data_points"] == []

    @pytest.mark.asyncio
    async def test_trend_repo_not_found(self, client: AsyncClient):
        resp = await client.get("/repos/nonexistent/health/trend")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_trend_response_structure(self, client: AsyncClient):
        resp = await client.get("/repos/r-diag/health/trend")
        data = resp.json()
        assert "repo_id" in data
        assert "data_points" in data
        assert "trend" in data
        assert "latest_score" in data
        assert "score_change" in data

    @pytest.mark.asyncio
    async def test_trend_limit_param(self, client: AsyncClient):
        resp = await client.get("/repos/r-diag/health/trend?limit=1")
        assert resp.status_code == 200
        # Should only look at 1 most recent snapshot
        assert len(resp.json()["data_points"]) <= 1

    @pytest.mark.asyncio
    async def test_trend_passed_count(self, client: AsyncClient):
        resp = await client.get("/repos/r-diag/health/trend")
        points = resp.json()["data_points"]
        # Second snapshot has 2 passing checks
        last_point = points[-1]
        assert last_point["passed_count"] == 2
        assert last_point["check_count"] == 2
