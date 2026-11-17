#!/usr/bin/env bash
# graduate.sh — move a project from projects/<name>/ into knowledge/<subdir>/<name>/.
#
# Usage:
#   graduate.sh <project-name> [knowledge-subdir]
#
# Defaults knowledge-subdir to "" — i.e., moves to knowledge/<name>/.
# Pass an explicit subdir to nest under (e.g., "reference" → knowledge/reference/<name>/).
#
# What it does:
#   1. If the project has a .git directory, MOVE it (not copy, not delete) to
#      .pka/graduate-backups/<name>-<timestamp>.git/. The whole repository is
#      kept: every branch, the stash, the config and all LFS objects.
#      `git clone <that path>` restores the history.
#   2. Move the project content into knowledge/.
#   3. Rewrite `[[projects/<name>/...]]` wikilinks in knowledge/**/_MOC.md.
#   4. Commit in the knowledge child repo — only the moved project and the
#      rewritten MOC files, never unrelated work in progress.
#   5. STAGE (do not commit) the .meta change in the root repo. The user
#      reviews and commits root.
#   6. Print remote-archival instructions only (never call remote APIs).
#
# Safety: nothing is deleted. If the commit in knowledge/ fails (hook, signing,
# identity), every step is rolled back and the project is left as it was.
#
# Idempotency: re-running after a successful graduation fails cleanly (source
# no longer exists).
#
# Exit codes:
#   0  success
#   1  precondition failure, or a failure that was rolled back
#   2  required binary (`git` / `git-lfs` / `python3`) missing on PATH
#  64  usage error

set -uo pipefail

die() { echo "ERROR: $*" >&2; exit 1; }

usage() {
  [ -n "${1:-}" ] && echo "ERROR: $1" >&2
  echo "Usage: $0 <project-name> [knowledge-subdir]" >&2
  echo "Examples:" >&2
  echo "  $0 widget                # → knowledge/widget/" >&2
  echo "  $0 widget reference      # → knowledge/reference/widget/" >&2
  exit 64
}

# --- preflight ---
for cmd in git git-lfs python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: '$cmd' not found on PATH. Install it and re-run." >&2
    exit 2
  fi
done

COAUTHOR_TRAILER="Co-Authored-By: Claude <noreply@anthropic.com>"

# --- arguments ---
if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then usage; fi

NAME="$1"
SUBDIR="${2:-}"

