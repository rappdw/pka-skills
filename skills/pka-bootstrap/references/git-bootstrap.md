# Git/Meta Hybrid Monorepo Bootstrap — Algorithm

Procedure for the `git` bootstrap target. Invoked when the user explicitly requests "bootstrap git", "initialize the hybrid repo", "set up the meta monorepo", or similar. Never auto-runs.

## Inputs

- `WORKSPACE_ROOT` — the directory containing `CLAUDE.md` (where the user invoked Claude).
- `bootstrap-assets/` — vendored templates and scripts in this plugin (`pka-skills/bootstrap-assets/`).

## Outputs (when run from cold)

```
<WORKSPACE_ROOT>/
├── .git/                         (root repo, no commits, scaffolding STAGED)
├── .gitignore                    (created or augmented; merged, never replaced)
├── .meta                         (JSON manifest of child repos)
├── .pka/
│   ├── manifest.json             (what was vendored, from which plugin version)
│   ├── bin/pka-tools             (executable; with bin/pka_tools/)
│   ├── gitattributes-template
│   ├── gitignore-template
│   ├── graduate.sh               (executable)
│   ├── init_project_repos.sh     (executable)
│   ├── reinit-project-with-lfs.sh (executable)
│   ├── push-all.sh               (executable)
│   ├── build-repo-list.sh        (executable)
│   └── roles/
│       └── _git-protocol.md      (seeded if absent)
├── knowledge/
│   ├── .git/                     (initial commit, LFS-configured)
│   ├── .gitattributes
│   └── .gitignore
└── projects/
    └── <each project>/
        ├── .git/                 (initial commit, LFS-configured)
        ├── .gitattributes
        └── .gitignore
```

## Hard rules (revisit before every step)

1. **No network operations.** No `curl`, no `git push`, no API calls. The bootstrap may set an origin URL only if the caller has explicitly opted in via the `ORIGIN_BASE` environment variable on `init_project_repos.sh` (and even that just calls `git remote add` locally — no network round-trip). Default behavior: no origin set at all.
2. **Root never auto-commits.** Stage only.
3. **Existing child repos are not reinitialized.** A project with `.git` but no LFS is **flagged** in the summary, not modified. Reinit is a separate, opt-in operation (`reinit-project-with-lfs.sh`) that replaces the history and requires typed confirmation per project; it keeps the old repository as a backup under `.pka/reinit-backups/`. Children that are symbolic links, or whose `.git` is a file (linked worktree, submodule), are never touched: their repository lives elsewhere.
4. **Idempotent.** Re-running on an already-bootstrapped state must produce no changes.
5. **Required binaries**: `git` 2.28 or newer and `git-lfs` on PATH, plus `python3` 3.9 or newer (the installer, `pka-tools`, and `.meta` JSON manipulation). If any are missing or git is too old, abort with a remediation hint and exit code 2.
6. **A usable git identity** (`user.name` / `user.email`). The helper checks before creating anything; without one, stop and tell the user to set it.

## Steps

### Step 0 — Preflight

- Verify `git` (2.28+) and `git-lfs` are on PATH. If not, abort with: *"Git bootstrap needs `git` and `git-lfs`. Install with `brew install git-lfs` (macOS) or your package manager, then re-run."*
- Resolve `WORKSPACE_ROOT` to absolute path.
- Create `.pka/` if absent (the base bootstrap may have done this; either way ensure it exists).

### Step 1 — Install templates and helper scripts

One command installs everything `bootstrap git` vendors, and records it in `.pka/manifest.json`:

```
python3 "<plugin root>/bootstrap-assets/tools/pka-tools" install --workspace . --git
```

