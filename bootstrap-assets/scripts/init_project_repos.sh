#!/usr/bin/env bash
# init_project_repos.sh — initialize git+LFS in child repos that lack `.git`.
#
# Operates on the current directory as the workspace root. For each of:
#   - knowledge/
#   - projects/*/ (every immediate subdirectory of projects/)
# if the directory exists and lacks `.git`, it:
#   1. Copies .pka/gitattributes-template -> <child>/.gitattributes (if absent)
#   2. Merges .pka/gitignore-template into <child>/.gitignore (lines, not replace)
#   3. Runs `git init -b main` in <child>
#   4. Runs `git lfs install --local` in <child>
#   5. Stages everything and creates the initial commit
#
# Idempotent: child repos that already have `.git` are skipped silently and
# reported in the summary. Never sets origin remotes. Never pushes.
#
# Exit codes:
#   0  success (any combination of init / skip)
#   1  workspace-level precondition failure (no .pka/, missing templates)
#   2  git or git-lfs binary missing

set -u

WORKSPACE_ROOT="${WORKSPACE_ROOT:-$(pwd)}"
PKA_DIR="${WORKSPACE_ROOT}/.pka"
GITATTR_TEMPLATE="${PKA_DIR}/gitattributes-template"
GITIGNORE_TEMPLATE="${PKA_DIR}/gitignore-template"

# Trailer (verbatim per _git-protocol.md)
COAUTHOR_TRAILER="Co-Authored-By: Claude <noreply@anthropic.com>"
COMMIT_MESSAGE="Bootstrap (git): Initial hybrid monorepo setup"

INITIALIZED=()
SKIPPED=()
LFS_FLAGGED=()

require_binary() {
  local bin="$1"
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "ERROR: required binary '$bin' not found on PATH." >&2
    exit 2
  fi
}

require_binary git
require_binary git-lfs

if [ ! -d "$PKA_DIR" ]; then
  echo "ERROR: $PKA_DIR not found. Run pka-bootstrap with target 'git' or 'all' first." >&2
  exit 1
fi

if [ ! -f "$GITATTR_TEMPLATE" ] || [ ! -f "$GITIGNORE_TEMPLATE" ]; then
  echo "ERROR: bootstrap templates missing in $PKA_DIR." >&2
  echo "Expected: $GITATTR_TEMPLATE and $GITIGNORE_TEMPLATE" >&2
  exit 1
fi

merge_gitignore() {
  local target="$1"
  if [ ! -f "$target" ]; then
    cp "$GITIGNORE_TEMPLATE" "$target"
    return
  fi
  # Append only lines from template not already present (line-exact match).
  while IFS= read -r line; do
    if [ -z "$line" ] || [ "${line:0:1}" = "#" ]; then
      continue
    fi
    if ! grep -qxF -- "$line" "$target" 2>/dev/null; then
      echo "$line" >> "$target"
    fi
  done < "$GITIGNORE_TEMPLATE"
}

has_lfs_filters() {
  local repo_dir="$1"
  [ -f "${repo_dir}/.gitattributes" ] && grep -q "filter=lfs" "${repo_dir}/.gitattributes" 2>/dev/null
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

  # Copy templates (don't overwrite if user-authored already)
  if [ ! -f "${repo_abs}/.gitattributes" ]; then
    cp "$GITATTR_TEMPLATE" "${repo_abs}/.gitattributes"
  fi
  merge_gitignore "${repo_abs}/.gitignore"

  (
    cd "$repo_abs"
    git init -b main >/dev/null 2>&1
    git lfs install --local >/dev/null 2>&1
    git add -A
    # If there's nothing staged (empty repo), still create an initial commit so
    # the branch ref exists.
    if git diff --cached --quiet; then
      git commit --allow-empty -m "$COMMIT_MESSAGE" -m "" -m "$COAUTHOR_TRAILER" >/dev/null
    else
      git commit -m "$COMMIT_MESSAGE" -m "" -m "$COAUTHOR_TRAILER" >/dev/null
    fi
  )

  INITIALIZED+=("$repo_rel")
}

# knowledge/ first
init_one "knowledge"

# projects/*/
if [ -d "${WORKSPACE_ROOT}/projects" ]; then
  shopt -s nullglob
  for proj in "${WORKSPACE_ROOT}"/projects/*/; do
    rel="projects/$(basename "$proj")"
    init_one "$rel"
  done
  shopt -u nullglob
fi

# Summary
echo "init_project_repos.sh summary"
echo "---------------------------------"
echo "Initialized:        ${#INITIALIZED[@]}"
for r in "${INITIALIZED[@]:-}"; do [ -n "$r" ] && echo "  + $r"; done
echo "Already initialized: ${#SKIPPED[@]}"
for r in "${SKIPPED[@]:-}"; do [ -n "$r" ] && echo "  = $r"; done
if [ ${#LFS_FLAGGED[@]} -gt 0 ]; then
  echo "LFS-missing (flagged, NOT modified):"
  for r in "${LFS_FLAGGED[@]}"; do
    echo "  ! $r — has .git but no LFS filters; run reinit-project-with-lfs.sh ${r#projects/} to opt in (DESTRUCTIVE)"
  done
fi

exit 0
