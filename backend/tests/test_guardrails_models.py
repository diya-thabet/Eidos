"""
Tests for the guardrails models.

Covers: EvalReport scoring, severity computation, edge cases.
"""

from app.guardrails.models import (
    EvalCategory,
    EvalCheck,
    EvalReport,
    EvalSeverity,
    SanitizationResult,
)


class TestEvalReport:
    def test_compute_all_pass(self):
        r = EvalReport(
            snapshot_id="s1",
            checks=[
                EvalCheck(
                    category=EvalCategory.OVERALL,
                    name="a",
                    passed=True,
                    severity=EvalSeverity.PASS,
                    score=1.0,
                ),
                EvalCheck(
                    category=EvalCategory.OVERALL,
                    name="b",
                    passed=True,
                    severity=EvalSeverity.PASS,
                    score=0.8,
                ),
            ],
        )
        r.compute_overall()
        assert r.overall_severity == EvalSeverity.PASS
        assert r.overall_score == 0.9
        assert "All 2 checks passed" in r.summary

    def test_compute_with_fail(self):
        r = EvalReport(
            snapshot_id="s1",
            checks=[
                EvalCheck(
                    category=EvalCategory.HALLUCINATION,
                    name="hal",
                    passed=False,
                    severity=EvalSeverity.FAIL,
                    score=0.0,
                ),
                EvalCheck(
                    category=EvalCategory.OVERALL,
                    name="ok",
                    passed=True,
                    severity=EvalSeverity.PASS,
                    score=1.0,
                ),
            ],
        )
        r.compute_overall()
        assert r.overall_severity == EvalSeverity.FAIL
        assert r.overall_score == 0.5
        assert "1 check(s) failed" in r.summary

    def test_compute_with_warning(self):
        r = EvalReport(
            snapshot_id="s1",
            checks=[
                EvalCheck(
                    category=EvalCategory.OVERALL,
                    name="w",
                    passed=False,
                    severity=EvalSeverity.WARNING,
                    score=0.5,
                ),
            ],
        )
        r.compute_overall()
        assert r.overall_severity == EvalSeverity.WARNING

    def test_empty_checks(self):
        r = EvalReport(snapshot_id="s1")
        r.compute_overall()
        assert r.overall_score == 1.0
        assert r.overall_severity == EvalSeverity.PASS


class TestSanitizationResult:
    def test_clean(self):
        r = SanitizationResult(clean_text="hello")
        assert not r.was_modified
        assert r.issues == []

    def test_modified(self):
        r = SanitizationResult(
            clean_text="hello [REDACTED]",
            was_modified=True,
            issues=["pii:email"],
        )
        assert r.was_modified
        assert len(r.issues) == 1
