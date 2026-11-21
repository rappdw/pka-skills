# SQLite Modes

Mode selection, the index schema, and the commands that create, fill and query it.

From v1.7 the schema, the indexing pass and the search query are owned by `pka-tools` (vendored at `.pka/bin/pka-tools`). Roles run the commands below; they do not write DDL, `INSERT`s or `MATCH` strings themselves.

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

No database. Claude reads files directly via Repo Map navigation. Practical to ~300–400 indexable files. No `.pka/knowledge.db` created. `pka-tools index` and `pka-tools search` exit 3 with "no index" in this mode; `pka-tools actions`, `pointers`, `timeline` and `obsidian` work without a database.

---

## Mode 2: Index Mode

SQLite database at `.pka/knowledge.db`, created by:

```
.pka/bin/pka-tools db init
```

### Schema (version 1)

The schema version is stored in `PRAGMA user_version`. `pka-tools db schema` prints the tables, columns and row counts of the live database.

```sql
-- Master file index: one row per file under the index roots, any type
CREATE TABLE file_index (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL,          -- workspace-relative, forward slashes: knowledge/AI/foo.md
    folder TEXT NOT NULL,        -- the file's parent folder: knowledge/AI
    filename TEXT NOT NULL,
    file_type TEXT,              -- extension without the dot
    size_bytes INTEGER,
    modified_at TEXT,
    inferred_topic TEXT,         -- frontmatter `topic` when present
    tags TEXT,                   -- frontmatter `tags`, comma-separated
    ocr_text TEXT,               -- text of the OCR sidecar, when there is one
    indexed_at TEXT,
    status TEXT,
    content_hash TEXT            -- SHA-256 of the file's bytes
);
CREATE UNIQUE INDEX file_index_path_uq ON file_index(path);
CREATE INDEX file_index_content_hash ON file_index(content_hash);

-- Full-text search. `is_pointer` is 1 for rows taken from a `## Pointers`
-- table in an _MOC.md (see "Pointer-row ranking"), 0 otherwise.
CREATE VIRTUAL TABLE search_fts USING fts5(
    path, filename, folder, content,
    is_pointer UNINDEXED,
    tokenize = 'porter unicode61'
);

