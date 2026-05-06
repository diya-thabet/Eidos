"""API endpoints for quality gates."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.gate_evaluator import (
    GATE_CONFIG_SCHEMA,
    evaluate_gate,
    parse_gate_config,
)
from app.storage.database import get_db
from app.storage.models import (
    CoverageReport,
    QualityGate,
    QualityGateResult,
    Repo,
    RepoSnapshot,
    Symbol,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class GateCreate(BaseModel):
    name: str
    config: dict[str, Any] = {}
    is_active: bool = True


class GateUpdate(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None
    is_active: bool | None = None


class GateOut(BaseModel):
    id: int
    repo_id: str
    name: str
    config: dict[str, Any]
    is_active: bool
    created_at: str
    updated_at: str


class GateCheckOut(BaseModel):
    check: str
    description: str
    expected: Any
    actual: Any
    passed: bool


class GateEvaluationOut(BaseModel):
    gate_id: int
    gate_name: str
    snapshot_id: str
    status: str
    checks: list[GateCheckOut]
    total_checks: int
    passed_checks: int
    failed_checks: int
    summary: str


class GateConfigSchemaOut(BaseModel):
    available_checks: dict[str, str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gate_to_out(gate: QualityGate) -> GateOut:
    try:
        config = json.loads(gate.config_json)
    except (json.JSONDecodeError, TypeError):
        config = {}
    return GateOut(
        id=gate.id,
        repo_id=gate.repo_id,
        name=gate.name,
        config=config,
        is_active=gate.is_active,
        created_at=gate.created_at.isoformat(),
        updated_at=gate.updated_at.isoformat(),
    )


async def _get_snapshot_metrics(
    db: AsyncSession, snapshot_id: str,
) -> dict[str, Any]:
    """Gather metrics from the snapshot for gate evaluation."""
    # Get symbols
    sym_result = await db.execute(
        select(Symbol).where(Symbol.snapshot_id == snapshot_id)
    )
    symbols = sym_result.scalars().all()

    methods = [s for s in symbols if s.kind in ("method", "constructor")]
    cc_values = [s.cyclomatic_complexity or 0 for s in methods]
    avg_cc = sum(cc_values) / len(cc_values) if cc_values else 0.0
    max_cc = max(cc_values) if cc_values else 0
    long_funcs = sum(
        1 for s in methods
        if (s.end_line or 0) - (s.start_line or 0) > 30
    )

    # Coverage
    cov_result = await db.execute(
        select(CoverageReport).where(CoverageReport.snapshot_id == snapshot_id)
    )
    cov = cov_result.scalar_one_or_none()
    coverage_percent = cov.overall_percent if cov else 0.0

    return {
        "error_count": 0,
        "warning_count": 0,
        "total_findings": 0,
        "coverage_percent": coverage_percent,
        "avg_cyclomatic_complexity": round(avg_cc, 2),
        "max_cyclomatic_complexity": max_cc,
        "long_function_count": long_funcs,
        "clone_group_count": 0,
        "dead_function_count": 0,
        "module_cycle_count": 0,
        "instability_violation_count": 0,
        "findings_by_rule": {},
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.post(
    "/{repo_id}/quality-gates",
    response_model=GateOut,
    status_code=201,
    summary="Create a quality gate",
)
async def create_gate(
    repo_id: str,
    body: GateCreate,
    db: AsyncSession = Depends(get_db),
) -> GateOut:
    """Create a new quality gate with configurable thresholds."""
    repo = await db.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")

    gate = QualityGate(
        repo_id=repo_id,
        name=body.name.strip(),
        config_json=json.dumps(body.config),
        is_active=body.is_active,
    )
    db.add(gate)
    await db.commit()
    await db.refresh(gate)
    return _gate_to_out(gate)


@router.get(
    "/{repo_id}/quality-gates",
    response_model=list[GateOut],
    summary="List quality gates for a repo",
)
async def list_gates(
    repo_id: str,
    active_only: bool = Query(False, description="Only return active gates"),
    db: AsyncSession = Depends(get_db),
) -> list[GateOut]:
    """List all quality gates for a repository."""
    stmt = select(QualityGate).where(QualityGate.repo_id == repo_id)
    if active_only:
        stmt = stmt.where(QualityGate.is_active.is_(True))
    stmt = stmt.order_by(QualityGate.created_at.desc())
    result = await db.execute(stmt)
    return [_gate_to_out(g) for g in result.scalars().all()]


@router.get(
    "/{repo_id}/quality-gates/{gate_id}",
    response_model=GateOut,
    summary="Get a quality gate",
)
async def get_gate(
    repo_id: str,
    gate_id: int,
    db: AsyncSession = Depends(get_db),
) -> GateOut:
    """Get a specific quality gate."""
    gate = await db.get(QualityGate, gate_id)
    if gate is None or gate.repo_id != repo_id:
        raise HTTPException(status_code=404, detail="Quality gate not found")
    return _gate_to_out(gate)


@router.patch(
    "/{repo_id}/quality-gates/{gate_id}",
    response_model=GateOut,
    summary="Update a quality gate",
)
async def update_gate(
    repo_id: str,
    gate_id: int,
    body: GateUpdate,
    db: AsyncSession = Depends(get_db),
) -> GateOut:
    """Update a quality gate's name, config, or active status."""
    gate = await db.get(QualityGate, gate_id)
    if gate is None or gate.repo_id != repo_id:
        raise HTTPException(status_code=404, detail="Quality gate not found")

    if body.name is not None:
        gate.name = body.name.strip()
    if body.config is not None:
        gate.config_json = json.dumps(body.config)
    if body.is_active is not None:
        gate.is_active = body.is_active

    await db.commit()
    await db.refresh(gate)
    return _gate_to_out(gate)


