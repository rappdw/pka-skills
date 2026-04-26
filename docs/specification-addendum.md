---
title: pka-skills Addendum — Obsidian Coexistence & Hybrid Monorepo
version: 1.1
date: 2026-04-23
status: draft — for implementation
---

# pka-skills Addendum: Obsidian Coexistence & Hybrid Monorepo

## Purpose

Extend pka-skills along two parallel axes:

1. **Obsidian coexistence** — roles (orchestrator, librarian, researcher, developer) produce work that plays well with an Obsidian vault when one is present, without breaking anything when it isn't. **Progressive enhancement**: a user with no Obsidian vault sees identical behavior to today; a user with an Obsidian vault at `knowledge/` gets frontmatter-rich notes, `[[wikilinks]]`, and maintained MOC (Map of Content) landing pages for free.

2. **Hybrid monorepo bootstrap & git discipline** — the bootstrap skill can set up a `meta`-coordinated hybrid monorepo (root git repo, `knowledge/` child repo, per-project child repos, `.meta` manifest, LFS-configured templates), and roles follow a defined commit/push protocol as they operate so work is preserved with structured, reviewable history.

These two axes are independent: either bootstrap can be run without the other. The commit/push protocol applies regardless of Obsidian state.

## Non-goals

- No **semantic** bulk retrofitting of existing content. Conversion that requires reading a file's body and inferring meaning (attendees, related topics, backlinks) happens *only when a role touches a file*, never as a migration pass.
- No dependency on any Obsidian plugin. Everything works with just core Obsidian; plugins (Dataview, Templater, Periodic Notes) are user-enhancement, not skill-required.
- No change to how Claude invokes roles or to the @role syntax.
- Do not take any automated action to enable or disable Obsidian. That's the user's choice.
- No automatic bootstrap (either kind). Both the Obsidian mechanical retrofit and the git/meta setup are user-triggered, not detection-triggered.
- The git bootstrap does **not** create remote repos on Gitea/GitHub, set origin URLs to user-specific orgs, or push. Anything requiring credentials or a remote-topology decision remains a user operation.

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
- (Recommended, not required) the vault is in a clean git state so the user can review the resulting diff before committing.

**Idempotency**: Must be safe to re-run. Re-running on an already-bootstrapped vault should detect existing state and either skip or augment, never overwrite user-authored content.

**What the bootstrap does**:

1. **Create MOC stubs** for each top-level knowledge domain that doesn't already have one. Location: `<domain>/_MOC.md`. Content: a bulleted list of files and subfolders in that domain, as wikilinks. Alphabetical order. No thematic grouping — leave that for the user.

2. **Create person index stubs** at `personnel/<name>/index.md` for each `personnel/<name>/` subfolder that doesn't already have one. Frontmatter: `type: person`, `name: <Name>` (de-slugified from folder name — `alec-smith` becomes `Alec Smith`). Body: a "Notes" section listing existing files in the folder as wikilinks.

3. **Add filename-pattern frontmatter** to files matching known patterns that don't already have frontmatter:
   - `personnel/<person>/YYYY-MM-DD-1on1.md`, `*1-1*.md`, `*1on1*.md` → `type: 1on1`, `date` from filename, `person` as wikilink to person index, `tags: [1on1]`
   - `leadership/YYYY-MM-DD-*.md`, `TechCouncil/YYYY-MM-DD-*.md` → `type: meeting`, `date` from filename, `topic` from filename (slug-to-title), `tags: [meeting]`
   - `lab-notebook/YYYY-MM-DD.md` → `type: daily`, `date` from filename, `tags: [daily]`
   - Files whose immediate parent folder matches a known domain → add `tags: [<domain-tag>]` (e.g., files under `AI/azure/` get `tags: [ai, azure]`)

4. **Domain tags**: every file under a top-level knowledge domain gets at minimum one tag for its top-level folder (`ai`, `leadership`, `personnel`, `dan`, `techcouncil`, `lab-notebook`, etc.). If a file already has frontmatter, merge; don't overwrite existing tags.

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

The user is expected to review the resulting diff in git and commit (or reject) as a single reviewable changeset.

## Bootstrap phase: Git/meta hybrid monorepo

