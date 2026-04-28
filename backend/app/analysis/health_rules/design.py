"""
Health rules: design.

Rules: see __all__
"""

from __future__ import annotations

from app.analysis.code_health import HealthConfig, HealthFinding, HealthRule, RuleCategory, Severity
from app.analysis.graph_builder import CodeGraph
from app.analysis.models import EdgeType, SymbolKind


def _get_parent_class(fq_name: str, graph: CodeGraph) -> str:
    """Get the parent class/struct FQ name for a symbol."""
    sym = graph.symbols.get(fq_name)
    if sym and sym.parent_fq_name:
        return sym.parent_fq_name
    parts = fq_name.rsplit(".", 1)
    return parts[0] if len(parts) > 1 else ""

__all__ = [
    "CircularDependencyRule",
    "OrphanClassRule",
    "DeadMethodRule",
    "FeatureEnvyRule",
    "DataClassSmellRule",
    "ShotgunSurgeryRule",
    "MiddleManRule",
    "SpeculativeGeneralityRule",
    "LazyClassRule",
    "ModuleTangleRule",
]


class CircularDependencyRule(HealthRule):
    rule_id = "DS001"
    rule_name = "circular_dependency"
    category = RuleCategory.DESIGN
    severity = Severity.ERROR
    description = "Modules/classes have circular dependencies"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        call_map: dict[str, set[str]] = {}
        for edge in graph.edges:
            if edge.edge_type in (EdgeType.CALLS, EdgeType.USES):
                src_ns = _get_parent_class(edge.source_fq_name, graph)
                tgt_ns = _get_parent_class(edge.target_fq_name, graph)
                if src_ns and tgt_ns and src_ns != tgt_ns:
                    call_map.setdefault(src_ns, set()).add(tgt_ns)

        seen: set[tuple[str, str]] = set()
        for src in call_map:
            for tgt in call_map.get(src, set()):
                if src in call_map.get(tgt, set()):
                    pair = (min(src, tgt), max(src, tgt))
                    if pair not in seen:
                        sym = graph.symbols.get(src)
                        findings.append(
                            HealthFinding(
                                rule_id=self.rule_id,
                                rule_name=self.rule_name,
                                category=self.category,
                                severity=self.severity,
                                symbol_fq_name=src,
                                file_path=sym.file_path if sym else "",
                                line=sym.start_line if sym else 0,
                                message=f"Circular dependency: {src} <-> {tgt}",
                                suggestion="Break the cycle with an interface or mediator",
                            )
                        )
                        seen.add(pair)
        return findings



class OrphanClassRule(HealthRule):
    rule_id = "DS002"
    rule_name = "orphan_class"
    category = RuleCategory.DESIGN
    severity = Severity.INFO
    description = "Class is never referenced by any other symbol"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        referenced: set[str] = set()
        for edge in graph.edges:
            referenced.add(edge.target_fq_name)
        for sym in graph.symbols.values():
            if sym.kind not in (SymbolKind.CLASS, SymbolKind.STRUCT):
                continue
            if sym.fq_name not in referenced:
                children = graph.get_children(sym.fq_name)
                child_referenced = any(c in referenced for c in children)
                if not child_referenced:
                    findings.append(
                        HealthFinding(
                            rule_id=self.rule_id,
                            rule_name=self.rule_name,
                            category=self.category,
                            severity=self.severity,
                            symbol_fq_name=sym.fq_name,
                            file_path=sym.file_path,
                            line=sym.start_line,
                            message="Class is never referenced (possibly dead code)",
                            suggestion="Remove if unused, or verify it is an entry point",
                        )
                    )
        return findings


# ==================================================================
# SECURITY rules
# ==================================================================



