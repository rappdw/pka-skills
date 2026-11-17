#!/usr/bin/env bash
# reinit-project-with-lfs.sh — reinitialize a child repo's git history in order
# to add LFS filters from the start.
#
# Use only when a project has `.git` but no LFS configuration. The repository
# gets a fresh history (one LFS-config commit plus one content commit on
# `main`). The old repository is not deleted: it is MOVED, whole, to
# .pka/reinit-backups/<name>-<timestamp>.git/ — every branch, the stash and the
# config. All remotes are carried over to the new repo; a separate
# `git push --force` is required to overwrite remote history.
#
# Usage:
#   reinit-project-with-lfs.sh [--yes|-y] <child-repo-relpath>
#
# <child-repo-relpath> must be `knowledge` or `projects/<name>`.
#
# Examples:
#   reinit-project-with-lfs.sh projects/legacy
#   reinit-project-with-lfs.sh -y projects/legacy   # bypass confirmation
#   reinit-project-with-lfs.sh knowledge
#
# Without --yes, the script requires the user to type the basename of the
# project as a confirmation. Default is abort.
#
# If any step fails after the old repository has been set aside, the script
# puts it back and restores .gitattributes / .gitignore as they were.
#
# Exit codes:
#   0  success
#   1  user aborted, precondition failure, or a failure that was rolled back
#   2  required binary missing on PATH, or git older than 2.28
#  64  usage error

set -uo pipefail

die() { echo "ERROR: $*" >&2; exit 1; }

usage() {
  [ -n "${1:-}" ] && echo "ERROR: $1" >&2
  echo "Usage: $0 [--yes|-y] <child-repo-relpath>" >&2
  echo "  <child-repo-relpath> is 'knowledge' or 'projects/<name>'." >&2
  echo "Example: $0 projects/legacy" >&2
  exit 64
}

# --- preflight ---
for cmd in git git-lfs; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: '$cmd' not found on PATH. Install it and re-run." >&2
    exit 2
  fi
done

# `git init -b` needs git 2.28 or newer.
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

COAUTHOR_TRAILER="Co-Authored-By: Claude <noreply@anthropic.com>"
LFS_COMMIT_SUBJECT="Bootstrap (git): Configure LFS tracking and .gitignore"
INIT_COMMIT_SUBJECT="Bootstrap (git): Reinit with LFS (history reset)"

# --- arg parsing ---
ASSUME_YES=0
if [ "${1:-}" = "--yes" ] || [ "${1:-}" = "-y" ]; then
  ASSUME_YES=1
  shift
fi
if [ "$#" -ne 1 ]; then usage; fi

REL="$1"
while [ "${REL%/}" != "$REL" ]; do REL="${REL%/}"; done
case "$REL" in
  knowledge) ;;
  projects/*)
    case "${REL#projects/}" in
      ""|.|..|*/*|-*|*[[:cntrl:]]*) usage "not a child repo path: '$1'" ;;
    esac
    ;;
  *) usage "not a child repo path: '$1'" ;;
esac

# --- workspace + path resolution ---
WORKSPACE_ROOT="${WORKSPACE_ROOT:-$(pwd)}"
[ -d "$WORKSPACE_ROOT" ] || die "workspace root ${WORKSPACE_ROOT} is not a directory."
WORKSPACE_ROOT=$(cd "$WORKSPACE_ROOT" && pwd -P) || die "cannot resolve the workspace root."
PKA_DIR="${WORKSPACE_ROOT}/.pka"
GITATTR_TEMPLATE="${PKA_DIR}/gitattributes-template"
GITIGNORE_TEMPLATE="${PKA_DIR}/gitignore-template"
BACKUP_DIR="${PKA_DIR}/reinit-backups"
REPO_ABS="${WORKSPACE_ROOT}/${REL}"

# --- preconditions (nothing is modified until all of these pass) ---
[ -L "$REPO_ABS" ] && die "${REL} is a symbolic link; refusing to reinit a repo that lives elsewhere."
[ -d "$REPO_ABS" ] || die "${REL} does not exist."
repo_real=$(cd "$REPO_ABS" && pwd -P) || die "cannot resolve ${REL}."
[ "$repo_real" = "$REPO_ABS" ] \
  || die "${REL} resolves to ${repo_real}, outside the expected location. Aborting."
if [ -L "${REPO_ABS}/.git" ] || { [ -e "${REPO_ABS}/.git" ] && [ ! -d "${REPO_ABS}/.git" ]; }; then
  die "${REL}/.git is not a plain directory (linked worktree or submodule). Its history lives elsewhere; nothing to reinit here."
