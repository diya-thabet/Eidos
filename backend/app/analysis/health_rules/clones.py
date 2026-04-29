"""
Health rules: duplicate / clone detection.

Uses AST structural fingerprinting to find copy-pasted code.
"""

from __future__ import annotations

from app.analysis.clone_detection import (
    MIN_FUNC_LINES,
    CloneInfo,
    detect_clones,
)
from app.analysis.code_health import (
    HealthConfig,
    HealthFinding,
    HealthRule,
    RuleCategory,
    Severity,
)
from app.analysis.graph_builder import CodeGraph
from app.analysis.models import SymbolKind

__all__ = [
    "ExactCloneRule",
    "NearCloneRule",
    "CloneClusterRule",
]


def _build_clone_data(graph: CodeGraph) -> list[CloneInfo]:
    """Extract clone info from the graph (no AST re-parsing needed for health rules)."""
    functions: list[CloneInfo] = []
    for sym in graph.symbols.values():
        if sym.kind not in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR):
            continue
        lines = sym.end_line - sym.start_line + 1
        if lines < MIN_FUNC_LINES:
            continue
        fp = getattr(sym, "_structural_fingerprint", "")
        if not fp:
            continue
        functions.append(CloneInfo(
            fq_name=sym.fq_name,
            name=sym.name,
            file_path=sym.file_path,
            start_line=sym.start_line,
            end_line=sym.end_line,
            lines=lines,
            fingerprint=fp,
        ))
    return functions


class ExactCloneRule(HealthRule):
    rule_id = "DUP001"
    rule_name = "exact_clone"
    category = RuleCategory.DESIGN
    severity = Severity.WARNING
    description = "Function is an exact structural clone of another"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        functions = _build_clone_data(graph)
        report = detect_clones(functions)
        findings: list[HealthFinding] = []
        for grp in report.exact_clone_groups:
            names = [m.name for m in grp.members]
            for m in grp.members:
                others = [n for n in names if n != m.name]
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=m.fq_name,
                        file_path=m.file_path,
                        line=m.start_line,
                        message=(
                            f"Exact clone of: {', '.join(others[:3])}"
                            if others else "Exact clone detected"
                        ),
                        suggestion="Extract shared logic into a common function",
                    )
                )
        return findings


class NearCloneRule(HealthRule):
    rule_id = "DUP002"
    rule_name = "near_clone"
    category = RuleCategory.DESIGN
    severity = Severity.INFO
    description = "Function is structurally similar (>60%) to another"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        # Near-clone detection requires statement windows which need AST
        # re-parsing. For health rules, we skip this (it runs in the API).
        return []


class CloneClusterRule(HealthRule):
    rule_id = "DUP003"
    rule_name = "clone_cluster"
    category = RuleCategory.DESIGN
    severity = Severity.ERROR
    description = "More than 3 functions share the same structure"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        functions = _build_clone_data(graph)
        report = detect_clones(functions)
        findings: list[HealthFinding] = []
        for grp in report.exact_clone_groups:
            if len(grp.members) > 3:
                first = grp.members[0]
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=first.fq_name,
                        file_path=first.file_path,
                        line=first.start_line,
                        message=(
                            f"{len(grp.members)} functions share "
                            f"identical structure"
                        ),
                        suggestion=(
                            "Refactor: extract a shared function "
                            "or use a template pattern"
                        ),
                    )
                )
        return findings
