#!/usr/bin/env bash
# push-all.sh — push every child repo with unpushed commits.
#
# Reads the list of child repos from `.meta` at the workspace root and runs
# `git push` in each. Failures and skips are surfaced in a summary; one
# failure does not block the others.
#
# The remote that is pushed to is always the child repo's own `origin`
# (`git -C <child> remote get-url origin`). `.meta` only says which child
# repos exist; the URL recorded there is a copy. To set a remote:
#     git -C <child> remote add origin <url>
#     .pka/build-repo-list.sh          # refresh the copy in .meta
# Editing the URL in `.meta` by hand does nothing; this script says so when
# the two disagree.
#
# A child repo is **skipped** (not failed) when:
#   - the child repo has no `origin` remote
#   - the child repo has no `.git` (stale .meta entry)
#   - there is nothing to push
# Child repos found on disk but missing from `.meta` are listed as skipped
# with a hint to run build-repo-list.sh.
#
# Exit codes:
#   0  all attempted pushes succeeded (or were skipped)
#   1  one or more pushes failed (details in summary)
#   2  preconditions missing (no .meta, or a required binary is missing)

set -u

# --- preflight ---
for cmd in git git-lfs python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: '$cmd' not found on PATH. Install it and re-run." >&2
    exit 2
  fi
done

WORKSPACE_ROOT="${WORKSPACE_ROOT:-$(pwd)}"
META_FILE="${WORKSPACE_ROOT}/.meta"

if [ ! -f "$META_FILE" ]; then
  echo "ERROR: $META_FILE not found. Run pka-bootstrap with target 'git' or 'all' first." >&2
  exit 2
fi

PUSHED=()
SKIPPED=()
FAILED=()
NOTES=()

# Emit one "<child path>\t<url recorded in .meta>" line per entry.
parse_meta() {
  python3 - "$META_FILE" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    data = json.load(f)
for k, v in (data.get("projects") or {}).items():
    print("%s\t%s" % (k, v if isinstance(v, str) else ""))
PY
}

ENTRIES=$(parse_meta) || {
  echo "ERROR: could not parse $META_FILE" >&2
  exit 2
}

in_meta() {
  local rel="$1"
  printf '%s\n' "$ENTRIES" | cut -f1 | grep -qxF -- "$rel"
}

unpushed_count() {
  local repo="$1"
  (
    cd "$repo" || exit 0
    # If no upstream is set, count all local commits as unpushed.
    if ! git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
      git rev-list --count HEAD 2>/dev/null || echo 0
    else
      git rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0
    fi
  )
}

while IFS=$'\t' read -r rel meta_origin; do
  [ -z "$rel" ] && continue
  repo_abs="${WORKSPACE_ROOT}/${rel}"

  if [ ! -e "${repo_abs}/.git" ]; then
    SKIPPED+=("$rel: no .git (stale .meta entry)")
    continue
  fi

  # The child repo's own remote is the only thing a push can use.
  origin=$(git -C "$repo_abs" remote get-url origin 2>/dev/null || echo "")
  case "$meta_origin" in TBD) meta_origin="" ;; esac

  if [ -z "$origin" ]; then
    if [ -n "$meta_origin" ]; then
      SKIPPED+=("$rel: no origin remote in the repo (.meta lists one)")
      NOTES+=("$rel: .meta lists ${meta_origin} but the repo has no 'origin' remote. Run: git -C ${rel} remote add origin ${meta_origin}")
    else
      SKIPPED+=("$rel: no origin configured")
    fi
    continue
  fi
  if [ "$origin" != "$meta_origin" ]; then
    NOTES+=("$rel: .meta is out of date (repo origin is ${origin}). Run .pka/build-repo-list.sh to refresh it.")
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

# Child repos on disk that .meta does not know about.
note_unlisted() {
  local rel="$1"
  if [ -d "${WORKSPACE_ROOT}/${rel}/.git" ] && ! in_meta "$rel"; then
    SKIPPED+=("$rel: not listed in .meta")
    NOTES+=("$rel: is a child repo but is not in .meta. Run .pka/build-repo-list.sh to add it.")
  fi
}
note_unlisted "knowledge"
if [ -d "${WORKSPACE_ROOT}/projects" ]; then
  shopt -s nullglob
  for proj in "${WORKSPACE_ROOT}"/projects/*/; do
    note_unlisted "projects/$(basename "$proj")"
  done
  shopt -u nullglob
fi

# Summary
echo
echo "push-all.sh summary"
echo "-----------------------"
echo "Pushed:  ${#PUSHED[@]}"
for r in "${PUSHED[@]:-}"; do [ -n "$r" ] && echo "  + $r"; done
echo "Skipped: ${#SKIPPED[@]}"
for r in "${SKIPPED[@]:-}"; do [ -n "$r" ] && echo "  = $r"; done
if [ ${#NOTES[@]} -gt 0 ]; then
  echo "Notes:"
  for r in "${NOTES[@]}"; do echo "  * $r"; done
fi
if [ ${#FAILED[@]} -gt 0 ]; then
  echo "Failed:  ${#FAILED[@]}"
  for r in "${FAILED[@]}"; do echo "  ! $r"; done
  exit 1
fi
exit 0
