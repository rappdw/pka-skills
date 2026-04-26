# Pointer-Layer Maintenance — Per-Route Algorithm

Applies to **every** routing operation that lands a file inside a domain that has (or should have) a `_MOC.md`. **Not** gated on `obsidian_present` — pointer-row maintenance runs in plain-markdown workspaces too. The retrieval value comes from FTS, not from rendering.

Conventions (file location, row schema, retrieval behavior, invariants) live in `.pka/roles/_obsidian.md` (the "Pointer Layer" section). This document is the **operational algorithm**; the conventions document is the **contract**.

## Inputs

For each route, the librarian has access to:

- The routed file's **path** (post-route).
- The file's **frontmatter** if present (`type`, `topic`, `tags`, `attendees` / `person` / `related`).
- The **routing context** — the user directive that prompted the route, when available.
- The destination **domain MOC** (`<domain>/_MOC.md`) and any **secondary MOCs** the file's tags imply.

Body content is NOT an input. The maintenance step never reads the file's body.

## Per-route checklist

### 1. Build the candidate token set

Tokens come from these fields in priority order, lowercased and split on `[-_\s]`:

- `topic` field of the frontmatter (highest signal)
- All `tags`
- `type`
- All values in `attendees`, `person`, `related` (after stripping wikilink brackets)
- The filename **stem** (after stripping date prefix and `.md`)
- Any salient nouns from the routing-context directive (best-effort; skip if no directive)

Strip stop-words (`the`, `and`, `for`, `with`, `to`, etc.) and very-short tokens (length < 3).

### 2. Score against existing topic slugs

For each existing row in the destination MOC's Pointers table:

```
slug_tokens   = lowercase split of Topic on '-'
candidate_tokens = the set from step 1
jaccard       = |slug_tokens ∩ candidate_tokens| / |slug_tokens ∪ candidate_tokens|
```

If `max(jaccard) >= 0.5`: the file matches an existing cluster. Use the highest-scoring row.

If `max(jaccard) < 0.5`: coin a new slug. Construct it from:

1. `frontmatter.topic` if present (already a slug or close to one).
2. Else: `<first-tag>-<type>` (e.g., `meeting-leadership` becomes `leadership-meeting` if neither is purely the `meeting` type tag).
3. Else: a slug derived from the filename stem.

Date-suffix the slug only if the cluster is event-bound (the file is dated and `topic`/`type` indicates a specific event). Examples:
- `anthropic-partnership-2026` (event-bound) — slug includes year
- `ai-adoption-research` (ongoing) — no date

### 3. Compute the entity set

Entities come from the file's `attendees`, `person`, `related` (after stripping wikilink brackets), plus any explicit organizations/products mentioned in `tags`. All lowercased, hyphenated. Strip duplicates.

Do NOT include entities derived from filename heuristics — too noisy. Frontmatter only.

### 4. Apply the update

Two cases:

**Case A — matched an existing cluster** (jaccard ≥ 0.5):

- Locate the matching row in the MOC's Pointers table.
- **Append** the file's full-vault-relative wikilink to the Files column if not already present.
- **Merge** new entities into the Entities column: union with the existing entity set, dedupe, sort alphabetically.
- Re-render the row with the merged columns. Other rows untouched.
- If the resulting row's Files column has **8 or more entries**, flag the row in the routing summary for the user to consider splitting. Do NOT auto-split.

**Case B — coined a new cluster**:

- Append a new row at the bottom of the Pointers table with the new slug, the entity set, and the single file's wikilink.
- If the table doesn't exist yet (the MOC is fresh from the obsidian bootstrap), create the `## Pointers` section with its preamble and the header row, then append the new data row.
- If the MOC itself doesn't exist, create it (using the standard MOC stub) including the empty `## Pointers` section, then append the data row.

Both cases are **idempotent**: re-routing the same file produces no diff (the wikilink and entities are already present).

### 5. Cross-MOC duplication

Inspect the file's tags. For every tag that matches a top-level domain folder under `knowledge/`, the same pointer row is duplicated into that domain's `_MOC.md` (creating the table or MOC if absent).

Example: a meeting note routed to `knowledge/AI/anthropic/` with `tags: [meeting, ai, leadership]`:
- Primary: append the row to `knowledge/AI/_MOC.md`'s Pointers table.
- Cross-MOC: append the same row to `knowledge/leadership/_MOC.md`'s Pointers table.

The same row in multiple MOCs is intentional — doubles the FTS hit rate. The append-only invariant keeps drift bounded: each MOC's row evolves independently, but neither is ever silently merged or deleted.

### 6. Wikilink format

Files-column wikilinks use **full vault-relative paths**: `[[anthropic/2026-04-23-gcn-partnership-meeting]]`. Bare names (`[[2026-04-23-gcn-partnership-meeting]]`) would be ambiguous in Obsidian and fragile under FTS. The path is relative to `knowledge/` (the vault root), without the `.md` extension.

## Failure handling

Per `.pka/roles/_obsidian.md`'s error-handling rules: any per-step failure logs a warning and completes the primary route. Pointer-row maintenance is opportunistic — never blocks routing. Failures land in the routing report.

Specific cases:

- **Malformed Pointers table** (header missing, columns misaligned): skip maintenance for that MOC; report the malformed table in the summary; do not attempt repair.
- **MOC file is locked / unwritable**: log; complete the route without the pointer update.
- **No frontmatter and no routing context**: coin a slug from the filename stem alone. The cluster may be coarse; the user can split it later.

## Rename / move propagation

When the librarian renames or moves a file (separate from routing), it walks every `_MOC.md` in the vault and rewrites pointer-row wikilinks pointing at the old path:

```
[[old/path/to/file]]   →  [[new/path/to/file]]
```

Idempotent (running twice produces no diff). Append-only at row level (never deletes a row even if the file is moved out of a domain — the row's other entries may still be valid).

## Graduation propagation

When `graduate.sh` moves a project from `projects/<name>/` to `knowledge/<subdir>/<name>/`, every pointer-row wikilink under `[[projects/<name>/...]]` is rewritten to `[[<subdir>/<name>/...]]`. Implementation lives in `graduate.sh` itself (see `bootstrap-assets/scripts/graduate.sh`). The graduation commit in `knowledge/` includes both the file moves and the pointer-row updates as one semantic unit.

## What the librarian does NOT do

- **Does not split overlong rows.** Rows with ≥ 8 files in the Files column are flagged in the summary for the user to split manually if desired.
- **Does not merge rows.** Two rows with similar topics stay separate; the user merges manually if appropriate.
- **Does not modify rows that the user has hand-edited.** As long as the librarian only ADDS files/entities and never reorders, user customizations to topic slugs, entity ordering, or surrounding markdown are preserved.
- **Does not delete rows.** Even when every file the row points at has been deleted, the empty row is preserved (with the broken wikilinks visible) — the lint health check (rule 2) flags those for user attention, and the user removes the row manually.

## Idempotency check

After every route, re-running the same maintenance step produces no diff: the wikilink is already in the Files column, the entities are already in the Entities column. Confirm in the test harness with PR2.