-- Project lifecycle events. The table is created and the dashboard data
-- reads it, but nothing in this release writes a row to it: no pka-tools
-- command and no skill step. Do not insert rows by hand.
CREATE TABLE project_lifecycle (
    id INTEGER PRIMARY KEY,
    project_slug TEXT NOT NULL,
    event TEXT NOT NULL,        -- 'created', 'archiving', 'transitioned', 'restored'
    event_date TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE pka_meta (key TEXT PRIMARY KEY, value TEXT);
```

`path` is unique: indexing the same file twice updates its row. `content_hash` lets later tools find byte-identical files without reading them again.

### Per-folder tables (optional)

Earlier releases let a role add a table per folder, named with the folder slug plus `_index` (`personnel/` → `personnel_index`, `lab-notebook/` → `lab_notebook_index`). Nothing reads them now: do not create one. `pka-tools` neither creates nor alters these tables, and a migration leaves the ones a workspace already has as they are.

### Schema documentation

`.pka/schema.md` describes the tables. The orchestrator writes it at bootstrap and after any schema change, taking the table and column list from the live database rather than from memory:

```
.pka/bin/pka-tools db schema
```

---

## Migrating an existing index

A database created before v1.7 is at schema version 0. Its layout was written by a role following prose, so `pka-tools` inspects it rather than assuming it.

```
.pka/bin/pka-tools db migrate            # prints the plan; changes nothing
.pka/bin/pka-tools db migrate --apply    # backs up, then migrates
```

**Ask the user before `--apply`.** It is a schema change. Show them the plan first.

What `--apply` does, in order:

1. Copies the database to `.pka/db-backups/knowledge-<timestamp>.db` and checks the copy's integrity. (`pka-tools db backup` does this step on its own.)
2. In one transaction: adds any missing `file_index` columns (including `content_hash`); removes duplicate `file_index` rows for the same path, keeping the newest; adds the unique index on `path`; rebuilds `search_fts` with the `is_pointer` column if it lacks it, copying every row across; creates missing universal tables; sets the schema version.
3. Runs SQLite's integrity checks. Any failure rolls the transaction back and leaves the index exactly as it was.

Per-folder tables and any other tables are not touched. To undo a migration, replace `.pka/knowledge.db` with the backup file.

Until the index is migrated, `index` and `search` refuse to run (exit 3) and say so.

---

## Filling and refreshing the index

```
.pka/bin/pka-tools index                 # everything under the index roots
.pka/bin/pka-tools index <path>...       # just these files or folders (after routing)
.pka/bin/pka-tools index --rebuild       # re-read every file in scope
.pka/bin/pka-tools index --prune         # also drop rows anywhere whose file is gone
.pka/bin/pka-tools index --dry-run       # report only
```

**Index roots** are the Repo Map folders with priority Active or Reference. Without a readable Repo Map the root is `knowledge/`. `.pkaignore` applies; dot-folders and symbolic links are skipped. Earshot capture directories contribute their `narrative.md` and nothing else.

A row nested inside another root is folded into it, so a priority is not inherited downwards as an exclusion: with `knowledge/` Active and `knowledge/archive/` Archive, the archive folder is indexed, because it is inside a root. An Archive row keeps a folder out of the index only when no folder above it is a root.

**The archive destination and transitioned projects.** The destination's row is Archive; a project transitioned into it gets its own row, Priority Reference, Status archived, and `index` reads that. `status` then lists `knowledge/archive/orion` (for example) among the index roots. Without that row a transitioned project is in no root: `index` removes its old `projects/` rows and adds nothing. Inside the archive the `.pkaignore` rule `projects/*/*/*` no longer matches, so the whole project is indexed, not just its top-level files.

**What gets indexed**

| File | `file_index` | `search_fts` |
|---|---|---|
| `.md`, `.markdown`, `.txt` | yes | the file's text |
| `_MOC.md` | yes | its text, plus one `is_pointer = 1` row per pointer-table row |
| Any other file with an OCR sidecar (`report.pdf` + `report.pdf.txt`) | yes, with `ocr_text` | the sidecar's text, under the source file's path |
| Any other file without a sidecar | yes (metadata and hash) | nothing new; text a role already stored for it is kept |

The tool does not extract text from PDFs or Office files. The librarian does that (see `pka-librarian/references/ocr-patterns.md`), writes the sidecar, and re-runs `index` on the file. `index` lists documents that have no searchable text, and documents whose bytes changed after their text was extracted.

**Incremental.** A file whose size and modification time are unchanged is skipped. A changed file is re-read; a file that is gone has its rows removed. The report gives N added, N updated, N removed, N unchanged.

**Bootstrap** runs `db init` and then `index`. Reading markdown is fast (a few seconds for thousands of notes), so there is no separate metadata-only pass any more.

---

## Searching

```
.pka/bin/pka-tools search <words>... [--limit N] [--any] [--json]
```

Use this instead of writing a query. It quotes every term, applies the pointer boost, and returns pointer hits with their file lists resolved to paths. If no file contains every term, it retries with any term and says so.

### Pointer-row ranking

Rows from a `## Pointers` table are separate `search_fts` rows: `path` is the MOC's path, `content` is the row's Topic, Entities and Files joined together, `is_pointer = 1`. On retrieval their rank is multiplied by 3. FTS5's `rank` is negative, lower is better, so the multiplication moves pointer rows up.

A pointer hit is a shortcut: read the 2–5 files it lists rather than every body match.

### How the MATCH string is built

This is what `pka-tools search` does for you. It is written down so the behaviour can be checked, not as a recipe: a role runs `.pka/bin/pka-tools search`, and does not write a `MATCH` query of its own. (The dashboard page queries nothing; it reads `dashboard-data.js`.)

FTS5 parses the string as a query language: a hyphen is the NOT/column operator, and `?`, `/`, `[`, `+`, `:` and the words `AND`, `OR`, `NOT`, `NEAR` are syntax. Unquoted, the slugs that pointer rows are made of fail outright:

| Search text | Unquoted result |
|---|---|
| `northwind-partnership-2026` | `no such column: partnership` |
| `what did we decide about pricing?` | `fts5: syntax error near "?"` |
| `AI/ML notes` | `fts5: syntax error near "/"` |

1. Split the search text on whitespace.
2. Drop any term with no letter or digit in it.
3. In each term, double any `"` character (`"` → `""`), then wrap the term in double quotes.
4. Join the terms with a single space (FTS5 treats that as AND).

`northwind-partnership-2026 pricing` becomes `"northwind-partnership-2026" "pricing"`. The tool passes the result as a bound parameter (`MATCH ?`), never by string concatenation into the SQL. The query it runs:

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

FTS finds words, not markup. Do not use it to look for syntax such as `- [ ]` (open checkboxes), `#tag` or `[[wikilink]]`. For open action items use `.pka/bin/pka-tools actions`.

### Why FTS5 not embeddings

The pointer rows are designed for keyword density — they are dense markdown table rows with topic slugs, entity names, and wikilinks side-by-side. FTS5's BM25 scoring naturally ranks them above sparse body matches without any embedding layer. No vector store, no embeddings, no separate database.

---

## Mode 3: Record-Store Mode

Opt-in only. Never selected automatically. Not in initial build scope.

Extends index mode with:
- User-defined structured tables (e.g., contacts CRM, decision log)
- Custom query interfaces via pka-interface
- Import/export between structured tables and markdown files

Post-bootstrap upgrade path — user says "change storage mode to record-store" to enable.
