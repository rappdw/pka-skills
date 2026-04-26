#!/usr/bin/env bash
# init_project_repos.sh — initialize git+LFS in child repos that lack `.git`.
#
# Operates on the workspace root (resolved via $WORKSPACE_ROOT or $(pwd)).
# For each of:
#   - knowledge/
#   - projects/*/ (every immediate subdirectory of projects/)
# if the directory exists and lacks `.git`, it:
#   1. Copies .pka/gitattributes-template -> <child>/.gitattributes (if absent)
#   2. Merges .pka/gitignore-template into <child>/.gitignore (line-merge,
#      never replaces an existing file)
#   3. Runs `git init -b main` in <child>
#   4. Runs `git lfs install --local` in <child>
#   5. Stages everything and creates the initial commit (with role prefix and
#      Co-Authored-By: Claude trailer)
#
# Idempotency: child repos that already have `.git` are skipped.
#   - If LFS is configured (`.gitattributes` contains `filter=lfs`) → reported as already-present.
#   - If `.git` exists but no LFS → reported as a REINIT CANDIDATE (P3 — never modified).
#
# Origin remotes: NEVER set by this script. The user decides remote topology.
# An optional `ORIGIN_BASE` environment variable may be set by the caller to
# add an origin URL on initialization (e.g., `ORIGIN_BASE='git@host:user/' \
# init_project_repos.sh`); when unset, no origin is added (no-network default).
#
# Exit codes:
#   0  success (any combination of init / skip / flag)
#   1  workspace-level precondition failure (no .pka/, missing templates)
#   2  required binary (`git` / `git-lfs`) missing on PATH

set -uo pipefail

# --- preflight: required binaries (P5) ---
for cmd in git git-lfs; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: '$cmd' not found on PATH. Install it and re-run." >&2
    exit 2
  fi
done

# --- workspace resolution (P1): WORKSPACE_ROOT env var, else $(pwd) ---
WORKSPACE_ROOT="${WORKSPACE_ROOT:-$(pwd)}"
PKA_DIR="${WORKSPACE_ROOT}/.pka"
GITATTR_TEMPLATE="${PKA_DIR}/gitattributes-template"
GITIGNORE_TEMPLATE="${PKA_DIR}/gitignore-template"
EMPTY_GIT_TEMPLATE="${TMPDIR:-/tmp}/pka-empty-git-template"

# Trailer (verbatim per .pka/roles/_git-protocol.md)
COAUTHOR_TRAILER="Co-Authored-By: Claude <noreply@anthropic.com>"
INIT_COMMIT_SUBJECT="Bootstrap (git): Initial hybrid monorepo setup"
LFS_COMMIT_SUBJECT="Bootstrap (git): Configure LFS tracking and .gitignore"

if [ ! -d "$PKA_DIR" ]; then
  echo "ERROR: $PKA_DIR not found. Run pka-bootstrap with target 'git' or 'all' first." >&2
  exit 1
fi
if [ ! -f "$GITATTR_TEMPLATE" ] || [ ! -f "$GITIGNORE_TEMPLATE" ]; then
  echo "ERROR: bootstrap templates missing in $PKA_DIR." >&2
  echo "Expected: $GITATTR_TEMPLATE and $GITIGNORE_TEMPLATE" >&2
  exit 1
fi

# Empty git template suppresses the default hooks/info clutter on init.
mkdir -p "$EMPTY_GIT_TEMPLATE"

INITIALIZED=()
SKIPPED=()
LFS_FLAGGED=()

slugify() {
  echo "$1" | tr '[:upper:]' '[:lower:]' | tr ' ' '-' \
    | sed 's/[^a-z0-9_-]//g' | sed 's/--*/-/g' | sed 's/^-//;s/-$//'
}

merge_gitignore() {
  local target="$1"
  if [ ! -f "$target" ]; then
    cp "$GITIGNORE_TEMPLATE" "$target"
    return
  fi
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    [ "${line:0:1}" = "#" ] && continue
    if ! grep -qxF -- "$line" "$target" 2>/dev/null; then
      echo "$line" >> "$target"
    fi
  done < "$GITIGNORE_TEMPLATE"
}

