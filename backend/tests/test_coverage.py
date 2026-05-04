"""
Tests for Phase 1 (Phase 10.1): Test Coverage Tracking.

Tests the coverage parser, DB model, and 4 API endpoints:
- POST /repos/{id}/snapshots/{sid}/coverage
- GET /repos/{id}/snapshots/{sid}/coverage
- DELETE /repos/{id}/snapshots/{sid}/coverage
- GET /repos/{id}/coverage/history
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.analysis.coverage_parser import (
    coverage_grade,
    parse_coverage_json,
    parse_coverage_text,
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
# Sample coverage payloads
# =======================================================================


SAMPLE_COVERAGE = {
    "meta": {
        "format": 3,
        "version": "7.6.0",
        "timestamp": "2026-01-01T12:00:00",
        "branch_coverage": True,
        "show_contexts": False,
    },
    "totals": {
        "covered_lines": 1500,
        "num_statements": 2000,
        "percent_covered": 75.0,
        "percent_covered_display": "75",
        "missing_lines": 500,
        "excluded_lines": 50,
        "num_branches": 400,
        "covered_branches": 320,
        "percent_branches_covered": 80.0,
    },
    "files": {
        "app/main.py": {
            "executed_lines": [1, 2, 3, 4, 5],
            "summary": {
                "covered_lines": 5,
                "num_statements": 5,
                "percent_covered": 100.0,
                "missing_lines": 0,
                "excluded_lines": 2,
                "num_branches": 0,
                "covered_branches": 0,
                "percent_branches_covered": 100.0,
            },
            "missing_lines": [],
            "excluded_lines": [10, 11],
        },
        "app/api/repos.py": {
            "executed_lines": list(range(1, 80)),
            "summary": {
                "covered_lines": 79,
                "num_statements": 100,
                "percent_covered": 79.0,
                "missing_lines": 21,
                "excluded_lines": 0,
                "num_branches": 20,
                "covered_branches": 15,
                "percent_branches_covered": 75.0,
            },
            "missing_lines": [80, 81, 82, 83, 84],
            "excluded_lines": [],
        },
        "app/legacy.py": {
            "executed_lines": [1, 2],
            "summary": {
                "covered_lines": 2,
                "num_statements": 50,
                "percent_covered": 4.0,
                "missing_lines": 48,
                "excluded_lines": 0,
                "num_branches": 10,
                "covered_branches": 0,
                "percent_branches_covered": 0.0,
            },
            "missing_lines": list(range(3, 51)),
            "excluded_lines": [],
        },
    },
}


# =======================================================================
# Unit tests: parser
# =======================================================================


class TestCoverageParser:

    def test_parses_totals(self):
        result = parse_coverage_json(SAMPLE_COVERAGE)
        assert result.overall_percent == 75.0
        assert result.branch_percent == 80.0
        assert result.covered_lines == 1500
        assert result.missing_lines == 500
        assert result.num_statements == 2000
        assert result.num_branches == 400
        assert result.covered_branches == 320

    def test_parses_files(self):
        result = parse_coverage_json(SAMPLE_COVERAGE)
        assert result.file_count == 3
        assert len(result.files) == 3

    def test_files_sorted_by_lowest_coverage(self):
        result = parse_coverage_json(SAMPLE_COVERAGE)
        # legacy.py (4%) should come first
        assert result.files[0].path == "app/legacy.py"
        assert result.files[0].percent == 4.0
        # main.py (100%) should come last
        assert result.files[-1].path == "app/main.py"

    def test_file_missing_lines(self):
        result = parse_coverage_json(SAMPLE_COVERAGE)
        legacy = next(f for f in result.files if "legacy" in f.path)
        assert len(legacy.missing_line_numbers) == 48

    def test_normalize_path_backslashes(self):
        data = {
            "totals": {"covered_lines": 1, "num_statements": 1, "percent_covered": 100.0},
            "files": {
                "app\\api\\repos.py": {
                    "summary": {"covered_lines": 1, "num_statements": 1, "percent_covered": 100.0},
                }
            },
        }
        result = parse_coverage_json(data)
        assert result.files[0].path == "app/api/repos.py"

    def test_meta_extracted(self):
        result = parse_coverage_json(SAMPLE_COVERAGE)
        assert result.format_version == "3"
        assert "2026" in result.timestamp

    def test_empty_files_dict(self):
        data = {
            "totals": {
                "covered_lines": 0, "num_statements": 0, "percent_covered": 0.0,
            },
            "files": {},
        }
        result = parse_coverage_json(data)
        assert result.file_count == 0
        assert result.files == []

    def test_invalid_input_raises(self):
        with pytest.raises(ValueError):
            parse_coverage_json("not a dict")  # type: ignore[arg-type]

    def test_empty_dict_raises(self):
        with pytest.raises(ValueError, match="missing"):
            parse_coverage_json({})

    def test_parse_text(self):
        text = json.dumps(SAMPLE_COVERAGE)
        result = parse_coverage_text(text)
        assert result.overall_percent == 75.0

    def test_parse_invalid_json_raises(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            parse_coverage_text("not json {{{")

    def test_percent_rounded(self):
        data = {
            "totals": {
                "covered_lines": 1, "num_statements": 3,
                "percent_covered": 33.333333,
                "missing_lines": 2,
            },
            "files": {},
        }
        result = parse_coverage_json(data)
        assert result.overall_percent == 33.33


class TestCoverageGrade:

    def test_a_grade(self):
        assert coverage_grade(95.0) == "A"
        assert coverage_grade(90.0) == "A"

    def test_b_grade(self):
        assert coverage_grade(85.0) == "B"
        assert coverage_grade(80.0) == "B"

    def test_c_grade(self):
        assert coverage_grade(75.0) == "C"
        assert coverage_grade(70.0) == "C"

    def test_d_grade(self):
        assert coverage_grade(65.0) == "D"
        assert coverage_grade(60.0) == "D"

    def test_f_grade(self):
        assert coverage_grade(50.0) == "F"
        assert coverage_grade(0.0) == "F"


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
            id="s1", repo_id="r1", commit_sha="abc",
            status=SnapshotStatus.completed, file_count=3,
        ))
        db.add(RepoSnapshot(
            id="s2", repo_id="r1", commit_sha="def",
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


# -----------------------------------------------------------------------
# POST upload
# -----------------------------------------------------------------------


class TestUploadCoverage:

    @pytest.mark.asyncio
    async def test_upload_success(self, client):
        resp = await client.post(
            "/repos/r1/snapshots/s1/coverage",
            json=SAMPLE_COVERAGE,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["overall_percent"] == 75.0
        assert data["grade"] == "C"
        assert data["covered_lines"] == 1500

    @pytest.mark.asyncio
    async def test_upload_returns_summary_fields(self, client):
        resp = await client.post(
            "/repos/r1/snapshots/s1/coverage",
            json=SAMPLE_COVERAGE,
        )
        data = resp.json()
        for field in [
            "snapshot_id", "overall_percent", "branch_percent",
            "grade", "covered_lines", "missing_lines",
            "file_count", "uploaded_at",
        ]:
            assert field in data

    @pytest.mark.asyncio
    async def test_upload_replaces_existing(self, client):
        await client.post(
            "/repos/r1/snapshots/s1/coverage", json=SAMPLE_COVERAGE,
        )
        # Upload modified version
        modified = dict(SAMPLE_COVERAGE)
        modified["totals"] = {**SAMPLE_COVERAGE["totals"], "percent_covered": 90.0}
        resp = await client.post(
            "/repos/r1/snapshots/s1/coverage", json=modified,
        )
        assert resp.status_code == 201
        assert resp.json()["overall_percent"] == 90.0

        # Verify only one record exists
        get_resp = await client.get("/repos/r1/snapshots/s1/coverage")
        assert get_resp.json()["overall_percent"] == 90.0

    @pytest.mark.asyncio
    async def test_upload_invalid_data(self, client):
        resp = await client.post(
            "/repos/r1/snapshots/s1/coverage",
            json={"totally": "wrong"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_404_unknown_snapshot(self, client):
        resp = await client.post(
            "/repos/r1/snapshots/unknown/coverage",
            json=SAMPLE_COVERAGE,
        )
        assert resp.status_code == 404


# -----------------------------------------------------------------------
# GET coverage
# -----------------------------------------------------------------------


class TestGetCoverage:

    @pytest.mark.asyncio
    async def test_get_returns_404_when_no_report(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/coverage")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_returns_uploaded_data(self, client):
        await client.post(
            "/repos/r1/snapshots/s1/coverage", json=SAMPLE_COVERAGE,
        )
        resp = await client.get("/repos/r1/snapshots/s1/coverage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["overall_percent"] == 75.0
        assert data["file_count"] == 3
        assert len(data["files"]) == 3

    @pytest.mark.asyncio
    async def test_get_files_sorted_by_lowest(self, client):
        await client.post(
            "/repos/r1/snapshots/s1/coverage", json=SAMPLE_COVERAGE,
        )
        resp = await client.get("/repos/r1/snapshots/s1/coverage")
        files = resp.json()["files"]
        # legacy.py (4%) should be first
        assert "legacy" in files[0]["path"]

    @pytest.mark.asyncio
    async def test_get_without_files(self, client):
        await client.post(
            "/repos/r1/snapshots/s1/coverage", json=SAMPLE_COVERAGE,
        )
        resp = await client.get(
            "/repos/r1/snapshots/s1/coverage?include_files=false",
        )
        assert resp.json()["files"] == []
        # Summary still present
        assert resp.json()["overall_percent"] == 75.0

    @pytest.mark.asyncio
    async def test_get_filter_by_min_percent(self, client):
        await client.post(
            "/repos/r1/snapshots/s1/coverage", json=SAMPLE_COVERAGE,
        )
        resp = await client.get(
            "/repos/r1/snapshots/s1/coverage?min_percent=50",
        )
        files = resp.json()["files"]
        # Only files BELOW 50% (legacy at 4%)
        assert len(files) == 1
        assert "legacy" in files[0]["path"]

    @pytest.mark.asyncio
    async def test_get_grade_in_response(self, client):
        await client.post(
            "/repos/r1/snapshots/s1/coverage", json=SAMPLE_COVERAGE,
        )
        resp = await client.get("/repos/r1/snapshots/s1/coverage")
        assert resp.json()["grade"] == "C"  # 75% = C


# -----------------------------------------------------------------------
# DELETE coverage
# -----------------------------------------------------------------------


class TestDeleteCoverage:

    @pytest.mark.asyncio
    async def test_delete_success(self, client):
        await client.post(
            "/repos/r1/snapshots/s1/coverage", json=SAMPLE_COVERAGE,
        )
        resp = await client.delete("/repos/r1/snapshots/s1/coverage")
        assert resp.status_code == 204
        # Verify gone
        get_resp = await client.get("/repos/r1/snapshots/s1/coverage")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_404_when_missing(self, client):
        resp = await client.delete("/repos/r1/snapshots/s1/coverage")
        assert resp.status_code == 404


# -----------------------------------------------------------------------
# GET history
# -----------------------------------------------------------------------


class TestCoverageHistory:

    @pytest.mark.asyncio
    async def test_history_empty(self, client):
        resp = await client.get("/repos/r1/coverage/history")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_history_one_snapshot(self, client):
        await client.post(
            "/repos/r1/snapshots/s1/coverage", json=SAMPLE_COVERAGE,
        )
        resp = await client.get("/repos/r1/coverage/history")
        assert len(resp.json()) == 1

    @pytest.mark.asyncio
    async def test_history_two_snapshots(self, client):
        await client.post(
            "/repos/r1/snapshots/s1/coverage", json=SAMPLE_COVERAGE,
        )
        modified = dict(SAMPLE_COVERAGE)
        modified["totals"] = {
            **SAMPLE_COVERAGE["totals"], "percent_covered": 88.0,
        }
        await client.post(
            "/repos/r1/snapshots/s2/coverage", json=modified,
        )
        resp = await client.get("/repos/r1/coverage/history")
        assert len(resp.json()) == 2

    @pytest.mark.asyncio
    async def test_history_summary_fields(self, client):
        await client.post(
            "/repos/r1/snapshots/s1/coverage", json=SAMPLE_COVERAGE,
        )
        item = (await client.get("/repos/r1/coverage/history")).json()[0]
        for field in [
            "snapshot_id", "overall_percent", "grade",
            "covered_lines", "file_count", "uploaded_at",
        ]:
            assert field in item

    @pytest.mark.asyncio
    async def test_history_limit(self, client):
        await client.post(
            "/repos/r1/snapshots/s1/coverage", json=SAMPLE_COVERAGE,
        )
        await client.post(
            "/repos/r1/snapshots/s2/coverage", json=SAMPLE_COVERAGE,
        )
        resp = await client.get("/repos/r1/coverage/history?limit=1")
        assert len(resp.json()) == 1


# -----------------------------------------------------------------------
# Cascading delete (snapshot deletion removes coverage)
# -----------------------------------------------------------------------


class TestCascadingDelete:

    @pytest.mark.asyncio
    async def test_snapshot_delete_cascades_to_coverage(self, client):
        await client.post(
            "/repos/r1/snapshots/s1/coverage", json=SAMPLE_COVERAGE,
        )
        # Verify exists via API
        resp = await client.get("/repos/r1/snapshots/s1/coverage")
        assert resp.status_code == 200

        # Delete snapshot
        resp = await client.delete("/repos/r1/snapshots/s1")
        assert resp.status_code == 204

        # Snapshot is gone, so verify_snapshot returns 404 for coverage too
        resp = await client.get("/repos/r1/snapshots/s1/coverage")
        assert resp.status_code == 404
