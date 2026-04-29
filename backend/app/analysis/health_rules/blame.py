"""
Health rules: git blame / churn.

Rules that use git blame data (last_author, commit_count, author_count)
to identify hotspots, stale code, and bus factor risks.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from app.analysis.code_health import (
    HealthConfig,
    HealthFinding,
    HealthRule,
    RuleCategory,
    Severity,
)
from app.analysis.graph_builder import CodeGraph
from app.analysis.models import SymbolKind

__all__ = [
    "HotspotRule",
    "StaleCodeRule",
    "BusFactorRule",
    "RecentChurnRule",
]


class HotspotRule(HealthRule):
    rule_id = "GB001"
    rule_name = "hotspot"
    category = RuleCategory.COMPLEXITY
    severity = Severity.WARNING
    description = "High-churn function with high complexity (hotspot)"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings: list[HealthFinding] = []
        for sym in graph.symbols.values():
            if sym.kind not in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR):
                continue
            cc = sym.cyclomatic_complexity
            churn = getattr(sym, "commit_count", 0) or 0
            if churn >= 5 and cc >= 10:
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
                            f"Hotspot: {churn} commits and CC={cc}"
                        ),
                        suggestion=(
                            "Frequently-changed complex code is high-risk; "
                            "refactor to reduce complexity"
                        ),
                    )
                )
        return findings


class StaleCodeRule(HealthRule):
    rule_id = "GB002"
    rule_name = "stale_code"
    category = RuleCategory.DESIGN
    severity = Severity.INFO
    description = "Function unchanged for >1 year with no callers"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings: list[HealthFinding] = []
        now = datetime.now(UTC)
        one_year_seconds = 365 * 24 * 3600

        for sym in graph.symbols.values():
            if sym.kind not in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR):
                continue
            last_mod = getattr(sym, "last_modified_at", None)
            if last_mod is None:
                continue
            if isinstance(last_mod, str):
                try:
                    last_mod = datetime.fromisoformat(last_mod)
                except (ValueError, TypeError):
                    continue
            if last_mod.tzinfo is None:
                last_mod = last_mod.replace(tzinfo=UTC)
            age = (now - last_mod).total_seconds()
            if age < one_year_seconds:
                continue
            # Check if no callers
            callers = graph.get_callers(sym.fq_name)
            if len(callers) > 0:
                continue
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
                        f"Last modified {int(age / (24*3600))} days ago "
                        f"with no callers"
                    ),
                    suggestion="Consider removing if truly unused",
                )
            )
        return findings


class BusFactorRule(HealthRule):
    rule_id = "GB003"
    rule_name = "bus_factor"
    category = RuleCategory.DESIGN
    severity = Severity.WARNING
    description = "Module has only 1 author across all functions"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings: list[HealthFinding] = []
        # Group by module (namespace)
        module_authors: dict[str, set[str]] = defaultdict(set)
        module_symbols: dict[str, int] = defaultdict(int)
        module_files: dict[str, set[str]] = defaultdict(set)

        for sym in graph.symbols.values():
            if sym.kind not in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR):
                continue
            author = getattr(sym, "last_author", "") or ""
            if not author:
                continue
            mod = sym.namespace or sym.file_path.rsplit("/", 1)[0]
            module_authors[mod].add(author)
            module_symbols[mod] += 1
            module_files[mod].add(sym.file_path)

        for mod, authors in module_authors.items():
            # Only flag modules with enough symbols to matter
            if module_symbols[mod] < 5 or len(module_files[mod]) < 2:
                continue
            if len(authors) == 1:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=f"module:{mod}",
                        file_path=next(iter(module_files[mod])),
                        line=0,
                        message=(
                            f"Module '{mod}' has {module_symbols[mod]} "
                            f"functions by only 1 author: "
                            f"{next(iter(authors))}"
                        ),
                        suggestion=(
                            "Encourage code review and shared ownership "
                            "to reduce bus factor risk"
                        ),
                    )
                )
        return findings


class RecentChurnRule(HealthRule):
    rule_id = "GB004"
    rule_name = "recent_churn"
    category = RuleCategory.DESIGN
    severity = Severity.INFO
    description = "Function has many commits (high churn)"

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        findings: list[HealthFinding] = []
        threshold = getattr(config, "max_commit_count", 10)
        for sym in graph.symbols.values():
            if sym.kind not in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR):
                continue
            churn = getattr(sym, "commit_count", 0) or 0
            if churn > threshold:
                findings.append(
                    HealthFinding(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        category=self.category,
                        severity=self.severity,
                        symbol_fq_name=sym.fq_name,
                        file_path=sym.file_path,
                        line=sym.start_line,
                        message=f"{churn} commits on this function",
                        suggestion=(
                            "Frequently-changed code may need "
                            "better abstraction or tests"
                        ),
                    )
                )
        return findings