# Detect LFS by looking for a `filter=lfs` line in the repo's .gitattributes
# (P3). We deliberately do NOT use `git config --get-regexp filter.lfs.*`:
# git-lfs is typically installed system-wide which sets those keys in the
# global config, giving a false positive on every repo. The .gitattributes
# signal reflects what the repo *intends* to LFS-track and is the canonical
# input to git-lfs's filters.
has_lfs_filters() {
  local repo_dir="$1"
  [ -f "${repo_dir}/.gitattributes" ] && grep -q 'filter=lfs' "${repo_dir}/.gitattributes" 2>/dev/null
}

commit_with_trailer() {
  # Args: <repo_dir> <subject>. Reads no body.
  local repo="$1" subject="$2"
  local msg
  msg=$(printf '%s\n\n%s\n' "$subject" "$COAUTHOR_TRAILER")
  if git -C "$repo" diff --cached --quiet; then
    git -C "$repo" commit --allow-empty -q -m "$msg"
  else
    git -C "$repo" commit -q -m "$msg"
  fi
}

init_one() {
  local repo_rel="$1"
  local repo_abs="${WORKSPACE_ROOT}/${repo_rel}"

  if [ ! -d "$repo_abs" ]; then
    return
  fi

  if [ -d "${repo_abs}/.git" ]; then
    if has_lfs_filters "$repo_abs"; then
      SKIPPED+=("$repo_rel")
    else
      LFS_FLAGGED+=("$repo_rel")
    fi
    return
  fi

  echo "Initializing: $repo_rel"

  # Templates: don't overwrite a user-authored .gitattributes/.gitignore.
  if [ ! -f "${repo_abs}/.gitattributes" ]; then
    cp "$GITATTR_TEMPLATE" "${repo_abs}/.gitattributes"
  fi
  merge_gitignore "${repo_abs}/.gitignore"

  git -C "$repo_abs" init -b main --template="$EMPTY_GIT_TEMPLATE" -q
  git -C "$repo_abs" lfs install --local >/dev/null

  # Optional, opt-in origin via ORIGIN_BASE — never set by default (C3).
  if [ -n "${ORIGIN_BASE:-}" ]; then
    local slug
    slug=$(slugify "$(basename "$repo_abs")")
    git -C "$repo_abs" remote add origin "${ORIGIN_BASE}${slug}.git"
  fi

  # Two-commit pattern: first the LFS config, then the rest. Keeps the LFS
  # filter setup auditable as its own commit.
  git -C "$repo_abs" add .gitattributes .gitignore
  commit_with_trailer "$repo_abs" "$LFS_COMMIT_SUBJECT"
  git -C "$repo_abs" add -A
  if ! git -C "$repo_abs" diff --cached --quiet; then
    commit_with_trailer "$repo_abs" "$INIT_COMMIT_SUBJECT"
  fi

  INITIALIZED+=("$repo_rel")
}

# --- main loop ---
init_one "knowledge"

if [ -d "${WORKSPACE_ROOT}/projects" ]; then
  shopt -s nullglob
  for proj in "${WORKSPACE_ROOT}"/projects/*/; do
    rel="projects/$(basename "$proj")"
    init_one "$rel"
  done
  shopt -u nullglob
fi

# --- summary ---
echo
echo "init_project_repos.sh summary"
echo "---------------------------------"
echo "Initialized:         ${#INITIALIZED[@]}"
for r in "${INITIALIZED[@]:-}"; do [ -n "$r" ] && echo "  + $r"; done
echo "Already initialized: ${#SKIPPED[@]}"
for r in "${SKIPPED[@]:-}"; do [ -n "$r" ] && echo "  = $r"; done
if [ ${#LFS_FLAGGED[@]} -gt 0 ]; then
  echo "Reinit candidates (have .git but no LFS — NOT modified):"
  for r in "${LFS_FLAGGED[@]}"; do
    echo "  ! $r — run './reinit-project-with-lfs.sh $r' to opt in (DESTRUCTIVE)"
  done
fi

# Note: This script does NOT print Gitea/GitHub-specific NEXT STEPS (V2).
# Remote topology, repo creation, and pushing are user decisions made after
# bootstrap, not vendored helper concerns.

exit 0
