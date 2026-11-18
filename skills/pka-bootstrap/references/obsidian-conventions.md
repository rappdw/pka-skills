# Obsidian Coexistence Conventions (seed)

This file is the **source of truth** for the `_obsidian.md` shared-reference that `pka-bootstrap` writes to `.pka/roles/_obsidian.md` in a user's workspace. The content below is what gets seeded verbatim (with no template substitution).

`.pka/roles/_obsidian.md` is **shared reference** for pka roles (orchestrator, librarian, researcher). It is not a role itself. Roles link here instead of duplicating these rules.

All conventions on this page apply **only when Obsidian is detected**. When it isn't, roles continue their pre-Obsidian behavior unchanged.

---

## Seed content (copied verbatim into `.pka/roles/_obsidian.md`)

```markdown
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
- **What a timeline can link to:** in an Obsidian vault, notes in the vault (a wikilink cannot leave it). Without Obsidian, any note in the workspace — `projects/`, a root `meeting-notes/`, the vault — except `owner-inbox/`, `team-inbox/` (not filed yet) and hidden folders. Notes are never moved to make them reachable.
- **Who writes it:** `.pka/bin/pka-tools post-route` when a note is filed (any role). The role supplies the summary: at most 140 characters, drawn only from the note — decisions and what this person owns; for a 1-1, the topics only.
- **Who is on a note's timeline:** the person whose folder holds the note; people its `person` / `attendees` frontmatter or `## Attendees` links name with high confidence; a person whose slug is in the filename. A body mention is not enough. Ambiguous names are never added. Meetings with more than 8 resolved attendees add none of them. A note with `no-backref: true` goes on nobody's timeline.
- **Editing:** the user may rewrite any summary or add text inside the block; the tool never changes an existing line except to follow a renamed note. Do not reorder lines by hand if you want new ones to land in date order.
- **Backfill:** notes filed before the timeline existed are added once, with `.pka/bin/pka-tools timeline plan` (a report to review) and then `timeline apply <plan>`, which backs up and verifies; `timeline restore <id>` undoes it. The librarian runs it on request.
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
- Avoid: `:`, `/`, `\`, `?`, `*`, `|`, `<`, `>`, `"` (Windows incompatibility, shell pain points).
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
```

---

## Notes for `pka-bootstrap`

- This seed is written by `pka-bootstrap` during base bootstrap (Phase 3f) **and** as the first step of `bootstrap obsidian` / `bootstrap all` (so users on older base bootstraps get it backfilled).
- **Do not overwrite** if the file already exists in the target workspace — the user may have customized it. Skip silently and report "already present" in the summary.
- The seed has no placeholders, so no template substitution is required. Copy verbatim from the fenced block above.
- After seeding, the orchestrator/librarian/researcher role files reference this file by path: `.pka/roles/_obsidian.md`. Do not duplicate the conventions in the role files.
- This file is **inert** when `knowledge/.obsidian/` is absent — its presence in `.pka/roles/` is harmless until detection turns true.
