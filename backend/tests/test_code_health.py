"""
Comprehensive code health engine tests.

Tests all 40 rules across 8 categories, configuration, scoring,
report format, category filtering, rule disabling, edge cases,
and boundary conditions.
"""

from app.analysis.code_health import (
    ALL_RULES,
    HealthConfig,
    HealthReport,
    RuleCategory,
    Severity,
    run_health_check,
)
from app.analysis.graph_builder import CodeGraph
from app.analysis.models import EdgeInfo, EdgeType, FileAnalysis, SymbolInfo, SymbolKind


def _graph(*symbols, edges=None, files=None):
    g = CodeGraph()
    for s in symbols:
        g.symbols[s.fq_name] = s
    if edges:
        g.edges.extend(edges)
    if files:
        for f in files:
            g.files[f.path] = f
    g.finalize()
    return g


def _sym(
    name="Foo",
    kind=SymbolKind.CLASS,
    fq="ns.Foo",
    file="test.cs",
    start=1,
    end=10,
    **kwargs,
):
    return SymbolInfo(
        name=name,
        kind=kind,
        fq_name=fq,
        file_path=file,
        start_line=start,
        end_line=end,
        **kwargs,
    )


def _find(report, rule_id):
    return [f for f in report.findings if f.rule_id == rule_id]


# ==================================================================
# Rule Registry
# ==================================================================


class TestRuleRegistry:
    def test_total_rule_count(self):
        assert len(ALL_RULES) == 58

    def test_all_have_id(self):
        for r in ALL_RULES:
            assert r.rule_id

    def test_all_have_category(self):
        for r in ALL_RULES:
            assert r.category

    def test_all_have_name(self):
        for r in ALL_RULES:
            assert r.rule_name

    def test_all_have_description(self):
        for r in ALL_RULES:
            assert r.description

    def test_unique_ids(self):
        ids = [r.rule_id for r in ALL_RULES]
        assert len(ids) == len(set(ids))

    def test_unique_names(self):
        names = [r.rule_name for r in ALL_RULES]
        assert len(names) == len(set(names))

    def test_metadata_returns_all(self):
        meta = HealthConfig.all_rules()
        assert len(meta) == 58
        assert all("rule_id" in m and "description" in m for m in meta)


# ==================================================================
# CC001 - Long Method
# ==================================================================


class TestCC001LongMethod:
    def test_triggers(self):
        g = _graph(_sym("run", SymbolKind.METHOD, "ns.A.run", start=1, end=50))
        assert _find(run_health_check(g, HealthConfig(max_method_lines=30)), "CC001")

    def test_passes_short(self):
        g = _graph(_sym("run", SymbolKind.METHOD, "ns.A.run", start=1, end=10))
        assert not _find(run_health_check(g, HealthConfig(max_method_lines=30)), "CC001")

    def test_exact_threshold(self):
        g = _graph(_sym("run", SymbolKind.METHOD, "ns.A.run", start=1, end=30))
        assert not _find(run_health_check(g, HealthConfig(max_method_lines=30)), "CC001")

    def test_custom_threshold(self):
        g = _graph(_sym("run", SymbolKind.METHOD, "ns.A.run", start=1, end=20))
        assert _find(run_health_check(g, HealthConfig(max_method_lines=15)), "CC001")

    def test_ignores_class(self):
        g = _graph(_sym("Big", SymbolKind.CLASS, "ns.Big", start=1, end=500))
        assert not _find(run_health_check(g), "CC001")


# ==================================================================
# CC002 - Long Class
# ==================================================================


class TestCC002LongClass:
    def test_triggers(self):
        g = _graph(_sym("Big", SymbolKind.CLASS, "ns.Big", start=1, end=400))
        assert _find(run_health_check(g, HealthConfig(max_class_lines=300)), "CC002")

    def test_passes(self):
        g = _graph(_sym("Small", SymbolKind.CLASS, "ns.Small", start=1, end=50))
        assert not _find(run_health_check(g), "CC002")


# ==================================================================
# CC003 - Too Many Parameters
# ==================================================================


class TestCC003TooManyParams:
    def test_triggers(self):
        g = _graph(_sym("set", SymbolKind.METHOD, "ns.A.set", parameters=list("abcdef")))
        assert _find(run_health_check(g, HealthConfig(max_parameters=5)), "CC003")

    def test_passes(self):
        g = _graph(_sym("get", SymbolKind.METHOD, "ns.A.get", parameters=["a"]))
        assert not _find(run_health_check(g), "CC003")

    def test_constructor_params(self):
        g = _graph(_sym("Foo", SymbolKind.CONSTRUCTOR, "ns.Foo.Foo", parameters=list("abcdefgh")))
        assert _find(run_health_check(g, HealthConfig(max_parameters=5)), "CC003")