A separate one-time, user-triggered bootstrap that establishes the hybrid monorepo structure: a root `.git` coordinating independent child repos at `knowledge/` and each `projects/<name>/` via a `meta` manifest (`.meta` at root). Independent from Obsidian bootstrap — either can run without the other.

**Preconditions**:
- User has explicitly requested the bootstrap (e.g., "bootstrap git" or "initialize hybrid repo").
- The `git` and `git-lfs` binaries are available in the environment.
- No silent auto-run on session start or on any detection signal.

**Idempotency**: detects existing state and no-ops where appropriate. Safe to re-run.

**What the bootstrap does**:

1. **Install templates to `.pka/`** (if not present):
   - `.pka/gitattributes-template` — LFS filters for common binary types (video: mp4, mov, avi, mkv; audio: m4a; images: png, jpg, jpeg; office: pptx, docx, xlsx, xlsm; pdf; 3D: skp, x3d).
   - `.pka/gitignore-template` — OS noise (`.DS_Store`, `Thumbs.db`), Word/Office lock files (`~$*`), `.claude/`, `.vscode/`, `.idea/`.

2. **Install `.pka/` helper scripts** (if not present): `graduate.sh`, `init_project_repos.sh`, `reinit-project-with-lfs.sh`, `push-all.sh`, `build-repo-list.sh`.

3. **Root `.gitignore`**: create or augment root `.gitignore` to exclude child-repo content (`knowledge/`, `projects/`), inboxes (`owner-inbox/`, `team-inbox/`), caches and local artifacts (`.pka/knowledge.db*`, `.pka/*-log.txt`), and secrets (`.gitea-pat*`, `*.token`, `*.secret`).

4. **Root `.git`**: initialize root repository if absent. Stage files. **Do not auto-commit** — print a summary and hand off to the user for review/commit. (Root repo commits require human review; see "Commit/push protocol" below.)

5. **`knowledge/` child repo**: if `knowledge/.git` does not exist, initialize as a child repo, copy the gitattributes and gitignore templates, run `git lfs install --local`, and make an initial commit (`Initial commit`) in the child repo. The child-repo initial commit is mechanical and safe to auto-commit.

6. **`projects/*` child repos**: for each project lacking `.git`, run the init pattern from `init_project_repos.sh`: copy templates, `git init -b main`, `git lfs install --local`, initial commit. Does NOT set `origin` remotes (remote topology is a user decision) and does NOT push.

7. **`.meta` manifest**: generate `.meta` at the root listing every child repo discovered, with placeholder remote URLs (`""` or `"TBD"`) for child repos that have no origin set. Entries whose child repo has an existing `origin` are populated with that URL.

**What the bootstrap does NOT do**:

- Does not create repos on any remote host (Gitea, GitHub, etc.). Those require credentials and are user operations.
- Does not set `origin` remotes. The user decides remote topology (org name, host, naming scheme).
- Does not push.
- Does not reinit existing child repos. If a project already has `.git` but no LFS, the bootstrap flags it in the summary and suggests `reinit-project-with-lfs.sh` as a separate, destructive operation the user opts into explicitly.
- Does not commit the root repo. That is the user's first review gate.
- Does not modify files inside child repos beyond the initial scaffolding.

**Output**: bootstrap prints a summary:
- N templates installed / already present
- N scripts installed / already present
- Root repo: initialized (uncommitted, awaiting review) / already present
- `knowledge/`: initialized with LFS / already present
- N projects initialized with LFS
- N projects flagged (have `.git` but no LFS — reinit candidates, listed by path)
- `.meta` generated with N entries
- Root working-tree changes staged for user review (listed)

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

**Meeting note** (location: `leadership/` or `TechCouncil/` typically)
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
- Ambiguous link names are resolved by Obsidian's configured setting; prefer the full relative path `[[personnel/alec/index]]` over bare `[[alec]]` to avoid ambiguity.

When `obsidian_present` is false:

- Continue to use plain markdown links as today. Do not emit `[[wikilinks]]` — they render as literal text in non-Obsidian markdown viewers.

### MOC (Map of Content) files

Each top-level knowledge domain should have one MOC file at the domain root:

