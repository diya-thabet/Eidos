"""
Health score computation and grading.

Computes a 0-100 health score from snapshot metrics stored in the DB.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Category weights (sum = 100)
_WEIGHTS: dict[str, int] = {
    "complexity": 20,
    "design": 20,
    "duplication": 10,
    "dead_code": 10,
    "documentation": 5,
    "naming": 5,
    "security": 15,
    "dependencies": 10,
    "testing": 5,
}


@dataclass
class CategoryScore:
    """Score for a single category."""

    category: str
    score: float  # 0-100
    weight: int
    weighted_score: float
    details: str = ""


@dataclass
class HealthScore:
    """Complete health score for a snapshot."""

    overall: float = 100.0
    grade: str = "A"
    categories: list[CategoryScore] = field(default_factory=list)
    total_findings: int = 0
    error_count: int = 0
    warning_count: int = 0


def compute_health_score(metrics: dict[str, Any]) -> HealthScore:
    """Compute a health score from snapshot metrics.

    Args:
        metrics: Dict with keys like:
            - error_count, warning_count, info_count
            - avg_cyclomatic_complexity, max_cyclomatic_complexity
            - long_function_count, total_methods
            - clone_group_count
            - dead_function_count
            - undocumented_public_count, total_public_count
            - naming_violations
            - security_findings
            - dependency_issues
            - has_tests (bool)
            - total_findings
    """
    categories: list[CategoryScore] = []

    # 1. Complexity (20%)
    avg_cc = metrics.get("avg_cyclomatic_complexity", 0)
    max_cc = metrics.get("max_cyclomatic_complexity", 0)
    long_funcs = metrics.get("long_function_count", 0)
    total_methods = max(metrics.get("total_methods", 1), 1)
    long_pct = (long_funcs / total_methods) * 100
    complexity_score = 100.0
    complexity_score -= min(avg_cc * 3, 30)  # avg CC penalty
    complexity_score -= min(max_cc * 0.5, 20)  # max CC penalty
    complexity_score -= min(long_pct, 50)  # long functions penalty
    complexity_score = max(complexity_score, 0)
    categories.append(CategoryScore(
        category="complexity", score=round(complexity_score, 1),
        weight=_WEIGHTS["complexity"],
        weighted_score=round(complexity_score * _WEIGHTS["complexity"] / 100, 2),
        details=f"avg_cc={avg_cc:.1f}, max_cc={max_cc}, long_funcs={long_funcs}",
    ))

    # 2. Design (20%) - based on error-level findings
    errors = metrics.get("error_count", 0)
    design_score = max(100 - errors * 5, 0)
    categories.append(CategoryScore(
        category="design", score=round(design_score, 1),
        weight=_WEIGHTS["design"],
        weighted_score=round(design_score * _WEIGHTS["design"] / 100, 2),
        details=f"errors={errors}",
    ))

    # 3. Duplication (10%)
    clones = metrics.get("clone_group_count", 0)
    dup_score = max(100 - clones * 10, 0)
    categories.append(CategoryScore(
        category="duplication", score=round(dup_score, 1),
        weight=_WEIGHTS["duplication"],
        weighted_score=round(dup_score * _WEIGHTS["duplication"] / 100, 2),
        details=f"clone_groups={clones}",
    ))

    # 4. Dead code (10%)
    dead = metrics.get("dead_function_count", 0)
    dead_score = max(100 - dead * 5, 0)
    categories.append(CategoryScore(
        category="dead_code", score=round(dead_score, 1),
        weight=_WEIGHTS["dead_code"],
        weighted_score=round(dead_score * _WEIGHTS["dead_code"] / 100, 2),
        details=f"dead_functions={dead}",
    ))

    # 5. Documentation (5%)
    undoc = metrics.get("undocumented_public_count", 0)
    total_pub = max(metrics.get("total_public_count", 1), 1)
    doc_pct = ((total_pub - undoc) / total_pub) * 100
    categories.append(CategoryScore(
        category="documentation", score=round(doc_pct, 1),
        weight=_WEIGHTS["documentation"],
        weighted_score=round(doc_pct * _WEIGHTS["documentation"] / 100, 2),
        details=f"documented={total_pub - undoc}/{total_pub}",
    ))

    # 6. Naming (5%)
    naming = metrics.get("naming_violations", 0)
    naming_score = max(100 - naming * 3, 0)
    categories.append(CategoryScore(
        category="naming", score=round(naming_score, 1),
        weight=_WEIGHTS["naming"],
        weighted_score=round(naming_score * _WEIGHTS["naming"] / 100, 2),
        details=f"violations={naming}",
    ))

    # 7. Security (15%)
    sec = metrics.get("security_findings", 0)
    sec_score = max(100 - sec * 15, 0)
    categories.append(CategoryScore(
        category="security", score=round(sec_score, 1),
        weight=_WEIGHTS["security"],
        weighted_score=round(sec_score * _WEIGHTS["security"] / 100, 2),
        details=f"findings={sec}",
    ))

    # 8. Dependencies (10%)
    dep_issues = metrics.get("dependency_issues", 0)
    dep_score = max(100 - dep_issues * 8, 0)
    categories.append(CategoryScore(
        category="dependencies", score=round(dep_score, 1),
        weight=_WEIGHTS["dependencies"],
        weighted_score=round(dep_score * _WEIGHTS["dependencies"] / 100, 2),
        details=f"issues={dep_issues}",
    ))

    # 9. Testing (5%)
    has_tests = metrics.get("has_tests", False)
    coverage = metrics.get("coverage_percent", 0)
    test_score = 50.0 if has_tests else 0.0
    test_score += min(coverage / 2, 50)  # up to 50 more from coverage
    categories.append(CategoryScore(
        category="testing", score=round(test_score, 1),
        weight=_WEIGHTS["testing"],
        weighted_score=round(test_score * _WEIGHTS["testing"] / 100, 2),
        details=f"has_tests={has_tests}, coverage={coverage:.1f}%",
    ))

    # Compute overall weighted score
    overall = sum(c.weighted_score for c in categories)
    overall = round(min(max(overall, 0), 100), 1)

    return HealthScore(
        overall=overall,
        grade=_grade(overall),
        categories=categories,
        total_findings=metrics.get("total_findings", 0),
        error_count=metrics.get("error_count", 0),
        warning_count=metrics.get("warning_count", 0),
    )


def _grade(score: float) -> str:
    """Convert score to letter grade."""
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"
