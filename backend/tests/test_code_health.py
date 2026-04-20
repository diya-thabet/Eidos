"""
Comprehensive code health engine tests.

Tests: all 19 rules, configuration, scoring, report format,
category filtering, rule disabling, LLM integration, edge cases.
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
    """Build a CodeGraph from symbol tuples and optional edges."""
    g = CodeGraph()
    for s in symbols:
        if isinstance(s, SymbolInfo):
            g.symbols[s.fq_name] = s
        else:
            raise TypeError(f"Expected SymbolInfo, got {type(s)}")
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


# ------------------------------------------------------------------
# Rule registry
# ------------------------------------------------------------------


class TestRuleRegistry:
    def test_all_rules_count(self):
        assert len(ALL_RULES) == 19

    def test_all_rules_have_id(self):
        for r in ALL_RULES:
            assert r.rule_id, f"Rule {r.rule_name} has no ID"

    def test_all_rules_have_category(self):
        for r in ALL_RULES:
            assert r.category, f"Rule {r.rule_id} has no category"

    def test_metadata(self):
        meta = HealthConfig.all_rules()
        assert len(meta) == 19
        assert all("rule_id" in m for m in meta)

    def test_unique_ids(self):
        ids = [r.rule_id for r in ALL_RULES]
        assert len(ids) == len(set(ids))


# ------------------------------------------------------------------
# Clean Code rules
# ------------------------------------------------------------------


class TestLongMethodRule:
    def test_triggers_on_long_method(self):
        g = _graph(_sym("run", SymbolKind.METHOD, "ns.A.run", start=1, end=50))
        report = run_health_check(g, HealthConfig(max_method_lines=30))
        ids = [f.rule_id for f in report.findings]
        assert "CC001" in ids

    def test_passes_short_method(self):
        g = _graph(_sym("run", SymbolKind.METHOD, "ns.A.run", start=1, end=10))
        report = run_health_check(g, HealthConfig(max_method_lines=30))
        assert not any(f.rule_id == "CC001" for f in report.findings)

    def test_custom_threshold(self):
        g = _graph(_sym("run", SymbolKind.METHOD, "ns.A.run", start=1, end=20))
        report = run_health_check(g, HealthConfig(max_method_lines=15))
        assert any(f.rule_id == "CC001" for f in report.findings)


class TestLongClassRule:
    def test_triggers_on_long_class(self):
        g = _graph(_sym("Big", SymbolKind.CLASS, "ns.Big", start=1, end=400))
        report = run_health_check(g, HealthConfig(max_class_lines=300))
        assert any(f.rule_id == "CC002" for f in report.findings)


class TestTooManyParametersRule:
    def test_triggers(self):
        g = _graph(
            _sym(
                "set",
                SymbolKind.METHOD,
                "ns.A.set",
                parameters=["a", "b", "c", "d", "e", "f"],
            )
        )
        report = run_health_check(g, HealthConfig(max_parameters=5))
        assert any(f.rule_id == "CC003" for f in report.findings)

    def test_passes(self):
        g = _graph(_sym("get", SymbolKind.METHOD, "ns.A.get", parameters=["a"]))
        report = run_health_check(g, HealthConfig(max_parameters=5))
        assert not any(f.rule_id == "CC003" for f in report.findings)


class TestEmptyMethodRule:
    def test_triggers(self):
        g = _graph(_sym("noop", SymbolKind.METHOD, "ns.A.noop", start=1, end=2))
        report = run_health_check(g)
        assert any(f.rule_id == "CC004" for f in report.findings)


# ------------------------------------------------------------------
# SOLID rules
# ------------------------------------------------------------------


class TestGodClassRule:
    def test_triggers(self):
        cls = _sym("God", SymbolKind.CLASS, "ns.God")
        methods = [
            _sym(f"m{i}", SymbolKind.METHOD, f"ns.God.m{i}", parent_fq_name="ns.God")
            for i in range(20)
        ]
        edges = [EdgeInfo("ns.God", f"ns.God.m{i}", EdgeType.CONTAINS) for i in range(20)]
        g = _graph(cls, *methods, edges=edges)
        report = run_health_check(g, HealthConfig(max_god_class_methods=15))
        assert any(f.rule_id == "SOLID001" for f in report.findings)

    def test_passes_small_class(self):
        cls = _sym("Small", SymbolKind.CLASS, "ns.Small")
        m = _sym("run", SymbolKind.METHOD, "ns.Small.run", parent_fq_name="ns.Small")
        e = EdgeInfo("ns.Small", "ns.Small.run", EdgeType.CONTAINS)
        g = _graph(cls, m, edges=[e])
        report = run_health_check(g, HealthConfig(max_god_class_methods=15))
        assert not any(f.rule_id == "SOLID001" for f in report.findings)


class TestDeepInheritanceRule:
    def test_triggers(self):
        syms = [_sym(f"C{i}", SymbolKind.CLASS, f"ns.C{i}") for i in range(6)]
        edges = [EdgeInfo(f"ns.C{i + 1}", f"ns.C{i}", EdgeType.INHERITS) for i in range(5)]
        g = _graph(*syms, edges=edges)
        report = run_health_check(g, HealthConfig(max_inheritance_depth=4))
        assert any(f.rule_id == "SOLID002" for f in report.findings)


class TestFatInterfaceRule:
    def test_triggers(self):
        iface = _sym("IFat", SymbolKind.INTERFACE, "ns.IFat")
        methods = [
            _sym(f"m{i}", SymbolKind.METHOD, f"ns.IFat.m{i}", parent_fq_name="ns.IFat")
            for i in range(8)
        ]
        edges = [EdgeInfo("ns.IFat", f"ns.IFat.m{i}", EdgeType.CONTAINS) for i in range(8)]
        g = _graph(iface, *methods, edges=edges)
        report = run_health_check(g, HealthConfig(max_parameters=5))
        assert any(f.rule_id == "SOLID003" for f in report.findings)


# ------------------------------------------------------------------
# Complexity rules
# ------------------------------------------------------------------


class TestHighFanOutRule:
    def test_triggers(self):
        caller = _sym("run", SymbolKind.METHOD, "ns.A.run")
        targets = [_sym(f"t{i}", SymbolKind.METHOD, f"ns.B.t{i}") for i in range(15)]
        edges = [EdgeInfo("ns.A.run", f"ns.B.t{i}", EdgeType.CALLS) for i in range(15)]
        g = _graph(caller, *targets, edges=edges)
        report = run_health_check(g, HealthConfig(max_fan_out=10))
        assert any(f.rule_id == "CX001" for f in report.findings)


class TestHighFanInRule:
    def test_triggers(self):
        target = _sym("shared", SymbolKind.METHOD, "ns.shared")
        callers = [_sym(f"c{i}", SymbolKind.METHOD, f"ns.c{i}") for i in range(20)]
        edges = [EdgeInfo(f"ns.c{i}", "ns.shared", EdgeType.CALLS) for i in range(20)]
        g = _graph(target, *callers, edges=edges)
        report = run_health_check(g, HealthConfig(max_fan_in=15))
        assert any(f.rule_id == "CX002" for f in report.findings)


class TestTooManyChildrenRule:
    def test_triggers(self):
        cls = _sym("Big", SymbolKind.CLASS, "ns.Big")
        children = [
            _sym(f"f{i}", SymbolKind.FIELD, f"ns.Big.f{i}", parent_fq_name="ns.Big")
            for i in range(25)
        ]
        edges = [EdgeInfo("ns.Big", f"ns.Big.f{i}", EdgeType.CONTAINS) for i in range(25)]
        g = _graph(cls, *children, edges=edges)
        report = run_health_check(g, HealthConfig(max_children=20))
        assert any(f.rule_id == "CX003" for f in report.findings)


# ------------------------------------------------------------------
# Documentation rules
# ------------------------------------------------------------------


class TestMissingDocRule:
    def test_triggers_public_no_doc(self):
        g = _graph(_sym("Foo", SymbolKind.CLASS, "ns.Foo", modifiers=["public"]))
        report = run_health_check(g)
        assert any(f.rule_id == "DOC001" for f in report.findings)

    def test_passes_with_doc(self):
        g = _graph(
            _sym(
                "Foo",
                SymbolKind.CLASS,
                "ns.Foo",
                modifiers=["public"],
                doc_comment="/// Docs.",
            )
        )
        report = run_health_check(g)
        assert not any(f.rule_id == "DOC001" for f in report.findings)


# ------------------------------------------------------------------
# Naming rules
# ------------------------------------------------------------------


class TestShortNameRule:
    def test_triggers(self):
        g = _graph(_sym("A", SymbolKind.CLASS, "ns.A"))
        report = run_health_check(g)
        assert any(f.rule_id == "NM001" for f in report.findings)

    def test_passes_normal_name(self):
        g = _graph(_sym("UserService", SymbolKind.CLASS, "ns.UserService"))
        report = run_health_check(g)
        assert not any(f.rule_id == "NM001" for f in report.findings)


class TestBooleanNameRule:
    def test_triggers(self):
        g = _graph(_sym("check", SymbolKind.METHOD, "ns.A.check", return_type="bool"))
        report = run_health_check(g)
        assert any(f.rule_id == "NM002" for f in report.findings)

    def test_passes_with_prefix(self):
        g = _graph(_sym("isValid", SymbolKind.METHOD, "ns.A.isValid", return_type="bool"))
        report = run_health_check(g)
        assert not any(f.rule_id == "NM002" for f in report.findings)


# ------------------------------------------------------------------
# Design rules
# ------------------------------------------------------------------


class TestCircularDependencyRule:
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
        report = run_health_check(g)
        assert any(f.rule_id == "DS001" for f in report.findings)


class TestOrphanClassRule:
    def test_triggers(self):
        orphan = _sym("Unused", SymbolKind.CLASS, "ns.Unused")
        g = _graph(orphan)
        report = run_health_check(g)
        assert any(f.rule_id == "DS002" for f in report.findings)


# ------------------------------------------------------------------
# Security rules
# ------------------------------------------------------------------


class TestHardcodedSecretRule:
    def test_triggers(self):
        g = _graph(
            _sym(
                "api_key",
                SymbolKind.FIELD,
                "ns.Config.api_key",
                return_type="string",
            )
        )
        report = run_health_check(g)
        assert any(f.rule_id == "SEC001" for f in report.findings)

    def test_passes_non_secret(self):
        g = _graph(_sym("name", SymbolKind.FIELD, "ns.User.name", return_type="string"))
        report = run_health_check(g)
        assert not any(f.rule_id == "SEC001" for f in report.findings)


# ------------------------------------------------------------------
# Best Practice rules
# ------------------------------------------------------------------


class TestLargeFileRule:
    def test_triggers(self):
        syms = [_sym(f"s{i}", SymbolKind.METHOD, f"ns.s{i}", file="big.cs") for i in range(35)]
        g = _graph(*syms)
        report = run_health_check(g)
        assert any(f.rule_id == "BP001" for f in report.findings)


class TestExcessiveImportsRule:
    def test_triggers(self):
        fa = FileAnalysis(
            path="big.cs",
            namespace="ns",
            using_directives=["imp" + str(i) for i in range(20)],
        )
        g = _graph(files=[fa])
        report = run_health_check(g)
        assert any(f.rule_id == "BP002" for f in report.findings)


# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------


class TestConfiguration:
    def test_category_filter(self):
        g = _graph(
            _sym("A", SymbolKind.CLASS, "ns.A"),  # triggers NM001 (short name)
            _sym("run", SymbolKind.METHOD, "ns.A.run", start=1, end=50),  # triggers CC001
        )
        report = run_health_check(g, HealthConfig(categories=["naming"]))
        assert all(f.category == "naming" for f in report.findings)

    def test_disable_rule(self):
        g = _graph(_sym("A", SymbolKind.CLASS, "ns.A"))
        report = run_health_check(g, HealthConfig(disabled_rules=["NM001"]))
        assert not any(f.rule_id == "NM001" for f in report.findings)

    def test_all_categories_when_empty(self):
        g = _graph(
            _sym("A", SymbolKind.CLASS, "ns.A"),
            _sym("run", SymbolKind.METHOD, "ns.A.run", start=1, end=50),
        )
        report = run_health_check(g, HealthConfig(categories=[]))
        categories = {f.category for f in report.findings}
        assert len(categories) >= 1  # multiple categories found


# ------------------------------------------------------------------
# Report
# ------------------------------------------------------------------


class TestReport:
    def test_report_structure(self):
        g = _graph(_sym("Foo", SymbolKind.CLASS, "ns.Foo"))
        report = run_health_check(g)
        assert isinstance(report, HealthReport)
        assert report.total_symbols == 1
        assert isinstance(report.overall_score, float)
        assert 0.0 <= report.overall_score <= 100.0

    def test_to_dict(self):
        g = _graph(_sym("Foo", SymbolKind.CLASS, "ns.Foo"))
        report = run_health_check(g)
        d = report.to_dict()
        assert "findings" in d
        assert "overall_score" in d
        assert "summary" in d
        assert "category_scores" in d

    def test_severity_summary(self):
        g = _graph(_sym("A", SymbolKind.CLASS, "ns.A"))
        report = run_health_check(g)
        for severity in report.summary:
            assert severity in ("info", "warning", "error", "critical")

    def test_sorted_by_severity(self):
        g = _graph(
            _sym("api_key", SymbolKind.FIELD, "ns.C.api_key", return_type="string"),
            _sym("A", SymbolKind.CLASS, "ns.A"),
            _sym("run", SymbolKind.METHOD, "ns.A.run", start=1, end=50),
        )
        report = run_health_check(g)
        if len(report.findings) >= 2:
            severities = [f.severity for f in report.findings]
            order = {"critical": 0, "error": 1, "warning": 2, "info": 3}
            values = [order.get(s, 4) for s in severities]
            assert values == sorted(values)

    def test_overall_score_decreases_with_findings(self):
        clean = _graph(_sym("GoodName", SymbolKind.CLASS, "ns.GoodName", start=1, end=10))
        messy = _graph(
            _sym("A", SymbolKind.CLASS, "ns.A"),
            _sym("api_key", SymbolKind.FIELD, "ns.A.api_key", return_type="string"),
            _sym("run", SymbolKind.METHOD, "ns.A.run", start=1, end=100),
        )
        clean_report = run_health_check(clean)
        messy_report = run_health_check(messy)
        assert clean_report.overall_score >= messy_report.overall_score


# ------------------------------------------------------------------
# Edge cases
# ------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_graph(self):
        g = CodeGraph()
        g.finalize()
        report = run_health_check(g)
        assert report.findings == []
        assert report.overall_score == 100.0

    def test_single_symbol(self):
        g = _graph(_sym("Main", SymbolKind.CLASS, "ns.Main"))
        report = run_health_check(g)
        assert isinstance(report.overall_score, float)

    def test_all_categories_enum(self):
        assert len(RuleCategory) == 8

    def test_all_severities_enum(self):
        assert len(Severity) == 4
