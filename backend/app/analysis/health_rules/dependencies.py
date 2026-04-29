"""
Health rules: dependencies.

Rules that check dependency manifests for quality issues.
These rules operate on DependencyInfo objects attached to the CodeGraph.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.analysis.code_health import (
    HealthConfig,
    HealthFinding,
    HealthRule,
    RuleCategory,
    Severity,
)
from app.analysis.graph_builder import CodeGraph
from app.analysis.models import EdgeType

__all__ = [
    "UnpinnedDependencyRule",
    "WideVersionRangeRule",
    "UnusedDependencyRule",
    "DuplicateDependencyRule",
    "DevInProductionRule",
]


class UnpinnedDependencyRule(HealthRule):
    rule_id = "DEP001"
    rule_name = "unpinned_dependency"
    category = RuleCategory.BEST_PRACTICES
    severity = Severity.WARNING
    description = "Dependency has no version pin (uses * or latest)"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        for dep in getattr(graph, "dependencies", []):
            v = dep.version.strip()
            if v in ("*", "latest", "") or not v:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=f"{dep.ecosystem}:{dep.name}",
                        file_path=dep.file_path,
                        line=0,
                        message=(
                            f"Dependency '{dep.name}' has no version pin"
                        ),
                        suggestion="Pin to a specific version for reproducibility",
                    )
                )
        return findings


class WideVersionRangeRule(HealthRule):
    rule_id = "DEP002"
    rule_name = "wide_version_range"
    category = RuleCategory.BEST_PRACTICES
    severity = Severity.INFO
    description = "Dependency version range spans multiple major versions"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        for dep in getattr(graph, "dependencies", []):
            v = dep.version.strip()
            # Detect >=X with no upper bound or very wide ranges
            if v.startswith(">=") and "<" not in v:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=f"{dep.ecosystem}:{dep.name}",
                        file_path=dep.file_path,
                        line=0,
                        message=(
                            f"'{dep.name}' version '{v}' has no upper bound"
                        ),
                        suggestion="Add an upper version bound (e.g. >=2.0,<3.0)",
                    )
                )
        return findings


class UnusedDependencyRule(HealthRule):
    rule_id = "DEP003"
    rule_name = "unused_dependency"
    category = RuleCategory.DESIGN
    severity = Severity.WARNING
    description = "Declared dependency is never imported in source code"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings: list[HealthFinding] = []
        deps = getattr(graph, "dependencies", [])
        if not deps:
            return findings

        # Collect all import targets from edges
        imported_names: set[str] = set()
        for edge in graph.edges:
            if edge.edge_type == EdgeType.IMPORTS:
                target = edge.target_fq_name.lower()
                imported_names.add(target)
                # Also add first component (e.g. "flask" from "flask.app")
                imported_names.add(target.split(".")[0])

        # Also check all symbol namespaces
        for sym in graph.symbols.values():
            if sym.namespace:
                imported_names.add(sym.namespace.lower().split(".")[0])

        for dep in deps:
            if dep.is_dev:
                continue  # Skip dev deps
            # Normalize dep name: PyPI uses - and _, npm uses @scope/name
            dep_name = dep.name.lower().replace("-", "_").replace(".", "_")
            # Also try without scope for npm
            short = dep_name.split("/")[-1] if "/" in dep_name else dep_name

            if dep_name not in imported_names and short not in imported_names:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=f"{dep.ecosystem}:{dep.name}",
                        file_path=dep.file_path,
                        line=0,
                        message=(
                            f"'{dep.name}' is declared but never imported"
                        ),
                        suggestion="Remove if unused, or verify it's a runtime-only dep",
                    )
                )
        return findings


class DuplicateDependencyRule(HealthRule):
    rule_id = "DEP004"
    rule_name = "duplicate_dependency"
    category = RuleCategory.BEST_PRACTICES
    severity = Severity.INFO
    description = "Same dependency declared in multiple manifest files"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        deps = getattr(graph, "dependencies", [])
        # Group by (ecosystem, name)
        groups: dict[tuple[str, str], list[Any]] = defaultdict(list)
        for dep in deps:
            key = (dep.ecosystem, dep.name.lower())
            groups[key].append(dep)

        for (eco, name), group in groups.items():
            files = {d.file_path for d in group}
            if len(files) > 1:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=f"{eco}:{name}",
                        file_path=group[0].file_path,
                        line=0,
                        message=(
                            f"'{name}' declared in {len(files)} files: "
                            f"{', '.join(sorted(files))}"
                        ),
                        suggestion="Consolidate into a single manifest file",
                    )
                )
        return findings


class DevInProductionRule(HealthRule):
    rule_id = "DEP005"
    rule_name = "dev_in_production"
    category = RuleCategory.BEST_PRACTICES
    severity = Severity.WARNING
    description = "Dev dependency is imported in non-test source code"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings: list[HealthFinding] = []
        deps = getattr(graph, "dependencies", [])
        dev_deps = {
            d.name.lower().replace("-", "_"): d
            for d in deps if d.is_dev
        }
        if not dev_deps:
            return findings

        # Check import edges from non-test files
        for edge in graph.edges:
            if edge.edge_type != EdgeType.IMPORTS:
                continue
            if "test" in edge.file_path.lower():
                continue
            target = edge.target_fq_name.lower().replace("-", "_")
            first = target.split(".")[0]
            if first in dev_deps:
                dep = dev_deps[first]
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=f"{dep.ecosystem}:{dep.name}",
                        file_path=edge.file_path,
                        line=edge.line,
                        message=(
                            f"Dev dependency '{dep.name}' imported in "
                            f"production code '{edge.file_path}'"
                        ),
                        suggestion="Move to production dependencies or remove import",
                    )
                )
        return findings
