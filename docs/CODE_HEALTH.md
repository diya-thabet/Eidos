# Code Health Analysis

> Static analysis engine that checks code for clean code principles, SOLID violations,
> complexity issues, naming conventions, security concerns, and design anti-patterns.
> Optional LLM integration for deeper semantic analysis.

---

## Overview

The code health engine runs **19 rules** across **8 categories** against the parsed code graph.
Users control which rules to enable, thresholds for each rule, and whether to use LLM-powered analysis.

---

## Rule Catalog

### Clean Code (CC)

| ID | Rule | Default | Description |
|----|------|---------|-------------|
| CC001 | `long_method` | >30 lines | Method exceeds max line count |
| CC002 | `long_class` | >300 lines | Class exceeds max line count |
| CC003 | `too_many_parameters` | >5 params | Method has too many parameters |
| CC004 | `empty_method` | <=2 lines | Method body appears empty |

### SOLID Principles

| ID | Rule | Description |
|----|------|-------------|
| SOLID001 | `god_class` | Class has too many methods (SRP violation) |
| SOLID002 | `deep_inheritance` | Inheritance chain too deep (prefer composition) |
| SOLID003 | `fat_interface` | Interface has too many methods (ISP violation) |
| SOLID004 | `concrete_dependency` | Class depends only on concrete types (DIP violation) |

### Complexity (CX)

| ID | Rule | Default | Description |
|----|------|---------|-------------|
| CX001 | `high_fan_out` | >10 | Method calls too many others |
| CX002 | `high_fan_in` | >15 | Symbol called by too many others |
| CX003 | `too_many_members` | >20 | Class has too many direct members |

### Documentation (DOC)

| ID | Rule | Description |
|----|------|-------------|
| DOC001 | `missing_doc` | Public symbol lacks documentation |

### Naming (NM)

| ID | Rule | Description |
|----|------|-------------|
| NM001 | `short_name` | Symbol name too short to be descriptive |
| NM002 | `non_boolean_bool_name` | Boolean method lacks is/has/can prefix |

### Design (DS)

| ID | Rule | Description |
|----|------|-------------|
| DS001 | `circular_dependency` | Classes have circular dependencies |
| DS002 | `orphan_class` | Class is never referenced |

### Security (SEC)

| ID | Rule | Severity | Description |
|----|------|----------|-------------|
| SEC001 | `hardcoded_secret` | CRITICAL | Field name suggests hardcoded secret |

### Best Practices (BP)

| ID | Rule | Description |
|----|------|-------------|
| BP001 | `large_file` | File contains >30 symbols |
| BP002 | `excessive_imports` | File has >15 imports |

---

## API Usage

### List available rules

```
GET /repos/{repo_id}/snapshots/{snapshot_id}/health/rules
```

Returns metadata for all 19 rules.

### Run health check

```
POST /repos/{repo_id}/snapshots/{snapshot_id}/health
```

**Request body** (all fields optional — defaults shown):

```json
{
    "categories": [],
    "disabled_rules": [],
    "max_method_lines": 30,
    "max_class_lines": 300,
    "max_parameters": 5,
    "max_fan_out": 10,
    "max_fan_in": 15,
    "max_children": 20,
    "max_inheritance_depth": 4,
    "max_god_class_methods": 15,
    "use_llm": false
}
```

**Response:**

```json
{
    "total_symbols": 142,
    "total_files": 12,
    "findings_count": 7,
    "findings": [
        {
            "rule_id": "SEC001",
            "rule_name": "hardcoded_secret",
            "category": "security",
            "severity": "critical",
            "symbol": "Config.api_key",
            "file": "src/config.rs",
            "line": 15,
            "message": "Field 'api_key' may contain a hardcoded secret",
            "suggestion": "Use environment variables or a secrets manager"
        }
    ],
    "summary": {
        "critical": 1,
        "warning": 4,
        "info": 2
    },
    "category_scores": {
        "security": 99.3,
        "clean_code": 97.2,
        "solid": 100.0
    },
    "overall_score": 92.5,
    "llm_insights": []
}
```

### Category filtering

Only run SOLID and security checks:

```json
{
    "categories": ["solid", "security"]
}
```

### Disable specific rules

Run everything except short-name and empty-method checks:

```json
{
    "disabled_rules": ["NM001", "CC004"]
}
```

### Custom thresholds

Strict mode:

```json
{
    "max_method_lines": 20,
    "max_class_lines": 200,
    "max_parameters": 3,
    "max_god_class_methods": 10
}
```

Relaxed mode:

```json
{
    "max_method_lines": 60,
    "max_class_lines": 500,
    "max_parameters": 8
}
```

---

## LLM Integration

Set `"use_llm": true` to get AI-powered insights on top of the rule-based findings.

The LLM receives:
- The health score and top findings
- Key symbol metrics (size, fan-in, fan-out)

It returns:
- Naming quality assessment
- Design pattern suggestions
- Refactoring recommendations
- Architecture improvement advice

**Requires** `EIDOS_LLM_BASE_URL` to be configured (see [DOCKER_GUIDE.md](DOCKER_GUIDE.md)).

```json
{
    "use_llm": true,
    "categories": ["solid", "design"]
}
```

Response includes `llm_insights`:

```json
{
    "llm_insights": [
        {
            "category": "refactoring",
            "title": "Extract UserService responsibilities",
            "recommendation": "The UserService class has 18 methods spanning authentication, profile management, and notification. Split into AuthService, ProfileService, and NotificationService."
        }
    ]
}
```

---

## Scoring

- **Category scores**: `100 - (findings / symbols * 100)` per category
- **Overall score**: `100 - (weighted_penalty / symbols * 10)`
  - Critical finding = 10 points
  - Error finding = 5 points
  - Warning finding = 2 points
  - Info finding = 1 point

Findings are sorted by severity (critical first), then by file and line.
