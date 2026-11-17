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

A role file that lacks both anchor headings ("## Output Conventions",
"## Invocation") still gets the new sections — appended at the end of the
file — and the summary says so, so the placement can be reviewed.

Exit codes:
    0  success
    1  workspace precondition failure (no .pka/roles/)
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

For the greeting's open threads, run `.pka/bin/pka-tools log open` (the open-threads field of the last 20 session-log entries, newest first) rather than reading the log by eye. `.pka/bin/pka-tools status` reports both predicates, the index state and whether the index needs migrating.
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

> "Which bootstrap should I run? Options: `obsidian` (vault retrofit), `git` (hybrid monorepo), `all` (both), `upgrade` (refresh role files and helpers in an already-bootstrapped workspace)."

Then hand off to the relevant procedure in the pka-bootstrap skill. All bootstraps are idempotent and user-triggered. Never run on detection alone.
""",
    ),
    (
        "## Session-end protocol (extended)",
        """\
In addition to the existing session log entry:

1. If `hybrid_monorepo_present`, run a consolidated push across child repos with unpushed commits. Implementation: `meta git push` if `meta` is on PATH; otherwise iterate `.meta` entries and run `git push` in each child directory (helper: `.pka/push-all.sh`).
2. If any child repo's push fails (auth, network, conflict, LFS upload disconnect): record the failure in the session summary with the repo path and error. Do not retry destructively. Session close still proceeds.
3. **Surface, do not commit, root-repo changes.** If `git status` in the root shows staged or unstaged changes, list them in the session summary and tell the user they're awaiting human review. Never auto-commit root.
4. Skipped pushes (the child repo has no `origin` remote, or there is nothing to push) are reported as **skipped**, not failures.
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

2. **Frontmatter and MOC update** — run `.pka/bin/pka-tools post-route <routed file>` once the file is in place. It adds the schema fields from `.pka/roles/_obsidian.md` that are missing (filename-derived values only: date, person, topic from the filename, domain tag from the folder), adds a `- [[file]]` bullet to the folder's `_MOC.md` (creating a stub if there is none), and then does the pointer row, index and commit steps below. Existing frontmatter lines and MOC entries are never changed or reordered. Files it cannot edit safely (malformed frontmatter, read-only, unusual line endings) are skipped and named in its output: put them in the routing report. Body-derived fields (attendees, a topic beyond the filename, related notes) are yours to fill, and only when confidence is high — empty is better than wrong.

3. **A different MOC section** — the bullet goes at the end of `## Files` (or a `## Unsorted` section). When the user keeps thematic sections and the right one is clear, pass `--section "<heading>"`.

4. **Person timelines** — `post-route` also puts the file on the `## Timeline` of each person it belongs to (the file is in their folder, or its `person` / `attendees` frontmatter or `## Attendees` links name them with high confidence, or their slug is in the filename). Give it the summary: `--summary` or `--summary-for <slug>=…`, at most 140 characters, from the file only — decisions and what that person owns; for a 1-1, topics only. Do not write `## Mentioned in` bullets; never guess who an ambiguous or nicknamed attendee is (`.pka/bin/pka-tools people resolve` says; ask the user, and save their answer with `people alias`). This step runs with or without Obsidian.

5. **Wikilinks vs plain links** — cross-references inside the vault use `[[wikilinks]]`; references to files outside the vault use plain markdown. See `.pka/roles/_obsidian.md` for the full rule.

When `obsidian_present` is false: no frontmatter and no MOC bullet. `post-route` still runs the person timeline (with relative markdown links), the pointer row (into existing MOCs only), the index and the commit.

Full conventions in `.pka/roles/_obsidian.md`. Consult that file when an Obsidian-specific decision is needed; do not duplicate the rules here.
""",
    ),
    (
        "## Commit/push protocol (gated on `hybrid_monorepo_present`)",
        """\
When the orchestrator's session-start detection reports `hybrid_monorepo_present` true:

- After completing a routing operation that lands in `knowledge/` or any `projects/<name>/`, auto-commit that semantic unit in **the destination child repo**. `.pka/bin/pka-tools post-route <file>` makes this commit as its last step, by path, with the message:
  ```
  Librarian: Route <filename> to <destination-folder>/

  Co-Authored-By: Claude <noreply@anthropic.com>
  ```
- One commit per routing unit. Side-effects of the route (MOC update, frontmatter, person-index backlink, **pointer-row maintenance**) belong to the same semantic unit and ride along in the same commit.
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

- After saving a brief inside a child repo (`knowledge/` or any `projects/<name>/`), run `.pka/bin/pka-tools post-route <brief> --role Researcher -m "Researcher: <short description of brief>"`. It adds the frontmatter, MOC link and pointer row, indexes the brief, and commits all of it as one unit in **the destination child repo** with the trailer:
  ```
  Researcher: <short description of brief>

  Co-Authored-By: Claude <noreply@anthropic.com>
  ```
- One commit per brief. If a brief includes other side-effect updates to the same vault (related-list updates in other notes), name them with `--also <path>` so they ride in the same commit.
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

