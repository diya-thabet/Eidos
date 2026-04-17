"""
Document evaluator.

Scores generated documentation for completeness, accuracy,
and staleness relative to the current snapshot data.
"""

from __future__ import annotations

from app.guardrails.models import EvalCategory, EvalCheck, EvalSeverity


def check_doc_completeness(
    markdown: str,
    expected_sections: list[str],
) -> EvalCheck:
    """
    Check whether the document contains all expected sections.
    """
    if not expected_sections:
        return EvalCheck(
            category=EvalCategory.DOC_COMPLETENESS,
            name="doc_completeness",
            passed=True,
            severity=EvalSeverity.PASS,
            score=1.0,
            message="No expected sections defined.",
        )

    found = 0
    missing: list[str] = []
    for section in expected_sections:
        if section.lower() in markdown.lower():
            found += 1
        else:
            missing.append(section)

    total = len(expected_sections)
    score = found / total if total > 0 else 0.0
    passed = score >= 0.7

    return EvalCheck(
        category=EvalCategory.DOC_COMPLETENESS,
        name="doc_completeness",
        passed=passed,
        severity=EvalSeverity.PASS if passed else EvalSeverity.WARNING,
        score=score,
        message=f"{found}/{total} expected sections found.",
        details={"missing_sections": missing},
    )


def check_doc_symbol_accuracy(
    markdown: str,
    known_symbols: set[str],
    known_files: set[str],
) -> EvalCheck:
    """
    Check that symbols/files referenced in the doc actually exist.
    """
    import re

    refs = set(re.findall(r"`([A-Za-z_][\w.]*)`", markdown))
    if not refs:
        return EvalCheck(
            category=EvalCategory.DOC_COMPLETENESS,
            name="doc_symbol_accuracy",
            passed=True,
            severity=EvalSeverity.PASS,
            score=1.0,
            message="No symbol references in document.",
        )

    valid = 0
    phantom: list[str] = []
    for ref in refs:
        if ref in known_symbols or ref in known_files:
            valid += 1
        elif any(ref in s for s in known_symbols):
            valid += 1
        elif len(ref) > 3:
            phantom.append(ref)

    total = len(refs)
    score = valid / total if total > 0 else 0.0
    passed = score >= 0.6

    return EvalCheck(
        category=EvalCategory.DOC_COMPLETENESS,
        name="doc_symbol_accuracy",
        passed=passed,
        severity=EvalSeverity.PASS if passed else EvalSeverity.WARNING,
        score=score,
        message=f"{valid}/{total} doc references are accurate.",
        details={"phantom_references": phantom[:10]},
    )


def check_doc_staleness(
    doc_snapshot_id: str,
    current_snapshot_id: str,
) -> EvalCheck:
    """
    Check if the document was generated from the current snapshot.
    """
    is_current = doc_snapshot_id == current_snapshot_id
    return EvalCheck(
        category=EvalCategory.DOC_STALENESS,
        name="doc_staleness",
        passed=is_current,
        severity=EvalSeverity.PASS if is_current else EvalSeverity.WARNING,
        score=1.0 if is_current else 0.0,
        message=(
            "Document is from current snapshot."
            if is_current
            else f"Document is stale (from {doc_snapshot_id}, current is {current_snapshot_id})."
        ),
    )


def check_doc_coverage(
    documented_symbols: set[str],
    all_public_symbols: set[str],
) -> EvalCheck:
    """
    Check what fraction of public symbols are covered by documentation.
    """
    if not all_public_symbols:
        return EvalCheck(
            category=EvalCategory.DOC_COMPLETENESS,
            name="doc_coverage",
            passed=True,
            severity=EvalSeverity.PASS,
            score=1.0,
            message="No public symbols to document.",
        )

    covered = documented_symbols & all_public_symbols
    score = len(covered) / len(all_public_symbols)
    passed = score >= 0.5

    return EvalCheck(
        category=EvalCategory.DOC_COMPLETENESS,
        name="doc_coverage",
        passed=passed,
        severity=EvalSeverity.PASS if passed else EvalSeverity.WARNING,
        score=score,
        message=(f"{len(covered)}/{len(all_public_symbols)} public symbols documented."),
    )
