"""
Tests for the analysis API endpoints (Phase 2).

Covers: symbol listing/filtering, edge listing, graph neighborhood,
analysis overview, and error handling.
"""

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models import Edge, Repo, RepoSnapshot, Symbol, SnapshotStatus
from app.storage.database import get_db
from app.main import app
from tests.conftest import override_get_db, create_tables, drop_tables, test_sessionmaker

app.dependency_overrides[get_db] = override_get_db


async def _seed_data() -> None:
    """Seed a repo, snapshot, symbols, and edges for testing."""
    async with test_sessionmaker() as db:
        repo = Repo(id="repo-001", name="test", url="https://example.com/test", default_branch="main")
        db.add(repo)

        snap = RepoSnapshot(
            id="snap-001", repo_id="repo-001", commit_sha="abc123", status=SnapshotStatus.completed
        )
        db.add(snap)
        await db.flush()

        cls = Symbol(
            snapshot_id="snap-001", kind="class", name="UserService",
            fq_name="MyApp.UserService", file_path="UserService.cs",
            start_line=5, end_line=30, namespace="MyApp", modifiers="public",
        )
        db.add(cls)
        await db.flush()

        method1 = Symbol(
            snapshot_id="snap-001", kind="method", name="GetById",
            fq_name="MyApp.UserService.GetById", file_path="UserService.cs",
            start_line=10, end_line=15, namespace="MyApp",
            parent_fq_name="MyApp.UserService", modifiers="public",
            return_type="User", signature="public User GetById(int id)",
        )
        db.add(method1)
        await db.flush()

        method2 = Symbol(
            snapshot_id="snap-001", kind="method", name="Delete",
            fq_name="MyApp.UserService.Delete", file_path="UserService.cs",
            start_line=17, end_line=22, namespace="MyApp",
            parent_fq_name="MyApp.UserService", modifiers="public",
        )
        db.add(method2)
        await db.flush()

        iface = Symbol(
            snapshot_id="snap-001", kind="interface", name="IUserService",
            fq_name="MyApp.IUserService", file_path="IUserService.cs",
            start_line=1, end_line=5, namespace="MyApp", modifiers="public",
        )
        db.add(iface)
        await db.flush()

        # Edges
        db.add(Edge(
            snapshot_id="snap-001", source_symbol_id=cls.id, target_symbol_id=method1.id,
            source_fq_name="MyApp.UserService", target_fq_name="MyApp.UserService.GetById",
            edge_type="contains", file_path="UserService.cs", line=10,
        ))
        db.add(Edge(
            snapshot_id="snap-001", source_symbol_id=cls.id, target_symbol_id=method2.id,
            source_fq_name="MyApp.UserService", target_fq_name="MyApp.UserService.Delete",
            edge_type="contains", file_path="UserService.cs", line=17,
        ))
        db.add(Edge(
            snapshot_id="snap-001", source_symbol_id=method2.id, target_symbol_id=method1.id,
            source_fq_name="MyApp.UserService.Delete", target_fq_name="MyApp.UserService.GetById",
            edge_type="calls", file_path="UserService.cs", line=19,
        ))
        db.add(Edge(
            snapshot_id="snap-001", source_symbol_id=cls.id, target_symbol_id=None,
            source_fq_name="MyApp.UserService", target_fq_name="MyApp.IUserService",
            edge_type="implements", file_path="UserService.cs", line=5,
        ))

        await db.commit()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await create_tables()
    await _seed_data()
    yield
    await drop_tables()


@pytest_asyncio.fixture
async def client():
    with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


