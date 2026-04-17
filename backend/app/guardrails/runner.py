"""
Evaluation runner.

Orchestrates all guardrail checks for a snapshot, pulling data from
the database and running each evaluator.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.guardrails.answer_evaluator import (
    check_answer_completeness,
    check_citation_coverage,
    check_factual_grounding,
)
from app.guardrails.doc_evaluator import (
    check_doc_staleness,
    check_doc_symbol_accuracy,
)
from app.guardrails.hallucination_detector import (
    check_hallucinated_relationships,
    check_hallucinated_symbols,
)
from app.guardrails.models import (
    EvalCategory,
    EvalCheck,
    EvalReport,
    EvalSeverity,
)
from app.guardrails.review_evaluator import (
    check_review_coverage,
    check_review_precision,
    check_review_severity_distribution,
)
from app.guardrails.sanitizer import check_output_safety
from app.storage.models import Edge, Evaluation, GeneratedDoc, Review, Symbol

logger = logging.getLogger(__name__)


async def run_snapshot_evaluation(
    db: AsyncSession,
    snapshot_id: str,
) -> EvalReport:
    """
    Run all guardrail checks for a snapshot.

    Evaluates:
    - Generated documents (completeness, accuracy, staleness)
    - PR reviews (precision, severity distribution)
    - Output safety (PII leaks)
    """
    known_symbols, known_files, known_edges = await _fetch_known_data(db, snapshot_id)

    report = EvalReport(
        snapshot_id=snapshot_id,
        scope="snapshot",
    )

    # 1. Evaluate generated docs
    doc_checks = await _evaluate_docs(db, snapshot_id, known_symbols, known_files)
    report.checks.extend(doc_checks)

    # 2. Evaluate PR reviews
    review_checks = await _evaluate_reviews(db, snapshot_id, known_symbols, known_files)
    report.checks.extend(review_checks)

    # 3. Overall coverage check
    report.checks.append(_check_symbol_coverage(known_symbols, known_files))

    report.compute_overall()

    # Persist
    db_eval = Evaluation(
        snapshot_id=snapshot_id,
        scope="snapshot",
        overall_score=report.overall_score,
        overall_severity=report.overall_severity.value,
        checks_json=json.dumps([_check_to_dict(c) for c in report.checks], default=str),
        summary=report.summary,
    )
    db.add(db_eval)
    await db.flush()
    await db.commit()

    logger.info(
        "Evaluation complete for snapshot %s: score=%.2f, severity=%s",
        snapshot_id,
        report.overall_score,
        report.overall_severity.value,
    )
    return report


async def evaluate_answer(
    known_symbols: set[str],
    known_files: set[str],
    known_edges: set[tuple[str, str]],
    answer_text: str,
    citations: list[dict[str, Any]],
    expected_symbols: list[str],
) -> EvalReport:
    """Run guardrails on a single Q&A answer."""
    report = EvalReport(snapshot_id="", scope="answer")

    report.checks.append(check_hallucinated_symbols(answer_text, known_symbols, known_files))
    report.checks.append(check_hallucinated_relationships(answer_text, known_edges))
    report.checks.append(check_citation_coverage(answer_text, citations, known_files))
    report.checks.append(check_factual_grounding(answer_text, known_symbols, known_files))
    report.checks.append(check_answer_completeness(answer_text, expected_symbols))
    report.checks.append(check_output_safety(answer_text))

    report.compute_overall()
    return report


# -------------------------------------------------------------------
# Internal helpers
# -------------------------------------------------------------------


async def _fetch_known_data(
    db: AsyncSession, snapshot_id: str
) -> tuple[set[str], set[str], set[tuple[str, str]]]:
    """Fetch symbols, files, and edges for verification."""
    result = await db.execute(
        select(Symbol.fq_name, Symbol.file_path).where(Symbol.snapshot_id == snapshot_id)
    )
    rows = result.all()
    known_symbols = {r[0] for r in rows}
    known_files = {r[1] for r in rows}

    result = await db.execute(
        select(Edge.source_fq_name, Edge.target_fq_name).where(Edge.snapshot_id == snapshot_id)
    )
    known_edges = {(r[0], r[1]) for r in result.all()}

    return known_symbols, known_files, known_edges


async def _evaluate_docs(
    db: AsyncSession,
    snapshot_id: str,
    known_symbols: set[str],
    known_files: set[str],
) -> list[EvalCheck]:
    """Evaluate all generated docs for a snapshot."""
    checks: list[EvalCheck] = []

    result = await db.execute(select(GeneratedDoc).where(GeneratedDoc.snapshot_id == snapshot_id))
    docs = result.scalars().all()

    if not docs:
        checks.append(
            EvalCheck(
                category=EvalCategory.DOC_COMPLETENESS,
                name="docs_exist",
                passed=False,
                severity=EvalSeverity.WARNING,
                score=0.0,
                message="No generated documents found.",
            )
        )
        return checks

    checks.append(
        EvalCheck(
            category=EvalCategory.DOC_COMPLETENESS,
            name="docs_exist",
            passed=True,
            severity=EvalSeverity.PASS,
            score=1.0,
            message=f"{len(docs)} document(s) generated.",
        )
    )

    # Check types present
    types = {d.doc_type for d in docs}
    expected_types = {"readme", "architecture", "runbook"}
    missing_types = expected_types - types
    checks.append(
        EvalCheck(
            category=EvalCategory.DOC_COMPLETENESS,
            name="doc_types_present",
            passed=len(missing_types) == 0,
            severity=(EvalSeverity.PASS if not missing_types else EvalSeverity.WARNING),
            score=len(types & expected_types) / len(expected_types),
            message=(
                f"Doc types present: {sorted(types)}."
                + (f" Missing: {sorted(missing_types)}." if missing_types else "")
            ),
        )
    )

    # Spot-check symbol accuracy on all docs
    all_markdown = " ".join(d.markdown for d in docs)
    checks.append(check_doc_symbol_accuracy(all_markdown, known_symbols, known_files))

    # Check staleness on each doc
    for d in docs:
        checks.append(check_doc_staleness(d.snapshot_id, snapshot_id))

    # Check output safety on combined text
    checks.append(check_output_safety(all_markdown))

    return checks


async def _evaluate_reviews(
    db: AsyncSession,
    snapshot_id: str,
    known_symbols: set[str],
    known_files: set[str],
) -> list[EvalCheck]:
    """Evaluate all PR reviews for a snapshot."""
    checks: list[EvalCheck] = []

    result = await db.execute(select(Review).where(Review.snapshot_id == snapshot_id))
    reviews = result.scalars().all()

    if not reviews:
        return checks

    for review in reviews:
        try:
            data = json.loads(review.report_json)
        except (json.JSONDecodeError, TypeError):
            continue

        findings = data.get("findings", [])
        changed = data.get("changed_symbols", [])

        checks.append(check_review_precision(findings, known_symbols, known_files))
        checks.append(check_review_severity_distribution(findings))
        checks.append(
            check_review_coverage(
                [c.get("fq_name", "") for c in changed],
                [f.get("symbol_fq_name", "") for f in findings],
            )
        )

    return checks


def _check_symbol_coverage(known_symbols: set[str], known_files: set[str]) -> EvalCheck:
    """Ensure the snapshot has a reasonable amount of data."""
    total = len(known_symbols)
    if total == 0:
        return EvalCheck(
            category=EvalCategory.OVERALL,
            name="symbol_coverage",
            passed=False,
            severity=EvalSeverity.FAIL,
            score=0.0,
            message="No symbols found in snapshot - analysis may have failed.",
        )

    return EvalCheck(
        category=EvalCategory.OVERALL,
        name="symbol_coverage",
        passed=True,
        severity=EvalSeverity.PASS,
        score=1.0,
        message=(f"Snapshot has {total} symbols across {len(known_files)} files."),
    )


def _check_to_dict(check: EvalCheck) -> dict[str, Any]:
    """Convert an EvalCheck to a serializable dict."""
    return {
        "category": check.category.value,
        "name": check.name,
        "passed": check.passed,
        "severity": check.severity.value,
        "score": check.score,
        "message": check.message,
        "details": check.details,
    }