class DeadMethodRule(HealthRule):
    rule_id = "SM001"
    rule_name = "dead_method"
    category = RuleCategory.DESIGN
    severity = Severity.WARNING
    description = "Method is never called (zero fan-in, not a constructor or entry point)"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        _entry_names = {"main", "run", "start", "execute", "handle", "Main"}
        for sym in graph.symbols.values():
            if sym.kind != SymbolKind.METHOD:
                continue
            if sym.name in _entry_names or sym.name.startswith("test"):
                continue
            if graph.fan_in(sym.fq_name) == 0:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message="Method is never called (dead code)",
                        suggestion="Remove if unused, or add tests that exercise it",
                    )
                )
        return findings



class FeatureEnvyRule(HealthRule):
    rule_id = "SM002"
    rule_name = "feature_envy"
    category = RuleCategory.DESIGN
    severity = Severity.WARNING
    description = "Method calls more methods from another class than from its own"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        for sym in graph.symbols.values():
            if sym.kind != SymbolKind.METHOD or not sym.parent_fq_name:
                continue
            callees = graph.get_callees(sym.fq_name)
            if len(callees) < 3:
                continue
            own_count = 0
            foreign_counts: dict[str, int] = {}
            for callee in callees:
                callee_sym = graph.symbols.get(callee)
                if callee_sym and callee_sym.parent_fq_name:
                    if callee_sym.parent_fq_name == sym.parent_fq_name:
                        own_count += 1
                    else:
                        p = callee_sym.parent_fq_name
                        foreign_counts[p] = foreign_counts.get(p, 0) + 1
            for foreign_class, count in foreign_counts.items():
                if count > own_count and count >= 3:
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
                                f"Method calls {count} methods on {foreign_class} "
                                f"but only {own_count} on its own class"
                            ),
                            suggestion="Move this method to the class it envies",
                        )
                    )
                    break
        return findings



class DataClassSmellRule(HealthRule):
    rule_id = "SM003"
    rule_name = "data_class"
    category = RuleCategory.DESIGN
    severity = Severity.INFO
    description = "Class is mostly fields with no behavior (anemic domain model)"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        for sym in graph.symbols.values():
            if sym.kind not in (SymbolKind.CLASS, SymbolKind.STRUCT):
                continue
            children = graph.get_children(sym.fq_name)
            if len(children) < 3:
                continue
            fields = 0
            methods = 0
            for c in children:
                cs = graph.symbols.get(c)
                if not cs:
                    continue
                if cs.kind == SymbolKind.FIELD:
                    fields += 1
                elif cs.kind in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR):
                    methods += 1
            total = fields + methods
            if total > 0 and fields / total >= 0.8 and fields >= 4:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message=f"Class has {fields} fields but only {methods} methods (anemic)",
                        suggestion="Add behavior methods or use a plain DTO/record type",
                    )
                )
        return findings



class ShotgunSurgeryRule(HealthRule):
    rule_id = "SM004"
    rule_name = "shotgun_surgery"
    category = RuleCategory.DESIGN
    severity = Severity.ERROR
    description = "Symbol is called from many different classes (changes ripple widely)"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        for sym in graph.symbols.values():
            if sym.kind != SymbolKind.METHOD:
                continue
            callers = graph.get_callers(sym.fq_name)
            if len(callers) < 5:
                continue
            caller_classes: set[str] = set()
            for caller_fq in callers:
                cs = graph.symbols.get(caller_fq)
                if cs and cs.parent_fq_name:
                    caller_classes.add(cs.parent_fq_name)
            if len(caller_classes) >= 5:
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
                            f"Called from {len(caller_classes)} different classes -- "
                            f"changes here cause shotgun surgery"
                        ),
                        suggestion="Reduce coupling; introduce an abstraction layer",
                    )
                )
        return findings



