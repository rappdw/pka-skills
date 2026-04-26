#!/usr/bin/env bash
# reinit-project-with-lfs.sh — DESTRUCTIVE: reinitialize a child repo's git
# history in order to add LFS filters from the start.
#
# Use only when a project has `.git` but no LFS configuration, and you accept
# losing its existing local commit history (back it up first if you care).
# The remote `origin` URL (if any) is preserved across the reinit; a separate
# `git push --force` to that origin is required to overwrite remote history.
#
# Usage:
#   reinit-project-with-lfs.sh [--yes|-y] <child-repo-relpath>
#
# Examples:
#   reinit-project-with-lfs.sh projects/legacy
#   reinit-project-with-lfs.sh -y projects/legacy   # bypass confirmation
#   reinit-project-with-lfs.sh knowledge
#
# C2: Without --yes, the script requires the user to type the basename of the
#     project as a confirmation before deleting .git. Default is abort.
#
# Exit codes:
#   0  success
#   1  user aborted, or precondition failure (no .git, missing templates)
#   2  required binary (`git` / `git-lfs`) missing on PATH
#  64  usage error

set -uo pipefail

# --- preflight (P5) ---
for cmd in git git-lfs; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: '$cmd' not found on PATH. Install it and re-run." >&2
    exit 2
  fi
done

# --- workspace + path resolution (P1, P2: no hardcoded /home/user paths) ---
WORKSPACE_ROOT="${WORKSPACE_ROOT:-$(pwd)}"
PKA_DIR="${WORKSPACE_ROOT}/.pka"
GITATTR_TEMPLATE="${PKA_DIR}/gitattributes-template"
GITIGNORE_TEMPLATE="${PKA_DIR}/gitignore-template"
EMPTY_GIT_TEMPLATE="${TMPDIR:-/tmp}/pka-empty-git-template"

COAUTHOR_TRAILER="Co-Authored-By: Claude <noreply@anthropic.com>"
LFS_COMMIT_SUBJECT="Bootstrap (git): Configure LFS tracking and .gitignore"
INIT_COMMIT_SUBJECT="Bootstrap (git): Reinit with LFS (history reset)"

# --- arg parsing ---
ASSUME_YES=0
if [ "${1:-}" = "--yes" ] || [ "${1:-}" = "-y" ]; then
  ASSUME_YES=1
  shift
fi

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 [--yes|-y] <child-repo-relpath>" >&2
  echo "Example: $0 projects/legacy" >&2
  exit 64
fi

REL="$1"
REPO_ABS="${WORKSPACE_ROOT}/${REL}"

if [ ! -d "${REPO_ABS}/.git" ]; then
  echo "ERROR: ${REL} has no .git directory; nothing to reinit." >&2
  exit 1
fi
if [ ! -f "$GITATTR_TEMPLATE" ] || [ ! -f "$GITIGNORE_TEMPLATE" ]; then
  echo "ERROR: bootstrap templates missing in ${PKA_DIR}." >&2
  exit 1
fi

# C2: typed-confirmation gate (unless --yes/-y was passed).
BASENAME=$(basename "$REPO_ABS")
if [ "$ASSUME_YES" -ne 1 ]; then
  cat <<EOF
WARNING: this will DELETE the existing .git directory in:
  ${REPO_ABS}
and create a fresh single-commit history with LFS filters from the start.

Existing remote 'origin' (if any) will be preserved on the new repo. To
overwrite the remote history, you'll need 'git push --force' afterwards.

This action is NOT reversible by this script.

Type the project name '${BASENAME}' to confirm:
EOF
  read -r CONFIRM
  if [ "$CONFIRM" != "$BASENAME" ]; then
    echo "Aborted." >&2
    exit 1
  fi
fi

mkdir -p "$EMPTY_GIT_TEMPLATE"

# Capture origin
ORIGIN=$(git -C "$REPO_ABS" remote get-url origin 2>/dev/null || echo "")

# Wipe .git
rm -rf "${REPO_ABS}/.git"

# Install templates (don't blow away user-authored .gitattributes/.gitignore)
if [ ! -f "${REPO_ABS}/.gitattributes" ]; then
  cp "$GITATTR_TEMPLATE" "${REPO_ABS}/.gitattributes"
fi
if [ ! -f "${REPO_ABS}/.gitignore" ]; then
  cp "$GITIGNORE_TEMPLATE" "${REPO_ABS}/.gitignore"
else
  # Line-merge any missing entries from template into existing .gitignore
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    [ "${line:0:1}" = "#" ] && continue
    grep -qxF -- "$line" "${REPO_ABS}/.gitignore" 2>/dev/null \
      || echo "$line" >> "${REPO_ABS}/.gitignore"
  done < "$GITIGNORE_TEMPLATE"
fi

git -C "$REPO_ABS" init -b main --template="$EMPTY_GIT_TEMPLATE" -q
git -C "$REPO_ABS" lfs install --local >/dev/null

# Two-commit pattern (V1: role prefix + trailer on each)
git -C "$REPO_ABS" add .gitattributes .gitignore
git -C "$REPO_ABS" commit -q \
  -m "$(printf '%s\n\n%s\n' "$LFS_COMMIT_SUBJECT" "$COAUTHOR_TRAILER")"

git -C "$REPO_ABS" add -A
if git -C "$REPO_ABS" diff --cached --quiet; then
  git -C "$REPO_ABS" commit --allow-empty -q \
    -m "$(printf '%s\n\n%s\n' "$INIT_COMMIT_SUBJECT" "$COAUTHOR_TRAILER")"
else
  git -C "$REPO_ABS" commit -q \
    -m "$(printf '%s\n\n%s\n' "$INIT_COMMIT_SUBJECT" "$COAUTHOR_TRAILER")"
fi

if [ -n "$ORIGIN" ]; then
  git -C "$REPO_ABS" remote add origin "$ORIGIN"
fi

# --- summary (idiom from user's version: ls-files + lfs ls-files counts) ---
LFS_COUNT=$(git -C "$REPO_ABS" lfs ls-files 2>/dev/null | wc -l | tr -d ' ')
TOTAL_FILES=$(git -C "$REPO_ABS" ls-files | wc -l | tr -d ' ')
echo "Done. ${REL} reinitialized with LFS."
echo "  total tracked files: $TOTAL_FILES"
echo "  LFS-tracked files:   $LFS_COUNT"
if [ -n "$ORIGIN" ]; then
  echo "  origin preserved:    $ORIGIN"
  echo "  To overwrite remote: git -C ${REL} push --force"
fi
exit 0
