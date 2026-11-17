#!/usr/bin/env bash
# build-repo-list.sh — generate or refresh `.meta` at the workspace root.
#
# Walks knowledge/ and projects/*/ for child repos (directories with .git),
# reads their `origin` remote URL (if set), and writes a `.meta` JSON file
# listing each child repo and its origin (or empty string when none).
#
# `.meta` is DERIVED from the child repos. The "projects" map is rebuilt on
# every run, so a URL typed into `.meta` by hand is replaced by whatever the
# child repo's `origin` remote actually is. To set a remote, use
# `git -C <child> remote add origin <url>` and re-run this script. Any other
# top-level key in `.meta` is preserved.
#
# Idempotent: re-running on the same state produces an identical `.meta`.
# The file is written to a temporary name and renamed into place, so an
# interrupted run cannot leave a half-written manifest.
#
# Format:
# {
#   "projects": {
#     "knowledge": "git@host:user/knowledge.git",
#     "projects/foo": ""
#   }
# }
#
# Exit codes:
#   0  success
#   1  existing .meta is not valid JSON (left untouched), or the write failed
#   2  required binary missing on PATH

set -u

# --- preflight ---
for cmd in git python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: '$cmd' not found on PATH. Install it and re-run." >&2
    exit 2
  fi
done

WORKSPACE_ROOT="${WORKSPACE_ROOT:-$(pwd)}"
META_FILE="${WORKSPACE_ROOT}/.meta"

# Collect (child_rel, origin) pairs into a temp file
TMP=$(mktemp "${TMPDIR:-/tmp}/pka-meta.XXXXXX") || exit 1
trap 'rm -f "$TMP"' EXIT

origin_of() {
  local repo_dir="$1"
  git -C "$repo_dir" remote get-url origin 2>/dev/null || echo ""
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

# Write JSON: keep other top-level keys, rebuild "projects" sorted by path.
TOTAL=$(python3 - "$META_FILE" "$TMP" <<'PY'
import json, os, sys
meta_path, pairs_path = sys.argv[1], sys.argv[2]

data = {}
if os.path.exists(meta_path):
    try:
        with open(meta_path, encoding="utf-8") as f:
            data = json.load(f)
    except ValueError as e:
        sys.stderr.write("ERROR: %s is not valid JSON (%s). Fix or remove it, then re-run.\n" % (meta_path, e))
        sys.exit(1)
    if not isinstance(data, dict):
        sys.stderr.write("ERROR: %s does not contain a JSON object. Fix or remove it, then re-run.\n" % meta_path)
        sys.exit(1)

projects = {}
with open(pairs_path, encoding="utf-8") as f:
    for line in f:
        line = line.rstrip("\n")
        if not line:
            continue
        rel, _, origin = line.partition("\t")
        projects[rel] = origin

out = {"projects": dict(sorted(projects.items()))}
for k, v in data.items():
    if k != "projects":
        out[k] = v

tmp_path = meta_path + ".tmp"
with open(tmp_path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
    f.write("\n")
os.replace(tmp_path, meta_path)
print(len(projects))
PY
) || exit 1

# Summary
echo "build-repo-list.sh: wrote $META_FILE with $TOTAL entr$([ "$TOTAL" -eq 1 ] && echo "y" || echo "ies")"
exit 0