# ==================================================================
# CC004 - Empty Method
# ==================================================================


class TestCC004EmptyMethod:
    def test_triggers(self):
        g = _graph(_sym("noop", SymbolKind.METHOD, "ns.A.noop", start=1, end=2))
        assert _find(run_health_check(g), "CC004")

    def test_passes(self):
        g = _graph(_sym("run", SymbolKind.METHOD, "ns.A.run", start=1, end=15))
        assert not _find(run_health_check(g), "CC004")


# ==================================================================
# CC005 - Constructor Over-injection
# ==================================================================


class TestCC005ConstructorOverInjection:
    def test_triggers(self):
        g = _graph(_sym("Svc", SymbolKind.CONSTRUCTOR, "ns.Svc.Svc", parameters=list("abcde")))
        assert _find(run_health_check(g), "CC005")

    def test_passes(self):
        g = _graph(_sym("Svc", SymbolKind.CONSTRUCTOR, "ns.Svc.Svc", parameters=["a", "b"]))
        assert not _find(run_health_check(g), "CC005")


# ==================================================================
# CC006 - Void Abuse
# ==================================================================


class TestCC006VoidAbuse:
    def test_triggers(self):
        cls = _sym("Svc", SymbolKind.CLASS, "ns.Svc")
        methods = [
            _sym(
                f"m{i}",
                SymbolKind.METHOD,
                f"ns.Svc.m{i}",
                parent_fq_name="ns.Svc",
                return_type="void",
            )
            for i in range(5)
        ]
        edges = [EdgeInfo("ns.Svc", f"ns.Svc.m{i}", EdgeType.CONTAINS) for i in range(5)]
        g = _graph(cls, *methods, edges=edges)
        assert _find(run_health_check(g), "CC006")

    def test_passes_mixed(self):
        cls = _sym("Svc", SymbolKind.CLASS, "ns.Svc")
        m1 = _sym("a", SymbolKind.METHOD, "ns.Svc.a", parent_fq_name="ns.Svc", return_type="void")
        m2 = _sym("b", SymbolKind.METHOD, "ns.Svc.b", parent_fq_name="ns.Svc", return_type="int")
        m3 = _sym("c", SymbolKind.METHOD, "ns.Svc.c", parent_fq_name="ns.Svc", return_type="str")
        m4 = _sym("d", SymbolKind.METHOD, "ns.Svc.d", parent_fq_name="ns.Svc", return_type="bool")
        edges = [EdgeInfo("ns.Svc", f"ns.Svc.{n}", EdgeType.CONTAINS) for n in "abcd"]
        g = _graph(cls, m1, m2, m3, m4, edges=edges)
        assert not _find(run_health_check(g), "CC006")


# ==================================================================
# CC007 - Static Abuse
# ==================================================================


class TestCC007StaticAbuse:
    def test_triggers(self):
        cls = _sym("Utils", SymbolKind.CLASS, "ns.Utils")
        methods = [
            _sym(
                f"m{i}",
                SymbolKind.METHOD,
                f"ns.Utils.m{i}",
                parent_fq_name="ns.Utils",
                modifiers=["static"],
            )
            for i in range(5)
        ]
        edges = [EdgeInfo("ns.Utils", f"ns.Utils.m{i}", EdgeType.CONTAINS) for i in range(5)]
        g = _graph(cls, *methods, edges=edges)
        assert _find(run_health_check(g), "CC007")


# ==================================================================
# CC008 - Mutable Public State
# ==================================================================


class TestCC008MutablePublicState:
    def test_triggers(self):
        cls = _sym("Cfg", SymbolKind.CLASS, "ns.Cfg")
        fields = [
            _sym(
                f"f{i}",
                SymbolKind.FIELD,
                f"ns.Cfg.f{i}",
                parent_fq_name="ns.Cfg",
                modifiers=["public"],
            )
            for i in range(6)
        ]
        edges = [EdgeInfo("ns.Cfg", f"ns.Cfg.f{i}", EdgeType.CONTAINS) for i in range(6)]
        g = _graph(cls, *fields, edges=edges)
        assert _find(run_health_check(g), "CC008")

    def test_passes_private(self):
        cls = _sym("Cfg", SymbolKind.CLASS, "ns.Cfg")
        fields = [
            _sym(
                f"f{i}",
                SymbolKind.FIELD,
                f"ns.Cfg.f{i}",
                parent_fq_name="ns.Cfg",
                modifiers=["private"],
            )
            for i in range(6)
        ]
        edges = [EdgeInfo("ns.Cfg", f"ns.Cfg.f{i}", EdgeType.CONTAINS) for i in range(6)]
        g = _graph(cls, *fields, edges=edges)
        assert not _find(run_health_check(g), "CC008")


