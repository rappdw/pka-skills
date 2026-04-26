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

## Hard guarantees

- **No network calls.** No `curl`, no `git push` of remote URLs that didn't already exist, no API calls to forges.
- **No hardcoded user-specific topology.** No script embeds a single user's host, organization, or filesystem layout. Origin remotes are user choices, not bootstrap choices.
- `init_project_repos.sh` and `build-repo-list.sh` are **idempotent**: re-running on the same workspace state produces the same final state.
- `init_project_repos.sh` does **not** reinit existing child repos. Projects that have `.git` but no LFS are listed in the summary as **reinit candidates** (detected via either `.gitattributes` `filter=lfs` or `git config filter.lfs.*`).
- `reinit-project-with-lfs.sh` is destructive and requires a typed-confirmation gate (the user must type the project basename). Pass `--yes`/`-y` only when an upstream caller has already collected explicit consent. Never runs unattended without that flag.
- `graduate.sh` saves the project's git history as a **portable `git bundle`** to `.pka/graduate-backups/` before deletion (so `git clone <bundle>` can restore the history later). For empty repos that can't be bundled, falls back to a tar of the `.git` directory.
- `graduate.sh` commits in `knowledge/` (child repo) but only **stages** root-repo changes — never commits root.

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
- Scripts require `git`, `git-lfs`, and (for the JSON-aware ones) `python3` on PATH. Each script does a preflight check at the top and exits with code 2 if a binary is missing.
- Scripts use the `--template=<empty>` trick on `git init` to suppress the default sample hooks. The empty template is created at `${TMPDIR}/pka-empty-git-template` on first run.

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
