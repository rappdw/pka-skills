#!/usr/bin/env python3
"""upgrade-roles.py — merge v1.6 / v1.6.1 additions into existing .pka/roles/ files.

A workspace bootstrapped with pka-skills v1.5 has these role files:
  .pka/roles/orchestrator.md
  .pka/roles/librarian.md
  .pka/roles/researcher.md

v1.6 adds:
  - Two shared-reference files: .pka/roles/_obsidian.md, .pka/roles/_git-protocol.md
  - New H2 sections in each existing role file (Obsidian coexistence,
    commit/push protocol, bootstrap dispatch, session-end push, etc.)

v1.6.1 adds (additive on top of 1.6.0):
  - A "## Pointer Layer" section in .pka/roles/_obsidian.md (for workspaces
    that already have an _obsidian.md file from a previous upgrade)
  - Three new H2 sections in librarian.md (Pointer-row maintenance, Indexing
    pointer rows, Rename / graduate propagation)

This script applies all additions IN PLACE without overwriting any content
the user has customized. It is:

  - Deterministic (no LLM in the loop for the merge — line-exact behavior)
  - Idempotent (re-running on already-upgraded files produces no further
    changes)
  - Non-destructive (creates a timestamped backup of .pka/roles/ before any
    modification)
  - Surgical (only adds H2 sections that aren't present; never modifies the
    body of existing sections)

What this script INTENTIONALLY does NOT do:

  - It does not modify any *existing* H2 section's body. If your
    Key Competencies bullets are out of date relative to the v1.6 seed,
    that's a manual merge — see the diff at the end of the run.
  - It does not touch the role's frontmatter.
  - It does not touch user-defined H2 sections (anything not in the v1.6
    section list below).

Usage:
    upgrade-roles.py [--workspace <root>] [--dry-run]

Environment:
    WORKSPACE_ROOT  defaults to $(pwd) if --workspace is not given.

Exit codes:
    0  success
    1  workspace precondition failure (no .pka/roles/)
    2  unexpected file shape (e.g., role file lacks the anchor section)
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shutil
import sys
from pathlib import Path

# Insertion anchor: every v1.5 role file has these sections. The new sections
# are inserted BEFORE the first of these that exists, in this priority order.
ANCHOR_SECTIONS = ("## Output Conventions", "## Invocation")

# ---------------------------------------------------------------------------
# v1.6 SECTION ADDITIONS
# ---------------------------------------------------------------------------
# Each role gets a list of (heading, content) tuples to add if not already
# present. Heading is the H2 line, used as the absent/present check. Content
# is the body that follows the heading (excluding the heading itself).

ORCHESTRATOR_SECTIONS = [
    (
        "## Session-start checks (cached for the session)",
        """\
In addition to the existing session-start protocol, evaluate two predicates:

```
obsidian_present       := directory_exists("./knowledge/.obsidian")
hybrid_monorepo_present := file_exists("./.meta") AND directory_exists("./.git")
```

If `obsidian_present` is true, surface one greeting line:

> "Obsidian vault detected — skills running in Obsidian-coexistence mode."

Conventions for Obsidian-mode behavior live in `.pka/roles/_obsidian.md`. Do not duplicate them here; consult that file when an Obsidian-specific decision is needed.

Conventions for the commit/push protocol live in `.pka/roles/_git-protocol.md`. Apply only when `hybrid_monorepo_present`.
""",
    ),
    (
        "## File references in responses",
        """\
When `obsidian_present` is true and a referenced file is **inside** `knowledge/`, prefer `[[wikilink]]` syntax (clickable in Obsidian, still readable as plain text otherwise). For files **outside** `knowledge/` (projects/, root, inboxes) use the standard `path:line` format.

When `obsidian_present` is false, use `path:line` everywhere as today.
""",
    ),
    (
        "## Bootstrap dispatch",
        """\
If the user invokes a "bootstrap" request — natural phrasings include "let's bootstrap the vault", "bootstrap obsidian", "initialize the hybrid repo", "bootstrap git", "bootstrap everything", "bootstrap all" — resolve the target:

| User phrasing contains                                       | Target     |
|--------------------------------------------------------------|------------|
| "obsidian", "vault", "moc", "frontmatter"                    | `obsidian` |
| "git", "hybrid repo", "monorepo", "meta", "lfs"              | `git`      |
| "all", "everything", or both Obsidian and git words appear   | `all`      |
| "upgrade", "upgrade roles", "update my pka"                  | `upgrade`  |

If the target is still ambiguous after this, ask:

> "Which bootstrap should I run? Options: `obsidian` (vault retrofit), `git` (hybrid monorepo), `all` (both), `upgrade` (refresh role files in an already-bootstrapped workspace)."

Then hand off to the relevant procedure in `pka-bootstrap`. All bootstraps are idempotent and user-triggered. Never run on detection alone.
""",
    ),
    (
        "## Session-end protocol (extended)",
        """\
In addition to the existing session log entry:

1. If `hybrid_monorepo_present`, run a consolidated push across child repos with unpushed commits. Implementation: `meta git push` if `meta` is on PATH; otherwise iterate `.meta` entries and run `git push` in each child directory (helper: `.pka/push-all.sh`).
2. If any child repo's push fails (auth, network, conflict, LFS upload disconnect): record the failure in the session summary with the repo path and error. Do not retry destructively. Session close still proceeds.
3. **Surface, do not commit, root-repo changes.** If `git status` in the root shows staged or unstaged changes, list them in the session summary and tell the user they're awaiting human review. Never auto-commit root.
4. Skipped pushes (no origin configured, placeholder `.meta` URL, nothing to push) are reported as **skipped**, not failures.
""",
    ),
    (
        "## Mid-session push handling",
        """\
