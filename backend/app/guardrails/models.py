"""
Data models for the evaluation & guardrails engine.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class EvalCategory(enum.StrEnum):
    """Category of evaluation check."""

    HALLUCINATION = "hallucination"
    CITATION_COVERAGE = "citation_coverage"
    FACTUAL_GROUNDING = "factual_grounding"
    DOC_COMPLETENESS = "doc_completeness"
    DOC_STALENESS = "doc_staleness"
    REVIEW_PRECISION = "review_precision"
    INPUT_SANITIZATION = "input_sanitization"
    OUTPUT_SANITIZATION = "output_sanitization"
    OVERALL = "overall"


class EvalSeverity(enum.StrEnum):
    """How serious the evaluation finding is."""

    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


@dataclass
class EvalCheck:
    """A single evaluation check result."""

    category: EvalCategory
    name: str
    passed: bool
    severity: EvalSeverity
    score: float = 1.0  # 0.0 to 1.0
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalReport:
    """Complete evaluation report for a snapshot or artifact."""

    snapshot_id: str
    scope: str = ""  # e.g. "answer:xyz", "doc:readme", "review:1"
    checks: list[EvalCheck] = field(default_factory=list)
    overall_score: float = 0.0  # 0.0 to 1.0
    overall_severity: EvalSeverity = EvalSeverity.PASS
    summary: str = ""

    def compute_overall(self) -> None:
        """Recompute overall score and severity from individual checks."""
        if not self.checks:
            self.overall_score = 1.0
            self.overall_severity = EvalSeverity.PASS
            return

        self.overall_score = sum(c.score for c in self.checks) / len(self.checks)

        if any(c.severity == EvalSeverity.FAIL for c in self.checks):
            self.overall_severity = EvalSeverity.FAIL
        elif any(c.severity == EvalSeverity.WARNING for c in self.checks):
            self.overall_severity = EvalSeverity.WARNING
        else:
            self.overall_severity = EvalSeverity.PASS

        fails = [c for c in self.checks if not c.passed]
        if fails:
            names = ", ".join(c.name for c in fails[:3])
            self.summary = f"{len(fails)} check(s) failed: {names}"
        else:
            self.summary = f"All {len(self.checks)} checks passed."


@dataclass
class SanitizationResult:
    """Result of input/output sanitization."""

    clean_text: str
    was_modified: bool = False
    issues: list[str] = field(default_factory=list)