1. **Identify the cluster** by running `.pka/bin/pka-tools pointers add <file>`. It uses the file's frontmatter (`type`, `topic`, `tags`, `attendees`/`person`/`related`), filename and folders — never the body. A row with the file's topic slug is its cluster; otherwise a row whose topic has at least two distinctive words, all of them among the file's; otherwise a new row is coined from the `topic`, the first tag plus `type`, or the filename. Pass `--topic <slug>` when you can see which cluster the file belongs to, and `--context` with the routing directive when there was one.
2. **Update the row.** The tool does this: for an existing cluster the file's wikilink goes at the end of the Files column and new entities at the end of the Entities column (nothing is re-sorted); for a new cluster a row is added below the existing rows. Do not edit the table by hand.
3. **Cross-MOC duplication.** If the file's tags include multiple top-level domain tags (e.g., `[ai, leadership]`), duplicate the pointer row to each corresponding MOC.
4. **Append-only.** Existing rows are extended, never deleted, reordered, or merged. User edits to row content are preserved verbatim across librarian routes.
5. **Soft size cap.** If a row's Files column reaches 8 entries, flag the row in the routing summary for human review rather than auto-splitting.
6. **Idempotency.** Re-routing the same file produces no change (the wikilink and entities are already present).

`post-route` runs this step for you; call `pointers add` directly only when you are not filing a file (for example, to put an existing note into a cluster with `--topic`).

Without Obsidian the pointer layer is **opt-in**: rows are written only into `_MOC.md` files that already exist, and no MOC is created. The tool reports "no MOC, pointer row not written". The user opts in with `.pka/bin/pka-tools pointers init`, which gives the vault's folders a MOC with an empty Pointers table.

Full conventions in `.pka/roles/_obsidian.md` (Pointer Layer section); the full procedure is `references/pointer-layer.md` in the pka-librarian skill.
""",
    ),
    (
        "## Indexing pointer rows",
        """\
`.pka/bin/pka-tools index` does this: each row of a `## Pointers` table becomes its own `search_fts` row tagged `is_pointer = 1`, and `.pka/bin/pka-tools search` ranks those rows 3× above equivalent body matches. Do not insert or query pointer rows by hand. See `references/sqlite-modes.md` in the pka-bootstrap skill for the schema and retrieval contract.
""",
    ),
    (
        "## Rename / graduate propagation",
        """\
When a file is renamed or moved by the librarian, every Pointers-row wikilink to its old path is updated to the new path across **all** `_MOC.md` files in the vault: `.pka/bin/pka-tools pointers rename <old> <new>` (add `--prefix` for a folder), then `post-route <new path> --also <old path>` so the move and the link updates are one commit. When a project is graduated from `projects/<name>/` into `knowledge/<subdir>/<name>/`, `graduate.sh` rewrites Pointers wikilinks for every file in that project. Both operations are idempotent and append-only at the row level.
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
| northwind-partnership-2026 | sasha-ortega, jamie-lin, taylor-brooks | [[northwind/2026-04-23-joint-partnership-meeting]], [[northwind/northwind_partnership_proposal]] |
| ai-adoption-research | satya-nadella, sundar-pichai | [[AI/ai-adoption-tier-productivity-gap-research]], [[AI/companies/vendor-landscape-research]] |
```

### Row schema

Three columns. All values are plain text; no nested structures; no YAML.

- **Topic** — hyphenated lowercase slug. Stable identifier for the concept cluster. Date-suffixed when event-bound (`northwind-partnership-2026`); undated for ongoing initiatives (`ai-adoption-research`).
- **Entities** — comma-separated lowercase hyphenated slugs (people, products, organizations, dates). No `[[wikilinks]]` here — entities are denormalized for FTS keyword density.
- **Files** — comma-separated `[[wikilinks]]` to constituent files. Use full relative paths from the vault root (`[[northwind/2026-04-23-joint-partnership-meeting]]`) to match the wikilink convention above.

**Granularity rule:** one row per concept cluster, not one row per file. A file may appear in multiple rows; that is correct. Row count per MOC should grow logarithmically with file count, not linearly — if a domain MOC has more pointer rows than files, the granularity is wrong.

### Librarian behavior (gated only on routing into a domain — NOT on `obsidian_present`)

When the librarian routes a file into a domain, after the file is moved and other Obsidian-mode side-effects are applied, it runs the pointer-maintenance step:

1. **Identify the cluster.** `.pka/bin/pka-tools pointers add <file>` uses the file's frontmatter (`type`, `topic`, `tags`, `attendees`/`person`/`related`), filename and folders, plus any routing-context directive. A row with the file's topic slug is its cluster; otherwise a row whose topic has at least two distinctive words, all of them among the file's; otherwise a new slug is coined from the file's topic / first tag plus type / filename. The librarian passes `--topic` when it can see which cluster the file belongs to.
2. **Update the row.** If a cluster matches, the new file's wikilink is added at the end of the Files column and any new entities from the file's frontmatter at the end of the Entities column (deduped; nothing is re-sorted). If no cluster matches, a new row is added below existing rows.
3. **Cross-MOC duplication.** If the file's tags include multiple top-level domain tags (e.g., `[ai, leadership]`), duplicate the pointer row to each corresponding MOC. The same row may appear in multiple `_MOC.md` files — that is correct and intentional (doubles the FTS hit rate; append-only invariant keeps drift bounded).
4. **Append-only.** Existing rows are extended, never deleted, reordered, or merged. User edits to row content are preserved verbatim across librarian routes.
5. **Soft size cap.** If a row's Files column reaches 8 entries, the librarian flags the row in the routing summary for human review rather than auto-splitting.
6. **Ambiguous cluster?** Default to the conservative read: append to the most-specific existing topic OR create a new row. Do not silently merge clusters that look similar but might not be.

`.pka/bin/pka-tools post-route` (or `pointers add`) does all of this. The full procedure is `references/pointer-layer.md` in the pka-librarian skill.

### Retrieval behavior

When a role needs to answer a question that requires reading existing knowledge:

1. **Query the FTS index** with `.pka/bin/pka-tools search <words>`, which boosts rows from `_MOC.md` Pointers tables 3× over body-level matches (rows tagged `is_pointer = 1`; see `references/sqlite-modes.md` in the pka-bootstrap skill).
2. **For each high-ranked pointer row hit**, parse the Files column → list of file paths.
3. **Expand to file bodies** by reading those files (typically 2–5 per cluster) instead of grepping all 1,500.
4. **Fall back to body-level FTS** if no pointer row matches above the confidence threshold. Pointer rows are a fast path, not the only path.

### Behavior without Obsidian

Without Obsidian the pointer layer is **opt-in**:

- Rows are written only into `_MOC.md` files that already exist. No MOC is created by routing, and a tag naming a folder without a MOC does not create one. The tool reports "no MOC, pointer row not written".
- To opt in, the user runs `.pka/bin/pka-tools pointers init` (optionally naming folders), which gives each folder a `_MOC.md` holding an empty Pointers table. From then on those MOCs are maintained like any other.
- In plain-markdown viewers the wikilinks render as literal `[[path]]` text. The FTS index still parses them and retrieval still benefits.

With Obsidian the layer is on by default: MOCs are created as needed, the wikilinks are clickable, and the Pointers section is an at-a-glance map of the domain.

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
- Not Obsidian-dependent. Plain-markdown workspaces that opt in get the same FTS-side gains; Obsidian only improves the rendering.
""",
    ),
]

OBSIDIAN_SECTIONS_V170 = [
    (
        "## Person timeline (added in v1.7.0)",
        """\
Each person's `index.md` carries a `## Timeline`: one line per note about them, newest first, kept by `pka-tools` inside two markers.

