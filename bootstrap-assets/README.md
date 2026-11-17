# bootstrap-assets

Templates and scripts that `pka-bootstrap` installs into a target workspace's `.pka/` directory when the user runs `bootstrap git` (or `bootstrap all`).

These are **vendored** here so the bootstrap works for any user without reading from anyone's personal workspace at runtime. The scripts started as user-proven versions from a real PKA workspace and have been adjusted to remove user-specific topology (no hardcoded Gitea hosts, no embedded `/home/<user>/...` paths) and to enforce the contract below.

## What gets installed where

| Source (in this repo)                    | Destination in user workspace      |
|------------------------------------------|------------------------------------|
| `gitattributes-template`                 | `.pka/gitattributes-template`      |
| `gitignore-template`                     | `.pka/gitignore-template`          |
| `scripts/graduate.sh`                    | `.pka/graduate.sh`                 |
| `scripts/init_project_repos.sh`          | `.pka/init_project_repos.sh`       |
| `scripts/reinit-project-with-lfs.sh`     | `.pka/reinit-project-with-lfs.sh`  |
| `scripts/push-all.sh`                    | `.pka/push-all.sh`                 |
| `scripts/build-repo-list.sh`             | `.pka/build-repo-list.sh`          |
| `scripts/upgrade-roles.py`               | `.pka/upgrade-roles.py`            |

## Hard guarantees

