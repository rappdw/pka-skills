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
#   1. If the project has a .git, save its history as a `git bundle` to
#      .pka/graduate-backups/ (P4). Bundles are portable: `git clone <bundle>`
#      restores the project's full history if you ever need it.
#   2. Remove the project's .git directory and move the content into knowledge/.
#   3. Auto-commit in the knowledge child repo with the role-prefixed message
#      and Co-Authored-By: Claude trailer (V1).
#   4. STAGE (do not commit) the .meta change in the root repo (C1). The user
#      reviews and commits root.
#   5. Print remote-archival instructions only (never call remote APIs).
#
# Idempotency: re-running after a successful graduation is a no-op (source no
# longer exists, knowledge/ already has it).
#
# Exit codes:
#   0  success
#   1  precondition failure (missing source, missing knowledge .git, etc.)
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

# --- workspace resolution (P1) ---
WORKSPACE_ROOT="${WORKSPACE_ROOT:-$(pwd)}"
COAUTHOR_TRAILER="Co-Authored-By: Claude <noreply@anthropic.com>"

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "Usage: $0 <project-name> [knowledge-subdir]" >&2
  echo "Examples:" >&2
  echo "  $0 widget                # → knowledge/widget/" >&2
  echo "  $0 widget reference      # → knowledge/reference/widget/" >&2
  exit 64
fi

NAME="$1"
SUBDIR="${2:-}"

PROJECT_DIR="${WORKSPACE_ROOT}/projects/${NAME}"
if [ -n "$SUBDIR" ]; then
  DEST_PARENT="${WORKSPACE_ROOT}/knowledge/${SUBDIR}"
else
  DEST_PARENT="${WORKSPACE_ROOT}/knowledge"
fi
DEST_DIR="${DEST_PARENT}/${NAME}"
META_FILE="${WORKSPACE_ROOT}/.meta"
BACKUP_DIR="${WORKSPACE_ROOT}/.pka/graduate-backups"  # P4

if [ ! -d "$PROJECT_DIR" ]; then
  echo "ERROR: ${PROJECT_DIR} does not exist." >&2
  exit 1
fi
if [ ! -d "${WORKSPACE_ROOT}/knowledge/.git" ]; then
  echo "ERROR: knowledge/.git not found. Run bootstrap git first." >&2
  exit 1
fi
if [ -e "$DEST_DIR" ]; then
  echo "ERROR: destination ${DEST_DIR} already exists. Aborting to avoid clobber." >&2
  exit 1
fi

# Capture origin for archival instructions
PROJECT_ORIGIN=""
if [ -d "${PROJECT_DIR}/.git" ]; then
  PROJECT_ORIGIN=$(git -C "$PROJECT_DIR" remote get-url origin 2>/dev/null || echo "")
fi

# Save git history as a bundle BEFORE deleting .git (P4: lives in
# .pka/graduate-backups/, NOT inside the knowledge repo where the user's
# adopted version put it).
if [ -d "${PROJECT_DIR}/.git" ]; then
  echo "Saving git history bundle..."
  mkdir -p "$BACKUP_DIR"
  ts=$(date +%Y%m%d-%H%M%S)
  bundle_path="${BACKUP_DIR}/${NAME}-${ts}.bundle"
  git -C "$PROJECT_DIR" bundle create "$bundle_path" --all 2>/dev/null || {
    # Empty repo (no refs to bundle) — degrade quietly to a tar so we still
    # have *something*. Bundles fail on truly empty repos.
    tar_path="${BACKUP_DIR}/${NAME}-${ts}.tar"
    (cd "${WORKSPACE_ROOT}/projects" && tar cf "$tar_path" "${NAME}/.git")
    bundle_path="$tar_path"
  }
  echo "  Saved to: $bundle_path"
  echo "Removing project .git directory..."
  rm -rf "${PROJECT_DIR}/.git"
fi

# Move content to destination
echo "Moving ${NAME} to knowledge/${SUBDIR:+${SUBDIR}/}..."
mkdir -p "$DEST_PARENT"
mv "$PROJECT_DIR" "$DEST_DIR"

# Commit in the knowledge child repo (V1 — role prefix + trailer)
echo "Committing to knowledge/..."
KNOWLEDGE_PATH_LABEL="knowledge/${SUBDIR:+${SUBDIR}/}"
COMMIT_SUBJECT="Graduate: ${NAME} → ${KNOWLEDGE_PATH_LABEL}"
git -C "${WORKSPACE_ROOT}/knowledge" add -A
git -C "${WORKSPACE_ROOT}/knowledge" commit -q \
  -m "$(printf '%s\n\n%s\n' "$COMMIT_SUBJECT" "$COAUTHOR_TRAILER")"

# Update .meta (remove projects/<NAME>); leave the change STAGED in the root,
# never committed (C1). Done by editing .meta in place + `git add` only.
if [ -f "$META_FILE" ]; then
  python3 - "$META_FILE" "projects/${NAME}" <<'PY'
import json, sys
path, key = sys.argv[1], sys.argv[2]
with open(path) as f:
    data = json.load(f)
projects = data.get("projects") or {}
if key in projects:
    del projects[key]
    data["projects"] = projects
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
PY
fi

# Stage root changes (C1: stage only, NEVER commit)
ROOT_STAGED=()
if [ -d "${WORKSPACE_ROOT}/.git" ]; then
  if [ -f "$META_FILE" ]; then
    git -C "$WORKSPACE_ROOT" add .meta 2>/dev/null && ROOT_STAGED+=(".meta") || true
  fi
  # If projects/<NAME> was tracked in root (rare — typically excluded by
  # .gitignore) then mark its deletion staged.
  if git -C "$WORKSPACE_ROOT" ls-files --error-unmatch "projects/${NAME}" >/dev/null 2>&1; then
    git -C "$WORKSPACE_ROOT" add -A "projects/${NAME}" 2>/dev/null \
      && ROOT_STAGED+=("projects/${NAME}") || true
  fi
fi

# --- output ---
cat <<EOF

Graduated ${NAME} → ${KNOWLEDGE_PATH_LABEL}${NAME}/

Knowledge child repo: COMMITTED (auto).
                      Subject: '${COMMIT_SUBJECT}'
EOF

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

[ -n "${bundle_path:-}" ] && echo "" && echo "History bundle: $bundle_path"
exit 0
