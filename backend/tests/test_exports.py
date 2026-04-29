"""
Tests for Phase 9: Export Enhancements.

Tests CSV ZIP, SARIF, and Markdown report generators,
plus the 3 new API endpoints.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.exports.generators import (
    generate_csv_zip,
    generate_markdown_report,
    generate_sarif,
)
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


# =======================================================================
# Unit tests: CSV ZIP generator
# =======================================================================


class TestCSVGenerator:

    def test_generates_valid_zip(self):
        symbols = [
            {"fq_name": "app.main", "name": "main", "kind": "method",
             "file_path": "main.py", "start_line": 1, "end_line": 10,
             "namespace": "app"},
        ]
        edges = [
            {"source_fq_name": "app.main", "target_fq_name": "app.helper",
             "edge_type": "calls", "file_path": "main.py", "line": 5},
        ]
        findings = [
            {"rule_id": "CC001", "rule_name": "test", "category": "complexity",
             "severity": "warning", "symbol_fq_name": "app.main",
             "file_path": "main.py", "line": 1, "message": "too complex"},
        ]
        data = generate_csv_zip(symbols, edges, findings)
        assert isinstance(data, bytes)
        assert len(data) > 0

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            assert "symbols.csv" in names
            assert "edges.csv" in names
            assert "health_findings.csv" in names

    def test_csv_content_correct(self):
        symbols = [
            {"fq_name": "a.b", "name": "b", "kind": "method",
             "file_path": "a.py", "start_line": 1, "end_line": 5},
        ]
        data = generate_csv_zip(symbols, [], [])

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            content = zf.read("symbols.csv").decode()
            reader = csv.DictReader(io.StringIO(content))
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]["fq_name"] == "a.b"
            assert rows[0]["name"] == "b"

    def test_includes_dependencies(self):
        deps = [
            {"name": "flask", "version": "2.0", "ecosystem": "pypi",
             "manifest_file": "requirements.txt"},
        ]
        data = generate_csv_zip([], [], [], dependencies=deps)

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            assert "dependencies.csv" in zf.namelist()
            content = zf.read("dependencies.csv").decode()
            assert "flask" in content

    def test_no_dependencies(self):
        data = generate_csv_zip([], [], [])
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            assert "dependencies.csv" not in zf.namelist()

    def test_empty_data(self):
        data = generate_csv_zip([], [], [])
        assert isinstance(data, bytes)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            content = zf.read("symbols.csv").decode()
            reader = csv.DictReader(io.StringIO(content))
            assert list(reader) == []

    def test_csv_headers_present(self):
        data = generate_csv_zip([], [], [])
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            content = zf.read("symbols.csv").decode()
            assert "fq_name" in content
            assert "kind" in content

    def test_multiple_symbols(self):
        symbols = [
            {"fq_name": f"ns.f{i}", "name": f"f{i}", "kind": "method",
             "file_path": "a.py", "start_line": i, "end_line": i + 5}
            for i in range(10)
        ]
        data = generate_csv_zip(symbols, [], [])
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            content = zf.read("symbols.csv").decode()
            reader = csv.DictReader(io.StringIO(content))
            assert len(list(reader)) == 10


# =======================================================================
# Unit tests: SARIF generator
# =======================================================================


class TestSARIFGenerator:

    def test_valid_sarif_structure(self):
        findings = [
            {"rule_id": "CC001", "rule_name": "high_cc",
             "severity": "warning", "file_path": "main.py",
             "line": 10, "message": "Complexity too high"},
        ]
        sarif = generate_sarif(findings)
        assert sarif["version"] == "2.1.0"
        assert "$schema" in sarif
        assert len(sarif["runs"]) == 1

    def test_sarif_tool_info(self):
        sarif = generate_sarif([], tool_name="TestTool", tool_version="9.9")
        driver = sarif["runs"][0]["tool"]["driver"]
        assert driver["name"] == "TestTool"
        assert driver["version"] == "9.9"

    def test_sarif_results(self):
        findings = [
            {"rule_id": "CC001", "severity": "error",
             "file_path": "a.py", "line": 5, "message": "bad"},
            {"rule_id": "CC002", "severity": "info",
             "file_path": "b.py", "line": 10, "message": "ok"},
        ]
        sarif = generate_sarif(findings)
        results = sarif["runs"][0]["results"]
        assert len(results) == 2
        assert results[0]["ruleId"] == "CC001"
        assert results[0]["level"] == "error"
        assert results[1]["level"] == "note"  # info -> note

    def test_sarif_locations(self):
        findings = [
            {"rule_id": "X", "file_path": "src/main.py",
             "line": 42, "message": "test"},
        ]
        sarif = generate_sarif(findings)
        loc = sarif["runs"][0]["results"][0]["locations"][0]
        assert loc["physicalLocation"]["artifactLocation"]["uri"] == "src/main.py"
        assert loc["physicalLocation"]["region"]["startLine"] == 42

    def test_sarif_no_location_when_empty(self):
        findings = [
            {"rule_id": "X", "file_path": "", "line": 0, "message": "no file"},
        ]
        sarif = generate_sarif(findings)
        assert "locations" not in sarif["runs"][0]["results"][0]

    def test_sarif_with_rules_meta(self):
        meta = [
            {"rule_id": "CC001", "rule_name": "high_cc",
             "description": "Too complex", "severity": "warning"},
        ]
        findings = [
            {"rule_id": "CC001", "message": "test", "severity": "warning"},
        ]
        sarif = generate_sarif(findings, rules_meta=meta)
        rules = sarif["runs"][0]["tool"]["driver"]["rules"]
        assert len(rules) == 1
        assert rules[0]["id"] == "CC001"

    def test_sarif_empty_findings(self):
        sarif = generate_sarif([])
        assert sarif["runs"][0]["results"] == []

    def test_sarif_is_json_serializable(self):
        findings = [
            {"rule_id": "X", "file_path": "a.py",
             "line": 1, "message": "test"},
        ]
        sarif = generate_sarif(findings)
        text = json.dumps(sarif)
        assert "$schema" in text


# =======================================================================
# Unit tests: Markdown report
# =======================================================================


class TestMarkdownGenerator:

    def test_markdown_structure(self):
        md = generate_markdown_report(
            snapshot_id="s1", repo_name="my-repo",
            symbol_count=100, file_count=20,
            edge_count=50, health_findings=[],
        )
        assert "# Code Health Report: my-repo" in md
        assert "s1" in md
        assert "| Files | 20 |" in md
        assert "| Symbols | 100 |" in md

    def test_markdown_findings(self):
        findings = [
            {"rule_id": "CC001", "severity": "warning",
             "file_path": "main.py", "line": 5, "message": "test msg"},
        ]
        md = generate_markdown_report(
            "s1", "repo", 10, 2, 5, findings,
        )
        assert "CC001" in md
        assert "warning" in md
        assert "test msg" in md

    def test_markdown_severity_counts(self):
        findings = [
            {"severity": "error", "rule_id": "X", "message": "a"},
            {"severity": "error", "rule_id": "X", "message": "b"},
            {"severity": "warning", "rule_id": "Y", "message": "c"},
        ]
        md = generate_markdown_report("s1", "r", 0, 0, 0, findings)
        assert "**ERROR**: 2" in md
        assert "**WARNING**: 1" in md

    def test_markdown_top_complex(self):
        top = [
            {"fq_name": "app.complex_fn", "file_path": "a.py",
             "cyclomatic_complexity": 25, "cognitive_complexity": 30},
        ]
        md = generate_markdown_report(
            "s1", "r", 10, 2, 5, [], top_complex=top,
        )
        assert "app.complex_fn" in md
        assert "25" in md

    def test_markdown_dependencies(self):
        deps = [{"name": "flask"}]
        md = generate_markdown_report(
            "s1", "r", 0, 0, 0, [], dependencies=deps,
        )
        assert "Dependencies" in md

    def test_markdown_clones(self):
        md = generate_markdown_report(
            "s1", "r", 0, 0, 0, [], clone_count=5,
        )
        assert "Code clones" in md
        assert "5" in md

    def test_markdown_empty(self):
        md = generate_markdown_report("s1", "r", 0, 0, 0, [])
        assert "Code Health Report" in md

    def test_markdown_truncates_findings(self):
        findings = [
            {"rule_id": f"R{i}", "severity": "info",
             "file_path": "a.py", "line": i, "message": f"msg{i}"}
            for i in range(50)
        ]
        md = generate_markdown_report("s1", "r", 0, 0, 0, findings)
        assert "...and 20 more findings" in md


# =======================================================================
# API tests
# =======================================================================


@pytest_asyncio.fixture(autouse=True)
async def setup():
    await drop_tables()
    await create_tables()
    async for db in override_get_db():
        db.add(Repo(id="r1", name="demo", url="https://example.com"))
        db.add(RepoSnapshot(
            id="s1", repo_id="r1", commit_sha="abc",
            status=SnapshotStatus.completed, file_count=2,
        ))
        db.add(File(
            snapshot_id="s1", path="main.py",
            language="python", hash="h1", size_bytes=100,
        ))
        db.add(Symbol(
            snapshot_id="s1", name="complex_func", kind="method",
            fq_name="app.complex_func", file_path="main.py",
            start_line=1, end_line=50,
            cyclomatic_complexity=20,
            cognitive_complexity=25,
        ))
        db.add(Symbol(
            snapshot_id="s1", name="simple_func", kind="method",
            fq_name="app.simple_func", file_path="main.py",
            start_line=55, end_line=60,
        ))
        db.add(Edge(
            snapshot_id="s1",
            source_fq_name="app.complex_func",
            target_fq_name="app.simple_func",
            edge_type="calls", file_path="main.py",
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


class TestCSVExportAPI:

    @pytest.mark.asyncio
    async def test_csv_endpoint(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/export/csv")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"

    @pytest.mark.asyncio
    async def test_csv_is_valid_zip(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/export/csv")
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            assert "symbols.csv" in zf.namelist()
            assert "edges.csv" in zf.namelist()
            assert "health_findings.csv" in zf.namelist()

    @pytest.mark.asyncio
    async def test_csv_symbols_content(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/export/csv")
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            content = zf.read("symbols.csv").decode()
            assert "complex_func" in content
            assert "simple_func" in content

    @pytest.mark.asyncio
    async def test_csv_has_findings(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/export/csv")
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            content = zf.read("health_findings.csv").decode()
            assert "CC001" in content

    @pytest.mark.asyncio
    async def test_csv_content_disposition(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/export/csv")
        assert "attachment" in resp.headers.get("content-disposition", "")


class TestSARIFExportAPI:

    @pytest.mark.asyncio
    async def test_sarif_endpoint(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/export/sarif")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "2.1.0"

    @pytest.mark.asyncio
    async def test_sarif_has_results(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/export/sarif")
        results = resp.json()["runs"][0]["results"]
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_sarif_tool_name(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/export/sarif")
        driver = resp.json()["runs"][0]["tool"]["driver"]
        assert driver["name"] == "Eidos"


class TestMarkdownExportAPI:

    @pytest.mark.asyncio
    async def test_markdown_endpoint(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/export/markdown")
        assert resp.status_code == 200
        assert "text/markdown" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_markdown_content(self, client):
        text = (await client.get(
            "/repos/r1/snapshots/s1/export/markdown"
        )).text
        assert "Code Health Report" in text
        assert "demo" in text

    @pytest.mark.asyncio
    async def test_markdown_has_findings(self, client):
        text = (await client.get(
            "/repos/r1/snapshots/s1/export/markdown"
        )).text
        assert "CC001" in text

    @pytest.mark.asyncio
    async def test_markdown_content_disposition(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/export/markdown")
        assert "attachment" in resp.headers.get("content-disposition", "")


class TestExportEdgeCases:

    @pytest.mark.asyncio
    async def test_empty_snapshot_csv(self, client):
        async for db in override_get_db():
            db.add(RepoSnapshot(
                id="s2", repo_id="r1", commit_sha="def",
                status=SnapshotStatus.completed, file_count=0,
            ))
            await db.commit()
        resp = await client.get("/repos/r1/snapshots/s2/export/csv")
        assert resp.status_code == 200
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            content = zf.read("symbols.csv").decode()
            reader = csv.DictReader(io.StringIO(content))
            assert list(reader) == []

    @pytest.mark.asyncio
    async def test_empty_snapshot_sarif(self, client):
        async for db in override_get_db():
            db.add(RepoSnapshot(
                id="s3", repo_id="r1", commit_sha="ghi",
                status=SnapshotStatus.completed, file_count=0,
            ))
            await db.commit()
        resp = await client.get("/repos/r1/snapshots/s3/export/sarif")
        assert resp.status_code == 200
        assert resp.json()["runs"][0]["results"] == []

    @pytest.mark.asyncio
    async def test_empty_snapshot_markdown(self, client):
        async for db in override_get_db():
            db.add(RepoSnapshot(
                id="s4", repo_id="r1", commit_sha="jkl",
                status=SnapshotStatus.completed, file_count=0,
            ))
            await db.commit()
        resp = await client.get("/repos/r1/snapshots/s4/export/markdown")
        assert resp.status_code == 200
        assert "Code Health Report" in resp.text