- **No network calls.** No `curl`, no `git push` of remote URLs that didn't already exist, no API calls to forges.
- **No hardcoded user-specific topology.** No script embeds a single user's host, organization, or filesystem layout. Origin remotes are user choices, not bootstrap choices.
- **Nothing is deleted.** `graduate.sh` and `reinit-project-with-lfs.sh` *move* the existing `.git` directory, whole, to `.pka/graduate-backups/` or `.pka/reinit-backups/` before doing anything else. That is the complete repository: every branch, the stash, the config and all LFS objects. `git clone <backup path>` restores the history. Both backup directories carry a `.gitignore` containing `*`, so they never appear as changes in the root repo.
- **Failures roll back.** Every `git init`, `git lfs install`, `git add` and `git commit` result is checked. If a step fails after work has started, `graduate.sh` and `reinit-project-with-lfs.sh` put the repository, the moved files and any rewritten files back as they were and exit 1. `init_project_repos.sh` removes the half-made `.git` of the child that failed, carries on with the others, and exits 1.
- **Targets are validated before anything is touched.** `graduate.sh` takes a single folder name under `projects/`; `reinit-project-with-lfs.sh` takes `knowledge` or `projects/<name>`. Empty strings, `.`, `..`, absolute paths and paths with `..` are usage errors (exit 64). Symbolic links, and children whose `.git` is a file (linked worktree, submodule), are refused or skipped: their repository lives elsewhere.
- **Commits are staged by path.** `graduate.sh` commits only the graduated project and the `_MOC.md` files it rewrote. Other modified, staged or untracked files in `knowledge/` are left exactly as they were.
- `init_project_repos.sh` and `build-repo-list.sh` are **idempotent**: re-running on the same workspace state produces the same final state.
- `init_project_repos.sh` does **not** reinit existing child repos. Projects that have `.git` but no LFS are listed in the summary as **reinit candidates** (detected by a `filter=lfs` line in the repo's `.gitattributes`).
- `reinit-project-with-lfs.sh` requires a typed-confirmation gate (the user must type the project basename). Pass `--yes`/`-y` only when an upstream caller has already collected explicit consent. Never runs unattended without that flag. All remotes (not just `origin`) are carried over to the new repository; an existing `.gitattributes` gets the LFS filter lines merged in.
- `graduate.sh` commits in `knowledge/` (child repo) but only **stages** root-repo changes — never commits root.
- **`.meta` is derived from the repos.** `build-repo-list.sh` rebuilds the "projects" map from each child's real `origin` remote (other top-level keys are preserved; an invalid `.meta` is left untouched and reported). `push-all.sh` pushes by the child repo's own remote and points out when `.meta` is out of date. Set remotes with `git -C <child> remote add origin <url>`, then re-run `build-repo-list.sh`.

## Notes for users

### Optional opt-in: setting an origin during init

`init_project_repos.sh` does **not** set an `origin` remote by default. To opt in for a session:

```bash
ORIGIN_BASE='git@host.example.com:myorg/' bash .pka/init_project_repos.sh
```

This sets each newly-initialized child repo's origin to `${ORIGIN_BASE}<slug>.git`, where `<slug>` is the slugified project name. When `ORIGIN_BASE` is unset (the default), no origin is added.

This is the only place a script touches remote topology. The repo URL convention, the host, and the org are all the user's choice.

### Bulk reinit

There is intentionally no `reinit-all-projects.sh` script. Bulk reinit is handled by `pka-bootstrap` itself (which collects consent for each candidate and then invokes `reinit-project-with-lfs.sh --yes <path>` per project). This keeps the per-project script as the single primitive.

## Notes for implementers

- Scripts assume `WORKSPACE_ROOT=$(pwd)` unless the env var `WORKSPACE_ROOT` overrides. They never use `$(dirname "$0")` to resolve workspace paths (so they work whether vendored to `.pka/` or invoked from a temp dir during testing).
- All commit messages follow the structure in `.pka/roles/_git-protocol.md`:
  ```
  <Role>: <description>

  Co-Authored-By: Claude <noreply@anthropic.com>
  ```
- Scripts require `git`, `git-lfs`, and (for the JSON-aware ones) `python3` on PATH. Each script does a preflight check at the top and exits with code 2 if a binary is missing. The scripts that run `git init -b` also require git 2.28 or newer and exit 2 on anything older.
- Scripts target bash 3.2 (the version macOS ships) as well as current bash: no associative arrays, no `mapfile`, no `${var,,}`.
- Scripts use the `--template=<empty>` trick on `git init` to suppress the default sample hooks. The empty template lives in a private `mktemp -d` directory that is removed when the script exits; nothing is written to a fixed path under `${TMPDIR}`.
- Every fix in these scripts has a regression test in `tests/test_script_safety.sh`. Add one when you change behaviour.

## Change log vs. user's source workspace

| File                              | Change                                                                                                                |
|-----------------------------------|-----------------------------------------------------------------------------------------------------------------------|
| `graduate.sh`                     | Backup target moved from `knowledge/.graduated/` to `.pka/graduate-backups/` (out of the knowledge repo).             |
| `graduate.sh`                     | Removed root-repo auto-commit. Root .meta change is staged only.                                                      |
| `graduate.sh`                     | Removed Gitea-specific archival URL; printed instructions are forge-agnostic.                                          |
| `graduate.sh`                     | Commit messages use `Graduate: <name> → knowledge/<subdir>/` with Co-Authored-By: Claude trailer.                      |
| `init_project_repos.sh`           | Removed hardcoded `ssh://git@git.thatsarapp.org:9022/PKA/...` origin. Origin set only when `ORIGIN_BASE` env is given. |
| `init_project_repos.sh`           | Added LFS detection for existing `.git` repos; flagged as reinit candidates without modification.                      |
| `init_project_repos.sh`           | Removed Gitea-specific `NEXT STEPS` output block.                                                                     |
| `init_project_repos.sh`           | Commit messages use `Bootstrap (git):` prefix with trailer.                                                            |
| `reinit-project-with-lfs.sh`      | Added typed-confirmation gate (`--yes`/`-y` to bypass).                                                                |
| `reinit-project-with-lfs.sh`      | Replaced hardcoded `/home/claude/pka/...` template paths with `$WORKSPACE_ROOT/.pka/...`.                              |
| `reinit-project-with-lfs.sh`      | Added preflight binary check (exit 2 on missing git/git-lfs).                                                          |
| `reinit-project-with-lfs.sh`      | Commit messages use `Bootstrap (git):` prefix with trailer.                                                            |
| All scripts                       | Resolve workspace via `${WORKSPACE_ROOT:-$(pwd)}` rather than `$(dirname "$0")`.                                       |

These changes resolve every gap flagged in the source workspace's `gaps.md`.

## Changes in v1.6.3

| File                              | Change                                                                                                                |
|-----------------------------------|-----------------------------------------------------------------------------------------------------------------------|
| `graduate.sh`                     | Backup is the moved `.git` directory (complete, includes LFS objects) instead of a `git bundle`; the old code deleted `.git` even when the bundle had not been written. |
| `graduate.sh`                     | Validates the project name and subdir; refuses symlinks and `.git` files; stages and commits by path; rolls back on a failed commit. |
| `reinit-project-with-lfs.sh`      | Accepts only `knowledge` or `projects/<name>`; keeps the old repository as a backup; merges LFS filters into an existing `.gitattributes`; preserves all remotes; rolls back on failure. |
| `init_project_repos.sh`           | Requires git 2.28+; checks identity up front; verifies each `git init`; reports and cleans up failed children; skips symlinks and `.git` files; repairs a missing final newline before appending to `.gitignore`. |
| `push-all.sh`                     | Uses the child repo's real `origin` remote rather than the URL recorded in `.meta`; reports the two disagreeing.        |
| `build-repo-list.sh`              | Writes `.meta` with a JSON library, atomically; preserves other top-level keys; refuses to overwrite invalid JSON.      |
| `upgrade-roles.py`                | Ignores headings inside fenced code blocks; preserves CRLF; warns when no anchor heading was found; unique backup names. |
