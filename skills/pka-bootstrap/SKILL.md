---
name: pka-bootstrap
description: >
  ALWAYS use this skill when the user mentions PKA, personal knowledge, repo map,
  knowledge base setup, replacing Obsidian/Notion/Tana/Heptabase, organizing
  notes and files into a unified system, adding roles to their AI team, project
  lifecycle management, transitioning or archiving projects, restoring archived
  projects, checking which projects are stale or winding down, bootstrapping
  any kind of personal knowledge assistant, OR setting up Obsidian coexistence,
  OR upgrading an existing workspace. Triggers also include: "bootstrap obsidian",
  "bootstrap vault", "MOC stubs", "frontmatter retrofit", "bootstrap upgrade",
  "bootstrap all", "bootstrap everything". This skill handles first-run setup (scanning folders, inferring
  structure, writing CLAUDE.md, creating SQLite indexes, defining roles) AND
  ongoing management (updating the repo map, adding team roles, transitioning
  completed projects to a knowledge archive, checking project activity) AND
  the additive Obsidian bootstrap and the upgrade (idempotent, user-triggered,
  never auto-run). It never runs git: nothing is committed or pushed. Use it even if the user doesn't say "PKA" explicitly — if
  they want to unify scattered notes, set up AI-powered file organization, or
  manage workspace lifecycle, this is the right skill.
user-invocable: true
argument-hint: "[command or context]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# pka-bootstrap

First-run setup and ongoing management for a Personal Knowledge Assistance system.

## Purpose

Everything related to PKA setup and management:
- First-run bootstrap (fresh or existing structure)
- Inferring and maintaining the Repo Map
- Initializing and managing SQLite
- Defining and extending the role team
- Managing project lifecycle (active → archiving → archived → restored)

## Trigger Phrases

- "Set up my PKA / personal knowledge system"
- "Bootstrap my AI assistant in this folder"
- "Initialize PKA here"
- "I want to replace Obsidian / Notion / Tana / Heptabase"
- "Add a new role / capability to my team"
- "Update my repo map"
- "Transition `<project>` to knowledge"
- "Archive `<project>`"
- "Restore `<project>` to active"
- "What projects are winding down?"
- "Bootstrap obsidian / the vault / the MOCs"
- "Bootstrap all / bootstrap everything"
- Any mention of "personal knowledge assistance", "PKA", "repo map", "CLAUDE.md orchestrator"

---

## Bootstrap targets

`pka-bootstrap` is a single skill that handles several independent bootstrap procedures. The user picks one (or `all`):

| Target     | What it does                                                                                  | Idempotent? | Reference                              |
|------------|-----------------------------------------------------------------------------------------------|-------------|-----------------------------------------|
| (default)  | Original PKA setup: Repo Map, `.pka/`, roles, SQLite, `CLAUDE.md`. Phase 1–3 below.            | Yes         | This document                          |
| `obsidian` | One-time mechanical retrofit of an Obsidian vault at `knowledge/`: MOC stubs, person indexes, filename-pattern frontmatter, domain tags. | Yes | `references/obsidian-bootstrap.md`     |
| `upgrade`  | For a workspace already bootstrapped on an earlier version of pka-skills: backs up `.pka/roles/`, seeds the shared-reference file `_obsidian.md` if missing, structured-merges new H2 sections into existing role files, and reports sections left over from removed features. Never overwrites user customizations. | Yes | `references/upgrade.md`                |
| `all`      | Run `upgrade` if a previous bootstrap exists, else base PKA setup; then `obsidian` if `knowledge/.obsidian/` exists. | Yes         | All three references                   |

**Resolution rules** (the orchestrator dispatches; this skill is the executor):

| Phrasing the user used                                       | Target     |
|--------------------------------------------------------------|------------|
| "bootstrap obsidian", "bootstrap the vault", "moc stubs", "frontmatter retrofit" | `obsidian` |
| "upgrade", "upgrade my pka", "bootstrap upgrade", "update my role files", "refresh the addendum behavior" | `upgrade`  |
| "bootstrap all", "bootstrap everything", or all vocabularies appear              | `all`      |
| Generic "bootstrap" without a target qualifier                                  | base PKA setup (existing behavior) |

