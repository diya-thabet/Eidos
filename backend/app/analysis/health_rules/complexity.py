"""
Health rules: complexity.

Rules: see __all__
"""

from __future__ import annotations

from app.analysis.code_health import HealthConfig, HealthFinding, HealthRule, RuleCategory, Severity
from app.analysis.graph_builder import CodeGraph
from app.analysis.models import SymbolKind

__all__ = [
    "HighFanOutRule",
    "HighFanInRule",
    "TooManyChildrenRule",
    "CouplingBetweenObjectsRule",
    "LackOfCohesionRule",
    "ComplexityDensityRule",
    "HighCyclomaticRule",
    "VeryHighCyclomaticRule",
    "HighCognitiveRule",
    "VeryHighCognitiveRule",
    "ComplexityPerLineRule",
]


class HighFanOutRule(HealthRule):
    rule_id = "CX001"
    rule_name = "high_fan_out"
    category = RuleCategory.COMPLEXITY
    severity = Severity.WARNING
    description = "Method calls too many other methods"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        for sym in graph.symbols.values():
            if sym.kind not in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR):
                continue
            fan_out = graph.fan_out(sym.fq_name)
            if fan_out > config.max_fan_out:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message=f"Fan-out is {fan_out} (max {config.max_fan_out})",
                        suggestion="Extract logic into intermediate methods",
                    )
                )
        return findings



class HighFanInRule(HealthRule):
    rule_id = "CX002"
    rule_name = "high_fan_in"
    category = RuleCategory.COMPLEXITY
    severity = Severity.INFO
    description = "Symbol is called by too many others (change is risky)"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        for sym in graph.symbols.values():
            fan_in = graph.fan_in(sym.fq_name)
            if fan_in > config.max_fan_in:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message=f"Fan-in is {fan_in} (max {config.max_fan_in})",
                        suggestion="High fan-in = high risk. Ensure thorough test coverage",
                    )
                )
        return findings



class TooManyChildrenRule(HealthRule):
    rule_id = "CX003"
    rule_name = "too_many_members"
    category = RuleCategory.COMPLEXITY
    severity = Severity.WARNING
    description = "Class has too many direct members"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        for sym in graph.symbols.values():
            if sym.kind not in (SymbolKind.CLASS, SymbolKind.STRUCT):
                continue
            count = len(graph.get_children(sym.fq_name))
            if count > config.max_children:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message=f"Class has {count} members (max {config.max_children})",
                        suggestion="Split into smaller, focused classes",
                    )
                )
        return findings


# ==================================================================
# DOCUMENTATION rules
# ==================================================================



class CouplingBetweenObjectsRule(HealthRule):
    rule_id = "MT001"
    rule_name = "high_coupling"
    category = RuleCategory.COMPLEXITY
    severity = Severity.WARNING
    description = "Class depends on too many other classes (CBO metric)"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        threshold = config.max_fan_out  # reuse
        for sym in graph.symbols.values():
            if sym.kind not in (SymbolKind.CLASS, SymbolKind.STRUCT):
                continue
            deps: set[str] = set()
            for child_fq in graph.get_children(sym.fq_name):
                for callee in graph.get_callees(child_fq):
                    cs = graph.symbols.get(callee)
                    if cs and cs.parent_fq_name and cs.parent_fq_name != sym.fq_name:
                        deps.add(cs.parent_fq_name)
            if len(deps) > threshold:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message=f"Coupled to {len(deps)} classes (CBO > {threshold})",
                        suggestion="Reduce dependencies; apply dependency inversion",
                    )
                )
        return findings



class LackOfCohesionRule(HealthRule):
    rule_id = "MT002"
    rule_name = "low_cohesion"
    category = RuleCategory.COMPLEXITY
    severity = Severity.WARNING
    description = "Class methods operate on disjoint sets of dependencies (LCOM-like)"

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
            if len(methods) < 4:
                continue
            callsets: list[set[str]] = []
            for m in methods:
                callsets.append(set(graph.get_callees(m)))
            if not callsets:
                continue
            pairs_sharing = 0
            total_pairs = 0
            for i in range(len(callsets)):
                for j in range(i + 1, len(callsets)):
                    total_pairs += 1
                    if callsets[i] & callsets[j]:
                        pairs_sharing += 1
            if total_pairs > 0:
                cohesion = pairs_sharing / total_pairs
                if cohesion < 0.2:
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
                                f"Low cohesion ({cohesion:.0%}) -- methods share few dependencies"
                            ),
                            suggestion="Split into focused classes with shared state",
                        )
                    )
        return findings