class MiddleManRule(HealthRule):
    rule_id = "SM005"
    rule_name = "middle_man"
    category = RuleCategory.DESIGN
    severity = Severity.INFO
    description = "Class delegates everything (all methods just call one other class)"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        for sym in graph.symbols.values():
            if sym.kind not in (SymbolKind.CLASS, SymbolKind.STRUCT):
                continue
            children = graph.get_children(sym.fq_name)
            methods = [
                c
                for c in children
                if c in graph.symbols and graph.symbols[c].kind == SymbolKind.METHOD
            ]
            if len(methods) < 3:
                continue
            delegate_targets: set[str] = set()
            all_delegate = True
            for m in methods:
                callees = graph.get_callees(m)
                if len(callees) != 1:
                    all_delegate = False
                    break
                callee_sym = graph.symbols.get(callees[0])
                if callee_sym and callee_sym.parent_fq_name:
                    delegate_targets.add(callee_sym.parent_fq_name)
            if all_delegate and len(delegate_targets) == 1:
                target = next(iter(delegate_targets))
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message=f"All methods delegate to {target} (middle man)",
                        suggestion="Remove the middle man; let callers use the target directly",
                    )
                )
        return findings



class SpeculativeGeneralityRule(HealthRule):
    rule_id = "SM006"
    rule_name = "speculative_generality"
    category = RuleCategory.DESIGN
    severity = Severity.INFO
    description = "Interface has zero or one implementor"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        impl_count: dict[str, int] = {}
        for edge in graph.edges:
            if edge.edge_type == EdgeType.IMPLEMENTS:
                impl_count[edge.target_fq_name] = impl_count.get(edge.target_fq_name, 0) + 1
        for sym in graph.symbols.values():
            if sym.kind != SymbolKind.INTERFACE:
                continue
            count = impl_count.get(sym.fq_name, 0)
            if count <= 1:
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
                            f"Interface has {count} implementor(s) -- may be speculative generality"
                        ),
                        suggestion="Remove if premature; add when a second implementation exists",
                    )
                )
        return findings



class LazyClassRule(HealthRule):
    rule_id = "SM007"
    rule_name = "lazy_class"
    category = RuleCategory.DESIGN
    severity = Severity.INFO
    description = "Class has only one method (too little behavior to justify a class)"

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
            if method_count == 1 and len(children) <= 2:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message="Class has only 1 method (lazy class)",
                        suggestion="Merge into caller or promote to a function",
                    )
                )
        return findings


# ==================================================================
# COUPLING & COHESION rules (OO metrics)
# ==================================================================



class ModuleTangleRule(HealthRule):
    rule_id = "AR001"
    rule_name = "module_tangle"
    category = RuleCategory.DESIGN
    severity = Severity.ERROR
    description = "Namespace has circular dependencies with other namespaces"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        ns_deps: dict[str, set[str]] = {}
        for edge in graph.edges:
            if edge.edge_type not in (EdgeType.CALLS, EdgeType.USES, EdgeType.IMPORTS):
                continue
            src_sym = graph.symbols.get(edge.source_fq_name)
            tgt_sym = graph.symbols.get(edge.target_fq_name)
            src_ns = src_sym.namespace if src_sym else ""
            tgt_ns = tgt_sym.namespace if tgt_sym else ""
            if src_ns and tgt_ns and src_ns != tgt_ns:
                ns_deps.setdefault(src_ns, set()).add(tgt_ns)
        seen: set[tuple[str, str]] = set()
        for ns_a, deps in ns_deps.items():
            for ns_b in deps:
                if ns_a in ns_deps.get(ns_b, set()):
                    pair = (min(ns_a, ns_b), max(ns_a, ns_b))
                    if pair not in seen:
                        seen.add(pair)
                        findings.append(
                            HealthFinding(
                                rule_id=self.rule_id,
                                rule_name=self.rule_name,
                                category=self.category,
                                severity=self.severity,
                                symbol_fq_name=ns_a,
                                file_path="",
                                line=0,
                                message=f"Module tangle: {ns_a} <-> {ns_b}",
                                suggestion="Break cycle with dependency inversion or facade",
                            )
                        )
        return findings