# ==================================================================
# SOLID001 - God Class
# ==================================================================


class TestSOLID001GodClass:
    def test_triggers(self):
        cls = _sym("God", SymbolKind.CLASS, "ns.God")
        methods = [
            _sym(f"m{i}", SymbolKind.METHOD, f"ns.God.m{i}", parent_fq_name="ns.God")
            for i in range(20)
        ]
        edges = [EdgeInfo("ns.God", f"ns.God.m{i}", EdgeType.CONTAINS) for i in range(20)]
        g = _graph(cls, *methods, edges=edges)
        assert _find(run_health_check(g, HealthConfig(max_god_class_methods=15)), "SOLID001")

    def test_passes(self):
        cls = _sym("Small", SymbolKind.CLASS, "ns.Small")
        m = _sym("run", SymbolKind.METHOD, "ns.Small.run", parent_fq_name="ns.Small")
        e = EdgeInfo("ns.Small", "ns.Small.run", EdgeType.CONTAINS)
        g = _graph(cls, m, edges=[e])
        assert not _find(run_health_check(g), "SOLID001")


# ==================================================================
# SOLID002 - Deep Inheritance
# ==================================================================


class TestSOLID002DeepInheritance:
    def test_triggers(self):
        syms = [_sym(f"C{i}", SymbolKind.CLASS, f"ns.C{i}") for i in range(6)]
        edges = [EdgeInfo(f"ns.C{i + 1}", f"ns.C{i}", EdgeType.INHERITS) for i in range(5)]
        g = _graph(*syms, edges=edges)
        assert _find(run_health_check(g, HealthConfig(max_inheritance_depth=4)), "SOLID002")

    def test_passes_shallow(self):
        syms = [_sym(f"C{i}", SymbolKind.CLASS, f"ns.C{i}") for i in range(3)]
        edges = [EdgeInfo(f"ns.C{i + 1}", f"ns.C{i}", EdgeType.INHERITS) for i in range(2)]
        g = _graph(*syms, edges=edges)
        assert not _find(run_health_check(g), "SOLID002")


# ==================================================================
# SOLID003 - Fat Interface
# ==================================================================


class TestSOLID003FatInterface:
    def test_triggers(self):
        iface = _sym("IFat", SymbolKind.INTERFACE, "ns.IFat")
        methods = [
            _sym(f"m{i}", SymbolKind.METHOD, f"ns.IFat.m{i}", parent_fq_name="ns.IFat")
            for i in range(8)
        ]
        edges = [EdgeInfo("ns.IFat", f"ns.IFat.m{i}", EdgeType.CONTAINS) for i in range(8)]
        g = _graph(iface, *methods, edges=edges)
        assert _find(run_health_check(g, HealthConfig(max_parameters=5)), "SOLID003")


# ==================================================================
# AR003 - Swiss Army Knife
# ==================================================================


class TestAR003SwissArmyKnife:
    def test_triggers(self):
        cls = _sym("Multi", SymbolKind.CLASS, "ns.Multi")
        edges = [EdgeInfo("ns.Multi", f"ns.IFace{i}", EdgeType.IMPLEMENTS) for i in range(5)]
        g = _graph(cls, edges=edges)
        assert _find(run_health_check(g), "AR003")


# ==================================================================
# CX001-003, MT001-003 - Complexity/Metrics
# ==================================================================


class TestCX001HighFanOut:
    def test_triggers(self):
        caller = _sym("run", SymbolKind.METHOD, "ns.A.run")
        targets = [_sym(f"t{i}", SymbolKind.METHOD, f"ns.B.t{i}") for i in range(15)]
        edges = [EdgeInfo("ns.A.run", f"ns.B.t{i}", EdgeType.CALLS) for i in range(15)]
        g = _graph(caller, *targets, edges=edges)
        assert _find(run_health_check(g, HealthConfig(max_fan_out=10)), "CX001")


