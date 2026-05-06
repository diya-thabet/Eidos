"""
Quality gate evaluator.

Evaluates a snapshot against configurable quality gate thresholds.
Pure logic � no DB access, no side effects.
"""

from __future__ import annotationsimport jsonfrom dataclasses import dataclass, fieldfrom typing import Any@dataclass
class GateCheck:
    """Result of a single gate check."""

    check: str
    description: str
    expected: Any
    actual: Any
    passed: bool


@dataclass
class GateEvaluation:
    """Full evaluation result."""

    gate_id: int
    gate_name: str
    snapshot_id: str
    status: str  # "passed" | "failed"
    checks: list[GateCheck] = field(default_factory=list)
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    summary: str = ""


# Available gate config keys and their descriptions
GATE_CONFIG_SCHEMA: dict[str, str] = {
    "max_errors": "Maximum number of error-severity findings",
    "max_warnings": "Maximum number of warning-severity findings",
    "max_findings": "Maximum total findings of any severity",
    "min_coverage_percent": "Minimum test coverage percentage",
    "max_avg_cyclomatic_complexity": "Maximum average cyclomatic complexity",
    "max_max_cyclomatic_complexity": "Maximum single-function cyclomatic complexity",
    "max_long_functions": "Maximum number of functions > 30 lines",
    "max_clone_groups": "Maximum number of clone groups",
    "max_dead_functions": "Maximum number of unreachable functions",
    "max_module_cycles": "Maximum number of module dependency cycles",
    "max_instability_violations": "Maximum modules with instability > 0.8",
    "blocked_rules": "List of rule IDs that must have 0 findings",
}


def parse_gate_config(config_json: str) -> dict[str, Any]:
    """Parse gate config from JSON string."""
    try:
        config = json.loads(config_json)
    except (json.JSONDecodeError, TypeError):
        config = {}
    if not isinstance(config, dict):
        return {}
    return config


def evaluate_gate(
    gate_id: int,
    gate_name: str,
    snapshot_id: str,
    config: dict[str, Any],
    snapshot_metrics: dict[str, Any],
) -> GateEvaluation:
    """Evaluate a snapshot against a quality gate config.

    Args:
        gate_id: The gate ID.
        gate_name: The gate name.
        snapshot_id: The snapshot ID.
        config: The gate configuration dict (thresholds).
        snapshot_metrics: The snapshot's current metrics dict with keys like:
            - error_count, warning_count, total_findings
            - coverage_percent
            - avg_cyclomatic_complexity, max_cyclomatic_complexity
            - long_function_count
            - clone_group_count
            - dead_function_count
            - module_cycle_count
            - instability_violation_count
            - findings_by_rule: dict[str, int]
    """
    checks: list[GateCheck] = []

    # Numeric threshold checks
    _NUMERIC_CHECKS = [
        ("max_errors", "error_count", "Error findings"),
        ("max_warnings", "warning_count", "Warning findings"),
        ("max_findings", "total_findings", "Total findings"),
        ("max_avg_cyclomatic_complexity", "avg_cyclomatic_complexity", "Avg CC"),
        ("max_max_cyclomatic_complexity", "max_cyclomatic_complexity", "Max CC"),
        ("max_long_functions", "long_function_count", "Long functions"),
        ("max_clone_groups", "clone_group_count", "Clone groups"),
        ("max_dead_functions", "dead_function_count", "Dead functions"),
        ("max_module_cycles", "module_cycle_count", "Module cycles"),
        ("max_instability_violations", "instability_violation_count", "Instability violations"),
    ]

    for config_key, metric_key, desc in _NUMERIC_CHECKS:
        if config_key not in config:
            continue
        threshold = config[config_key]
        actual = snapshot_metrics.get(metric_key, 0)
        passed = actual <= threshold
        checks.append(GateCheck(
            check=config_key,
            description=desc,
            expected=f"<= {threshold}",
            actual=actual,
            passed=passed,
        ))

    # Minimum coverage check (inverted: actual must be >= threshold)
    if "min_coverage_percent" in config:
        threshold = config["min_coverage_percent"]
        actual = snapshot_metrics.get("coverage_percent", 0.0)
        passed = actual >= threshold
        checks.append(GateCheck(
            check="min_coverage_percent",
            description="Test coverage",
            expected=f">= {threshold}%",
            actual=round(actual, 2),
            passed=passed,
        ))

    # Blocked rules check
    if "blocked_rules" in config:
        blocked = config["blocked_rules"]
        if isinstance(blocked, list):
            findings_by_rule = snapshot_metrics.get("findings_by_rule", {})
            for rule_id in blocked:
                count = findings_by_rule.get(rule_id, 0)
                passed = count == 0
                checks.append(GateCheck(
                    check=f"blocked_rule:{rule_id}",
                    description=f"Rule {rule_id} must have 0 findings",
                    expected=0,
                    actual=count,
                    passed=passed,
                ))

    passed_count = sum(1 for c in checks if c.passed)
    failed_count = len(checks) - passed_count
    status = "passed" if failed_count == 0 else "failed"

    summary = (
        f"{passed_count} of {len(checks)} checks passed"
        if checks
        else "No checks configured"
    )

    return GateEvaluation(
        gate_id=gate_id,
        gate_name=gate_name,
        snapshot_id=snapshot_id,
        status=status,
        checks=checks,
        total_checks=len(checks),
        passed_checks=passed_count,
        failed_checks=failed_count,
        summary=summary,
    )
