"""
Tests for the question router.

Covers: classification of all question types, target symbol extraction,
question building, and edge cases.
"""

from app.reasoning.models import QuestionType
from app.reasoning.question_router import (
    build_question,
    classify_question,
    extract_target_symbol,
)


class TestClassifyQuestion:
    def test_architecture_question(self):
        assert classify_question("How is the system structured?") == QuestionType.ARCHITECTURE

    def test_architecture_keywords(self):
        assert classify_question("What is the overall architecture?") == QuestionType.ARCHITECTURE
        assert classify_question("Explain the module organization") == QuestionType.ARCHITECTURE
        assert classify_question("Show me the high-level design") == QuestionType.ARCHITECTURE

    def test_flow_question(self):
        assert classify_question("What happens when a user submits an order?") == QuestionType.FLOW

    def test_flow_keywords(self):
        assert classify_question("Trace the call chain for CreateOrder") == QuestionType.FLOW
        assert classify_question("Show the execution sequence") == QuestionType.FLOW
        assert classify_question("What is the data flow for payments?") == QuestionType.FLOW

    def test_impact_question(self):
        assert classify_question("What would break if I change UserService?") == QuestionType.IMPACT

    def test_impact_keywords(self):
        assert (
            classify_question("What is the blast radius of modifying GetById?")
            == QuestionType.IMPACT
        )
        assert classify_question("What depends on the OrderService?") == QuestionType.IMPACT
        assert (
            classify_question("What are the side effects of changing this?") == QuestionType.IMPACT
        )

    def test_component_question(self):
        assert classify_question("What does the UserService class do?") == QuestionType.COMPONENT

    def test_component_keywords(self):
        assert classify_question("Explain the OrderController") == QuestionType.COMPONENT
        assert classify_question("Describe the purpose of GetById method") == QuestionType.COMPONENT
        assert (
            classify_question("What is the role of IUserService interface?")
            == QuestionType.COMPONENT
        )

    def test_general_fallback(self):
        assert classify_question("How many files are there?") == QuestionType.GENERAL
        assert classify_question("Hello") == QuestionType.GENERAL

    def test_case_insensitive(self):
        assert classify_question("WHAT IS THE ARCHITECTURE?") == QuestionType.ARCHITECTURE

    def test_mixed_signals_picks_strongest(self):
        # "impact" + "change" + "break" = 3 impact signals
        q = "What would break and what is the impact if I change this method?"
        assert classify_question(q) == QuestionType.IMPACT


class TestExtractTargetSymbol:
    def test_backtick_quoted(self):
        assert (
            extract_target_symbol("What does `MyApp.Services.UserService` do?")
            == "MyApp.Services.UserService"
        )

    def test_dotted_identifier(self):
        assert (
            extract_target_symbol("Explain MyApp.Services.UserService")
            == "MyApp.Services.UserService"
        )

    def test_pascal_case(self):
        assert extract_target_symbol("What does UserService do?") == "UserService"

    def test_no_symbol(self):
        assert extract_target_symbol("How is the system organized?") == ""

    def test_multiple_backticks_returns_first(self):
        result = extract_target_symbol("Compare `Foo.Bar` and `Baz.Qux`")
        assert result == "Foo.Bar"

    def test_longest_dotted(self):
        result = extract_target_symbol("See MyApp.Services.UserService.GetById and MyApp.Foo")
        assert "MyApp.Services.UserService.GetById" == result


class TestBuildQuestion:
    def test_builds_with_type_and_symbol(self):
        q = build_question("What does `MyApp.Foo` do?", "snap-001")
        assert q.question_type == QuestionType.COMPONENT
        assert q.target_symbol == "MyApp.Foo"
        assert q.snapshot_id == "snap-001"

    def test_impact_gets_higher_max_hops(self):
        q = build_question("What would break if I change Foo?", "snap-001")
        assert q.question_type == QuestionType.IMPACT
        assert q.max_hops == 3

    def test_architecture_gets_lower_max_hops(self):
        q = build_question("What is the architecture?", "snap-001")
        assert q.question_type == QuestionType.ARCHITECTURE
        assert q.max_hops == 1

    def test_general_default_hops(self):
        q = build_question("Hello", "snap-001")
        assert q.max_hops == 2
