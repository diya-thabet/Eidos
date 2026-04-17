# Phase 6 -- Auto Documentation

## Overview

Phase 6 adds automatic documentation generation from the analysed
codebase. Documents are **deterministic** (facts from code graph and
summaries) with optional LLM narration. Every claim has a citation
back to the source code.

## Document Types

| Type | Content | Scope |
|------|---------|-------|
| `readme` | Overview, tech stack, modules, entry points, key flows, metrics | Whole codebase |
| `architecture` | Module map, dependencies, entry points, flows, hotspots | Whole codebase |
| `module` | Files, classes, public API, internals, dependencies | One namespace |
| `flow` | BFS call trace, callers, side effects | One entry point |
| `runbook` | Quick start, entry points, configuration, known risks | Whole codebase |

## Pipeline

```
DB (symbols, edges, summaries)
       |
       v
  Data Fetcher            (query all analysis data for snapshot)
       |
       v
  Template Sections       (define structure per doc type)
       |
       v
  Generator               (fill sections with factual content)
       |
       v
  Renderer                (Markdown + citation appendix)
       |
       v
  (Optional) LLM          (narrative summary, no invented facts)
       |
       v
  Persist to DB            (GeneratedDoc table)
```

## Components

### 1. Models (`docgen/models.py`)

- `DocType` -- enum: readme, architecture, module, flow, runbook
- `Citation` -- file_path + symbol + line range, renders to Markdown link
- `DocSection` -- heading, body, citations, subsections
- `GeneratedDocument` -- title, type, scope, sections, metadata

### 2. Templates (`docgen/templates.py`)

Each document type has a list of `(section_key, heading)` pairs.
The generator uses section keys to decide what content to fill in.

### 3. Generator (`docgen/generator.py`)

Five generator functions:
- `generate_readme()` -- codebase overview
- `generate_architecture()` -- structural deep-dive
- `generate_module_doc()` -- per-namespace docs with class/API listing
- `generate_flow_doc()` -- BFS call chain trace from an entry point
- `generate_runbook()` -- operations guide with config and risks

All content is deterministic. Citations are attached to every
section that references source code.

### 4. Renderer (`docgen/renderer.py`)

Converts `GeneratedDocument` to Markdown:
- H1 title with snapshot ID
- H2 sections, H3 subsections
- Citation appendix with deduplicated source links
- Symbol links: `` [`Foo.Bar`](Foo.cs#L10-L20) ``

### 5. Orchestrator (`docgen/orchestrator.py`)

Pipeline coordinator:
1. Fetches all symbols, edges, summaries from DB
2. Builds module map from namespace grouping
3. Detects entry points from symbol patterns
4. Computes simple metrics (fan-in, fan-out, LOC)
5. Generates each document type
6. Renders to Markdown
7. Optionally enriches with LLM narration
8. Persists to `generated_docs` table

## Database Model

```sql
CREATE TABLE generated_docs (
    id             SERIAL PRIMARY KEY,
    snapshot_id    VARCHAR(24) REFERENCES repo_snapshots(id),
    doc_type       VARCHAR(32) NOT NULL,  -- readme|architecture|module|flow|runbook
    scope_id       TEXT DEFAULT '',        -- module name, entry fq_name
    title          TEXT NOT NULL,
    markdown       TEXT NOT NULL,
    llm_narrative  TEXT DEFAULT '',
    metadata_json  TEXT DEFAULT '{}',
    created_at     TIMESTAMPTZ DEFAULT NOW()
);
```

## API Endpoints

### `POST /repos/{id}/snapshots/{sid}/docs`

Generate documentation.

**Request (generate all):**
```json
{}
```

**Request (generate specific):**
```json
{
  "doc_type": "module",
  "scope_id": "MyApp.Services"
}
```

**Response:**
```json
{
  "snapshot_id": "snap-001",
  "documents": [
    {
      "id": 1,
      "doc_type": "readme",
      "title": "README",
      "scope_id": "",
      "markdown": "# README\n\n> Auto-generated from snapshot...",
      "llm_narrative": ""
    }
  ],
  "total": 5
}
```

### `GET /repos/{id}/snapshots/{sid}/docs`

List generated documents. Optional filter: `?doc_type=module`

### `GET /repos/{id}/snapshots/{sid}/docs/{doc_id}`

Retrieve a specific document by ID.

## Regeneration

Documents are regenerated on each new snapshot. The pipeline
is idempotent -- generating docs again creates new rows
(previous versions are preserved for comparison).

## LLM Integration

The LLM **only narrates** existing facts. It receives the rendered
Markdown and produces a 2-4 paragraph summary. If the LLM fails,
the document is still complete from deterministic content.
