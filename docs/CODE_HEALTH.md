# Code Health Analysis

> Static analysis engine with **40 rules** across **8 categories** that checks
> code for clean code principles, SOLID violations, coupling/cohesion metrics,
> code smells (Fowler catalogue), architectural patterns, naming conventions,
> and security concerns. Optional LLM integration for deeper semantic analysis.

---

## Rule Catalog (40 rules)

### Clean Code (CC) -- 8 rules

| ID | Rule | Default | Description |
|----|------|---------|-------------|
| CC001 | `long_method` | >30 lines | Method exceeds max line count |
| CC002 | `long_class` | >300 lines | Class exceeds max line count |
| CC003 | `too_many_parameters` | >5 params | Method has too many parameters |
| CC004 | `empty_method` | <=2 lines | Method body appears empty |
| CC005 | `constructor_over_injection` | >4 params | Constructor has too many dependencies |
| CC006 | `void_abuse` | >70% void | Class has too many void methods (side-effect heavy) |
| CC007 | `static_abuse` | >50% static | Class has too many static methods |
| CC008 | `mutable_public_state` | >=5 fields | Class exposes many public mutable fields |

### SOLID Principles -- 5 rules

| ID | Rule | Description |
|----|------|-------------|
| SOLID001 | `god_class` | Class has too many methods (SRP violation) |
| SOLID002 | `deep_inheritance` | Inheritance chain too deep (prefer composition) |
| SOLID003 | `fat_interface` | Interface has too many methods (ISP violation) |
| SOLID004 | `concrete_dependency` | Class depends only on concrete types (DIP violation) |
| AR003 | `swiss_army_knife` | Class implements too many interfaces (>3) |

### Complexity and Metrics -- 6 rules

| ID | Rule | Default | Description |
|----|------|---------|-------------|
| CX001 | `high_fan_out` | >10 | Method calls too many others |
| CX002 | `high_fan_in` | >15 | Symbol called by too many others |
| CX003 | `too_many_members` | >20 | Class has too many direct members |
| MT001 | `high_coupling` | CBO > threshold | Class depends on too many other classes |
| MT002 | `low_cohesion` | LCOM < 20% | Class methods share few dependencies |
| MT003 | `complexity_density` | >0.5 calls/line | High fan-out relative to method size |

### Documentation -- 1 rule

| ID | Rule | Description |
|----|------|-------------|
| DOC001 | `missing_doc` | Public symbol lacks documentation |

### Naming -- 4 rules

| ID | Rule | Description |
|----|------|-------------|
| NM001 | `short_name` | Symbol name too short to be descriptive |
| NM002 | `non_boolean_bool_name` | Boolean method lacks is/has/can prefix |
| NM003 | `inconsistent_naming` | Class mixes camelCase and snake_case |
| NM004 | `hungarian_notation` | Symbol uses type prefixes (strName, bIsValid) |

### Design and Code Smells (Fowler catalogue) -- 10 rules

| ID | Rule | Severity | Description |
|----|------|----------|-------------|
| DS001 | `circular_dependency` | ERROR | Classes have circular dependencies |
| DS002 | `orphan_class` | INFO | Class is never referenced |
| SM001 | `dead_method` | WARNING | Method with zero fan-in (never called) |
| SM002 | `feature_envy` | WARNING | Method uses another class more than its own |
| SM003 | `data_class` | INFO | Class with >80% fields, little behavior (anemic) |
| SM004 | `shotgun_surgery` | ERROR | Called from 5+ different classes |
| SM005 | `middle_man` | INFO | Class delegates all methods to one target |
| SM006 | `speculative_generality` | INFO | Interface with 0-1 implementors |
| SM007 | `lazy_class` | INFO | Class with only 1 method |

### Architecture -- 2 rules

| ID | Rule | Description |
|----|------|-------------|
| AR001 | `module_tangle` | Namespaces have circular dependencies |
| AR002 | `deep_namespace` | Namespace depth > 5 levels |

### Security -- 3 rules

| ID | Rule | Severity | Description |
|----|------|----------|-------------|
| SEC001 | `hardcoded_secret` | CRITICAL | Field name suggests hardcoded secret |
| SEC002 | `sql_injection_risk` | CRITICAL | Method name suggests raw SQL execution |
| SEC003 | `insecure_field` | WARNING | Public field with sensitive name |

### Best Practices -- 2 rules

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

Returns metadata for all 40 rules.

### Run health check

```
POST /repos/{repo_id}/snapshots/{snapshot_id}/health
```

**Request body** (all fields optional -- defaults shown):

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

### Category filtering

Only run SOLID and security checks:

```json
{ "categories": ["solid", "security"] }
```

### Disable specific rules

```json
{ "disabled_rules": ["NM001", "CC004", "SM001"] }
```

### Custom thresholds (strict mode)

```json
{
    "max_method_lines": 20,
    "max_class_lines": 200,
    "max_parameters": 3,
    "max_god_class_methods": 10
}
```

---

## LLM Integration

Set `"use_llm": true` for AI-powered insights on top of rule-based findings.
Requires `EIDOS_LLM_BASE_URL` configured (see [DOCKER_GUIDE.md](DOCKER_GUIDE.md)).

---

## Scoring

- **Category scores**: `100 - (findings / symbols * 100)` per category
- **Overall score**: `100 - (weighted_penalty / symbols * 10)`
  - Critical = 10 points, Error = 5, Warning = 2, Info = 1
- Findings sorted by severity (critical first)
