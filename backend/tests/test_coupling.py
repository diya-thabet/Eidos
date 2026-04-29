"""
Tests for Phase 6: Module Coupling & Cohesion Metrics.

Tests the coupling analyzer, Martin metrics, cycle detection,
health rules, and the API endpoint.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.analysis.code_health import HealthConfig
from app.analysis.coupling import analyze_coupling
from app.analysis.graph_builder import CodeGraph
from app.analysis.models import (
    EdgeInfo,
    EdgeType,
    SymbolInfo,
    SymbolKind,
)
from app.main import app
from app.storage.database import get_db
from app.storage.models import (
    Edge,
    Repo,
    RepoSnapshot,
    SnapshotStatus,
    Symbol,
)
from tests.conftest import create_tables, drop_tables, override_get_db

app.dependency_overrides[get_db] = override_get_db


def _sym(name, kind=SymbolKind.METHOD, ns="app", mods="public"):
    return SymbolInfo(
        name=name, kind=kind, fq_name=f"{ns}.{name}",
        file_path=f"{ns}/{name}.py", start_line=1, end_line=10,
        namespace=ns, modifiers=[mods] if mods else [],
    )


def _edge(src, tgt, etype=EdgeType.CALLS):
    return EdgeInfo(
        source_fq_name=src, target_fq_name=tgt,
        edge_type=etype, file_path="test.py",
    )


def _graph(symbols, edges=None):
    g = CodeGraph()
    for s in symbols:
        g.symbols[s.fq_name] = s
    if edges:
        g.edges = edges
    g.finalize()
    return g


# =======================================================================
# Unit tests: coupling metrics
# =======================================================================


class TestCouplingMetrics:

    def test_isolated_modules(self):
        """Two modules with no cross-dependencies."""
        g = _graph([
            _sym("a", ns="mod_a"), _sym("b", ns="mod_b"),
        ])
        r = analyze_coupling(g)
        assert r.total_modules == 2
        for m in r.modules:
            assert m.afferent_coupling == 0
            assert m.efferent_coupling == 0
            assert m.instability == 0.0

    def test_one_way_dependency(self):
        """mod_a calls mod_b: a has Ce=1, b has Ca=1."""
        g = _graph(
            [_sym("a", ns="mod_a"), _sym("b", ns="mod_b")],
            [_edge("mod_a.a", "mod_b.b")],
        )
        r = analyze_coupling(g)
        mods = {m.name: m for m in r.modules}
        assert mods["mod_a"].efferent_coupling == 1
        assert mods["mod_a"].afferent_coupling == 0
        assert mods["mod_b"].afferent_coupling == 1
        assert mods["mod_b"].efferent_coupling == 0

    def test_instability_calculation(self):
        """Ce / (Ca + Ce)."""
        g = _graph(
            [
                _sym("a", ns="core"),
                _sym("b", ns="util"),
                _sym("c", ns="api"),
            ],
            [
                _edge("api.c", "core.a"),
                _edge("api.c", "util.b"),
            ],
        )
        r = analyze_coupling(g)
        mods = {m.name: m for m in r.modules}
        # api: Ce=2, Ca=0 => I = 2/2 = 1.0
        assert mods["api"].instability == 1.0
        # core: Ce=0, Ca=1 => I = 0/1 = 0.0
        assert mods["core"].instability == 0.0

    def test_cohesion_intra_vs_inter(self):
        """Module with all internal calls has high cohesion."""
        g = _graph(
            [
                _sym("a", ns="tight"),
                _sym("b", ns="tight"),
                _sym("c", ns="tight"),
            ],
            [
                _edge("tight.a", "tight.b"),
                _edge("tight.b", "tight.c"),
            ],
        )
        r = analyze_coupling(g)
        mods = {m.name: m for m in r.modules}
        assert mods["tight"].cohesion == 1.0
        assert mods["tight"].intra_edges == 2

    def test_low_cohesion(self):
        """Module where most calls go outside."""
        g = _graph(
            [
                _sym("a", ns="loose"),
                _sym("ext1", ns="other1"),
                _sym("ext2", ns="other2"),
            ],
            [
                _edge("loose.a", "other1.ext1"),
                _edge("loose.a", "other2.ext2"),
            ],
        )
        r = analyze_coupling(g)
        mods = {m.name: m for m in r.modules}
        assert mods["loose"].cohesion == 0.0
        assert mods["loose"].inter_edges == 2

    def test_abstractness(self):
        """Module with interfaces has higher abstractness."""
        g = _graph([
            _sym("IFoo", kind=SymbolKind.INTERFACE, ns="abs_mod"),
            _sym("Bar", kind=SymbolKind.CLASS, ns="abs_mod"),
        ])
        r = analyze_coupling(g)
        mods = {m.name: m for m in r.modules}
        # 1 interface, 2 total classes => A = 0.5
        assert mods["abs_mod"].abstractness == 0.5

    def test_distance_from_main_sequence(self):
        """Distance = |A + I - 1|."""
        g = _graph(
            [
                _sym("IFoo", kind=SymbolKind.INTERFACE, ns="mod"),
                _sym("Bar", kind=SymbolKind.CLASS, ns="mod"),
                _sym("ext", ns="ext"),
            ],
            [_edge("mod.Bar", "ext.ext")],
        )
        r = analyze_coupling(g)
        mods = {m.name: m for m in r.modules}
        m = mods["mod"]
        expected = abs(m.abstractness + m.instability - 1.0)
        assert abs(m.distance - expected) < 0.01


# =======================================================================
# Unit tests: cycle detection
# =======================================================================


class TestCycleDetection:

    def test_no_cycles(self):
        g = _graph(
            [_sym("a", ns="m1"), _sym("b", ns="m2")],
            [_edge("m1.a", "m2.b")],
        )
        r = analyze_coupling(g)
        assert r.dependency_cycles == []

    def test_simple_cycle(self):
        g = _graph(
            [_sym("a", ns="m1"), _sym("b", ns="m2")],
            [
                _edge("m1.a", "m2.b"),
                _edge("m2.b", "m1.a"),
            ],
        )
        r = analyze_coupling(g)
        assert len(r.dependency_cycles) >= 1

    def test_triangle_cycle(self):
        g = _graph(
            [
                _sym("a", ns="m1"),
                _sym("b", ns="m2"),
                _sym("c", ns="m3"),
            ],
            [
                _edge("m1.a", "m2.b"),
                _edge("m2.b", "m3.c"),
                _edge("m3.c", "m1.a"),
            ],
        )
        r = analyze_coupling(g)
        assert len(r.dependency_cycles) >= 1
        # Cycle should contain all 3 modules
        cycle_mods = set()
        for c in r.dependency_cycles:
            cycle_mods.update(c)
        assert {"m1", "m2", "m3"}.issubset(cycle_mods)


# =======================================================================
# Unit tests: averages
# =======================================================================


class TestAverages:

    def test_avg_instability(self):
        g = _graph(
            [_sym("a", ns="m1"), _sym("b", ns="m2")],
            [_edge("m1.a", "m2.b")],
        )
        r = analyze_coupling(g)
        assert 0.0 <= r.avg_instability <= 1.0

    def test_empty_graph(self):
        g = _graph([])
        r = analyze_coupling(g)
        assert r.total_modules == 0
        assert r.avg_instability == 0.0
        assert r.avg_cohesion == 0.0


# =======================================================================
# Health rule tests
# =======================================================================


class TestCouplingHealthRules:

    def test_mc001_high_instability(self):
        from app.analysis.health_rules.coupling import HighInstabilityRule
        g = _graph(
            [
                _sym("a", ns="unstable"),
                _sym("b", ns="unstable"),
                _sym("c", ns="unstable"),
                _sym("s1", ns="stable1"),
                _sym("s2", ns="stable2"),
                _sym("s3", ns="stable3"),
            ],
            [
                _edge("unstable.a", "stable1.s1"),
                _edge("unstable.b", "stable2.s2"),
                _edge("unstable.c", "stable3.s3"),
            ],
        )
        findings = HighInstabilityRule().check(g, HealthConfig())
        mc001 = [f for f in findings if f.rule_id == "MC001"]
        assert len(mc001) >= 1

    def test_mc002_low_cohesion(self):
        from app.analysis.health_rules.coupling import LowCohesionModuleRule
        syms = [_sym(f"f{i}", ns="scattered") for i in range(6)]
        ext_syms = [_sym(f"e{i}", ns=f"ext{i}") for i in range(6)]
        edges = [
            _edge(f"scattered.f{i}", f"ext{i}.e{i}")
            for i in range(6)
        ]
        g = _graph(syms + ext_syms, edges)
        findings = LowCohesionModuleRule().check(g, HealthConfig())
        mc002 = [f for f in findings if f.rule_id == "MC002"]
        assert len(mc002) >= 1

    def test_mc003_zone_of_pain(self):
        from app.analysis.health_rules.coupling import ZoneOfPainRule
        # Stable + concrete = zone of pain
        syms = [
            _sym("C1", kind=SymbolKind.CLASS, ns="pain"),
            _sym("C2", kind=SymbolKind.CLASS, ns="pain"),
            _sym("user1", ns="user1"),
            _sym("user2", ns="user2"),
        ]
        edges = [
            _edge("user1.user1", "pain.C1"),
            _edge("user2.user2", "pain.C2"),
        ]
        g = _graph(syms, edges)
        findings = ZoneOfPainRule().check(g, HealthConfig())
        mc003 = [f for f in findings if f.rule_id == "MC003"]
        assert len(mc003) >= 1

    def test_mc005_cycle(self):
        from app.analysis.health_rules.coupling import ModuleCycleRule
        g = _graph(
            [_sym("a", ns="m1"), _sym("b", ns="m2")],
            [
                _edge("m1.a", "m2.b"),
                _edge("m2.b", "m1.a"),
            ],
        )
        findings = ModuleCycleRule().check(g, HealthConfig())
        assert len(findings) >= 1
        assert findings[0].rule_id == "MC005"


# =======================================================================
# API tests
# =======================================================================


class TestCouplingAPI:

    @pytest_asyncio.fixture(autouse=True)
    async def setup(self):
        await drop_tables()
        await create_tables()
        async for db in override_get_db():
            db.add(Repo(id="r1", name="demo", url="https://example.com"))
            db.add(RepoSnapshot(
                id="s1", repo_id="r1", commit_sha="abc",
                status=SnapshotStatus.completed, file_count=3,
            ))
            db.add(Symbol(
                snapshot_id="s1", name="handler", kind="method",
                fq_name="api.handler", file_path="api/handler.py",
                start_line=1, end_line=10, namespace="api",
            ))
            db.add(Symbol(
                snapshot_id="s1", name="service", kind="method",
                fq_name="core.service", file_path="core/service.py",
                start_line=1, end_line=10, namespace="core",
            ))
            db.add(Symbol(
                snapshot_id="s1", name="repo", kind="method",
                fq_name="data.repo", file_path="data/repo.py",
                start_line=1, end_line=10, namespace="data",
            ))
            db.add(Edge(
                snapshot_id="s1",
                source_fq_name="api.handler",
                target_fq_name="core.service",
                edge_type="calls", file_path="api/handler.py",
            ))
            db.add(Edge(
                snapshot_id="s1",
                source_fq_name="core.service",
                target_fq_name="data.repo",
                edge_type="calls", file_path="core/service.py",
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
    async def test_coupling_endpoint(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/coupling")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_modules"] >= 3
        assert len(data["modules"]) >= 3

    @pytest.mark.asyncio
    async def test_module_fields(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/coupling")
        m = resp.json()["modules"][0]
        for field in [
            "name", "symbol_count", "afferent_coupling",
            "efferent_coupling", "instability", "abstractness",
            "distance", "cohesion", "depends_on", "depended_by",
        ]:
            assert field in m

    @pytest.mark.asyncio
    async def test_averages(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/coupling")
        data = resp.json()
        assert "avg_instability" in data
        assert "avg_cohesion" in data
        assert "avg_distance" in data

    @pytest.mark.asyncio
    async def test_dependency_chain(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/coupling")
        mods = {m["name"]: m for m in resp.json()["modules"]}
        assert "core" in mods["api"]["depends_on"]
        assert "data" in mods["core"]["depends_on"]

    @pytest.mark.asyncio
    async def test_empty_snapshot(self, client):
        async for db in override_get_db():
            db.add(RepoSnapshot(
                id="s2", repo_id="r1", commit_sha="def",
                status=SnapshotStatus.completed, file_count=0,
            ))
            await db.commit()
        resp = await client.get("/repos/r1/snapshots/s2/coupling")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_modules"] == 0


# =======================================================================
# Edge cases
# =======================================================================


class TestCouplingEdgeCases:

    def test_single_module(self):
        g = _graph(
            [_sym("a", ns="only"), _sym("b", ns="only")],
            [_edge("only.a", "only.b")],
        )
        r = analyze_coupling(g)
        assert r.total_modules == 1
        assert r.modules[0].cohesion == 1.0

    def test_self_referencing_module(self):
        g = _graph(
            [_sym("a", ns="m"), _sym("b", ns="m")],
            [
                _edge("m.a", "m.b"),
                _edge("m.b", "m.a"),
            ],
        )
        r = analyze_coupling(g)
        assert r.modules[0].intra_edges == 2

    def test_many_modules_performance(self):
        syms = [_sym(f"f{i}", ns=f"m{i}") for i in range(100)]
        edges = [_edge(f"m{i}.f{i}", f"m{i+1}.f{i+1}") for i in range(99)]
        g = _graph(syms, edges)
        r = analyze_coupling(g)
        assert r.total_modules == 100