class TestCX002HighFanIn:
    def test_triggers(self):
        target = _sym("shared", SymbolKind.METHOD, "ns.shared")
        callers = [_sym(f"c{i}", SymbolKind.METHOD, f"ns.c{i}") for i in range(20)]
        edges = [EdgeInfo(f"ns.c{i}", "ns.shared", EdgeType.CALLS) for i in range(20)]
        g = _graph(target, *callers, edges=edges)
        assert _find(run_health_check(g, HealthConfig(max_fan_in=15)), "CX002")


class TestCX003TooManyChildren:
    def test_triggers(self):
        cls = _sym("Big", SymbolKind.CLASS, "ns.Big")
        children = [
            _sym(f"f{i}", SymbolKind.FIELD, f"ns.Big.f{i}", parent_fq_name="ns.Big")
            for i in range(25)
        ]
        edges = [EdgeInfo("ns.Big", f"ns.Big.f{i}", EdgeType.CONTAINS) for i in range(25)]
        g = _graph(cls, *children, edges=edges)
        assert _find(run_health_check(g, HealthConfig(max_children=20)), "CX003")


class TestMT001Coupling:
    def test_triggers(self):
        cls_a = _sym("A", SymbolKind.CLASS, "ns.A")
        m = _sym("run", SymbolKind.METHOD, "ns.A.run", parent_fq_name="ns.A")
        targets = [
            _sym(f"t{i}", SymbolKind.METHOD, f"ns.Cls{i}.t{i}", parent_fq_name=f"ns.Cls{i}")
            for i in range(15)
        ]
        edges = [
            EdgeInfo("ns.A", "ns.A.run", EdgeType.CONTAINS),
            *[EdgeInfo("ns.A.run", f"ns.Cls{i}.t{i}", EdgeType.CALLS) for i in range(15)],
        ]
        g = _graph(cls_a, m, *targets, edges=edges)
        assert _find(run_health_check(g, HealthConfig(max_fan_out=10)), "MT001")


class TestMT002LowCohesion:
    def test_triggers_disjoint_methods(self):
        cls = _sym("Incoherent", SymbolKind.CLASS, "ns.X")
        methods = [
            _sym(f"m{i}", SymbolKind.METHOD, f"ns.X.m{i}", parent_fq_name="ns.X") for i in range(5)
        ]
        targets = [_sym(f"ext{i}", SymbolKind.METHOD, f"ns.Ext.e{i}") for i in range(5)]
        edges = [
            *[EdgeInfo("ns.X", f"ns.X.m{i}", EdgeType.CONTAINS) for i in range(5)],
            *[EdgeInfo(f"ns.X.m{i}", f"ns.Ext.e{i}", EdgeType.CALLS) for i in range(5)],
        ]
        g = _graph(cls, *methods, *targets, edges=edges)
        assert _find(run_health_check(g), "MT002")


class TestMT003ComplexityDensity:
    def test_triggers(self):
        m = _sym("dense", SymbolKind.METHOD, "ns.A.dense", start=1, end=8)
        targets = [_sym(f"t{i}", SymbolKind.METHOD, f"ns.B.t{i}") for i in range(6)]
        edges = [EdgeInfo("ns.A.dense", f"ns.B.t{i}", EdgeType.CALLS) for i in range(6)]
        g = _graph(m, *targets, edges=edges)
        assert _find(run_health_check(g), "MT003")


# ==================================================================
# DOC001 - Missing Doc
# ==================================================================


class TestDOC001MissingDoc:
    def test_triggers_public_no_doc(self):
        g = _graph(_sym("Foo", SymbolKind.CLASS, "ns.Foo", modifiers=["public"]))
        assert _find(run_health_check(g), "DOC001")

    def test_passes_with_doc(self):
        g = _graph(
            _sym("Foo", SymbolKind.CLASS, "ns.Foo", modifiers=["public"], doc_comment="/// Docs.")
        )
        assert not _find(run_health_check(g), "DOC001")

    def test_ignores_private(self):
        g = _graph(_sym("Foo", SymbolKind.CLASS, "ns.Foo", modifiers=["private"]))
        assert not _find(run_health_check(g), "DOC001")


# ==================================================================
# NM001-004 - Naming
# ==================================================================


class TestNM001ShortName:
    def test_triggers(self):
        g = _graph(_sym("A", SymbolKind.CLASS, "ns.A"))
        assert _find(run_health_check(g), "NM001")

    def test_passes(self):
        g = _graph(_sym("UserService", SymbolKind.CLASS, "ns.UserService"))
        assert not _find(run_health_check(g), "NM001")

    def test_skips_common_short_names(self):
        g = _graph(_sym("id", SymbolKind.METHOD, "ns.id"))
        assert not _find(run_health_check(g), "NM001")

    def test_skips_fields(self):
        g = _graph(_sym("x", SymbolKind.FIELD, "ns.P.x"))
        assert not _find(run_health_check(g), "NM001")