```markdown
## Timeline
<!-- pka:timeline v1 — maintained by pka-tools; newest first; edit summaries freely, leave links alone -->
- 2026-11-14 · meeting · [[leadership/2026-11-14-slt-sync|SLT sync]] — deferred the vendor decision; Priya owns the adapter spike
- 2026-11-10 · 1on1 · [[personnel/priya/2026-11-10-1-1-priya|1-1]] — Q1 goals, hiring plan
<!-- /pka:timeline -->
```

- **Line grammar:** `- <date> · <kind> · <link>[ — <summary>]`; kind is `1on1`, `meeting` or `doc`. The link is a wikilink in an Obsidian vault and a relative markdown link otherwise. This section is **not** gated on `obsidian_present`.
- **Who writes it:** `.pka/bin/pka-tools post-route` when a note is filed (any role). The role supplies the summary: at most 140 characters, drawn only from the note — decisions and what this person owns; for a 1-1, the topics only.
- **Who is on a note's timeline:** the person whose folder holds the note; people its `person` / `attendees` frontmatter or `## Attendees` links name with high confidence; a person whose slug is in the filename. A body mention is not enough. Ambiguous names are never added. Meetings with more than 8 resolved attendees add none of them. A note with `no-backref: true` goes on nobody's timeline.
- **Editing:** the user may rewrite any summary or add text inside the block; the tool never changes an existing line except to follow a renamed note. Do not reorder lines by hand if you want new ones to land in date order.
- **Rollback:** `.pka/bin/pka-tools timeline strip` removes the blocks.
- The older `## Mentioned in` back-link sections are no longer written; existing ones stay.
""",
    ),
]

SHARED_REF_SECTIONS = {
    "_obsidian.md": OBSIDIAN_SECTIONS_V161 + OBSIDIAN_SECTIONS_V170,
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
Location: `leadership/`, `ArchCouncil/`, or any domain-specific meeting folder
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
Location: `<people-home>/<person>/index.md` (the people home is the Repo Map folder tagged `people-home`; usually `personnel/`)
```yaml
---
type: person
name: <full name>
role: <role/title>
org: <org>
aliases: [<other names this person goes by>]
tags: [person]
---
```

`aliases` holds names the user has confirmed mean this person (a nickname, a maiden name). Roles add to it only when the user says so (`.pka/bin/pka-tools people alias <slug> "<name>"`); they never guess one.

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
- Prefer full relative paths (`[[personnel/robin/index]]`) over bare names (`[[robin]]`) to avoid Obsidian ambiguity resolution.

When `obsidian_present` is false: plain markdown links everywhere. Do not emit `[[wikilinks]]` — they render as literal text in non-Obsidian viewers.

## MOC (Map of Content) files

Filename: `_MOC.md` — underscore prefix sorts to the top of a folder listing.

Locations (one per top-level knowledge domain):
- `knowledge/_MOC.md`
- `knowledge/AI/_MOC.md`
- `knowledge/personnel/_MOC.md`
- `knowledge/leadership/_MOC.md`
- `knowledge/owner/_MOC.md`
- `knowledge/ArchCouncil/_MOC.md`
- `knowledge/lab-notebook/_MOC.md`
- (others as new domains emerge)

### Structure

Minimum-viable MOC is a bulleted list of wikilinks:

```markdown
# AI

## Subdomains
- [[AI/azure/_MOC|Azure]]
- [[AI/Meridian/_MOC|Meridian]]
- [[AI/companies/_MOC|Companies]]

## Files
- [[AI/ai-adoption-tier-productivity-gap-research]]
- [[AI/some-other-brief]]
```

Thematic grouping (e.g., "Strategy docs" vs "Research briefs" vs "Vendor notes") is user work — roles do not attempt it automatically. Roles only append to an existing section or to an "Unsorted" catch-all at the bottom.

### Update policy

- When a role files a new note into a domain, a bullet linking to it is added to the nearest MOC (the note's folder, else its top-level folder), at the end of `## Files` or under `## Unsorted`. The MOC is created if absent (with a stub matching the structure above). `.pka/bin/pka-tools post-route` does this; `.pka/bin/pka-tools moc add-link` does it alone.
- Never remove or reorder existing entries.
- MOCs are navigation aids, not authoritative indexes — if the MOC diverges from the actual folder contents, the folder contents win.

## Pointer Layer (added in v1.6.1)

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
| northwind-partnership-2026 | sasha-ortega, jamie-lin, taylor-brooks | [[northwind/2026-04-23-joint-partnership-meeting]], [[northwind/northwind_partnership_proposal]] |
| ai-adoption-research | satya-nadella, sundar-pichai | [[AI/ai-adoption-tier-productivity-gap-research]], [[AI/companies/vendor-landscape-research]] |
```

### Row schema

Three columns. All values are plain text; no nested structures; no YAML.

- **Topic** — hyphenated lowercase slug. Stable identifier for the concept cluster. Date-suffixed when event-bound (`northwind-partnership-2026`); undated for ongoing initiatives (`ai-adoption-research`).
- **Entities** — comma-separated lowercase hyphenated slugs (people, products, organizations, dates). No `[[wikilinks]]` here — entities are denormalized for FTS keyword density.
- **Files** — comma-separated `[[wikilinks]]` to constituent files. Use full relative paths from the vault root (`[[northwind/2026-04-23-joint-partnership-meeting]]`) to match the wikilink convention above.

**Granularity rule:** one row per concept cluster, not one row per file. A file may appear in multiple rows; that is correct. Row count per MOC should grow logarithmically with file count, not linearly — if a domain MOC has more pointer rows than files, the granularity is wrong.

### Librarian behavior (gated only on routing into a domain — NOT on `obsidian_present`)

When the librarian routes a file into a domain, after the file is moved and other Obsidian-mode side-effects are applied, it runs the pointer-maintenance step:

1. **Identify the cluster.** `.pka/bin/pka-tools pointers add <file>` uses the file's frontmatter (`type`, `topic`, `tags`, `attendees`/`person`/`related`), filename and folders, plus any routing-context directive. A row with the file's topic slug is its cluster; otherwise a row whose topic has at least two distinctive words, all of them among the file's; otherwise a new slug is coined from the file's topic / first tag plus type / filename. The librarian passes `--topic` when it can see which cluster the file belongs to.
2. **Update the row.** If a cluster matches, the new file's wikilink is added at the end of the Files column and any new entities from the file's frontmatter at the end of the Entities column (deduped; nothing is re-sorted). If no cluster matches, a new row is added below existing rows.
3. **Cross-MOC duplication.** If the file's tags include multiple top-level domain tags (e.g., `[ai, leadership]`), duplicate the pointer row to each corresponding MOC. The same row may appear in multiple `_MOC.md` files — that is correct and intentional (doubles the FTS hit rate; append-only invariant keeps drift bounded).
4. **Append-only.** Existing rows are extended, never deleted, reordered, or merged. User edits to row content are preserved verbatim across librarian routes.
5. **Soft size cap.** If a row's Files column reaches 8 entries, the librarian flags the row in the routing summary for human review rather than auto-splitting.
6. **Ambiguous cluster?** Default to the conservative read: append to the most-specific existing topic OR create a new row. Do not silently merge clusters that look similar but might not be.

`.pka/bin/pka-tools post-route` (or `pointers add`) does all of this. The full procedure is `references/pointer-layer.md` in the pka-librarian skill.

### Retrieval behavior

When a role needs to answer a question that requires reading existing knowledge:

1. **Query the FTS index** with `.pka/bin/pka-tools search <words>`, which boosts rows from `_MOC.md` Pointers tables 3× over body-level matches (rows tagged `is_pointer = 1`; see `references/sqlite-modes.md` in the pka-bootstrap skill).
2. **For each high-ranked pointer row hit**, parse the Files column → list of file paths.
3. **Expand to file bodies** by reading those files (typically 2–5 per cluster) instead of grepping all 1,500.
4. **Fall back to body-level FTS** if no pointer row matches above the confidence threshold. Pointer rows are a fast path, not the only path.

### Behavior without Obsidian

Without Obsidian the pointer layer is **opt-in**:

- Rows are written only into `_MOC.md` files that already exist. No MOC is created by routing, and a tag naming a folder without a MOC does not create one. The tool reports "no MOC, pointer row not written".
- To opt in, the user runs `.pka/bin/pka-tools pointers init` (optionally naming folders), which gives each folder a `_MOC.md` holding an empty Pointers table. From then on those MOCs are maintained like any other.
- In plain-markdown viewers the wikilinks render as literal `[[path]]` text. The FTS index still parses them and retrieval still benefits.

With Obsidian the layer is on by default: MOCs are created as needed, the wikilinks are clickable, and the Pointers section is an at-a-glance map of the domain.

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
- Not Obsidian-dependent. Plain-markdown workspaces that opt in get the same FTS-side gains; Obsidian only improves the rendering.

## Person timeline (added in v1.7.0)

Each person's `index.md` carries a `## Timeline`: one line per note about them, newest first, kept by `pka-tools` inside two markers.

```markdown
## Timeline
<!-- pka:timeline v1 — maintained by pka-tools; newest first; edit summaries freely, leave links alone -->
- 2026-11-14 · meeting · [[leadership/2026-11-14-slt-sync|SLT sync]] — deferred the vendor decision; Priya owns the adapter spike
- 2026-11-10 · 1on1 · [[personnel/priya/2026-11-10-1-1-priya|1-1]] — Q1 goals, hiring plan
<!-- /pka:timeline -->
```

- **Line grammar:** `- <date> · <kind> · <link>[ — <summary>]`; kind is `1on1`, `meeting` or `doc`. The link is a wikilink in an Obsidian vault and a relative markdown link otherwise. This section is **not** gated on `obsidian_present`.
- **Who writes it:** `.pka/bin/pka-tools post-route` when a note is filed (any role). The role supplies the summary: at most 140 characters, drawn only from the note — decisions and what this person owns; for a 1-1, the topics only.
- **Who is on a note's timeline:** the person whose folder holds the note; people its `person` / `attendees` frontmatter or `## Attendees` links name with high confidence; a person whose slug is in the filename. A body mention is not enough. Ambiguous names are never added. Meetings with more than 8 resolved attendees add none of them. A note with `no-backref: true` goes on nobody's timeline.
- **Editing:** the user may rewrite any summary or add text inside the block; the tool never changes an existing line except to follow a renamed note. Do not reorder lines by hand if you want new ones to land in date order.
- **Rollback:** `.pka/bin/pka-tools timeline strip` removes the blocks.
- The older `## Mentioned in` back-link sections are no longer written; existing ones stay.

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
- `ai`, `leadership`, `personnel`, `archcouncil`, `lab-notebook`, `dev-process`, `reference`, `data`, `archived`

### Topic tags

Free-form, added as useful: `strategy`, `mcp`, `lunch-and-learn`, etc.

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

Roles make these commits with the workspace's tool, never with `git add -A`: `.pka/bin/pka-tools post-route <file> --role <Role>` after filing a note (it commits the note with every file it touched), or `.pka/bin/pka-tools commit -m "<Role>: …" -- <paths>` for anything else. Both stage and commit exactly the named paths, add the trailer, refuse to commit the root repo, and exit 1 when git refuses the commit.

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

If a child repo has no `origin` remote, report it as a **skipped** push, not a failure. The child repo's own remote is what a push uses; the URL in `.meta` is a copy that `.pka/build-repo-list.sh` regenerates, so set remotes with `git -C <child> remote add origin <url>` and then re-run that script.

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

_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def _outside_fence_lines(text: str):
    """Yield (offset, line_without_newline) for every line that is NOT inside
    a fenced code block (``` or ~~~). Headings shown as examples inside a
    fence are documentation, not structure, and must never be matched.
    """
    offset = 0
    fence = None  # (char, length) of the fence that is currently open
    for line in text.splitlines(keepends=True):
        bare = line.rstrip("\r\n")
        m = _FENCE_RE.match(bare)
        if fence is None:
            if m:
                fence = (m.group(1)[0], len(m.group(1)))
            else:
                yield offset, bare
        elif m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] \
                and not bare[m.end():].strip():
            fence = None
        offset += len(line)


def section_present(text: str, heading: str) -> bool:
    """True if the markdown text contains an H2 with this exact heading text
    (outside fenced code blocks)."""
    needle = heading.strip()
    for _, line in _outside_fence_lines(text):
        if line.strip() == needle:
            return True
    return False


def find_anchor_offset(text: str, anchors: tuple[str, ...] = ANCHOR_SECTIONS) -> int | None:
    """Return the character offset where new sections should be inserted.

    Searches for the first occurrence of any anchor heading outside fenced
    code blocks. Returns None if no anchor is found (caller will append at
    end of file).
    """
    for offset, line in _outside_fence_lines(text):
        if line.rstrip() in anchors:
            return offset
    return None


def detect_newline(text: str) -> str:
    """The file's line ending: CRLF if that is what it uses, else LF."""
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    return "\r\n" if crlf > lf else "\n"


def read_text_exact(path: Path) -> str:
    """Read without newline translation, so CRLF files stay CRLF."""
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write_text_exact(path: Path, text: str) -> None:
    """Write without newline translation, via a temp file renamed into place
    so an interrupted run cannot leave a half-written role file."""
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)


def merge_sections(
    text: str,
    sections: list[tuple[str, str]],
    anchors: tuple[str, ...] = ANCHOR_SECTIONS,
) -> tuple[str, list[str], bool]:
    """Insert any missing sections into `text` before the first anchor.
    Returns the updated text, the list of headings that were added, and
    whether an anchor was found (False means the sections were appended at
    the end of the file).

    Identical merge logic for both role files and shared-reference files;
    only the anchor list differs. Inserted text uses the file's own line
    ending.
    """
    added: list[str] = []
    insertion = ""
    for heading, body in sections:
        if section_present(text, heading):
            continue
        insertion += f"\n{heading}\n\n{body.rstrip()}\n"
        added.append(heading)

    if not insertion:
        return text, [], True

    nl = detect_newline(text)
    if nl != "\n":
        insertion = insertion.replace("\n", nl)

    anchor = find_anchor_offset(text, anchors)
    if anchor is None:
        new_text = text.rstrip() + nl + insertion + nl
    else:
        new_text = text[:anchor] + insertion.lstrip("\r\n") + nl + text[anchor:]
    return new_text, added, anchor is not None


def merge_role(text: str, sections: list[tuple[str, str]]) -> tuple[str, list[str], bool]:
    """Role-file wrapper around merge_sections."""
    return merge_sections(text, sections, ANCHOR_SECTIONS)


# ---------------------------------------------------------------------------
# REFRESHING SECTIONS A WORKSPACE ALREADY HAS
# ---------------------------------------------------------------------------
# Merging only adds missing sections, so a section seeded by an earlier
# version keeps its old wording. A section can be refreshed safely when its
# text is exactly one that some version of pka-skills shipped: then the user
# never edited it. KNOWN_SECTION_HASHES lists those versions, per file and
# heading; scripts/seeds.py maintains it (append-only). Anything else is the
# user's text and is left alone unless they name it with --refresh-section.

KNOWN_SECTION_HASHES = {
    "_git-protocol.md:## Commit message structure": [
        "126711e5cea369e1",
        "75a8a124961afb6d",
    ],
    "_git-protocol.md:## Commit triggers": [
        "e7568f8322fc40bf",
    ],
    "_git-protocol.md:## Detection": [
        "4995172e138727ac",
    ],
    "_git-protocol.md:## Failure behavior": [
        "a6fa554b79eccaa0",
    ],
    "_git-protocol.md:## Graduation commit sequence": [
        "1f0a351155730e76",
    ],
    "_git-protocol.md:## Interaction with the Obsidian bootstrap": [
        "4087e248bd11924e",
    ],
    "_git-protocol.md:## Interaction with the git bootstrap": [
        "16ed3c8ed9df669f",
    ],
    "_git-protocol.md:## Invariants": [
        "d42361167e8ce225",
    ],
    "_git-protocol.md:## Push behavior — never silent failures": [
        "7fca636ec0def1ea",
        "8f363bff35c45323",
    ],
    "_git-protocol.md:## Push triggers": [
        "7dd825f0e537bb4a",
    ],
    "_obsidian.md:## Bootstrap": [
        "b618b9c19693c59c",
    ],
    "_obsidian.md:## Detection": [
        "7e65b438597956a2",
    ],
    "_obsidian.md:## Error handling": [
        "84b0fe3cf1a3134e",
    ],
    "_obsidian.md:## Filename conventions": [
        "935e32e08a412eb8",
    ],
    "_obsidian.md:## Frontmatter schemas": [
        "3867a112ba2567a5",
        "c8a8541ce5e8a058",
    ],
    "_obsidian.md:## Invariants": [
        "226d78da88f75110",
    ],
    "_obsidian.md:## MOC (Map of Content) files": [
        "635438f5814f1445",
        "744712aba83670e6",
    ],
    "_obsidian.md:## Person timeline (added in v1.7.0)": [
        "14e620138389ca80",
    ],
    "_obsidian.md:## Pointer Layer (added in v1.6.1)": [
        "0828652fcbd3498a",
        "387e539222cb1a1b",
        "480c1093f80bc9a4",
        "934d75cb738d5168",
        "fcadb8fab61ccda5",
    ],
    "_obsidian.md:## Rules for writing frontmatter": [
        "8391a8393849ff71",
    ],
    "_obsidian.md:## Tag conventions": [
        "ae5a9559d0ddcb28",
    ],
    "_obsidian.md:## When this file is out of date": [
        "2c0297e40ceba15f",
    ],
    "_obsidian.md:## Wikilink syntax": [
        "7bdfac0e77fcb0c5",
    ],
    "librarian.md:## Commit/push protocol (gated on `hybrid_monorepo_present`)": [
        "175ebb697c4e1453",
        "742bffe4b2a0b59e",
        "f7c63d0b795c52ac",
    ],
    "librarian.md:## Indexing pointer rows": [
        "394b4ec9ecfaacc5",
        "acc2d758eff419d3",
    ],
    "librarian.md:## Obsidian coexistence (gated on `obsidian_present`)": [
        "3a018531223ad484",
        "e8318781cac59a41",
        "ea5b5c5245088095",
    ],
    "librarian.md:## Pointer-row maintenance (gated only on routing into a domain — NOT on `obsidian_present`)": [
        "0cbeab387c62987f",
        "729b90af7286cc06",
        "d6134ae35bdaf95b",
    ],
    "librarian.md:## Rename / graduate propagation": [
        "4c33bf525498ff00",
        "aa6f7019518431e6",
    ],
    "orchestrator.md:## Bootstrap dispatch": [
        "5e90aed21362ad95",
        "7b69d81990957438",
        "d24f1dc6b3c43b6e",
    ],
    "orchestrator.md:## File references in responses": [
        "15900644fd78297f",
    ],
    "orchestrator.md:## Mid-session push handling": [
        "be23555efbeb6c03",
    ],
    "orchestrator.md:## Session-end protocol (extended)": [
        "d38aa1431e1ee2c7",
        "dfaed399435dc0ba",
    ],
    "orchestrator.md:## Session-start checks (cached for the session)": [
        "2f287173daffc1c5",
        "84e84c3377a6019d",
    ],
    "researcher.md:## Commit/push protocol (gated on `hybrid_monorepo_present`)": [
        "1aae6574f77242fb",
        "8513d149f6340902",
    ],
    "researcher.md:## Obsidian coexistence (gated on `obsidian_present`)": [
        "081c2181daa2fdbf",
    ],
}


def normalise_section(body: str) -> str:
    """Whitespace-insensitive form of a section body, for comparison."""
    lines = [line.rstrip() for line in body.replace("\r\n", "\n").split("\n")]
    out: list[str] = []
    for line in lines:
        if not line and (not out or not out[-1]):
            continue
        out.append(line)
    while out and not out[-1]:
        out.pop()
    return "\n".join(out)


def section_hash(body: str) -> str:
    import hashlib
    return hashlib.sha256(normalise_section(body).encode("utf-8")).hexdigest()[:16]


def h2_sections(text: str) -> list[tuple[str, int, int, int]]:
    """(heading, heading offset, body offset, end offset) for each H2
    outside fenced blocks. The body runs to the next such H2 or the end."""
    heads = []
    for offset, line in _outside_fence_lines(text):
        if line.startswith("## "):
            heads.append((line.rstrip(), offset))
    out = []
    for idx, (heading, offset) in enumerate(heads):
        newline_at = text.find("\n", offset)
        body_start = len(text) if newline_at == -1 else newline_at + 1
        end = heads[idx + 1][1] if idx + 1 < len(heads) else len(text)
        out.append((heading, offset, body_start, end))
    return out


def _seed_sections(seed: str) -> list[tuple[str, str]]:
    return [(heading, seed[body:end]) for heading, _, body, end in h2_sections(seed)]


def refreshable_sections(filename: str) -> list[tuple[str, str]]:
    """The sections of a seeded file that pka-skills owns and may refresh."""
    if filename == "_obsidian.md":
        return _seed_sections(OBSIDIAN_SEED)
    if filename == "_git-protocol.md":
        return _seed_sections(GIT_PROTOCOL_SEED)
    role = filename[:-3] if filename.endswith(".md") else filename
    return list(ROLE_SECTIONS.get(role, []))


def plan_refresh(filename: str, text: str, forced: set) -> tuple[str, list[dict]]:
    """Return (new text, findings). A finding is {heading, state} with state
    current, refreshed (was a shipped version), or customised (left alone
    unless forced)."""
    wanted = dict(refreshable_sections(filename))
    if not wanted:
        return text, []
    nl = detect_newline(text)
    findings = []
    replacements = []
    sections = h2_sections(text)
    for index, (heading, _, body_start, end) in enumerate(sections):
        if heading not in wanted:
            continue
        have = text[body_start:end]
        target = wanted[heading]
        if normalise_section(have) == normalise_section(target):
            findings.append({"heading": heading, "state": "current"})
            continue
        known = section_hash(have) in KNOWN_SECTION_HASHES.get("%s:%s" % (filename, heading), [])
        if known or heading in forced:
            last = index == len(sections) - 1
            new_body = nl + target.strip("\n").replace("\n", nl) + nl + ("" if last else nl)
            replacements.append((body_start, end, new_body))
            findings.append({"heading": heading, "state": "refreshed" if known else "replaced (customised)",
                             "old": have, "new": target})
        else:
            findings.append({"heading": heading, "state": "customised", "old": have, "new": target})
    for start, end, body in sorted(replacements, reverse=True):
        text = text[:start] + body + text[end:]
    return text, findings


def unique_backup_root(parent: Path, stamp: str) -> Path:
    """A backup directory name that does not exist yet. Two runs within the
    same second get `<stamp>` and `<stamp>-2` rather than a crash."""
    candidate = parent / stamp
    n = 1
    while candidate.exists():
        n += 1
        candidate = parent / f"{stamp}-{n}"
    return candidate


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------

def upgrade_workspace(workspace: Path, dry_run: bool = False, refresh: bool = False,
                      forced: list | None = None) -> dict:
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
        "appended_at_end": [],
        "refresh": {},
        "refresh_applied": refresh,
        "dry_run": dry_run,
    }
    forced_by_file: dict = {}
    for item in forced or []:
        filename, _, heading = item.partition(":")
        heading = heading.strip()
        if not heading.startswith("## "):
            raise SystemExit("ERROR: --refresh-section takes FILE:## Heading, e.g. "
                             "'researcher.md:## Commit/push protocol (gated on `hybrid_monorepo_present`)'")
        allowed = [h for h, _ in refreshable_sections(filename)]
        if heading not in allowed:
            listing = "\n  ".join(allowed) if allowed else "(none: not a seeded file)"
            raise SystemExit(f"ERROR: {filename}: {heading!r} is not a seeded section, so it cannot be "
                             f"refreshed. The seeded sections of {filename} are:\n  {listing}")
        forced_by_file.setdefault(filename, set()).add(heading)

    def refreshed(filename: str, text: str) -> str:
        new_text, findings = plan_refresh(filename, text, forced_by_file.get(filename, set()) if refresh else set())
        if findings:
            summary["refresh"][filename] = findings
        return new_text if refresh else text

    # 1. Backup .pka/roles/ to .pka/upgrade-backups/<timestamp>/roles/
    if not dry_run:
        ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backups_dir = pka_dir / "upgrade-backups"
        backups_dir.mkdir(parents=True, exist_ok=True)
        # Keep the backups out of the root repo even on workspaces whose root
        # .gitignore predates this directory.
        ignore_file = backups_dir / ".gitignore"
        if not ignore_file.exists():
            ignore_file.write_text("*\n", encoding="utf-8")
        backup_root = unique_backup_root(backups_dir, ts)
        backup_root.mkdir(parents=True)
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
        if not target.exists() and not dry_run:
            continue  # Should not happen — step 2 either seeded or skipped only when present
        original = read_text_exact(target) if target.exists() else (OBSIDIAN_SEED if filename == "_obsidian.md" else GIT_PROTOCOL_SEED)
        merged, added, anchored = merge_sections(original, sections, SHARED_REF_ANCHORS)
        already_present = [h for h, _ in sections if h not in added]
        summary["shared_sections_added"][filename] = added
        summary["shared_sections_already_present"][filename] = already_present
        if added and not anchored:
            summary["appended_at_end"].append(filename)
        final = refreshed(filename, merged)
        if final != original and not dry_run:
            write_text_exact(target, final)

    # 3. Per-role section merge
    for role, sections in ROLE_SECTIONS.items():
        role_path = roles_dir / f"{role}.md"
        if not role_path.exists():
            # Role file doesn't exist — out of scope for upgrade. (Base
            # bootstrap creates these. If a user has deleted one, we don't
            # try to recreate it from the seed; that's a different operation.)
            summary["roles_unchanged"].append(role)
            continue

        original = read_text_exact(role_path)
        merged, added, anchored = merge_role(original, sections)
        already_present = [h for h, _ in sections if h not in added]
        summary["role_sections_added"][role] = added
        summary["role_sections_already_present"][role] = already_present
        if added and not anchored:
            summary["appended_at_end"].append(f"{role}.md")
        final = refreshed(f"{role}.md", merged)
        if final == original:
            summary["roles_unchanged"].append(role)
            continue
        if not dry_run:
            write_text_exact(role_path, final)

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
    if s.get("appended_at_end"):
        verb = "would be" if s["dry_run"] else "were"
        print("WARNING: no anchor heading ('## Output Conventions' / '## Invocation',")
        print("         or a shared-reference anchor) was found in the file(s) below,")
        print(f"         so the new sections {verb} appended at the END of the file.")
        print("         Review the placement:")
        for f in s["appended_at_end"]:
            print(f"           - .pka/roles/{f}")
        print()
    stale = [(f, x) for f, items in s.get("refresh", {}).items() for x in items if x["state"] != "current"]
    if stale:
        done = s.get("refresh_applied") and not s["dry_run"]
        print("Sections seeded by an earlier version:")
        for filename, item in stale:
            state = item["state"]
            if state == "refreshed":
                label = "refreshed" if done else ("would be refreshed" if s.get("refresh_applied") else
                                                  "can be refreshed (unchanged since it was seeded)")
            elif state == "replaced (customised)":
                label = "replaced as requested" if done else "would be replaced as requested"
            else:
                label = "customised — left alone"
            print(f"  {filename}: {item['heading']}  — {label}")
        if not s.get("refresh_applied"):
            print("  Run again with --refresh to update the unchanged ones (a backup is taken first).")
        if any(item["state"] == "customised" for _, item in stale):
            print("  Customised sections are never replaced automatically. Compare with --diff;")
            print("  to take the new text for one, pass --refresh --refresh-section 'FILE:## Heading'.")
        print()
    print("NOTE: Sections outside the seeded set (e.g. 'Key Competencies', 'Output")
    print("      Conventions', 'Invocation') are never modified. If you want later")
    print("      bullet-level additions there, see references/role-definitions.md and")
    print("      merge manually.")


def print_diffs(s: dict) -> None:
    import difflib
    for filename, items in s.get("refresh", {}).items():
        for item in items:
            if item["state"] == "current":
                continue
            old = normalise_section(item["old"]).split("\n")
            new = normalise_section(item["new"]).split("\n")
            print(f"--- {filename}: {item['heading']} (yours)")
            print(f"+++ {filename}: {item['heading']} (current pka-skills)")
            for line in list(difflib.unified_diff(old, new, lineterm="", n=1))[2:]:
                print(line)
            print()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Merge v1.6 additions into existing .pka/roles/ files (idempotent)."
    )
    ap.add_argument("--workspace", default=os.environ.get("WORKSPACE_ROOT", os.getcwd()))
    ap.add_argument("--dry-run", action="store_true", help="Report what would change; don't modify files.")
    ap.add_argument("--refresh", action="store_true",
                    help="Also replace seeded sections that are unchanged since an earlier version seeded them.")
    ap.add_argument("--refresh-section", action="append", default=[], metavar="FILE:## Heading",
                    help="With --refresh: also replace this customised section (repeatable).")
    ap.add_argument("--diff", action="store_true", help="Print how each out-of-date section differs.")
    args = ap.parse_args()
    if args.refresh_section and not args.refresh:
        ap.error("--refresh-section needs --refresh")
    s = upgrade_workspace(Path(args.workspace).resolve(), dry_run=args.dry_run, refresh=args.refresh,
                          forced=args.refresh_section)
    print_summary(s)
    if args.diff:
        print_diffs(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
