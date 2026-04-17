"""
Answer evaluator.

Scores Q&A answers for citation coverage, factual grounding,
and completeness against the retrieval context.
"""

from __future__ import annotations

from typing import Any

from app.guardrails.models import EvalCategory, EvalCheck, EvalSeverity


def check_citation_coverage(
    answer_text: str,
    citations: list[dict[str, Any]],
    known_files: set[str],
) -> EvalCheck:
    """
    Verify that cited files actually exist in the snapshot.
    """
    if not citations:
        return EvalCheck(
            category=EvalCategory.CITATION_COVERAGE,
            name="citation_coverage",
            passed=True,
            severity=EvalSeverity.WARNING,
            score=0.5,
            message="No citations provided with the answer.",
        )

    valid = 0
    invalid_files: list[str] = []
    for cite in citations:
        fp = cite.get("file_path", "")
        if fp and fp in known_files:
            valid += 1
        elif fp:
            invalid_files.append(fp)

    total = len(citations)
    score = valid / total if total > 0 else 0.0
    passed = score >= 0.8

    return EvalCheck(
        category=EvalCategory.CITATION_COVERAGE,
        name="citation_coverage",
        passed=passed,
        severity=EvalSeverity.PASS if passed else EvalSeverity.WARNING,
        score=score,
        message=f"{valid}/{total} citations reference valid files.",
        details={"invalid_files": invalid_files[:5]},
    )


def check_factual_grounding(
    answer_text: str,
    known_symbols: set[str],
    known_files: set[str],
) -> EvalCheck:
    """
    Check that the answer text references real symbols/files.
    An answer that mentions many non-existent symbols is poorly grounded.
    """
    import re

    backtick_refs = set(re.findall(r"`([A-Za-z_][\w.]*)`", answer_text))
    if not backtick_refs:
        return EvalCheck(
            category=EvalCategory.FACTUAL_GROUNDING,
            name="factual_grounding",
            passed=True,
            severity=EvalSeverity.PASS,
            score=0.7,
            message="No backtick references in answer.",
        )

    grounded = 0
    for ref in backtick_refs:
        if ref in known_symbols or ref in known_files:
            grounded += 1
        elif any(ref in s for s in known_symbols):
            grounded += 1

    total = len(backtick_refs)
    score = grounded / total if total > 0 else 0.0
    passed = score >= 0.6

    return EvalCheck(
        category=EvalCategory.FACTUAL_GROUNDING,
        name="factual_grounding",
        passed=passed,
        severity=EvalSeverity.PASS if passed else EvalSeverity.WARNING,
        score=score,
        message=f"{grounded}/{total} references grounded in codebase.",
    )


def check_answer_completeness(
    answer_text: str,
    expected_symbols: list[str],
) -> EvalCheck:
    """
    Check whether the answer mentions the key symbols that should
    be covered (based on the question and retrieval context).
    """
    if not expected_symbols:
        return EvalCheck(
            category=EvalCategory.FACTUAL_GROUNDING,
            name="answer_completeness",
            passed=True,
            severity=EvalSeverity.PASS,
            score=1.0,
            message="No specific symbols expected.",
        )

    mentioned = 0
    for sym in expected_symbols:
        # Check full name or last segment
        short = sym.rsplit(".", 1)[-1]
        if sym in answer_text or short in answer_text:
            mentioned += 1

    total = len(expected_symbols)
    score = mentioned / total if total > 0 else 0.0
    passed = score >= 0.5

    return EvalCheck(
        category=EvalCategory.FACTUAL_GROUNDING,
        name="answer_completeness",
        passed=passed,
        severity=EvalSeverity.PASS if passed else EvalSeverity.WARNING,
        score=score,
        message=f"{mentioned}/{total} expected symbols mentioned.",
    )
