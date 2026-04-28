"""
Health rules: solid.

Rules: see __all__
"""

from __future__ import annotations

from app.analysis.code_health import HealthConfig, HealthFinding, HealthRule, RuleCategory, Severity
from app.analysis.graph_builder import CodeGraph
from app.analysis.models import EdgeType, SymbolKind

__all__ = [
    "GodClassRule",
    "DeepInheritanceRule",
    "FatInterfaceRule",
    "NoAbstractionDependencyRule",
    "SwissArmyKnifeRule",
]


class GodClassRule(HealthRule):
    rule_id = "SOLID001"
    rule_name = "god_class"
    category = RuleCategory.SOLID
    severity = Severity.ERROR
    description = "Class has too many methods (violates SRP)"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        for sym in graph.symbols.values():
            if sym.kind not in (SymbolKind.CLASS, SymbolKind.STRUCT):
                continue
            children = graph.get_children(sym.fq_name)
            method_count = sum(
                1
                for c in children
                if c in graph.symbols
                and graph.symbols[c].kind in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR)
            )
            if method_count > config.max_god_class_methods:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message=(
                            f"Class has {method_count} methods "
                            f"(max {config.max_god_class_methods}) -- likely violates SRP"
                        ),
                        suggestion="Extract responsibilities into separate classes",
                    )
                )
        return findings



class DeepInheritanceRule(HealthRule):
    rule_id = "SOLID002"
    rule_name = "deep_inheritance"
    category = RuleCategory.SOLID
    severity = Severity.WARNING
    description = "Inheritance chain is too deep"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        inherits = {
            e.source_fq_name: e.target_fq_name
            for e in graph.edges
            if e.edge_type == EdgeType.INHERITS
        }
        for sym in graph.symbols.values():
            if sym.kind not in (SymbolKind.CLASS, SymbolKind.STRUCT):
                continue
            depth = 0
            current = sym.fq_name
            visited: set[str] = set()
            while current in inherits and current not in visited:
                visited.add(current)
                current = inherits[current]
                depth += 1
            if depth >= config.max_inheritance_depth:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message=(
                            f"Inheritance depth is {depth} (max {config.max_inheritance_depth})"
                        ),
                        suggestion="Prefer composition over inheritance",
                    )
                )
        return findings



class FatInterfaceRule(HealthRule):
    rule_id = "SOLID003"
    rule_name = "fat_interface"
    category = RuleCategory.SOLID
    severity = Severity.WARNING
    description = "Interface has too many methods (violates ISP)"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        for sym in graph.symbols.values():
            if sym.kind != SymbolKind.INTERFACE:
                continue
            children = graph.get_children(sym.fq_name)
            method_count = len(children)
            if method_count > config.max_parameters:  # reuse threshold
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message=f"Interface has {method_count} methods -- may violate ISP",
                        suggestion="Split into smaller, role-specific interfaces",
                    )
                )
        return findings



class NoAbstractionDependencyRule(HealthRule):
    rule_id = "SOLID004"
    rule_name = "concrete_dependency"
    category = RuleCategory.SOLID
    severity = Severity.INFO
    description = "Class depends on concrete classes only (no interfaces) -- may violate DIP"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings: list[HealthFinding] = []
        interfaces = {s.fq_name for s in graph.symbols.values() if s.kind == SymbolKind.INTERFACE}
        if not interfaces:
            return findings
        for sym in graph.symbols.values():
            if sym.kind not in (SymbolKind.CLASS, SymbolKind.STRUCT):
                continue
            callees = set(graph.get_callees(sym.fq_name))
            children_callees: set[str] = set()
            for child_fq in graph.get_children(sym.fq_name):
                children_callees.update(graph.get_callees(child_fq))
            all_deps = callees | children_callees
            if not all_deps:
                continue
            uses_interface = any(d in interfaces for d in all_deps)
            if not uses_interface and len(all_deps) > 3:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message=(
                            f"Class has {len(all_deps)} dependencies but uses no interfaces (DIP)"
                        ),
                        suggestion="Depend on abstractions (interfaces/traits) not concretions",
                    )
                )
        return findings


# ==================================================================
# COMPLEXITY rules
# ==================================================================



class SwissArmyKnifeRule(HealthRule):
    rule_id = "AR003"
    rule_name = "swiss_army_knife"
    category = RuleCategory.SOLID
    severity = Severity.WARNING
    description = "Class implements too many interfaces"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        impl_counts: dict[str, list[str]] = {}
        for edge in graph.edges:
            if edge.edge_type == EdgeType.IMPLEMENTS:
                impl_counts.setdefault(edge.source_fq_name, []).append(edge.target_fq_name)
        for fq, ifaces in impl_counts.items():
            if len(ifaces) > 3:
                sym = graph.symbols.get(fq)
                if sym:
                    findings.append(
                        HealthFinding(
                            rule_id=self.rule_id,
                            rule_name=self.rule_name,
                            category=self.category,
                            severity=self.severity,
                            symbol_fq_name=fq,
                            file_path=sym.file_path,
                            line=sym.start_line,
                            message=f"Implements {len(ifaces)} interfaces",
                            suggestion="Split responsibilities; each class should have one role",
                        )
                    )
        return findings


# ==================================================================
# ADDITIONAL CLEAN CODE rules
# ==================================================================