class ComplexityDensityRule(HealthRule):
    rule_id = "MT003"
    rule_name = "complexity_density"
    category = RuleCategory.COMPLEXITY
    severity = Severity.WARNING
    description = "Method has high fan-out relative to its size (too much in too few lines)"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        for sym in graph.symbols.values():
            if sym.kind != SymbolKind.METHOD:
                continue
            loc = sym.end_line - sym.start_line + 1
            if loc < 5:
                continue
            fan_out = graph.fan_out(sym.fq_name)
            density = fan_out / loc
            if density > 0.5 and fan_out >= 5:
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
                            f"Complexity density {density:.2f} ({fan_out} calls in {loc} lines)"
                        ),
                        suggestion="Extract helper methods to reduce density",
                    )
                )
        return findings


# ==================================================================
# ARCHITECTURE rules
# ==================================================================


# ==================================================================
# CYCLOMATIC / COGNITIVE COMPLEXITY rules (computed by tree-sitter)
# ==================================================================


class HighCyclomaticRule(HealthRule):
    rule_id = "CX004"
    rule_name = "high_cyclomatic_complexity"
    category = RuleCategory.COMPLEXITY
    severity = Severity.WARNING
    description = "Cyclomatic complexity exceeds 15"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        threshold = getattr(config, "max_cyclomatic", 15)
        for sym in graph.symbols.values():
            if sym.kind not in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR):
                continue
            cc = sym.cyclomatic_complexity
            if cc > threshold:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message=f"Cyclomatic complexity is {cc} (max {threshold})",
                        suggestion="Split into smaller functions with fewer branches",
                    )
                )
        return findings


class VeryHighCyclomaticRule(HealthRule):
    rule_id = "CX005"
    rule_name = "very_high_cyclomatic_complexity"
    category = RuleCategory.COMPLEXITY
    severity = Severity.ERROR
    description = "Cyclomatic complexity exceeds 30"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        threshold = getattr(config, "max_cyclomatic_error", 30)
        for sym in graph.symbols.values():
            if sym.kind not in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR):
                continue
            cc = sym.cyclomatic_complexity
            if cc > threshold:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message=f"Cyclomatic complexity is {cc} (max {threshold})",
                        suggestion="This function is extremely complex; refactor urgently",
                    )
                )
        return findings


class HighCognitiveRule(HealthRule):
    rule_id = "CX006"
    rule_name = "high_cognitive_complexity"
    category = RuleCategory.COMPLEXITY
    severity = Severity.WARNING
    description = "Cognitive complexity exceeds 20"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        threshold = getattr(config, "max_cognitive", 20)
        for sym in graph.symbols.values():
            if sym.kind not in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR):
                continue
            cog = sym.cognitive_complexity
            if cog > threshold:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message=f"Cognitive complexity is {cog} (max {threshold})",
                        suggestion="Reduce nesting depth; extract nested logic into helpers",
                    )
                )
        return findings


class VeryHighCognitiveRule(HealthRule):
    rule_id = "CX007"
    rule_name = "very_high_cognitive_complexity"
    category = RuleCategory.COMPLEXITY
    severity = Severity.ERROR
    description = "Cognitive complexity exceeds 40"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        threshold = getattr(config, "max_cognitive_error", 40)
        for sym in graph.symbols.values():
            if sym.kind not in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR):
                continue
            cog = sym.cognitive_complexity
            if cog > threshold:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message=f"Cognitive complexity is {cog} (max {threshold})",
                        suggestion=(
                            "This function is extremely hard to understand; "
                            "refactor urgently"
                        ),
                    )
                )
        return findings


class ComplexityPerLineRule(HealthRule):
    rule_id = "CX008"
    rule_name = "complexity_per_line"
    category = RuleCategory.COMPLEXITY
    severity = Severity.WARNING
    description = "Cyclomatic complexity per line of code is too high"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        for sym in graph.symbols.values():
            if sym.kind not in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR):
                continue
            cc = sym.cyclomatic_complexity
            loc = sym.end_line - sym.start_line + 1
            if loc < 3 or cc < 3:
                continue
            ratio = cc / loc
            if ratio > 0.5:
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
                            f"CC/LOC ratio is {ratio:.2f} ({cc} branches in {loc} lines)"
                        ),
                        suggestion="Nearly every line is a branch; simplify the logic",
                    )
                )
        return findings