class TestNM002BooleanName:
    def test_triggers(self):
        g = _graph(_sym("check", SymbolKind.METHOD, "ns.A.check", return_type="bool"))
        assert _find(run_health_check(g), "NM002")

    def test_passes_with_prefix(self):
        g = _graph(_sym("isValid", SymbolKind.METHOD, "ns.A.isValid", return_type="bool"))
        assert not _find(run_health_check(g), "NM002")

    def test_passes_non_bool(self):
        g = _graph(_sym("check", SymbolKind.METHOD, "ns.A.check", return_type="int"))
        assert not _find(run_health_check(g), "NM002")


class TestNM003InconsistentNaming:
    def test_triggers(self):
        cls = _sym("X", SymbolKind.CLASS, "ns.X")
        members = [
            _sym("getData", SymbolKind.METHOD, "ns.X.getData", parent_fq_name="ns.X"),
            _sym("setData", SymbolKind.METHOD, "ns.X.setData", parent_fq_name="ns.X"),
            _sym("get_name", SymbolKind.METHOD, "ns.X.get_name", parent_fq_name="ns.X"),
            _sym("set_name", SymbolKind.METHOD, "ns.X.set_name", parent_fq_name="ns.X"),
        ]
        edges = [EdgeInfo("ns.X", m.fq_name, EdgeType.CONTAINS) for m in members]
        g = _graph(cls, *members, edges=edges)
        assert _find(run_health_check(g), "NM003")


class TestNM004HungarianNotation:
    def test_triggers(self):
        g = _graph(_sym("strName", SymbolKind.FIELD, "ns.A.strName"))
        assert _find(run_health_check(g), "NM004")

    def test_passes(self):
        g = _graph(_sym("name", SymbolKind.FIELD, "ns.A.name"))
        assert not _find(run_health_check(g), "NM004")


# ==================================================================
# DS001-002 - Design
# ==================================================================


class TestDS001CircularDependency:
    def test_triggers(self):
        a = _sym("A", SymbolKind.CLASS, "ns.A")
        b = _sym("B", SymbolKind.CLASS, "ns.B")
        ma = _sym("run", SymbolKind.METHOD, "ns.A.run", parent_fq_name="ns.A")
        mb = _sym("go", SymbolKind.METHOD, "ns.B.go", parent_fq_name="ns.B")
        edges = [
            EdgeInfo("ns.A.run", "ns.B.go", EdgeType.CALLS),
            EdgeInfo("ns.B.go", "ns.A.run", EdgeType.CALLS),
        ]
        g = _graph(a, b, ma, mb, edges=edges)
        assert _find(run_health_check(g), "DS001")


class TestDS002OrphanClass:
    def test_triggers(self):
        g = _graph(_sym("Unused", SymbolKind.CLASS, "ns.Unused"))
        assert _find(run_health_check(g), "DS002")

    def test_passes_if_referenced(self):
        cls = _sym("Used", SymbolKind.CLASS, "ns.Used")
        m = _sym("call", SymbolKind.METHOD, "ns.call")
        edge = EdgeInfo("ns.call", "ns.Used", EdgeType.CALLS)
        g = _graph(cls, m, edges=[edge])
        assert not _find(run_health_check(g), "DS002")


# ==================================================================
# SM001-007 - Code Smells
# ==================================================================


class TestSM001DeadMethod:
    def test_triggers(self):
        g = _graph(_sym("unused", SymbolKind.METHOD, "ns.A.unused"))
        assert _find(run_health_check(g), "SM001")

    def test_passes_if_called(self):
        m = _sym("used", SymbolKind.METHOD, "ns.A.used")
        caller = _sym("main", SymbolKind.METHOD, "ns.B.main")
        edge = EdgeInfo("ns.B.main", "ns.A.used", EdgeType.CALLS)
        g = _graph(m, caller, edges=[edge])
        assert not any(f.symbol_fq_name == "ns.A.used" for f in _find(run_health_check(g), "SM001"))

    def test_ignores_entry_points(self):
        g = _graph(_sym("main", SymbolKind.METHOD, "ns.main"))
        assert not _find(run_health_check(g), "SM001")

    def test_ignores_constructors(self):
        g = _graph(_sym("Foo", SymbolKind.CONSTRUCTOR, "ns.Foo.Foo"))
        assert not _find(run_health_check(g), "SM001")


