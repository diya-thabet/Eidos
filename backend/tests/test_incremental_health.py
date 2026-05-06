"""
Tests for Phase 10 (Phase 10.10): Incremental Health Analysis.

Tests fingerprinting, persistence, diff logic, and 3 API endpoints.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.analysis.incremental_health import (
    compute_fingerprint,
    compute_health_diff,
    copy_unchanged_findings,
    persist_findings,
)
from app.main import app
from app.storage.database import get_db
from app.storage.models import (
    Repo,
    RepoSnapshot,
    SnapshotStatus,
)
from tests.conftest import create_tables, drop_tables, override_get_db

app.dependency_overrides[get_db] = override_get_db


# =======================================================================
# Unit tests: fingerprinting
# =======================================================================


class TestFingerprint:

    def test_deterministic(self):
        fp1 = compute_fingerprint("CC001", "mod.func", "main.py", 10)
        fp2 = compute_fingerprint("CC001", "mod.func", "main.py", 10)
        assert fp1 == fp2

    def test_different_rule(self):
        fp1 = compute_fingerprint("CC001", "mod.func", "main.py", 10)
        fp2 = compute_fingerprint("CC002", "mod.func", "main.py", 10)
        assert fp1 != fp2

    def test_different_line(self):
        fp1 = compute_fingerprint("CC001", "mod.func", "main.py", 10)
        fp2 = compute_fingerprint("CC001", "mod.func", "main.py", 20)
        assert fp1 != fp2

    def test_different_file(self):
        fp1 = compute_fingerprint("CC001", "mod.func", "main.py", 10)
        fp2 = compute_fingerprint("CC001", "mod.func", "other.py", 10)
        assert fp1 != fp2

    def test_length(self):
        fp = compute_fingerprint("CC001", "mod.func", "main.py", 10)
        assert len(fp) == 32


# =======================================================================
# Unit tests: persist and diff
# =======================================================================


class TestPersistAndDiff:

    @pytest.mark.asyncio
    async def test_persist_findings(self):
        await drop_tables()
        await create_tables()
        async for db in override_get_db():
            db.add(Repo(id="r1", name="t", url="http://x"))
            db.add(RepoSnapshot(
                id="s1", repo_id="r1", commit_sha="a",
                status=SnapshotStatus.completed, file_count=1,
            ))
            await db.commit()

            findings = [
                {"rule_id": "CC001", "symbol_fq_name": "mod.f",
                 "file_path": "a.py", "line": 5, "severity": "warning",
                 "message": "High CC"},
                {"rule_id": "DUP001", "symbol_fq_name": "mod.g",
                 "file_path": "b.py", "line": 10, "severity": "error",
                 "message": "Duplicate"},
            ]
            count = await persist_findings(db, "s1", findings)
            await db.commit()
            assert count == 2
            break
        await drop_tables()

    @pytest.mark.asyncio
    async def test_diff_added_and_fixed(self):
        await drop_tables()
        await create_tables()
        async for db in override_get_db():
            db.add(Repo(id="r1", name="t", url="http://x"))
            db.add(RepoSnapshot(
                id="s1", repo_id="r1", commit_sha="a",
                status=SnapshotStatus.completed, file_count=1,
            ))
            db.add(RepoSnapshot(
                id="s2", repo_id="r1", commit_sha="b",
                status=SnapshotStatus.completed, file_count=1,
            ))
            await db.commit()

            # s1 has findings A, B
            await persist_findings(db, "s1", [
                {"rule_id": "CC001", "symbol_fq_name": "f",
                 "file_path": "a.py", "line": 5, "severity": "warning",
                 "message": "A"},
                {"rule_id": "CC002", "symbol_fq_name": "g",
                 "file_path": "b.py", "line": 10, "severity": "error",
                 "message": "B"},
            ])
            # s2 has findings A, C (B fixed, C added)
            await persist_findings(db, "s2", [
                {"rule_id": "CC001", "symbol_fq_name": "f",
                 "file_path": "a.py", "line": 5, "severity": "warning",
                 "message": "A"},
                {"rule_id": "CC003", "symbol_fq_name": "h",
                 "file_path": "c.py", "line": 1, "severity": "info",
                 "message": "C"},
            ])
            await db.commit()

            diff = await compute_health_diff(db, "s2", "s1")
            assert len(diff.added) == 1  # C
            assert len(diff.fixed) == 1  # B
            assert diff.unchanged_count == 1  # A
            assert diff.new_total == 2
            assert diff.prev_total == 2
            break
        await drop_tables()

    @pytest.mark.asyncio
    async def test_copy_unchanged(self):
        await drop_tables()
        await create_tables()
        async for db in override_get_db():
            db.add(Repo(id="r1", name="t", url="http://x"))
            db.add(RepoSnapshot(
                id="s1", repo_id="r1", commit_sha="a",
                status=SnapshotStatus.completed, file_count=1,
            ))
            db.add(RepoSnapshot(
                id="s2", repo_id="r1", commit_sha="b",
                status=SnapshotStatus.completed, file_count=1,
            ))
            await db.commit()

            await persist_findings(db, "s1", [
                {"rule_id": "CC001", "symbol_fq_name": "f",
                 "file_path": "a.py", "line": 5, "severity": "warning",
                 "message": "unchanged"},
                {"rule_id": "CC002", "symbol_fq_name": "g",
                 "file_path": "changed.py", "line": 10, "severity": "error",
                 "message": "changed file"},
            ])
            await db.commit()

            copied = await copy_unchanged_findings(
                db, "s1", "s2", {"changed.py"},
            )
            await db.commit()
            assert copied == 1  # only a.py finding copied
            break
        await drop_tables()


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
            id="s1", repo_id="r1", commit_sha="aaa",
            status=SnapshotStatus.completed, file_count=3,
        ))
        db.add(RepoSnapshot(
            id="s2", repo_id="r1", commit_sha="bbb",
            status=SnapshotStatus.completed, file_count=4,
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


class TestPersistEndpoint:

    @pytest.mark.asyncio
    async def test_persist(self, client):
        resp = await client.post(
            "/repos/r1/snapshots/s1/health/findings",
            json={"findings": [
                {"rule_id": "CC001", "symbol_fq_name": "mod.f",
                 "file_path": "a.py", "line": 5, "severity": "warning",
                 "message": "High CC"},
            ]},
        )
        assert resp.status_code == 201
        assert resp.json()["persisted"] == 1

    @pytest.mark.asyncio
    async def test_persist_multiple(self, client):
        findings = [
            {"rule_id": f"CC{i:03d}", "symbol_fq_name": f"f{i}",
             "file_path": "x.py", "line": i, "severity": "warning",
             "message": f"m{i}"}
            for i in range(5)
        ]
        resp = await client.post(
            "/repos/r1/snapshots/s1/health/findings",
            json={"findings": findings},
        )
        assert resp.json()["persisted"] == 5

    @pytest.mark.asyncio
    async def test_persist_404(self, client):
        resp = await client.post(
            "/repos/r1/snapshots/bad/health/findings",
            json={"findings": []},
        )
        assert resp.status_code == 404


class TestListFindings:

    @pytest.mark.asyncio
    async def test_list_empty(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/health/findings")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["findings"] == []

    @pytest.mark.asyncio
    async def test_list_after_persist(self, client):
        await client.post(
            "/repos/r1/snapshots/s1/health/findings",
            json={"findings": [
                {"rule_id": "CC001", "symbol_fq_name": "f",
                 "file_path": "a.py", "line": 5, "severity": "warning",
                 "message": "x"},
                {"rule_id": "CC002", "symbol_fq_name": "g",
                 "file_path": "b.py", "line": 10, "severity": "error",
                 "message": "y"},
            ]},
        )
        resp = await client.get("/repos/r1/snapshots/s1/health/findings")
        data = resp.json()
        assert data["total"] == 2
        assert len(data["findings"]) == 2

    @pytest.mark.asyncio
    async def test_filter_severity(self, client):
        await client.post(
            "/repos/r1/snapshots/s1/health/findings",
            json={"findings": [
                {"rule_id": "A", "symbol_fq_name": "f",
                 "file_path": "a.py", "line": 1, "severity": "error",
                 "message": "e"},
                {"rule_id": "B", "symbol_fq_name": "g",
                 "file_path": "b.py", "line": 2, "severity": "warning",
                 "message": "w"},
            ]},
        )
        resp = await client.get(
            "/repos/r1/snapshots/s1/health/findings?severity=error",
        )
        findings = resp.json()["findings"]
        assert len(findings) == 1
        assert findings[0]["severity"] == "error"

    @pytest.mark.asyncio
    async def test_filter_file(self, client):
        await client.post(
            "/repos/r1/snapshots/s1/health/findings",
            json={"findings": [
                {"rule_id": "A", "symbol_fq_name": "f",
                 "file_path": "target.py", "line": 1, "severity": "warning",
                 "message": "x"},
                {"rule_id": "B", "symbol_fq_name": "g",
                 "file_path": "other.py", "line": 2, "severity": "warning",
                 "message": "y"},
            ]},
        )
        resp = await client.get(
            "/repos/r1/snapshots/s1/health/findings?file_path=target.py",
        )
        assert len(resp.json()["findings"]) == 1


class TestDiffEndpoint:

    @pytest.mark.asyncio
    async def test_diff(self, client):
        # Persist findings for s1
        await client.post(
            "/repos/r1/snapshots/s1/health/findings",
            json={"findings": [
                {"rule_id": "CC001", "symbol_fq_name": "f",
                 "file_path": "a.py", "line": 5, "severity": "warning",
                 "message": "shared"},
                {"rule_id": "CC002", "symbol_fq_name": "g",
                 "file_path": "b.py", "line": 10, "severity": "error",
                 "message": "will be fixed"},
            ]},
        )
        # Persist findings for s2
        await client.post(
            "/repos/r1/snapshots/s2/health/findings",
            json={"findings": [
                {"rule_id": "CC001", "symbol_fq_name": "f",
                 "file_path": "a.py", "line": 5, "severity": "warning",
                 "message": "shared"},
                {"rule_id": "CC003", "symbol_fq_name": "h",
                 "file_path": "c.py", "line": 1, "severity": "info",
                 "message": "new issue"},
            ]},
        )
        resp = await client.get("/repos/r1/snapshots/s2/health/diff/s1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["added"]) == 1
        assert len(data["fixed"]) == 1
        assert data["unchanged_count"] == 1
        assert "+1 new" in data["summary"]
        assert "-1 fixed" in data["summary"]

    @pytest.mark.asyncio
    async def test_diff_no_changes(self, client):
        findings = [
            {"rule_id": "CC001", "symbol_fq_name": "f",
             "file_path": "a.py", "line": 5, "severity": "warning",
             "message": "same"},
        ]
        await client.post(
            "/repos/r1/snapshots/s1/health/findings",
            json={"findings": findings},
        )
        await client.post(
            "/repos/r1/snapshots/s2/health/findings",
            json={"findings": findings},
        )
        resp = await client.get("/repos/r1/snapshots/s2/health/diff/s1")
        data = resp.json()
        assert data["added"] == []
        assert data["fixed"] == []
        assert data["unchanged_count"] == 1

    @pytest.mark.asyncio
    async def test_diff_404_prev(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/health/diff/bad")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_diff_404_snapshot(self, client):
        resp = await client.get("/repos/r1/snapshots/bad/health/diff/s1")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_diff_fields(self, client):
        await client.post(
            "/repos/r1/snapshots/s1/health/findings",
            json={"findings": []},
        )
        await client.post(
            "/repos/r1/snapshots/s2/health/findings",
            json={"findings": []},
        )
        resp = await client.get("/repos/r1/snapshots/s2/health/diff/s1")
        data = resp.json()
        for field in [
            "new_snapshot_id", "prev_snapshot_id", "added", "fixed",
            "unchanged_count", "new_total", "prev_total", "summary",
        ]:
            assert field in data
