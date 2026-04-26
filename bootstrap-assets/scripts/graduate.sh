#!/usr/bin/env bash
# graduate.sh — move a project from projects/<name>/ into knowledge/<subdir>/<name>/.
#
# Usage:
#   graduate.sh <project-name> [knowledge-subdir]
#
# Defaults knowledge-subdir to "reference" when not given.
#
# Steps:
#   1. Verify projects/<name>/ exists, knowledge/.git exists.
#   2. Move project content (excluding .git) to knowledge/<subdir>/<name>/.
#      The project's existing git history is left as a tarball backup at
#      .pka/graduate-backups/<name>-<date>.tar so it isn't lost silently.
#   3. In knowledge/ (child repo): commit the new content with message
#      `Graduate: <name> → knowledge/<subdir>/`, including the Claude trailer.
#   4. Remove projects/<name>/ from the workspace.
#   5. Stage (do not commit) the .meta change in root that removes the
#      projects/<name> entry. Also stage the projects/<name> deletion.
#   6. Print remote-archival instructions for the user — never call APIs.
#
# Idempotent within a single workspace state: re-running after a successful
# graduation is a no-op (source no longer exists, knowledge/ already has it).

set -u

WORKSPACE_ROOT="${WORKSPACE_ROOT:-$(pwd)}"
COAUTHOR_TRAILER="Co-Authored-By: Claude <noreply@anthropic.com>"

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "Usage: $0 <project-name> [knowledge-subdir]" >&2
  echo "Example: $0 widget reference" >&2
  exit 64
fi

NAME="$1"
SUBDIR="${2:-reference}"

PROJECT_DIR="${WORKSPACE_ROOT}/projects/${NAME}"
DEST_PARENT="${WORKSPACE_ROOT}/knowledge/${SUBDIR}"
DEST_DIR="${DEST_PARENT}/${NAME}"
META_FILE="${WORKSPACE_ROOT}/.meta"
BACKUP_DIR="${WORKSPACE_ROOT}/.pka/graduate-backups"

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
  PROJECT_ORIGIN=$(cd "$PROJECT_DIR" && git remote get-url origin 2>/dev/null || echo "")
fi

# Backup the project's git history before we lose it
mkdir -p "$BACKUP_DIR"
TS=$(date +%Y%m%d-%H%M%S)
BACKUP_PATH="${BACKUP_DIR}/${NAME}-${TS}.tar"
if [ -d "${PROJECT_DIR}/.git" ]; then
  (cd "${WORKSPACE_ROOT}/projects" && tar cf "$BACKUP_PATH" "${NAME}/.git")
  echo "Backed up project .git to ${BACKUP_PATH}"
fi

# Move content (excluding .git)
mkdir -p "$DEST_PARENT"
mkdir -p "$DEST_DIR"
# Copy everything except .git, then remove the source after successful copy
(
  cd "$PROJECT_DIR"
  shopt -s dotglob nullglob
  for entry in *; do
    [ "$entry" = ".git" ] && continue
    cp -a "$entry" "${DEST_DIR}/"
  done
  shopt -u dotglob nullglob
)

# Commit in knowledge/
(
  cd "${WORKSPACE_ROOT}/knowledge"
  git add -A "${SUBDIR}/${NAME}"
  git commit -m "Graduate: ${NAME} → knowledge/${SUBDIR}/" -m "" -m "$COAUTHOR_TRAILER" >/dev/null
)

# Remove the source project (after successful copy + commit)
rm -rf "$PROJECT_DIR"

# Update .meta if present (remove projects/<name>); leave changes staged in root
if [ -f "$META_FILE" ]; then
  python3 - "$META_FILE" "projects/${NAME}" <<'PY'
import json, sys
path = sys.argv[1]
key = sys.argv[2]
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

# Stage root changes (do NOT commit — root is human-review only).
# .meta is the main artifact; projects/<NAME> is just removed from disk
# (and only appears as a deletion in `git status` if root previously tracked it,
# which is uncommon since `.gitignore` typically excludes child repos).
if [ -d "${WORKSPACE_ROOT}/.git" ]; then
  (
    cd "$WORKSPACE_ROOT"
    [ -f .meta ] && git add .meta 2>/dev/null || true
    # If projects/<NAME> was tracked in root, mark its deletion staged
    git ls-files --error-unmatch "projects/${NAME}" >/dev/null 2>&1 \
      && git add -A "projects/${NAME}" 2>/dev/null || true
  )
fi

# Output
cat <<EOF

Graduated ${NAME} → knowledge/${SUBDIR}/${NAME}/

Knowledge child repo: committed (auto).
Root repo: changes STAGED but NOT committed (.meta updated, projects/${NAME} removed).
           Review with 'git status' / 'git diff --cached' and commit when ready.

EOF

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

echo "Backup of original .git: ${BACKUP_PATH}"
exit 0
