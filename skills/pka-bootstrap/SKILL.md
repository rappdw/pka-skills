---
name: pka-bootstrap
description: >
  ALWAYS use this skill when the user mentions PKA, personal knowledge, repo map,
  knowledge base setup, replacing Obsidian/Notion/Tana/Heptabase, organizing
  notes and files into a unified system, adding roles to their AI team, project
  lifecycle management, transitioning or archiving projects, restoring archived
  projects, checking which projects are stale or winding down, or bootstrapping
  any kind of personal knowledge assistant. This skill handles first-run setup
  (scanning folders, inferring structure, writing CLAUDE.md, creating SQLite
  indexes, defining roles) AND ongoing management (updating the repo map, adding
  team roles, transitioning completed projects to a knowledge archive, checking
  project activity). Use it even if the user doesn't say "PKA" explicitly — if
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
- Any mention of "personal knowledge assistance", "PKA", "repo map", "CLAUDE.md orchestrator"

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

The flat vs. subfolder-organized distinction is critical for inference quality — a folder of 30 subfolders named after people is personnel notes; a flat folder of 30 date-named `.md` files is a journal or meeting log.

### Step 4 — Infer Repo Map

For each folder, infer using `references/inference-guide.md`:
- **What it contains** — one plain-language sentence
- **How it's organized** — by person, date, topic, flat, etc.
- **Priority** — Active / Reference / Archive
- **Meeting tag** — `meeting-home` if the folder contains date-slug meeting files; multiple folders can be tagged
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

**Q1 — Name:** "What's your first name?"

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
├── session-log.md
└── knowledge.db          (index mode only)
```

### 3c — Inboxes

Create `owner-inbox/` and `team-inbox/` at PKA root. Never create content folders when adapting to an existing structure.

### 3d — `CLAUDE.md`

If an existing `CLAUDE.md` lacks the `<!-- PKA` header comment: show diff and confirm before overwriting regardless of autonomy level.

Generate using `references/claude-md-template.md`.

### 3e — Role definition files

Seed roles in `.pka/roles/`: orchestrator, researcher, librarian. See `references/role-definitions.md` for the standard schema and seed definitions.

### 3f — `session-log.md`

```
## <date> | bootstrap | PKA initialized | Repo map inferred — verify low-confidence entries | Start using team-inbox
```

### 3g — SQLite initialization (index mode)

Schema generated from Repo Map. Documented in `.pka/schema.md` (runtime-generated, not a skill asset). Bootstrap population is metadata-only — full content indexing is the librarian's job. Target: under 30 seconds for any repo size.

See `references/sqlite-modes.md` for schema details.

### 3h — Confirm and orient

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
