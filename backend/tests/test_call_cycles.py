"""
Tests for Phase 5 (Phase 10.5): Function-Level Cycle Detection.

Tests Tarjan's SCC algorithm and the call-cycles API endpoint.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.analysis.call_cycles import (
    detect_call_cycles,
)
from app.main import app
from app.storage.database import get_db
from app.storage.models import Edge, Repo, RepoSnapshot, SnapshotStatus, Symbol
from tests.conftest import create_tables, drop_tables, override_get_db

app.dependency_overrides[get_db] = override_get_db


# =======================================================================
# Unit tests: Tarjan's SCC
# =======================================================================


class TestDetectCallCycles:

    def test_no_cycles(self):
        callees = {"a": ["b"], "b": ["c"], "c": []}
        report = detect_call_cycles(callees)
        assert report.total_cycles == 0
        assert report.direct_recursion_count == 0

    def test_direct_recursion(self):
        callees = {"a": ["a"]}
        report = detect_call_cycles(callees)
        assert report.direct_recursion_count == 1
        assert "a" in report.direct_recursions
        assert report.total_cycles == 0  # Direct recursion not counted as cycle

    def test_mutual_recursion_2(self):
        callees = {"a": ["b"], "b": ["a"]}
        report = detect_call_cycles(callees)
        assert report.total_cycles == 1
        assert report.cycles[0].size == 2
        assert set(report.cycles[0].members) == {"a", "b"}

    def test_mutual_recursion_3(self):
        callees = {"a": ["b"], "b": ["c"], "c": ["a"]}
        report = detect_call_cycles(callees)
        assert report.total_cycles == 1
        assert report.cycles[0].size == 3

    def test_multiple_cycles(self):
        callees = {
            "a": ["b"], "b": ["a"],  # cycle 1
            "x": ["y"], "y": ["z"], "z": ["x"],  # cycle 2
        }
        report = detect_call_cycles(callees)
        assert report.total_cycles == 2
        assert report.largest_cycle_size == 3

    def test_cycle_with_tail(self):
        # entry -> a -> b -> a (cycle is {a, b})
        callees = {"entry": ["a"], "a": ["b"], "b": ["a"]}
        report = detect_call_cycles(callees)
        assert report.total_cycles == 1
        assert report.cycles[0].size == 2

    def test_large_cycle(self):
        callees = {
            "f1": ["f2"], "f2": ["f3"], "f3": ["f4"],
            "f4": ["f5"], "f5": ["f1"],
        }
        report = detect_call_cycles(callees)
        assert report.total_cycles == 1
        assert report.cycles[0].size == 5

    def test_cycle_path_forms_loop(self):
        callees = {"a": ["b"], "b": ["c"], "c": ["a"]}
        report = detect_call_cycles(callees)
        path = report.cycles[0].cycle_path
        # Path should start and end with same node
        assert path[0] == path[-1]
        assert len(path) >= 3

    def test_files_populated(self):
        callees = {"mod.func_a": ["mod.func_b"], "mod.func_b": ["mod.func_a"]}
        symbol_files = {"mod.func_a": "main.py", "mod.func_b": "helper.py"}
        report = detect_call_cycles(callees, symbol_files)
        assert len(report.cycles[0].files) == 2

    def test_sorted_by_size_desc(self):
        callees = {
            "a": ["b"], "b": ["a"],  # size 2
            "x": ["y"], "y": ["z"], "z": ["w"], "w": ["x"],  # size 4
        }
        report = detect_call_cycles(callees)
        assert report.cycles[0].size >= report.cycles[1].size

    def test_empty_graph(self):
        report = detect_call_cycles({})
        assert report.total_cycles == 0
        assert report.direct_recursion_count == 0

    def test_self_loop_and_cycle(self):
        callees = {"a": ["a", "b"], "b": ["a"]}
        report = detect_call_cycles(callees)
        assert report.direct_recursion_count == 1  # a calls itself
        assert report.total_cycles == 1  # {a, b} form a mutual cycle
        assert report.cycles[0].size == 2

    def test_disconnected_components(self):
        callees = {"a": ["b"], "b": [], "x": ["y"], "y": []}
        report = detect_call_cycles(callees)
        assert report.total_cycles == 0


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
        # Symbols
        db.add(Symbol(
            snapshot_id="s1", name="func_a", kind="method",
            fq_name="mod.func_a", file_path="main.py",
            start_line=1, end_line=10,
        ))
        db.add(Symbol(
            snapshot_id="s1", name="func_b", kind="method",
            fq_name="mod.func_b", file_path="helper.py",
            start_line=1, end_line=10,
        ))
        db.add(Symbol(
            snapshot_id="s1", name="func_c", kind="method",
            fq_name="mod.func_c", file_path="util.py",
            start_line=1, end_line=10,
        ))
        # Edges forming a cycle: a -> b -> c -> a
        db.add(Edge(
            snapshot_id="s1", edge_type="calls",
            source_fq_name="mod.func_a", target_fq_name="mod.func_b",
        ))
        db.add(Edge(
            snapshot_id="s1", edge_type="calls",
            source_fq_name="mod.func_b", target_fq_name="mod.func_c",
        ))
        db.add(Edge(
            snapshot_id="s1", edge_type="calls",
            source_fq_name="mod.func_c", target_fq_name="mod.func_a",
        ))
        # Direct recursion
        db.add(Edge(
            snapshot_id="s1", edge_type="calls",
            source_fq_name="mod.func_a", target_fq_name="mod.func_a",
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


class TestCallCyclesEndpoint:

    @pytest.mark.asyncio
    async def test_detect_cycles(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/call-cycles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["snapshot_id"] == "s1"
        assert data["total_cycles"] >= 1
        assert data["direct_recursion_count"] >= 1

    @pytest.mark.asyncio
    async def test_cycle_members(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/call-cycles")
        data = resp.json()
        cycle = data["cycles"][0]
        assert cycle["size"] == 3
        assert "mod.func_a" in cycle["members"]
        assert "mod.func_b" in cycle["members"]
        assert "mod.func_c" in cycle["members"]

    @pytest.mark.asyncio
    async def test_cycle_path_loops(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/call-cycles")
        cycle = resp.json()["cycles"][0]
        # Path should form a loop
        assert cycle["cycle_path"][0] == cycle["cycle_path"][-1]

    @pytest.mark.asyncio
    async def test_cycle_files(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/call-cycles")
        cycle = resp.json()["cycles"][0]
        assert len(cycle["files"]) >= 2

    @pytest.mark.asyncio
    async def test_direct_recursions(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/call-cycles")
        data = resp.json()
        assert "mod.func_a" in data["direct_recursions"]

    @pytest.mark.asyncio
    async def test_min_cycle_size_filter(self, client):
        resp = await client.get(
            "/repos/r1/snapshots/s1/call-cycles?min_cycle_size=4",
        )
        data = resp.json()
        # Our cycle is size 3, so filtered out
        assert data["total_cycles"] == 0

    @pytest.mark.asyncio
    async def test_404_unknown_snapshot(self, client):
        resp = await client.get("/repos/r1/snapshots/bad/call-cycles")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_response_fields(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/call-cycles")
        data = resp.json()
        for field in [
            "snapshot_id", "total_cycles", "direct_recursion_count",
            "mutual_recursion_count", "largest_cycle_size",
            "cycles", "direct_recursions",
        ]:
            assert field in data