# A trailing slash (tab completion) is harmless; anything else that is not a
# single plain folder name is refused.
while [ "${NAME%/}" != "$NAME" ]; do NAME="${NAME%/}"; done
case "$NAME" in
  ""|.|..)           usage "project name is empty or not a folder name." ;;
  */*)               usage "project name must be a single folder name under projects/, not a path: '$1'" ;;
  -*)                usage "project name must not start with '-': '$1'" ;;
  *[[:cntrl:]]*)     usage "project name contains control characters." ;;
esac

while [ "${SUBDIR%/}" != "$SUBDIR" ]; do SUBDIR="${SUBDIR%/}"; done
if [ -n "$SUBDIR" ]; then
  case "$SUBDIR" in
    /*)              usage "knowledge-subdir must be relative to knowledge/: '$2'" ;;
    -*)              usage "knowledge-subdir must not start with '-': '$2'" ;;
    *[[:cntrl:]]*)   usage "knowledge-subdir contains control characters." ;;
  esac
  case "/$SUBDIR/" in
    */../*|*/./*|*//*) usage "knowledge-subdir must not contain '.', '..' or empty components: '$2'" ;;
  esac
fi

# --- workspace resolution ---
WORKSPACE_ROOT="${WORKSPACE_ROOT:-$(pwd)}"
[ -d "$WORKSPACE_ROOT" ] || die "workspace root ${WORKSPACE_ROOT} is not a directory."
WORKSPACE_ROOT=$(cd "$WORKSPACE_ROOT" && pwd -P) || die "cannot resolve the workspace root."

PROJECT_DIR="${WORKSPACE_ROOT}/projects/${NAME}"
KNOWLEDGE_DIR="${WORKSPACE_ROOT}/knowledge"
REL_DEST="${SUBDIR:+${SUBDIR}/}${NAME}"          # relative to knowledge/
DEST_DIR="${KNOWLEDGE_DIR}/${REL_DEST}"
DEST_PARENT=$(dirname "$DEST_DIR")
META_FILE="${WORKSPACE_ROOT}/.meta"
BACKUP_DIR="${WORKSPACE_ROOT}/.pka/graduate-backups"

# --- preconditions (nothing is modified until all of these pass) ---
if [ -L "$PROJECT_DIR" ]; then
  die "projects/${NAME} is a symbolic link. Graduating it would move the link, not the project. Graduate the real directory instead."
fi
[ -d "$PROJECT_DIR" ] || die "${PROJECT_DIR} does not exist."
[ -L "$KNOWLEDGE_DIR" ] && die "knowledge/ is a symbolic link; refusing to graduate into it."
[ -d "${KNOWLEDGE_DIR}/.git" ] || die "knowledge/.git not found. Run bootstrap git first."
git -C "$KNOWLEDGE_DIR" rev-parse -q --verify HEAD >/dev/null 2>&1 \
  || die "the knowledge repo has no commits yet. Run bootstrap git first."
if [ -e "$DEST_DIR" ] || [ -L "$DEST_DIR" ]; then
  die "destination ${DEST_DIR} already exists. Aborting to avoid clobber."
fi

# The destination must really be inside knowledge/ (no symlink leading out).
KNOWLEDGE_REAL=$(cd "$KNOWLEDGE_DIR" && pwd -P) || die "cannot resolve knowledge/."
probe="$DEST_PARENT"
while [ ! -d "$probe" ]; do probe=$(dirname "$probe"); done
probe_real=$(cd "$probe" && pwd -P) || die "cannot resolve ${probe}."
case "${probe_real}/" in
  "${KNOWLEDGE_REAL}/"*) ;;
  *) die "destination resolves outside knowledge/ (${probe_real}). Aborting." ;;
esac

HAS_GIT=0
if [ -d "${PROJECT_DIR}/.git" ] && [ ! -L "${PROJECT_DIR}/.git" ]; then
  HAS_GIT=1
elif [ -e "${PROJECT_DIR}/.git" ] || [ -L "${PROJECT_DIR}/.git" ]; then
  die "projects/${NAME}/.git is not a plain directory (linked worktree or submodule). Its history lives elsewhere; graduate it by hand."
fi

# The knowledge commit needs an identity. Check before touching anything.
git -C "$KNOWLEDGE_DIR" var GIT_COMMITTER_IDENT >/dev/null 2>&1 \
  || die "git has no usable identity for commits in knowledge/. Set user.name and user.email, then re-run."

PROJECT_ORIGIN=""
if [ "$HAS_GIT" -eq 1 ]; then
  PROJECT_ORIGIN=$(git -C "$PROJECT_DIR" remote get-url origin 2>/dev/null || echo "")
  # LFS files that were never downloaded are pointer stubs in the working
  # tree. Moving them would file the stubs, not the content.
  missing_lfs=$(git -C "$PROJECT_DIR" lfs ls-files 2>/dev/null | awk '$2 == "-"' | wc -l | tr -d ' ')
  if [ "${missing_lfs:-0}" -gt 0 ]; then
    die "projects/${NAME} has ${missing_lfs} LFS file(s) that are not downloaded. Run 'git -C projects/${NAME} lfs pull' first."
  fi
fi

# --- working state for rollback ---
WORK_TMP=$(mktemp -d "${TMPDIR:-/tmp}/pka-graduate.XXXXXX") || die "cannot create a temporary directory."
KEEP_TMP=0
trap 'if [ "$KEEP_TMP" -eq 0 ]; then rm -rf "$WORK_TMP"; fi' EXIT
MOC_LIST="${WORK_TMP}/moc-list.tsv"       # <index>\t<path relative to knowledge/>
: > "$MOC_LIST"

backup_path=""
MOVED=0
CREATED_DIRS=()                            # destination parents we created, deepest last
STAGE_PATHS=("$REL_DEST")

rollback() {
  echo "Rolling back: restoring projects/${NAME} to its previous state..." >&2
  git -C "$KNOWLEDGE_DIR" reset -q -- "${STAGE_PATHS[@]}" >/dev/null 2>&1 || true
  while IFS=$'\t' read -r idx rel; do
    [ -n "$idx" ] || continue
    cp -p "${WORK_TMP}/moc-${idx}" "${KNOWLEDGE_DIR}/${rel}" \
      || { KEEP_TMP=1; echo "WARNING: could not restore ${KNOWLEDGE_DIR}/${rel}; the original is at ${WORK_TMP}/moc-${idx}" >&2; }
  done < "$MOC_LIST"
  if [ "$MOVED" -eq 1 ]; then
    mv "$DEST_DIR" "$PROJECT_DIR" \
      || echo "ERROR: could not move ${DEST_DIR} back to ${PROJECT_DIR}. Move it by hand." >&2
  fi
  if [ -n "$backup_path" ] && [ -d "$backup_path" ] && [ -d "$PROJECT_DIR" ]; then
    mv "$backup_path" "${PROJECT_DIR}/.git" \
      || echo "ERROR: could not restore the repository. It is intact at ${backup_path}; move it to ${PROJECT_DIR}/.git by hand." >&2
  fi
  local i=${#CREATED_DIRS[@]}
  while [ "$i" -gt 0 ]; do
    i=$((i - 1))
    rmdir "${CREATED_DIRS[$i]}" 2>/dev/null || true
  done
}

fail_and_rollback() {
  echo "ERROR: $*" >&2
  rollback
  echo "Nothing was graduated." >&2
  exit 1
}

# --- 1. set the repository aside (moved, never deleted) ---
if [ "$HAS_GIT" -eq 1 ]; then
  echo "Setting the project's git repository aside..."
  mkdir -p "$BACKUP_DIR" || die "cannot create ${BACKUP_DIR}."
  # Keep the backups out of the root repo even on workspaces whose root
  # .gitignore predates this directory.
  [ -f "${BACKUP_DIR}/.gitignore" ] || printf '*\n' > "${BACKUP_DIR}/.gitignore"
  ts=$(date +%Y%m%d-%H%M%S)
  backup_path="${BACKUP_DIR}/${NAME}-${ts}.git"
  n=1
  while [ -e "$backup_path" ]; do
    n=$((n + 1))
    backup_path="${BACKUP_DIR}/${NAME}-${ts}-${n}.git"
  done
  if ! mv "${PROJECT_DIR}/.git" "$backup_path"; then
    backup_path=""
    die "could not move projects/${NAME}/.git to ${BACKUP_DIR}. Nothing was changed."
  fi
  if [ ! -f "${backup_path}/HEAD" ] || [ -e "${PROJECT_DIR}/.git" ]; then
    fail_and_rollback "the repository did not arrive intact at ${backup_path}."
  fi
  echo "  Kept at: $backup_path"
fi

# --- 2. move content ---
echo "Moving ${NAME} to knowledge/${SUBDIR:+${SUBDIR}/}..."
missing=()
probe="$DEST_PARENT"
while [ ! -d "$probe" ]; do
  missing+=("$probe")
  probe=$(dirname "$probe")
done
i=${#missing[@]}
while [ "$i" -gt 0 ]; do
  i=$((i - 1))
  mkdir "${missing[$i]}" || fail_and_rollback "cannot create ${missing[$i]}."
  CREATED_DIRS+=("${missing[$i]}")
done
mv "$PROJECT_DIR" "$DEST_DIR" || fail_and_rollback "could not move ${PROJECT_DIR} to ${DEST_DIR}."
MOVED=1

# --- 3. pointer-row propagation (added in v1.6.1) ---
# Rewrite any `[[projects/<NAME>/...]]` wikilinks inside `knowledge/**/_MOC.md`
# to the new vault-relative path. The original of every file changed is saved
# first so a failed graduation can put it back byte for byte.
POINTER_REWRITES=$(python3 - "$KNOWLEDGE_DIR" "$NAME" "$REL_DEST" "$WORK_TMP" "$MOC_LIST" <<'PY'
import os, re, shutil, sys
root, name, new_prefix, save_dir, list_path = sys.argv[1:6]
old = re.compile(r"\[\[projects/" + re.escape(name) + r"(/[^\]]+)\]\]")
total = 0
changed = []
for dirpath, dirnames, files in os.walk(root):
    dirnames[:] = [d for d in dirnames if d not in (".git", ".obsidian", ".trash")]
    for fn in files:
        if not fn.endswith("_MOC.md"):
            continue
        p = os.path.join(dirpath, fn)
        with open(p, "r", encoding="utf-8", newline="") as f:
            text = f.read()
        new_text, n = old.subn(lambda m: "[[" + new_prefix + m.group(1) + "]]", text)
        if not n:
            continue
        idx = len(changed)
        shutil.copy2(p, os.path.join(save_dir, "moc-%d" % idx))
        changed.append((idx, os.path.relpath(p, root)))
        with open(list_path, "a", encoding="utf-8") as lf:
            lf.write("%d\t%s\n" % (idx, os.path.relpath(p, root)))
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(new_text)
        total += n
print(total)
PY
) || fail_and_rollback "rewriting pointer-row wikilinks failed."
if [ "${POINTER_REWRITES:-0}" -gt 0 ]; then
  echo "Pointer-row wikilinks rewritten: ${POINTER_REWRITES}"
fi
while IFS=$'\t' read -r idx rel; do
  [ -n "$idx" ] && STAGE_PATHS+=("$rel")
done < "$MOC_LIST"

# --- 4. commit in the knowledge child repo ---
# Stage and commit by path: only the graduated project and the MOC files this
# run rewrote. Anything else that is modified or staged in knowledge/ stays
# exactly as the user left it.
echo "Committing to knowledge/..."
KNOWLEDGE_PATH_LABEL="knowledge/${SUBDIR:+${SUBDIR}/}"
COMMIT_SUBJECT="Graduate: ${NAME} → ${KNOWLEDGE_PATH_LABEL}"
KNOWLEDGE_COMMITTED=0
git -C "$KNOWLEDGE_DIR" add -- "${STAGE_PATHS[@]}" \
  || fail_and_rollback "'git add' failed in knowledge/."
if git -C "$KNOWLEDGE_DIR" diff --cached --quiet -- "${STAGE_PATHS[@]}"; then
  echo "  Nothing to commit: the project has no files git would track."
else
  git -C "$KNOWLEDGE_DIR" commit -q \
    -m "$(printf '%s\n\n%s\n' "$COMMIT_SUBJECT" "$COAUTHOR_TRAILER")" \
    -- "${STAGE_PATHS[@]}" \
    || fail_and_rollback "'git commit' failed in knowledge/ (see the message above)."
  KNOWLEDGE_COMMITTED=1
fi

# From here on the graduation has happened; later problems are warnings.
WARNINGS=()

# --- 5. .meta: remove projects/<NAME>; staged in root, never committed ---
if [ -f "$META_FILE" ]; then
  python3 - "$META_FILE" "projects/${NAME}" <<'PY' || WARNINGS+=(".meta could not be updated; remove the 'projects/${NAME}' entry by hand or run .pka/build-repo-list.sh")
import json, sys
path, key = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as f:
    data = json.load(f)
projects = data.get("projects") or {}
if key in projects:
    del projects[key]
    data["projects"] = projects
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
PY
fi

ROOT_STAGED=()
if [ -d "${WORKSPACE_ROOT}/.git" ]; then
  if [ -f "$META_FILE" ]; then
    git -C "$WORKSPACE_ROOT" add -- .meta 2>/dev/null && ROOT_STAGED+=(".meta")
  fi
  # If projects/<NAME> was tracked in root (rare — typically excluded by
  # .gitignore) then mark its deletion staged.
  if git -C "$WORKSPACE_ROOT" ls-files --error-unmatch "projects/${NAME}" >/dev/null 2>&1; then
    git -C "$WORKSPACE_ROOT" add -A -- "projects/${NAME}" 2>/dev/null \
      && ROOT_STAGED+=("projects/${NAME}")
  fi
fi

# --- output ---
echo
echo "Graduated ${NAME} → ${KNOWLEDGE_PATH_LABEL}${NAME}/"
echo
if [ "$KNOWLEDGE_COMMITTED" -eq 1 ]; then
  echo "Knowledge child repo: COMMITTED (auto)."
  echo "                      Subject: '${COMMIT_SUBJECT}'"
else
  echo "Knowledge child repo: no commit (nothing to track)."
fi

if [ ${#ROOT_STAGED[@]} -gt 0 ]; then
  echo "Root repo:            STAGED (NOT committed — root is human-review only)."
  echo "                      Staged files:"
  for f in "${ROOT_STAGED[@]}"; do echo "                        - $f"; done
  echo "                      Review with: git -C ${WORKSPACE_ROOT} diff --cached"
  echo "                      Commit when ready: git -C ${WORKSPACE_ROOT} commit"
fi

if [ -n "$PROJECT_ORIGIN" ]; then
  cat <<EOF

Remote archival (manual — never automated):
  The previous project remote was: ${PROJECT_ORIGIN}
  Archive it via your forge's UI or API. Examples:
    Gitea:  curl -X PATCH -H "Authorization: token \$PAT" \\
             -H "Content-Type: application/json" \\
             -d '{"archived": true}' \\
             https://<host>/api/v1/repos/<owner>/${NAME}
    GitHub: gh repo archive <owner>/${NAME}
EOF
fi

if [ -n "$backup_path" ]; then
  cat <<EOF

Previous repository (full history, all branches, LFS objects): ${backup_path}
  Browse or restore it with: git clone "${backup_path}" <somewhere>
  It is a complete copy; delete it when you no longer need the history.
EOF
fi

if [ ${#WARNINGS[@]} -gt 0 ]; then
  echo
  for w in "${WARNINGS[@]}"; do echo "WARNING: $w" >&2; done
fi
exit 0
