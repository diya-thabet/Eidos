"""
Health rules: module coupling and cohesion.

Quantitative rules based on Robert C. Martin's package metrics.
"""

from __future__ import annotations

from app.analysis.code_health import (
    HealthConfig,
    HealthFinding,
    HealthRule,
    RuleCategory,
    Severity,
)
from app.analysis.coupling import CouplingReport, analyze_coupling
from app.analysis.graph_builder import CodeGraph

__all__ = [
    "HighInstabilityRule",
    "LowCohesionModuleRule",
    "ZoneOfPainRule",
    "ZoneOfUselessnessRule",
    "ModuleCycleRule",
]


def _get_report(graph: CodeGraph) -> CouplingReport:
    return analyze_coupling(graph)


class HighInstabilityRule(HealthRule):
    rule_id = "MC001"
    rule_name = "high_instability"
    category = RuleCategory.DESIGN
    severity = Severity.WARNING
    description = "Module instability > 0.8 (highly dependent on external modules)"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        report = _get_report(graph)
        findings: list[HealthFinding] = []
        for m in report.modules:
            if m.symbol_count < 3:
                continue
            if m.instability > 0.8:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=f"module:{m.name}",
                        file_path=m.depends_on[0] if m.depends_on else "",
                        line=0,
                        message=(
                            f"Module '{m.name}' instability is "
                            f"{m.instability:.2f} "
                            f"(Ce={m.efferent_coupling}, "
                            f"Ca={m.afferent_coupling})"
                        ),
                        suggestion=(
                            "Reduce outgoing dependencies or add "
                            "abstractions for stability"
                        ),
                    )
                )
        return findings


class LowCohesionModuleRule(HealthRule):
    rule_id = "MC002"
    rule_name = "low_cohesion_module"
    category = RuleCategory.DESIGN
    severity = Severity.WARNING
    description = "Module cohesion < 0.3 (symbols barely interact)"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        report = _get_report(graph)
        findings: list[HealthFinding] = []
        for m in report.modules:
            if m.symbol_count < 5:
                continue
            total = m.intra_edges + m.inter_edges
            if total < 3:
                continue
            if m.cohesion < 0.3:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=f"module:{m.name}",
                        file_path="",
                        line=0,
                        message=(
                            f"Module '{m.name}' cohesion is "
                            f"{m.cohesion:.2f} "
                            f"({m.intra_edges} intra / "
                            f"{total} total edges)"
                        ),
                        suggestion="Split into smaller, focused modules",
                    )
                )
        return findings


class ZoneOfPainRule(HealthRule):
    rule_id = "MC003"
    rule_name = "zone_of_pain"
    category = RuleCategory.DESIGN
    severity = Severity.ERROR
    description = (
        "Module in Zone of Pain: highly stable and concrete "
        "(hard to change)"
    )

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        report = _get_report(graph)
        findings: list[HealthFinding] = []
        for m in report.modules:
            if m.class_count < 2:
                continue
            # Zone of Pain: low instability + low abstractness
            if m.instability < 0.2 and m.abstractness < 0.2:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=f"module:{m.name}",
                        file_path="",
                        line=0,
                        message=(
                            f"Module '{m.name}' is in the Zone of Pain "
                            f"(I={m.instability:.2f}, A={m.abstractness:.2f})"
                        ),
                        suggestion=(
                            "Add abstractions (interfaces) to make "
                            "the module easier to extend"
                        ),
                    )
                )
        return findings


class ZoneOfUselessnessRule(HealthRule):
    rule_id = "MC004"
    rule_name = "zone_of_uselessness"
    category = RuleCategory.DESIGN
    severity = Severity.INFO
    description = (
        "Module in Zone of Uselessness: highly abstract and unstable "
        "(over-engineered)"
    )

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        report = _get_report(graph)
        findings: list[HealthFinding] = []
        for m in report.modules:
            if m.class_count < 2:
                continue
            if m.instability > 0.8 and m.abstractness > 0.8:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=f"module:{m.name}",
                        file_path="",
                        line=0,
                        message=(
                            f"Module '{m.name}' is in the Zone of "
                            f"Uselessness "
                            f"(I={m.instability:.2f}, A={m.abstractness:.2f})"
                        ),
                        suggestion=(
                            "Remove unused abstractions or add "
                            "concrete implementations"
                        ),
                    )
                )
        return findings


class ModuleCycleRule(HealthRule):
    rule_id = "MC005"
    rule_name = "module_dependency_cycle"
    category = RuleCategory.DESIGN
    severity = Severity.ERROR
    description = "Modules form a dependency cycle"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        report = _get_report(graph)
        findings: list[HealthFinding] = []
        for cycle in report.dependency_cycles:
            chain = " -> ".join(cycle)
            findings.append(
                HealthFinding(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    category=self.category,
                    severity=self.severity,
                    symbol_fq_name=f"cycle:{cycle[0]}",
                    file_path="",
                    line=0,
                    message=f"Module cycle: {chain}",
                    suggestion=(
                        "Break the cycle with dependency inversion "
                        "or merge the modules"
                    ),
                )
            )
        return findings
