"""
Tests for behavioral risk heuristics.

Covers every heuristic detector: removed validation, null checks,
error handling, changed conditions, new side effects, changed returns,
concurrency, security, and edge cases.
"""

from app.reviews.diff_parser import parse_unified_diff
from app.reviews.heuristics import (
    detect_changed_condition,
    detect_changed_return,
    detect_concurrency_risk,
    detect_new_side_effects,
    detect_removed_error_handling,
    detect_removed_null_check,
    detect_removed_validation,
    detect_security_sensitive,
    run_all_heuristics,
)
from app.reviews.models import FindingCategory, Severity


def _make_diff(
    removed_lines: list[str] = None, added_lines: list[str] = None, path: str = "Test.cs"
):
    """Build a minimal unified diff from added/removed lines."""
    removed = removed_lines or []
    added = added_lines or []
    old_count = len(removed) + 1
    new_count = len(added) + 1
    lines = [f"diff --git a/{path} b/{path}"]
    lines.append(f"--- a/{path}")
    lines.append(f"+++ b/{path}")
    lines.append(f"@@ -{10},{old_count} +{10},{new_count} @@")
    lines.append(" context line")
    for r in removed:
        lines.append("-" + r)
    for a in added:
        lines.append("+" + a)
    return parse_unified_diff("\n".join(lines))[0]


class TestRemovedValidation:
    def test_detects_null_check_removal(self):
        diff = _make_diff(removed_lines=["    if (x == null) throw new ArgumentNullException();"])
        findings = detect_removed_validation(diff)
        assert len(findings) >= 1
        assert findings[0].category == FindingCategory.REMOVED_VALIDATION
        assert findings[0].severity == Severity.HIGH

    def test_detects_guard_clause(self):
        diff = _make_diff(removed_lines=["    Guard.AgainstNull(x);"])
        findings = detect_removed_validation(diff)
        assert len(findings) >= 1

    def test_no_validation_no_finding(self):
        diff = _make_diff(removed_lines=["    var x = 1;"])
        findings = detect_removed_validation(diff)
        assert findings == []


class TestRemovedNullCheck:
    def test_detects_not_null(self):
        diff = _make_diff(removed_lines=["    if (user != null)"])
        findings = detect_removed_null_check(diff)
        assert len(findings) >= 1
        assert findings[0].category == FindingCategory.REMOVED_NULL_CHECK

    def test_detects_null_coalescing(self):
        diff = _make_diff(removed_lines=['    var name = user?.Name ?? "default";'])
        findings = detect_removed_null_check(diff)
        assert len(findings) >= 1

    def test_detects_is_null(self):
        diff = _make_diff(removed_lines=["    if (value is null) return;"])
        findings = detect_removed_null_check(diff)
        assert len(findings) >= 1


class TestRemovedErrorHandling:
    def test_detects_try_removal(self):
        diff = _make_diff(removed_lines=["    try {"])
        findings = detect_removed_error_handling(diff)
        assert len(findings) >= 1
        assert findings[0].category == FindingCategory.REMOVED_ERROR_HANDLING

    def test_detects_catch_removal(self):
        diff = _make_diff(removed_lines=["    catch (Exception ex)"])
        findings = detect_removed_error_handling(diff)
        assert len(findings) >= 1


class TestChangedCondition:
    def test_detects_changed_if(self):
        diff = _make_diff(
            removed_lines=["    if (x > 0)"],
            added_lines=["    if (x >= 0)"],
        )
        findings = detect_changed_condition(diff)
        assert len(findings) >= 1
        assert findings[0].category == FindingCategory.CHANGED_CONDITION

    def test_no_change_no_finding(self):
        diff = _make_diff(added_lines=["    var y = 42;"])
        findings = detect_changed_condition(diff)
        assert findings == []


