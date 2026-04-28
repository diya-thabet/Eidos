"""
Tests for ingestion progress reporting.

Covers:
- Progress fields in snapshot status response
- Progress fields in snapshot detail response
- Default values for new snapshots
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.storage.database import get_db
from app.storage.models import Repo, RepoSnapshot, SnapshotStatus
from tests.conftest import create_tables, drop_tables, override_get_db, test_sessionmaker

app.dependency_overrides[get_db] = override_get_db


async def _seed() -> None:
    async with test_sessionmaker() as db:
        repo = Repo(id="r-prog", name="progress-test", url="https://example.com/prog")
        db.add(repo)

        # Pending snapshot (no progress yet)
        db.add(RepoSnapshot(
            id="s-pending", repo_id="r-prog", status=SnapshotStatus.pending,
        ))

        # Running snapshot (mid-ingestion)
        snap_running = RepoSnapshot(
            id="s-running", repo_id="r-prog", status=SnapshotStatus.running,
        )
        snap_running.progress_percent = 50
        snap_running.progress_message = "Parsing ASTs..."
        db.add(snap_running)

        # Completed snapshot
        snap_done = RepoSnapshot(
            id="s-done", repo_id="r-prog", status=SnapshotStatus.completed,
            file_count=42,
        )
        snap_done.progress_percent = 100
        snap_done.progress_message = "Ingestion complete"
        db.add(snap_done)

        # Failed snapshot
        snap_fail = RepoSnapshot(
            id="s-fail", repo_id="r-prog", status=SnapshotStatus.failed,
            error_message="Git clone failed",
        )
        snap_fail.progress_percent = 5
        snap_fail.progress_message = "Failed: Git clone failed"
        db.add(snap_fail)

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


class TestProgressInStatus:
    @pytest.mark.asyncio
    async def test_pending_snapshot_has_zero_progress(self, client: AsyncClient):
        resp = await client.get("/repos/r-prog/status")
        assert resp.status_code == 200
        snaps = resp.json()["snapshots"]
        pending = next(s for s in snaps if s["id"] == "s-pending")
        assert pending["progress_percent"] == 0
        assert pending["progress_message"] == ""

    @pytest.mark.asyncio
    async def test_running_snapshot_shows_progress(self, client: AsyncClient):
        resp = await client.get("/repos/r-prog/status")
        snaps = resp.json()["snapshots"]
        running = next(s for s in snaps if s["id"] == "s-running")
        assert running["progress_percent"] == 50
        assert running["progress_message"] == "Parsing ASTs..."

    @pytest.mark.asyncio
    async def test_completed_snapshot_shows_100(self, client: AsyncClient):
        resp = await client.get("/repos/r-prog/status")
        snaps = resp.json()["snapshots"]
        done = next(s for s in snaps if s["id"] == "s-done")
        assert done["progress_percent"] == 100
        assert done["progress_message"] == "Ingestion complete"

    @pytest.mark.asyncio
    async def test_failed_snapshot_shows_failure_message(self, client: AsyncClient):
        resp = await client.get("/repos/r-prog/status")
        snaps = resp.json()["snapshots"]
        fail = next(s for s in snaps if s["id"] == "s-fail")
        assert fail["progress_percent"] == 5
        assert "Failed" in fail["progress_message"]

    @pytest.mark.asyncio
    async def test_all_snapshots_have_progress_fields(self, client: AsyncClient):
        resp = await client.get("/repos/r-prog/status")
        for snap in resp.json()["snapshots"]:
            assert "progress_percent" in snap
            assert "progress_message" in snap


class TestProgressInDetail:
    @pytest.mark.asyncio
    async def test_detail_includes_progress(self, client: AsyncClient):
        resp = await client.get("/repos/r-prog/snapshots/s-running")
        assert resp.status_code == 200
        data = resp.json()
        assert data["progress_percent"] == 50
        assert data["progress_message"] == "Parsing ASTs..."

    @pytest.mark.asyncio
    async def test_new_ingest_starts_with_zero(self, client: AsyncClient):
        resp = await client.post("/repos/r-prog/ingest")
        assert resp.status_code == 202
        snap_id = resp.json()["snapshot_id"]

        async with test_sessionmaker() as db:
            snap = await db.get(RepoSnapshot, snap_id)
            assert snap is not None
            assert snap.progress_percent == 0
            assert snap.progress_message == ""
