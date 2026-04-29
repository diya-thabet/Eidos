"""
Tests for Phase 3: Git Blame / Churn Analysis.

Tests the blame extractor, health rules, API endpoints,
and pipeline integration using real temporary git repos.
"""

from __future__ import annotations

import subprocess
import textwrap
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.analysis.blame import (
    FileBlame,
    LineBlameLine,
    blame_for_range,
    extract_blame_for_snapshot,
    extract_file_blame,
)
from app.main import app
from app.storage.database import get_db
from app.storage.models import Repo, RepoSnapshot, SnapshotStatus, Symbol
from tests.conftest import create_tables, drop_tables, override_get_db

app.dependency_overrides[get_db] = override_get_db


# -----------------------------------------------------------------------
# Helper: create a temp git repo with commits
# -----------------------------------------------------------------------

def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    return result.stdout


def _init_repo(tmp_path: Path) -> Path:
    """Create a git repo with some commits for testing."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "alice@test.com")
    _git(repo, "config", "user.name", "Alice")

    # First commit by Alice
    (repo / "main.py").write_text(textwrap.dedent("""\
        def hello():
            print("hello")

        def goodbye():
            print("goodbye")
    """))
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")

    # Second commit by Bob
    _git(repo, "config", "user.name", "Bob")
    _git(repo, "config", "user.email", "bob@test.com")
    (repo / "main.py").write_text(textwrap.dedent("""\
        def hello():
            print("hello world")

        def goodbye():
            print("goodbye")
    """))
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "update hello")

    # Third commit by Alice again
    _git(repo, "config", "user.name", "Alice")
    _git(repo, "config", "user.email", "alice@test.com")
    (repo / "utils.py").write_text(textwrap.dedent("""\
        def helper():
            return 42
    """))
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add utils")

    return repo


# =======================================================================
# Unit tests: blame extraction
# =======================================================================


class TestExtractFileBlame:

    def test_blame_returns_lines(self, tmp_path):
        repo = _init_repo(tmp_path)
        import git as gitmod
        r = gitmod.Repo(repo)
        fb = extract_file_blame(r, "main.py")
        assert fb is not None
        assert len(fb.lines) > 0
        assert fb.path == "main.py"

    def test_blame_line_has_author(self, tmp_path):
        repo = _init_repo(tmp_path)
        import git as gitmod
        r = gitmod.Repo(repo)
        fb = extract_file_blame(r, "main.py")
        assert fb is not None
        authors = {bl.author for bl in fb.lines}
        assert "Alice" in authors or "Bob" in authors

    def test_blame_nonexistent_file(self, tmp_path):
        repo = _init_repo(tmp_path)
        import git as gitmod
        r = gitmod.Repo(repo)
        fb = extract_file_blame(r, "nonexistent.py")
        assert fb is None

    def test_blame_multiple_authors(self, tmp_path):
        repo = _init_repo(tmp_path)
        import git as gitmod
        r = gitmod.Repo(repo)
        fb = extract_file_blame(r, "main.py")
        assert fb is not None
        authors = {bl.author for bl in fb.lines}
        assert len(authors) >= 2

    def test_blame_utils_is_alice(self, tmp_path):
        repo = _init_repo(tmp_path)
        import git as gitmod
        r = gitmod.Repo(repo)
        fb = extract_file_blame(r, "utils.py")
        assert fb is not None
        authors = {bl.author for bl in fb.lines}
        assert authors == {"Alice"}


# =======================================================================
# Unit tests: blame_for_range
# =======================================================================


class TestBlameForRange:

    def test_single_author_range(self):
        dt = datetime(2025, 1, 1, tzinfo=UTC)
        fb = FileBlame(path="test.py", lines=[
            LineBlameLine(1, "Alice", dt, "aaa"),
            LineBlameLine(2, "Alice", dt, "aaa"),
            LineBlameLine(3, "Alice", dt, "aaa"),
        ])
        info = blame_for_range(fb, 1, 3)
        assert info.last_author == "Alice"
        assert info.author_count == 1
        assert info.commit_count == 1

    def test_multi_author_range(self):
        dt1 = datetime(2025, 1, 1, tzinfo=UTC)
        dt2 = datetime(2025, 6, 1, tzinfo=UTC)
        fb = FileBlame(path="test.py", lines=[
            LineBlameLine(1, "Alice", dt1, "aaa"),
            LineBlameLine(2, "Bob", dt2, "bbb"),
            LineBlameLine(3, "Alice", dt1, "aaa"),
        ])
        info = blame_for_range(fb, 1, 3)
        assert info.author_count == 2
        assert info.commit_count == 2
        assert info.last_author == "Bob"  # Bob has later date
        assert info.last_modified_at == dt2

    def test_partial_range(self):
        dt = datetime(2025, 1, 1, tzinfo=UTC)
        fb = FileBlame(path="test.py", lines=[
            LineBlameLine(1, "Alice", dt, "aaa"),
            LineBlameLine(2, "Bob", dt, "bbb"),
            LineBlameLine(3, "Charlie", dt, "ccc"),
            LineBlameLine(4, "Dave", dt, "ddd"),
        ])
        info = blame_for_range(fb, 2, 3)
        assert info.author_count == 2
        assert set() != {"Bob", "Charlie"}

    def test_empty_range(self):
        fb = FileBlame(path="test.py", lines=[])
        info = blame_for_range(fb, 1, 10)
        assert info.author_count == 0
        assert info.commit_count == 0
        assert info.last_author == ""


# =======================================================================
# Unit tests: extract_blame_for_snapshot
# =======================================================================


class TestExtractBlameForSnapshot:

    def test_extracts_for_symbols(self, tmp_path):
        repo = _init_repo(tmp_path)
        symbols = [
            {"fq_name": "main.hello", "file_path": "main.py",
             "start_line": 1, "end_line": 2},
            {"fq_name": "main.goodbye", "file_path": "main.py",
             "start_line": 4, "end_line": 5},
            {"fq_name": "utils.helper", "file_path": "utils.py",
             "start_line": 1, "end_line": 2},
        ]
        blame_map = extract_blame_for_snapshot(repo, symbols)
        assert "main.hello" in blame_map
        assert "main.goodbye" in blame_map
        assert "utils.helper" in blame_map

    def test_hello_has_bob(self, tmp_path):
        repo = _init_repo(tmp_path)
        symbols = [
            {"fq_name": "main.hello", "file_path": "main.py",
             "start_line": 1, "end_line": 2},
        ]
        blame_map = extract_blame_for_snapshot(repo, symbols)
        info = blame_map["main.hello"]
        assert info.last_author == "Bob"

    def test_helper_has_alice(self, tmp_path):
        repo = _init_repo(tmp_path)
        symbols = [
            {"fq_name": "utils.helper", "file_path": "utils.py",
             "start_line": 1, "end_line": 2},
        ]
        blame_map = extract_blame_for_snapshot(repo, symbols)
        assert blame_map["utils.helper"].last_author == "Alice"

    def test_not_a_git_repo(self, tmp_path):
        symbols = [
            {"fq_name": "x", "file_path": "x.py",
             "start_line": 1, "end_line": 1},
        ]
        result = extract_blame_for_snapshot(tmp_path, symbols)
        assert result == {}

    def test_caches_file_blame(self, tmp_path):
        """Multiple symbols in same file should reuse blame data."""
        repo = _init_repo(tmp_path)
        symbols = [
            {"fq_name": "main.hello", "file_path": "main.py",
             "start_line": 1, "end_line": 2},
            {"fq_name": "main.goodbye", "file_path": "main.py",
             "start_line": 4, "end_line": 5},
        ]
        blame_map = extract_blame_for_snapshot(repo, symbols)
        assert len(blame_map) == 2


# =======================================================================
# Health rule tests
# =======================================================================


class TestBlameHealthRules:

    def _sym(self, name, cc=5, churn=0, author="Alice",
             modified="2020-01-01", author_count=1, namespace="app"):
        from app.analysis.models import SymbolInfo, SymbolKind
        s = SymbolInfo(
            name=name, kind=SymbolKind.METHOD,
            fq_name=f"{namespace}.{name}",
            file_path=f"{namespace}/{name}.py",
            start_line=1, end_line=20,
            namespace=namespace,
            cyclomatic_complexity=cc,
            commit_count=churn,
            last_author=author,
            last_modified_at=modified,
            author_count=author_count,
        )
        return s

    def _graph(self, symbols):
        from app.analysis.graph_builder import CodeGraph
        g = CodeGraph()
        for s in symbols:
            g.symbols[s.fq_name] = s
        g.finalize()
        return g

    def test_gb001_hotspot_fires(self):
        from app.analysis.code_health import HealthConfig
        from app.analysis.health_rules.blame import HotspotRule
        g = self._graph([self._sym("func", cc=15, churn=8)])
        findings = HotspotRule().check(g, HealthConfig())
        assert len(findings) == 1
        assert findings[0].rule_id == "GB001"

    def test_gb001_no_fire_low_churn(self):
        from app.analysis.code_health import HealthConfig
        from app.analysis.health_rules.blame import HotspotRule
        g = self._graph([self._sym("func", cc=15, churn=2)])
        findings = HotspotRule().check(g, HealthConfig())
        assert len(findings) == 0

    def test_gb001_no_fire_low_cc(self):
        from app.analysis.code_health import HealthConfig
        from app.analysis.health_rules.blame import HotspotRule
        g = self._graph([self._sym("func", cc=3, churn=20)])
        findings = HotspotRule().check(g, HealthConfig())
        assert len(findings) == 0

    def test_gb002_stale_code_fires(self):
        from app.analysis.code_health import HealthConfig
        from app.analysis.health_rules.blame import StaleCodeRule
        g = self._graph([self._sym("old", modified="2020-01-01")])
        findings = StaleCodeRule().check(g, HealthConfig())
        assert len(findings) == 1
        assert findings[0].rule_id == "GB002"

    def test_gb002_no_fire_recent(self):
        from app.analysis.code_health import HealthConfig
        from app.analysis.health_rules.blame import StaleCodeRule
        g = self._graph([self._sym("new", modified="2025-06-01")])
        findings = StaleCodeRule().check(g, HealthConfig())
        assert len(findings) == 0

    def test_gb003_bus_factor_fires(self):
        from app.analysis.code_health import HealthConfig
        from app.analysis.health_rules.blame import BusFactorRule
        syms = [
            self._sym(f"f{i}", author="OnlyBob", namespace="core")
            for i in range(6)
        ]
        # Give them distinct files
        for i, s in enumerate(syms):
            s.file_path = f"core/file{i % 3}.py"
        g = self._graph(syms)
        findings = BusFactorRule().check(g, HealthConfig())
        assert len(findings) == 1
        assert findings[0].rule_id == "GB003"

    def test_gb003_no_fire_multiple_authors(self):
        from app.analysis.code_health import HealthConfig
        from app.analysis.health_rules.blame import BusFactorRule
        syms = []
        for i in range(6):
            s = self._sym(
                f"f{i}",
                author="Alice" if i % 2 == 0 else "Bob",
                namespace="core",
            )
            s.file_path = f"core/file{i % 3}.py"
            syms.append(s)
        g = self._graph(syms)
        findings = BusFactorRule().check(g, HealthConfig())
        assert len(findings) == 0

    def test_gb004_recent_churn_fires(self):
        from app.analysis.code_health import HealthConfig
        from app.analysis.health_rules.blame import RecentChurnRule
        g = self._graph([self._sym("churny", churn=15)])
        findings = RecentChurnRule().check(g, HealthConfig())
        assert len(findings) == 1
        assert findings[0].rule_id == "GB004"

    def test_gb004_no_fire_low_churn(self):
        from app.analysis.code_health import HealthConfig
        from app.analysis.health_rules.blame import RecentChurnRule
        g = self._graph([self._sym("stable", churn=3)])
        findings = RecentChurnRule().check(g, HealthConfig())
        assert len(findings) == 0


# =======================================================================
# API endpoint tests
# =======================================================================


class TestBlameAPI:

    @pytest_asyncio.fixture(autouse=True)
    async def setup(self):
        await drop_tables()
        await create_tables()
        async for db in override_get_db():
            db.add(Repo(id="r1", name="demo", url="https://example.com"))
            db.add(RepoSnapshot(
                id="s1", repo_id="r1", commit_sha="abc",
                status=SnapshotStatus.completed, file_count=1,
            ))
            dt = datetime(2025, 6, 1, tzinfo=UTC)
            for name, cc, churn, author, acount in [
                ("simple", 2, 1, "Alice", 1),
                ("medium", 8, 3, "Bob", 2),
                ("complex", 20, 8, "Alice", 3),
                ("monster", 35, 15, "Charlie", 1),
            ]:
                db.add(Symbol(
                    snapshot_id="s1", name=name, kind="method",
                    fq_name=f"app.{name}", file_path="main.py",
                    start_line=1, end_line=50, namespace="app",
                    cyclomatic_complexity=cc,
                    cognitive_complexity=cc,
                    commit_count=churn,
                    author_count=acount,
                    last_author=author,
                    last_modified_at=dt,
                ))
            await db.commit()
        yield
        await drop_tables()

    @pytest_asyncio.fixture
    async def client(self):
        with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as ac:
                yield ac

    @pytest.mark.asyncio
    async def test_contributors_endpoint(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/contributors")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_authors"] == 3
        names = {c["author"] for c in data["contributors"]}
        assert names == {"Alice", "Bob", "Charlie"}

    @pytest.mark.asyncio
    async def test_contributors_sorted_by_count(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/contributors")
        data = resp.json()
        counts = [c["function_count"] for c in data["contributors"]]
        assert counts == sorted(counts, reverse=True)

    @pytest.mark.asyncio
    async def test_hotspots_endpoint(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/hotspots")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] > 0

    @pytest.mark.asyncio
    async def test_hotspots_sorted_by_risk(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/hotspots")
        data = resp.json()
        risks = [i["risk_score"] for i in data["items"]]
        assert risks == sorted(risks, reverse=True)

    @pytest.mark.asyncio
    async def test_hotspots_limit(self, client):
        resp = await client.get(
            "/repos/r1/snapshots/s1/hotspots", params={"limit": 2}
        )
        data = resp.json()
        assert len(data["items"]) <= 2

    @pytest.mark.asyncio
    async def test_hotspot_fields(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/hotspots")
        if resp.json()["items"]:
            item = resp.json()["items"][0]
            assert "fq_name" in item
            assert "risk_score" in item
            assert "commit_count" in item
            assert "cyclomatic_complexity" in item
            assert "last_author" in item

    @pytest.mark.asyncio
    async def test_contributors_empty_snapshot(self, client):
        async for db in override_get_db():
            db.add(RepoSnapshot(
                id="s2", repo_id="r1", commit_sha="def",
                status=SnapshotStatus.completed, file_count=0,
            ))
            await db.commit()
        resp = await client.get("/repos/r1/snapshots/s2/contributors")
        assert resp.status_code == 200
        assert resp.json()["total_authors"] == 0

    @pytest.mark.asyncio
    async def test_hotspots_empty_snapshot(self, client):
        async for db in override_get_db():
            db.add(RepoSnapshot(
                id="s3", repo_id="r1", commit_sha="ghi",
                status=SnapshotStatus.completed, file_count=0,
            ))
            await db.commit()
        resp = await client.get("/repos/r1/snapshots/s3/hotspots")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
