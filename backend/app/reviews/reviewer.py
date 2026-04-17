"""
Review orchestrator.

Coordinates the full PR review pipeline:
  1. Parse the unified diff
  2. Map changed lines to symbols
  3. Run behavioral heuristics
  4. Analyse blast radius via call graph
  5. Compute risk score
  6. (Optionally) enrich with LLM summary
  7. Assemble the ReviewReport
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.reasoning.llm_client import LLMClient, StubLLMClient
from app.reviews.diff_parser import map_lines_to_symbols, parse_unified_diff
from app.reviews.heuristics import run_all_heuristics
from app.reviews.impact_analyzer import compute_risk_score, find_impacted_symbols
from app.reviews.models import (
    ChangedSymbol,
    FindingCategory,
    ImpactedSymbol,
    ReviewFinding,
    ReviewReport,
    Severity,
)
from app.storage.models import Edge, Symbol

logger = logging.getLogger(__name__)


async def review_diff(
    db: AsyncSession,
    snapshot_id: str,
    diff_text: str,
    *,
    llm: LLMClient | None = None,
    max_hops: int = 3,
) -> ReviewReport:
    """
    Run the full review pipeline on a unified diff.

    Args:
        db: Database session.
        snapshot_id: The snapshot to look up symbols/edges against.
        diff_text: Raw unified diff text.
        llm: Optional LLM client for summary generation.
        max_hops: Maximum call-graph traversal depth.

    Returns:
        A complete ReviewReport.
    """
    # Step 1: Parse diff
    file_diffs = parse_unified_diff(diff_text)

    if not file_diffs:
        return ReviewReport(
            snapshot_id=snapshot_id,
            diff_summary="Empty diff -- no changes detected.",
            files_changed=[],
        )

    # Step 2: Map changed lines to symbols
    all_changed_symbols: list[ChangedSymbol] = []
    all_findings: list[ReviewFinding] = []

    for fd in file_diffs:
        # Look up symbols in this file
        file_symbols = await _get_file_symbols(db, snapshot_id, fd.path)
        matched = map_lines_to_symbols(fd, file_symbols)

        for m in matched:
            all_changed_symbols.append(
                ChangedSymbol(
                    fq_name=m["fq_name"],
                    kind=m["kind"],
                    file_path=m.get("file_path", fd.path),
                    start_line=m.get("start_line", 0),
                    end_line=m.get("end_line", 0),
                    change_type=m.get("change_type", "modified"),
                    lines_changed=m.get("lines_changed", 0),
                )
            )

        # Step 3: Run heuristics on each file
        all_findings.extend(run_all_heuristics(fd))

    # Deduplicate findings by (category, file, line)
    seen_findings: set[tuple] = set()
    unique_findings: list[ReviewFinding] = []
    for f in all_findings:
        key = (f.category.value, f.file_path, f.line)
        if key not in seen_findings:
            seen_findings.add(key)
            unique_findings.append(f)
    all_findings = unique_findings

    # Add high-fan-in findings for changed symbols
    for cs in all_changed_symbols:
        fan_in = await _count_callers(db, snapshot_id, cs.fq_name)
        if fan_in >= 5:
            all_findings.append(
                ReviewFinding(
                    category=FindingCategory.HIGH_FAN_IN_CHANGE,
                    severity=Severity.HIGH,
                    title=f"Changed symbol with high fan-in ({fan_in} callers)",
                    description=(
                        f"`{cs.fq_name}` has {fan_in} callers -- changes here have wide impact."
                    ),
                    file_path=cs.file_path,
                    line=cs.start_line,
                    symbol_fq_name=cs.fq_name,
                    suggestion="Verify all callers still work correctly with the change.",
                )
            )

    # Step 4: Impact analysis (blast radius)
    impacted = await find_impacted_symbols(db, snapshot_id, all_changed_symbols, max_hops=max_hops)

    # Step 5: Risk score
    high_count = sum(1 for f in all_findings if f.severity in (Severity.CRITICAL, Severity.HIGH))
    risk_score, risk_level = compute_risk_score(
        all_changed_symbols, impacted, len(all_findings), high_count
    )

    # Step 6: Build diff summary
    total_added = sum(len(fd.added_lines) for fd in file_diffs)
    total_removed = sum(len(fd.removed_lines) for fd in file_diffs)
    diff_summary = (
        f"{len(file_diffs)} file(s) changed, "
        f"+{total_added} additions, -{total_removed} deletions, "
        f"{len(all_changed_symbols)} symbol(s) affected."
    )

    # Step 7: Optional LLM summary
    llm_summary = ""
    if llm is not None and not isinstance(llm, StubLLMClient):
        llm_summary = await _generate_llm_summary(
            llm, diff_summary, all_findings, all_changed_symbols, impacted
        )

    report = ReviewReport(
        snapshot_id=snapshot_id,
        diff_summary=diff_summary,
        files_changed=[fd.path for fd in file_diffs],
        changed_symbols=all_changed_symbols,
        findings=all_findings,
        impacted_symbols=impacted,
        risk_score=risk_score,
        risk_level=risk_level,
        llm_summary=llm_summary,
    )

    logger.info(
        "Review complete: %d files, %d changed symbols, %d findings, %d impacted, risk=%d/%s",
        len(file_diffs),
        len(all_changed_symbols),
        len(all_findings),
        len(impacted),
        risk_score,
        risk_level,
    )
    return report


async def _get_file_symbols(db: AsyncSession, snapshot_id: str, file_path: str) -> list[dict]:
    """Look up all symbols in a file from the database."""
    result = await db.execute(
        select(Symbol).where(
            Symbol.snapshot_id == snapshot_id,
            Symbol.file_path == file_path,
        )
    )
    return [
        {
            "fq_name": s.fq_name,
            "kind": s.kind,
            "name": s.name,
            "file_path": s.file_path,
            "start_line": s.start_line,
            "end_line": s.end_line,
            "namespace": s.namespace,
            "modifiers": s.modifiers,
            "signature": s.signature,
        }
        for s in result.scalars().all()
    ]


async def _count_callers(db: AsyncSession, snapshot_id: str, fq_name: str) -> int:
    """Count how many symbols call the given symbol."""
    from sqlalchemy import func

    result = await db.execute(
        select(func.count()).where(
            Edge.snapshot_id == snapshot_id,
            Edge.edge_type == "calls",
            Edge.target_fq_name == fq_name,
        )
    )
    return result.scalar() or 0


async def _generate_llm_summary(
    llm: LLMClient,
    diff_summary: str,
    findings: list[ReviewFinding],
    changed: list[ChangedSymbol],
    impacted: list[ImpactedSymbol],
) -> str:
    """Ask the LLM for a narrative risk summary."""
    system_prompt = (
        "You are a senior code reviewer. Summarise the PR risk based on the "
        "provided analysis. Focus on behavioral risks, not style. Be concise. "
        "Mention the most important findings and impacted areas."
    )

    findings_text = "\n".join(
        f"- [{f.severity.value}] {f.title}: {f.description}" for f in findings[:10]
    )
    changed_text = "\n".join(
        f"- {cs.fq_name} ({cs.change_type}, {cs.lines_changed} lines)" for cs in changed[:10]
    )
    impacted_text = "\n".join(f"- {imp.fq_name} (distance {imp.distance})" for imp in impacted[:10])

    user_message = (
        f"Diff summary: {diff_summary}\n\n"
        f"Changed symbols:\n{changed_text}\n\n"
        f"Findings:\n{findings_text}\n\n"
        f"Impacted symbols (blast radius):\n{impacted_text}"
    )

    try:
        from app.reviews.impact_analyzer import compute_risk_score as _unused  # noqa: F401

        return await llm.chat(system_prompt, user_message)
    except Exception as e:
        logger.warning("LLM summary generation failed: %s", e)
        return ""
