# Obsidian-Aware Routing — Per-Route Checklist

Applies **only when** `obsidian_present` is true and the routing destination is **inside** `knowledge/`. Run after the file has been moved to its destination.

**Steps 2, 3 and 4 are carried out by `.pka/bin/pka-tools post-route <file>`** (see the librarian's step 5). They are described here so you know what it does and what to expect in its output; do not perform them by hand. Steps 1, 5 and 6 are yours.

Conventions (frontmatter schemas, wikilink rules, MOC structure, malformed-frontmatter handling) live in `.pka/roles/_obsidian.md`. This document is the **operational checklist**; the conventions document is the **contract**. When they disagree, the conventions document wins.

## Per-route checklist

For each file routed into `knowledge/`:

### 1. Filename hygiene (always run, regardless of Obsidian)

- Replace `:` and `/` with `-` or ` `.
- Preserve spaces — Obsidian handles them; existing content uses them.
- Do not rename a file that's already at its destination unless the user asks.

### 2. Frontmatter merge (done by `post-route`)

If the note's name and folder match a known kind, the schema fields are added when missing. Which folder plays which role comes from the Repo Map tags:

| Repo Map tag | Folder role | Fallback when no folder carries the tag |
|---|---|---|
| `people-home` | one subfolder per person | `knowledge/personnel/` |
| `meeting-home` | dated meeting notes (several folders may carry it) | `knowledge/leadership/`, `knowledge/ArchCouncil/` |
| `daily-home` | daily notes | `knowledge/lab-notebook/` |

| Kind | Trigger | Fields written when missing |
|---|---|---|
| 1on1 | `<people-home>/<person>/YYYY-MM-DD-<1-1 marker>[-<anything>].md` | `type: 1on1`, `date`, `person: "[[<people-home>/<person>/index]]"`, `tags: [1on1, <domain>]` |
| meeting | `<meeting-home>/YYYY-MM-DD-<topic>.md` | `type: meeting`, `date`, `topic` (the rest of the filename), `attendees: []`, `tags: [meeting, <domain>]` |
| daily | `<daily-home>/YYYY-MM-DD.md` | `date`, `tags: [daily, <domain>]` |
| any other note in a top-level folder | — | `tags: [<domain>]` |
| brief | written by @researcher | the researcher writes these itself (`type: brief`, `date`, `related`, `tags: [research, <domain>]`); `post-route` adds only the domain tag if missing |
| person | `<people-home>/<person>/index.md` | created by `bootstrap obsidian` only |

**1-1 filenames.** Existing notes use several forms and are never renamed. The 1-1 marker is any of `1on1`, `1-1` or `1-on-1`, in any case, optionally followed by more of the name: `2026-03-31-1on1.md`, `2026-03-31-1-1.md`, `2026-03-31-1-1-priya.md` and `2026-03-31-1-on-1-priya-roadmap.md` are all 1-1 notes. **New** 1-1 notes are written as `YYYY-MM-DD-1-1-<person-slug>.md` (`pka-meetings` does this), because a name in the filename keeps the note findable outside its folder.

Merge rules (the tool keeps to them):
- Frontmatter **absent**: a block is added above the content, which is otherwise left byte for byte.
- Frontmatter **present and readable**: missing keys are inserted as new lines; existing lines are never changed. The one exception is `tags:`, which gains the domain tag.
- Frontmatter **present but unreadable** (or the file is not UTF-8, is read-only, or uses bare carriage returns): the file is skipped and the reason is in the output. Put it in the routing report's malformed-frontmatter list. Do not repair it.

Filename-derived values are the only ones the tool writes. Body-derived values (attendees, a topic beyond the filename, related notes) are yours to add afterwards, and only when confidence is high.

### 3. Domain tag (done by `post-route`)

The domain tag is the top-level folder's name in lower case with spaces and underscores as hyphens:

| Destination folder | Domain tag       |
|--------------------|------------------|
| `knowledge/AI/`    | `ai`             |
| `knowledge/leadership/` | `leadership`     |
| `knowledge/personnel/<x>/` | `personnel` |
| `knowledge/lab-notebook/`  | `lab-notebook`  |
| `knowledge/ArchCouncil/`   | `archcouncil`   |

It is added to a flow list (`tags: [a, b]`) or a block list (`- a` lines). A `tags:` value in any other form is left alone and reported.

### 4. MOC update (done by `post-route`)

A `- [[<vault-relative path>]]` bullet goes into the nearest `_MOC.md`: the note's own folder if it has one, else the nearest parent up to the top-level folder, else a new stub in the top-level folder.

- It is added at the end of `## Files`, or under a `## Unsorted` section appended to the file. When the user keeps thematic sections and the right one is obvious, pass `--section "<heading>"` to `post-route`.
- A note already linked anywhere in the MOC's text gets no second bullet. (A link inside the Pointers table, a fenced example or inline code does not count.)
- Existing entries are never reordered or removed.

### 5. Person backlinks (high-confidence only, yours)

If the routed file's filename or **first-line title** clearly references a person (e.g., `2026-04-22-1-1-priya.md`, or H1 = `1-1 with Priya`), **and** `personnel/<that-person>/index.md` exists:

- Append a bullet to that person's `index.md` under `## Mentioned in` (create the section if absent).
- Bullet: `- [[<path-to-routed-file>]] (YYYY-MM-DD)`.

Confidence rules:
- High confidence: filename contains the personnel folder name as a token (split on `-` or `_`), or the filename matches a 1on1 pattern with that person.
- Low confidence: a name appears only in the body, or could match multiple personnel folders. **Do not link.**

Err strongly on the side of **not linking**. A missing backlink is a minor inconvenience; a wrong backlink is a real correctness issue.

### 6. Wikilink hygiene in the routed content (light touch)

This step is **optional and conservative**. The librarian routes — it is not a content-rewriter. But:

- If the routed content contains plain markdown links to **vault-internal** files (e.g., `[Robin](personnel/robin/index.md)`), and `obsidian_present` is true, those links would still work in Obsidian (markdown links are valid). Do not rewrite as a routing side-effect.
- New content the librarian generates (e.g., the `Mentioned in` bullets, MOC bullets) **must** use `[[wikilinks]]` for vault-internal references and plain markdown for vault-external references.

## Failure handling

Per `.pka/roles/_obsidian.md`'s error-handling rules: any per-step failure logs a warning and continues. The routing primary task (move + index) must complete even if MOC/frontmatter/backlink steps partially fail. Failures are surfaced in the routing report.

## What this checklist is NOT

- Not a bulk retrofit. The bulk retrofit is the Obsidian bootstrap (see `pka-bootstrap` skill, target `obsidian`). This per-route checklist runs lazily, one file at a time.
- Not a body-content reader. Frontmatter parsing is fine; body summarization, attendee inference from minutes, topic extraction beyond filename slug — all out of scope.
- Not a renamer. Filename hygiene applies to **incoming** filenames at routing time. Existing files at their destination keep their names.
