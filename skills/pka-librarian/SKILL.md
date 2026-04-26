---
name: pka-librarian
description: >
  ALWAYS use this skill when the user wants to process, route, OCR, index, or
  organize documents in their knowledge system. Triggers on: processing an inbox
  or team-inbox, routing dropped files to the right folders, OCR on PDFs or
  scanned documents, re-indexing a knowledge base, setting up a scanner (ScanSnap,
  iPhone), organizing files into a folder structure, inventorying what's in an
  inbox, extracting text from PDFs, or any document ingestion task within a PKA
  or personal knowledge system. Use this skill even when the user just says
  "process my inbox", "what's in the inbox", "route these docs", "re-index",
  "OCR these", "set up my scanner", or drops files and asks what to do with
  them. Handles transcript detection (holds .vtt/.srt files for meeting
  processing instead of routing them). Also runs lint / health checks on the
  knowledge base (orphan files, broken links, stale wiki sources, contradiction
  candidates) — triggered by "run a health check", "lint my knowledge base",
  "what needs attention", or "check for broken links". Works standalone or with
  pka-bootstrap.
user-invocable: true
argument-hint: "[file or command]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# pka-librarian

Ingest, OCR, categorize, and index documents for a Personal Knowledge Assistance system.

## Pre-Flight

1. Load `.pkaignore` if present; apply defaults if not
2. Load `CLAUDE.md` `## Repo Map` if present
3. Check for `.pka/knowledge.db` — determines whether to update SQLite
4. If no Repo Map: read `references/inference-guide.md` and infer routing from destination folder structure
5. **Cache detection predicates** (used by Obsidian and commit-protocol behavior below):
   - `obsidian_present := directory_exists("./knowledge/.obsidian")`
   - `hybrid_monorepo_present := file_exists("./.meta") AND directory_exists("./.git")`
   These are evaluated once per session and used to gate the additive behaviors at the end of routing.

## Transcript Awareness

Before routing anything, scan `team-inbox/` for transcript files.

Transcript detection patterns: `*.vtt`, `*.srt`, files matching `*transcript*`, `GMT*.txt`, `*_recording.txt`, `*recording*.docx`

If transcripts found:
- **Do not auto-route to knowledge/**
- Hold and flag: "I found what looks like meeting transcripts: `<list>`. Process these with `pka-meetings` or route them to a specific location?"
- If user says route: accept the destination and proceed normally
- If user says `pka-meetings`: hand off and exit the librarian flow for those files

This prevents transcripts from being buried in the knowledge base before reconciliation.

## OCR Capability Detection

Check in order before any OCR attempt:

```bash
python3 -c "import pdfplumber" 2>/dev/null && echo "pdfplumber available"
python3 -c "import pypdf" 2>/dev/null && echo "pypdf available"
which tesseract 2>/dev/null && echo "tesseract available"
```

If nothing available:
- Text-layer PDFs: offer to `pip install pdfplumber --break-system-packages`
- Image PDFs / scans: flag as "OCR unavailable — install tesseract (`brew install tesseract`)" — add to report, never silently skip

See `references/ocr-patterns.md` for full detection and fallback strategy.

## Steps

1. **Inventory** — file type, text layer detection, language, date hints
2. **Infer routing** — Repo Map first; flag project slugs in filenames; present proposals before moving. See `references/file-routing-rules.md`.
3. **OCR** — extract text; sidecar `.txt` + SQLite `ocr_text` + `search_fts`; originals never modified
4. **Move and index** — confirm first (except hands-off); update `file_index`, per-folder table, `search_fts`; append to `session-log.md`
5. **Obsidian-aware enhancements** (only when `obsidian_present` and the destination is inside `knowledge/`) — see `references/obsidian-routing.md` for the per-route checklist. Conventions live in `.pka/roles/_obsidian.md`.
6. **Commit per semantic unit** (only when `hybrid_monorepo_present` and the destination is inside a child repo) — see `references/commit-protocol.md` for the trigger and message format. Rules live in `.pka/roles/_git-protocol.md`.
7. **Report** — `owner-inbox/librarian-report-<YYYY-MM-DD>.md` with counts, destinations, OCR status, unsorted items, and (when `obsidian_present`) any malformed-frontmatter files surfaced for user review

Unsorted files → `team-inbox/unsorted/`, never silently discarded.

## Full Content Index Pass

Run on "index my knowledge base" or after a project transition. Reads `.md` content, extracts PDF text, reads OCR sidecars; populates `search_fts.content`. This is what makes full-text search work — bootstrap intentionally defers it.

## Re-index Command

Diff `file_index` by path + modified_at; update changed entries only; report N added/updated/removed.

## Lint / Health Check

**Trigger:** "run a health check", "lint my knowledge base", "what needs attention", "check for broken links".

Runs a non-destructive scan producing `owner-inbox/librarian-lint-<YYYY-MM-DD>.md` with findings across 7 rule categories:

1. Orphan files (team-inbox/unsorted/ older than 14 days)
2. Broken links (markdown links + `[[wikilinks]]` to missing paths)
3. Stale wiki sources (wiki Sources entries pointing at missing files)
4. Empty Repo Map folders
5. Missing back-references (low priority)
6. Contradiction candidates (wikis with many newer uningested mentions)
7. Uncited wiki claims

Lint reports only — never auto-fixes. User acts on the report. See `references/lint-rules.md` for full rule definitions and `references/cross-reference-maintenance.md` for the back-reference model.

**Variants:**
- "quick lint" → rules 1-4 only (fast)
- "lint" / "full lint" → all 7 rules (default)

## Key Constraints

- Never delete from `team-inbox/` without explicit confirmation
- Never auto-route to project workspaces
- Never auto-route transcripts — hold for `pka-meetings`
- OCR stored in sidecars only — originals never modified
- Routing proposals shown before moves (except hands-off mode)
- When `obsidian_present`, never modify a file's existing frontmatter fields — merge only. See `.pka/roles/_obsidian.md`.
- When `obsidian_present`, never read file bodies during the Obsidian bootstrap (mechanical retrofit only). The lazy/per-route behavior may use frontmatter and routing context, but bootstrap uses filename + folder structure exclusively.
- When `hybrid_monorepo_present`, auto-commits land **only in child repos** (`knowledge/`, `projects/*`). The root repo is **never** auto-committed; root-tracked side effects are staged and surfaced for user review.
