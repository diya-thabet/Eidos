"""
Health rules: security.

Rules: HardcodedSecretRule, SqlInjectionRiskRule, InsecureFieldRule
"""

from __future__ import annotations

from app.analysis.code_health import HealthConfig, HealthFinding, HealthRule, RuleCategory, Severity
from app.analysis.graph_builder import CodeGraph
from app.analysis.models import SymbolKind

__all__ = ['HardcodedSecretRule', 'SqlInjectionRiskRule', 'InsecureFieldRule']


class HardcodedSecretRule(HealthRule):
    rule_id = "SEC001"
    rule_name = "hardcoded_secret"
    category = RuleCategory.SECURITY
    severity = Severity.CRITICAL
    description = "Symbol name suggests hardcoded secret/password"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        suspect_names = {
            "password",
            "passwd",
            "secret",
            "api_key",
            "apikey",
            "token",
            "private_key",
            "privatekey",
            "access_key",
        }
        for sym in graph.symbols.values():
            if sym.kind != SymbolKind.FIELD:
                continue
            lower = sym.name.lower()
            if any(s in lower for s in suspect_names):
                if sym.return_type.lower() in ("string", "str", "&str", "String"):
                    findings.append(
                        HealthFinding(
                            rule_id=self.rule_id,
                            rule_name=self.rule_name,
                            category=self.category,
                            severity=self.severity,
                            symbol_fq_name=sym.fq_name,
                            file_path=sym.file_path,
                            line=sym.start_line,
                            message=f"Field '{sym.name}' may contain a hardcoded secret",
                            suggestion="Use environment variables or a secrets manager",
                        )
                    )
        return findings


# ==================================================================
# BEST PRACTICES rules
# ==================================================================



class SqlInjectionRiskRule(HealthRule):
    rule_id = "SEC002"
    rule_name = "sql_injection_risk"
    category = RuleCategory.SECURITY
    severity = Severity.CRITICAL
    description = "Method name suggests raw SQL usage"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        suspect_names = {
            "execute_raw",
            "raw_sql",
            "executeRaw",
            "rawSql",
            "rawQuery",
            "raw_query",
            "execute_sql",
            "executeSql",
        }
        for sym in graph.symbols.values():
            if sym.kind != SymbolKind.METHOD:
                continue
            if sym.name in suspect_names:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message=f"Method '{sym.name}' suggests raw SQL execution",
                        suggestion="Use parameterized queries to prevent SQL injection",
                    )
                )
        return findings



class InsecureFieldRule(HealthRule):
    rule_id = "SEC003"
    rule_name = "insecure_field"
    category = RuleCategory.SECURITY
    severity = Severity.WARNING
    description = "Publicly exposed field with sensitive name"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings = []
        sensitive = {"password", "secret", "token", "key", "credential"}
        for sym in graph.symbols.values():
            if sym.kind != SymbolKind.FIELD:
                continue
            is_public = "public" in sym.modifiers or "pub" in sym.modifiers
            if not is_public:
                continue
            lower = sym.name.lower()
            for s in sensitive:
                if s in lower:
                    findings.append(
                        HealthFinding(
                            rule_id=self.rule_id,
                            rule_name=self.rule_name,
                            category=self.category,
                            severity=self.severity,
                            symbol_fq_name=sym.fq_name,
                            file_path=sym.file_path,
                            line=sym.start_line,
                            message=f"Public field '{sym.name}' contains sensitive data",
                            suggestion="Make private; expose through controlled accessors",
                        )
                    )
                    break
        return findings