If the user says "push", "push now", "push the changes", or similar, run the same consolidated push immediately and report a summary. Session continues.
""",
    ),
]

LIBRARIAN_SECTIONS = [
    (
        "## Obsidian coexistence (gated on `obsidian_present`)",
        """\
When routing a file **into `knowledge/`** with `obsidian_present` true:

1. **Filename hygiene** (this step applies regardless of Obsidian state):
   - Replace `:` and `/` in incoming filenames with `-` or ` `.
   - Preserve spaces where they exist — Obsidian handles them and existing content uses them.
   - Do not rename existing files unless explicitly asked.

2. **Frontmatter** — if the file matches a known type (meeting, 1on1, brief, daily, person), ensure frontmatter is present with the schema fields from `.pka/roles/_obsidian.md`. Use filename-derived values (date, person from `personnel/<name>/`, domain tags from folder). Leave body-derived fields (attendees, topic beyond filename slug, related notes) **empty** when confidence is low — empty is better than wrong. If existing frontmatter is malformed, skip augmentation and flag the file in the routing report.

3. **MOC update** — append a bullet linking to the routed file in the destination domain's `_MOC.md`. If the MOC is absent, create a stub matching the structure in `.pka/roles/_obsidian.md`. Never reorder or remove existing MOC entries.

4. **Person backlinks** — if the routed content's filename or front-of-content references a person whose `personnel/<name>/index.md` exists, add a bullet under "Mentioned in" or "Related meetings" on that person's index page. **Only when confidence is high.** Err on the side of NOT linking when ambiguous — rogue backlinks are worse than missing ones.

5. **Wikilinks vs plain links** — cross-references inside the vault use `[[wikilinks]]`; references to files outside the vault use plain markdown. See `.pka/roles/_obsidian.md` for the full rule.

When `obsidian_present` is false: current behavior only — no frontmatter, no MOC update, no backlinks.

Full conventions in `.pka/roles/_obsidian.md`. Consult that file when an Obsidian-specific decision is needed; do not duplicate the rules here.
""",
    ),
    (
        "## Commit/push protocol (gated on `hybrid_monorepo_present`)",
        """\
When the orchestrator's session-start detection reports `hybrid_monorepo_present` true:

- After completing a routing operation that lands in `knowledge/` or any `projects/<name>/`, auto-commit that semantic unit in **the destination child repo** with message:
  ```
  Librarian: Route <filename> to <destination-folder>/

  Co-Authored-By: Claude <noreply@anthropic.com>
  ```
