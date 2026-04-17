# Phase 7 -- Evaluation & Guardrails

## Overview

Phase 7 adds self-verification and safety guardrails to every
output Eidos produces. The system checks LLM outputs against the
code graph, scores documentation for accuracy, validates review
findings, and blocks prompt injection and PII leaks.

## Architecture

```
              User Input
                  |
                  v
            +-----------+
            | Sanitizer |--- Prompt injection check
            +-----------+--- PII redaction
                  |
                  v
            [Pipeline]  (Q&A / Docs / Review)
                  |
                  v
          +----------------+
          | Output Safety  |--- PII leak check
          +----------------+
                  |
                  v
          +------------------+
          | Hallucination    |--- Symbol verification
          | Detector         |--- Relationship verification
          +------------------+
                  |
                  v
          +------------------+
          | Evaluators       |--- Answer: citations, grounding, completeness
          |                  |--- Docs: completeness, accuracy, staleness
          |                  |--- Reviews: precision, severity, coverage
          +------------------+
                  |
                  v
          +------------------+
          | Runner           |--- Orchestrate all checks
          +------------------+--- Persist to DB
                  |
                  v
          Evaluation table
```

## Components

### 1. Models (`guardrails/models.py`)

- **`EvalCategory`** -- hallucination, citation_coverage, factual_grounding,
  doc_completeness, doc_staleness, review_precision, input/output sanitization
- **`EvalSeverity`** -- pass, warning, fail
- **`EvalCheck`** -- single check result with score (0-1), message, details
- **`EvalReport`** -- collection of checks with auto-computed overall score/severity
- **`SanitizationResult`** -- clean text + list of issues found

### 2. Hallucination Detector (`guardrails/hallucination_detector.py`)

Extracts backtick-quoted and dotted identifiers from LLM text, verifies
each against the known symbol and file sets from the code graph.

- **`check_hallucinated_symbols`** -- finds phantom references
- **`check_hallucinated_relationships`** -- finds false "calls"/"inherits" claims

Uses substring matching for partial names (e.g. `Foo` matches `MyApp.Foo`).

### 3. Answer Evaluator (`guardrails/answer_evaluator.py`)

Scores Q&A answers on three dimensions:

- **Citation coverage** -- do cited files exist in the snapshot?
- **Factual grounding** -- do backtick references point to real code?
- **Completeness** -- are expected symbols mentioned?

### 4. Document Evaluator (`guardrails/doc_evaluator.py`)

Scores generated docs on four dimensions:

- **Section completeness** -- are expected sections present?
- **Symbol accuracy** -- do referenced symbols exist?
- **Staleness** -- was the doc generated from the current snapshot?
- **Coverage** -- what fraction of public symbols are documented?

### 5. Review Evaluator (`guardrails/review_evaluator.py`)

Scores PR reviews on three dimensions:

- **Precision** -- do findings reference real code?
- **Severity distribution** -- is there nuance, or all-one-severity?
- **Coverage** -- do findings touch the changed symbols?

### 6. Sanitizer (`guardrails/sanitizer.py`)

Input/output protection:

- **Prompt injection detection** -- 7 pattern families:
  ignore-previous, role-override, system-prefix, rule-override,
  persona-hijack, special-tokens, llama-format
- **PII redaction** -- email, phone, SSN, API keys
- **Input sanitization** -- removes injection + PII before LLM
- **Output sanitization** -- redacts leaked PII in responses

### 7. Runner (`guardrails/runner.py`)

Orchestrator that:
1. Fetches known symbols, files, edges from DB
2. Evaluates all generated docs
3. Evaluates all PR reviews
4. Runs overall coverage check
5. Computes aggregate score
6. Persists to `evaluations` table

Also provides `evaluate_answer()` for inline Q&A checking.

## Database Model

```sql
CREATE TABLE evaluations (
    id                SERIAL PRIMARY KEY,
    snapshot_id       VARCHAR(24) REFERENCES repo_snapshots(id),
    scope             VARCHAR(64) DEFAULT 'snapshot',
    overall_score     FLOAT DEFAULT 0.0,
    overall_severity  VARCHAR(16) DEFAULT 'pass',
    checks_json       TEXT NOT NULL,
    summary           TEXT DEFAULT '',
    created_at        TIMESTAMPTZ DEFAULT NOW()
);
```

## API Endpoints

### `POST /repos/{id}/snapshots/{sid}/evaluate`

Run all guardrail checks. Returns `EvalReportOut`.

### `GET /repos/{id}/snapshots/{sid}/evaluations`

List past evaluation reports.

## Scoring

- Each check produces a **score** (0.0 to 1.0) and a **severity** (pass/warning/fail)
- Overall score = average of all check scores
- Overall severity = worst severity across all checks
- A score >= 0.8 is considered healthy

## Test Coverage

| File | Tests | Scope |
|------|-------|-------|
| `test_guardrails_models.py` | 5 | EvalReport scoring, severity computation |
| `test_hallucination_detector.py` | 14 | Symbol/relationship verification, partial match |
| `test_answer_evaluator.py` | 13 | Citation coverage, grounding, completeness |
| `test_doc_evaluator.py` | 13 | Completeness, accuracy, staleness, coverage |
| `test_review_evaluator.py` | 12 | Precision, severity distribution, coverage |
| `test_sanitizer.py` | 16 | Injection detection, PII redaction, I/O sanitization |
| `test_eval_runner.py` | 10 | Full pipeline, persistence, empty snapshot, answer eval |
| `test_eval_api.py` | 8 | Endpoints, response structure, error handling |
