"""
Tests for the docgen API endpoints.

Covers: generate all docs, generate single doc, list docs,
get doc by id, filtering, error handling, persistence.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.storage.database import get_db
from app.storage.models import (
    Edge,
    Repo,
    RepoSnapshot,
    SnapshotStatus,
    Summary,
    Symbol,
)
from tests.conftest import (
    create_tables,
    drop_tables,
    override_get_db,
    test_sessionmaker,
)

app.dependency_overrides[get_db] = override_get_db


async def _seed():
    async with test_sessionmaker() as db:
        db.add(
            Repo(
                id="r-dg",
                name="test",
                url="https://example.com",
                default_branch="main",
            )
        )
        db.add(
            RepoSnapshot(
                id="s-dg",
                repo_id="r-dg",
                commit_sha="abc",
                status=SnapshotStatus.completed,
            )
        )
        await db.flush()

        db.add(
            Symbol(
                snapshot_id="s-dg",
                kind="class",
                name="Bar",
                fq_name="MyApp.Bar",
                file_path="Bar.cs",
                start_line=1,
                end_line=20,
                namespace="MyApp",
                modifiers="public",
            )
        )
        db.add(
            Symbol(
                snapshot_id="s-dg",
                kind="method",
                name="Run",
                fq_name="MyApp.Bar.Run",
                file_path="Bar.cs",
                start_line=5,
                end_line=15,
                namespace="MyApp",
                parent_fq_name="MyApp.Bar",
                modifiers="public",
            )
        )
        await db.flush()

        db.add(
            Edge(
                snapshot_id="s-dg",
                source_fq_name="MyApp.Bar.Run",
                target_fq_name="MyApp.Bar",
                edge_type="contains",
                file_path="Bar.cs",
                line=5,
            )
        )
        db.add(
            Summary(
                snapshot_id="s-dg",
                scope_type="module",
                scope_id="MyApp",
                summary_json=json.dumps({"purpose": "Main module."}),
            )
        )
        await db.commit()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
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


class TestGenerateDocsEndpoint:
    @pytest.mark.asyncio
    async def test_generate_all_returns_200(self, client):
        resp = await client.post("/repos/r-dg/snapshots/s-dg/docs")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_generate_all_response_structure(self, client):
        resp = await client.post("/repos/r-dg/snapshots/s-dg/docs")
        data = resp.json()
        assert "snapshot_id" in data
        assert "documents" in data
        assert "total" in data
        assert data["total"] >= 3

    @pytest.mark.asyncio
    async def test_generate_all_has_readme(self, client):
        resp = await client.post("/repos/r-dg/snapshots/s-dg/docs")
        types = [d["doc_type"] for d in resp.json()["documents"]]
        assert "readme" in types

    @pytest.mark.asyncio
    async def test_generate_single_readme(self, client):
        resp = await client.post(
            "/repos/r-dg/snapshots/s-dg/docs",
            json={"doc_type": "readme"},
        )
        data = resp.json()
        assert data["total"] == 1
        assert data["documents"][0]["doc_type"] == "readme"

    @pytest.mark.asyncio
    async def test_generate_module_doc(self, client):
        resp = await client.post(
            "/repos/r-dg/snapshots/s-dg/docs",
            json={"doc_type": "module", "scope_id": "MyApp"},
        )
        data = resp.json()
        assert data["total"] == 1
        assert "MyApp" in data["documents"][0]["markdown"]

    @pytest.mark.asyncio
    async def test_invalid_doc_type(self, client):
        resp = await client.post(
            "/repos/r-dg/snapshots/s-dg/docs",
            json={"doc_type": "invalid"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_module_not_found(self, client):
        resp = await client.post(
            "/repos/r-dg/snapshots/s-dg/docs",
            json={"doc_type": "module", "scope_id": "NoSuch"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_snapshot_not_found(self, client):
        resp = await client.post("/repos/r-dg/snapshots/bad/docs")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_docs_contain_markdown(self, client):
        resp = await client.post("/repos/r-dg/snapshots/s-dg/docs")
        for doc in resp.json()["documents"]:
            assert len(doc["markdown"]) > 0
            assert "#" in doc["markdown"]


class TestListDocsEndpoint:
    @pytest.mark.asyncio
    async def test_list_empty(self, client):
        resp = await client.get("/repos/r-dg/snapshots/s-dg/docs")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_after_generate(self, client):
        await client.post("/repos/r-dg/snapshots/s-dg/docs")
        resp = await client.get("/repos/r-dg/snapshots/s-dg/docs")
        assert resp.status_code == 200
        assert len(resp.json()) >= 3

    @pytest.mark.asyncio
    async def test_filter_by_type(self, client):
        await client.post("/repos/r-dg/snapshots/s-dg/docs")
        resp = await client.get("/repos/r-dg/snapshots/s-dg/docs?doc_type=readme")
        assert resp.status_code == 200
        assert all(d["doc_type"] == "readme" for d in resp.json())

    @pytest.mark.asyncio
    async def test_snapshot_not_found(self, client):
        resp = await client.get("/repos/r-dg/snapshots/bad/docs")
        assert resp.status_code == 404


class TestGetDocEndpoint:
    @pytest.mark.asyncio
    async def test_get_by_id(self, client):
        await client.post("/repos/r-dg/snapshots/s-dg/docs")
        listing = await client.get("/repos/r-dg/snapshots/s-dg/docs")
        doc_id = listing.json()[0]["id"]

        resp = await client.get(f"/repos/r-dg/snapshots/s-dg/docs/{doc_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == doc_id

    @pytest.mark.asyncio
    async def test_doc_not_found(self, client):
        resp = await client.get("/repos/r-dg/snapshots/s-dg/docs/999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_doc_has_full_markdown(self, client):
        await client.post("/repos/r-dg/snapshots/s-dg/docs")
        listing = await client.get("/repos/r-dg/snapshots/s-dg/docs")
        doc_id = listing.json()[0]["id"]

        resp = await client.get(f"/repos/r-dg/snapshots/s-dg/docs/{doc_id}")
        assert len(resp.json()["markdown"]) > 0
