# Eidos User Guide

A complete guide to what Eidos does and how to use every feature.

---

## What Is Eidos?

Eidos is a **code intelligence platform**. You point it at any Git repository, and it:

1. **Parses every source file** into a structured code graph (classes, methods, interfaces, fields, call relationships, inheritance)
2. **Generates summaries** at symbol, file, and module level — explaining what each piece of code does
3. **Answers questions** about the codebase in natural language
4. **Reviews pull requests** for behavioral risks (not style issues — actual logic changes that could break things)
5. **Auto-generates documentation** with citations to specific files and line numbers
6. **Tracks code health** with 40 built-in rules covering SOLID principles, complexity, coupling, and security
7. **Compares snapshots** to show what changed between versions

Everything works **without an LLM**. All features use deterministic static analysis. An optional LLM connection adds narrative enrichment, but the core engine doesn't need it.

---

## Supported Languages

| Language | What's Parsed |
|----------|--------------|
| C# | Classes, interfaces, structs, enums, methods, properties, fields, constructors, delegates, records |
| Java | Classes, interfaces, enums, methods, fields, constructors |
| Python | Classes, functions, methods, decorators, async functions |
| TypeScript / TSX | Classes, interfaces, functions, methods, type aliases, enums |
| Go | Structs, interfaces, functions, methods |
| Rust | Structs, enums, traits, functions, impl blocks, methods |
| C | Functions, structs, enums, typedefs |
| C++ | Classes, structs, functions, methods, namespaces, templates |

