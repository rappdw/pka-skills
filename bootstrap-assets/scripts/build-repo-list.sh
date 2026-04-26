#!/usr/bin/env bash
# build-repo-list.sh — generate or refresh `.meta` at the workspace root.
#
# Walks knowledge/ and projects/*/ for child repos (directories with .git),
# reads their `origin` remote URL (if set), and writes a `.meta` JSON file
# listing each child repo and its origin (or empty string when none).
#
# Idempotent: re-running on the same state produces an identical `.meta`.
# Preserves any existing entries in `.meta` whose child repo no longer exists
# only by removing them; existing origins are kept fresh from the actual
# remote configuration of each child repo.
#
# Format:
# {
#   "projects": {
#     "knowledge": "git@host:user/knowledge.git",
#     "projects/foo": ""
#   }
# }

set -u

WORKSPACE_ROOT="${WORKSPACE_ROOT:-$(pwd)}"
META_FILE="${WORKSPACE_ROOT}/.meta"

# Collect (child_rel, origin) pairs into a temp file
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT

origin_of() {
  local repo_dir="$1"
  if [ ! -d "${repo_dir}/.git" ]; then
    echo ""
    return
  fi
  (cd "$repo_dir" && git remote get-url origin 2>/dev/null) || echo ""
}

emit() {
  local rel="$1"
  local origin="$2"
  printf '%s\t%s\n' "$rel" "$origin" >> "$TMP"
}

# knowledge/
if [ -d "${WORKSPACE_ROOT}/knowledge/.git" ]; then
  emit "knowledge" "$(origin_of "${WORKSPACE_ROOT}/knowledge")"
fi

# projects/*/
if [ -d "${WORKSPACE_ROOT}/projects" ]; then
  shopt -s nullglob
  for proj in "${WORKSPACE_ROOT}"/projects/*/; do
    if [ -d "${proj}.git" ]; then
      rel="projects/$(basename "$proj")"
      emit "$rel" "$(origin_of "$proj")"
    fi
  done
  shopt -u nullglob
fi

# Sort for deterministic output (idempotency)
sort "$TMP" > "${TMP}.sorted" && mv "${TMP}.sorted" "$TMP"

# Emit JSON
{
  echo "{"
  echo "  \"projects\": {"
  COUNT=0
  TOTAL=$(wc -l < "$TMP" | tr -d ' ')
  while IFS=$'\t' read -r rel origin; do
    COUNT=$((COUNT + 1))
    SEP=","
    [ "$COUNT" -eq "$TOTAL" ] && SEP=""
    # Escape backslash and double-quote in URL (origin URLs rarely contain these)
    esc_origin=${origin//\\/\\\\}
    esc_origin=${esc_origin//\"/\\\"}
    printf '    "%s": "%s"%s\n' "$rel" "$esc_origin" "$SEP"
  done < "$TMP"
  echo "  }"
  echo "}"
} > "$META_FILE"

# Summary
echo "build-repo-list.sh: wrote $META_FILE with $TOTAL entr$([ "$TOTAL" -eq 1 ] && echo "y" || echo "ies")"
exit 0
