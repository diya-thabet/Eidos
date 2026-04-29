"""
Health rules: dead code (graph reachability).

Uses BFS from entry points to find deeply unreachable symbols.
"""

from __future__ import annotations

from app.analysis.code_health import (
    HealthConfig,
    HealthFinding,
    HealthRule,
    RuleCategory,
    Severity,
)
from app.analysis.dead_code import DeadCodeReport, analyze_dead_code
from app.analysis.graph_builder import CodeGraph

__all__ = [
    "UnreachableFunctionRule",
    "UnreachableClassRule",
    "DeadModuleRule",
    "DeadImportRule",
]


class UnreachableFunctionRule(HealthRule):
    rule_id = "DC001"
    rule_name = "unreachable_function"
    category = RuleCategory.DESIGN
    severity = Severity.WARNING
    description = "Function is unreachable from any entry point (deep dead code)"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        report = _get_cached_report(graph, config)
        findings: list[HealthFinding] = []
        for ds in report.unreachable_functions:
            findings.append(
                HealthFinding(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    category=self.category,
                    severity=self.severity,
                    symbol_fq_name=ds.fq_name,
                    file_path=ds.file_path,
                    line=ds.start_line,
                    message=(
                        f"Function '{ds.name}' is unreachable from "
                        f"any entry point"
                    ),
                    suggestion="Remove or connect to an active code path",
                )
            )
        return findings


class UnreachableClassRule(HealthRule):
    rule_id = "DC002"
    rule_name = "unreachable_class"
    category = RuleCategory.DESIGN
    severity = Severity.INFO
    description = "Class/interface is never referenced from reachable code"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        report = _get_cached_report(graph, config)
        findings: list[HealthFinding] = []
        for ds in report.unreachable_classes:
            findings.append(
                HealthFinding(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    category=self.category,
                    severity=self.severity,
                    symbol_fq_name=ds.fq_name,
                    file_path=ds.file_path,
                    line=ds.start_line,
                    message=(
                        f"{ds.kind.title()} '{ds.name}' is never "
                        f"referenced from reachable code"
                    ),
                    suggestion="Remove if unused or add to active code path",
                )
            )
        return findings


class DeadModuleRule(HealthRule):
    rule_id = "DC003"
    rule_name = "dead_module"
    category = RuleCategory.DESIGN
    severity = Severity.WARNING
    description = "Module has zero reachable symbols"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        report = _get_cached_report(graph, config)
        findings: list[HealthFinding] = []
        for dm in report.unreachable_modules:
            findings.append(
                HealthFinding(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    category=self.category,
                    severity=self.severity,
                    symbol_fq_name=f"module:{dm.module}",
                    file_path=dm.files[0] if dm.files else "",
                    line=0,
                    message=(
                        f"Module '{dm.module}' has {dm.symbol_count} "
                        f"symbols across {dm.file_count} files, "
                        f"none reachable"
                    ),
                    suggestion="Remove the entire module if unused",
                )
            )
        return findings


class DeadImportRule(HealthRule):
    rule_id = "DC004"
    rule_name = "dead_import"
    category = RuleCategory.BEST_PRACTICES
    severity = Severity.INFO
    description = "Import target is unreachable (imported but never used)"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        report = _get_cached_report(graph, config)
        findings: list[HealthFinding] = []
        for di in report.dead_imports:
            findings.append(
                HealthFinding(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    category=self.category,
                    severity=self.severity,
                    symbol_fq_name=di.target,
                    file_path=di.source_file,
                    line=di.line,
                    message=(
                        f"Import of '{di.target}' is dead "
                        f"(target is unreachable)"
                    ),
                    suggestion="Remove the import statement",
                )
            )
        return findings


# No caching - BFS is fast enough to run per check call


def _get_cached_report(graph: CodeGraph, config: HealthConfig) -> DeadCodeReport:
    """Run dead code analysis on the graph."""
    return analyze_dead_code(graph)