If the orchestrator can't tell, it asks the user before delegating here.

**"Bootstrap git", "the hybrid repo", "the meta monorepo"**: that target was removed. Earlier releases could set a workspace up as a root repository coordinating separate repositories at `knowledge/` and each `projects/<name>/`, and committed into them after every route. pka-skills no longer creates that layout, commits or pushes. Say so, and that a workspace lives in one ordinary repository (or none) which the user commits themselves. A workspace that already has the layout keeps working; see "Workspaces with nested repositories" below.

**Hard rules across all targets**:

- Bootstraps run **only on explicit user request**. Detection (e.g., finding `knowledge/.obsidian/`) is **not** a trigger.
- Bootstraps are **idempotent**. Re-running on an already-bootstrapped state produces no further changes.
- No bootstrap runs git. Nothing is initialised, staged, committed or pushed; whatever a bootstrap changes is left in the working tree for the user to review and commit.
- The `obsidian` bootstrap **fails soft** — non-critical errors log and continue; the primary task isn't blocked.

---

## Phase 1: Pre-Flight Scan

Runs before any user interaction or file modification.

### Step 1 — Detect situation

Walk up from cwd checking for `.pka/` directories:

```python
def find_pka_root(cwd):
    path = cwd
    while path != os.path.dirname(path):
        if os.path.exists(os.path.join(path, '.pka')):
            return path
        path = os.path.dirname(path)
    return None

pka_root = find_pka_root(os.getcwd())
has_local_pka  = os.path.exists('.pka/')
has_local_cmd  = os.path.exists('CLAUDE.md')
```

| Signals | Situation | Action |
|---------|-----------|--------|
| No `.pka/`, no `CLAUDE.md` | Fresh setup | Full bootstrap |
| Folders present, no `.pka/`, no `CLAUDE.md` | Existing structure | Adapt bootstrap — infer, add infrastructure, don't move content |
| `.pka/` exists but no `CLAUDE.md` | Partial/interrupted bootstrap | Resume: write `CLAUDE.md`, skip already-created infrastructure |
| `CLAUDE.md` exists but no `.pka/` | CLAUDE.md without PKA infrastructure | Ask: "I see a CLAUDE.md but no PKA infrastructure. Treat as an existing PKA and add `.pka/`, or is this an unrelated CLAUDE.md?" |
| `.pka/` and `CLAUDE.md` both exist | Already bootstrapped | Update mode — refresh map, extend roles, or lifecycle command |
| `pka_root` found and `pka_root != cwd` | Inside a project workspace | Refuse. Say: "You're inside a project workspace under `<pka_root>`. Run PKA bootstrap from `<pka_root>` to manage the full system." |

### Step 2 — Load or generate `.pkaignore`

If `.pkaignore` exists at root, load it. If not, write the default (see `references/pkaignore-defaults.md`). Always load before scanning.

### Step 3 — Structural scan (noise-filtered)

Walk the directory applying `.pkaignore`. For each top-level folder, collect:
- Folder name
- Count of immediate children that are **files** vs. **subdirectories**
- If subfolder-organized: list of subfolder names (up to 10)
- If flat: sample of up to 10 filenames
- Dominant file extension(s)
- Presence of `CLAUDE.md` → project workspace signal
- Presence of `project-summary.md` → transitioned project signal
- Presence of `Cargo.toml`, `package.json`, `go.mod`, `pyproject.toml` at root → code-primary project; index top-level markdown only
- Presence of date-slug named files (e.g., `2026-03-15-1-1-priya.md`) → **meeting notes home signal** (used by `pka-meetings` for routing)
- Presence of subfolders each containing `wiki.md` → **topic wiki home signal** (used by `pka-wiki` for synthesis)

The flat vs. subfolder-organized distinction is critical for inference quality — a folder of 30 subfolders named after people is personnel notes; a flat folder of 30 date-named `.md` files is a journal or meeting log.

### Step 4 — Infer Repo Map

