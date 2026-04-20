"""
Code health analysis engine.

Provides a rule-based static analysis system that checks code for:
- Clean code principles (naming, method length, parameter count, etc.)
- SOLID principles (SRP, OCP, LSP, ISP, DIP)
- Best practices (error handling, documentation, complexity)
- Design patterns and anti-patterns

Each rule produces findings with severity, and the user can select
which rule categories to enable per request.

Optional LLM integration for deeper semantic analysis (naming quality,
design pattern suggestions, refactoring advice).
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from typing import Any

from app.analysis.graph_builder import CodeGraph
from app.analysis.models import EdgeType, SymbolKind

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Data models
# ------------------------------------------------------------------


class Severity(enum.StrEnum):
    """Finding severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class RuleCategory(enum.StrEnum):
    """Broad categories of code health rules."""

    CLEAN_CODE = "clean_code"
    SOLID = "solid"
    BEST_PRACTICES = "best_practices"
    COMPLEXITY = "complexity"
    DOCUMENTATION = "documentation"
    NAMING = "naming"
    DESIGN = "design"
    SECURITY = "security"


@dataclass
class HealthFinding:
    """A single code health finding."""

    rule_id: str
    rule_name: str
    category: str
    severity: str
    symbol_fq_name: str
    file_path: str
    line: int
    message: str
    suggestion: str = ""


@dataclass
class HealthConfig:
    """User-configurable health check settings."""

    # Which categories to enable (empty = all)
    categories: list[str] = field(default_factory=list)
    # Which specific rules to disable
    disabled_rules: list[str] = field(default_factory=list)
    # Thresholds (user can override)
    max_method_lines: int = 30
    max_class_lines: int = 300
    max_parameters: int = 5
    max_fan_out: int = 10
    max_fan_in: int = 15
    max_children: int = 20
    max_inheritance_depth: int = 4
    min_doc_coverage: float = 0.5
    max_god_class_methods: int = 15
    max_return_type_none: int = 0  # methods with unclear return
    # LLM-powered analysis
    use_llm: bool = False

    @staticmethod
    def all_rules() -> list[dict[str, str]]:
        """Return metadata for every available rule."""
        return [r.metadata() for r in ALL_RULES]


@dataclass
class HealthReport:
    """Complete code health report."""

    total_symbols: int = 0
    total_files: int = 0
    findings: list[HealthFinding] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)  # severity -> count
    category_scores: dict[str, float] = field(default_factory=dict)  # category -> 0-100
    overall_score: float = 100.0
    llm_insights: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_symbols": self.total_symbols,
            "total_files": self.total_files,
            "findings_count": len(self.findings),
            "findings": [
                {
                    "rule_id": f.rule_id,
                    "rule_name": f.rule_name,
                    "category": f.category,
                    "severity": f.severity,
                    "symbol": f.symbol_fq_name,
                    "file": f.file_path,
                    "line": f.line,
                    "message": f.message,
                    "suggestion": f.suggestion,
                }
                for f in self.findings
            ],
            "summary": self.summary,
            "category_scores": self.category_scores,
            "overall_score": round(self.overall_score, 1),
            "llm_insights": self.llm_insights,
        }


# ------------------------------------------------------------------
# Rule base class
# ------------------------------------------------------------------


class HealthRule:
    """Base class for all code health rules."""

    rule_id: str = ""
    rule_name: str = ""
    category: str = ""
    severity: str = Severity.WARNING
    description: str = ""

    def check(self, graph: CodeGraph, config: HealthConfig) -> list[HealthFinding]:
        raise NotImplementedError

    @classmethod
    def metadata(cls) -> dict[str, str]:
        return {
            "rule_id": cls.rule_id,
            "rule_name": cls.rule_name,
            "category": cls.category,
            "severity": cls.severity,
            "description": cls.description,
        }


# ==================================================================
# CLEAN CODE rules
# ==================================================================


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


# ==================================================================
# Registry
# ==================================================================

ALL_RULES: list[HealthRule] = [
    # Clean Code
    LongMethodRule(),
    LongClassRule(),
    TooManyParametersRule(),
    EmptyMethodRule(),
    ConstructorOverInjectionRule(),
    VoidAbuseRule(),
    StaticAbuseRule(),
    MutablePublicStateRule(),
    # SOLID
    GodClassRule(),
    DeepInheritanceRule(),
    FatInterfaceRule(),
    NoAbstractionDependencyRule(),
    SwissArmyKnifeRule(),
    # Complexity / Metrics
    HighFanOutRule(),
    HighFanInRule(),
    TooManyChildrenRule(),
    CouplingBetweenObjectsRule(),
    LackOfCohesionRule(),
    ComplexityDensityRule(),
    # Documentation
    MissingDocRule(),
    # Naming
    ShortNameRule(),
    BooleanNameRule(),
    InconsistentNamingRule(),
    PrefixedNameRule(),
    # Design / Code Smells
    CircularDependencyRule(),
    OrphanClassRule(),
    DeadMethodRule(),
    FeatureEnvyRule(),
    DataClassSmellRule(),
    ShotgunSurgeryRule(),
    MiddleManRule(),
    SpeculativeGeneralityRule(),
    LazyClassRule(),
    # Architecture
    ModuleTangleRule(),
    DeepNamespaceRule(),
    # Security
    HardcodedSecretRule(),
    SqlInjectionRiskRule(),
    InsecureFieldRule(),
    # Best Practices
    LargeFileRule(),
    UnusedImportRule(),
]