(`<plugin root>` is the folder holding this plugin's `skills/` and `bootstrap-assets/`; see "Installing the toolkit" in `SKILL.md`.)

| Installed to `.pka/` | Kind |
|---|---|
| `bin/pka-tools`, `bin/pka_tools/*.py`, `upgrade-roles.py` | code |
| `graduate.sh`, `init_project_repos.sh`, `reinit-project-with-lfs.sh`, `push-all.sh`, `build-repo-list.sh` | code, executable |
| `gitattributes-template`, `gitignore-template` | templates, meant to be edited |

Do not copy these by hand: the manifest is what lets a later upgrade tell an untouched file from one the user edited.

### Step 2 — Report what the installer did

The installer prints five lists. Carry them into the summary:

- **Installed** — was absent.
- **Updated** — the workspace's copy was untouched since it was installed and the plugin's copy is newer, so it was replaced. In a workspace from before v1.7 (no manifest) the helper scripts are replaced whenever they differ, and the previous copies are saved under `.pka/upgrade-backups/<timestamp>/vendored/`. A stale helper keeps old bugs alive (the v1.6.3 data-loss fixes only reach a workspace this way).
- **Current** — already identical.
- **Kept** — the user edited it and the plugin's copy has not changed since. Nothing to do.
- **Conflicts** — the user edited it *and* the plugin's copy changed. Their file is kept; the plugin's version is beside it as `<name>.new`. Tell the user which files, so they can merge.

### Step 3 — Seed `_git-protocol.md`

Copy the content from the fenced markdown block in `references/git-protocol.md` to `.pka/roles/_git-protocol.md`. If the destination already exists, skip silently.

### Step 4 — Root `.gitignore` (merge, never replace)

Merge these entries into root `.gitignore` (create the file if absent; append only missing lines if present):

```
# Child repos (independent histories)
knowledge/
projects/

# Inboxes (transient hand-off areas)
owner-inbox/
team-inbox/

# Meeting captures (audio and transcripts written by earshot; large, private)
meeting-notes/

# Local artifacts
.pka/knowledge.db
.pka/knowledge.db-*
.pka/*-log.txt
.pka/graduate-backups/
.pka/reinit-backups/
.pka/upgrade-backups/
.pka/db-backups/
.pka/bin/**/__pycache__/
.pka/**/*.new

# Secrets
.gitea-pat
.gitea-pat-*
*.token
*.secret
*.env
.env
.env.local

# OS noise
.DS_Store
Thumbs.db
```

The merge is line-exact: each non-empty, non-comment line that already exists is left alone; missing lines are appended at the end (with a `# pka-bootstrap` separator if a section header is needed for clarity).

### Step 5 — Root `.git` (initialize, no commit)

```
if not directory_exists("./.git"):
    git init -b main
```

Stage the scaffolding this bootstrap wrote, **by path**: `git add -- .gitignore .pka/<each template, script and role file installed or updated>` (and `.meta` after Step 8). Do not use `git add -A` at the root: it would also stage whatever else is lying in the workspace — loose notes, exports, anything the ignore list does not cover — and present it to the user as bootstrap output. **Do not commit.** The root commit is the user's first review gate — they do it manually.

If `./.git` already exists, leave it alone. Stage any newly-created scaffolding so the working tree shows what's ready for review.

### Step 6 — `knowledge/.git` (initialize with LFS)

```
if directory_exists("./knowledge") AND not directory_exists("./knowledge/.git"):
    cp .pka/gitattributes-template knowledge/.gitattributes  # (only if absent)
    merge .pka/gitignore-template into knowledge/.gitignore  # (line-merge)
    cd knowledge
    git init -b main
    git lfs install --local
    git add -- .gitattributes .gitignore
    git commit -m "Bootstrap (git): Configure LFS tracking and .gitignore" ...
    git add -A        # a brand-new repo: the whole directory is its content
    git commit -m "Bootstrap (git): Initial hybrid monorepo setup" \
              -m "" \
              -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

Do this by running `.pka/init_project_repos.sh`, not by hand. The script checks every step: if `git init` or a commit fails for a child it removes the half-made `.git`, lists the child under "Failed", carries on with the others and exits 1. Relay its "Failed" and "Left alone" lists to the user verbatim.

If `knowledge/` doesn't exist yet, skip — base bootstrap or the user creates it first.

If `knowledge/.git` already exists:
- If LFS is configured (`.gitattributes` contains `filter=lfs`), report "already present".
- If LFS is **not** configured, **flag** as a reinit candidate in the summary; do **not** modify.

### Step 7 — `projects/<each>/.git` (initialize with LFS)

For each immediate subdirectory of `projects/`:

Same as Step 6 substituting `projects/<name>` for `knowledge`. Implementation can simply invoke `.pka/init_project_repos.sh` after Steps 1–2 are done — that script encodes exactly this loop with idempotency.

### Step 8 — `.meta` manifest

Run `.pka/build-repo-list.sh` (or equivalent inline logic) to walk `knowledge/` and `projects/*/` for child repos with `.git` and emit `.meta` JSON at root:

```json
{
  "projects": {
    "knowledge": "<origin URL or empty>",
    "projects/<name1>": "<origin URL or empty>",
    "projects/<name2>": ""
  }
}
```

An empty origin means the child repo has no `origin` remote yet. The auto-push at session end **skips** such repos, reporting them as skipped (not failed).

`.meta` is **derived** from the child repos, never the other way round. The "projects" map is rebuilt on every run from each child's actual `origin` remote, so a URL typed into `.meta` by hand is overwritten and is never used for pushing. To give a child repo a remote:

```
git -C <child> remote add origin <url>
.pka/build-repo-list.sh
```

If `.meta` already exists, regenerate from current state (entries may have been added or removed since last run). Other top-level keys in the file are preserved. The format is deterministic, so re-running on identical state produces an identical file. If the existing `.meta` is not valid JSON the script stops without touching it.

### Step 9 — Stage root scaffolding

Final pass: stage, by path, anything Steps 1–8 produced in the root (`.gitignore`, `.meta`, the `.pka/` files installed or updated). List the staged files in the summary so the user knows what's awaiting their review. Never `git add -A` at the root (see Step 5).

### Step 10 — Summary

Print to the user:

```
Hybrid monorepo bootstrap complete.

Vendored files:             N installed, K updated, M current
                            kept (edited locally): <names>
                            conflicts (yours kept, plugin's copy beside it as <name>.new): <names>
                            previous copies saved under: .pka/upgrade-backups/<timestamp>/vendored/
Shared reference seeded:    .pka/roles/_git-protocol.md (or "already present")
Root .gitignore:            created / augmented (lines added: K)

Root repo:                  initialized (uncommitted, awaiting your review)
                            OR  already present
knowledge/:                 initialized with LFS (initial commit made)
                            OR  already present
                            OR  flagged: has .git but no LFS — see reinit-project-with-lfs.sh
Projects initialized:       N
Projects flagged:           M (have .git but no LFS — listed below)
  - projects/<name>: run .pka/reinit-project-with-lfs.sh projects/<name> to opt into LFS
    (replaces the history; the old repository is kept under .pka/reinit-backups/)
Left alone:                 K (symbolic links, linked worktrees, submodules — listed below)
Failed:                     J (listed below with the reason; no .git was left behind)
.meta manifest:             generated/updated with K entries

Root working-tree changes STAGED for your review:
  - .gitignore
  - .meta
  - .pka/...
  ...

Next steps:
  1. git status / git diff --cached  to review staged changes
  2. git commit  to lock in the scaffolding
  3. When you've decided where each repo should live:
       git -C <child> remote add origin <url>
       .pka/build-repo-list.sh        (refreshes .meta from the repos)
  4. .pka/push-all.sh  whenever you're ready to push
```

## Failure modes

- **Missing binaries** (Step 0): abort with hint, exit 2.
- **Templates missing in `bootstrap-assets/`**: bug in this plugin, abort with diagnostic.
- **Filesystem permission errors**: abort with the path that failed and the OS error.
- **No usable git identity**: the helper stops before creating anything. Tell the user to set `user.name` and `user.email`.
- **`git init`, `git lfs install` or a commit fails for one child** (hook, signing, permissions): the helper removes the `.git` it had just created for that child, reports the child under "Failed" with git's own error, continues with the others and exits 1. Surface the error verbatim. A re-run retries the failed children; it never reports them as "already initialized".

All failures land in the summary. Children that initialized successfully stay initialized.

## What NOT to do

- Do not call `curl`, `wget`, or any HTTP client.
- Do not call `git push`, `git fetch`, or any remote-aware git command.
- Do not auto-commit the root repo. Period.
- Do not reinit a child repo that already has `.git`. Even if it lacks LFS — flag instead.
- Do not modify files in `team-inbox/`, `owner-inbox/`, or any user-content directory beyond the scaffolding listed above.
- Do not remove origin URLs that already exist in child repo configs — preserve them and reflect them in `.meta`.

## Idempotency check

After running the bootstrap, immediately re-running it must produce no further file changes. `tests/test_git_bootstrap.sh` checks this.
