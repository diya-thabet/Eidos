"""
Incremental health analysis.

Only re-runs health checks on changed files; copies unchanged findings
from a previous snapshot. Also provides a diff endpoint showing
added/fixed findings between two snapshots.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models import HealthFindingPersisted


def compute_fingerprint(
    rule_id: str, symbol_fq_name: str, file_path: str, line: int,
) -> str:
    """Compute a stable fingerprint for a finding.

    This allows comparing findings across snapshots even if IDs differ.
    """
    content = f"{rule_id}:{symbol_fq_name}:{file_path}:{line}"
    return hashlib.sha256(content.encode()).hexdigest()[:32]


@dataclass
class HealthDiff:
    """Diff between two snapshots' health findings."""

    new_snapshot_id: str
    prev_snapshot_id: str
    added: list[dict[str, Any]] = field(default_factory=list)
    fixed: list[dict[str, Any]] = field(default_factory=list)
    unchanged_count: int = 0
    new_total: int = 0
    prev_total: int = 0


async def persist_findings(
    db: AsyncSession,
    snapshot_id: str,
    findings: list[dict[str, Any]],
) -> int:
    """Persist health findings for a snapshot. Returns count persisted."""
    count = 0
    for f in findings:
        fp = compute_fingerprint(
            f.get("rule_id", ""),
            f.get("symbol_fq_name", ""),
            f.get("file_path", ""),
            f.get("line", 0),
        )
        db.add(HealthFindingPersisted(
            snapshot_id=snapshot_id,
            symbol_fq_name=f.get("symbol_fq_name", ""),
            rule_id=f.get("rule_id", ""),
            severity=f.get("severity", "warning"),
            message=f.get("message", ""),
            file_path=f.get("file_path", ""),
            line=f.get("line", 0),
            fingerprint=fp,
        ))
        count += 1
    await db.flush()
    return count


async def compute_health_diff(
    db: AsyncSession,
    new_snapshot_id: str,
    prev_snapshot_id: str,
) -> HealthDiff:
    """Compute the diff between two snapshots' health findings.

    Returns added findings (in new but not prev) and fixed findings
    (in prev but not new), identified by fingerprint.
    """
    # Get new findings
    new_result = await db.execute(
        select(HealthFindingPersisted).where(
            HealthFindingPersisted.snapshot_id == new_snapshot_id,
        )
    )
    new_findings = new_result.scalars().all()
    new_fps = {f.fingerprint: f for f in new_findings}

    # Get prev findings
    prev_result = await db.execute(
        select(HealthFindingPersisted).where(
            HealthFindingPersisted.snapshot_id == prev_snapshot_id,
        )
    )
    prev_findings = prev_result.scalars().all()
    prev_fps = {f.fingerprint: f for f in prev_findings}

    # Added: in new but not in prev
    added = []
    for fp, finding in new_fps.items():
        if fp not in prev_fps:
            added.append(_finding_to_dict(finding))

    # Fixed: in prev but not in new
    fixed = []
    for fp, finding in prev_fps.items():
        if fp not in new_fps:
            fixed.append(_finding_to_dict(finding))

    unchanged_count = len(new_fps) - len(added)

    return HealthDiff(
        new_snapshot_id=new_snapshot_id,
        prev_snapshot_id=prev_snapshot_id,
        added=added,
        fixed=fixed,
        unchanged_count=max(unchanged_count, 0),
        new_total=len(new_findings),
        prev_total=len(prev_findings),
    )


async def copy_unchanged_findings(
    db: AsyncSession,
    prev_snapshot_id: str,
    new_snapshot_id: str,
    changed_files: set[str],
) -> int:
    """Copy findings from prev snapshot that are NOT in changed files.

    Returns count of copied findings.
    """
    prev_result = await db.execute(
        select(HealthFindingPersisted).where(
            HealthFindingPersisted.snapshot_id == prev_snapshot_id,
        )
    )
    prev_findings = prev_result.scalars().all()

    copied = 0
    for f in prev_findings:
        if f.file_path not in changed_files:
            db.add(HealthFindingPersisted(
                snapshot_id=new_snapshot_id,
                symbol_fq_name=f.symbol_fq_name,
                rule_id=f.rule_id,
                severity=f.severity,
                message=f.message,
                file_path=f.file_path,
                line=f.line,
                fingerprint=f.fingerprint,
            ))
            copied += 1

    await db.flush()
    return copied


def _finding_to_dict(f: HealthFindingPersisted) -> dict[str, Any]:
    return {
        "rule_id": f.rule_id,
        "severity": f.severity,
        "symbol_fq_name": f.symbol_fq_name,
        "file_path": f.file_path,
        "line": f.line,
        "message": f.message,
        "fingerprint": f.fingerprint,
    }
