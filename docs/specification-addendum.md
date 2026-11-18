---
title: pka-skills Addendum — Obsidian Coexistence
version: 1.1
date: 2026-04-23
status: draft — for implementation
---

# pka-skills Addendum: Obsidian Coexistence

> **Amended after v1.7.0.** This addendum originally specified two things: Obsidian coexistence, and a "hybrid monorepo" (a root git repository coordinating separate repositories at `knowledge/` and each `projects/<name>/` through a `.meta` manifest) with a commit/push protocol for the roles. The second was implemented in v1.6.0 and **removed** after v1.7.0: pka-skills no longer sets that layout up, and no role or tool stages, commits or pushes. The sections that specified it ("Bootstrap phase: Git/meta hybrid monorepo", "Commit/push protocol", test scenarios 12 to 22) have been deleted from this document; they are in the repository's history up to the `v1.7.0` tag. What remains is the Obsidian half, which is current. Workspaces that already have the layout are left as they are: see `CHANGELOG.md` and "Workspaces with nested repositories" in `skills/pka-bootstrap/SKILL.md`.

## Purpose

Extend pka-skills so that it works alongside an Obsidian vault:

**Obsidian coexistence** — roles (orchestrator, librarian, researcher, developer) produce work that plays well with an Obsidian vault when one is present, without breaking anything when it isn't. **Progressive enhancement**: a user with no Obsidian vault sees identical behavior to today; a user with an Obsidian vault at `knowledge/` gets frontmatter-rich notes, `[[wikilinks]]`, and maintained MOC (Map of Content) landing pages for free.

## Non-goals

- No **semantic** bulk retrofitting of existing content. Conversion that requires reading a file's body and inferring meaning (attendees, related topics, backlinks) happens *only when a role touches a file*, never as a migration pass.
- No dependency on any Obsidian plugin. Everything works with just core Obsidian; plugins (Dataview, Templater, Periodic Notes) are user-enhancement, not skill-required.
- No change to how Claude invokes roles or to the @role syntax.
- Do not take any automated action to enable or disable Obsidian. That's the user's choice.
- No automatic bootstrap. The Obsidian mechanical retrofit is user-triggered, not detection-triggered.
- No git. Nothing is staged, committed or pushed for the user; whether the workspace is in a repository, and when to commit, is theirs.

## Retrofit strategy: eager mechanical, lazy semantic

Without any retrofit, a freshly-opened vault looks empty: graph mostly disconnected, Dataview queries return nothing, MOCs don't exist. Users feel no value from Obsidian for months. Pure lazy retrofit is too slow.

Without *any* restraint, a bulk retrofit pass guesses wrong a lot (wrong attendees, hallucinated topic links) across hundreds of files, producing a large changeset that's hard to review.

The split:

- **Eager (mechanical)**: things derivable from filename and folder structure alone. No content inference. Runs once as an explicit bootstrap phase (see below).
- **Lazy (semantic)**: things requiring content reading or inference. Happens only when a role touches a file during normal operation.

## Bootstrap phase: Obsidian mechanical retrofit

A one-time, user-triggered pass that does the mechanical retrofit of an Obsidian vault. Not automatic; does not run on Obsidian detection. The user invokes it explicitly, e.g., via an orchestrator command such as "bootstrap obsidian".

**Preconditions**:
- `obsidian_present` is true.
- User has explicitly requested bootstrap.
- (Recommended, not required) if the vault is in a git repository, it is in a clean state so the user can review the resulting diff before committing.

**Idempotency**: Must be safe to re-run. Re-running on an already-bootstrapped vault should detect existing state and either skip or augment, never overwrite user-authored content.

**What the bootstrap does**:

1. **Create MOC stubs** for each top-level knowledge domain that doesn't already have one. Location: `<domain>/_MOC.md`. Content: a bulleted list of files and subfolders in that domain, as wikilinks. Alphabetical order. No thematic grouping — leave that for the user.