- `knowledge/_MOC.md` — vault root landing page
- `knowledge/AI/_MOC.md`
- `knowledge/personnel/_MOC.md`
- `knowledge/leadership/_MOC.md`
- `knowledge/dan/_MOC.md`
- `knowledge/TechCouncil/_MOC.md`
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

## Commit/push protocol

Roles operate continuously across a session, touching files in multiple repos. This protocol defines when they commit and when they push. Applies whether or not Obsidian is present — it's git hygiene, not Obsidian-specific. Activates only in a workspace that has been bootstrapped as a hybrid monorepo (root `.git` + child repos). In a single-repo or no-repo workspace, roles continue their pre-protocol behavior.

### Commit triggers

**Child repos** (`knowledge/`, `projects/*`): **auto-commit per semantic unit** after a role completes meaningful work.

- The "unit" is a coherent, reviewable change — not every file-write, but one commit per *thing accomplished*. The role decides the unit boundary.
- Examples:
  - Librarian routing a file into `knowledge/` → one commit after the route completes (including any MOC/frontmatter/backlink side-effects from the Obsidian behavior).
  - Researcher finalizing a brief → one commit when the brief is saved.
  - Obsidian bootstrap → one commit in `knowledge/` summarizing the batch.
  - Graduation → see "Graduation commit sequence" below.

**Root repo**: **no auto-commit.** Root repo changes (CLAUDE.md updates, `.meta` changes, new/updated `.pka/` scripts or templates, git bootstrap scaffolding) accumulate in the working tree. The role stages changes where obvious, lists them in the session summary, and hands off to the user for review and manual commit.

Rationale: the root is the system's own configuration. Its blast radius is larger than any single child repo, changes are rarer and more consequential, and a bad auto-commit there is harder to notice and unwind. Human review.

### Commit message structure

Commits carry a role prefix and a short description, followed by a Claude trailer:

```
<Role>: <short description>

<optional body>

Co-Authored-By: Claude <noreply@anthropic.com>
```

Examples:
- `Librarian: Route 2026-04-22-slt-meeting.md to leadership/`
- `Researcher: Add brief on Thoma Bravo AI adoption tier research`
- `Bootstrap (obsidian): 7 MOC stubs, 12 person indexes, 41 frontmatter additions`
- `Bootstrap (git): Initial hybrid monorepo setup` (in `knowledge/` and each new `projects/*` initial commit; root bootstrap scaffolding is staged, not committed)
- `Graduate: threat_actors → knowledge/reference/` (in `knowledge/`)

### Push triggers

**At session end**: consolidated auto-push via `meta git push` across all child repos that have unpushed commits. Runs as part of the session-end protocol.

**Mid-session on user request**: if the user says "push", "push now", or similar natural phrasing, push immediately across all child repos with unpushed commits.

**Root repo push**: pushed only after the user has committed it. The auto-push uses `meta git push` which operates on registered child repos; if the root is also tracked in the manifest (or by a separate command), it pushes only committed state — same gate as commit.

**Never silent failures**: any push failure (auth, conflict, network, LFS upload disconnect) surfaces explicitly in the session summary with the failing repo and error. Do not hide or silently retry.

### Graduation commit sequence

When a project is graduated from `projects/<name>/` to `knowledge/<subdir>/` via `graduate.sh`:

1. In `knowledge/` (child repo): auto-commit the new content with message `Graduate: <name> from projects/` (or `Graduate <name> from projects` to match existing script convention).
2. In root repo: `.meta` update removing `projects/<name>` is staged, **not committed**. Flagged in session summary for user review.
3. The old project repo on the remote (if any): graduation script prints instructions for archiving (e.g., Gitea API call). Role does not call remote APIs.

### Failure behavior

