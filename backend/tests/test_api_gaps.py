"""
Tests for Phase 8: API Endpoint Gaps.

Tests the 6 new endpoints: list repos, list snapshots, delete snapshot,
list files, get callers, and symbol notes.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.storage.database import get_db
from app.storage.models import (
    Edge,
    File,
    Repo,
    RepoSnapshot,
    SnapshotStatus,
    Symbol,
)
from tests.conftest import create_tables, drop_tables, override_get_db

app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await drop_tables()
    await create_tables()
    async for db in override_get_db():
        db.add(Repo(id="r1", name="alpha", url="https://example.com/alpha"))
        db.add(Repo(id="r2", name="beta", url="https://example.com/beta"))
        db.add(RepoSnapshot(
            id="s1", repo_id="r1", commit_sha="aaa",
            status=SnapshotStatus.completed, file_count=3,
        ))
        db.add(RepoSnapshot(
            id="s2", repo_id="r1", commit_sha="bbb",
            status=SnapshotStatus.completed, file_count=1,
        ))
        db.add(File(
            snapshot_id="s1", path="main.py",
            language="python", hash="h1", size_bytes=100,
        ))
        db.add(File(
            snapshot_id="s1", path="utils.py",
            language="python", hash="h2", size_bytes=200,
        ))
        db.add(File(
            snapshot_id="s1", path="App.java",
            language="java", hash="h3", size_bytes=500,
        ))
        db.add(Symbol(
            snapshot_id="s1", name="main", kind="method",
            fq_name="app.main", file_path="main.py",
            start_line=1, end_line=10,
        ))
        db.add(Symbol(
            snapshot_id="s1", name="helper", kind="method",
            fq_name="app.helper", file_path="utils.py",
            start_line=1, end_line=5,
        ))
        db.add(Symbol(
            snapshot_id="s1", name="util", kind="method",
            fq_name="app.util", file_path="utils.py",
            start_line=10, end_line=20,
        ))
        db.add(Edge(
            snapshot_id="s1",
            source_fq_name="app.main",
            target_fq_name="app.helper",
            edge_type="calls",
            file_path="main.py",
        ))
        db.add(Edge(
            snapshot_id="s1",
            source_fq_name="app.util",
            target_fq_name="app.helper",
            edge_type="calls",
            file_path="utils.py",
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


# =======================================================================
# 8.1 List repos
# =======================================================================


class TestListRepos:

    @pytest.mark.asyncio
    async def test_list_repos(self, client):
        resp = await client.get("/repos")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_list_repos_fields(self, client):
        resp = await client.get("/repos")
        r = resp.json()[0]
        assert "id" in r
        assert "name" in r
        assert "url" in r
        assert "created_at" in r

    @pytest.mark.asyncio
    async def test_list_repos_empty(self, client):
        # Delete all repos first
        async for db in override_get_db():
            from sqlalchemy import delete
            await db.execute(delete(Repo))
            await db.commit()
        resp = await client.get("/repos")
        assert resp.status_code == 200
        assert resp.json() == []


# =======================================================================
# 8.2 List snapshots
# =======================================================================


class TestListSnapshots:

    @pytest.mark.asyncio
    async def test_list_snapshots(self, client):
        resp = await client.get("/repos/r1/snapshots")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_list_snapshots_fields(self, client):
        resp = await client.get("/repos/r1/snapshots")
        s = resp.json()[0]
        for field in ["id", "repo_id", "commit_sha", "status", "file_count"]:
            assert field in s

    @pytest.mark.asyncio
    async def test_list_snapshots_pagination(self, client):
        resp = await client.get("/repos/r1/snapshots?limit=1&offset=0")
        assert len(resp.json()) == 1
        resp2 = await client.get("/repos/r1/snapshots?limit=1&offset=1")
        assert len(resp2.json()) == 1
        assert resp.json()[0]["id"] != resp2.json()[0]["id"]

    @pytest.mark.asyncio
    async def test_list_snapshots_404(self, client):
        resp = await client.get("/repos/nonexistent/snapshots")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_snapshots_other_repo(self, client):
        resp = await client.get("/repos/r2/snapshots")
        assert resp.status_code == 200
        assert len(resp.json()) == 0


# =======================================================================
# 8.3 Delete snapshot
# =======================================================================


class TestDeleteSnapshot:

    @pytest.mark.asyncio
    async def test_delete_snapshot(self, client):
        resp = await client.delete("/repos/r1/snapshots/s2")
        assert resp.status_code == 204
        # Verify gone
        resp2 = await client.get("/repos/r1/snapshots")
        ids = [s["id"] for s in resp2.json()]
        assert "s2" not in ids

    @pytest.mark.asyncio
    async def test_delete_snapshot_404(self, client):
        resp = await client.delete("/repos/r1/snapshots/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_snapshot_wrong_repo(self, client):
        resp = await client.delete("/repos/r2/snapshots/s1")
        assert resp.status_code == 404


# =======================================================================
# 8.4 List files
# =======================================================================


class TestListFiles:

    @pytest.mark.asyncio
    async def test_list_files(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/files")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3

    @pytest.mark.asyncio
    async def test_list_files_fields(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/files")
        f = resp.json()[0]
        for field in ["id", "path", "language", "hash", "size_bytes"]:
            assert field in f

    @pytest.mark.asyncio
    async def test_list_files_filter_language(self, client):
        resp = await client.get(
            "/repos/r1/snapshots/s1/files?language=python"
        )
        data = resp.json()
        assert len(data) == 2
        assert all(f["language"] == "python" for f in data)

    @pytest.mark.asyncio
    async def test_list_files_filter_java(self, client):
        resp = await client.get(
            "/repos/r1/snapshots/s1/files?language=java"
        )
        data = resp.json()
        assert len(data) == 1
        assert data[0]["path"] == "App.java"

    @pytest.mark.asyncio
    async def test_list_files_sorted_by_path(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/files")
        paths = [f["path"] for f in resp.json()]
        assert paths == sorted(paths)

    @pytest.mark.asyncio
    async def test_list_files_404(self, client):
        resp = await client.get("/repos/r1/snapshots/bad/files")
        assert resp.status_code == 404


# =======================================================================
# 8.5 Get callers
# =======================================================================


class TestGetCallers:

    @pytest.mark.asyncio
    async def test_get_callers(self, client):
        resp = await client.get(
            "/repos/r1/snapshots/s1/symbols/app.helper/callers"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["target_fq_name"] == "app.helper"
        assert data["total"] == 2

    @pytest.mark.asyncio
    async def test_callers_names(self, client):
        resp = await client.get(
            "/repos/r1/snapshots/s1/symbols/app.helper/callers"
        )
        names = {c["fq_name"] for c in resp.json()["callers"]}
        assert names == {"app.main", "app.util"}

    @pytest.mark.asyncio
    async def test_callers_fields(self, client):
        resp = await client.get(
            "/repos/r1/snapshots/s1/symbols/app.helper/callers"
        )
        if resp.json()["callers"]:
            c = resp.json()["callers"][0]
            for field in ["fq_name", "name", "kind", "file_path", "start_line"]:
                assert field in c

    @pytest.mark.asyncio
    async def test_no_callers(self, client):
        resp = await client.get(
            "/repos/r1/snapshots/s1/symbols/app.main/callers"
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_callers_nonexistent_symbol(self, client):
        resp = await client.get(
            "/repos/r1/snapshots/s1/symbols/app.doesnotexist/callers"
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# =======================================================================
# 8.6 Symbol notes
# =======================================================================


class TestSymbolNotes:

    @pytest.mark.asyncio
    async def test_create_note(self, client):
        resp = await client.patch(
            "/repos/r1/snapshots/s1/symbols/app.main/notes",
            json={"note": "This is important", "author": "Alice"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["note"] == "This is important"
        assert data["author"] == "Alice"
        assert data["symbol_fq_name"] == "app.main"

    @pytest.mark.asyncio
    async def test_update_note(self, client):
        await client.patch(
            "/repos/r1/snapshots/s1/symbols/app.main/notes",
            json={"note": "v1", "author": "Alice"},
        )
        resp = await client.patch(
            "/repos/r1/snapshots/s1/symbols/app.main/notes",
            json={"note": "v2", "author": "Bob"},
        )
        assert resp.json()["note"] == "v2"
        assert resp.json()["author"] == "Bob"

    @pytest.mark.asyncio
    async def test_get_notes(self, client):
        await client.patch(
            "/repos/r1/snapshots/s1/symbols/app.main/notes",
            json={"note": "hello", "author": "Alice"},
        )
        resp = await client.get(
            "/repos/r1/snapshots/s1/symbols/app.main/notes"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["note"] == "hello"

    @pytest.mark.asyncio
    async def test_get_notes_empty(self, client):
        resp = await client.get(
            "/repos/r1/snapshots/s1/symbols/app.helper/notes"
        )
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_note_fields(self, client):
        await client.patch(
            "/repos/r1/snapshots/s1/symbols/app.main/notes",
            json={"note": "test"},
        )
        resp = await client.get(
            "/repos/r1/snapshots/s1/symbols/app.main/notes"
        )
        n = resp.json()[0]
        for field in [
            "id", "snapshot_id", "symbol_fq_name",
            "note", "author", "created_at", "updated_at",
        ]:
            assert field in n

    @pytest.mark.asyncio
    async def test_note_404_wrong_snapshot(self, client):
        resp = await client.patch(
            "/repos/r1/snapshots/bad/symbols/app.main/notes",
            json={"note": "test"},
        )
        assert resp.status_code == 404