2. **Create person index stubs** at `personnel/<name>/index.md` for each `personnel/<name>/` subfolder that doesn't already have one. Frontmatter: `type: person`, `name: <Name>` (de-slugified from folder name — `robin-smith` becomes `Robin Smith`). Body: a "Notes" section listing existing files in the folder as wikilinks.

3. **Add filename-pattern frontmatter** to files matching known patterns that don't already have frontmatter:
   - `personnel/<person>/YYYY-MM-DD-1on1.md`, `*1-1*.md`, `*1on1*.md` → `type: 1on1`, `date` from filename, `person` as wikilink to person index, `tags: [1on1]`
   - `leadership/YYYY-MM-DD-*.md`, `ArchCouncil/YYYY-MM-DD-*.md` → `type: meeting`, `date` from filename, `topic` from filename (slug-to-title), `tags: [meeting]`
   - `lab-notebook/YYYY-MM-DD.md` → `type: daily`, `date` from filename, `tags: [daily]`
   - Files whose immediate parent folder matches a known domain → add `tags: [<domain-tag>]` (e.g., files under `AI/azure/` get `tags: [ai, azure]`)

4. **Domain tags**: every file under a top-level knowledge domain gets at minimum one tag for its top-level folder (`ai`, `leadership`, `personnel`, `owner`, `archcouncil`, `lab-notebook`, etc.). If a file already has frontmatter, merge; don't overwrite existing tags.

**What the bootstrap does NOT do**:

- Does not read file bodies.
- Does not infer attendees, topics (beyond filename-slug), related notes, or backlinks.
- Does not reorganize MOC stubs thematically.
- Does not modify filenames.
- Does not modify or touch files outside `knowledge/`.
- Does not touch files whose frontmatter is malformed — flags them for user review in the bootstrap summary.

**Output**: bootstrap prints a summary before finishing:
- N MOC stubs created
- N person indexes created
- N files given frontmatter
- N files with malformed existing frontmatter (skipped, listed by path)
- Total files touched

The bootstrap commits nothing. A user who keeps the vault in git reviews the resulting diff and commits (or rejects) it as a single reviewable changeset.

## Ongoing (post-bootstrap) behavior

After bootstrap, the per-role changes described below apply. These are the lazy/semantic enhancements that happen when roles touch files during normal work.

## Detection

Claude is always invoked at the pka workspace root (where `CLAUDE.md` lives). Detection therefore uses a relative path:

```
obsidian_present := directory_exists("./knowledge/.obsidian")
```

Evaluate once at session start, cache for the session.

- If true, the vault is `knowledge/` and Obsidian-enhanced behaviors activate.
- If false, all Obsidian-specific behaviors are skipped; current behavior is preserved.

Do not probe any other path. The vault location is fixed by convention at `knowledge/`. If a user wants the vault elsewhere, that's a future extension — flag it and leave as out-of-scope for this addendum.

The detection result should be surfaced in the orchestrator's session-start greeting when true (e.g., "Obsidian vault detected at knowledge/") so the user can confirm. Silent behavior change is a footgun.

## Data conventions

These conventions apply **only when `obsidian_present` is true**. When false, roles continue to produce plain markdown without frontmatter as they do today.

### Frontmatter schemas

Files created or touched by roles should carry frontmatter when they match one of these types. Frontmatter is YAML, enclosed in `---` fences, first lines of the file.

**Daily note** (location: `lab-notebook/YYYY-MM-DD.md`)
```yaml
---
date: YYYY-MM-DD
tags: [daily]
---
```

**Meeting note** (location: `leadership/` or `ArchCouncil/` typically)
```yaml
---
type: meeting
date: YYYY-MM-DD
topic: <short slug>
attendees: ["[[firstname]]", "[[firstname]]"]
tags: [meeting, <domain-tag>]
---
```

**1-on-1 note** (location: `personnel/<person>/YYYY-MM-DD-1on1.md`)
```yaml
---
type: 1on1
date: YYYY-MM-DD
person: "[[personnel/<person>/index]]"
tags: [1on1]
---
```