For each folder, infer using `references/inference-guide.md`:
- **What it contains** — one plain-language sentence
- **How it's organized** — by person, date, topic, flat, etc.
- **Priority** — Active / Reference / Archive
- **Meeting tag** — `meeting-home` if the folder contains date-slug meeting files; multiple folders can be tagged
- **People tag** — `people-home` on the one folder whose subfolders are people (see `references/inference-guide.md`)
- **Daily tag** — `daily-home` if the folder's notes are named `YYYY-MM-DD.md`
- **Wiki tag** — `wiki-home` if the folder contains subfolders each with `wiki.md`; multiple folders can be tagged
- **Archive destination** — flag one folder as where completed projects land
- **Confidence** — High / Medium / Low

Present as a readable table. Low-confidence entries flagged for user correction at Q3.

### Step 5 — Select SQLite mode

Count noise-filtered indexable files (`.md`, `.pdf`, `.docx`, `.txt`) in knowledge-domain folders only — Active or Reference priority, excluding project workspaces (folders containing `CLAUDE.md`).

| Knowledge-domain file count | Mode |
|-----------------------------|------|
| < 300 | Markdown-only |
| 300–800 | Index mode |
| > 800 | Index mode (strongly recommended) |
| User has CRM / structured query needs | Record-store mode (opt-in post-bootstrap only) |

Present as a recommendation already made, one-sentence rationale. Override with "change storage mode."

---

## Phase 2: Interview

Three questions only.

**Q1 — Name and profile:** "What's your first name?" Then gather a lightweight owner profile — role/title, domain expertise, communication style preference. Keep it conversational, not a form. See `references/owner-profile.md` for the full protocol. Never ask more than 5 questions total across the entire interview.

**Q2 — Autonomy level:**
- *Ask before everything* — confirm every file write, move, delete
- *Ask before destructive actions* (recommended) — proceed freely on creates; confirm on moves, overwrites, deletes
- *Hands-off* — fully autonomous; interrupt with Escape

**Q3 — Confirm or correct the Repo Map**

Show draft map including the meeting-home, people-home and daily-home tags and the archive destination. For low-confidence entries, ask specifically. Confirm archive destination: "I've identified `<folder>` as where completed project archives should live — is that right?" If none inferred, ask.

---

## Phase 3: Write Output Files

### 3a — `.pkaignore`

Written in Phase 1 if absent. See `references/pkaignore-defaults.md`.

### 3b — `.pka/` directory

```
.pka/
├── bin/
│   ├── pka-tools         (the deterministic helper; see "Installing the toolkit")
│   └── pka_tools/
├── manifest.json         (which plugin version the vendored files came from)
├── upgrade-roles.py
├── roles/
│   ├── roster.md
│   ├── orchestrator.md
│   ├── researcher.md
│   └── librarian.md
├── owner-profile.md
├── session-log.md
├── decision-log.md
└── knowledge.db          (index mode only)
```

#### Installing the toolkit

`pka-tools` is a Python 3.9+ standard-library command that does the mechanical work for every skill: the index schema, indexing, search, pointer rows, person timelines, the Obsidian retrofit. It makes no network calls and never runs git. Install it into the workspace from the plugin's copy:

```
python3 "<plugin root>/bootstrap-assets/tools/pka-tools" install --workspace .
```

`<plugin root>` is the folder that holds this plugin's `skills/` and `bootstrap-assets/` — `${CLAUDE_PLUGIN_ROOT}` when the environment provides it, otherwise two directories above this skill's folder. After that, every skill runs the workspace's own copy: `.pka/bin/pka-tools <command>`.