- **Commit failure** (merge conflict, pre-commit hook failure, unexpected working-tree state): surface to the user, pause further automatic commits in that repo, continue with other work. Do not force, amend, or retry destructively.
- **Push failure at session end**: record in session log and summary; continue (don't block session close). User can re-invoke push next session.
- **LFS-specific failures** (missing `git-lfs` binary, oversized object, remote-side disconnect mid-upload): surface with a remediation hint (e.g., install lfs, retry push — LFS uploads are resumable, prior objects are already on the server).

### Interaction with the Obsidian bootstrap

The Obsidian bootstrap produces changes inside `knowledge/` only. Under this protocol it is a single child-repo commit (`Bootstrap (obsidian): ...`), auto-committed per the child-repo rule above. The user reviews the diff in `knowledge/` before (or after) the session-end push.

## Lifecycle interactions

The `graduate.sh` script (root-level) moves a project from `projects/` to `knowledge/`. Once graduated, the project *is* inside the vault (when Obsidian is present).

- Graduated project content does not automatically get frontmatter — that's a retrofit task the librarian handles if/when it routes individual files later.
- The librarian SHOULD add the graduated project to `knowledge/_MOC.md` (or the relevant sub-MOC) as part of the graduate flow when `obsidian_present` is true.

## Session log

**No change** in this addendum. Session log remains at `.pka/session-log.md` as a single append-only file. This is a potential future extension (per-session files under `knowledge/_sessions/`) but is out of scope here.

## Tagging conventions

When `obsidian_present` is true and frontmatter tags are being written:

- Use lowercase, hyphenated tags: `ai-strategy`, not `AIStrategy` or `AI_Strategy`.
- Established tags: `daily`, `meeting`, `1on1`, `brief`, `person`, `research`.
- Domain tags: `ai`, `leadership`, `tech-council`, `personnel`, `projects` — match the top-level folder.
- Topic tags as needed: `strategy`, `mcp`, `satori`, `thoma-bravo`, etc.

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
9. **Person-match backlink**: librarian routes a meeting note mentioning "Alec" when `personnel/alec/index.md` exists. Assert: backlink added. When person index doesn't exist, assert no backlink attempted.
10. **Frontmatter on existing file**: librarian routes a file that already has frontmatter. Assert: existing frontmatter preserved; missing required fields added; extra fields left alone.
11. **Researcher brief emission**: researcher creates a new brief under vault. Assert: `type: brief` frontmatter present; `related` populated only when confidence is high; `tags` include domain tag.

### Git/meta bootstrap

12. **Git bootstrap, cold workspace**: fresh workspace with no `.git` anywhere, `knowledge/` folder with files but no `.git`, `projects/foo/` and `projects/bar/` with no `.git`. Run git bootstrap. Assert: `.pka/` templates and scripts installed; root `.gitignore` created; root `.git` initialized but no commit made; `knowledge/.git` and each project's `.git` initialized with LFS; `.meta` generated with entries for all three child repos; summary lists root working-tree changes staged for user review.

13. **Git bootstrap, idempotent**: run git bootstrap twice in sequence. Assert: second run is a no-op; no child repo is reinitialized; `.meta` is unchanged; no files are duplicated or overwritten.

14. **Git bootstrap, partial pre-existing**: workspace with root `.git` already present and `knowledge/.git` present, but `projects/newbie/` without `.git`. Run git bootstrap. Assert: root and `knowledge/` left alone; `projects/newbie/` initialized with LFS; `.meta` updated to include `projects/newbie`; summary reports what it did and didn't touch.

15. **Git bootstrap, LFS-missing project flagged**: workspace with `projects/legacy/` that has `.git` but no `.gitattributes` with LFS filters. Run git bootstrap. Assert: `projects/legacy/` is NOT modified; it appears in the summary as a reinit candidate with a pointer to `reinit-project-with-lfs.sh`.

16. **Git bootstrap does not create remotes or push**: run git bootstrap in a workspace with no network. Assert: completes successfully; no `origin` remotes set on child repos; no `curl` or push attempts made; `.meta` entries for new child repos have placeholder URLs.

### Commit/push protocol

17. **Child-repo auto-commit per unit**: librarian routes a file into `knowledge/`. Assert: exactly one commit created in `knowledge/`, message prefixed `Librarian:`, trailer includes `Co-Authored-By: Claude`. No commit in root repo.

18. **Root-repo no auto-commit**: role makes a change that touches `.meta` (e.g., graduation). Assert: `.meta` is modified and staged (or at least listed for review); no commit is made in the root repo; summary flags the change for user review.

19. **Session-end push**: complete a session with commits in `knowledge/` and one `projects/foo/`. At session close, assert: `meta git push` or equivalent is invoked, attempting to push both repos. If a remote isn't configured (placeholder `.meta` URL), surface that as a skipped push in the summary, not a failure.

20. **Push failure surfaces, doesn't block**: simulate a push failure in one child repo (e.g., unreachable origin). Assert: failure is listed in session summary with error detail; session close proceeds; other child repos are still pushed.

21. **User "push now" mid-session**: user says "push" partway through a session. Assert: push runs immediately against child repos with unpushed commits; returns a summary; session continues.

22. **Graduation commit sequence**: graduate `projects/widget/` to `knowledge/reference/widget/`. Assert: commit in `knowledge/` has message `Graduate: widget → knowledge/reference/` (or equivalent); root `.meta` change is staged but not committed; graduation script prints remote-archival instructions.

## Open questions for the implementer

1. **Should there be an explicit "disable Obsidian mode" override?** If a user has `knowledge/.obsidian/` but wants plain behavior for a session, is there a flag? Recommend: not in v1 — keep the detection boolean simple. Can add a `PKA_DISABLE_OBSIDIAN=1` env var later if demand exists.

2. **MOC structure specifics**: how deep does grouping go? Recommend: start flat (bullet list per file), let users reorganize manually. Auto-grouping by date or tag is future work.

3. **How does the orchestrator recognize the "bootstrap" request?** Free-form phrasing, a specific keyword, a slash-command? Implementer's call, but should be robust to natural phrasing ("let's bootstrap", "run the obsidian bootstrap", "bootstrap the vault", "bootstrap git", "initialize hybrid repo") rather than exact string matching.

4. **Single bootstrap command or two?** "bootstrap" could take a target (`bootstrap obsidian`, `bootstrap git`, `bootstrap all`), or the two could be separate commands. Recommend a single "bootstrap" skill with a target argument; defaults to prompting the user for which to run if ambiguous.

## Design decisions (locked in)

- **Commit/push protocol lives in its own shared-reference file**: `.pka/roles/_git-protocol.md`, sibling to `_obsidian.md`. Keeps `_obsidian.md` focused on Obsidian conventions; roles link to whichever shared file applies.

## Summary of file changes expected

In pka-skills repo:

### Obsidian coexistence

- `.pka/roles/orchestrator.md` — add session-start Obsidian detection, file-reference syntax note, "bootstrap obsidian" command handling
- `.pka/roles/librarian.md` — add routing behavior (frontmatter, MOC, backlinks) for ongoing lazy enhancement
- `.pka/roles/researcher.md` — add brief frontmatter emission
- `.pka/roles/developer.md` — no change
- New: `.pka/roles/_obsidian.md` — shared Obsidian conventions (detection predicate, frontmatter schemas, wikilink rules, MOC policy, tag conventions, filename rules, error handling). Referenced by the roles that need them to avoid repetition.

### Git/meta hybrid monorepo

- New: git-bootstrap logic. Location is the implementer's call — could be a dedicated role (`.pka/roles/_git-bootstrap.md`), a routine inside the orchestrator, or a standalone script invoked by the orchestrator. The spec requires only the behavior, not the structure.
- New: template files that the git bootstrap installs to `.pka/`: `gitattributes-template`, `gitignore-template`.
- New: helper scripts that the git bootstrap installs to `.pka/`: `graduate.sh`, `init_project_repos.sh`, `reinit-project-with-lfs.sh`, `push-all.sh`, `build-repo-list.sh`. These already exist in Dan's current workspace and can be vendored into the pka-skills repo as the installable artifacts.

### Commit/push protocol

- New: shared reference documenting the protocol (e.g., `.pka/roles/_git-protocol.md`) — see open question #4.
- `.pka/roles/orchestrator.md` — add session-end push behavior (`meta git push` or equivalent), surfacing of staged-but-uncommitted root changes in the session summary, handling of user "push" command mid-session.
- `.pka/roles/librarian.md` / `researcher.md` — add auto-commit-per-semantic-unit behavior in child repos, with structured commit messages per the spec. Do not auto-commit in the root repo.

### Bootstrap command unification

- Orchestrator "bootstrap" handler should support both targets (`obsidian`, `git`) — see open question #5.

### Tests

- Scenarios 1–11 for Obsidian behavior.
- Scenarios 12–16 for git bootstrap.
- Scenarios 17–22 for commit/push protocol.
