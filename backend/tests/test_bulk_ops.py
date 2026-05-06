"""
Tests for Phase 7 (Phase 10.7): Bulk Operations.

Tests 4 endpoints:
- POST /repos/{id}/snapshots/bulk-delete
- POST /repos/{id}/snapshots/bulk-tag
- DELETE /repos/{id}/snapshots/older-than/{days}
- POST /repos/bulk-delete
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
        db.add(Repo(id="r2", name="other", url="https://example.com/2"))
        now = datetime.now(UTC)
        # Recent snapshots
        db.add(RepoSnapshot(
            id="s1", repo_id="r1", commit_sha="aaa",
            status=SnapshotStatus.completed, file_count=5,
            created_at=now - timedelta(hours=1),
        ))
        db.add(RepoSnapshot(
            id="s2", repo_id="r1", commit_sha="bbb",
            status=SnapshotStatus.completed, file_count=8,
            created_at=now - timedelta(hours=2),
        ))
        # Old snapshot
        db.add(RepoSnapshot(
            id="s_old", repo_id="r1", commit_sha="old",
            status=SnapshotStatus.completed, file_count=3,
            created_at=now - timedelta(days=100),
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


class TestBulkDeleteSnapshots:

    @pytest.mark.asyncio
    async def test_delete_multiple(self, client):
        resp = await client.post("/repos/r1/snapshots/bulk-delete", json={
            "snapshot_ids": ["s1", "s2"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] == 2
        assert data["failed"] == []

    @pytest.mark.asyncio
    async def test_delete_with_invalid(self, client):
        resp = await client.post("/repos/r1/snapshots/bulk-delete", json={
            "snapshot_ids": ["s1", "nonexistent"],
        })
        data = resp.json()
        assert data["deleted"] == 1
        assert "nonexistent" in data["failed"]

    @pytest.mark.asyncio
    async def test_delete_wrong_repo(self, client):
        resp = await client.post("/repos/r2/snapshots/bulk-delete", json={
            "snapshot_ids": ["s1"],  # belongs to r1
        })
        data = resp.json()
        assert data["deleted"] == 0
        assert "s1" in data["failed"]

    @pytest.mark.asyncio
    async def test_delete_max_100(self, client):
        ids = [f"x{i}" for i in range(101)]
        resp = await client.post("/repos/r1/snapshots/bulk-delete", json={
            "snapshot_ids": ids,
        })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_repo_not_found(self, client):
        resp = await client.post("/repos/bad/snapshots/bulk-delete", json={
            "snapshot_ids": ["s1"],
        })
        assert resp.status_code == 404


class TestBulkTagSnapshots:

    @pytest.mark.asyncio
    async def test_tag_multiple(self, client):
        resp = await client.post("/repos/r1/snapshots/bulk-tag", json={
            "snapshot_ids": ["s1", "s2"], "tag": "release",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["tagged"] == 2
        assert data["skipped"] == 0

    @pytest.mark.asyncio
    async def test_tag_skips_duplicates(self, client):
        await client.post("/repos/r1/snapshots/bulk-tag", json={
            "snapshot_ids": ["s1"], "tag": "prod",
        })
        resp = await client.post("/repos/r1/snapshots/bulk-tag", json={
            "snapshot_ids": ["s1", "s2"], "tag": "prod",
        })
        data = resp.json()
        assert data["tagged"] == 1  # only s2
        assert data["skipped"] == 1  # s1 already tagged

    @pytest.mark.asyncio
    async def test_tag_invalid_snapshot(self, client):
        resp = await client.post("/repos/r1/snapshots/bulk-tag", json={
            "snapshot_ids": ["bad"], "tag": "x",
        })
        data = resp.json()
        assert data["tagged"] == 0
        assert data["skipped"] == 1

    @pytest.mark.asyncio
    async def test_tag_empty_rejected(self, client):
        resp = await client.post("/repos/r1/snapshots/bulk-tag", json={
            "snapshot_ids": ["s1"], "tag": "",
        })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_tag_normalized(self, client):
        await client.post("/repos/r1/snapshots/bulk-tag", json={
            "snapshot_ids": ["s1"], "tag": " RELEASE ",
        })
        # Verify via tags endpoint
        resp = await client.get("/repos/r1/snapshots/s1/tags")
        tags = [t["tag"] for t in resp.json()]
        assert "release" in tags


class TestDeleteOlderThan:

    @pytest.mark.asyncio
    async def test_delete_old(self, client):
        resp = await client.delete("/repos/r1/snapshots/older-than/30")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted_count"] == 1  # s_old
        assert data["remaining_count"] == 2  # s1, s2

    @pytest.mark.asyncio
    async def test_delete_nothing(self, client):
        resp = await client.delete("/repos/r1/snapshots/older-than/365")
        data = resp.json()
        assert data["deleted_count"] == 0
        assert data["remaining_count"] == 3

    @pytest.mark.asyncio
    async def test_repo_not_found(self, client):
        resp = await client.delete("/repos/bad/snapshots/older-than/30")
        assert resp.status_code == 404


class TestBulkDeleteRepos:

    @pytest.mark.asyncio
    async def test_delete_repos(self, client):
        resp = await client.post("/repos/bulk-delete", json={
            "repo_ids": ["r1", "r2"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] == 2

    @pytest.mark.asyncio
    async def test_delete_with_invalid(self, client):
        resp = await client.post("/repos/bulk-delete", json={
            "repo_ids": ["r1", "nonexistent"],
        })
        data = resp.json()
        assert data["deleted"] == 1
        assert "nonexistent" in data["failed"]

    @pytest.mark.asyncio
    async def test_delete_max_50(self, client):
        ids = [f"x{i}" for i in range(51)]
        resp = await client.post("/repos/bulk-delete", json={
            "repo_ids": ids,
        })
        assert resp.status_code == 400
