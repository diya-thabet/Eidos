"""
Tests for the document evaluator.

Covers: completeness, symbol accuracy, staleness, coverage.
"""

from app.guardrails.doc_evaluator import (
    check_doc_completeness,
    check_doc_coverage,
    check_doc_staleness,
    check_doc_symbol_accuracy,
)


class TestDocCompleteness:
    def test_all_sections_present(self):
        md = "# Overview\n## Modules\n## Entry Points"
        r = check_doc_completeness(md, ["Overview", "Modules", "Entry Points"])
        assert r.passed
        assert r.score == 1.0

    def test_missing_sections(self):
        md = "# Overview"
        r = check_doc_completeness(md, ["Overview", "Modules", "Entry Points"])
        assert r.score < 1.0
        assert "Modules" in r.details["missing_sections"]

    def test_no_expected(self):
        r = check_doc_completeness("any", [])
        assert r.passed

    def test_case_insensitive(self):
        md = "## overview"
        r = check_doc_completeness(md, ["Overview"])
        assert r.passed

    def test_all_missing(self):
        r = check_doc_completeness("nothing", ["A", "B", "C"])
        assert not r.passed
        assert r.score == 0.0


class TestDocSymbolAccuracy:
    def test_all_accurate(self):
        md = "`MyApp.Foo` in `Bar.cs`"
        r = check_doc_symbol_accuracy(md, {"MyApp.Foo"}, {"Bar.cs"})
        assert r.passed

    def test_phantom_references(self):
        md = "`Ghost.Class` is mentioned"
        r = check_doc_symbol_accuracy(md, {"MyApp.Foo"}, set())
        assert not r.passed

    def test_no_refs(self):
        md = "Plain text no backticks"
        r = check_doc_symbol_accuracy(md, {"Foo"}, set())
        assert r.passed

    def test_partial_match(self):
        md = "`Foo` is a class"
        r = check_doc_symbol_accuracy(md, {"MyApp.Foo"}, set())
        assert r.passed


class TestDocStaleness:
    def test_current(self):
        r = check_doc_staleness("snap-1", "snap-1")
        assert r.passed
        assert r.score == 1.0

    def test_stale(self):
        r = check_doc_staleness("snap-old", "snap-new")
        assert not r.passed
        assert r.score == 0.0
        assert "stale" in r.message


class TestDocCoverage:
    def test_full_coverage(self):
        r = check_doc_coverage({"A", "B", "C"}, {"A", "B", "C"})
        assert r.passed
        assert r.score == 1.0

    def test_partial_coverage(self):
        r = check_doc_coverage({"A"}, {"A", "B", "C"})
        assert r.score < 1.0

    def test_no_public_symbols(self):
        r = check_doc_coverage(set(), set())
        assert r.passed

    def test_zero_coverage(self):
        r = check_doc_coverage(set(), {"A", "B"})
        assert not r.passed
        assert r.score == 0.0
