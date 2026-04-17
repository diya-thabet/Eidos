"""
Tests for the answer evaluator.

Covers: citation coverage, factual grounding, completeness,
edge cases.
"""

from app.guardrails.answer_evaluator import (
    check_answer_completeness,
    check_citation_coverage,
    check_factual_grounding,
)


class TestCitationCoverage:
    def test_no_citations(self):
        r = check_citation_coverage("answer", [], {"a.cs"})
        assert r.score == 0.5  # warning, not fail

    def test_all_valid(self):
        cites = [{"file_path": "a.cs"}, {"file_path": "b.cs"}]
        r = check_citation_coverage("answer", cites, {"a.cs", "b.cs"})
        assert r.passed
        assert r.score == 1.0

    def test_invalid_citation(self):
        cites = [{"file_path": "a.cs"}, {"file_path": "ghost.cs"}]
        r = check_citation_coverage("answer", cites, {"a.cs"})
        assert r.score == 0.5

    def test_all_invalid(self):
        cites = [{"file_path": "ghost.cs"}]
        r = check_citation_coverage("answer", cites, {"a.cs"})
        assert not r.passed
        assert r.score == 0.0

    def test_empty_file_path_skipped(self):
        cites = [{"file_path": ""}]
        r = check_citation_coverage("answer", cites, {"a.cs"})
        assert r.score == 0.0


class TestFactualGrounding:
    def test_no_backtick_refs(self):
        r = check_factual_grounding("just text", {"Foo"}, {"a.cs"})
        assert r.passed

    def test_all_grounded(self):
        text = "The class `MyApp.Foo` does work"
        r = check_factual_grounding(text, {"MyApp.Foo"}, set())
        assert r.passed
        assert r.score == 1.0

    def test_ungrounded_refs(self):
        text = "The class `MyApp.Ghost` does work"
        r = check_factual_grounding(text, {"MyApp.Foo"}, set())
        assert not r.passed

    def test_partial_match(self):
        text = "`Foo` is a class"
        r = check_factual_grounding(text, {"MyApp.Foo"}, set())
        assert r.passed

    def test_file_match(self):
        text = "`UserService.cs` has logic"
        r = check_factual_grounding(text, set(), {"UserService.cs"})
        assert r.passed


class TestAnswerCompleteness:
    def test_no_expected(self):
        r = check_answer_completeness("text", [])
        assert r.passed
        assert r.score == 1.0

    def test_all_mentioned(self):
        text = "MyApp.Foo and MyApp.Bar are classes"
        r = check_answer_completeness(text, ["MyApp.Foo", "MyApp.Bar"])
        assert r.passed
        assert r.score == 1.0

    def test_partial_mention(self):
        text = "Only Foo is mentioned"
        r = check_answer_completeness(text, ["MyApp.Foo", "MyApp.Bar"])
        assert r.score == 0.5

    def test_none_mentioned(self):
        text = "nothing relevant"
        r = check_answer_completeness(text, ["MyApp.Foo", "MyApp.Bar"])
        assert not r.passed
        assert r.score == 0.0

    def test_short_name_match(self):
        text = "Bar does work"
        r = check_answer_completeness(text, ["MyApp.Bar"])
        assert r.passed
