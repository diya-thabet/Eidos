"""
Evaluation & Guardrails engine (Phase 7).

Modules:
    models                  - EvalResult, EvalScore, GuardrailCheck, etc.
    hallucination_detector  - Verify LLM outputs against code graph facts
    answer_evaluator        - Score Q&A answers for grounding & coverage
    doc_evaluator           - Score generated docs for accuracy & completeness
    review_evaluator        - Score PR reviews for precision & recall
    sanitizer               - Input/output sanitization & prompt injection guard
    runner                  - Orchestrator: run all evaluations for a snapshot
"""
