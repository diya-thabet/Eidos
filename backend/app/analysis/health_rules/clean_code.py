"""
Health rules: clean_code.

Rules: see __all__
"""

from __future__ import annotations

from app.analysis.code_health import HealthConfig, HealthFinding, HealthRule, RuleCategory, Severity
from app.analysis.graph_builder import CodeGraph
from app.analysis.models import SymbolKind

__all__ = [
    "LongMethodRule",
    "LongClassRule",
    "TooManyParametersRule",
    "EmptyMethodRule",
    "ConstructorOverInjectionRule",
    "VoidAbuseRule",
    "StaticAbuseRule",
    "MutablePublicStateRule",
]


class LongMethodRule(HealthRule):
    rule_id = "CC001"
    rule_name = "long_method"
    category = RuleCategory.CLEAN_CODE
    severity = Severity.WARNING
    description = "Method exceeds maximum line count"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        for sym in graph.symbols.values():
            if sym.kind not in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR):
                continue
            loc = sym.end_line - sym.start_line + 1
            if loc > config.max_method_lines:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message=f"Method is {loc} lines (max {config.max_method_lines})",
                        suggestion="Extract smaller helper methods to improve readability",
                    )
                )
        return findings



class LongClassRule(HealthRule):
    rule_id = "CC002"
    rule_name = "long_class"
    category = RuleCategory.CLEAN_CODE
    severity = Severity.WARNING
    description = "Class/struct exceeds maximum line count"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        for sym in graph.symbols.values():
            if sym.kind not in (SymbolKind.CLASS, SymbolKind.STRUCT):
                continue
            loc = sym.end_line - sym.start_line + 1
            if loc > config.max_class_lines:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message=f"Class is {loc} lines (max {config.max_class_lines})",
                        suggestion="Split into smaller, focused classes (SRP)",
                    )
                )
        return findings



class TooManyParametersRule(HealthRule):
    rule_id = "CC003"
    rule_name = "too_many_parameters"
    category = RuleCategory.CLEAN_CODE
    severity = Severity.WARNING
    description = "Method has too many parameters"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        for sym in graph.symbols.values():
            if sym.kind not in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR):
                continue
            count = len(sym.parameters)
            if count > config.max_parameters:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message=f"Method has {count} parameters (max {config.max_parameters})",
                        suggestion="Group related parameters into a config/options object",
                    )
                )
        return findings



class EmptyMethodRule(HealthRule):
    rule_id = "CC004"
    rule_name = "empty_method"
    category = RuleCategory.CLEAN_CODE
    severity = Severity.INFO
    description = "Method body appears empty (1-2 lines)"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        for sym in graph.symbols.values():
            if sym.kind not in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR):
                continue
            loc = sym.end_line - sym.start_line + 1
            if loc <= 2:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message="Method body appears empty or trivial",
                        suggestion="Remove dead code or add a TODO comment",
                    )
                )
        return findings


# ==================================================================
# SOLID rules
# ==================================================================



class ConstructorOverInjectionRule(HealthRule):
    rule_id = "CC005"
    rule_name = "constructor_over_injection"
    category = RuleCategory.CLEAN_CODE
    severity = Severity.WARNING
    description = "Constructor has too many parameters (dependency over-injection)"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        for sym in graph.symbols.values():
            if sym.kind != SymbolKind.CONSTRUCTOR:
                continue
            count = len(sym.parameters)
            if count > 4:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message=f"Constructor has {count} parameters (max 4)",
                        suggestion="Use a builder pattern or split into focused services",
                    )
                )
        return findings



class VoidAbuseRule(HealthRule):
    rule_id = "CC006"
    rule_name = "void_abuse"
    category = RuleCategory.CLEAN_CODE
    severity = Severity.INFO
    description = "Class has >70% void methods (side-effect heavy, hard to test)"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        void_types = {"void", "", "None", "unit", "()", "Unit"}
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
            void_count = sum(1 for m in methods if graph.symbols[m].return_type in void_types)
            ratio = void_count / len(methods)
            if ratio > 0.7:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message=(f"{void_count}/{len(methods)} methods return void ({ratio:.0%})"),
                        suggestion="Return results instead of mutating state; improves testability",
                    )
                )
        return findings



class StaticAbuseRule(HealthRule):
    rule_id = "CC007"
    rule_name = "static_abuse"
    category = RuleCategory.CLEAN_CODE
    severity = Severity.INFO
    description = "Class has >50% static methods (may indicate missing OOP design)"

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
            static_count = sum(1 for m in methods if "static" in graph.symbols[m].modifiers)
            ratio = static_count / len(methods)
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
                        message=f"{static_count}/{len(methods)} methods are static ({ratio:.0%})",
                        suggestion="Consider instance methods with dependency injection",
                    )
                )
        return findings



class MutablePublicStateRule(HealthRule):
    rule_id = "CC008"
    rule_name = "mutable_public_state"
    category = RuleCategory.CLEAN_CODE
    severity = Severity.WARNING
    description = "Class exposes many public mutable fields (encapsulation violation)"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        for sym in graph.symbols.values():
            if sym.kind not in (SymbolKind.CLASS, SymbolKind.STRUCT):
                continue
            children = graph.get_children(sym.fq_name)
            public_fields = 0
            for c in children:
                cs = graph.symbols.get(c)
                if cs and cs.kind == SymbolKind.FIELD:
                    if "public" in cs.modifiers or "pub" in cs.modifiers:
                        public_fields += 1
            if public_fields >= 5:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message=f"Class has {public_fields} public fields",
                        suggestion="Use private fields with accessor methods (encapsulation)",
                    )
                )
        return findings


# ==================================================================
# ADDITIONAL NAMING rules
# ==================================================================



