#!/usr/bin/env bash
# Common helpers for pka-skills shell tests.
#
# Usage in test scripts:
#   source "$(dirname "$0")/lib.sh"
#   ws=$(make_workspace)
#   install_pka_assets "$ws"
#   ...
#   pass

set -u

# ---------- terminal ----------
RED=$(printf '\033[31m')
GREEN=$(printf '\033[32m')
YELLOW=$(printf '\033[33m')
RESET=$(printf '\033[0m')

# Track failures for the summary
TESTS_RUN=0
TESTS_FAILED=0
FAIL_DETAIL=()

# ---------- repo paths ----------
THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKA_REPO="$(cd "${THIS_DIR}/.." && pwd)"
ASSETS_DIR="${PKA_REPO}/bootstrap-assets"

# ---------- workspace creation ----------
make_workspace() {
  local dir
  dir=$(mktemp -d "${TMPDIR:-/tmp}/pka-test.XXXXXX")
  echo "$dir"
}

cleanup_workspace() {
  local dir="$1"
  if [[ "$dir" == /tmp/pka-test.* || "$dir" == "${TMPDIR:-/tmp}"/pka-test.* ]]; then
    rm -rf "$dir"
  fi
}

# Install vendored .pka assets into a workspace (mirrors what `bootstrap git`
# would do for the templates+scripts subset).
install_pka_assets() {
  local ws="$1"
  mkdir -p "$ws/.pka"
  cp "${ASSETS_DIR}/gitattributes-template" "$ws/.pka/gitattributes-template"
  cp "${ASSETS_DIR}/gitignore-template"     "$ws/.pka/gitignore-template"
  for s in "${ASSETS_DIR}"/scripts/*.sh; do
    cp "$s" "$ws/.pka/$(basename "$s")"
    chmod +x "$ws/.pka/$(basename "$s")"
  done
}

# ---------- assertions ----------
fail() {
  TESTS_FAILED=$((TESTS_FAILED + 1))
  FAIL_DETAIL+=("${TEST_NAME:-?}: $1")
  echo "${RED}FAIL${RESET} ${TEST_NAME:-?}: $1" >&2
}

pass_step() {
  echo "  ${GREEN}ok${RESET} $1"
}

assert_dir_exists() {
  local p="$1" msg="${2:-}"
  if [ -d "$p" ]; then
    pass_step "directory exists: $p ${msg:+— $msg}"
  else
    fail "expected directory: $p ${msg:+— $msg}"
  fi
}

assert_dir_absent() {
  local p="$1" msg="${2:-}"
  if [ ! -e "$p" ]; then
    pass_step "absent: $p ${msg:+— $msg}"
  else
    fail "expected absent: $p ${msg:+— $msg}"
  fi
}

assert_file_exists() {
  local p="$1" msg="${2:-}"
  if [ -f "$p" ]; then
    pass_step "file exists: $p ${msg:+— $msg}"
  else
    fail "expected file: $p ${msg:+— $msg}"
  fi
}

assert_file_contains() {
  local p="$1" needle="$2" msg="${3:-}"
  if [ ! -f "$p" ]; then
    fail "$p missing (looking for '$needle') ${msg:+— $msg}"
    return
  fi
  if grep -qF -- "$needle" "$p"; then
    pass_step "$p contains '$needle' ${msg:+— $msg}"
  else
    fail "$p does NOT contain '$needle' ${msg:+— $msg}"
  fi
}

assert_file_lacks() {
  local p="$1" needle="$2" msg="${3:-}"
  if [ ! -f "$p" ]; then
    return
  fi
  if grep -qF -- "$needle" "$p"; then
    fail "$p unexpectedly contains '$needle' ${msg:+— $msg}"
  else
    pass_step "$p lacks '$needle' ${msg:+— $msg}"
  fi
}

assert_eq() {
  local expected="$1" actual="$2" msg="${3:-}"
  if [ "$expected" = "$actual" ]; then
    pass_step "eq: '$expected' ${msg:+— $msg}"
  else
    fail "expected '$expected', got '$actual' ${msg:+— $msg}"
  fi
}

assert_clean_worktree() {
  local repo_dir="$1" msg="${2:-}"
  local out
  out=$(cd "$repo_dir" && git status --porcelain 2>/dev/null)
  if [ -z "$out" ]; then
    pass_step "clean worktree: $repo_dir ${msg:+— $msg}"
  else
    fail "$repo_dir has uncommitted changes:
$out
${msg:+— $msg}"
  fi
}

assert_commit_count() {
  local repo_dir="$1" expected="$2" msg="${3:-}"
  local actual
  actual=$(cd "$repo_dir" && git rev-list --count HEAD 2>/dev/null || echo "no-head")
  if [ "$expected" = "$actual" ]; then
    pass_step "commit count $expected: $repo_dir ${msg:+— $msg}"
  else
    fail "$repo_dir: expected $expected commits, got $actual ${msg:+— $msg}"
  fi
}

assert_no_commit() {
  local repo_dir="$1" msg="${2:-}"
  local has_head
  has_head=$(cd "$repo_dir" && git rev-parse --verify HEAD 2>/dev/null || echo "")
  if [ -z "$has_head" ]; then
    pass_step "no commits in $repo_dir ${msg:+— $msg}"
  else
    fail "$repo_dir unexpectedly has at least one commit: $has_head ${msg:+— $msg}"
  fi
}

assert_last_commit_message_starts_with() {
  local repo_dir="$1" prefix="$2" msg="${3:-}"
  local subject
  subject=$(cd "$repo_dir" && git log -1 --format='%s' 2>/dev/null || echo "")
  if [[ "$subject" == "$prefix"* ]]; then
    pass_step "last commit subject starts with '$prefix' in $repo_dir"
  else
    fail "$repo_dir: last commit subject is '$subject', expected to start with '$prefix' ${msg:+— $msg}"
  fi
}

assert_last_commit_has_trailer() {
  local repo_dir="$1" trailer="$2"
  local body
  body=$(cd "$repo_dir" && git log -1 --format='%B' 2>/dev/null || echo "")
  if echo "$body" | grep -qF -- "$trailer"; then
    pass_step "last commit has trailer '$trailer' in $repo_dir"
  else
    fail "$repo_dir: last commit lacks trailer '$trailer'"
  fi
}

# ---------- runners ----------
start_test() {
  TEST_NAME="$1"
  echo
  echo "${YELLOW}=== ${TEST_NAME} ===${RESET}"
  TESTS_RUN=$((TESTS_RUN + 1))
}

end_run() {
  echo
  if [ "$TESTS_FAILED" -eq 0 ]; then
    echo "${GREEN}All $TESTS_RUN test(s) passed.${RESET}"
    return 0
  fi
  echo "${RED}${TESTS_FAILED} of ${TESTS_RUN} tests failed:${RESET}"
  for d in "${FAIL_DETAIL[@]}"; do
    echo "  - $d"
  done
  return 1
}

# Parse origin from .meta for a child repo (uses python3)
meta_origin_of() {
  local meta="$1" rel="$2"
  python3 - "$meta" "$rel" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
print((data.get("projects") or {}).get(sys.argv[2], "<MISSING>"))
PY
}

meta_count() {
  local meta="$1"
  python3 - "$meta" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
print(len(data.get("projects") or {}))
PY
}

# Configure git identity for tests so commits work in CI without global config
configure_test_git_identity() {
  git config --global user.email "test@pka-skills.test" 2>/dev/null || true
  git config --global user.name  "PKA Test Runner"     2>/dev/null || true
}