The same command is how a workspace is brought up to date later: it replaces vendored files the user has not changed, keeps ones they have (writing the plugin's version beside them as `<name>.new`), and records the result in `.pka/manifest.json`. It never deletes anything: a file the plugin no longer ships is moved to `.pka/upgrade-backups/<timestamp>/vendored/` if the user never edited it and left in place otherwise.

If `python3 --version` reports older than 3.9, stop and tell the user; do not fall back to doing the tool's work by hand.

### 3c — Inboxes

Create `owner-inbox/` and `team-inbox/` at PKA root. Never create content folders when adapting to an existing structure.

### 3d — `CLAUDE.md`

If an existing `CLAUDE.md` lacks the `<!-- PKA` header comment: show diff and confirm before overwriting regardless of autonomy level.

Generate using `references/claude-md-template.md`.

### 3e — Owner profile

Generate `.pka/owner-profile.md` from Q1 interview responses. See `references/owner-profile.md` for schema and generation rules.

### 3f — Role definition files and shared references

Seed roles in `.pka/roles/`: orchestrator, researcher, librarian. See `references/role-definitions.md` for the standard schema and seed definitions.

Also seed two shared-reference files in `.pka/roles/` (these are **not roles** — they have no `role:` frontmatter and aren't in the roster, but they sit alongside roles because the roles reference them):

| Target file                    | Source seed                              | Notes                                                    |
|--------------------------------|------------------------------------------|----------------------------------------------------------|
| `.pka/roles/_obsidian.md`      | `references/obsidian-conventions.md`     | Inert when `knowledge/.obsidian/` is absent              |

The file is seeded verbatim from the fenced `markdown` block inside its source seed. **Do not overwrite if the file already exists** — the user may have customized it. If absent, write it.

Seeding it in the base bootstrap is benign — it only documents conventions that activate when `knowledge/.obsidian/` exists. It also means role-file references like "see `.pka/roles/_obsidian.md`" don't dangle.

### 3g — `session-log.md`

```
## <date> | bootstrap | PKA initialized | Repo map inferred — verify low-confidence entries | Start using team-inbox
```

### 3h — `decision-log.md`

Seed with bootstrap decisions (storage mode, autonomy level, archive destination). See `references/decision-log.md` for entry format and when-to-log rules.

### 3i — SQLite initialization (index mode)

```
.pka/bin/pka-tools db init
.pka/bin/pka-tools index
```

`db init` creates `.pka/knowledge.db` with the current schema; `index` fills it from the Repo Map's Active and Reference folders (markdown and text content, plus metadata and a content hash for every file). Do not write the schema or the inserts by hand. `index` lists documents that have no searchable text yet (PDFs without an OCR sidecar); hand that list to the librarian. Write `.pka/schema.md` from the output of `.pka/bin/pka-tools db schema`.

See `references/sqlite-modes.md` for the schema and the commands.

### 3j — Pointer layer (plain-markdown workspaces only)

If `knowledge/.obsidian/` exists, skip this: in an Obsidian vault the pointer layer is on by default.

Otherwise it is opt-in. Offer it in one sentence: *"I can add a small `_MOC.md` to each top-level folder so routed files get a searchable summary row — useful once there are hundreds of notes. Want that?"* On a yes, run `.pka/bin/pka-tools pointers init`. On a no, do nothing; routing then writes no MOCs, and the user can opt in later.

### 3k — Confirm and orient

Print: Repo Map summary, meeting-home and people-home folders, archive destination, storage mode, roles, two suggested first actions.

Then offer the weekly health check: run `.pka/bin/pka-tools lint schedule` and show what it prints (a cron line and a macOS launchd file that run a quick lint every Monday). Say plainly that nothing was installed and that installing either one is the user's to do. Never write to a crontab or `~/Library/LaunchAgents/`.

---

## Extending the Team (Post-Bootstrap)

1. `@researcher` generates competency brief → `owner-inbox/research-<role>-<date>.md`
2. New role `.md` written to `.pka/roles/`
3. If alias requested, `CLAUDE.md` `## Roles` section updated
4. `roster.md` updated
5. Definition shown to user for confirmation before finalizing
6. `session-log.md` entry appended

---

## Project Lifecycle Management

### Proactive Detection (Session Start)

Check all project workspace folders (contain `CLAUDE.md` at root, not in `.pka/`):
- No file modifications in 60+ days → flag for archiving/transition suggestion
- Referenced consistently in past tense in session log → flag similarly

### Transition Workflow

Triggered by: "transition `<folder>` to knowledge"

1. Read archive destination from `## Archive Destination` in `CLAUDE.md`
2. Read project `CLAUDE.md` + top-level markdown → generate `project-summary.md` draft using `references/project-summary-template.md` → save to `owner-inbox/<folder>-summary-draft.md`
3. **Mandatory pause** for user review and approval regardless of autonomy level
4. Show artifact cleanup list (`.pkaignore` matches) → confirm deletion
5. Move the folder and carry its links along:
   - **First check for a nested repository.** If `<project>/.git` exists, stop and ask. A plain move would carry the project's whole repository into the destination, and pka-skills no longer manages nested repositories: the user decides whether to keep that history somewhere (move `.git` aside first) or let it travel with the folder.
   - `mv <project>/ <archive-destination>/<folder>/`
   - Rewrite the wikilinks that pointed at the old location, in the vault's MOCs and notes and in the moved folder's own notes:
     ```
     .pka/bin/pka-tools pointers rename <project path> <new path> --prefix --notes
     ```
     Both paths are relative to the workspace root (`projects/orion`, `knowledge/archive/orion`). It prints how many links it rewrote and in which files; running it again changes nothing. It rewrites `[[wikilinks]]` only. Search for the old path afterwards (`grep -rn "<project path>" --include='*.md' .`) and show the user what is left: relative markdown links, and mentions in `CLAUDE.md` or other projects, are theirs to fix. Then run `.pka/bin/pka-tools index`.

   Then copy the approved summary into the moved directory as `project-summary.md`. Nothing is committed: the move, the rewritten links and the summary are left in the working tree for the user.
6. Update Repo Map: status → archived, Priority → Reference
7. Librarian runs content index pass on moved directory
8. Append to `session-log.md`

### Reverse Transition

1. Move back from archive destination to original location, then run `.pka/bin/pka-tools pointers rename <archive path> <original path> --prefix --notes` so wikilinks follow it, in the vault and inside the project's own notes, then `.pka/bin/pka-tools index`. If the project was graduated by an earlier release's `graduate.sh`, its original repository is still at `.pka/graduate-backups/<folder>-<timestamp>.git`: tell the user it is there and that restoring it (`mv <backup> projects/<folder>/.git`) is theirs to do. Never delete anything under `.pka/graduate-backups/`.
2. Update Repo Map: status → active
3. Remove from full-text index; add back to shallow index
4. `project-summary.md` stays in project directory as context
5. Append to session log

---

## Obsidian Coexistence Bootstrap (target: `obsidian`)

A one-time, user-triggered mechanical retrofit of an existing Obsidian vault at `knowledge/`. **Detection-only** behavior (when `knowledge/.obsidian/` exists but bootstrap hasn't been run) does not modify any vault content — it only causes roles to enhance files they touch during normal work.

### Preconditions

- `knowledge/.obsidian/` exists (vault is opted in).
- The user has explicitly requested the bootstrap.
- (Recommended) if the vault is in a git repository, it is in a clean state so the resulting diff is reviewable.

If `knowledge/.obsidian/` is absent, refuse with a clear message: *"No Obsidian vault detected at `knowledge/.obsidian/`. The Obsidian bootstrap is a no-op outside an Obsidian vault."*

### Procedure

Full procedure in `references/obsidian-bootstrap.md`. The retrofit is one command; the skill does not edit vault files itself.

1. **Seed `.pka/roles/_obsidian.md`** from `references/obsidian-conventions.md` if absent.
2. **Make sure `.pka/bin/pka-tools` is installed** (see "Installing the toolkit").
3. **Preview**: `.pka/bin/pka-tools obsidian bootstrap --dry-run`, and show the counts.
4. **Run**: `.pka/bin/pka-tools obsidian bootstrap`. It commits nothing; the user reviews the diff and commits it.
5. **Relay the summary**, including every skipped file and note.

What the command guarantees:

- **Mechanical only** — filename, folder structure and existing frontmatter are the inputs. Note bodies are carried through byte for byte.
- **Merge, never overwrite** — existing frontmatter lines are not rewritten; missing keys are inserted as new lines and the domain tag is added to `tags`.
- **Skips what it cannot read safely** — malformed or unsupported frontmatter, non-UTF-8 and read-only notes are listed and left untouched.
- **Existing `_MOC.md` and person `index.md` files are never edited.**
- **Nothing is committed.** The changes are left in the working tree.

### Output summary

Print before finishing:
- N MOC stubs created
- N person indexes created
- N files given frontmatter
- N files with malformed existing frontmatter (skipped, listed by path)
- Total files touched
- That nothing was committed, and the changes are theirs to review

### Idempotency

Re-running produces no changes. The bootstrap detects existing MOCs, indexes, and frontmatter and skips. Augmentation on re-run is additive only (e.g., a new domain folder created since last run gets a new MOC).

---

## Workspaces with nested repositories

Earlier releases offered a `git` target that made the workspace a "hybrid monorepo": a root repository, separate repositories at `knowledge/` and each `projects/<name>/`, a `.meta` manifest listing them, helper scripts under `.pka/` (`graduate.sh`, `init_project_repos.sh`, `reinit-project-with-lfs.sh`, `push-all.sh`, `build-repo-list.sh`) and a commit after every route. That support has been removed. In a workspace that still has the layout:

- **Leave it alone.** Never delete or edit `.meta`, the nested `.git` directories, the root `.gitignore` (its `knowledge/` and `projects/` lines keep the root repository from swallowing the nested ones), `.pka/graduate-backups/` or `.pka/reinit-backups/` (the only copies of some project histories).
- **Nothing is committed or pushed any more.** Filing a note changes files; the user commits them in whichever repository holds them. `post-route` says so in its summary when it sees `.meta`. Tell the user once per session; do not offer to commit for them.
- **The helper scripts are no longer shipped or maintained.** `bootstrap upgrade` reports what it does with the copies in `.pka/`: ones recorded in the manifest and never edited are moved to `.pka/upgrade-backups/<timestamp>/vendored/`; edited ones, and ones from before the manifest existed, stay where they are for the user to keep running by hand or delete.
- **Do not run those scripts**, and do not re-create the layout. If the user asks for a push across their repositories, that is theirs to run.
- **Turning the workspace into one repository** is a decision about their history and remotes. Do not attempt it as part of any bootstrap; if asked, plan it with the user step by step.

---

## Upgrade Existing Bootstrap (target: `upgrade`)

A user with an already-bootstrapped workspace (typically from a pre-v1.6 install) requests this target to refresh role files in place without losing customizations. Common phrasings: "upgrade my pka", "bootstrap upgrade", "update my role files".

### Preconditions

- `.pka/roles/` exists (the workspace has been bootstrapped at least once).
- The user has explicitly requested the upgrade.

If `.pka/roles/` is absent, refuse with a message pointing to base bootstrap.

### Procedure

Full step-by-step algorithm in `references/upgrade.md`. Summary:

1. **Refresh the vendored helpers** with the installer (see "Installing the toolkit"):
   ```
   python3 "<plugin root>/bootstrap-assets/tools/pka-tools" install --workspace .
   ```
   It installs or updates `.pka/bin/pka-tools` and `.pka/upgrade-roles.py`, and reports what it did with files the plugin no longer ships (see "Workspaces with nested repositories"). In a workspace from before v1.7 (no `.pka/manifest.json`) the old helper scripts are replaced and the previous copies are saved under `.pka/upgrade-backups/<timestamp>/vendored/`; relay that path. An old `upgrade-roles.py` only knows the sections of its own version and silently skips whatever was added since, so this step always comes first.
2. **Migrate the index, if there is one and it is behind.** `.pka/bin/pka-tools status` shows the schema version. When it says the index needs `db migrate`:
   - run `.pka/bin/pka-tools db migrate` and show the user the plan (it changes nothing);
   - **ask before applying** — it is a schema change, whatever the autonomy level;
   - on a yes, run `.pka/bin/pka-tools db migrate --apply` (it backs the database up to `.pka/db-backups/` first and rolls back on any failure), then `.pka/bin/pka-tools index`;
   - on a no, carry on: the rest of the upgrade does not depend on it, but `index` and `search` stay unavailable until the index is migrated.
3. **Run the helper** with `python3 .pka/upgrade-roles.py --workspace <root>`. The helper:
   - Backs up `.pka/roles/` to `.pka/upgrade-backups/<timestamp>/`
   - Seeds `.pka/roles/_obsidian.md` if absent
   - Structured-merges new H2 sections into orchestrator/librarian/researcher role files
   - Never modifies the body of existing sections on this run
   - Lists **sections seeded by an earlier version**: "can be refreshed" (the text is exactly what an earlier version shipped, so the user never edited it) or "customised — left alone"
   - Lists **obsolete** sections and files, left by the removed commit/push protocol (`.pka/roles/_git-protocol.md`, the "Commit/push protocol" sections, the orchestrator's push sections): "can be removed" or "customised — left alone"
4. **Print the helper's summary** to the user.
5. **Offer the refresh, if the summary lists sections that can be refreshed or removed.** These carry superseded instructions (the pre-v1.7 pointer-row rule, for example). Ask once, naming both kinds; on a yes run `python3 .pka/upgrade-roles.py --workspace <root> --refresh`. It takes a new backup, replaces the refreshable sections, removes the obsolete ones that were never edited, and leaves customised ones alone. Until the obsolete sections are gone the role files still tell the roles to commit, to push and to run helper scripts the upgrade has just moved to the backup folder. Say this plainly if the user declines the refresh or a section is customised and stays: those instructions must not be followed, and they should remove or reword them.
   - For a **customised** section, show the difference with `--diff` and let the user decide. Replace one (or remove an obsolete one) only on an explicit yes for that section: `--refresh --refresh-section '<file>:## <Heading>'`. Never pass `--refresh-section` on your own judgement — it overwrites or removes the user's text (the backup keeps it). A customised `_git-protocol.md` is never removed by the helper; the user deletes it when they no longer want it.
6. **Suggest follow-ups** based on what's now present:
   - If `knowledge/.obsidian/` exists and the user hasn't already, suggest `bootstrap obsidian` for the mechanical retrofit.
   - If there is no Obsidian vault and no `_MOC.md` anywhere in `knowledge/`, mention that the pointer layer is opt-in (step 3j of base bootstrap).
   - If the workspace has a `.meta` file at root, tell the user what changed for it (see "Workspaces with nested repositories").
   - Mention the manual bullet-merges into `## Key Competencies` and `## Output Conventions` (the upgrade does not touch these — see `references/upgrade.md` for the rationale).
   - Show the weekly health-check entry: run `.pka/bin/pka-tools lint schedule` and relay what it prints. Nothing is installed; installing it is the user's to do, and they can skip it. If they already installed it for this workspace, there is nothing to change.

### Hard rules

- **Never commits.** Changes are left in the working tree for human review.
- **Never modifies the body of existing H2 sections** unless `--refresh` is given. Without it, only ADDS new sections.
- **Never modifies frontmatter** in role files.
- **Always creates a backup** before any modification (even if the upgrade ends up being a no-op, the backup is created — cheap insurance).

### Idempotency

Re-running on an already-upgraded workspace produces no further role-file changes (every new section's H2 heading is detected as already-present). A new backup is still created, by design.

### Output

The helper prints (and the orchestrator surfaces):
```
Role upgrade summary
------------------------
Backup:  /workspace/.pka/upgrade-backups/<timestamp>/roles

Shared references seeded:           N (M already present)
orchestrator: added K section(s):
  + ## Session-start checks (cached for the session)
  + ## File references in responses
  ...
librarian:    added K section(s):
  + ## Obsidian coexistence (gated on `obsidian_present`)
  + ## Pointer-row maintenance (…)
researcher:   added K section(s):
  ...

NOTE: This upgrade only ADDS new H2 sections. It does NOT modify
      existing sections (e.g., 'Key Competencies', 'Output Conventions',
      or 'Invocation'). See references/role-definitions.md for any
      bullet-level additions you may want to merge manually.
```

---

## All-target Bootstrap (target: `all`)

If the user requests `bootstrap all` or `bootstrap everything`:

1. If `.pka/roles/` already exists (bootstrapped previously), run the `upgrade` target first to refresh roles. Otherwise run base bootstrap (Phase 1–3).
2. If `knowledge/.obsidian/` exists, run the Obsidian bootstrap. (If absent, skip with a one-line note in the summary.)
3. Print one consolidated summary across all phases.
