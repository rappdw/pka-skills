# SQLite Modes

Mode selection logic and schema generation for PKA's SQLite layer.

---

## Mode Selection

Count noise-filtered indexable files (`.md`, `.pdf`, `.docx`, `.txt`) in **knowledge-domain folders only** — Active or Reference priority, excluding project workspaces (folders containing `CLAUDE.md`).

| Knowledge-domain file count | Mode | Rationale |
|-----------------------------|------|-----------|
| < 300 | Markdown-only | Claude can navigate this directly via Repo Map |
| 300–800 | Index mode | File count warrants structured lookup |
| > 800 | Index mode (strongly recommended) | Full-text search essential at this scale |
| User has CRM / structured query needs | Record-store mode | Opt-in post-bootstrap only |

Present as a recommendation already made, with a one-sentence rationale. User can override with "change storage mode."

---

## Mode 1: Markdown-Only

No database. Claude reads files directly via Repo Map navigation. Practical to ~300–400 indexable files. No `.pka/knowledge.db` created.

---

## Mode 2: Index Mode

SQLite database at `.pka/knowledge.db`. Schema derived from the Repo Map — not predefined. Table names are always folder slugs, never generic category names.

### Universal Tables (always created)

```sql
-- Master file index: every indexed file gets a row
CREATE TABLE file_index (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL,
    folder TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_type TEXT,
    size_bytes INTEGER,
    modified_at TEXT,
    inferred_topic TEXT,
    tags TEXT,
    ocr_text TEXT,
    indexed_at TEXT,
    status TEXT
);

-- Full-text search across all content.
-- The `is_pointer` column is UNINDEXED — it carries the pointer-layer flag
-- (1 if this row was extracted from a `## Pointers` table inside an _MOC.md;
-- 0 otherwise) without participating in FTS tokenization. See "Pointer-row
-- ranking" below.
CREATE VIRTUAL TABLE search_fts USING fts5(
    path, filename, folder, content,
    is_pointer UNINDEXED,
    tokenize = 'porter unicode61'
);

-- Project lifecycle tracking
CREATE TABLE project_lifecycle (
    id INTEGER PRIMARY KEY,
    project_slug TEXT NOT NULL,
    event TEXT NOT NULL,        -- 'created', 'archiving', 'transitioned', 'restored'
    event_date TEXT NOT NULL,
    notes TEXT
);
```

### Per-Folder Tables

Generated from the Repo Map. One table per Active or Reference priority folder. Table name is always `<folder_slug>_index`.

| Inferred content type | Table name example | Generated columns |
|-----------------------|-------------------|-------------------|
| Per-person notes | `personnel_index` | `person_slug TEXT, note_type TEXT, last_modified TEXT, excerpt TEXT` |
| Meeting / strategy notes | `leadership_index` | `topic TEXT, note_date TEXT, note_type TEXT, excerpt TEXT` |
| Research outputs | `research_index` | `topic_slug TEXT, has_pdf INTEGER, has_source_doc INTEGER, excerpt TEXT` |
| Journal / lab notes | `lab_notebook_index` | `entry_date TEXT, excerpt TEXT` |
| Project workspaces | `projects_index` | `project_slug TEXT, has_claude_md INTEGER, last_modified TEXT, excerpt TEXT, status TEXT` |
| Generic / flat | `<folder>_index` | `note_date TEXT, excerpt TEXT` |

### Schema Naming Convention

Table names are always folder slugs — never generic category names:
- `personnel/` → `personnel_index` (not `contacts`)
- `leadership/` → `leadership_index` (not `meetings`)
- `lab-notebook/` → `lab_notebook_index` (hyphen → underscore)

### Schema Documentation

Bootstrap writes `.pka/schema.md` at runtime documenting all created tables, their columns, and which Repo Map folder each table corresponds to. This file is regenerated on any schema change. It is not a skill asset — it's a runtime artifact.

---

## Bootstrap Population

Bootstrap does **metadata-only** population:
- `file_index`: path, folder, filename, file_type, size_bytes, modified_at
- Per-folder tables: populated from filesystem metadata
- `search_fts`: **NOT populated** — content indexing is the librarian's job
- `project_lifecycle`: initial entries for detected projects

Target: under 30 seconds for any repo size. No file content reads at bootstrap.

### Full Content Index Pass

Separate from bootstrap. Run by the librarian on "index my knowledge base" or after a project transition:
1. Read `.md` file content
2. Extract PDF text (via pdfplumber/pypdf)
3. Read OCR sidecar `.txt` files
4. Populate `search_fts.content`

This is what makes full-text search work.

### Re-index (Incremental)

Diff `file_index` by `path + modified_at`. Update only changed entries. Report: N added, N updated, N removed.

---

## Pointer-row ranking (added in v1.6.1)

When a librarian indexes an `_MOC.md` file, rows inside the `## Pointers` table are inserted into `search_fts` as **separate rows** (one FTS row per pointer-table row), distinct from the row carrying the file's body content.

Pointer-table FTS rows:
- `path` is the MOC file path (e.g., `knowledge/AI/_MOC.md`).
- `content` is the concatenation of the row's `Topic`, `Entities`, and `Files` columns (denormalized for keyword density).
- `is_pointer = 1`.

The MOC file's body content is also indexed normally (one additional row with `is_pointer = 0`, `content` = the MOC's narrative paragraphs and headings).

### Retrieval — 3× rank boost

On retrieval, queries against `search_fts` apply a multiplicative rank boost to `is_pointer = 1` rows. SQLite FTS5 uses `rank` such that **lower (more negative) values mean better matches** (BM25 sign convention; values lie in `(-Infinity, 0]`). To rank pointer rows higher, multiply their rank by `3.0` (making the value more negative); body rows stay at `1.0`.

Example query:
```sql
SELECT
  path,
  filename,
  snippet(search_fts, 3, '<b>', '</b>', '...', 32) AS excerpt,
  is_pointer,
  rank * (CASE is_pointer WHEN 1 THEN 3.0 ELSE 1.0 END) AS adjusted_rank
FROM search_fts
WHERE search_fts MATCH ?
ORDER BY adjusted_rank
LIMIT 20;
```

### Why FTS5 not embeddings

The pointer rows are designed for keyword density — they are dense markdown table rows with topic slugs, entity names, and wikilinks side-by-side. FTS5's BM25 scoring naturally ranks them above sparse body matches without any embedding layer. No vector store, no embeddings, no separate database.

### Maintenance contract

The librarian re-indexes pointer rows on:

1. **MOC file change** — re-extract all rows in the `## Pointers` table; replace the old FTS rows for that MOC.
2. **File rename / graduation** — the librarian rewrites Pointers wikilinks in MOCs (see `pka-skills/skills/pka-librarian/references/pointer-layer.md`); a re-index of those MOCs follows.

Pointer-row indexing is part of the same incremental re-index pass as body-content indexing — no separate command.

---

## Mode 3: Record-Store Mode

Opt-in only. Never selected automatically. Not in initial build scope.

Extends index mode with:
- User-defined structured tables (e.g., contacts CRM, decision log)
- Custom query interfaces via pka-interface
- Import/export between structured tables and markdown files

Post-bootstrap upgrade path — user says "change storage mode to record-store" to enable.