class TestSM002FeatureEnvy:
    def test_triggers(self):
        cls_a = _sym("A", SymbolKind.CLASS, "ns.A")
        cls_b = _sym("B", SymbolKind.CLASS, "ns.B")
        m = _sym("envy", SymbolKind.METHOD, "ns.A.envy", parent_fq_name="ns.A")
        own = _sym("self_m", SymbolKind.METHOD, "ns.A.self_m", parent_fq_name="ns.A")
        foreign = [
            _sym(f"f{i}", SymbolKind.METHOD, f"ns.B.f{i}", parent_fq_name="ns.B") for i in range(4)
        ]
        edges = [
            EdgeInfo("ns.A.envy", "ns.A.self_m", EdgeType.CALLS),
            *[EdgeInfo("ns.A.envy", f"ns.B.f{i}", EdgeType.CALLS) for i in range(4)],
        ]
        g = _graph(cls_a, cls_b, m, own, *foreign, edges=edges)
        assert _find(run_health_check(g), "SM002")


class TestSM003DataClass:
    def test_triggers(self):
        cls = _sym("Dto", SymbolKind.CLASS, "ns.Dto")
        fields = [
            _sym(f"f{i}", SymbolKind.FIELD, f"ns.Dto.f{i}", parent_fq_name="ns.Dto")
            for i in range(5)
        ]
        m = _sym("ctor", SymbolKind.CONSTRUCTOR, "ns.Dto.ctor", parent_fq_name="ns.Dto")
        edges = [
            *[EdgeInfo("ns.Dto", f"ns.Dto.f{i}", EdgeType.CONTAINS) for i in range(5)],
            EdgeInfo("ns.Dto", "ns.Dto.ctor", EdgeType.CONTAINS),
        ]
        g = _graph(cls, *fields, m, edges=edges)
        assert _find(run_health_check(g), "SM003")


class TestSM004ShotgunSurgery:
    def test_triggers(self):
        target = _sym("shared", SymbolKind.METHOD, "ns.shared")
        callers = [
            _sym(f"c{i}", SymbolKind.METHOD, f"ns.Cls{i}.c{i}", parent_fq_name=f"ns.Cls{i}")
            for i in range(6)
        ]
        edges = [EdgeInfo(f"ns.Cls{i}.c{i}", "ns.shared", EdgeType.CALLS) for i in range(6)]
        g = _graph(target, *callers, edges=edges)
        assert _find(run_health_check(g), "SM004")


class TestSM005MiddleMan:
    def test_triggers(self):
        cls = _sym("Proxy", SymbolKind.CLASS, "ns.Proxy")
        target = _sym("Real", SymbolKind.CLASS, "ns.Real")
        methods = [
            _sym(f"m{i}", SymbolKind.METHOD, f"ns.Proxy.m{i}", parent_fq_name="ns.Proxy")
            for i in range(3)
        ]
        targets = [
            _sym(f"t{i}", SymbolKind.METHOD, f"ns.Real.t{i}", parent_fq_name="ns.Real")
            for i in range(3)
        ]
        edges = [
            *[EdgeInfo("ns.Proxy", f"ns.Proxy.m{i}", EdgeType.CONTAINS) for i in range(3)],
            *[EdgeInfo(f"ns.Proxy.m{i}", f"ns.Real.t{i}", EdgeType.CALLS) for i in range(3)],
        ]
        g = _graph(cls, target, *methods, *targets, edges=edges)
        assert _find(run_health_check(g), "SM005")


class TestSM006SpeculativeGenerality:
    def test_triggers_no_impl(self):
        iface = _sym("IEmpty", SymbolKind.INTERFACE, "ns.IEmpty")
        g = _graph(iface)
        assert _find(run_health_check(g), "SM006")

    def test_passes_multiple_impl(self):
        iface = _sym("IRepo", SymbolKind.INTERFACE, "ns.IRepo")
        edges = [
            EdgeInfo("ns.ImplA", "ns.IRepo", EdgeType.IMPLEMENTS),
            EdgeInfo("ns.ImplB", "ns.IRepo", EdgeType.IMPLEMENTS),
        ]
        g = _graph(iface, edges=edges)
        assert not _find(run_health_check(g), "SM006")