class TestListSymbols:
    @pytest.mark.asyncio
    async def test_list_all_symbols(self, client):
        resp = await client.get("/repos/repo-001/snapshots/snap-001/symbols")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 4

    @pytest.mark.asyncio
    async def test_filter_by_kind(self, client):
        resp = await client.get("/repos/repo-001/snapshots/snap-001/symbols?kind=method")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert all(s["kind"] == "method" for s in data)

    @pytest.mark.asyncio
    async def test_filter_by_file(self, client):
        resp = await client.get("/repos/repo-001/snapshots/snap-001/symbols?file_path=IUserService.cs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "IUserService"

    @pytest.mark.asyncio
    async def test_pagination(self, client):
        resp = await client.get("/repos/repo-001/snapshots/snap-001/symbols?limit=2&offset=0")
        assert resp.status_code == 200
        page1 = resp.json()
        assert len(page1) == 2

        resp2 = await client.get("/repos/repo-001/snapshots/snap-001/symbols?limit=2&offset=2")
        assert resp2.status_code == 200
        page2 = resp2.json()
        assert len(page2) == 2

        # Pages should not overlap
        ids1 = {s["id"] for s in page1}
        ids2 = {s["id"] for s in page2}
        assert ids1.isdisjoint(ids2)

    @pytest.mark.asyncio
    async def test_snapshot_not_found(self, client):
        resp = await client.get("/repos/repo-001/snapshots/nonexistent/symbols")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_repo_not_found(self, client):
        resp = await client.get("/repos/nonexistent/snapshots/snap-001/symbols")
        assert resp.status_code == 404


class TestGetSymbol:
    @pytest.mark.asyncio
    async def test_get_symbol_by_fq_name(self, client):
        resp = await client.get("/repos/repo-001/snapshots/snap-001/symbols/MyApp.UserService")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "UserService"
        assert data["kind"] == "class"
        assert data["fq_name"] == "MyApp.UserService"

    @pytest.mark.asyncio
    async def test_get_method_symbol(self, client):
        resp = await client.get("/repos/repo-001/snapshots/snap-001/symbols/MyApp.UserService.GetById")
        assert resp.status_code == 200
        data = resp.json()
        assert data["return_type"] == "User"
        assert "GetById" in data["signature"]

    @pytest.mark.asyncio
    async def test_symbol_not_found(self, client):
        resp = await client.get("/repos/repo-001/snapshots/snap-001/symbols/Nonexistent.Symbol")
        assert resp.status_code == 404


class TestListEdges:
    @pytest.mark.asyncio
    async def test_list_all_edges(self, client):
        resp = await client.get("/repos/repo-001/snapshots/snap-001/edges")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 4

    @pytest.mark.asyncio
    async def test_filter_by_edge_type(self, client):
        resp = await client.get("/repos/repo-001/snapshots/snap-001/edges?edge_type=calls")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["source_fq_name"] == "MyApp.UserService.Delete"
        assert data[0]["target_fq_name"] == "MyApp.UserService.GetById"

    @pytest.mark.asyncio
    async def test_filter_by_source(self, client):
        resp = await client.get(
            "/repos/repo-001/snapshots/snap-001/edges?source=MyApp.UserService.Delete"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert all(e["source_fq_name"] == "MyApp.UserService.Delete" for e in data)

    @pytest.mark.asyncio
    async def test_filter_by_target(self, client):
        resp = await client.get(
            "/repos/repo-001/snapshots/snap-001/edges?target=MyApp.UserService.GetById"
        )
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


class TestGraphNeighborhood:
    @pytest.mark.asyncio
    async def test_get_class_neighborhood(self, client):
        resp = await client.get("/repos/repo-001/snapshots/snap-001/graph/MyApp.UserService")
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"]["name"] == "UserService"
        assert len(data["children"]) == 2  # GetById, Delete

    @pytest.mark.asyncio
    async def test_method_callers(self, client):
        resp = await client.get("/repos/repo-001/snapshots/snap-001/graph/MyApp.UserService.GetById")
        assert resp.status_code == 200
        data = resp.json()
        callers = [c["fq_name"] for c in data["callers"]]
        assert "MyApp.UserService.Delete" in callers

    @pytest.mark.asyncio
    async def test_method_callees(self, client):
        resp = await client.get("/repos/repo-001/snapshots/snap-001/graph/MyApp.UserService.Delete")
        assert resp.status_code == 200
        data = resp.json()
        callees = [c["fq_name"] for c in data["callees"]]
        assert "MyApp.UserService.GetById" in callees

    @pytest.mark.asyncio
    async def test_symbol_not_found(self, client):
        resp = await client.get("/repos/repo-001/snapshots/snap-001/graph/NonExistent")
        assert resp.status_code == 404


class TestAnalysisOverview:
    @pytest.mark.asyncio
    async def test_overview(self, client):
        resp = await client.get("/repos/repo-001/snapshots/snap-001/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["snapshot_id"] == "snap-001"
        assert data["total_symbols"] == 4
        assert data["total_edges"] == 4
        assert data["symbols_by_kind"]["class"] == 1
        assert data["symbols_by_kind"]["method"] == 2
        assert data["symbols_by_kind"]["interface"] == 1
