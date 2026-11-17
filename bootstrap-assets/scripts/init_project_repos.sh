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
#   5. Stages everything and creates the initial commits (with role prefix and
#      Co-Authored-By: Claude trailer)
#
# Never modified:
#   - child repos that already have a `.git` directory. With LFS configured
#     (`.gitattributes` contains `filter=lfs`) they are reported as
#     already-present; without it, as a REINIT CANDIDATE.
#   - children whose `.git` is a file (linked worktree or submodule): their
#     history lives elsewhere.
#   - children that are symbolic links: the repo they point at is not ours.
#
# A child whose init or commit fails is reported under "Failed", the half-made
# `.git` this run created is removed so a re-run starts clean, and the script
# exits 1 after processing the remaining children.
#
# Origin remotes: NEVER set by this script. The user decides remote topology.
# An optional `ORIGIN_BASE` environment variable may be set by the caller to
# add an origin URL on initialization (e.g., `ORIGIN_BASE='git@host:user/' \
# init_project_repos.sh`); when unset, no origin is added (no-network default).
#
# Exit codes:
#   0  success (any combination of init / skip / flag)
#   1  workspace-level precondition failure, or at least one child failed
#   2  required binary missing on PATH, or git older than 2.28

set -uo pipefail

# --- preflight: required binaries ---
for cmd in git git-lfs; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: '$cmd' not found on PATH. Install it and re-run." >&2
    exit 2
  fi
done

# `git init -b` needs git 2.28 or newer. On older versions the init fails and
# the commands that follow would run against whatever repository encloses the
# child — so stop here instead.
git_version_ok() {
  local v major rest minor
  v=$(git version 2>/dev/null | awk '{print $3}')
  major=${v%%.*}; rest=${v#*.}; minor=${rest%%.*}
  case "${major}${minor}" in ""|*[!0-9]*) return 1 ;; esac
  [ "$major" -gt 2 ] || { [ "$major" -eq 2 ] && [ "$minor" -ge 28 ]; }
}
if ! git_version_ok; then
  echo "ERROR: git 2.28 or newer is required (found: $(git version 2>/dev/null || echo unknown))." >&2
  exit 2
fi

# --- workspace resolution: WORKSPACE_ROOT env var, else $(pwd) ---
WORKSPACE_ROOT="${WORKSPACE_ROOT:-$(pwd)}"
if [ ! -d "$WORKSPACE_ROOT" ]; then
  echo "ERROR: workspace root $WORKSPACE_ROOT is not a directory." >&2
  exit 1
fi
WORKSPACE_ROOT=$(cd "$WORKSPACE_ROOT" && pwd -P) || exit 1
PKA_DIR="${WORKSPACE_ROOT}/.pka"
GITATTR_TEMPLATE="${PKA_DIR}/gitattributes-template"
GITIGNORE_TEMPLATE="${PKA_DIR}/gitignore-template"

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

# The commits below need an identity; without one every child would fail.
if ! git var GIT_COMMITTER_IDENT >/dev/null 2>&1; then
  echo "ERROR: git has no usable identity for commits. Set user.name and user.email, then re-run." >&2
  exit 1
fi

# Empty git template suppresses the default hooks/info clutter on init. It
# lives in a private temporary directory that is removed on exit.
WORK_TMP=$(mktemp -d "${TMPDIR:-/tmp}/pka-init.XXXXXX") || exit 1
trap 'rm -rf "$WORK_TMP"' EXIT
EMPTY_GIT_TEMPLATE="${WORK_TMP}/empty-template"
mkdir "$EMPTY_GIT_TEMPLATE" || exit 1

INITIALIZED=()
SKIPPED=()
LFS_FLAGGED=()
NOT_OURS=()
FAILED=()

slugify() {
  echo "$1" | tr '[:upper:]' '[:lower:]' | tr ' ' '-' \
    | sed 's/[^a-z0-9_-]//g' | sed 's/--*/-/g' | sed 's/^-//;s/-$//'
}

# Append template lines that are missing from an existing .gitignore. The file
# is never replaced, and a missing final newline is repaired first so the
# first appended line cannot fuse with the user's last pattern.
merge_gitignore() {
  local target="$1" line
  if [ ! -f "$target" ]; then
    cp "$GITIGNORE_TEMPLATE" "$target"
    return
  fi
  if [ -s "$target" ] && [ -n "$(tail -c 1 "$target")" ]; then
    printf '\n' >> "$target" || return 1
  fi
  while IFS= read -r line || [ -n "$line" ]; do
    [ -z "$line" ] && continue
    [ "${line:0:1}" = "#" ] && continue
    if ! grep -qxF -- "$line" "$target" 2>/dev/null; then
      printf '%s\n' "$line" >> "$target" || return 1
    fi
  done < "$GITIGNORE_TEMPLATE"
  return 0
}

# Detect LFS by looking for a `filter=lfs` line in the repo's .gitattributes.
# We deliberately do NOT use `git config --get-regexp filter.lfs.*`:
# git-lfs is typically installed system-wide which sets those keys in the
# global config, giving a false positive on every repo. The .gitattributes
# signal reflects what the repo *intends* to LFS-track and is the canonical
# input to git-lfs's filters.
has_lfs_filters() {
  local repo_dir="$1"
  [ -f "${repo_dir}/.gitattributes" ] && grep -q 'filter=lfs' "${repo_dir}/.gitattributes" 2>/dev/null
}