class TestSM007LazyClass:
    def test_triggers(self):
        cls = _sym("Lazy", SymbolKind.CLASS, "ns.Lazy")
        m = _sym("run", SymbolKind.METHOD, "ns.Lazy.run", parent_fq_name="ns.Lazy")
        edge = EdgeInfo("ns.Lazy", "ns.Lazy.run", EdgeType.CONTAINS)
        g = _graph(cls, m, edges=[edge])
        assert _find(run_health_check(g), "SM007")


# ==================================================================
# AR001-002 - Architecture
# ==================================================================


class TestAR001ModuleTangle:
    def test_triggers(self):
        a = _sym("a", SymbolKind.METHOD, "ns.A.a", namespace="modA")
        b = _sym("b", SymbolKind.METHOD, "ns.B.b", namespace="modB")
        edges = [
            EdgeInfo("ns.A.a", "ns.B.b", EdgeType.CALLS),
            EdgeInfo("ns.B.b", "ns.A.a", EdgeType.CALLS),
        ]
        g = _graph(a, b, edges=edges)
        assert _find(run_health_check(g), "AR001")


class TestAR002DeepNamespace:
    def test_triggers(self):
        g = _graph(_sym("X", SymbolKind.CLASS, "a.b.c.d.e.f.X", namespace="a.b.c.d.e.f"))
        assert _find(run_health_check(g), "AR002")

    def test_passes(self):
        g = _graph(_sym("X", SymbolKind.CLASS, "a.b.X", namespace="a.b"))
        assert not _find(run_health_check(g), "AR002")


# ==================================================================
# SEC001-003 - Security
# ==================================================================


class TestSEC001HardcodedSecret:
    def test_triggers(self):
        g = _graph(_sym("api_key", SymbolKind.FIELD, "ns.C.api_key", return_type="string"))
        assert _find(run_health_check(g), "SEC001")

    def test_passes(self):
        g = _graph(_sym("name", SymbolKind.FIELD, "ns.U.name", return_type="string"))
        assert not _find(run_health_check(g), "SEC001")


class TestSEC002SqlInjection:
    def test_triggers(self):
        g = _graph(_sym("execute_raw", SymbolKind.METHOD, "ns.Db.execute_raw"))
        assert _find(run_health_check(g), "SEC002")

    def test_passes(self):
        g = _graph(_sym("execute", SymbolKind.METHOD, "ns.Db.execute"))
        assert not _find(run_health_check(g), "SEC002")


class TestSEC003InsecureField:
    def test_triggers(self):
        g = _graph(_sym("password", SymbolKind.FIELD, "ns.U.password", modifiers=["public"]))
        assert _find(run_health_check(g), "SEC003")

    def test_passes_private(self):
        g = _graph(_sym("password", SymbolKind.FIELD, "ns.U.password", modifiers=["private"]))
        assert not _find(run_health_check(g), "SEC003")


# ==================================================================
# BP001-002 - Best Practices
# ==================================================================


class TestBP001LargeFile:
    def test_triggers(self):
        syms = [_sym(f"s{i}", SymbolKind.METHOD, f"ns.s{i}", file="big.cs") for i in range(35)]
        g = _graph(*syms)
        assert _find(run_health_check(g), "BP001")


class TestBP002ExcessiveImports:
    def test_triggers(self):
        fa = FileAnalysis(
            path="big.cs", namespace="ns", using_directives=[f"imp{i}" for i in range(20)]
        )
        g = _graph(files=[fa])
        assert _find(run_health_check(g), "BP002")


# ==================================================================
# Configuration
# ==================================================================


class TestConfiguration:
    def test_category_filter(self):
        g = _graph(
            _sym("A", SymbolKind.CLASS, "ns.A"),
            _sym("run", SymbolKind.METHOD, "ns.A.run", start=1, end=50),
        )
        report = run_health_check(g, HealthConfig(categories=["naming"]))
        assert all(f.category == "naming" for f in report.findings)

    def test_disable_rule(self):
        g = _graph(_sym("A", SymbolKind.CLASS, "ns.A"))
        report = run_health_check(g, HealthConfig(disabled_rules=["NM001"]))
        assert not _find(report, "NM001")

    def test_multiple_disabled(self):
        g = _graph(_sym("A", SymbolKind.CLASS, "ns.A"))
        report = run_health_check(g, HealthConfig(disabled_rules=["NM001", "DS002"]))
        assert not _find(report, "NM001")
        assert not _find(report, "DS002")

    def test_all_categories_when_empty(self):
        g = _graph(
            _sym("A", SymbolKind.CLASS, "ns.A"),
            _sym("run", SymbolKind.METHOD, "ns.A.run", start=1, end=50),
        )
        report = run_health_check(g, HealthConfig(categories=[]))
        categories = {f.category for f in report.findings}
        assert len(categories) >= 2

    def test_multiple_categories(self):
        g = _graph(
            _sym("api_key", SymbolKind.FIELD, "ns.C.api_key", return_type="string"),
            _sym("A", SymbolKind.CLASS, "ns.A"),
        )
        report = run_health_check(g, HealthConfig(categories=["security", "naming"]))
        cats = {f.category for f in report.findings}
        assert cats <= {"security", "naming"}


