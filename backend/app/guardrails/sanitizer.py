"""
Input/output sanitizer.

Protects against prompt injection, removes PII patterns,
and validates text safety before sending to LLM or returning
to users.
"""

from __future__ import annotations

import re

from app.guardrails.models import (
    EvalCategory,
    EvalCheck,
    EvalSeverity,
    SanitizationResult,
)

# -------------------------------------------------------------------
# Prompt injection patterns
# -------------------------------------------------------------------

_INJECTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I),
        "prompt_injection:ignore_previous",
    ),
    (
        re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.I),
        "prompt_injection:role_override",
    ),
    (
        re.compile(r"system\s*:\s*", re.I),
        "prompt_injection:system_prefix",
    ),
    (
        re.compile(
            r"(do\s+not|don'?t)\s+(follow|obey|listen|use)\s+"
            r"(your|the|any)\s+(rules|instructions|guidelines)",
            re.I,
        ),
        "prompt_injection:rule_override",
    ),
    (
        re.compile(r"\bpretend\b.*\b(you are|to be)\b", re.I),
        "prompt_injection:persona_hijack",
    ),
    (
        re.compile(r"<\|.*?\|>", re.I),
        "prompt_injection:special_token",
    ),
    (
        re.compile(r"\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>", re.I),
        "prompt_injection:llama_format",
    ),
]

# -------------------------------------------------------------------
# PII patterns (conservative -- only obvious formats)
# -------------------------------------------------------------------

_PII_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z]{2,}\b", re.I),
        "[EMAIL_REDACTED]",
        "pii:email",
    ),
    (
        re.compile(r"\b(?:(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})\b"),
        "[PHONE_REDACTED]",
        "pii:phone",
    ),
    (
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "[SSN_REDACTED]",
        "pii:ssn",
    ),
    (
        re.compile(
            r"\b(?:sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{36,}"
            r"|AKIA[A-Z0-9]{16})\b"
        ),
        "[API_KEY_REDACTED]",
        "pii:api_key",
    ),
]


def check_prompt_injection(text: str) -> EvalCheck:
    """Check text for prompt injection attempts."""
    detected: list[str] = []
    for pattern, label in _INJECTION_PATTERNS:
        if pattern.search(text):
            detected.append(label)

    if not detected:
        return EvalCheck(
            category=EvalCategory.INPUT_SANITIZATION,
            name="prompt_injection",
            passed=True,
            severity=EvalSeverity.PASS,
            score=1.0,
            message="No prompt injection patterns detected.",
        )

    return EvalCheck(
        category=EvalCategory.INPUT_SANITIZATION,
        name="prompt_injection",
        passed=False,
        severity=EvalSeverity.FAIL,
        score=0.0,
        message=f"Prompt injection detected: {', '.join(detected)}.",
        details={"patterns": detected},
    )


def sanitize_input(text: str) -> SanitizationResult:
    """
    Sanitize user input before processing.
    Removes injection patterns and PII.
    """
    clean = text
    issues: list[str] = []

    for pattern, label in _INJECTION_PATTERNS:
        if pattern.search(clean):
            clean = pattern.sub("[FILTERED]", clean)
            issues.append(label)

    for pattern, replacement, label in _PII_PATTERNS:
        if pattern.search(clean):
            clean = pattern.sub(replacement, clean)
            issues.append(label)

    return SanitizationResult(
        clean_text=clean,
        was_modified=bool(issues),
        issues=issues,
    )


def sanitize_output(text: str) -> SanitizationResult:
    """
    Sanitize LLM output before returning to users.
    Redacts PII and API keys that may have leaked.
    """
    clean = text
    issues: list[str] = []

    for pattern, replacement, label in _PII_PATTERNS:
        if pattern.search(clean):
            clean = pattern.sub(replacement, clean)
            issues.append(label)

    return SanitizationResult(
        clean_text=clean,
        was_modified=bool(issues),
        issues=issues,
    )


def check_output_safety(text: str) -> EvalCheck:
    """Evaluate output text for safety issues (leaked PII, etc.)."""
    result = sanitize_output(text)

    if not result.was_modified:
        return EvalCheck(
            category=EvalCategory.OUTPUT_SANITIZATION,
            name="output_safety",
            passed=True,
            severity=EvalSeverity.PASS,
            score=1.0,
            message="No safety issues in output.",
        )

    return EvalCheck(
        category=EvalCategory.OUTPUT_SANITIZATION,
        name="output_safety",
        passed=False,
        severity=EvalSeverity.WARNING,
        score=0.5,
        message=(f"Output contained sensitive patterns: {', '.join(result.issues)}."),
        details={"patterns": result.issues},
    )
