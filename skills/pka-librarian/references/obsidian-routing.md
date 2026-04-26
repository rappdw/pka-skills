# Obsidian-Aware Routing — Per-Route Checklist

Applies **only when** `obsidian_present` is true and the routing destination is **inside** `knowledge/`. Run after the file has been moved to its destination.

Conventions (frontmatter schemas, wikilink rules, MOC structure, malformed-frontmatter handling) live in `.pka/roles/_obsidian.md`. This document is the **operational checklist**; the conventions document is the **contract**. When they disagree, the conventions document wins.

## Per-route checklist

For each file routed into `knowledge/`:

### 1. Filename hygiene (always run, regardless of Obsidian)

- Replace `:` and `/` with `-` or ` `.
- Preserve spaces — Obsidian handles them; existing content uses them.
- Do not rename a file that's already at its destination unless the user asks.

### 2. Frontmatter merge

If the destination filename or folder matches a known type (meeting, 1on1, brief, daily, person), ensure schema fields are present in the frontmatter:

| Type    | Trigger                                                       | Required fields                                                                |
|---------|---------------------------------------------------------------|--------------------------------------------------------------------------------|
| 1on1    | path matches `personnel/<name>/YYYY-MM-DD-1on1.md`             | `type: 1on1`, `date`, `person: "[[personnel/<name>/index]]"`, `tags: [1on1]`   |
| meeting | path matches `leadership/YYYY-MM-DD-*.md` or `TechCouncil/YYYY-MM-DD-*.md` | `type: meeting`, `date`, `topic` (filename slug), `attendees: []`, `tags: [meeting, <domain>]` |
| brief   | created by @researcher, see `obsidian-routing` rules above     | `type: brief`, `date`, `related: []`, `tags: [research, <domain>]`              |
| daily   | path matches `lab-notebook/YYYY-MM-DD.md`                      | `date`, `tags: [daily]`                                                         |
| person  | path matches `personnel/<name>/index.md`                       | `type: person`, `name`, `role: ""`, `org: ""`, `tags: [person]`                 |

Merge rules:
- If frontmatter is **absent**: create it. Required fields with no high-confidence value get `""` or `[]`.
- If frontmatter is **present and parses as YAML**: add missing required fields; **leave existing fields untouched**, even if they look incomplete.
- If frontmatter is **present but malformed**: **skip the file**. Add it to the routing report's `malformed_frontmatter` list. Do not attempt repair.

Filename-derived values are safe (date, person from `personnel/<name>/`, domain tag from folder). Body-derived values (attendees beyond filename, topic beyond filename slug) require care — leave empty when not high-confidence.

### 3. Domain tag

Every file landing in a top-level `knowledge/` folder should carry a domain tag matching the folder. Examples:

| Destination folder | Domain tag       |
|--------------------|------------------|
| `knowledge/AI/`    | `ai`             |
| `knowledge/leadership/` | `leadership`     |
| `knowledge/personnel/<x>/` | `personnel` |
| `knowledge/lab-notebook/`  | `lab-notebook`  |
| `knowledge/TechCouncil/`   | `techcouncil`   |

Merge into the existing `tags:` list (don't overwrite). If `tags:` is absent, add `tags: [<domain-tag>]`.

### 4. MOC update

Append a bullet linking to the routed file in the destination domain's `_MOC.md`:

- If the MOC exists: locate the appropriate section (`## Files`, or thematic section if user has created one). If unsure, append to `## Files` or to a `## Unsorted` section at the bottom.
- If the MOC does not exist: create a stub matching the structure in `.pka/roles/_obsidian.md`.
- Never reorder existing entries.
- Never remove entries.

The bullet is a wikilink: `- [[<path-relative-to-vault>]]`.

### 5. Person backlinks (high-confidence only)

If the routed file's filename or **first-line title** clearly references a person (e.g., `2026-04-22-1-1-aarav.md`, or H1 = `1-1 with Aarav`), **and** `personnel/<that-person>/index.md` exists:

- Append a bullet to that person's `index.md` under `## Mentioned in` (create the section if absent).
- Bullet: `- [[<path-to-routed-file>]] (YYYY-MM-DD)`.

Confidence rules:
- High confidence: filename contains the personnel folder name as a token (split on `-` or `_`), or the filename matches a 1on1 pattern with that person.
- Low confidence: a name appears only in the body, or could match multiple personnel folders. **Do not link.**

Err strongly on the side of **not linking**. A missing backlink is a minor inconvenience; a wrong backlink is a real correctness issue.

### 6. Wikilink hygiene in the routed content (light touch)

This step is **optional and conservative**. The librarian routes — it is not a content-rewriter. But:

- If the routed content contains plain markdown links to **vault-internal** files (e.g., `[Alec](personnel/alec/index.md)`), and `obsidian_present` is true, those links would still work in Obsidian (markdown links are valid). Do not rewrite as a routing side-effect.
- New content the librarian generates (e.g., the `Mentioned in` bullets, MOC bullets) **must** use `[[wikilinks]]` for vault-internal references and plain markdown for vault-external references.

## Failure handling

Per `.pka/roles/_obsidian.md`'s error-handling rules: any per-step failure logs a warning and continues. The routing primary task (move + index) must complete even if MOC/frontmatter/backlink steps partially fail. Failures are surfaced in the routing report.

## What this checklist is NOT

- Not a bulk retrofit. The bulk retrofit is the Obsidian bootstrap (see `pka-bootstrap` skill, target `obsidian`). This per-route checklist runs lazily, one file at a time.
- Not a body-content reader. Frontmatter parsing is fine; body summarization, attendee inference from minutes, topic extraction beyond filename slug — all out of scope.
- Not a renamer. Filename hygiene applies to **incoming** filenames at routing time. Existing files at their destination keep their names.
