#!/usr/bin/env bash
# Common helpers for pka-skills shell tests.
#
# Usage in test scripts:
#   source "$(dirname "$0")/lib.sh"
#   ws=$(make_workspace)
#   install_pka_tools "$ws"
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
# Workspaces are created with their physical path (no symlinked prefix such as
# macOS's /var -> /private/var) so tests can compare paths with script output.
make_workspace() {
  local dir
  dir=$(mktemp -d "${TMPDIR:-/tmp}/pka-test.XXXXXX")
  (cd "$dir" && pwd -P)
}

cleanup_workspace() {
  local dir="$1"
  case "$dir" in
    */pka-test.*) rm -rf "$dir" ;;
  esac
}

# Paths registered here are removed when the test script exits. Use this
# instead of setting an EXIT trap in a test script: there is one trap, owned
# by this file.
PKA_TEST_CLEANUP=()
register_cleanup() {
  PKA_TEST_CLEANUP+=("$1")
}
_pka_test_cleanup() {
  local p
  for p in "${PKA_TEST_CLEANUP[@]:-}"; do
    [ -n "$p" ] && rm -rf "$p"
  done
}
trap _pka_test_cleanup EXIT

# A scratch directory outside any workspace. Call it as
#   d=$(make_scratch_dir); register_cleanup "$d"
# (registration cannot happen inside the command substitution).
make_scratch_dir() {
  local dir
  dir=$(mktemp -d "${TMPDIR:-/tmp}/pka-scratch.XXXXXX")
  dir=$(cd "$dir" && pwd -P)
  echo "$dir"
}

# Install the plugin's helpers into a workspace, as bootstrap does.
install_pka_tools() {
  local ws="$1"
  mkdir -p "$ws/.pka"
  python3 "${ASSETS_DIR}/tools/pka-tools" install --workspace "$ws" >/dev/null || {
    echo "${RED}pka-tools install failed for $ws${RESET}" >&2
    return 1
  }
}

# Run the workspace's vendored tool: pka_tools <workspace> <command> [args...]
pka_tools() {
  local ws="$1"; shift
  python3 "$ws/.pka/bin/pka-tools" --workspace "$ws" "$@"
}

# ---------- portable helpers (GNU and BSD userlands differ) ----------
# Content fingerprint of a file. `cksum` is POSIX; `md5sum` is not on every Mac.
file_hash() {
  cksum < "$1" | awk '{print $1 "-" $2}'
}

# Replace a literal string in a file, in place. (`sed -i` takes different
# arguments on GNU and BSD.)
replace_in_file() {
  python3 - "$1" "$2" "$3" <<'PY'
import sys
path, old, new = sys.argv[1:4]
with open(path, encoding="utf-8", newline="") as f:
    text = f.read()
with open(path, "w", encoding="utf-8", newline="") as f:
    f.write(text.replace(old, new))
PY
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

# Give the tests a git identity WITHOUT touching the developer's own config.
#
# Git is pointed at a throwaway home directory: HOME and GIT_CONFIG_GLOBAL both
# lead there, the system config is ignored, and XDG_CONFIG_HOME is cleared.
# Nothing a test does with `git config --global` can reach the real
# ~/.gitconfig. (An earlier version of this helper wrote the test identity
# into the real global config, and a release was later committed under it.)
configure_test_git_identity() {
  PKA_TEST_HOME=$(mktemp -d "${TMPDIR:-/tmp}/pka-test-home.XXXXXX")
  PKA_TEST_HOME=$(cd "$PKA_TEST_HOME" && pwd -P)
  register_cleanup "$PKA_TEST_HOME"
  export HOME="$PKA_TEST_HOME"
  export GIT_CONFIG_GLOBAL="$PKA_TEST_HOME/.gitconfig"
  export GIT_CONFIG_NOSYSTEM=1
  unset XDG_CONFIG_HOME
  # Identity variables inherited from the caller would override the config.
  unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL EMAIL
  git config --global user.email "test@pka-skills.test"
  git config --global user.name  "PKA Test Runner"
  git config --global init.defaultBranch main
  git config --global commit.gpgsign false
  git config --global protocol.file.allow always
}