All parsers use [tree-sitter](https://tree-sitter.github.io/) for accurate AST-based analysis (not regex).

---

## Core Concepts

### Repository

A Git repository you want to analyze. You register it once with its URL.

### Snapshot

A point-in-time analysis of a repository at a specific commit. Every time you run ingestion, a new snapshot is created. Older snapshots are preserved, so you can compare them.

### Symbol

Any named code entity: a class, method, interface, function, field, property, etc. Each symbol has a **fully-qualified name** (e.g., `MyApp.Services.OrderService.PlaceOrder`), a file path, and line numbers.

### Edge

A relationship between two symbols: calls, inherits, implements, uses, or contains.

### Summary

An auto-generated explanation of what a symbol, file, or module does. Includes purpose, side effects, risks, and citations.

---

## Feature Guide

### 1. Analysis — Understand the Code Structure

After ingestion, Eidos gives you:

**Symbols** — Every class, method, interface in the codebase:

```
GET /repos/{id}/snapshots/{sid}/symbols
GET /repos/{id}/snapshots/{sid}/symbols?kind=class
GET /repos/{id}/snapshots/{sid}/symbols?file_path=Services/OrderService.cs
```

**Edges** — How symbols relate to each other:

```
GET /repos/{id}/snapshots/{sid}/edges
GET /repos/{id}/snapshots/{sid}/edges?edge_type=calls&source=MyApp.OrderService.PlaceOrder
```

**Call Graph** — Who calls a symbol, and who it calls:

```
GET /repos/{id}/snapshots/{sid}/graph/MyApp.OrderService.PlaceOrder
```

Returns: the symbol, its callers, its callees, and its children (methods inside a class).

**Overview** — High-level stats:

```
GET /repos/{id}/snapshots/{sid}/overview
```

Returns: symbol counts by kind, edge counts by type, file count, namespace list.

---

### 2. Search — Find Anything

Full-text search across symbols, summaries, and generated docs:

```
GET /repos/{id}/snapshots/{sid}/search?q=authentication
GET /repos/{id}/snapshots/{sid}/search?q=OrderService&entity_type=symbol
GET /repos/{id}/snapshots/{sid}/search?q=database&entity_type=summary
```

Results are ranked by relevance. Each hit includes entity type, title, snippet, file path, and a relevance score.

---

### 3. Q&A — Ask Questions About the Code

Ask anything in natural language:

```
POST /repos/{id}/snapshots/{sid}/ask
{
  "question": "How does the payment processing work?",
  "target_symbol": "PaymentService"     // optional: focus on a specific symbol
}
```

The system:
1. Classifies your question (architecture, flow, component, or impact)
2. Retrieves relevant context via vector search + graph traversal
3. Builds a structured answer

**Response includes:**
- The answer text
- **Evidence**: specific files, symbols, and line ranges that support the answer
- **Confidence**: high, medium, or low
- **Verification steps**: how to manually verify the answer

---

### 4. PR Review — Behavioral Risk Analysis

Submit a unified diff:

```
POST /repos/{id}/snapshots/{sid}/review
{
  "diff": "<unified diff string>"
}
```

**What it detects:**
- Removed input validation or guard clauses
- Changed conditional logic
- Modified error handling
- Altered security-related code
- Changed database queries
- Modified concurrency patterns
- Removed logging
- Changed API contracts

**Response includes:**
- Risk score (0.0 to 1.0)
- Risk level (low / medium / high / critical)
- Each finding with severity, file path, line number, and evidence
- Blast radius: which other symbols are affected by the changes

---

### 5. Documentation — Auto-Generate Docs

```
POST /repos/{id}/snapshots/{sid}/docs
{}
```

Generates multiple document types:
- **README** — Project overview, architecture, key components
- **Architecture** — System structure, layers, dependencies
- **Module docs** — Per-namespace documentation
- **Flow docs** — Data flow descriptions
- **Runbooks** — Operational guides

Every statement in the generated docs includes **citations** — the exact file and line range where the information comes from. No hallucinations.

---

### 6. Code Health — 40 Built-In Rules

```
POST /repos/{id}/snapshots/{sid}/health
```

**Rule categories:**
- **SOLID**: Single responsibility, open/closed, Liskov, interface segregation, dependency inversion
- **Clean code**: Method length, class size, parameter count, nesting depth
- **Complexity**: Cyclomatic complexity, coupling metrics
- **Design smells**: God class, feature envy, shotgun surgery, data clumps
- **Naming**: PascalCase, camelCase, abbreviation detection
- **Security**: Hardcoded secrets, SQL injection patterns, unsafe deserialization
- **Architecture**: Circular dependencies, layer violations

**Response**: Each violation includes the rule name, severity, affected symbol, file path, line, and a human-readable explanation.

See all available rules:

```
GET /repos/{id}/snapshots/{sid}/health/rules
```

---

### 7. Diagrams — Visualize the Architecture

```
GET /repos/{id}/snapshots/{sid}/diagram?diagram_type=class
GET /repos/{id}/snapshots/{sid}/diagram?diagram_type=module
GET /repos/{id}/snapshots/{sid}/diagram?diagram_type=class&namespace=MyApp.Services
```

Returns **Mermaid syntax** that you can paste into:
- GitHub Markdown (renders automatically)
- [Mermaid Live Editor](https://mermaid.live)
- Any documentation tool that supports Mermaid

**Class diagram** shows classes, interfaces, their members, and inheritance/implementation relationships.

**Module diagram** shows namespaces and their cross-namespace dependencies.

---

### 8. Snapshot Comparison — What Changed?

Compare two snapshots to see what evolved:

```
GET /repos/{id}/snapshots/{sid1}/diff/{sid2}
```

Returns:
- **Added symbols** — new classes, methods, etc.
- **Removed symbols** — deleted code
- **Modified symbols** — changed signature, moved file, different line range
- **Summary**: counts of each category + unchanged count

---

### 9. Health Trends — Is It Getting Better?

Track health scores over time:

```
GET /repos/{id}/health/trend
```

Returns:
- Score for each snapshot that has been evaluated
- Overall trend: **improving**, **degrading**, **stable**, or **insufficient_data**
- Score change between first and latest

---

### 10. Export — Get Everything as JSON

Download the complete analysis for CI/CD integration or offline use:

```
GET /repos/{id}/snapshots/{sid}/export
```

Returns all symbols, edges, summaries, and generated docs in a single JSON payload.

---

### 10b. Portable Export & Import — Migrate Between Instances

Export a snapshot as a compact `.eidos` file (gzip-compressed JSON with short keys):

```
GET /repos/{id}/snapshots/{sid}/portable
```

This downloads a binary file that is typically **80-90% smaller** than the raw JSON export. The file contains everything: symbols, edges, files, summaries, docs, and evaluations.

To restore it on another Eidos instance (or the same one after a reset):

```
POST /repos/{id}/import
Content-Type: multipart/form-data
Body: file=<your-file.eidos>
```

This creates a new snapshot with status `completed` and all data restored. No re-cloning or re-parsing needed.

**Use cases:**
- Migrate analysis results between staging and production
- Back up a snapshot before a database reset
- Share analysis with a colleague who has their own Eidos instance
- Pre-compute analysis in CI and import the result into the main server

---

### 10c. API Key Authentication -- Programmatic Access

For CI/CD pipelines and scripts that can't do an OAuth dance, create an API key:

```
POST /auth/api-keys?name=my-ci-pipeline
```

Response (the raw key is shown **only once**):
```json
{"id": "abc123", "name": "my-ci-pipeline", "key": "eidos_abc...xyz", "prefix": "eidos_abc..."}
```

Use the key in any request via the `X-API-Key` header:
```
GET /repos/my-repo/status
X-API-Key: eidos_abc...xyz
```

Manage your keys:
- `GET /auth/api-keys` -- list active keys (shows prefix, not raw key)
- `DELETE /auth/api-keys/{id}` -- revoke a key permanently

**Security**: Keys are SHA-256 hashed in the database. The raw key is never stored.

---

### 11. Webhooks — Auto-Analyze on Push

Configure your Git provider to send push events to Eidos:

| Provider | Webhook URL | Auth |
|----------|-------------|------|
| GitHub | `POST /webhooks/github` | HMAC-SHA256 (`X-Hub-Signature-256`) |
| GitLab | `POST /webhooks/gitlab` | Shared token (`X-Gitlab-Token`) |
| Any | `POST /webhooks/push` | Body-based matching |

When a push happens to the repo's default branch, Eidos automatically creates a new snapshot and runs the full analysis pipeline.

---

### 12. Guardrails & Evaluation

Run quality checks on Eidos's own output:

```
POST /repos/{id}/snapshots/{sid}/evaluate
```

Checks:
- Document completeness (are all modules documented?)
- Symbol coverage (are all public APIs summarized?)
- Output safety (PII detection, sensitive data redaction)

---

## API Reference

Open **http://localhost:8000/docs** for the complete interactive Swagger UI with all endpoints, parameters, and response schemas.

---

## Architecture at a Glance

```
???????????????     ????????????????     ????????????????
?  Git Repo   ???????  Ingestion   ???????   Parsing    ?
?  (any lang) ?     ?  (clone)     ?     ?  (tree-sitter)?
???????????????     ????????????????     ????????????????
                                                ?
                    ?????????????????????????????
                    ?
            ????????????????     ????????????????
            ? Code Graph   ???????  Summaries   ?
            ? (symbols +   ?     ?  (facts +    ?
            ?  edges)      ?     ?   optional   ?
            ????????????????     ?   LLM)       ?
                   ?             ????????????????
                   ?                    ?
            ????????????????     ????????????????
            ? PostgreSQL   ?     ?   Qdrant     ?
            ? (structured) ?     ?  (vectors)   ?
            ????????????????     ????????????????
```

Every output includes **evidence** (file + line range), **confidence** (high/medium/low), and **verification steps**.

---

## Key Design Principles

1. **Evidence-first**: Every answer, finding, and doc section cites specific files and lines
2. **No LLM required**: Core engine is fully deterministic
3. **Language-agnostic**: Same API, same output format, regardless of source language
4. **Snapshot-based**: Analyses are immutable — you can always go back and compare
5. **Extensible**: Adding a new language = 1 parser file + 2 lines of registration
