#!/usr/bin/env bash
# reinit-project-with-lfs.sh — DESTRUCTIVE: reinitialize a child repo's git
# history in order to add LFS filters from the start.
#
# Use only when a project has `.git` but no LFS configuration, and you accept
# losing its existing git history. The remote `origin` URL (if any) is
# preserved across the reinit; a separate `git push --force` to that origin
# is required to overwrite the remote history.
#
# Usage:
#   reinit-project-with-lfs.sh projects/<name>
#   reinit-project-with-lfs.sh knowledge
#
# This script intentionally requires a typed confirmation. It never runs
# unattended.

set -u

WORKSPACE_ROOT="${WORKSPACE_ROOT:-$(pwd)}"
PKA_DIR="${WORKSPACE_ROOT}/.pka"
GITATTR_TEMPLATE="${PKA_DIR}/gitattributes-template"
GITIGNORE_TEMPLATE="${PKA_DIR}/gitignore-template"

COAUTHOR_TRAILER="Co-Authored-By: Claude <noreply@anthropic.com>"
COMMIT_MESSAGE="Reinit with LFS (history reset)"

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <child-repo-relpath>" >&2
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

cat <<EOF
WARNING: this will DELETE the existing .git directory in ${REL}
and create a fresh single-commit history with LFS filters from the start.

Existing remote 'origin' (if any) will be preserved on the new repo.
You will need to 'git push --force' to overwrite remote history if you
want the remote to match.

This action is NOT reversible by this script.

Type 'reinit ${REL}' to confirm:
EOF

read -r CONFIRM
if [ "$CONFIRM" != "reinit ${REL}" ]; then
  echo "Aborted." >&2
  exit 1
fi

# Capture origin
ORIGIN=$(cd "$REPO_ABS" && git remote get-url origin 2>/dev/null || echo "")

# Wipe .git
rm -rf "${REPO_ABS}/.git"

# Install templates (don't blow away user-authored .gitattributes)
if [ ! -f "${REPO_ABS}/.gitattributes" ]; then
  cp "$GITATTR_TEMPLATE" "${REPO_ABS}/.gitattributes"
fi
# Merge .gitignore
if [ ! -f "${REPO_ABS}/.gitignore" ]; then
  cp "$GITIGNORE_TEMPLATE" "${REPO_ABS}/.gitignore"
else
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    [ "${line:0:1}" = "#" ] && continue
    grep -qxF -- "$line" "${REPO_ABS}/.gitignore" 2>/dev/null || echo "$line" >> "${REPO_ABS}/.gitignore"
  done < "$GITIGNORE_TEMPLATE"
fi

(
  cd "$REPO_ABS"
  git init -b main >/dev/null
  git lfs install --local >/dev/null
  git add -A
  if git diff --cached --quiet; then
    git commit --allow-empty -m "$COMMIT_MESSAGE" -m "" -m "$COAUTHOR_TRAILER" >/dev/null
  else
    git commit -m "$COMMIT_MESSAGE" -m "" -m "$COAUTHOR_TRAILER" >/dev/null
  fi
  if [ -n "$ORIGIN" ]; then
    git remote add origin "$ORIGIN"
  fi
)

echo "Done. ${REL} reinitialized with LFS."
if [ -n "$ORIGIN" ]; then
  echo "Origin preserved: $ORIGIN"
  echo "To overwrite the remote history, run: (cd ${REL} && git push --force)"
fi
exit 0