# ------------------------------------------------------------------
# Engine
# ------------------------------------------------------------------


def run_health_check(graph: CodeGraph, config: HealthConfig | None = None) -> HealthReport:
    """Run all enabled rules against the code graph."""
    if config is None:
        config = HealthConfig()

    report = HealthReport(
        total_symbols=len(graph.symbols),
        total_files=len(graph.files),
    )

    enabled_categories = set(config.categories) if config.categories else None
    disabled = set(config.disabled_rules)

    category_findings: dict[str, int] = {}
    category_totals: dict[str, int] = {}

    for rule in ALL_RULES:
        if rule.rule_id in disabled:
            continue
        if enabled_categories and rule.category not in enabled_categories:
            continue

        try:
            findings = rule.check(graph, config)
        except Exception:
            logger.exception("Rule %s failed", rule.rule_id)
            continue

        report.findings.extend(findings)
        cat = rule.category
        category_findings[cat] = category_findings.get(cat, 0) + len(findings)
        category_totals[cat] = category_totals.get(cat, 0) + 1

    # Severity summary
    for f in report.findings:
        report.summary[f.severity] = report.summary.get(f.severity, 0) + 1

    # Category scores (100 = no findings, deduct per finding)
    for cat in category_totals:
        count = category_findings.get(cat, 0)
        symbols = max(report.total_symbols, 1)
        ratio = count / symbols
        report.category_scores[cat] = max(0.0, round(100.0 * (1 - ratio), 1))

    # Overall score
    total_syms = max(report.total_symbols, 1)
    # Weight: critical=10, error=5, warning=2, info=1
    weights = {"critical": 10, "error": 5, "warning": 2, "info": 1}
    penalty = sum(weights.get(f.severity, 1) for f in report.findings)
    report.overall_score = max(0.0, 100.0 - (penalty / total_syms) * 10)

    report.findings.sort(
        key=lambda f: (
            {"critical": 0, "error": 1, "warning": 2, "info": 3}.get(f.severity, 4),
            f.file_path,
            f.line,
        )
    )

    return report


# ------------------------------------------------------------------
# LLM-powered analysis
# ------------------------------------------------------------------


async def run_llm_health_analysis(
    graph: CodeGraph,
    report: HealthReport,
    llm_client: Any,
) -> list[dict[str, str]]:
    """
    Use an LLM to provide deeper insights on the code health findings.

    Generates:
    - Naming quality assessment
    - Design pattern suggestions
    - Refactoring recommendations
    - Architecture improvement advice
    """
    if not llm_client:
        return []

    # Build a concise summary for the LLM
    top_findings = report.findings[:20]
    symbols_summary = []
    for sym in list(graph.symbols.values())[:50]:
        symbols_summary.append(
            f"- {sym.kind.value} {sym.fq_name} "
            f"({sym.end_line - sym.start_line + 1} lines, "
            f"fan_in={graph.fan_in(sym.fq_name)}, "
            f"fan_out={graph.fan_out(sym.fq_name)})"
        )

    findings_text = "\n".join(
        f"- [{f.severity}] {f.rule_name}: {f.message} ({f.symbol_fq_name})" for f in top_findings
    )

    system_prompt = (
        "You are a senior software architect reviewing code health. "
        "Provide concise, actionable insights. Format each insight as a JSON object "
        "with 'category', 'title', and 'recommendation' fields. "
        "Return a JSON array of insights."
    )
    user_message = (
        f"Code health score: {report.overall_score}/100\n"
        f"Total symbols: {report.total_symbols}\n"
        f"Total findings: {len(report.findings)}\n\n"
        f"Top findings:\n{findings_text}\n\n"
        f"Key symbols:\n" + "\n".join(symbols_summary[:30])
    )

    try:
        result = await llm_client.chat_json(system_prompt, user_message)
        insights: list[dict[str, str]]
        if isinstance(result, list):
            insights = result
        elif isinstance(result, dict) and "insights" in result:
            insights = result["insights"]
        else:
            insights = [result]
        return insights
    except Exception:
        logger.exception("LLM health analysis failed")
        return [
            {
                "category": "error",
                "title": "LLM analysis unavailable",
                "recommendation": "Configure EIDOS_LLM_BASE_URL for AI-powered insights",
            }
        ]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _get_parent_class(fq_name: str, graph: CodeGraph) -> str:
    """Get the parent class/struct FQ name for a symbol."""
    sym = graph.symbols.get(fq_name)
    if sym and sym.parent_fq_name:
        return sym.parent_fq_name
    parts = fq_name.rsplit(".", 1)
    return parts[0] if len(parts) > 1 else ""