# ==================================================================
# Report
# ==================================================================


class TestReport:
    def test_structure(self):
        g = _graph(_sym("Foo", SymbolKind.CLASS, "ns.Foo"))
        report = run_health_check(g)
        assert isinstance(report, HealthReport)
        assert report.total_symbols == 1
        assert 0.0 <= report.overall_score <= 100.0

    def test_to_dict(self):
        g = _graph(_sym("Foo", SymbolKind.CLASS, "ns.Foo"))
        d = run_health_check(g).to_dict()
        assert "findings" in d
        assert "overall_score" in d
        assert "summary" in d
        assert "category_scores" in d
        assert "llm_insights" in d
        assert "findings_count" in d

    def test_severity_summary_values(self):
        g = _graph(_sym("A", SymbolKind.CLASS, "ns.A"))
        for sev in run_health_check(g).summary:
            assert sev in ("info", "warning", "error", "critical")

    def test_sorted_by_severity(self):
        g = _graph(
            _sym("api_key", SymbolKind.FIELD, "ns.C.api_key", return_type="string"),
            _sym("A", SymbolKind.CLASS, "ns.A"),
            _sym("run", SymbolKind.METHOD, "ns.A.run", start=1, end=50),
        )
        report = run_health_check(g)
        if len(report.findings) >= 2:
            order = {"critical": 0, "error": 1, "warning": 2, "info": 3}
            values = [order.get(f.severity, 4) for f in report.findings]
            assert values == sorted(values)

    def test_score_decreases_with_findings(self):
        clean = _graph(_sym("GoodName", SymbolKind.CLASS, "ns.GoodName", start=1, end=10))
        messy = _graph(
            _sym("A", SymbolKind.CLASS, "ns.A"),
            _sym("api_key", SymbolKind.FIELD, "ns.A.api_key", return_type="string"),
            _sym("run", SymbolKind.METHOD, "ns.A.run", start=1, end=100),
        )
        assert run_health_check(clean).overall_score >= run_health_check(messy).overall_score

    def test_finding_fields(self):
        g = _graph(_sym("A", SymbolKind.CLASS, "ns.A"))
        report = run_health_check(g)
        for f in report.findings:
            assert f.rule_id
            assert f.rule_name
            assert f.category
            assert f.severity
            assert f.message


# ==================================================================
# Edge Cases
# ==================================================================


class TestEdgeCases:
    def test_empty_graph(self):
        g = CodeGraph()
        g.finalize()
        report = run_health_check(g)
        assert report.findings == []
        assert report.overall_score == 100.0

    def test_single_symbol(self):
        g = _graph(_sym("Main", SymbolKind.CLASS, "ns.Main"))
        assert isinstance(run_health_check(g).overall_score, float)

    def test_all_categories_enum(self):
        assert len(RuleCategory) == 8

    def test_all_severities_enum(self):
        assert len(Severity) == 4

    def test_no_crash_on_missing_parent(self):
        g = _graph(_sym("orphan", SymbolKind.METHOD, "ns.orphan", parent_fq_name="ns.Missing"))
        run_health_check(g)  # should not crash

    def test_graph_with_only_edges(self):
        g = CodeGraph()
        g.edges.append(EdgeInfo("a", "b", EdgeType.CALLS))
        g.finalize()
        run_health_check(g)  # should not crash

    def test_very_large_graph(self):
        syms = [
            _sym(f"m{i}", SymbolKind.METHOD, f"ns.C.m{i}", parent_fq_name="ns.C")
            for i in range(100)
        ]
        cls = _sym("C", SymbolKind.CLASS, "ns.C")
        edges = [EdgeInfo("ns.C", f"ns.C.m{i}", EdgeType.CONTAINS) for i in range(100)]
        g = _graph(cls, *syms, edges=edges)
        report = run_health_check(g)
        assert report.total_symbols > 0
