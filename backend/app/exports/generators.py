"""
Export generators: CSV (ZIP), SARIF, and Markdown report.

All pure Python using stdlib csv, json, io, zipfile.
"""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import UTC, datetime
from typing import Any

# -----------------------------------------------------------------------
# CSV Export (ZIP)
# -----------------------------------------------------------------------


def generate_csv_zip(
    symbols: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    health_findings: list[dict[str, Any]],
    dependencies: list[dict[str, Any]] | None = None,
) -> bytes:
    """Generate a ZIP containing CSV files for symbols, edges, findings, deps."""
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("symbols.csv", _dicts_to_csv(symbols, [
            "fq_name", "name", "kind", "file_path",
            "start_line", "end_line", "namespace",
            "cyclomatic_complexity", "cognitive_complexity",
            "last_author", "author_count", "commit_count",
        ]))
        zf.writestr("edges.csv", _dicts_to_csv(edges, [
            "source_fq_name", "target_fq_name", "edge_type",
            "file_path", "line",
        ]))
        zf.writestr("health_findings.csv", _dicts_to_csv(health_findings, [
            "rule_id", "rule_name", "category", "severity",
            "symbol_fq_name", "file_path", "line", "message",
        ]))
        if dependencies:
            zf.writestr("dependencies.csv", _dicts_to_csv(dependencies, [
                "name", "version", "ecosystem", "manifest_file",
            ]))

    return buf.getvalue()


def _dicts_to_csv(rows: list[dict[str, Any]], columns: list[str]) -> str:
    """Convert list of dicts to CSV string with given columns."""
    output = io.StringIO()
    writer = csv.DictWriter(
        output, fieldnames=columns, extrasaction="ignore",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in columns})
    return output.getvalue()


# -----------------------------------------------------------------------
# SARIF Export
# -----------------------------------------------------------------------

_SARIF_SCHEMA = (
    "https://raw.githubusercontent.com/oasis-tcs/"
    "sarif-spec/main/sarif-2.1/schema/sarif-schema-2.1.0.json"
)

_SEVERITY_MAP = {
    "error": "error",
    "warning": "warning",
    "info": "note",
    "hint": "note",
}


def generate_sarif(
    health_findings: list[dict[str, Any]],
    rules_meta: list[dict[str, Any]] | None = None,
    tool_name: str = "Eidos",
    tool_version: str = "1.0.0",
) -> dict[str, Any]:
    """Generate SARIF 2.1.0 output from health findings."""
    # Build rules array
    rule_ids_seen: set[str] = set()
    sarif_rules: list[dict[str, Any]] = []

    if rules_meta:
        for rm in rules_meta:
            sarif_rules.append({
                "id": rm["rule_id"],
                "name": rm.get("rule_name", ""),
                "shortDescription": {"text": rm.get("description", "")},
                "defaultConfiguration": {
                    "level": _SEVERITY_MAP.get(
                        rm.get("severity", "warning"), "warning",
                    ),
                },
            })
            rule_ids_seen.add(rm["rule_id"])

    # Build results array
    results: list[dict[str, Any]] = []
    for f in health_findings:
        rule_id = f.get("rule_id", "UNKNOWN")

        # Auto-add rule if not in meta
        if rule_id not in rule_ids_seen:
            sarif_rules.append({
                "id": rule_id,
                "name": f.get("rule_name", ""),
                "shortDescription": {"text": f.get("message", "")},
            })
            rule_ids_seen.add(rule_id)

        result: dict[str, Any] = {
            "ruleId": rule_id,
            "level": _SEVERITY_MAP.get(
                f.get("severity", "warning"), "warning",
            ),
            "message": {"text": f.get("message", "")},
        }

        file_path = f.get("file_path", "")
        line = f.get("line", 0)
        if file_path:
            result["locations"] = [{
                "physicalLocation": {
                    "artifactLocation": {"uri": file_path},
                    "region": {"startLine": max(line, 1)},
                },
            }]

        results.append(result)

    return {
        "$schema": _SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": tool_name,
                    "version": tool_version,
                    "rules": sarif_rules,
                },
            },
            "results": results,
        }],
    }


# -----------------------------------------------------------------------
# Markdown Report
# -----------------------------------------------------------------------


def generate_markdown_report(
    snapshot_id: str,
    repo_name: str,
    symbol_count: int,
    file_count: int,
    edge_count: int,
    health_findings: list[dict[str, Any]],
    top_complex: list[dict[str, Any]] | None = None,
    dependencies: list[dict[str, Any]] | None = None,
    clone_count: int = 0,
) -> str:
    """Generate a Markdown health report for a snapshot."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = []

    lines.append(f"# Code Health Report: {repo_name}")
    lines.append(f"\n*Generated: {now} | Snapshot: `{snapshot_id}`*\n")

    # Summary
    lines.append("## Summary\n")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Files | {file_count} |")
    lines.append(f"| Symbols | {symbol_count} |")
    lines.append(f"| Edges | {edge_count} |")
    lines.append(f"| Health findings | {len(health_findings)} |")
    if dependencies:
        lines.append(f"| Dependencies | {len(dependencies)} |")
    if clone_count:
        lines.append(f"| Code clones | {clone_count} |")
    lines.append("")

    # Findings by severity
    sev_counts: dict[str, int] = {}
    for f in health_findings:
        s = f.get("severity", "info")
        sev_counts[s] = sev_counts.get(s, 0) + 1

    if sev_counts:
        lines.append("## Findings by Severity\n")
        for sev in ["error", "warning", "info", "hint"]:
            if sev in sev_counts:
                icon = {"error": "??", "warning": "??", "info": "??", "hint": "?"}.get(sev, "")
                lines.append(f"- {icon} **{sev.upper()}**: {sev_counts[sev]}")
        lines.append("")

    # Top findings
    if health_findings:
        lines.append("## Top Findings\n")
        lines.append("| Rule | Severity | File | Line | Message |")
        lines.append("|------|----------|------|------|---------|")
        for f in health_findings[:30]:
            rule = f.get("rule_id", "")
            sev = f.get("severity", "")
            fp = f.get("file_path", "")
            ln = f.get("line", "")
            msg = f.get("message", "")[:80]
            lines.append(f"| {rule} | {sev} | `{fp}` | {ln} | {msg} |")
        if len(health_findings) > 30:
            lines.append(
                f"\n*...and {len(health_findings) - 30} more findings*\n"
            )
        lines.append("")

    # Top complex functions
    if top_complex:
        lines.append("## Most Complex Functions\n")
        lines.append("| Function | File | CC | Cognitive |")
        lines.append("|----------|------|----|-----------|")
        for s in top_complex[:15]:
            name = s.get("fq_name", s.get("name", ""))
            fp = s.get("file_path", "")
            cc = s.get("cyclomatic_complexity", 0)
            cog = s.get("cognitive_complexity", 0)
            lines.append(f"| `{name}` | `{fp}` | {cc} | {cog} |")
        lines.append("")

    lines.append("---\n*Report generated by Eidos*\n")
    return "\n".join(lines)
