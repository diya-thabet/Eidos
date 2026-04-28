"""
Health rules: best_practices.

Rules: LargeFileRule, UnusedImportRule, DeepNamespaceRule
"""

from __future__ import annotations

from app.analysis.code_health import HealthConfig, HealthFinding, HealthRule, RuleCategory, Severity
from app.analysis.graph_builder import CodeGraph

__all__ = ['LargeFileRule', 'UnusedImportRule', 'DeepNamespaceRule']


class LargeFileRule(HealthRule):
    rule_id = "BP001"
    rule_name = "large_file"
    category = RuleCategory.BEST_PRACTICES
    severity = Severity.WARNING
    description = "File contains too many symbols"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        file_symbols: dict[str, int] = {}
        for sym in graph.symbols.values():
            file_symbols[sym.file_path] = file_symbols.get(sym.file_path, 0) + 1
        for path, count in file_symbols.items():
            if count > 30:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=path,
                        file_path=path,
                        line=1,
                        message=f"File has {count} symbols (consider splitting)",
                        suggestion="Break into multiple files grouped by responsibility",
                    )
                )
        return findings



class UnusedImportRule(HealthRule):
    rule_id = "BP002"
    rule_name = "excessive_imports"
    category = RuleCategory.BEST_PRACTICES
    severity = Severity.INFO
    description = "File has too many imports (>15)"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        for path, fa in graph.files.items():
            if len(fa.using_directives) > 15:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=path,
                        file_path=path,
                        line=1,
                        message=f"File has {len(fa.using_directives)} imports",
                        suggestion="Review imports; many imports suggest too many responsibilities",
                    )
                )
        return findings


# ==================================================================
# CODE SMELL rules (Martin Fowler catalogue)
# ==================================================================



class DeepNamespaceRule(HealthRule):
    rule_id = "AR002"
    rule_name = "deep_namespace"
    category = RuleCategory.BEST_PRACTICES
    severity = Severity.INFO
    description = "Namespace nesting is too deep (>5 levels)"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        seen_ns: set[str] = set()
        for sym in graph.symbols.values():
            ns = sym.namespace
            if ns and ns not in seen_ns:
                seen_ns.add(ns)
                depth = ns.count(".") + 1
                if depth > 5:
                    findings.append(
                        HealthFinding(
                            rule_id=self.rule_id,
                            rule_name=self.rule_name,
                            category=self.category,
                            severity=self.severity,
                            symbol_fq_name=ns,
                            file_path=sym.file_path,
                            line=1,
                            message=f"Namespace depth is {depth} (max 5)",
                            suggestion="Flatten namespace hierarchy",
                        )
                    )
        return findings



