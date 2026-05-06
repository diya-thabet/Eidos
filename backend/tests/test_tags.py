"""
Tests for Phase 6 (Phase 10.6): Snapshot Tagging & Search.

Tests 5 API endpoints:
- POST /repos/{id}/snapshots/{sid}/tags
- DELETE /repos/{id}/snapshots/{sid}/tags/{tag}
- GET /repos/{id}/snapshots/{sid}/tags
- GET /repos/{id}/snapshots/by-tag/{tag}
- GET /repos/tags/stats
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.storage.database import get_db
from app.storage.models import Repo, RepoSnapshot, SnapshotStatus
from tests.conftest import create_tables, drop_tables, override_get_db

app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await drop_tables()
    await create_tables()
    async for db in override_get_db():
        db.add(Repo(id="r1", name="demo", url="https://example.com"))
        db.add(RepoSnapshot(
            id="s1", repo_id="r1", commit_sha="aaa",
            status=SnapshotStatus.completed, file_count=5,
        ))
        db.add(RepoSnapshot(
            id="s2", repo_id="r1", commit_sha="bbb",
            status=SnapshotStatus.completed, file_count=8,
        ))
        db.add(RepoSnapshot(
            id="s3", repo_id="r1", commit_sha="ccc",
            status=SnapshotStatus.completed, file_count=3,
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


class TestAddTag:

    @pytest.mark.asyncio
    async def test_add_tag(self, client):
        resp = await client.post(
            "/repos/r1/snapshots/s1/tags", json={"tag": "prod"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["tag"] == "prod"
        assert data["snapshot_id"] == "s1"

    @pytest.mark.asyncio
    async def test_tag_normalized_lowercase(self, client):
        resp = await client.post(
            "/repos/r1/snapshots/s1/tags", json={"tag": "RELEASE"},
        )
        assert resp.json()["tag"] == "release"

    @pytest.mark.asyncio
    async def test_tag_trimmed(self, client):
        resp = await client.post(
            "/repos/r1/snapshots/s1/tags", json={"tag": "  v1.0  "},
        )
        assert resp.json()["tag"] == "v1.0"

    @pytest.mark.asyncio
    async def test_duplicate_tag_409(self, client):
        await client.post("/repos/r1/snapshots/s1/tags", json={"tag": "prod"})
        resp = await client.post(
            "/repos/r1/snapshots/s1/tags", json={"tag": "prod"},
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_empty_tag_400(self, client):
        resp = await client.post(
            "/repos/r1/snapshots/s1/tags", json={"tag": ""},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_404_unknown_snapshot(self, client):
        resp = await client.post(
            "/repos/r1/snapshots/bad/tags", json={"tag": "x"},
        )
        assert resp.status_code == 404


class TestRemoveTag:

    @pytest.mark.asyncio
    async def test_remove(self, client):
        await client.post("/repos/r1/snapshots/s1/tags", json={"tag": "temp"})
        resp = await client.delete("/repos/r1/snapshots/s1/tags/temp")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_remove_404(self, client):
        resp = await client.delete("/repos/r1/snapshots/s1/tags/nonexistent")
        assert resp.status_code == 404


class TestListTags:

    @pytest.mark.asyncio
    async def test_list_empty(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/tags")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_with_tags(self, client):
        await client.post("/repos/r1/snapshots/s1/tags", json={"tag": "prod"})
        await client.post("/repos/r1/snapshots/s1/tags", json={"tag": "v1.0"})
        resp = await client.get("/repos/r1/snapshots/s1/tags")
        tags = resp.json()
        assert len(tags) == 2
        tag_names = [t["tag"] for t in tags]
        assert "prod" in tag_names
        assert "v1.0" in tag_names

    @pytest.mark.asyncio
    async def test_list_404_unknown_snapshot(self, client):
        resp = await client.get("/repos/r1/snapshots/bad/tags")
        assert resp.status_code == 404


class TestFindByTag:

    @pytest.mark.asyncio
    async def test_find_by_tag(self, client):
        await client.post("/repos/r1/snapshots/s1/tags", json={"tag": "prod"})
        await client.post("/repos/r1/snapshots/s2/tags", json={"tag": "prod"})
        resp = await client.get("/repos/r1/snapshots/by-tag/prod")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        ids = [s["id"] for s in data]
        assert "s1" in ids
        assert "s2" in ids

    @pytest.mark.asyncio
    async def test_find_by_tag_empty(self, client):
        resp = await client.get("/repos/r1/snapshots/by-tag/nonexistent")
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_find_includes_all_tags(self, client):
        await client.post("/repos/r1/snapshots/s1/tags", json={"tag": "prod"})
        await client.post("/repos/r1/snapshots/s1/tags", json={"tag": "v1.0"})
        resp = await client.get("/repos/r1/snapshots/by-tag/prod")
        snapshot = resp.json()[0]
        assert "prod" in snapshot["tags"]
        assert "v1.0" in snapshot["tags"]


class TestTagStats:

    @pytest.mark.asyncio
    async def test_stats_empty(self, client):
        resp = await client.get("/repos/tags/stats")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_stats_with_data(self, client):
        await client.post("/repos/r1/snapshots/s1/tags", json={"tag": "prod"})
        await client.post("/repos/r1/snapshots/s2/tags", json={"tag": "prod"})
        await client.post("/repos/r1/snapshots/s1/tags", json={"tag": "draft"})
        resp = await client.get("/repos/tags/stats")
        data = resp.json()
        assert len(data) == 2
        # Sorted by count desc
        assert data[0]["tag"] == "prod"
        assert data[0]["count"] == 2
        assert data[1]["tag"] == "draft"
        assert data[1]["count"] == 1

    @pytest.mark.asyncio
    async def test_stats_limit(self, client):
        await client.post("/repos/r1/snapshots/s1/tags", json={"tag": "a"})
        await client.post("/repos/r1/snapshots/s1/tags", json={"tag": "b"})
        await client.post("/repos/r1/snapshots/s1/tags", json={"tag": "c"})
        resp = await client.get("/repos/tags/stats?limit=2")
        assert len(resp.json()) == 2
