"""
Impact analyser.

Uses the symbol and edge tables in the database to determine
the blast radius of changed symbols via call-graph traversal.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.reviews.models import ChangedSymbol, ImpactedSymbol
from app.storage.models import Edge, Symbol

logger = logging.getLogger(__name__)

MAX_HOPS = 3
MAX_IMPACTED = 50


async def find_impacted_symbols(
    db: AsyncSession,
    snapshot_id: str,
    changed_symbols: list[ChangedSymbol],
    max_hops: int = MAX_HOPS,
) -> list[ImpactedSymbol]:
    """
    BFS traversal of callers to find symbols impacted by the changed set.

    Only follows ``calls`` edges in the **inbound** direction (callers),
    since we want to know "what else might break".
    """
    changed_fq = {cs.fq_name for cs in changed_symbols}
    visited: set[str] = set(changed_fq)
    frontier: set[str] = set(changed_fq)
    impacted: list[ImpactedSymbol] = []

    for distance in range(1, max_hops + 1):
        if not frontier or len(impacted) >= MAX_IMPACTED:
            break

        next_frontier: set[str] = set()
        for fq_name in frontier:
            result = await db.execute(
                select(Edge).where(
                    Edge.snapshot_id == snapshot_id,
                    Edge.edge_type == "calls",
                    Edge.target_fq_name == fq_name,
                )
            )
            for edge in result.scalars().all():
                caller = edge.source_fq_name
                if caller not in visited:
                    visited.add(caller)
                    next_frontier.add(caller)

                    # Look up the symbol details
                    sym_result = await db.execute(
                        select(Symbol).where(
                            Symbol.snapshot_id == snapshot_id,
                            Symbol.fq_name == caller,
                        )
                    )
                    sym = sym_result.scalar_one_or_none()
                    if sym:
                        impacted.append(
                            ImpactedSymbol(
                                fq_name=sym.fq_name,
                                kind=sym.kind,
                                file_path=sym.file_path,
                                start_line=sym.start_line,
                                end_line=sym.end_line,
                                distance=distance,
                            )
                        )

                    if len(impacted) >= MAX_IMPACTED:
                        break
            if len(impacted) >= MAX_IMPACTED:
                break

        frontier = next_frontier

    impacted.sort(key=lambda x: (x.distance, x.fq_name))
    logger.info(
        "Impact analysis: %d changed -> %d impacted (max %d hops)",
        len(changed_symbols),
        len(impacted),
        max_hops,
    )
    return impacted


def compute_risk_score(
    changed_symbols: list[ChangedSymbol],
    impacted: list[ImpactedSymbol],
    findings_count: int,
    high_severity_count: int,
) -> tuple[int, str]:
    """
    Compute a 0-100 risk score and risk level.

    Factors:
    - Number of changed symbols
    - Number of impacted symbols (blast radius)
    - Number of findings
    - Severity of findings
    """
    score = 0

    # Changed symbols factor (0-20)
    score += min(len(changed_symbols) * 4, 20)

    # Blast radius factor (0-30)
    score += min(len(impacted) * 3, 30)

    # Findings factor (0-30)
    score += min(findings_count * 5, 30)

    # High severity factor (0-20)
    score += min(high_severity_count * 10, 20)

    score = min(score, 100)

    if score >= 70:
        level = "critical"
    elif score >= 50:
        level = "high"
    elif score >= 25:
        level = "medium"
    else:
        level = "low"

    return score, level
