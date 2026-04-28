"""
Health rules: documentation.

Rules: MissingDocRule
"""

from __future__ import annotations

from app.analysis.code_health import HealthConfig, HealthFinding, HealthRule, RuleCategory, Severity
from app.analysis.graph_builder import CodeGraph
from app.analysis.models import SymbolKind

__all__ = ['MissingDocRule']


class MissingDocRule(HealthRule):
    rule_id = "DOC001"
    rule_name = "missing_doc"
    category = RuleCategory.DOCUMENTATION
    severity = Severity.INFO
    description = "Public symbol lacks documentation"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        for sym in graph.symbols.values():
            if sym.kind not in (
                SymbolKind.CLASS,
                SymbolKind.INTERFACE,
                SymbolKind.STRUCT,
                SymbolKind.METHOD,
            ):
                continue
            is_public = "public" in sym.modifiers or "pub" in sym.modifiers
            if not is_public and sym.modifiers:
                continue
            if not sym.doc_comment:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message="Public symbol has no documentation",
                        suggestion="Add a doc comment describing purpose and behavior",
                    )
                )
        return findings


# ==================================================================
# NAMING rules
# ==================================================================