commit_with_trailer() {
  # Args: <repo_dir> <subject>. Returns git's exit status.
  local repo="$1" subject="$2"
  local msg
  msg=$(printf '%s\n\n%s\n' "$subject" "$COAUTHOR_TRAILER")
  if git -C "$repo" diff --cached --quiet; then
    git -C "$repo" commit --allow-empty -q -m "$msg"
  else
    git -C "$repo" commit -q -m "$msg"
  fi
}

# Record a failed child and remove the `.git` this run created for it, so the
# next run retries instead of reporting it as already initialized.
fail_child() {
  local repo_rel="$1" repo_abs="$2" reason="$3" created_git="$4"
  echo "ERROR: ${repo_rel}: ${reason}" >&2
  if [ "$created_git" -eq 1 ] && [ -d "${repo_abs}/.git" ] && [ ! -L "${repo_abs}/.git" ]; then
    rm -rf "${repo_abs}/.git"
  fi
  FAILED+=("${repo_rel}: ${reason}")
}

init_one() {
  local repo_rel="$1"
  local repo_abs="${WORKSPACE_ROOT}/${repo_rel}"

  if [ -L "$repo_abs" ]; then
    NOT_OURS+=("${repo_rel}: symbolic link")
    return
  fi
  if [ ! -d "$repo_abs" ]; then
    return
  fi

  if [ -L "${repo_abs}/.git" ] || { [ -e "${repo_abs}/.git" ] && [ ! -d "${repo_abs}/.git" ]; }; then
    NOT_OURS+=("${repo_rel}: .git is a file or link (linked worktree or submodule)")
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
    cp "$GITATTR_TEMPLATE" "${repo_abs}/.gitattributes" \
      || { fail_child "$repo_rel" "$repo_abs" "could not write .gitattributes" 0; return; }
  fi
  merge_gitignore "${repo_abs}/.gitignore" \
    || { fail_child "$repo_rel" "$repo_abs" "could not write .gitignore" 0; return; }

  if ! git -C "$repo_abs" init -b main --template="$EMPTY_GIT_TEMPLATE" -q; then
    fail_child "$repo_rel" "$repo_abs" "'git init' failed" 1
    return
  fi
  # Every later command uses `git -C <child>`. If the init did not take, those
  # would act on an enclosing repository (the workspace root), so verify that
  # the child really is its own repository before going on.
  local top top_real="" child_real
  top=$(git -C "$repo_abs" rev-parse --show-toplevel 2>/dev/null) || top=""
  [ -n "$top" ] && top_real=$(cd "$top" 2>/dev/null && pwd -P)
  child_real=$(cd "$repo_abs" && pwd -P)
  if [ -z "$top_real" ] || [ "$top_real" != "$child_real" ]; then
    fail_child "$repo_rel" "$repo_abs" "'git init' did not create a repository here" 0
    return
  fi

  if ! git -C "$repo_abs" lfs install --local >/dev/null; then
    fail_child "$repo_rel" "$repo_abs" "'git lfs install --local' failed" 1
    return
  fi

  # Optional, opt-in origin via ORIGIN_BASE — never set by default.
  if [ -n "${ORIGIN_BASE:-}" ]; then
    local slug
    slug=$(slugify "$(basename "$repo_abs")")
    if ! git -C "$repo_abs" remote add origin "${ORIGIN_BASE}${slug}.git"; then
      fail_child "$repo_rel" "$repo_abs" "could not add the origin remote" 1
      return
    fi
  fi

  # Two-commit pattern: first the LFS config, then the rest. Keeps the LFS
  # filter setup auditable as its own commit.
  if ! git -C "$repo_abs" add -- .gitattributes .gitignore; then
    fail_child "$repo_rel" "$repo_abs" "'git add' failed" 1
    return
  fi
  if ! commit_with_trailer "$repo_abs" "$LFS_COMMIT_SUBJECT"; then
    fail_child "$repo_rel" "$repo_abs" "'git commit' failed (see the message above)" 1
    return
  fi
  # The whole directory is this new repository's content, so everything in it
  # is staged.
  if ! git -C "$repo_abs" add -A; then
    fail_child "$repo_rel" "$repo_abs" "'git add' failed" 1
    return
  fi
  if ! git -C "$repo_abs" diff --cached --quiet; then
    if ! commit_with_trailer "$repo_abs" "$INIT_COMMIT_SUBJECT"; then
      fail_child "$repo_rel" "$repo_abs" "'git commit' failed (see the message above)" 1
      return
    fi
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
    echo "  ! $r — run '.pka/reinit-project-with-lfs.sh $r' to opt in (replaces the history; the old repo is kept as a backup)"
  done
fi
if [ ${#NOT_OURS[@]} -gt 0 ]; then
  echo "Left alone (repository lives elsewhere — NOT modified):"
  for r in "${NOT_OURS[@]}"; do echo "  - $r"; done
fi
if [ ${#FAILED[@]} -gt 0 ]; then
  echo "Failed:              ${#FAILED[@]}"
  for r in "${FAILED[@]}"; do echo "  x $r"; done
  echo "Fix the cause and re-run; failed children were left without a .git."
  exit 1
fi

# Note: This script does NOT print Gitea/GitHub-specific NEXT STEPS.
# Remote topology, repo creation, and pushing are user decisions made after
# bootstrap, not vendored helper concerns.

exit 0
