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

1. **No remote operations.** No `git remote add`, no `git push`, no `curl`, no anything that touches the network.
2. **Root never auto-commits.** Stage only.
3. **Existing child repos are not reinitialized.** A project with `.git` but no LFS is **flagged** in the summary, not modified.
4. **Idempotent.** Re-running on an already-bootstrapped state must produce no changes.
5. **Required binaries**: `git`, `git-lfs` on PATH. If either is missing, abort with a remediation hint and exit code 2.

## Steps

### Step 0 — Preflight

- Verify `git` and `git-lfs` are on PATH. If not, abort with: *"Git bootstrap needs `git` and `git-lfs`. Install with `brew install git-lfs` (macOS) or your package manager, then re-run."*
- Resolve `WORKSPACE_ROOT` to absolute path.
- Create `.pka/` if absent (the base bootstrap may have done this; either way ensure it exists).

### Step 1 — Install templates

For each:
- `bootstrap-assets/gitattributes-template` → `.pka/gitattributes-template`
- `bootstrap-assets/gitignore-template`     → `.pka/gitignore-template`

Logic: if destination exists, leave it alone (count as "already present" in summary). Otherwise, copy.

### Step 2 — Install helper scripts

For each script in `bootstrap-assets/scripts/*.sh`:
- Copy to `.pka/<basename>` if absent.
- Set executable bit (`chmod +x`).
- If destination already exists, count as "already present" — do not overwrite.

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

# Local artifacts
.pka/knowledge.db
.pka/knowledge.db-*
.pka/*-log.txt
.pka/graduate-backups/

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

Stage all root-tracked changes (the `.gitignore`, `.pka/` scaffolding, etc.) with `git add -A`. **Do not commit.** The root commit is the user's first review gate — they do it manually.

If `./.git` already exists, leave it alone. Stage any newly-created scaffolding so the working tree shows what's ready for review.

### Step 6 — `knowledge/.git` (initialize with LFS)

```
if directory_exists("./knowledge") AND not directory_exists("./knowledge/.git"):
    cp .pka/gitattributes-template knowledge/.gitattributes  # (only if absent)
    merge .pka/gitignore-template into knowledge/.gitignore  # (line-merge)
    cd knowledge
    git init -b main
    git lfs install --local
    git add -A
    git commit -m "Bootstrap (git): Initial hybrid monorepo setup" \
              -m "" \
              -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

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

Empty origins indicate placeholder remotes — the user populates these later when they decide on a remote topology. The auto-push at session end **skips** child repos with empty origins, reporting them as skipped (not failed).

If `.meta` already exists, regenerate from current state (entries may have been added or removed since last run). The format must be deterministic so re-running on identical state produces an identical file.

### Step 9 — Stage root scaffolding

Final pass: `git add -A` in the root to stage anything Steps 1–8 produced. List the staged files in the summary so the user knows what's awaiting their review.

### Step 10 — Summary

Print to the user:

```
Hybrid monorepo bootstrap complete.

Templates installed:        N (M already present)
Helper scripts installed:   N (M already present)
Shared reference seeded:    .pka/roles/_git-protocol.md (or "already present")
Root .gitignore:            created / augmented (lines added: K)

Root repo:                  initialized (uncommitted, awaiting your review)
                            OR  already present
knowledge/:                 initialized with LFS (initial commit made)
                            OR  already present
                            OR  flagged: has .git but no LFS — see reinit-project-with-lfs.sh
Projects initialized:       N
Projects flagged:           M (have .git but no LFS — listed below)
  - projects/<name>: run .pka/reinit-project-with-lfs.sh projects/<name> to opt into LFS (DESTRUCTIVE)
.meta manifest:             generated/updated with K entries

Root working-tree changes STAGED for your review:
  - .gitignore
  - .meta
  - .pka/...
  ...

Next steps:
  1. git status / git diff --cached  to review staged changes
  2. git commit  to lock in the scaffolding
  3. Set origin URLs in .meta when you've decided remote topology
  4. .pka/push-all.sh  whenever you're ready to push
```

## Failure modes

- **Missing binaries** (Step 0): abort with hint, exit 2.
- **Templates missing in `bootstrap-assets/`**: bug in this plugin, abort with diagnostic.
- **Filesystem permission errors**: abort with the path that failed and the OS error.
- **`git init` fails**: surface the git error verbatim. Do not retry destructively.
- **LFS install fails for one child**: report the specific child, continue with others.

All failures land in the summary; partial successes are not reverted.

## What NOT to do

- Do not call `curl`, `wget`, or any HTTP client.
- Do not call `git push`, `git fetch`, or any remote-aware git command.
- Do not auto-commit the root repo. Period.
- Do not reinit a child repo that already has `.git`. Even if it lacks LFS — flag instead.
- Do not modify files in `team-inbox/`, `owner-inbox/`, or any user-content directory beyond the scaffolding listed above.
- Do not remove origin URLs that already exist in child repo configs — preserve them and reflect them in `.meta`.

## Idempotency check

After running the bootstrap, immediately re-running it must produce no further file changes. Confirm this in tests (see `pka-skills/tests/`).
