"""
Tests for the review evaluator.

Covers: precision, severity distribution, coverage, edge cases.
"""

from app.guardrails.review_evaluator import (
    check_review_coverage,
    check_review_precision,
    check_review_severity_distribution,
)


class TestReviewPrecision:
    def test_no_findings(self):
        r = check_review_precision([], {"A"}, {"a.cs"})
        assert r.passed

    def test_all_grounded(self):
        findings = [
            {"file_path": "a.cs", "symbol_fq_name": "A", "title": "f1"},
        ]
        r = check_review_precision(findings, {"A"}, {"a.cs"})
        assert r.passed
        assert r.score == 1.0

    def test_suspect_finding(self):
        findings = [
            {"file_path": "ghost.cs", "symbol_fq_name": "X", "title": "bad"},
        ]
        r = check_review_precision(findings, {"A"}, {"a.cs"})
        assert not r.passed
        assert "bad" in r.details["suspect_findings"]

    def test_mixed(self):
        findings = [
            {"file_path": "a.cs", "symbol_fq_name": "", "title": "ok"},
            {"file_path": "ghost.cs", "symbol_fq_name": "", "title": "bad"},
        ]
        r = check_review_precision(findings, set(), {"a.cs"})
        assert r.score == 0.5

    def test_empty_paths_pass(self):
        findings = [{"file_path": "", "symbol_fq_name": "", "title": "ok"}]
        r = check_review_precision(findings, set(), set())
        assert r.passed


class TestSeverityDistribution:
    def test_no_findings(self):
        r = check_review_severity_distribution([])
        assert r.passed

    def test_varied_severities(self):
        findings = [
            {"severity": "high"},
            {"severity": "medium"},
            {"severity": "low"},
        ]
        r = check_review_severity_distribution(findings)
        assert r.passed

    def test_all_same_severity(self):
        findings = [
            {"severity": "high"},
            {"severity": "high"},
            {"severity": "high"},
        ]
        r = check_review_severity_distribution(findings)
        assert not r.passed
        assert r.score == 0.5

    def test_two_same_ok(self):
        findings = [
            {"severity": "high"},
            {"severity": "high"},
        ]
        r = check_review_severity_distribution(findings)
        assert r.passed  # only 2, threshold is 3


class TestReviewCoverage:
    def test_no_changed(self):
        r = check_review_coverage([], [])
        assert r.passed

    def test_full_coverage(self):
        r = check_review_coverage(["A", "B"], ["A", "B"])
        assert r.passed
        assert r.score == 1.0

    def test_partial_coverage(self):
        r = check_review_coverage(["A", "B", "C"], ["A"])
        assert r.score < 1.0

    def test_no_coverage(self):
        r = check_review_coverage(["A", "B"], [])
        assert not r.passed
        assert r.score == 0.0
