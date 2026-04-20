# System Hardening & Production Readiness

This document describes the hardening pass applied to make Eidos
production-ready with robust input validation, security guards, and
comprehensive parser coverage.

---

## Input Validation (RepoCreate)

All user-supplied fields on `POST /repos` are now validated:

| Field | Validation |
|-------|-----------|
| `name` | Non-empty, max 256 chars, whitespace-stripped |
| `url` | Must be http/https, blocked hosts: `localhost`, `127.0.0.1`, `0.0.0.0`, `::1`, `metadata.google.internal` |
| `default_branch` | Non-empty, no `..` path traversal, no leading `/`, max 128 chars |
| `git_provider` | Must be one of: `github`, `gitlab`, `azure_devops`, `bitbucket`, `other` |
| `git_token` | Max 1024 chars |

Invalid input returns `422 Unprocessable Entity` with detailed error messages.

---

## Path Traversal Protection

`scan_files()` in `app/core/ingestion.py` now:

1. **Resolves** every file path and verifies it is within the repo root
2. **Rejects** any relative path containing `..`
3. **Logs warnings** for suspicious paths

This prevents symlink-based or crafted filename attacks from reading
files outside the cloned repository.

---

## Parser Enhancements

### Python

- `@property` decorated methods are now detected as `PROPERTY` kind
- `@staticmethod` and `@classmethod` are extracted as modifiers
- Decorated classes at top level (`@dataclass class Foo:`) are now parsed
- All dunder methods (`__init__`, `__str__`, `__repr__`, `__eq__`) extracted

### TypeScript

- **Arrow functions**: `export const fn = () => {}` now extracted as symbols
  with parameters, return types, and call edges
- **Type aliases**: `export type UserId = string` extracted as INTERFACE kind
- **Abstract methods** in abstract classes parsed correctly
- **Optional parameters** (`x?: number`) extracted
- **Rest parameters** (`...args: number[]`) extracted

### Java

- Enum methods and fields inside `enum_body_declarations` fully parsed
- Annotation types (`@interface`) recognized
- Abstract methods in abstract classes parsed

---

## Security Hardening

### Sanitizer Coverage

The sanitizer now catches:

| Pattern | Category | Action |
|---------|----------|--------|
| OpenAI keys (`sk-...`) | `pii:api_key` | Redacted |
| GitHub tokens (`ghp_...`) | `pii:api_key` | Redacted |
| AWS keys (`AKIA...`) | `pii:api_key` | Redacted |
| Emails | `pii:email` | Redacted |
| SSNs | `pii:ssn` | Redacted |
| Phone numbers | `pii:phone` | Redacted |
| `ignore previous instructions` | `prompt_injection` | Filtered |
| `system:` prefix | `prompt_injection` | Filtered |
| `pretend you are` | `prompt_injection` | Filtered |
| LLaMA format tokens | `prompt_injection` | Filtered |
| Special tokens (`<\|...\|>`) | `prompt_injection` | Filtered |

### Token Encryption

- Git PATs are encrypted with Fernet (AES-128-CBC) before storage
- Tokens are never returned in API responses
- Token injection into clone URLs is provider-aware

### Binary Input Resilience

All parsers gracefully handle:
- Empty files (return empty analysis)
- Binary garbage (no crashes, partial results)
- Syntax errors (tree-sitter error-tolerant parsing)

---

## Test Coverage: 1037 tests

| Area | Tests |
|------|-------|
| Parser tests (C#, Java, Python, TypeScript) | 287 |
| Hardening tests | 82 |
| API tests | 200+ |
| Cross-module / E2E tests | 149 |
| Auth / Security tests | 42 |
| Other (indexing, reasoning, reviews, docs, guardrails) | 277 |
