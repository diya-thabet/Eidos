"""
Tests for the evaluations API endpoints.

Covers: run evaluation, list evaluations, snapshot not found,
response structure.
"""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.storage.database import get_db
from app.storage.models import (
    GeneratedDoc,
    Repo,
    RepoSnapshot,
    SnapshotStatus,
    Symbol,
)
from tests.conftest import (
    create_tables,
    drop_tables,
    override_get_db,
    test_sessionmaker,
)

app.dependency_overrides[get_db] = override_get_db


async def _seed() -> None:
    async with test_sessionmaker() as db:
        db.add(
            Repo(
                id="r-eapi",
                name="test",
                url="https://example.com",
                default_branch="main",
            )
        )
        db.add(
            RepoSnapshot(
                id="s-eapi",
                repo_id="r-eapi",
                commit_sha="abc",
                status=SnapshotStatus.completed,
            )
        )
        await db.flush()
        db.add(
            Symbol(
                snapshot_id="s-eapi",
                kind="class",
                name="Svc",
                fq_name="MyApp.Svc",
                file_path="Svc.cs",
                start_line=1,
                end_line=20,
                namespace="MyApp",
            )
        )
        db.add(
            GeneratedDoc(
                snapshot_id="s-eapi",
                doc_type="readme",
                title="README",
                markdown="# README\n`MyApp.Svc`",
                scope_id="",
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


class TestEvaluateEndpoint:
    @pytest.mark.asyncio
    async def test_evaluate_returns_200(self, client):
        resp = await client.post("/repos/r-eapi/snapshots/s-eapi/evaluate")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_response_structure(self, client):
        resp = await client.post("/repos/r-eapi/snapshots/s-eapi/evaluate")
        data = resp.json()
        assert "snapshot_id" in data
        assert "overall_score" in data
        assert "overall_severity" in data
        assert "checks" in data
        assert "summary" in data
        assert isinstance(data["checks"], list)

    @pytest.mark.asyncio
    async def test_checks_have_fields(self, client):
        resp = await client.post("/repos/r-eapi/snapshots/s-eapi/evaluate")
        checks = resp.json()["checks"]
        assert len(checks) > 0
        for c in checks:
            assert "category" in c
            assert "name" in c
            assert "passed" in c
            assert "severity" in c
            assert "score" in c
            assert "message" in c

    @pytest.mark.asyncio
    async def test_snapshot_not_found(self, client):
        resp = await client.post("/repos/r-eapi/snapshots/bad/evaluate")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_score_range(self, client):
        resp = await client.post("/repos/r-eapi/snapshots/s-eapi/evaluate")
        score = resp.json()["overall_score"]
        assert 0.0 <= score <= 1.0


class TestListEvaluations:
    @pytest.mark.asyncio
    async def test_empty_list(self, client):
        resp = await client.get("/repos/r-eapi/snapshots/s-eapi/evaluations")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_after_evaluate(self, client):
        await client.post("/repos/r-eapi/snapshots/s-eapi/evaluate")
        resp = await client.get("/repos/r-eapi/snapshots/s-eapi/evaluations")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["snapshot_id"] == "s-eapi"

    @pytest.mark.asyncio
    async def test_snapshot_not_found(self, client):
        resp = await client.get("/repos/r-eapi/snapshots/bad/evaluations")
        assert resp.status_code == 404
