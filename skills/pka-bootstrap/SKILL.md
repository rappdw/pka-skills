---
name: pka-bootstrap
description: >
  ALWAYS use this skill when the user mentions PKA, personal knowledge, repo map,
  knowledge base setup, replacing Obsidian/Notion/Tana/Heptabase, organizing
  notes and files into a unified system, adding roles to their AI team, project
  lifecycle management, transitioning or archiving projects, restoring archived
  projects, checking which projects are stale or winding down, bootstrapping
  any kind of personal knowledge assistant, OR setting up Obsidian coexistence
  / a hybrid monorepo (root .git + child repos at knowledge/ and projects/*
  coordinated via .meta). Triggers also include: "bootstrap obsidian", "bootstrap
  vault", "MOC stubs", "frontmatter retrofit", "bootstrap git", "initialize the
  hybrid repo", "set up the meta monorepo", "bootstrap all", "bootstrap
  everything". This skill handles first-run setup (scanning folders, inferring
  structure, writing CLAUDE.md, creating SQLite indexes, defining roles) AND
  ongoing management (updating the repo map, adding team roles, transitioning
  completed projects to a knowledge archive, checking project activity) AND
  the additive Obsidian / hybrid-monorepo bootstraps (idempotent, user-triggered,
  never auto-run). Use it even if the user doesn't say "PKA" explicitly — if
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
- "Bootstrap git / the hybrid repo / the meta monorepo"
- "Bootstrap all / bootstrap everything"
- Any mention of "personal knowledge assistance", "PKA", "repo map", "CLAUDE.md orchestrator"

---

## Bootstrap targets

`pka-bootstrap` is a single skill that handles three independent bootstrap procedures. The user picks one (or `all`):

| Target     | What it does                                                                                  | Idempotent? | Reference                              |
|------------|-----------------------------------------------------------------------------------------------|-------------|-----------------------------------------|
| (default)  | Original PKA setup: Repo Map, `.pka/`, roles, SQLite, `CLAUDE.md`. Phase 1–3 below.            | Yes         | This document                          |
| `obsidian` | One-time mechanical retrofit of an Obsidian vault at `knowledge/`: MOC stubs, person indexes, filename-pattern frontmatter, domain tags. | Yes | `references/obsidian-bootstrap.md`     |
| `git`      | One-time setup of a hybrid monorepo: root `.git`, `knowledge/.git`, each `projects/*/.git` with LFS, `.meta` manifest, `.pka/` templates and helper scripts. | Yes | `references/git-bootstrap.md`          |
| `all`      | Run base PKA setup if needed, then `obsidian` if `knowledge/.obsidian/` exists, then `git`.    | Yes         | All three references                    |

**Resolution rules** (the orchestrator dispatches; this skill is the executor):

| Phrasing the user used                                       | Target     |
|--------------------------------------------------------------|------------|
| "bootstrap obsidian", "bootstrap the vault", "moc stubs", "frontmatter retrofit" | `obsidian` |
| "bootstrap git", "bootstrap the hybrid repo", "bootstrap the monorepo", "set up meta" | `git`      |
| "bootstrap all", "bootstrap everything", or both vocabularies appear            | `all`      |
| Generic "bootstrap" without a target qualifier                                  | base PKA setup (existing behavior) |

If the orchestrator can't tell, it asks the user before delegating here.

**Hard rules across all targets**:

- Bootstraps run **only on explicit user request**. Detection (e.g., finding `knowledge/.obsidian/`) is **not** a trigger.
- Bootstraps are **idempotent**. Re-running on an already-bootstrapped state produces no further changes.
- The `git` bootstrap **never** creates remote repos, sets `origin` URLs, or pushes. Remote topology is the user's decision.
- The `git` bootstrap **never** auto-commits the root repo. Root scaffolding is staged for the user's review only.
- Both `obsidian` and `git` bootstraps **fail soft** — non-critical errors log and continue; the primary task isn't blocked.

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
- Presence of date-slug named files (e.g., `2026-03-15-1-1-aarav.md`) → **meeting notes home signal** (used by `pka-meetings` for routing)
- Presence of subfolders each containing `wiki.md` → **topic wiki home signal** (used by `pka-wiki` for synthesis)

The flat vs. subfolder-organized distinction is critical for inference quality — a folder of 30 subfolders named after people is personnel notes; a flat folder of 30 date-named `.md` files is a journal or meeting log.

### Step 4 — Infer Repo Map

For each folder, infer using `references/inference-guide.md`:
- **What it contains** — one plain-language sentence
- **How it's organized** — by person, date, topic, flat, etc.
- **Priority** — Active / Reference / Archive
- **Meeting tag** — `meeting-home` if the folder contains date-slug meeting files; multiple folders can be tagged
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

Show draft map including meeting-home tags and archive destination. For low-confidence entries, ask specifically. Confirm archive destination: "I've identified `<folder>` as where completed project archives should live — is that right?" If none inferred, ask.

---

## Phase 3: Write Output Files

### 3a — `.pkaignore`

Written in Phase 1 if absent. See `references/pkaignore-defaults.md`.

### 3b — `.pka/` directory

```
.pka/
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
| `.pka/roles/_git-protocol.md`  | `references/git-protocol.md`             | Inert when no `.meta` / hybrid monorepo                  |

Both files are seeded verbatim from the fenced `markdown` block inside their source seeds. **Do not overwrite if the file already exists** — the user may have customized it. If absent, write it.

Seeding these in the base bootstrap is benign — they only document conventions that activate when the relevant predicate is true. It also means role-file references like "see `.pka/roles/_obsidian.md`" don't dangle.

### 3g — `session-log.md`

```
## <date> | bootstrap | PKA initialized | Repo map inferred — verify low-confidence entries | Start using team-inbox
```

### 3h — `decision-log.md`

Seed with bootstrap decisions (storage mode, autonomy level, archive destination). See `references/decision-log.md` for entry format and when-to-log rules.

### 3i — SQLite initialization (index mode)

Schema generated from Repo Map. Documented in `.pka/schema.md` (runtime-generated, not a skill asset). Bootstrap population is metadata-only — full content indexing is the librarian's job. Target: under 30 seconds for any repo size.

See `references/sqlite-modes.md` for schema details.

### 3j — Confirm and orient

Print: Repo Map summary, meeting-home folders, archive destination, storage mode, roles, two suggested first actions.

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
5. Move: `mv <project>/ <archive-destination>/<folder>/`; copy approved summary
6. Update Repo Map: status → archived, Priority → Reference
7. Librarian runs content index pass on moved directory
8. Append to `session-log.md`

### Reverse Transition

1. Move back from archive destination to original location
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
- (Recommended) the vault is in a clean git state so the resulting diff is reviewable.

If `knowledge/.obsidian/` is absent, refuse with a clear message: *"No Obsidian vault detected at `knowledge/.obsidian/`. The Obsidian bootstrap is a no-op outside an Obsidian vault."*

### Procedure

Full step-by-step algorithm in `references/obsidian-bootstrap.md`. Summary:

1. **Seed `.pka/roles/_obsidian.md`** from `references/obsidian-conventions.md` if absent.
2. **Walk `knowledge/`** collecting:
   - Top-level domain folders (each gets a `_MOC.md` stub if absent).
   - `personnel/<name>/` subfolders (each gets an `index.md` stub if absent).
   - Files matching known patterns (1on1, meeting, daily) for filename-pattern frontmatter.
3. **Mechanical retrofits only** — no body reading. Use only filename and folder structure.
4. **Merge, never overwrite** — files with existing frontmatter get missing schema fields added; existing fields are left alone.
5. **Skip malformed frontmatter** — list in summary, do not modify.
6. **Single commit** in `knowledge/` (when `hybrid_monorepo_present`): `Bootstrap (obsidian): N MOCs, N person indexes, N frontmatter additions`. Never commits the root.

### Output summary

Print before finishing:
- N MOC stubs created
- N person indexes created
- N files given frontmatter
- N files with malformed existing frontmatter (skipped, listed by path)
- Total files touched
- Whether a commit was made (and in which repo)

### Idempotency

Re-running produces no changes. The bootstrap detects existing MOCs, indexes, and frontmatter and skips. Augmentation on re-run is additive only (e.g., a new domain folder created since last run gets a new MOC).

---

## Git/Meta Hybrid Monorepo Bootstrap (target: `git`)

A one-time, user-triggered setup of a hybrid monorepo: root `.git` coordinating independent child repos at `knowledge/` and each `projects/<name>/`, tied together by a `.meta` manifest.

### Preconditions

- User has explicitly requested the bootstrap.
- `git` and `git-lfs` binaries are on PATH (else fail with a remediation hint).
- The skill has access to `bootstrap-assets/` (vendored templates and scripts in this plugin).

### Procedure

Full step-by-step algorithm in `references/git-bootstrap.md`. Summary:

1. **Install `.pka/` templates** from `bootstrap-assets/`:
   - `gitattributes-template` → `.pka/gitattributes-template`
   - `gitignore-template` → `.pka/gitignore-template`
2. **Install `.pka/` helper scripts** from `bootstrap-assets/scripts/`:
   - `graduate.sh`, `init_project_repos.sh`, `reinit-project-with-lfs.sh`, `push-all.sh`, `build-repo-list.sh`
   - Set executable bit on each.
3. **Seed `.pka/roles/_git-protocol.md`** from `references/git-protocol.md` if absent.
4. **Root `.gitignore`**: create or augment to exclude child-repo content (`knowledge/`, `projects/`), inboxes (`owner-inbox/`, `team-inbox/`), local artifacts (`.pka/knowledge.db*`, `.pka/*-log.txt`), and secrets (`.gitea-pat*`, `*.token`, `*.secret`). Merge — never replace.
5. **Root `.git`**: initialize if absent. Stage files. **Do not commit.** Root commits are the user's review gate.
6. **`knowledge/` child repo**: if `knowledge/.git` is absent, initialize with `init_project_repos.sh`'s pattern (templates → `git init -b main` → `git lfs install --local` → initial commit `Bootstrap (git): Initial hybrid monorepo setup`).
7. **Each `projects/*/`**: same as `knowledge/` for any directory lacking `.git`. Projects with `.git` but no LFS are **flagged** in the summary as reinit candidates — never modified silently.
8. **`.meta` generation**: walk `knowledge/` and `projects/*/`, read each child's origin remote (or empty if none), write `.meta` JSON at root. Use `build-repo-list.sh` after the init pass.

### Hard rules

- **No remotes are created or set.** Bootstrap never calls `git remote add origin`, never makes network requests.
- **No pushes.** Bootstrap never calls `git push`.
- **Root never auto-commits.** Stage scaffolding, surface in summary.
- **Existing child repos with `.git` but no LFS are NOT reinitialized.** They are flagged with a pointer to `reinit-project-with-lfs.sh` (which is a destructive opt-in operation).

### Output summary

Print before finishing:
- N templates installed / already present
- N helper scripts installed / already present
- Root repo: initialized (uncommitted, awaiting review) / already present
- `knowledge/`: initialized with LFS / already present
- N projects initialized with LFS
- N projects flagged as reinit candidates (have `.git` but no LFS)
- `.meta` generated/updated with N entries
- Root working-tree changes staged for user review (listed)

### Idempotency

Re-running produces no changes. Each step checks "is this already done?" before acting.

---

## All-target Bootstrap (target: `all`)

If the user requests `bootstrap all` or `bootstrap everything`:

1. If no PKA setup exists, run base bootstrap (Phase 1–3).
2. If `knowledge/.obsidian/` exists, run the Obsidian bootstrap. (If absent, skip with a one-line note in the summary.)
3. Run the git bootstrap.
4. Print one consolidated summary across all three.
