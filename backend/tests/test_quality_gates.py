"""
Tests for Phase 2 (Phase 10.2): Quality Gates.

Tests the gate evaluator logic and 7 API endpoints:
- POST /repos/{id}/quality-gates
- GET /repos/{id}/quality-gates
- GET /repos/{id}/quality-gates/{gate_id}
- PATCH /repos/{id}/quality-gates/{gate_id}
- DELETE /repos/{id}/quality-gates/{gate_id}
- POST /repos/{id}/snapshots/{sid}/evaluate-gate/{gate_id}
- GET /quality-gates/schema
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.analysis.gate_evaluator import evaluate_gate, parse_gate_config
from app.main import app
from app.storage.database import get_db
from app.storage.models import (
    CoverageReport,
    Repo,
    RepoSnapshot,
    SnapshotStatus,
    Symbol,
)
from tests.conftest import create_tables, drop_tables, override_get_db

app.dependency_overrides[get_db] = override_get_db


# =======================================================================
# Unit tests: gate evaluator
# =======================================================================


class TestGateEvaluator:

    def test_all_checks_pass(self):
        config = {"max_errors": 5, "max_warnings": 10}
        metrics = {"error_count": 2, "warning_count": 3}
        result = evaluate_gate(1, "test", "s1", config, metrics)
        assert result.status == "passed"
        assert result.failed_checks == 0
        assert result.total_checks == 2

    def test_check_fails(self):
        config = {"max_errors": 0}
        metrics = {"error_count": 5}
        result = evaluate_gate(1, "test", "s1", config, metrics)
        assert result.status == "failed"
        assert result.failed_checks == 1
        assert result.checks[0].actual == 5

    def test_coverage_threshold_pass(self):
        config = {"min_coverage_percent": 80}
        metrics = {"coverage_percent": 85.0}
        result = evaluate_gate(1, "test", "s1", config, metrics)
        assert result.status == "passed"

    def test_coverage_threshold_fail(self):
        config = {"min_coverage_percent": 80}
        metrics = {"coverage_percent": 60.0}
        result = evaluate_gate(1, "test", "s1", config, metrics)
        assert result.status == "failed"

    def test_blocked_rules_pass(self):
        config = {"blocked_rules": ["CC001", "DUP003"]}
        metrics = {"findings_by_rule": {"CC001": 0, "DUP003": 0}}
        result = evaluate_gate(1, "test", "s1", config, metrics)
        assert result.status == "passed"
        assert result.total_checks == 2

    def test_blocked_rules_fail(self):
        config = {"blocked_rules": ["CC001"]}
        metrics = {"findings_by_rule": {"CC001": 3}}
        result = evaluate_gate(1, "test", "s1", config, metrics)
        assert result.status == "failed"
        assert result.checks[0].actual == 3

    def test_empty_config_passes(self):
        result = evaluate_gate(1, "test", "s1", {}, {})
        assert result.status == "passed"
        assert result.summary == "No checks configured"

    def test_mixed_pass_fail(self):
        config = {"max_errors": 0, "max_warnings": 100}
        metrics = {"error_count": 5, "warning_count": 10}
        result = evaluate_gate(1, "test", "s1", config, metrics)
        assert result.status == "failed"
        assert result.passed_checks == 1
        assert result.failed_checks == 1

    def test_summary_format(self):
        config = {"max_errors": 0, "max_warnings": 10, "max_findings": 50}
        metrics = {"error_count": 0, "warning_count": 5, "total_findings": 20}
        result = evaluate_gate(1, "g", "s1", config, metrics)
        assert "3 of 3 checks passed" in result.summary

    def test_missing_metric_defaults_to_zero(self):
        config = {"max_dead_functions": 5}
        metrics = {}  # No dead_function_count key
        result = evaluate_gate(1, "test", "s1", config, metrics)
        assert result.status == "passed"
        assert result.checks[0].actual == 0

    def test_all_numeric_checks(self):
        config = {
            "max_errors": 10,
            "max_warnings": 20,
            "max_findings": 30,
            "max_avg_cyclomatic_complexity": 15,
            "max_max_cyclomatic_complexity": 50,
            "max_long_functions": 10,
            "max_clone_groups": 5,
            "max_dead_functions": 3,
            "max_module_cycles": 0,
            "max_instability_violations": 2,
        }
        metrics = {
            "error_count": 5,
            "warning_count": 10,
            "total_findings": 15,
            "avg_cyclomatic_complexity": 8,
            "max_cyclomatic_complexity": 25,
            "long_function_count": 3,
            "clone_group_count": 2,
            "dead_function_count": 1,
            "module_cycle_count": 0,
            "instability_violation_count": 1,
        }
        result = evaluate_gate(1, "full", "s1", config, metrics)
        assert result.status == "passed"
        assert result.total_checks == 10


class TestParseGateConfig:

    def test_valid_json(self):
        assert parse_gate_config('{"max_errors": 5}') == {"max_errors": 5}

    def test_empty_string(self):
        assert parse_gate_config("") == {}

    def test_invalid_json(self):
        assert parse_gate_config("not json") == {}

    def test_non_dict(self):
        assert parse_gate_config("[1,2,3]") == {}

    def test_none(self):
        assert parse_gate_config(None) == {}  # type: ignore[arg-type]


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
        db.add(Symbol(
            snapshot_id="s1", name="func_a", kind="method",
            fq_name="mod.func_a", file_path="main.py",
            start_line=1, end_line=50, cyclomatic_complexity=15,
        ))
        db.add(Symbol(
            snapshot_id="s1", name="func_b", kind="method",
            fq_name="mod.func_b", file_path="main.py",
            start_line=55, end_line=60, cyclomatic_complexity=3,
        ))
        db.add(CoverageReport(
            snapshot_id="s1", overall_percent=75.0,
            branch_percent=60.0, covered_lines=100,
            missing_lines=33, num_statements=133,
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


class TestCreateGate:

    @pytest.mark.asyncio
    async def test_create(self, client):
        resp = await client.post("/repos/r1/quality-gates", json={
            "name": "CI Gate",
            "config": {"max_errors": 0, "min_coverage_percent": 80},
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "CI Gate"
        assert data["config"]["max_errors"] == 0
        assert data["is_active"] is True
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_minimal(self, client):
        resp = await client.post("/repos/r1/quality-gates", json={
            "name": "Empty Gate",
        })
        assert resp.status_code == 201
        assert resp.json()["config"] == {}

    @pytest.mark.asyncio
    async def test_create_404_unknown_repo(self, client):
        resp = await client.post("/repos/unknown/quality-gates", json={
            "name": "test",
        })
        assert resp.status_code == 404


class TestListGates:

    @pytest.mark.asyncio
    async def test_list_empty(self, client):
        resp = await client.get("/repos/r1/quality-gates")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_with_gates(self, client):
        await client.post("/repos/r1/quality-gates", json={"name": "G1"})
        await client.post("/repos/r1/quality-gates", json={"name": "G2"})
        resp = await client.get("/repos/r1/quality-gates")
        assert len(resp.json()) == 2

    @pytest.mark.asyncio
    async def test_list_active_only(self, client):
        await client.post("/repos/r1/quality-gates", json={
            "name": "Active", "is_active": True,
        })
        await client.post("/repos/r1/quality-gates", json={
            "name": "Inactive", "is_active": False,
        })
        resp = await client.get("/repos/r1/quality-gates?active_only=true")
        assert len(resp.json()) == 1
        assert resp.json()[0]["name"] == "Active"


class TestGetGate:

    @pytest.mark.asyncio
    async def test_get(self, client):
        create = await client.post("/repos/r1/quality-gates", json={
            "name": "My Gate", "config": {"max_errors": 3},
        })
        gate_id = create.json()["id"]
        resp = await client.get(f"/repos/r1/quality-gates/{gate_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "My Gate"

    @pytest.mark.asyncio
    async def test_get_404(self, client):
        resp = await client.get("/repos/r1/quality-gates/999")
        assert resp.status_code == 404


class TestUpdateGate:

    @pytest.mark.asyncio
    async def test_update_name(self, client):
        create = await client.post("/repos/r1/quality-gates", json={
            "name": "Old",
        })
        gate_id = create.json()["id"]
        resp = await client.patch(f"/repos/r1/quality-gates/{gate_id}", json={
            "name": "New",
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "New"

    @pytest.mark.asyncio
    async def test_update_config(self, client):
        create = await client.post("/repos/r1/quality-gates", json={
            "name": "G", "config": {"max_errors": 5},
        })
        gate_id = create.json()["id"]
        resp = await client.patch(f"/repos/r1/quality-gates/{gate_id}", json={
            "config": {"max_errors": 0, "max_warnings": 10},
        })
        assert resp.json()["config"] == {"max_errors": 0, "max_warnings": 10}

    @pytest.mark.asyncio
    async def test_update_active_status(self, client):
        create = await client.post("/repos/r1/quality-gates", json={
            "name": "G",
        })
        gate_id = create.json()["id"]
        resp = await client.patch(f"/repos/r1/quality-gates/{gate_id}", json={
            "is_active": False,
        })
        assert resp.json()["is_active"] is False

    @pytest.mark.asyncio
    async def test_update_404(self, client):
        resp = await client.patch("/repos/r1/quality-gates/999", json={
            "name": "x",
        })
        assert resp.status_code == 404


class TestDeleteGate:

    @pytest.mark.asyncio
    async def test_delete(self, client):
        create = await client.post("/repos/r1/quality-gates", json={
            "name": "Del",
        })
        gate_id = create.json()["id"]
        resp = await client.delete(f"/repos/r1/quality-gates/{gate_id}")
        assert resp.status_code == 204
        # Verify gone
        get_resp = await client.get(f"/repos/r1/quality-gates/{gate_id}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_404(self, client):
        resp = await client.delete("/repos/r1/quality-gates/999")
        assert resp.status_code == 404


class TestEvaluateGate:

    @pytest.mark.asyncio
    async def test_evaluate_passes(self, client):
        create = await client.post("/repos/r1/quality-gates", json={
            "name": "Lenient", "config": {
                "max_max_cyclomatic_complexity": 50,
                "max_long_functions": 10,
            },
        })
        gate_id = create.json()["id"]
        resp = await client.post(
            f"/repos/r1/snapshots/s1/evaluate-gate/{gate_id}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "passed"
        assert data["failed_checks"] == 0
        assert data["total_checks"] == 2

    @pytest.mark.asyncio
    async def test_evaluate_fails(self, client):
        create = await client.post("/repos/r1/quality-gates", json={
            "name": "Strict", "config": {
                "max_max_cyclomatic_complexity": 5,
                "min_coverage_percent": 90,
            },
        })
        gate_id = create.json()["id"]
        resp = await client.post(
            f"/repos/r1/snapshots/s1/evaluate-gate/{gate_id}",
        )
        data = resp.json()
        assert data["status"] == "failed"
        # Max CC is 15, threshold 5 -> fails
        # Coverage is 75%, threshold 90% -> fails
        assert data["failed_checks"] == 2

    @pytest.mark.asyncio
    async def test_evaluate_coverage_check(self, client):
        create = await client.post("/repos/r1/quality-gates", json={
            "name": "Cov", "config": {"min_coverage_percent": 70},
        })
        gate_id = create.json()["id"]
        resp = await client.post(
            f"/repos/r1/snapshots/s1/evaluate-gate/{gate_id}",
        )
        data = resp.json()
        assert data["status"] == "passed"
        assert data["checks"][0]["actual"] == 75.0

    @pytest.mark.asyncio
    async def test_evaluate_empty_config(self, client):
        create = await client.post("/repos/r1/quality-gates", json={
            "name": "Empty",
        })
        gate_id = create.json()["id"]
        resp = await client.post(
            f"/repos/r1/snapshots/s1/evaluate-gate/{gate_id}",
        )
        data = resp.json()
        assert data["status"] == "passed"
        assert data["summary"] == "No checks configured"

    @pytest.mark.asyncio
    async def test_evaluate_404_snapshot(self, client):
        create = await client.post("/repos/r1/quality-gates", json={
            "name": "G",
        })
        gate_id = create.json()["id"]
        resp = await client.post(
            f"/repos/r1/snapshots/bad/evaluate-gate/{gate_id}",
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_evaluate_404_gate(self, client):
        resp = await client.post(
            "/repos/r1/snapshots/s1/evaluate-gate/999",
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_evaluate_returns_check_details(self, client):
        create = await client.post("/repos/r1/quality-gates", json={
            "name": "Detail", "config": {"max_long_functions": 0},
        })
        gate_id = create.json()["id"]
        resp = await client.post(
            f"/repos/r1/snapshots/s1/evaluate-gate/{gate_id}",
        )
        check = resp.json()["checks"][0]
        assert "check" in check
        assert "description" in check
        assert "expected" in check
        assert "actual" in check
        assert "passed" in check


class TestGateSchema:

    @pytest.mark.asyncio
    async def test_schema_endpoint(self, client):
        resp = await client.get("/repos/quality-gates/schema")
        assert resp.status_code == 200
        data = resp.json()
        assert "available_checks" in data
        assert "max_errors" in data["available_checks"]
        assert "min_coverage_percent" in data["available_checks"]
        assert "blocked_rules" in data["available_checks"]
