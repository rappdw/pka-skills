# bootstrap-assets

Templates and scripts that `pka-bootstrap` installs into a target workspace's `.pka/` directory when the user runs `bootstrap git` (or `bootstrap all`).

These are **vendored** here so the bootstrap works for any user without reading from anyone's personal workspace at runtime.

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

- No script makes network calls. No `curl`, no `git push` of remote URLs that didn't already exist.
- `init_project_repos.sh` and `build-repo-list.sh` are **idempotent**: re-running on the same workspace state produces the same final state.
- `init_project_repos.sh` does **not** reinit existing child repos. Projects that have `.git` but no LFS are listed in the summary as reinit candidates.
- `reinit-project-with-lfs.sh` is destructive and requires a typed confirmation. Never runs unattended.
- `graduate.sh` backs up the project's `.git` to `.pka/graduate-backups/` before deletion.
- `graduate.sh` commits in `knowledge/` (child repo) but only **stages** root-repo changes — never commits root.

## Notes for implementers

- Scripts assume `WORKSPACE_ROOT=$(pwd)` unless the env var `WORKSPACE_ROOT` overrides.
- All commit messages follow the structure in `.pka/roles/_git-protocol.md`:
  ```
  <Role>: <description>

  Co-Authored-By: Claude <noreply@anthropic.com>
  ```
- Scripts require `git` and `git-lfs` on PATH; they fail loudly with exit code 2 when missing.
