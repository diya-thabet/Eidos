# Phase 5 -- PR Review Engine

## Overview

Phase 5 adds an automated PR review engine that analyses unified diffs
against an indexed codebase snapshot. It focuses on **behavioural risks**
(not style or formatting) and produces structured findings with evidence,
blast-radius analysis, and a risk score.

## Pipeline Flow

```
Unified Diff (from git diff / PR webhook)
       |
       v
  Diff Parser            (parse files, hunks, line numbers)
       |
       v
  Symbol Mapper          (map changed lines -> known symbols via DB)
       |
       v
  Heuristic Engine       (8 behavioural risk detectors)
       |
       v
  Impact Analyser        (BFS over call graph for blast radius)
       |
       v
  Risk Scorer            (0-100 composite score)
       |
       v
  (Optional) LLM         (narrative risk summary)
       |
       v
  ReviewReport           (persisted to DB, returned via API)
```

## Components

### 1. Diff Parser (`reviews/diff_parser.py`)

Parses standard unified diff format into structured objects:

- **FileDiff**: path, old_path, is_new, is_deleted, is_renamed, hunks
- **DiffHunk**: old_start, old_count, new_start, new_count, lines
- **DiffLine**: number, old_number, content, is_added, is_removed

Handles: new files, deleted files, renamed files, multiple hunks, binary (skipped).

**Symbol mapping**: `map_lines_to_symbols()` takes a FileDiff and a list of
known symbols from the DB, and returns symbols whose line ranges overlap
with changed lines.

### 2. Heuristic Engine (`reviews/heuristics.py`)

Eight behavioural risk detectors -- each scans diff hunks for patterns
that indicate real behavioural changes:

| Heuristic | Category | Severity | What It Detects |
|-----------|----------|----------|-----------------|
| `detect_removed_validation` | `removed_validation` | HIGH | Removed guard clauses, ArgumentException, Guard.* |
| `detect_removed_null_check` | `removed_null_check` | HIGH | Removed `!= null`, `?? `, `?.`, `is null` |
| `detect_removed_error_handling` | `removed_error_handling` | HIGH | Removed try/catch/finally |
| `detect_changed_condition` | `changed_condition` | MEDIUM | Modified if/while/switch conditions |
| `detect_new_side_effects` | `new_side_effect` | MEDIUM | New SaveChanges, Delete, Send, File ops |
| `detect_changed_return` | `changed_return` | MEDIUM | Modified return statements |
| `detect_concurrency_risk` | `concurrency_risk` | MEDIUM | lock, async, static mutable state |
| `detect_security_sensitive` | `security_sensitive` | HIGH/MEDIUM | password, auth attrs, raw SQL, crypto |

**Design principle**: No style nitpicks. Every finding represents a potential
behavioural change that could break something.

### 3. Impact Analyser (`reviews/impact_analyzer.py`)

BFS traversal of **inbound call edges** to find the blast radius:

```
Changed symbol S
  <- caller A (distance 1)
  <- caller B (distance 1)
     <- caller C (distance 2)
        <- caller D (distance 3)
```

Configuration: max 3 hops, max 50 impacted symbols.

### 4. Risk Scorer (`reviews/impact_analyzer.py`)

Composite 0-100 score:

| Factor | Max Points | Calculation |
|--------|-----------|-------------|
| Changed symbols | 20 | 4 per symbol |
| Blast radius | 30 | 3 per impacted symbol |
| Findings count | 30 | 5 per finding |
| High severity | 20 | 10 per high/critical finding |

| Score | Level |
|-------|-------|
| 0-24 | low |
| 25-49 | medium |
| 50-69 | high |
| 70-100 | critical |

### 5. Reviewer Orchestrator (`reviews/reviewer.py`)

Coordinates the full pipeline. Also:
- Adds `high_fan_in_change` findings for symbols with >= 5 callers
- Deduplicates findings by (category, file, line)
- Optionally calls LLM for a narrative risk summary
- Gracefully handles LLM failures

## Database Model

```sql
CREATE TABLE reviews (
    id           SERIAL PRIMARY KEY,
    snapshot_id  VARCHAR(24) REFERENCES repo_snapshots(id) ON DELETE CASCADE,
    diff_summary TEXT NOT NULL,
    risk_score   INTEGER DEFAULT 0,
    risk_level   VARCHAR(16) DEFAULT 'low',
    report_json  TEXT NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
```

## API Endpoints

### `POST /repos/{id}/snapshots/{sid}/review`

Submit a diff for review.

**Request:**
```json
{
  "diff": "diff --git a/Foo.cs b/Foo.cs\n...",
  "max_hops": 3
}
```

**Response:**
```json
{
  "id": 1,
  "snapshot_id": "snap-001",
  "diff_summary": "1 file(s) changed, +2 additions, -3 deletions, 1 symbol(s) affected.",
  "files_changed": ["Services/UserService.cs"],
  "changed_symbols": [
    {"fq_name": "MyApp.UserService.GetById", "kind": "method", "file_path": "...", "change_type": "modified", "lines_changed": 3}
  ],
  "findings": [
    {
      "category": "removed_validation",
      "severity": "high",
      "title": "Removed validation or guard clause",
      "description": "A validation check was removed: `if (id <= 0) throw new ArgumentNullException(...)`",
      "file_path": "Services/UserService.cs",
      "line": 12,
      "evidence": "if (id <= 0) throw new ArgumentNullException(nameof(id))",
      "suggestion": "Verify the validation is handled elsewhere or is no longer needed."
    }
  ],
  "impacted_symbols": [
    {"fq_name": "MyApp.Controller.HandleRequest", "kind": "method", "file_path": "...", "distance": 1}
  ],
  "risk_score": 35,
  "risk_level": "medium",
  "llm_summary": ""
}
```

### `GET /repos/{id}/snapshots/{sid}/reviews`

List all past reviews for a snapshot.

## Integration with CI/CD

```bash
# In your CI pipeline:
DIFF=$(git diff origin/main...HEAD)
curl -X POST "http://eidos:8000/repos/$REPO_ID/snapshots/$SNAP_ID/review" \
  -H "Content-Type: application/json" \
  -d "{\"diff\": $(echo "$DIFF" | jq -Rs .)}"
```
