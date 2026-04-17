"""
Behavioral risk heuristics.

Scans diff hunks for patterns that indicate real behavioral changes
(not style changes). Each heuristic produces zero or more
``ReviewFinding`` objects.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.reviews.models import (
    FileDiff,
    FindingCategory,
    ReviewFinding,
    Severity,
)

# Type alias for a heuristic function
HeuristicFn = Callable[[FileDiff], list[ReviewFinding]]


def run_all_heuristics(file_diff: FileDiff) -> list[ReviewFinding]:
    """Run every registered heuristic against a file diff."""
    findings: list[ReviewFinding] = []
    for heuristic in _ALL_HEURISTICS:
        findings.extend(heuristic(file_diff))
    return findings


# ---------------------------------------------------------------------------
# Individual heuristics
# ---------------------------------------------------------------------------


def detect_removed_validation(diff: FileDiff) -> list[ReviewFinding]:
    """Detect removed input validation or guard clauses."""
    patterns = [
        re.compile(
            r"\b(if\s*\(.*(?:null|empty|length|count|valid|check|assert|require|guard))", re.I
        ),
        re.compile(r"\b(throw\s+new\s+Argument(?:Null)?Exception)", re.I),
        re.compile(r"\b(ArgumentNullException|ArgumentException|InvalidOperationException)", re.I),
        re.compile(r"\bGuard\.", re.I),
    ]
    findings: list[ReviewFinding] = []
    for line in diff.removed_lines:
        for pattern in patterns:
            if pattern.search(line.content):
                findings.append(
                    ReviewFinding(
                        category=FindingCategory.REMOVED_VALIDATION,
                        severity=Severity.HIGH,
                        title="Removed validation or guard clause",
                        description=f"A validation check was removed: `{line.content.strip()}`",
                        file_path=diff.path,
                        line=line.old_number,
                        evidence=line.content.strip(),
                        suggestion="Verify validation is handled elsewhere.",
                    )
                )
                break
    return findings


def detect_removed_null_check(diff: FileDiff) -> list[ReviewFinding]:
    """Detect removed null checks that could cause NullReferenceException."""
    patterns = [
        re.compile(r"!=\s*null"),
        re.compile(r"==\s*null"),
        re.compile(r"\bis\s+null\b"),
        re.compile(r"\bis\s+not\s+null\b"),
        re.compile(r"\?\?"),
        re.compile(r"\?\."),
    ]
    findings: list[ReviewFinding] = []
    for line in diff.removed_lines:
        for pattern in patterns:
            if pattern.search(line.content):
                findings.append(
                    ReviewFinding(
                        category=FindingCategory.REMOVED_NULL_CHECK,
                        severity=Severity.HIGH,
                        title="Removed null check",
                        description=f"A null check was removed: `{line.content.strip()}`",
                        file_path=diff.path,
                        line=line.old_number,
                        evidence=line.content.strip(),
                        suggestion="Ensure null safety is maintained.",
                    )
                )
                break
    return findings


def detect_removed_error_handling(diff: FileDiff) -> list[ReviewFinding]:
    """Detect removed try/catch blocks or error handling."""
    patterns = [
        re.compile(r"\b(try\s*\{)"),
        re.compile(r"\b(catch\s*\()"),
        re.compile(r"\b(finally\s*\{)"),
        re.compile(r"\b(\.Catch\(|\.OnError\()"),
    ]
    findings: list[ReviewFinding] = []
    for line in diff.removed_lines:
        for pattern in patterns:
            if pattern.search(line.content):
                findings.append(
                    ReviewFinding(
                        category=FindingCategory.REMOVED_ERROR_HANDLING,
                        severity=Severity.HIGH,
                        title="Removed error handling",
                        description=f"Error handling was removed: `{line.content.strip()}`",
                        file_path=diff.path,
                        line=line.old_number,
                        evidence=line.content.strip(),
                        suggestion="Verify errors are still handled properly.",
                    )
                )
                break
    return findings


def detect_changed_condition(diff: FileDiff) -> list[ReviewFinding]:
    """Detect modified if/else conditions and boolean logic."""
    findings: list[ReviewFinding] = []
    condition_pattern = re.compile(r"\b(if|else\s+if|while|switch)\s*\(")

    for hunk in diff.hunks:
        removed_conditions = [
            ln for ln in hunk.lines if ln.is_removed and condition_pattern.search(ln.content)
        ]
        added_conditions = [
            ln for ln in hunk.lines if ln.is_added and condition_pattern.search(ln.content)
        ]

        if removed_conditions and added_conditions:
            for old, new in zip(removed_conditions, added_conditions):
                findings.append(
                    ReviewFinding(
                        category=FindingCategory.CHANGED_CONDITION,
                        severity=Severity.MEDIUM,
                        title="Changed conditional logic",
                        description=(
                            f"Condition was changed from `{old.content.strip()}` "
                            f"to `{new.content.strip()}`"
                        ),
                        file_path=diff.path,
                        line=new.number,
                        evidence=f"Old: {old.content.strip()}\nNew: {new.content.strip()}",
                        suggestion="Verify the new condition covers all expected cases.",
                    )
                )
    return findings


def detect_new_side_effects(diff: FileDiff) -> list[ReviewFinding]:
    """Detect newly added code that performs writes, sends, or mutations."""
    patterns = [
        (re.compile(r"\b(SaveChanges|SaveChangesAsync|ExecuteNonQuery)\b"), "database write"),
        (re.compile(r"\b(Delete|Remove|Drop|Truncate)\s*\("), "destructive operation"),
        (re.compile(r"\b(Send|Post|Put|Publish|Enqueue|Emit)\w*\s*\("), "external communication"),
        (
            re.compile(r"\b(File\.Write|File\.Delete|File\.Move|Directory\.Delete)\b"),
            "file system operation",
        ),
        (re.compile(r"\b(Process\.Start|Runtime\.exec)\b"), "process execution"),
    ]
    findings: list[ReviewFinding] = []
    for line in diff.added_lines:
        for pattern, effect_type in patterns:
            if pattern.search(line.content):
                findings.append(
                    ReviewFinding(
                        category=FindingCategory.NEW_SIDE_EFFECT,
                        severity=Severity.MEDIUM,
                        title=f"New {effect_type} detected",
                        description=(
                            f"New code introduces a {effect_type}: `{line.content.strip()}`"
                        ),
                        file_path=diff.path,
                        line=line.number,
                        evidence=line.content.strip(),
                        suggestion=f"Verify the {effect_type} is intentional and properly guarded.",
                    )
                )
                break
    return findings


def detect_changed_return(diff: FileDiff) -> list[ReviewFinding]:
    """Detect changed return statements which may alter method contracts."""
    findings: list[ReviewFinding] = []
    return_pattern = re.compile(r"\breturn\b")

    for hunk in diff.hunks:
        removed_returns = [
            ln for ln in hunk.lines if ln.is_removed and return_pattern.search(ln.content)
        ]
        added_returns = [
            ln for ln in hunk.lines if ln.is_added and return_pattern.search(ln.content)
        ]

        if removed_returns and added_returns:
            for old, new in zip(removed_returns, added_returns):
                old_val = old.content.strip()
                new_val = new.content.strip()
                if old_val != new_val:
                    findings.append(
                        ReviewFinding(
                            category=FindingCategory.CHANGED_RETURN,
                            severity=Severity.MEDIUM,
                            title="Changed return value",
                            description=f"Return changed from `{old_val}` to `{new_val}`",
                            file_path=diff.path,
                            line=new.number,
                            evidence=f"Old: {old_val}\nNew: {new_val}",
                            suggestion="Verify all callers handle the new return value correctly.",
                        )
                    )
    return findings


def detect_concurrency_risk(diff: FileDiff) -> list[ReviewFinding]:
    """Detect changes involving locks, async patterns, or shared state."""
    patterns = [
        (
            re.compile(r"\b(lock|Monitor\.Enter|Mutex|Semaphore|Interlocked)\b"),
            "lock/synchronisation",
        ),
        (re.compile(r"\b(async|await|Task\.Run|Task\.Factory)\b"), "async pattern"),
        (
            re.compile(r"\b(static\s+(?!readonly\s+string|readonly\s+int).*=)"),
            "static mutable state",
        ),
        (
            re.compile(r"\b(ConcurrentDictionary|ConcurrentBag|ConcurrentQueue)\b"),
            "concurrent collection",
        ),
    ]
    findings: list[ReviewFinding] = []
    for line in diff.added_lines:
        for pattern, risk_type in patterns:
            if pattern.search(line.content):
                findings.append(
                    ReviewFinding(
                        category=FindingCategory.CONCURRENCY_RISK,
                        severity=Severity.MEDIUM,
                        title=f"Concurrency-sensitive change: {risk_type}",
                        description=f"Code touches {risk_type}: `{line.content.strip()}`",
                        file_path=diff.path,
                        line=line.number,
                        evidence=line.content.strip(),
                        suggestion=f"Review thread safety around this {risk_type} change.",
                    )
                )
                break
    return findings


def detect_security_sensitive(diff: FileDiff) -> list[ReviewFinding]:
    """Detect changes in security-sensitive areas."""
    patterns = [
        (
            re.compile(r"\b(password|secret|token|apikey|api_key|credential)\b", re.I),
            "credential handling",
        ),
        (re.compile(r"\b(Authorize|AllowAnonymous|Authenticate)\b"), "auth attribute"),
        (
            re.compile(r"\b(SqlCommand|SqlQuery|FromSqlRaw|ExecuteSqlRaw)\b"),
            "raw SQL (injection risk)",
        ),
        (re.compile(r"\b(HttpOnly|Secure|SameSite|CORS|AllowAny)\b", re.I), "security config"),
        (re.compile(r"\b(Decrypt|Encrypt|Hash|HMAC|RSA|AES)\b"), "cryptography"),
    ]
    findings: list[ReviewFinding] = []
    all_changed = list(diff.added_lines) + list(diff.removed_lines)
    for line in all_changed:
        for pattern, risk_type in patterns:
            if pattern.search(line.content):
                sev = Severity.HIGH if line.is_removed else Severity.MEDIUM
                findings.append(
                    ReviewFinding(
                        category=FindingCategory.SECURITY_SENSITIVE,
                        severity=sev,
                        title=f"Security-sensitive change: {risk_type}",
                        description=f"Change involves {risk_type}: `{line.content.strip()}`",
                        file_path=diff.path,
                        line=line.number or line.old_number,
                        evidence=line.content.strip(),
                        suggestion=f"Security review recommended for {risk_type} changes.",
                    )
                )
                break
    return findings


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_ALL_HEURISTICS: list[HeuristicFn] = [
    detect_removed_validation,
    detect_removed_null_check,
    detect_removed_error_handling,
    detect_changed_condition,
    detect_new_side_effects,
    detect_changed_return,
    detect_concurrency_risk,
    detect_security_sensitive,
]