- One commit per routing unit. Side-effects of the route (MOC update, frontmatter, person-index backlink) belong to the same semantic unit and ride along in the same commit.
- Never auto-commit in the **root repo**. If routing produces root-tracked side effects (e.g., updates to `CLAUDE.md`'s Repo Map when a new domain folder is added), stage those changes and surface them in the routing report for user review.
- A bulk re-routing pass should produce **one commit per logical unit**, not one giant commit — this preserves reviewability and enables targeted reverts.

Full protocol in `.pka/roles/_git-protocol.md`.

When `hybrid_monorepo_present` is false: no auto-commit; current behavior.
""",
    ),
]

RESEARCHER_SECTIONS = [
    (
        "## Obsidian coexistence (gated on `obsidian_present`)",
        """\
When the orchestrator's session-start detection reports `obsidian_present` true, briefs that land **inside the vault** (`knowledge/`) carry frontmatter per the `brief` schema in `.pka/roles/_obsidian.md`:

```yaml
---
type: brief
date: YYYY-MM-DD
related: ["[[...]]", "[[...]]"]
tags: [research, <domain-tag>]
---
```

Rules:
- `related` is populated with `[[wikilinks]]` to prior briefs on adjacent topics encountered during research. If none found with high confidence, leave as `related: []`.
- `tags` always includes `research` plus a domain tag matching the destination folder (e.g., `ai`, `leadership`).
- For briefs landing **outside** `knowledge/` (e.g., `owner-inbox/`), no frontmatter is added — current behavior.
- Body cross-references inside the vault use `[[wikilinks]]`; outside-vault references stay as plain markdown.

When `obsidian_present` is false, briefs are produced without frontmatter — current behavior.

Full conventions (frontmatter rules, wikilink rules, malformed-frontmatter handling) are in `.pka/roles/_obsidian.md`. Consult that file when an Obsidian-specific decision is needed; do not duplicate the rules here.
""",
    ),
    (
        "## Commit/push protocol (gated on `hybrid_monorepo_present`)",
        """\
When the orchestrator's session-start detection reports `hybrid_monorepo_present` true:

- After saving a brief inside a child repo (`knowledge/` or any `projects/<name>/`), auto-commit that semantic unit in **the destination child repo** with message:
  ```
  Researcher: <short description of brief>

  Co-Authored-By: Claude <noreply@anthropic.com>
  ```
- One commit per brief. If a brief includes side-effect updates to the same vault (MOC entries, related-list updates), include them in the same commit.
- Never auto-commit in the **root repo**. If saving a brief touches root files (rare — typically only when adding a new domain to the Repo Map), stage those changes and surface them in the session summary for user review.
- Briefs saved to `owner-inbox/` (root-tracked) are not committed by the role; they're delivered for review and the user decides when (or whether) to commit.

Full protocol in `.pka/roles/_git-protocol.md`.

When `hybrid_monorepo_present` is false: no auto-commit; current behavior.
""",
    ),
]

# --- v1.6.1 additions ---
# Three new H2 sections on the librarian role file. Same anchor (insert
# before `## Output Conventions`).

LIBRARIAN_SECTIONS_V161 = [
    (
        "## Pointer-row maintenance (gated only on routing into a domain — NOT on `obsidian_present`)",
        """\
After every route into `knowledge/<domain>/` or `projects/<name>/`, append a step to maintain the destination MOC's `## Pointers` table:

1. **Identify the cluster** using Jaccard similarity (≥ 0.5) between the file's frontmatter tokens (`type`, `topic`, `tags`, `attendees`/`person`/`related`) plus any routing-context directive, and the existing topic-slug tokens in the MOC's Pointers table. If no row scores above threshold, coin a new slug from the file's primary `topic` field, first tag, or `type` (in that priority order).
2. **Update the row.** Existing cluster: append the new file's wikilink to the Files column; merge new entities into the Entities column (deduped, sorted alphabetically). New cluster: append a new row below existing rows.
3. **Cross-MOC duplication.** If the file's tags include multiple top-level domain tags (e.g., `[ai, leadership]`), duplicate the pointer row to each corresponding MOC.
4. **Append-only.** Existing rows are extended, never deleted, reordered, or merged. User edits to row content are preserved verbatim across librarian routes.
5. **Soft size cap.** If a row's Files column reaches 8 entries, flag the row in the routing summary for human review rather than auto-splitting.
6. **Idempotency.** Re-routing the same file produces no change (the wikilink and entities are already present).

This step runs **regardless of `obsidian_present`** — the retrieval value comes from FTS, not from rendering. Wikilinks render literally outside Obsidian; that's fine.

Full algorithm in `.pka/roles/_obsidian.md` (Pointer Layer section) and `pka-skills/skills/pka-librarian/references/pointer-layer.md`.
""",
    ),
    (
        "## Indexing pointer rows",
        """\
When ingesting an `_MOC.md` file into `search_fts`, detect rows in the `## Pointers` table and tag them with `is_pointer = 1`. On retrieval, multiply the BM25 rank of `is_pointer = 1` rows by `3.0` (FTS5 BM25 returns negative values where more negative = better match; the `3.0` multiplier makes pointer matches more negative, ranking them above equivalent body matches). See `pka-skills/skills/pka-bootstrap/references/sqlite-modes.md` for the schema change and retrieval contract.
""",
    ),
    (
        "## Rename / graduate propagation",
        """\
When a file is renamed or moved by the librarian, every Pointers-row wikilink to its old path is updated to the new path across **all** `_MOC.md` files in the vault. When a project is graduated from `projects/<name>/` into `knowledge/<subdir>/<name>/`, `graduate.sh` rewrites Pointers wikilinks for every file in that project. Both operations are idempotent and append-only at the row level.
""",
    ),
]

ROLE_SECTIONS = {
    "orchestrator": ORCHESTRATOR_SECTIONS,
    "librarian": LIBRARIAN_SECTIONS + LIBRARIAN_SECTIONS_V161,
    "researcher": RESEARCHER_SECTIONS,
}

# Shared-reference section additions (for files that already exist in
# .pka/roles/ from a v1.6.0 upgrade and need the v1.6.1 sections merged in).
# Anchor: insert BEFORE the first one of these existing sections.
SHARED_REF_ANCHORS = ("## Tag conventions", "## Filename conventions", "## Error handling")

OBSIDIAN_SECTIONS_V161 = [
    (
        "## Pointer Layer (added in v1.6.1)",
        """\
A small set of curated, dense, machine-readable rows inside each `_MOC.md` — one row per concept cluster — that the librarian maintains as files are routed. The pointer layer is **not Obsidian-specific** (it works in plain markdown too), but it lives in the same files as the rest of the MOC convention so it's documented here.

### Why

At ~1,500+ files, body-level FTS retrieval signal-to-noise drops. Pointer rows give roles a fast pre-FTS targeting layer: hit a pointer row first (high keyword density makes it rank above body matches), then expand to the small list of files the row points at. Converts "1,500-file haystack" queries into "30-cluster summary, then 3–5 targeted file reads". No vector store, no embeddings, no separate database — just markdown table rows that FTS naturally ranks highly.

### File location

A new section appended below the existing `## Subdomains` and `## Files` sections in each `_MOC.md`:

```markdown
# AI

## Subdomains
- [[AI/azure/_MOC|Azure]]

## Files
- [[AI/some-brief]]

## Pointers

Compact retrieval rows maintained by the librarian. Format: one row per concept cluster. FTS-indexed for fast lookup before expanding to file bodies.

| Topic | Entities | Files |
|---|---|---|
| anthropic-partnership-2026 | sam-werboff, jordan-josloff, tom-turvey | [[anthropic/2026-04-23-gcn-partnership-meeting]], [[anthropic/anthropic_partnership_proposal]] |
| ai-adoption-research | satya-nadella, sundar-pichai | [[AI/ai-adoption-tier-productivity-gap-research]], [[AI/companies/darktrace-email-security-research]] |
```

### Row schema

Three columns. All values are plain text; no nested structures; no YAML.

- **Topic** — hyphenated lowercase slug. Stable identifier for the concept cluster. Date-suffixed when event-bound (`anthropic-partnership-2026`); undated for ongoing initiatives (`ai-adoption-research`).
- **Entities** — comma-separated lowercase hyphenated slugs (people, products, organizations, dates). No `[[wikilinks]]` here — entities are denormalized for FTS keyword density.
- **Files** — comma-separated `[[wikilinks]]` to constituent files. Use full relative paths from the vault root (`[[anthropic/2026-04-23-gcn-partnership-meeting]]`) to match the wikilink convention above.

**Granularity rule:** one row per concept cluster, not one row per file. A file may appear in multiple rows; that is correct. Row count per MOC should grow logarithmically with file count, not linearly — if a domain MOC has more pointer rows than files, the granularity is wrong.

### Librarian behavior (gated only on routing into a domain — NOT on `obsidian_present`)

When the librarian routes a file into a domain, after the file is moved and other Obsidian-mode side-effects are applied, it runs the pointer-maintenance step:

1. **Identify the cluster.** Use the file's frontmatter (`type`, `topic`, `tags`, `attendees`/`person`/`related`) plus any routing-context directive. Pick an existing topic slug from the destination MOC's Pointers table by Jaccard similarity ≥ 0.5 against the candidate token set; if no row matches, coin a new slug from the file's primary topic / first tag / type.
2. **Update the row.** If a cluster matches, append the new file's wikilink to the Files column and merge any new entities from the file's frontmatter into the Entities column (deduped, sorted alphabetically). If no cluster matches, append a new row below existing rows.
3. **Cross-MOC duplication.** If the file's tags include multiple top-level domain tags (e.g., `[ai, leadership]`), duplicate the pointer row to each corresponding MOC. The same row may appear in multiple `_MOC.md` files — that is correct and intentional.
4. **Append-only.** Existing rows are extended, never deleted, reordered, or merged. User edits to row content are preserved verbatim across librarian routes.
5. **Soft size cap.** If a row's Files column reaches 8 entries, the librarian flags the row in the routing summary for human review rather than auto-splitting.
6. **Ambiguous cluster?** Default to the conservative read: append to the most-specific existing topic OR create a new row. Do not silently merge clusters that look similar but might not be.

The full algorithm lives in `pka-skills/skills/pka-librarian/references/pointer-layer.md`.

### Retrieval behavior

When a role needs to answer a question that requires reading existing knowledge:

1. **Query the FTS index** as today, but boost rows from `_MOC.md` Pointers tables ~3× over body-level matches (rows tagged `is_pointer = 1` in the index — see `skills/pka-bootstrap/references/sqlite-modes.md`).
2. **For each high-ranked pointer row hit**, parse the Files column → list of file paths.
3. **Expand to file bodies** by reading those files (typically 2–5 per cluster) instead of grepping all 1,500.
4. **Fall back to body-level FTS** if no pointer row matches above the confidence threshold. Pointer rows are a fast path, not the only path.

### Behavior without Obsidian

The pointer layer works regardless of `obsidian_present`:

- Without Obsidian: pointer-row wikilinks render as literal `[[path]]` text in plain-markdown viewers. The FTS index still parses them, the librarian still maintains them, retrieval still benefits — just less navigable for the human reader.
- With Obsidian: the wikilinks become clickable navigation; the Pointers section becomes a usable at-a-glance map of the domain.

Roles do **not** skip pointer-layer maintenance based on `obsidian_present` — the retrieval value is independent of the rendering layer.

### Invariants

1. **Rows are append-only at the row level.** Existing rows are extended (new files / new entities) but never deleted, reordered, or merged by the librarian.
2. **Files column entries are wikilinks to actual files** — broken links inside Pointers tables are bugs, surfaced by the lint health check (rule 2: broken links).
3. **A renamed/moved file triggers pointer-row updates** in every MOC where the file is referenced.
4. **A graduated project's files do not lose their pointer-row entries** — `graduate.sh` rewrites the wikilinks to the new `knowledge/` paths.
5. **Pointer rows are never read by an LLM at full-document scale** — they are FTS-targeted retrieval primitives. If a row is being rendered to a user verbatim, the data has been pulled into the wrong layer.

### What this is NOT

- Not a vector store. No embeddings.
- Not a replacement for full-text search. It is a faster path that sits in front of FTS.
- Not a separate file. It is a section inside existing `_MOC.md` files, never a `_pointers.md` or similar.
- Not Obsidian-dependent. Plain-markdown workspaces benefit from FTS-side gains; Obsidian only improves the rendering.
""",
    ),
]

SHARED_REF_SECTIONS = {
    "_obsidian.md": OBSIDIAN_SECTIONS_V161,
    # _git-protocol.md has no v1.6.1 additions
}

# ---------------------------------------------------------------------------
# SHARED-REFERENCE SEEDS (verbatim from references/obsidian-conventions.md
# and references/git-protocol.md fenced blocks)
# ---------------------------------------------------------------------------

OBSIDIAN_SEED = """\
---
title: Obsidian Coexistence Conventions
type: shared-reference
status: active when knowledge/.obsidian/ is present
---

# Obsidian Coexistence Conventions

This file is **shared reference** for pka roles (orchestrator, librarian, researcher). It is not a role itself. Roles link here instead of duplicating these rules.

All conventions on this page apply **only when Obsidian is detected**. When it isn't, roles continue their pre-Obsidian behavior unchanged.

## Detection

Claude is invoked at the pka workspace root (same directory as `CLAUDE.md`). All paths in this file are relative to that root.

```
obsidian_present := directory_exists("./knowledge/.obsidian")
```

Evaluate once at session start, cache for the session. Vault is fixed at `knowledge/` by convention.

If the predicate is true, surface it in the session-start greeting: "Obsidian vault detected — skills running in Obsidian-coexistence mode."

## Frontmatter schemas

YAML frontmatter, fenced by `---` on the first lines of the file. Unknown fields are safe to leave in place — Obsidian ignores them.

### Daily note
Location: `lab-notebook/YYYY-MM-DD.md`
```yaml
---
date: YYYY-MM-DD
tags: [daily]
---
```

### Meeting note
Location: `leadership/`, `TechCouncil/`, or any domain-specific meeting folder
```yaml
---
type: meeting
date: YYYY-MM-DD
topic: <short slug or phrase>
attendees: ["[[firstname]]", "[[firstname]]"]
tags: [meeting, <domain-tag>]
---
```

### 1-on-1 note
Location: `personnel/<person>/YYYY-MM-DD-1on1.md`
```yaml
---
type: 1on1
date: YYYY-MM-DD
person: "[[personnel/<person>/index]]"
tags: [1on1]
---
```

### Research brief
Location: under a topic folder, typically in `AI/` or `leadership/`
```yaml
---
type: brief
date: YYYY-MM-DD
related: ["[[...]]", "[[...]]"]
tags: [research, <domain-tag>]
---
```

### Person index
Location: `personnel/<person>/index.md`
```yaml
---
type: person
name: <full name>
role: <role/title>
org: <org>
tags: [person]
---
```

## Rules for writing frontmatter

1. **Never overwrite** existing fields the user has filled in. When adding to existing frontmatter, merge: add missing schema fields, leave existing fields alone.

2. **Empty is better than wrong.** If you can't confidently infer a field's value, leave it empty (`""` or `[]`) rather than guessing.

3. **Filename-derived values are safe.** Dates, person names (from `personnel/<name>/`), and folder-based domain tags are derivable mechanically with no inference.

4. **Body-derived values require care.** Attendees, topics (beyond filename slug), related notes — these require reading content and inferring. Only emit when confidence is high. When unsure, empty.

5. **Malformed existing frontmatter**: do not attempt to repair. Skip the file and surface it in a warning to the user.

## Wikilink syntax

When `obsidian_present` is true:

- Cross-references **within the vault** (`knowledge/`) → `[[wikilinks]]`.
- References to files **outside the vault** (`projects/`, root, inboxes) → plain markdown `[text](relative/path)`.
- Display-text form: `[[target|display]]` when the target path shouldn't be what's shown.
- Prefer full relative paths (`[[personnel/alec/index]]`) over bare names (`[[alec]]`) to avoid Obsidian ambiguity resolution.

When `obsidian_present` is false: plain markdown links everywhere. Do not emit `[[wikilinks]]` — they render as literal text in non-Obsidian viewers.

## MOC (Map of Content) files

Filename: `_MOC.md` — underscore prefix sorts to the top of a folder listing.

Locations (one per top-level knowledge domain):
- `knowledge/_MOC.md`
- `knowledge/AI/_MOC.md`
- `knowledge/personnel/_MOC.md`
- `knowledge/leadership/_MOC.md`
- `knowledge/dan/_MOC.md`
- `knowledge/TechCouncil/_MOC.md`
- `knowledge/lab-notebook/_MOC.md`
- (others as new domains emerge)

### Structure

Minimum-viable MOC is a bulleted list of wikilinks:

```markdown
# AI

## Subdomains
- [[AI/azure/_MOC|Azure]]
- [[AI/ThomaBravo/_MOC|Thoma Bravo]]
- [[AI/companies/_MOC|Companies]]

## Files
- [[AI/ai-adoption-tier-productivity-gap-research]]
- [[AI/some-other-brief]]
```

Thematic grouping (e.g., "Strategy docs" vs "Research briefs" vs "Vendor notes") is user work — roles do not attempt it automatically. Roles only append to an existing section or to an "Unsorted" catch-all at the bottom.

### Update policy

- When librarian routes a new file into a domain, append a bullet linking to the file in the relevant MOC. Create the MOC if absent (with a stub matching the structure above).
- Never remove or reorder existing entries.
- MOCs are navigation aids, not authoritative indexes — if the MOC diverges from the actual folder contents, the folder contents win.

## Tag conventions

Tags are lowercase, hyphenated: `ai-strategy`, not `AIStrategy` or `AI_Strategy`.

### Established tags

- `daily` — on daily notes
- `meeting` — on meeting notes
- `1on1` — on 1:1 notes
- `brief` — on research briefs
- `person` — on person index pages
- `research` — on research content
- `project` — on project-related content (if any ends up in vault)

### Domain tags

Every file in the vault should carry at least one tag matching its top-level folder. Examples (not exhaustive — match the actual top-level folders in `knowledge/`):
- `ai`, `leadership`, `personnel`, `techcouncil`, `lab-notebook`, `dev-process`, `reference`, `data`, `archived`

### Topic tags

Free-form, added as useful: `strategy`, `mcp`, `harvard-lunch-learn`, etc.

Tag hygiene is not strict. Duplicates, case drift, and near-synonyms happen over time — this is a vault-wide cleanup task for the user, not a per-edit concern.

## Filename conventions

Apply regardless of Obsidian state (existing good practice):

- Dated content: `YYYY-MM-DD-<topic>.md` for single-event files; `YYYY-MM-DD.md` for daily notes.
- Spaces allowed in filenames. Obsidian handles them; existing content uses them.
- Avoid: `:`, `/`, `\\`, `?`, `*`, `|`, `<`, `>`, `"` (Windows incompatibility, shell pain points).
- Prefer hyphens over underscores in new filenames; follow sibling convention in the target folder.
- Do not rename existing files unless explicitly asked. Stable paths matter more than naming consistency.

## Error handling

When an Obsidian-specific operation fails, the role must **not** block the primary task. Degradation rules:

- If the MOC can't be written (permissions, file lock, etc.), log a warning, complete the primary routing, surface the warning in the summary.
- If existing frontmatter is malformed, skip frontmatter augmentation for that file. Do not attempt to repair. Flag in the summary.
- If a wikilink target can't be resolved with confidence, fall back to a plain markdown link to the best-guess path.
- If detection is ambiguous (`.obsidian/` exists but is empty), treat as `obsidian_present = true`. An empty config is a valid state.

## Bootstrap

The mechanical retrofit described in the addendum runs only when the user explicitly invokes it (e.g., "bootstrap obsidian" to orchestrator). It is never triggered by detection alone. Must be idempotent and safe to re-run.

When running, the bootstrap obeys all the conventions above — it's the same rules, applied in bulk to existing content, using only filename and folder structure as inputs. It never reads file bodies.

## Invariants

Things that MUST hold across all coexistence behavior:

1. A user with no Obsidian vault sees identical output to pre-addendum behavior.
2. A user with an Obsidian vault but who has never run bootstrap sees non-destructive, additive behavior on files roles touch during normal work.
3. Running bootstrap twice produces the same final state as running it once.
4. No role modifies files outside `knowledge/` based on Obsidian state.
5. No role modifies files the user has explicitly marked read-only.
6. Frontmatter added to a file is always YAML-valid; if the role can't produce valid YAML, it emits nothing rather than broken frontmatter.

## When this file is out of date

This file captures the contract between pka-skills roles and the Obsidian vault. If a role behavior diverges from what's documented here, either:
- The behavior is wrong, or
- This file is wrong and should be updated.

Roles should treat this file as authoritative. When in doubt during implementation, follow this file; raise the divergence with the user.
"""

GIT_PROTOCOL_SEED = """\
---
title: Commit/Push Protocol
type: shared-reference
status: active when workspace is a hybrid monorepo (root .git + .meta + child repos)
---

# Commit/Push Protocol

Shared reference for pka roles. Roles link here instead of duplicating commit-and-push rules.

This protocol activates only when the workspace is a **hybrid monorepo**: a root `.git`, a `.meta` manifest at the root, and one or more child repos (`knowledge/`, `projects/<name>/`) each with their own `.git`. In a single-repo or no-repo workspace, roles continue their pre-protocol behavior — no auto-commit, no session-end push.

## Detection

```
hybrid_monorepo_present := file_exists("./.meta") AND directory_exists("./.git")
```

Evaluate once at session start, cache for the session.

## Commit triggers

### Child repos (`knowledge/`, `projects/*`)

**Auto-commit per semantic unit** after a role completes meaningful work.

A "unit" is a coherent, reviewable change — not every file-write, but one commit per *thing accomplished*. The role decides the unit boundary.

Examples:
- Librarian routing a file into `knowledge/` → one commit after the route completes (including any MOC/frontmatter/backlink side-effects).
- Researcher finalizing a brief → one commit when the brief is saved.
- Obsidian bootstrap → one commit in `knowledge/` summarizing the batch.
- Graduation → see "Graduation commit sequence" below.

### Root repo

**No auto-commit. Ever.**

Root repo changes (`CLAUDE.md` updates, `.meta` changes, new/updated `.pka/` scripts or templates, git-bootstrap scaffolding) accumulate in the working tree. The role:

1. Stages obviously-related changes with `git add` (best-effort grouping).
2. Lists them in the session summary.
3. Hands off to the user for review and manual commit.

Rationale: the root is the system's own configuration. Its blast radius is larger than any single child repo. Bad auto-commits there are harder to notice and unwind. Human review is the gate.

## Commit message structure

Commits carry a role prefix and a short description, followed by a Claude trailer:

```
<Role>: <short description>

<optional body>

Co-Authored-By: Claude <noreply@anthropic.com>
```

Examples:
- `Librarian: Route 2026-04-22-slt-meeting.md to leadership/`
- `Researcher: Add brief on AI adoption tier productivity gap`
- `Bootstrap (obsidian): 7 MOC stubs, 12 person indexes, 41 frontmatter additions`
- `Bootstrap (git): Initial hybrid monorepo setup`
- `Graduate: widget → knowledge/reference/`

The trailer is mandatory. Do not omit. The exact trailer string is `Co-Authored-By: Claude <noreply@anthropic.com>`.

## Push triggers

### Session end (auto)

At session end, the orchestrator runs a consolidated push across all child repos with unpushed commits. Implementation: `meta git push` if `meta` is on PATH, else iterate `.meta` entries and run `git push` in each child repo directory.

The session-end push is part of the session-end protocol — it runs after the final session-log entry is written.

### Mid-session on user request

If the user says "push", "push now", "push the changes", or similar natural phrasing, push immediately across all child repos with unpushed commits and report a summary. Session continues.

### Root repo push

The root is pushed only after the user has committed it. The auto-push uses `meta git push` (or equivalent), which operates on registered child repos; if the root is also tracked in the manifest, it pushes only committed state — same gate as commit.

If the root has uncommitted changes at session end, surface them in the summary. Do not commit; do not push.

## Push behavior — never silent failures

Any push failure (auth error, conflict, network unreachable, LFS upload disconnect) surfaces explicitly in the session summary with the failing repo and the error message. Do not hide. Do not retry destructively (no `--force`, no rebase).

If a child repo has no remote configured (placeholder `.meta` URL or empty `origin`), report it as a **skipped** push, not a failure.

## Graduation commit sequence

When a project is graduated from `projects/<name>/` to `knowledge/<subdir>/<name>/` via `graduate.sh`:

1. In `knowledge/` (child repo): auto-commit the new content with message `Graduate: <name> → knowledge/<subdir>/`.
2. In root repo: `.meta` update removing `projects/<name>` is **staged, not committed**. Flagged in the session summary for user review.
3. The old project repo on the remote (if any): the graduation script prints instructions for archiving (e.g., a Gitea/GitHub API call). The role does not call remote APIs.

## Failure behavior

- **Commit failure** (merge conflict, pre-commit hook failure, unexpected working-tree state): surface to the user, pause further automatic commits in that repo, continue with other work. Do not force, amend, or retry destructively.
- **Push failure at session end**: record in session log and summary; continue (don't block session close). User can re-invoke push next session.
- **LFS-specific failures** (missing `git-lfs` binary, oversized object, remote-side disconnect mid-upload): surface with a remediation hint (e.g., install lfs, retry push — LFS uploads are resumable, prior objects are already on the server).

## Interaction with the Obsidian bootstrap

The Obsidian bootstrap produces changes inside `knowledge/` only. Under this protocol it is a single child-repo commit (`Bootstrap (obsidian): ...`), auto-committed per the child-repo rule above. The user reviews the diff in `knowledge/` before (or after) the session-end push.

## Interaction with the git bootstrap

The git bootstrap is a special case:

- Initial commits in `knowledge/` and each `projects/*` are mechanical and safe to auto-commit (`Bootstrap (git): Initial hybrid monorepo setup`).
- Root-repo scaffolding (root `.gitignore`, `.meta`, `.pka/` templates and scripts) is **staged but not committed**. The user reviews and commits.
- No remotes are set; no push is attempted.

## Invariants

Things that MUST hold:

1. **Root never auto-commits.** Every code path that touches root files must stop at "staged, ready for review" and surface the changes in the session summary.
2. **Auto-commits in child repos are idempotent at the unit level.** A repeated semantic action (e.g., re-routing the same file with no change) does not produce an empty or duplicate commit.
3. **Trailer is always `Co-Authored-By: Claude <noreply@anthropic.com>`** (verbatim) on auto-commits.
4. **Session-end push is non-blocking.** Failures surface; session close still proceeds.
5. **No remote operations during git bootstrap.** No `git push`, no `curl`, no origin URLs to user-specific orgs.
"""


# ---------------------------------------------------------------------------
# Merge engine
# ---------------------------------------------------------------------------

def section_present(text: str, heading: str) -> bool:
    """True if the markdown text contains an H2 with this exact heading text."""
    needle = heading.strip()
    for line in text.splitlines():
        if line.strip() == needle:
            return True
    return False


def find_anchor_offset(text: str, anchors: tuple[str, ...] = ANCHOR_SECTIONS) -> int | None:
    """Return the character offset where new sections should be inserted.

    Searches for the first occurrence of any anchor heading. Returns None if
    no anchor is found (caller will append at end of file).
    """
    lines = text.splitlines(keepends=True)
    offset = 0
    for line in lines:
        stripped = line.rstrip("\n").rstrip()
        if stripped in anchors:
            return offset
        offset += len(line)
    return None


def merge_sections(
    text: str,
    sections: list[tuple[str, str]],
    anchors: tuple[str, ...] = ANCHOR_SECTIONS,
) -> tuple[str, list[str]]:
    """Insert any missing sections into `text` before the first anchor.
    Returns the updated text and the list of headings that were added.

    Identical merge logic for both role files and shared-reference files;
    only the anchor list differs.
    """
    added: list[str] = []
    insertion = ""
    for heading, body in sections:
        if section_present(text, heading):
            continue
        insertion += f"\n{heading}\n\n{body.rstrip()}\n"
        added.append(heading)

    if not insertion:
        return text, []

    anchor = find_anchor_offset(text, anchors)
    if anchor is None:
        new_text = text.rstrip() + "\n" + insertion + "\n"
    else:
        new_text = text[:anchor] + insertion.lstrip("\n") + "\n" + text[anchor:]
    return new_text, added


def merge_role(text: str, sections: list[tuple[str, str]]) -> tuple[str, list[str]]:
    """Backwards-compatible wrapper. Use merge_sections directly for new code."""
    return merge_sections(text, sections, ANCHOR_SECTIONS)


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------

def upgrade_workspace(workspace: Path, dry_run: bool = False) -> dict:
    pka_dir = workspace / ".pka"
    roles_dir = pka_dir / "roles"
    if not roles_dir.is_dir():
        raise SystemExit(
            f"ERROR: {roles_dir} not found. This workspace doesn't appear to be "
            f"PKA-bootstrapped; run base bootstrap first."
        )

    summary: dict = {
        "backup": None,
        "shared_seeded": [],
        "shared_already_present": [],
        "shared_sections_added": {},
        "shared_sections_already_present": {},
        "role_sections_added": {},
        "role_sections_already_present": {},
        "roles_unchanged": [],
        "dry_run": dry_run,
    }

    # 1. Backup .pka/roles/ to .pka/upgrade-backups/<timestamp>/roles/
    if not dry_run:
        ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_root = pka_dir / "upgrade-backups" / ts
        backup_root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(roles_dir, backup_root / "roles")
        summary["backup"] = str(backup_root / "roles")

    # 2. Seed shared references if absent
    obsidian_target = roles_dir / "_obsidian.md"
    git_target = roles_dir / "_git-protocol.md"
    if obsidian_target.exists():
        summary["shared_already_present"].append("_obsidian.md")
    else:
        if not dry_run:
            obsidian_target.write_text(OBSIDIAN_SEED, encoding="utf-8")
        summary["shared_seeded"].append("_obsidian.md")
    if git_target.exists():
        summary["shared_already_present"].append("_git-protocol.md")
    else:
        if not dry_run:
            git_target.write_text(GIT_PROTOCOL_SEED, encoding="utf-8")
        summary["shared_seeded"].append("_git-protocol.md")

    # 2b. Per-shared-reference section merge (v1.6.1+ additions). Runs against
    # both freshly-seeded files (which carry only the v1.6.0 baseline content)
    # and existing files (which may also be on the v1.6.0 baseline).
    for filename, sections in SHARED_REF_SECTIONS.items():
        target = roles_dir / filename
        if not target.exists():
            continue  # Should not happen — step 2 either seeded or skipped only when present
        original = target.read_text(encoding="utf-8")
        merged, added = merge_sections(original, sections, SHARED_REF_ANCHORS)
        already_present = [h for h, _ in sections if h not in added]
        summary["shared_sections_added"][filename] = added
        summary["shared_sections_already_present"][filename] = already_present
        if added and not dry_run:
            target.write_text(merged, encoding="utf-8")

    # 3. Per-role section merge
    for role, sections in ROLE_SECTIONS.items():
        role_path = roles_dir / f"{role}.md"
        if not role_path.exists():
            # Role file doesn't exist — out of scope for upgrade. (Base
            # bootstrap creates these. If a user has deleted one, we don't
            # try to recreate it from the seed; that's a different operation.)
            summary["roles_unchanged"].append(role)
            continue

        original = role_path.read_text(encoding="utf-8")
        merged, added = merge_role(original, sections)
        already_present = [h for h, _ in sections if h not in added]
        summary["role_sections_added"][role] = added
        summary["role_sections_already_present"][role] = already_present

        if not added:
            summary["roles_unchanged"].append(role)
            continue
        if not dry_run:
            role_path.write_text(merged, encoding="utf-8")

    return summary


def print_summary(s: dict) -> None:
    print("Role upgrade summary")
    print("------------------------")
    if s["dry_run"]:
        print("(DRY RUN — no files modified)")
    if s["backup"]:
        print(f"Backup:  {s['backup']}")
    print()
    print(f"Shared references seeded:        {len(s['shared_seeded'])}")
    for f in s["shared_seeded"]:
        print(f"  + {f}")
    print(f"Shared references already present: {len(s['shared_already_present'])}")
    for f in s["shared_already_present"]:
        print(f"  = {f}")
    # v1.6.1+ section additions inside shared references
    for filename, added in s.get("shared_sections_added", {}).items():
        present = s.get("shared_sections_already_present", {}).get(filename, [])
        if added or present:
            print(f"{filename}:")
            if added:
                print(f"  added {len(added)} section(s):")
                for h in added:
                    print(f"    + {h}")
            if present:
                print(f"  already had {len(present)} section(s):")
                for h in present:
                    print(f"    = {h}")
    print()
    for role in ROLE_SECTIONS:
        added = s["role_sections_added"].get(role, [])
        present = s["role_sections_already_present"].get(role, [])
        if role in s["roles_unchanged"] and not added and not present:
            print(f"{role}: file not found — skipped")
            continue
        print(f"{role}:")
        if added:
            print(f"  added {len(added)} section(s):")
            for h in added:
                print(f"    + {h}")
        if present:
            print(f"  already had {len(present)} section(s):")
            for h in present:
                print(f"    = {h}")
        if not added and not present:
            print("  no changes")
    print()
    print("NOTE: This upgrade only ADDS new H2 sections. It does NOT modify")
    print("      existing sections (e.g., 'Key Competencies', 'Output Conventions',")
    print("      or 'Invocation'). If you want the v1.6 bullet-level additions")
    print("      to those sections, see references/role-definitions.md and merge")
    print("      manually.")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Merge v1.6 additions into existing .pka/roles/ files (idempotent)."
    )
    ap.add_argument("--workspace", default=os.environ.get("WORKSPACE_ROOT", os.getcwd()))
    ap.add_argument("--dry-run", action="store_true", help="Report what would change; don't modify files.")
    args = ap.parse_args()
    s = upgrade_workspace(Path(args.workspace).resolve(), dry_run=args.dry_run)
    print_summary(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