fi
[ -d "${REPO_ABS}/.git" ] || die "${REL} has no .git directory; nothing to reinit."
if [ ! -f "$GITATTR_TEMPLATE" ] || [ ! -f "$GITIGNORE_TEMPLATE" ]; then
  die "bootstrap templates missing in ${PKA_DIR}."
fi
git -C "$REPO_ABS" var GIT_COMMITTER_IDENT >/dev/null 2>&1 \
  || die "git has no usable identity for commits. Set user.name and user.email, then re-run."

# --- typed-confirmation gate (unless --yes/-y was passed) ---
BASENAME=$(basename "$REPO_ABS")
if [ "$ASSUME_YES" -ne 1 ]; then
  cat <<EOF
WARNING: this will replace the git history in:
  ${REPO_ABS}
with a fresh two-commit history that has LFS filters from the start.

The current repository (all branches) is moved to ${BACKUP_DIR}/ first,
so this can be undone by hand. Remotes are carried over to the new repo. To
overwrite the remote history you will need 'git push --force' afterwards.

Type the project name '${BASENAME}' to confirm:
EOF
  read -r CONFIRM || CONFIRM=""
  if [ "$CONFIRM" != "$BASENAME" ]; then
    echo "Aborted." >&2
    exit 1
  fi
fi

# --- working state ---
WORK_TMP=$(mktemp -d "${TMPDIR:-/tmp}/pka-reinit.XXXXXX") || die "cannot create a temporary directory."
trap 'rm -rf "$WORK_TMP"' EXIT
EMPTY_GIT_TEMPLATE="${WORK_TMP}/empty-template"
mkdir "$EMPTY_GIT_TEMPLATE" || die "cannot create a temporary directory."

# Remotes of the current repo: name, fetch URL, push URL (if different).
REMOTE_NAMES=()
REMOTE_URLS=()
REMOTE_PUSHURLS=()
while IFS= read -r r; do
  [ -n "$r" ] || continue
  REMOTE_NAMES+=("$r")
  REMOTE_URLS+=("$(git -C "$REPO_ABS" config --get "remote.${r}.url" 2>/dev/null || echo "")")
  REMOTE_PUSHURLS+=("$(git -C "$REPO_ABS" config --get "remote.${r}.pushurl" 2>/dev/null || echo "")")
done < <(git -C "$REPO_ABS" remote 2>/dev/null)

HAD_GITATTR=0
HAD_GITIGNORE=0
[ -f "${REPO_ABS}/.gitattributes" ] && { HAD_GITATTR=1; cp -p "${REPO_ABS}/.gitattributes" "${WORK_TMP}/gitattributes.orig"; }
[ -f "${REPO_ABS}/.gitignore" ]     && { HAD_GITIGNORE=1; cp -p "${REPO_ABS}/.gitignore" "${WORK_TMP}/gitignore.orig"; }

# --- 1. set the old repository aside (moved, never deleted) ---
mkdir -p "$BACKUP_DIR" || die "cannot create ${BACKUP_DIR}."
[ -f "${BACKUP_DIR}/.gitignore" ] || printf '*\n' > "${BACKUP_DIR}/.gitignore"
slug=$(printf '%s' "$REL" | tr '/' '-')
ts=$(date +%Y%m%d-%H%M%S)
backup_path="${BACKUP_DIR}/${slug}-${ts}.git"
n=1
while [ -e "$backup_path" ]; do
  n=$((n + 1))
  backup_path="${BACKUP_DIR}/${slug}-${ts}-${n}.git"
done
mv "${REPO_ABS}/.git" "$backup_path" \
  || die "could not move ${REL}/.git to ${BACKUP_DIR}. Nothing was changed."

rollback() {
  echo "Rolling back: restoring ${REL} to its previous state..." >&2
  # The .git present now (if any) is the one this run created.
  rm -rf "${REPO_ABS}/.git"
  mv "$backup_path" "${REPO_ABS}/.git" \
    || echo "ERROR: could not restore the repository. It is intact at ${backup_path}; move it to ${REPO_ABS}/.git by hand." >&2
  if [ "$HAD_GITATTR" -eq 1 ]; then cp -p "${WORK_TMP}/gitattributes.orig" "${REPO_ABS}/.gitattributes"; else rm -f "${REPO_ABS}/.gitattributes"; fi
  if [ "$HAD_GITIGNORE" -eq 1 ]; then cp -p "${WORK_TMP}/gitignore.orig" "${REPO_ABS}/.gitignore"; else rm -f "${REPO_ABS}/.gitignore"; fi
}

fail_and_rollback() {
  echo "ERROR: $*" >&2
  rollback
  echo "${REL} was not reinitialized." >&2
  exit 1
}

if [ ! -f "${backup_path}/HEAD" ] || [ -e "${REPO_ABS}/.git" ]; then
  fail_and_rollback "the repository did not arrive intact at ${backup_path}."