class TestNewSideEffects:
    def test_detects_save(self):
        diff = _make_diff(added_lines=["    await _db.SaveChangesAsync();"])
        findings = detect_new_side_effects(diff)
        assert len(findings) >= 1
        assert findings[0].category == FindingCategory.NEW_SIDE_EFFECT

    def test_detects_delete(self):
        diff = _make_diff(added_lines=["    _repo.Delete(entity);"])
        findings = detect_new_side_effects(diff)
        assert len(findings) >= 1

    def test_detects_send(self):
        diff = _make_diff(added_lines=["    await _client.SendAsync(request);"])
        findings = detect_new_side_effects(diff)
        assert len(findings) >= 1

    def test_detects_file_operation(self):
        diff = _make_diff(added_lines=["    File.Delete(path);"])
        findings = detect_new_side_effects(diff)
        assert len(findings) >= 1

    def test_benign_code_no_finding(self):
        diff = _make_diff(added_lines=["    var name = user.Name;"])
        findings = detect_new_side_effects(diff)
        assert findings == []


class TestChangedReturn:
    def test_detects_changed_return(self):
        diff = _make_diff(
            removed_lines=["    return null;"],
            added_lines=["    return new User();"],
        )
        findings = detect_changed_return(diff)
        assert len(findings) >= 1
        assert findings[0].category == FindingCategory.CHANGED_RETURN

    def test_same_return_no_finding(self):
        diff = _make_diff(
            removed_lines=["    return null;"],
            added_lines=["    return null;"],
        )
        findings = detect_changed_return(diff)
        assert findings == []


class TestConcurrencyRisk:
    def test_detects_lock(self):
        diff = _make_diff(added_lines=["    lock (_syncRoot)"])
        findings = detect_concurrency_risk(diff)
        assert len(findings) >= 1
        assert findings[0].category == FindingCategory.CONCURRENCY_RISK

    def test_detects_async(self):
        diff = _make_diff(added_lines=["    await Task.Run(() => DoWork());"])
        findings = detect_concurrency_risk(diff)
        assert len(findings) >= 1


class TestSecuritySensitive:
    def test_detects_password(self):
        diff = _make_diff(added_lines=["    var password = GetPassword();"])
        findings = detect_security_sensitive(diff)
        assert len(findings) >= 1
        assert findings[0].category == FindingCategory.SECURITY_SENSITIVE

    def test_detects_sql_injection_risk(self):
        diff = _make_diff(
            added_lines=['    db.FromSqlRaw("SELECT * FROM users WHERE id = " + id);']
        )
        findings = detect_security_sensitive(diff)
        assert len(findings) >= 1

    def test_detects_auth_removal(self):
        diff = _make_diff(removed_lines=["    [Authorize]"])
        findings = detect_security_sensitive(diff)
        assert len(findings) >= 1
        assert findings[0].severity == Severity.HIGH  # removed = higher severity

    def test_detects_crypto(self):
        diff = _make_diff(added_lines=["    var hash = SHA256.Create().ComputeHash(data);"])
        findings = detect_security_sensitive(diff)
        assert len(findings) == 0  # SHA256 is not in patterns, Hash is
        diff2 = _make_diff(added_lines=["    var hash = Hash(data);"])
        findings2 = detect_security_sensitive(diff2)
        assert len(findings2) >= 1


class TestRunAllHeuristics:
    def test_combines_multiple_findings(self):
        diff = _make_diff(
            removed_lines=[
                "    if (x == null) throw new ArgumentNullException();",
                "    try {",
            ],
            added_lines=[
                "    await _db.SaveChangesAsync();",
                '    var password = "secret";',
            ],
        )
        findings = run_all_heuristics(diff)
        categories = {f.category for f in findings}
        assert (
            FindingCategory.REMOVED_VALIDATION in categories
            or FindingCategory.REMOVED_NULL_CHECK in categories
        )
        assert FindingCategory.REMOVED_ERROR_HANDLING in categories
        assert FindingCategory.NEW_SIDE_EFFECT in categories

    def test_empty_diff_no_findings(self):
        diff = _make_diff()
        findings = run_all_heuristics(diff)
        assert findings == []
