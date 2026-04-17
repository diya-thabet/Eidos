"""
Tests for the hallucination detector.

Covers: symbol verification, relationship verification,
partial matches, edge cases, and severity scoring.
"""

from app.guardrails.hallucination_detector import (
    check_hallucinated_relationships,
    check_hallucinated_symbols,
)


class TestHallucinatedSymbols:
    def test_no_references(self):
        r = check_hallucinated_symbols("Hello world", {"A"}, {"b.cs"})
        assert r.passed
        assert r.score == 1.0

    def test_all_valid(self):
        text = "`MyApp.Foo` is in `Bar.cs`"
        r = check_hallucinated_symbols(text, {"MyApp.Foo"}, {"Bar.cs"})
        assert r.passed
        assert r.score == 1.0

    def test_hallucinated_symbol(self):
        text = "`MyApp.Foo` calls `MyApp.Ghost`"
        r = check_hallucinated_symbols(text, {"MyApp.Foo"}, {"Foo.cs"})
        assert not r.passed
        assert "Ghost" in str(r.details.get("hallucinated", []))

    def test_partial_match_accepted(self):
        text = "`Foo` does something"
        r = check_hallucinated_symbols(text, {"MyApp.Foo"}, set())
        assert r.passed

    def test_many_hallucinations_low_score(self):
        text = "`A.B` `C.D` `E.F` `G.H`"
        r = check_hallucinated_symbols(text, set(), set())
        assert not r.passed
        assert r.score < 0.5

    def test_severity_warning_for_few(self):
        text = "`MyApp.Foo` `MyApp.Ghost`"
        r = check_hallucinated_symbols(text, {"MyApp.Foo"}, set())
        assert r.severity.value in ("warning", "fail")

    def test_file_references_verified(self):
        text = "`UserService.cs` has `MyApp.Svc`"
        r = check_hallucinated_symbols(text, {"MyApp.Svc"}, {"UserService.cs"})
        assert r.passed

    def test_empty_sets(self):
        r = check_hallucinated_symbols("", set(), set())
        assert r.passed


class TestHallucinatedRelationships:
    def test_no_claims(self):
        r = check_hallucinated_relationships(
            "No relationships here",
            {("A", "B")},
        )
        assert r.passed

    def test_valid_call(self):
        text = "`Foo` calls `Bar`"
        r = check_hallucinated_relationships(text, {("Foo", "Bar")})
        assert r.passed

    def test_false_call(self):
        text = "`Foo` calls `Baz`"
        r = check_hallucinated_relationships(text, {("Foo", "Bar")})
        assert not r.passed

    def test_inherits_claim(self):
        text = "`Child` extends `Parent`"
        r = check_hallucinated_relationships(text, {("Child", "Parent")})
        assert r.passed

    def test_false_inherits(self):
        text = "`Child` inherits `Ghost`"
        r = check_hallucinated_relationships(text, {("Child", "Parent")})
        assert not r.passed

    def test_empty_edges(self):
        text = "`A` calls `B`"
        r = check_hallucinated_relationships(text, set())
        assert not r.passed
