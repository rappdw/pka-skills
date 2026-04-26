#!/usr/bin/env bash
# push-all.sh — push every child repo with unpushed commits.
#
# Reads `.meta` from the workspace root, iterates child repos, and runs
# `git push` in each. Failures and skips are surfaced in a summary; one
# failure does not block the others.
#
# A child repo is **skipped** (not failed) when:
#   - origin URL is empty / missing in `.meta`
#   - origin URL is the placeholder "TBD"
#   - the child repo has no `.git` (stale .meta entry)
#   - the working tree is clean and there is nothing to push
#
# Exit codes:
#   0  all attempted pushes succeeded (or were skipped)
#   1  one or more pushes failed (details in summary)
#   2  preconditions missing (no .meta)

set -u

WORKSPACE_ROOT="${WORKSPACE_ROOT:-$(pwd)}"
META_FILE="${WORKSPACE_ROOT}/.meta"

if [ ! -f "$META_FILE" ]; then
  echo "ERROR: $META_FILE not found. Run pka-bootstrap with target 'git' or 'all' first." >&2
  exit 2
fi

PUSHED=()
SKIPPED=()
FAILED=()

# Parse .meta (json-ish, simple key:value lines inside "projects": { ... })
# We grep for lines like:    "knowledge": "git@host:user/knowledge.git",
parse_meta() {
  python3 - "$META_FILE" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
for k, v in (data.get("projects") or {}).items():
    print(f"{k}\t{v}")
PY
}

ENTRIES=$(parse_meta) || {
  echo "ERROR: could not parse $META_FILE" >&2
  exit 2
}

unpushed_count() {
  local repo="$1"
  (
    cd "$repo"
    # If no upstream is set, count all local commits as unpushed.
    if ! git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
      git rev-list --count HEAD 2>/dev/null || echo 0
    else
      git rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0
    fi
  )
}

while IFS=$'\t' read -r rel origin; do
  [ -z "$rel" ] && continue
  repo_abs="${WORKSPACE_ROOT}/${rel}"

  if [ ! -d "${repo_abs}/.git" ]; then
    SKIPPED+=("$rel: no .git (stale .meta entry)")
    continue
  fi

  if [ -z "$origin" ] || [ "$origin" = "TBD" ]; then
    SKIPPED+=("$rel: no origin configured (placeholder in .meta)")
    continue
  fi

  count=$(unpushed_count "$repo_abs" || echo 0)
  if [ "${count:-0}" -eq 0 ]; then
    SKIPPED+=("$rel: nothing to push")
    continue
  fi

  echo "Pushing $rel ($count commit(s))..."
  # If no upstream is set yet (first push to this remote), use -u to set it.
  # This makes the script work cleanly on workspaces just emerging from bootstrap.
  has_upstream=$(cd "$repo_abs" && git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || echo "")
  if [ -z "$has_upstream" ]; then
    branch=$(cd "$repo_abs" && git symbolic-ref --short HEAD 2>/dev/null || echo "main")
    if (cd "$repo_abs" && git push -u origin "$branch" 2>&1); then
      PUSHED+=("$rel")
    else
      FAILED+=("$rel")
    fi
  else
    if (cd "$repo_abs" && git push 2>&1); then
      PUSHED+=("$rel")
    else
      FAILED+=("$rel")
    fi
  fi
done <<< "$ENTRIES"

# Summary
echo
echo "push-all.sh summary"
echo "-----------------------"
echo "Pushed:  ${#PUSHED[@]}"
for r in "${PUSHED[@]:-}"; do [ -n "$r" ] && echo "  + $r"; done
echo "Skipped: ${#SKIPPED[@]}"
for r in "${SKIPPED[@]:-}"; do [ -n "$r" ] && echo "  = $r"; done
if [ ${#FAILED[@]} -gt 0 ]; then
  echo "Failed:  ${#FAILED[@]}"
  for r in "${FAILED[@]}"; do echo "  ! $r"; done
  exit 1
fi
exit 0