**Research brief** (location: varies, typically under a topic folder in `AI/` or `leadership/`)
```yaml
---
type: brief
date: YYYY-MM-DD
related: ["[[...]]", "[[...]]"]
tags: [research, <domain-tag>]
---
```

**Person index** (location: `personnel/<person>/index.md`)
```yaml
---
type: person
name: <full name>
role: <role/title>
org: <org>
tags: [person]
---
```

Unknown frontmatter fields are safe — Obsidian ignores them. So adding project-specific fields is fine; removing these schema-required ones is not.

### Wikilink syntax

When `obsidian_present` is true:

- Cross-references **within the vault** (`knowledge/`) should use `[[wikilinks]]`.
- Links to files **outside the vault** (projects/, root, inboxes) should remain plain markdown: `[text](relative/path)`.
- Display-text form is `[[target|display]]` when the target path isn't what you want shown.
- Ambiguous link names are resolved by Obsidian's configured setting; prefer the full relative path `[[personnel/robin/index]]` over bare `[[robin]]` to avoid ambiguity.

When `obsidian_present` is false:

- Continue to use plain markdown links as today. Do not emit `[[wikilinks]]` — they render as literal text in non-Obsidian markdown viewers.

### MOC (Map of Content) files

Each top-level knowledge domain should have one MOC file at the domain root:

- `knowledge/_MOC.md` — vault root landing page
- `knowledge/AI/_MOC.md`
- `knowledge/personnel/_MOC.md`
- `knowledge/leadership/_MOC.md`
- `knowledge/owner/_MOC.md`
- `knowledge/ArchCouncil/_MOC.md`
- `knowledge/lab-notebook/_MOC.md`

MOC filename is `_MOC.md` with underscore prefix so it sorts to the top of the folder listing. Structure: grouped bullet lists of wikilinks to constituent files/subfolders.

**Creation policy:**

- MOC files are created lazily. When a role first touches content in a domain under Obsidian, if no `_MOC.md` exists for that domain, the role creates a minimal stub and adds a link to the file it's working on.
- Roles update the relevant `_MOC.md` when adding new content to a domain.
- MOCs are not authoritative — they're navigation aids. If an MOC diverges from the folder contents, the folder contents win.

## Per-role changes

### Orchestrator

**Session start**:
- Include `obsidian_present` detection in the existing session-start protocol.
- If true, add one line to the greeting: "Obsidian vault detected — skills running in Obsidian-coexistence mode."

**File references in responses**:
- When referring to a file in `knowledge/`, prefer `[[path/to/file]]` syntax when `obsidian_present` is true. (Users with Obsidian get clickable links; the reference is still human-readable plain text either way.)
- When referring to files outside `knowledge/`, continue to use `file_path:line_number` format as today.