fi

# --- 2. templates ---
# Append template lines that are missing from an existing file. The file is
# never replaced, and a missing final newline is repaired first so the first
# appended line cannot fuse with the user's last one.
merge_lines() {
  local template="$1" target="$2" line
  if [ ! -f "$target" ]; then
    cp "$template" "$target"
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
  done < "$template"
  return 0
}

# An existing .gitattributes without LFS filters is exactly the case this
# script exists for, so the template's filter lines are merged into it.
merge_lines "$GITATTR_TEMPLATE"   "${REPO_ABS}/.gitattributes" || fail_and_rollback "could not write ${REL}/.gitattributes."
merge_lines "$GITIGNORE_TEMPLATE" "${REPO_ABS}/.gitignore"     || fail_and_rollback "could not write ${REL}/.gitignore."
grep -q 'filter=lfs' "${REPO_ABS}/.gitattributes" \
  || fail_and_rollback "${REL}/.gitattributes has no LFS filters after merging the template."

# --- 3. fresh repository ---
git -C "$REPO_ABS" init -b main --template="$EMPTY_GIT_TEMPLATE" -q \
  || fail_and_rollback "'git init' failed in ${REL}."
# Guard against operating on an enclosing repository if the init did not take.
top=$(git -C "$REPO_ABS" rev-parse --show-toplevel 2>/dev/null) || top=""
top_real=""
[ -n "$top" ] && top_real=$(cd "$top" 2>/dev/null && pwd -P)
[ "$top_real" = "$REPO_ABS" ] \
  || fail_and_rollback "'git init' did not create a repository in ${REL}."
git -C "$REPO_ABS" lfs install --local >/dev/null \
  || fail_and_rollback "'git lfs install --local' failed in ${REL}."

commit_msg() { printf '%s\n\n%s\n' "$1" "$COAUTHOR_TRAILER"; }

git -C "$REPO_ABS" add -- .gitattributes .gitignore \
  || fail_and_rollback "'git add' failed in ${REL}."
git -C "$REPO_ABS" commit -q -m "$(commit_msg "$LFS_COMMIT_SUBJECT")" \
  || fail_and_rollback "'git commit' failed in ${REL} (see the message above)."

# The whole working tree is this repository's content, so everything is staged.
git -C "$REPO_ABS" add -A \
  || fail_and_rollback "'git add' failed in ${REL}."
if git -C "$REPO_ABS" diff --cached --quiet; then
  git -C "$REPO_ABS" commit --allow-empty -q -m "$(commit_msg "$INIT_COMMIT_SUBJECT")" \
    || fail_and_rollback "'git commit' failed in ${REL} (see the message above)."
else
  git -C "$REPO_ABS" commit -q -m "$(commit_msg "$INIT_COMMIT_SUBJECT")" \
    || fail_and_rollback "'git commit' failed in ${REL} (see the message above)."
fi

# --- 4. carry the remotes over ---
i=0
while [ "$i" -lt "${#REMOTE_NAMES[@]}" ]; do
  r="${REMOTE_NAMES[$i]}"; url="${REMOTE_URLS[$i]}"; pushurl="${REMOTE_PUSHURLS[$i]}"
  if [ -n "$url" ]; then
    git -C "$REPO_ABS" remote add "$r" "$url" \
      || fail_and_rollback "could not re-add remote '${r}'."
    if [ -n "$pushurl" ]; then
      git -C "$REPO_ABS" remote set-url --push "$r" "$pushurl" \
        || fail_and_rollback "could not restore the push URL of remote '${r}'."
    fi
  fi
  i=$((i + 1))
done

# --- summary ---
LFS_COUNT=$(git -C "$REPO_ABS" lfs ls-files 2>/dev/null | wc -l | tr -d ' ')
TOTAL_FILES=$(git -C "$REPO_ABS" ls-files | wc -l | tr -d ' ')
echo "Done. ${REL} reinitialized with LFS."
echo "  total tracked files: $TOTAL_FILES"
echo "  LFS-tracked files:   $LFS_COUNT"
i=0
while [ "$i" -lt "${#REMOTE_NAMES[@]}" ]; do
  echo "  remote preserved:    ${REMOTE_NAMES[$i]} ${REMOTE_URLS[$i]}"
  i=$((i + 1))
done
if [ "${#REMOTE_NAMES[@]}" -gt 0 ]; then
  echo "  To overwrite remote history: git -C ${REL} push --force <remote> main"
fi
cat <<EOF
  previous repository: ${backup_path}
    (complete: all branches, stash, config). To undo this reinit:
      rm -rf "${REPO_ABS}/.git" && mv "${backup_path}" "${REPO_ABS}/.git"
    Delete it when you no longer need the old history.
EOF
exit 0