@router.delete(
    "/{repo_id}/quality-gates/{gate_id}",
    status_code=204,
    summary="Delete a quality gate",
)
async def delete_gate(
    repo_id: str,
    gate_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a quality gate and all its results."""
    gate = await db.get(QualityGate, gate_id)
    if gate is None or gate.repo_id != repo_id:
        raise HTTPException(status_code=404, detail="Quality gate not found")
    await db.delete(gate)
    await db.commit()


# ---------------------------------------------------------------------------
# Evaluate
# ---------------------------------------------------------------------------


@router.post(
    "/{repo_id}/snapshots/{snapshot_id}/evaluate-gate/{gate_id}",
    response_model=GateEvaluationOut,
    summary="Evaluate a snapshot against a quality gate",
)
async def evaluate_snapshot_gate(
    repo_id: str,
    snapshot_id: str,
    gate_id: int,
    db: AsyncSession = Depends(get_db),
) -> GateEvaluationOut:
    """Evaluate a snapshot against quality gate thresholds.

    Returns 200 on success (even if gate fails).
    Check the `status` field: "passed" or "failed".
    """
    snapshot = await db.get(RepoSnapshot, snapshot_id)
    if snapshot is None or snapshot.repo_id != repo_id:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    gate = await db.get(QualityGate, gate_id)
    if gate is None or gate.repo_id != repo_id:
        raise HTTPException(status_code=404, detail="Quality gate not found")

    config = parse_gate_config(gate.config_json)
    metrics = await _get_snapshot_metrics(db, snapshot_id)

    evaluation = evaluate_gate(
        gate_id=gate.id,
        gate_name=gate.name,
        snapshot_id=snapshot_id,
        config=config,
        snapshot_metrics=metrics,
    )

    # Persist result
    result_row = QualityGateResult(
        gate_id=gate.id,
        snapshot_id=snapshot_id,
        status=evaluation.status,
        violations_json=json.dumps([
            {"check": c.check, "expected": c.expected, "actual": c.actual, "passed": c.passed}
            for c in evaluation.checks if not c.passed
        ]),
        summary=evaluation.summary,
    )
    db.add(result_row)
    await db.commit()

    return GateEvaluationOut(
        gate_id=evaluation.gate_id,
        gate_name=evaluation.gate_name,
        snapshot_id=evaluation.snapshot_id,
        status=evaluation.status,
        checks=[
            GateCheckOut(
                check=c.check, description=c.description,
                expected=c.expected, actual=c.actual, passed=c.passed,
            )
            for c in evaluation.checks
        ],
        total_checks=evaluation.total_checks,
        passed_checks=evaluation.passed_checks,
        failed_checks=evaluation.failed_checks,
        summary=evaluation.summary,
    )


# ---------------------------------------------------------------------------
# Gate config schema (for UI)
# ---------------------------------------------------------------------------


@router.get(
    "/quality-gates/schema",
    response_model=GateConfigSchemaOut,
    summary="Get available quality gate config options",
)
async def get_gate_schema() -> GateConfigSchemaOut:
    """Return the available quality gate configuration keys and descriptions."""
    return GateConfigSchemaOut(available_checks=GATE_CONFIG_SCHEMA)