**Repo Map**:
- The Repo Map table in root `CLAUDE.md` remains plain markdown (it's the global navigation that every session reads — must render cleanly for Claude itself). No change.
- The *knowledge-specific* Repo Map content can additionally be reflected in `knowledge/_MOC.md` when `obsidian_present` is true, but this is not a hard requirement.

### Librarian

**When routing a file into knowledge/** (with `obsidian_present` true):

1. **Filename hygiene** (do this regardless of Obsidian):
   - Replace `:` and `/` in filenames with `-` or ` `.
   - Preserve spaces where they exist — Obsidian handles them, and filenames like "2026-Needle Movers" are established content.
   - Do not change existing filenames unless explicitly asked.

2. **Ensure frontmatter is present** if the file matches a known type (meeting, 1on1, brief, daily). Generate with best-effort values extracted from the content or filename; leave fields empty (`[]` or `""`) rather than inventing.

3. **Update the destination domain's `_MOC.md`**:
   - If it doesn't exist, create a stub.
   - Add a bullet linking to the new file under the appropriate section, or at the end if no section fits.

4. **Add backlinks where obvious**:
   - If the routed content mentions a person with a `personnel/<person>/index.md` page, add a bullet to that person's page under an "Mentioned in" or "Related meetings" section.
   - If the content references a project (name match against `projects/`), note it in the MOC but don't attempt to link into the project directory (vault-external).
   - Err on the side of NOT linking when ambiguous — rogue backlinks are worse than missing ones.

**When routing a file with `obsidian_present` false**:

- Current behavior only. No frontmatter added, no MOC updated, no backlinks.

### Researcher

**When creating a new research brief** (with `obsidian_present` true):

- Include the `type: brief` frontmatter schema (see above).
- Populate `related:` with links to prior briefs on adjacent topics that the researcher has seen in the current session or discovered during research. If none found, leave as `related: []`.
- Populate `tags:` with the domain hashtag (e.g., `research, ai-strategy`).

**When creating a brief with `obsidian_present` false**:

- No frontmatter. Current behavior only.

### Developer

No changes. Developer operates in `projects/` which is outside the vault. Even if `obsidian_present` is true, developer continues to use plain markdown and standard code-project conventions.

## Lifecycle interactions

The transition workflow moves a finished project from `projects/` to `knowledge/` and rewrites the links that pointed at it (`pka-tools pointers rename … --prefix --notes`). Once graduated, the project *is* inside the vault (when Obsidian is present).

- Graduated project content does not automatically get frontmatter — that's a retrofit task the librarian handles if/when it routes individual files later.
- The librarian SHOULD add the graduated project to `knowledge/_MOC.md` (or the relevant sub-MOC) as part of the graduate flow when `obsidian_present` is true.

## Session log

**No change** in this addendum. Session log remains at `.pka/session-log.md` as a single append-only file. This is a potential future extension (per-session files under `knowledge/_sessions/`) but is out of scope here.

## Tagging conventions

When `obsidian_present` is true and frontmatter tags are being written:

- Use lowercase, hyphenated tags: `ai-strategy`, not `AIStrategy` or `AI_Strategy`.
- Established tags: `daily`, `meeting`, `1on1`, `brief`, `person`, `research`.
- Domain tags: `ai`, `leadership`, `arch-council`, `personnel`, `projects` — match the top-level folder.
- Topic tags as needed: `strategy`, `mcp`, `orion`, `meridian`, etc.

Tag hygiene is not strict — duplicates and case variations won't break anything, just make Tag panel in Obsidian messier. Roles should aim for consistency but not block on it.

## Filename conventions

Apply regardless of Obsidian state (these are existing good practice):

- Dates in filenames: `YYYY-MM-DD-<topic>.md`.
- Spaces allowed but prefer hyphens in new filenames.
- Avoid: `:`, `/`, `\`, `?`, `*`, `|`, `<`, `>`, `"` (some break on Windows, all break in shells).
- Underscores vs hyphens: no strong preference; follow sibling-file convention in the target folder.

## Error handling

- If Obsidian-specific behavior fails (e.g., can't write to `_MOC.md` due to permissions, malformed existing frontmatter prevents parse), the role must **not** block the primary task. Log a warning, complete the primary work, surface the warning in the summary to the user.
- If detection is ambiguous (e.g., `.obsidian/` exists but is empty), treat as `obsidian_present = true` and proceed. An empty vault config is a valid state (fresh install).

## Testing

### Detection and gating

1. **No vault**: create a fake workspace without `knowledge/.obsidian/`. Invoke librarian routing a meeting note. Assert: no frontmatter added, no MOC created, file placed correctly.
2. **Vault present, no request**: create `knowledge/.obsidian/` but do not invoke bootstrap. Invoke librarian routing a new file. Assert: ongoing-behavior enhancements apply (frontmatter on new file, MOC updated if exists), but no bootstrap-scale changes to other files.

### Bootstrap

3. **Bootstrap, cold vault**: vault with 50 varied files, no MOCs, no person indexes, no frontmatter. Run bootstrap. Assert: all mechanical retrofits applied per spec; filename-pattern matches have correct frontmatter; domains all have MOC stubs; persons all have index.md stubs; no file bodies were read beyond what's required.
4. **Bootstrap, idempotent**: run bootstrap twice in sequence. Assert: second run is a no-op (no new changes). Any augmentation on re-run is additive, never overwriting.
5. **Bootstrap, partial pre-existing**: vault with some MOCs and some person indexes already authored by the user. Run bootstrap. Assert: existing files not modified; missing ones created.
6. **Bootstrap, malformed frontmatter**: seed a file with broken YAML frontmatter (e.g., unquoted colon). Run bootstrap. Assert: file is listed in the skipped-for-review summary; file is NOT modified.

### Ongoing per-role behavior

7. **Vault present, existing MOC**: pre-seed `_MOC.md` with entries. Librarian routes a new file into that domain. Assert: new entry added without disturbing existing entries.
8. **Mixed vault+non-vault references**: role producing a response that references both `knowledge/AI/foo.md` and `projects/bar/baz.md`. Assert: former uses `[[...]]`, latter uses plain markdown link.
9. **Person-match backlink**: librarian routes a meeting note mentioning "Robin" when `personnel/robin/index.md` exists. Assert: backlink added. When person index doesn't exist, assert no backlink attempted.
10. **Frontmatter on existing file**: librarian routes a file that already has frontmatter. Assert: existing frontmatter preserved; missing required fields added; extra fields left alone.
11. **Researcher brief emission**: researcher creates a new brief under vault. Assert: `type: brief` frontmatter present; `related` populated only when confidence is high; `tags` include domain tag.

Scenarios 12 to 22 (git bootstrap, commit/push protocol) were removed with the feature.

## Open questions for the implementer

1. **Should there be an explicit "disable Obsidian mode" override?** If a user has `knowledge/.obsidian/` but wants plain behavior for a session, is there a flag? Recommend: not in v1 — keep the detection boolean simple. Can add a `PKA_DISABLE_OBSIDIAN=1` env var later if demand exists.

2. **MOC structure specifics**: how deep does grouping go? Recommend: start flat (bullet list per file), let users reorganize manually. Auto-grouping by date or tag is future work.

3. **How does the orchestrator recognize the "bootstrap" request?** Free-form phrasing, a specific keyword, a slash-command? Implementer's call, but should be robust to natural phrasing ("let's bootstrap", "run the obsidian bootstrap", "bootstrap the vault") rather than exact string matching.

4. **Single bootstrap command or two?** "bootstrap" could take a target (`bootstrap obsidian`, `bootstrap upgrade`, `bootstrap all`), or these could be separate commands. Recommend a single "bootstrap" skill with a target argument; defaults to prompting the user for which to run if ambiguous.

## Design decisions (locked in)

- **Obsidian conventions live in one shared-reference file**: `.pka/roles/_obsidian.md`. Roles link to it rather than repeating the rules.
- **No git** (decided after v1.7.0): the commit/push protocol and its shared reference `.pka/roles/_git-protocol.md` were removed.

## Summary of file changes expected

In pka-skills repo:

### Obsidian coexistence

- `.pka/roles/orchestrator.md` — add session-start Obsidian detection, file-reference syntax note, "bootstrap obsidian" command handling
- `.pka/roles/librarian.md` — add routing behavior (frontmatter, MOC, backlinks) for ongoing lazy enhancement
- `.pka/roles/researcher.md` — add brief frontmatter emission
- `.pka/roles/developer.md` — no change
- New: `.pka/roles/_obsidian.md` — shared Obsidian conventions (detection predicate, frontmatter schemas, wikilink rules, MOC policy, tag conventions, filename rules, error handling). Referenced by the roles that need them to avoid repetition.

### Bootstrap command unification

- Orchestrator "bootstrap" handler takes a target (`obsidian`, `upgrade`, `all`) — see open question #4.

### Tests

- Scenarios 1–11 for Obsidian behavior.
