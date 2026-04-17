"""
Tests for the repos API endpoints (Phase 1).

Covers: repo creation, ingestion trigger, snapshot status,
error handling, and data validation.
"""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.storage.database import get_db
from tests.conftest import create_tables, drop_tables, override_get_db

app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await create_tables()
    yield
    await drop_tables()


@pytest_asyncio.fixture
async def client():
    with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_create_repo(client: AsyncClient):
    resp = await client.post(
        "/repos",
        json={"name": "test-repo", "url": "https://github.com/example/test"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "test-repo"
    assert "id" in data
    assert data["default_branch"] == "main"
    assert data["last_indexed_at"] is None


@pytest.mark.asyncio
async def test_create_repo_custom_branch(client: AsyncClient):
    resp = await client.post(
        "/repos",
        json={
            "name": "test",
            "url": "https://github.com/example/test",
            "default_branch": "develop",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["default_branch"] == "develop"


@pytest.mark.asyncio
async def test_create_repo_invalid_url(client: AsyncClient):
    resp = await client.post("/repos", json={"name": "test", "url": "not-a-url"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_repo_missing_fields(client: AsyncClient):
    resp = await client.post("/repos", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ingest_returns_pending(client: AsyncClient):
    resp = await client.post(
        "/repos",
        json={"name": "demo", "url": "https://github.com/example/demo"},
    )
    repo_id = resp.json()["id"]

    resp = await client.post(f"/repos/{repo_id}/ingest", json={"commit_sha": "abc123"})
    assert resp.status_code == 202
    assert resp.json()["status"] == "pending"
    assert "snapshot_id" in resp.json()


@pytest.mark.asyncio
async def test_ingest_without_sha(client: AsyncClient):
    resp = await client.post(
        "/repos",
        json={"name": "demo", "url": "https://github.com/example/demo"},
    )
    repo_id = resp.json()["id"]

    resp = await client.post(f"/repos/{repo_id}/ingest")
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_status_shows_snapshots(client: AsyncClient):
    resp = await client.post(
        "/repos",
        json={"name": "demo", "url": "https://github.com/example/demo"},
    )
    repo_id = resp.json()["id"]

    await client.post(f"/repos/{repo_id}/ingest", json={"commit_sha": "abc123"})
    await client.post(f"/repos/{repo_id}/ingest", json={"commit_sha": "def456"})

    resp = await client.get(f"/repos/{repo_id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["repo_id"] == repo_id
    assert len(data["snapshots"]) == 2


@pytest.mark.asyncio
async def test_repo_not_found_ingest(client: AsyncClient):
    resp = await client.post("/repos/nonexistent/ingest")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_repo_not_found_status(client: AsyncClient):
    resp = await client.get("/repos/nonexistent/status")
    assert resp.status_code == 404
