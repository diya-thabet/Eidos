"""
Review evaluator.

Scores PR review findings for precision (are findings real?)
and coverage (did we catch the important things?).
"""

from __future__ import annotations

from typing import Any

from app.guardrails.models import EvalCategory, EvalCheck, EvalSeverity


def check_review_precision(
    findings: list[dict[str, Any]],
    known_symbols: set[str],
    known_files: set[str],
) -> EvalCheck:
    """
    Estimate false positive rate: findings that reference
    non-existent symbols or files are likely false.
    """
    if not findings:
        return EvalCheck(
            category=EvalCategory.REVIEW_PRECISION,
            name="review_precision",
            passed=True,
            severity=EvalSeverity.PASS,
            score=1.0,
            message="No findings to evaluate.",
        )

    grounded = 0
    suspect: list[str] = []

    for f in findings:
        fp = f.get("file_path", "")
        sym = f.get("symbol_fq_name", "")
        file_ok = not fp or fp in known_files
        sym_ok = not sym or sym in known_symbols or any(sym in s for s in known_symbols)
        if file_ok and sym_ok:
            grounded += 1
        else:
            suspect.append(f.get("title", "unknown"))

    total = len(findings)
    score = grounded / total if total > 0 else 0.0
    passed = score >= 0.7

    return EvalCheck(
        category=EvalCategory.REVIEW_PRECISION,
        name="review_precision",
        passed=passed,
        severity=EvalSeverity.PASS if passed else EvalSeverity.WARNING,
        score=score,
        message=f"{grounded}/{total} findings reference real code.",
        details={"suspect_findings": suspect[:5]},
    )


def check_review_severity_distribution(
    findings: list[dict[str, Any]],
) -> EvalCheck:
    """
    Check that the severity distribution is reasonable.
    All-critical or all-info is suspicious.
    """
    if not findings:
        return EvalCheck(
            category=EvalCategory.REVIEW_PRECISION,
            name="severity_distribution",
            passed=True,
            severity=EvalSeverity.PASS,
            score=1.0,
            message="No findings.",
        )

    severities = [f.get("severity", "unknown") for f in findings]
    unique = set(severities)

    if len(findings) >= 3 and len(unique) == 1:
        return EvalCheck(
            category=EvalCategory.REVIEW_PRECISION,
            name="severity_distribution",
            passed=False,
            severity=EvalSeverity.WARNING,
            score=0.5,
            message=(
                f"All {len(findings)} findings have severity '{severities[0]}' -- may lack nuance."
            ),
        )

    counts = {s: severities.count(s) for s in unique}
    return EvalCheck(
        category=EvalCategory.REVIEW_PRECISION,
        name="severity_distribution",
        passed=True,
        severity=EvalSeverity.PASS,
        score=1.0,
        message=f"Severity spread: {counts}.",
    )


def check_review_coverage(
    changed_symbols: list[str],
    findings_symbols: list[str],
) -> EvalCheck:
    """
    Check that findings cover a reasonable fraction of changed symbols.
    """
    if not changed_symbols:
        return EvalCheck(
            category=EvalCategory.REVIEW_PRECISION,
            name="review_coverage",
            passed=True,
            severity=EvalSeverity.PASS,
            score=1.0,
            message="No changed symbols.",
        )

    changed_set = set(changed_symbols)
    covered = set(findings_symbols) & changed_set
    score = len(covered) / len(changed_set)
    passed = score >= 0.3

    return EvalCheck(
        category=EvalCategory.REVIEW_PRECISION,
        name="review_coverage",
        passed=passed,
        severity=EvalSeverity.PASS if passed else EvalSeverity.WARNING,
        score=score,
        message=(f"{len(covered)}/{len(changed_set)} changed symbols have associated findings."),
    )
