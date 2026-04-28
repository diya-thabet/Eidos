"""
Health rules: naming.

Rules: ShortNameRule, BooleanNameRule, InconsistentNamingRule, PrefixedNameRule
"""

from __future__ import annotations

from app.analysis.code_health import HealthConfig, HealthFinding, HealthRule, RuleCategory, Severity
from app.analysis.graph_builder import CodeGraph
from app.analysis.models import SymbolKind

__all__ = ['ShortNameRule', 'BooleanNameRule', 'InconsistentNamingRule', 'PrefixedNameRule']


class ShortNameRule(HealthRule):
    rule_id = "NM001"
    rule_name = "short_name"
    category = RuleCategory.NAMING
    severity = Severity.INFO
    description = "Symbol name is too short to be descriptive"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        _skip = {"id", "db", "ok", "io", "os", "fs", "rx", "tx", "fn"}
        for sym in graph.symbols.values():
            if sym.kind == SymbolKind.FIELD:
                continue
            if len(sym.name) <= 2 and sym.name.lower() not in _skip:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message=f"Name '{sym.name}' is too short ({len(sym.name)} chars)",
                        suggestion="Use a descriptive name that reveals intent",
                    )
                )
        return findings



class BooleanNameRule(HealthRule):
    rule_id = "NM002"
    rule_name = "non_boolean_bool_name"
    category = RuleCategory.NAMING
    severity = Severity.INFO
    description = "Method returning bool should use is/has/can/should prefix"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        bool_types = {"bool", "boolean", "Boolean", "Bool"}
        prefixes = ("is", "has", "can", "should", "was", "will", "did", "are")
        for sym in graph.symbols.values():
            if sym.kind != SymbolKind.METHOD:
                continue
            if sym.return_type not in bool_types:
                continue
            lower = sym.name.lower()
            if not any(lower.startswith(p) for p in prefixes):
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message=f"Boolean method '{sym.name}' lacks is/has/can prefix",
                        suggestion="Rename to isXxx, hasXxx, canXxx for clarity",
                    )
                )
        return findings


# ==================================================================
# DESIGN rules
# ==================================================================



class InconsistentNamingRule(HealthRule):
    rule_id = "NM003"
    rule_name = "inconsistent_naming"
    category = RuleCategory.NAMING
    severity = Severity.INFO
    description = "Class mixes naming conventions (camelCase + snake_case)"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        for sym in graph.symbols.values():
            if sym.kind not in (SymbolKind.CLASS, SymbolKind.STRUCT):
                continue
            children = graph.get_children(sym.fq_name)
            snake = 0
            camel = 0
            for c in children:
                cs = graph.symbols.get(c)
                if not cs:
                    continue
                name = cs.name
                if "_" in name and name != name.upper():
                    snake += 1
                elif name and name[0].islower() and any(ch.isupper() for ch in name):
                    camel += 1
            if snake >= 2 and camel >= 2:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message=f"Mixes naming: {snake} snake_case + {camel} camelCase",
                        suggestion="Pick one naming convention and apply consistently",
                    )
                )
        return findings



class PrefixedNameRule(HealthRule):
    rule_id = "NM004"
    rule_name = "hungarian_notation"
    category = RuleCategory.NAMING
    severity = Severity.INFO
    description = "Symbol uses Hungarian notation prefixes (strName, bIsValid)"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        prefixes = (
            "str",
            "int",
            "bln",
            "dbl",
            "arr",
            "lst",
            "obj",
            "b_",
            "i_",
            "s_",
            "n_",
            "m_",
        )
        for sym in graph.symbols.values():
            if sym.kind == SymbolKind.NAMESPACE:
                continue
            lower = sym.name.lower()
            for pfx in prefixes:
                if lower.startswith(pfx) and len(sym.name) > len(pfx):
                    next_char = sym.name[len(pfx)]
                    if next_char.isupper() or next_char == "_":
                        findings.append(
                            HealthFinding(
                                rule_id=self.rule_id,
                                rule_name=self.rule_name,
                                category=self.category,
                                severity=self.severity,
                                symbol_fq_name=sym.fq_name,
                                file_path=sym.file_path,
                                line=sym.start_line,
                                message=f"Name '{sym.name}' appears to use Hungarian notation",
                                suggestion="Use descriptive names without type prefixes",
                            )
                        )
                        break
        return findings


# ==================================================================
# ADDITIONAL SECURITY rules
# ==================================================================



