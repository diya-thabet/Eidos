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



# Import all rules from category modules
from app.analysis.health_rules.best_practices import (  # noqa: E402
    DeepNamespaceRule,
    LargeFileRule,
    UnusedImportRule,
)
from app.analysis.health_rules.blame import (  # noqa: E402
    BusFactorRule,
    HotspotRule,
    RecentChurnRule,
    StaleCodeRule,
)
from app.analysis.health_rules.clean_code import (  # noqa: E402
    ConstructorOverInjectionRule,
    EmptyMethodRule,
    LongClassRule,
    LongMethodRule,
    MutablePublicStateRule,
    StaticAbuseRule,
    TooManyParametersRule,
    VoidAbuseRule,
)
from app.analysis.health_rules.complexity import (  # noqa: E402
    ComplexityDensityRule,
    ComplexityPerLineRule,
    CouplingBetweenObjectsRule,
    HighCognitiveRule,
    HighCyclomaticRule,
    HighFanInRule,
    HighFanOutRule,
    LackOfCohesionRule,
    TooManyChildrenRule,
    VeryHighCognitiveRule,
    VeryHighCyclomaticRule,
)
from app.analysis.health_rules.dependencies import (  # noqa: E402
    DevInProductionRule,
    DuplicateDependencyRule,
    UnpinnedDependencyRule,
    UnusedDependencyRule,
    WideVersionRangeRule,
)
from app.analysis.health_rules.design import (  # noqa: E402
    CircularDependencyRule,
    DataClassSmellRule,
    DeadMethodRule,
    FeatureEnvyRule,
    LazyClassRule,
    MiddleManRule,
    ModuleTangleRule,
    OrphanClassRule,
    ShotgunSurgeryRule,
    SpeculativeGeneralityRule,
)
from app.analysis.health_rules.documentation import MissingDocRule  # noqa: E402
from app.analysis.health_rules.naming import (  # noqa: E402
    BooleanNameRule,
    InconsistentNamingRule,
    PrefixedNameRule,
    ShortNameRule,
)
from app.analysis.health_rules.security import (  # noqa: E402
    HardcodedSecretRule,
    InsecureFieldRule,
    SqlInjectionRiskRule,
)
from app.analysis.health_rules.solid import (  # noqa: E402
    DeepInheritanceRule,
    FatInterfaceRule,
    GodClassRule,
    NoAbstractionDependencyRule,
    SwissArmyKnifeRule,
)

# ------------------------------------------------------------------
# Rule registry
# ------------------------------------------------------------------

ALL_RULES: list[HealthRule] = [
    # Clean Code (8)
    LongMethodRule(),
    LongClassRule(),
    TooManyParametersRule(),
    EmptyMethodRule(),
    ConstructorOverInjectionRule(),
    VoidAbuseRule(),
    StaticAbuseRule(),
    MutablePublicStateRule(),
    # SOLID (5)
    GodClassRule(),
    DeepInheritanceRule(),
    FatInterfaceRule(),
    NoAbstractionDependencyRule(),
    SwissArmyKnifeRule(),
    # Complexity (6)
    HighFanOutRule(),
    HighFanInRule(),
    TooManyChildrenRule(),
    CouplingBetweenObjectsRule(),
    LackOfCohesionRule(),
    ComplexityDensityRule(),
    # Complexity: cyclomatic/cognitive (5)
    HighCyclomaticRule(),
    VeryHighCyclomaticRule(),
    HighCognitiveRule(),
    VeryHighCognitiveRule(),
    ComplexityPerLineRule(),
    # Design (10)
    CircularDependencyRule(),
    OrphanClassRule(),
    DeadMethodRule(),
    FeatureEnvyRule(),
    DataClassSmellRule(),
    ShotgunSurgeryRule(),
    MiddleManRule(),
    SpeculativeGeneralityRule(),
    LazyClassRule(),
    ModuleTangleRule(),
    # Documentation (1)
    MissingDocRule(),
    # Naming (4)
    ShortNameRule(),
    BooleanNameRule(),
    InconsistentNamingRule(),
    PrefixedNameRule(),
    # Best Practices (3)
    LargeFileRule(),
    UnusedImportRule(),
    DeepNamespaceRule(),
    # Security (3)
    HardcodedSecretRule(),
    SqlInjectionRiskRule(),
    InsecureFieldRule(),
    # Dependencies (5)
    UnpinnedDependencyRule(),
    WideVersionRangeRule(),
    UnusedDependencyRule(),
    DuplicateDependencyRule(),
    DevInProductionRule(),
    # Git Blame / Churn (4)
    HotspotRule(),
    StaleCodeRule(),
    BusFactorRule(),
    RecentChurnRule(),
]


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
