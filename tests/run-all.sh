#!/usr/bin/env bash
# Run all the test suites.
#
# Each individual test script exits 0 when its tests pass, non-zero on failure.
# This runner aggregates and prints a final summary.

set -u
THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN=$(printf '\033[32m')
RED=$(printf '\033[31m')
RESET=$(printf '\033[0m')

run_suite() {
  local name="$1" path="$2"
  echo
  echo "##############################"
  echo "# Suite: $name"
  echo "##############################"
  if bash "$path"; then
    SUITES_PASS+=("$name")
  else
    SUITES_FAIL+=("$name")
  fi
}

SUITES_PASS=()
SUITES_FAIL=()

# The suites must never write to the developer's real git configuration (an
# earlier version did, and a release was committed under the test identity).
# Fingerprint it before and after; a difference fails the run.
git_config_fingerprint() {
  { git config --global --list 2>/dev/null; cat "${HOME}/.gitconfig" 2>/dev/null; } | cksum
}
GIT_CONFIG_BEFORE=$(git_config_fingerprint)

# First: if the harness could remove a directory it did not create, stop here.
run_suite "harness-safety"     "$THIS_DIR/test_harness_safety.sh"
if [ "${#SUITES_FAIL[@]}" -gt 0 ]; then
  echo "${RED}The harness safety check failed; not running the other suites.${RESET}" >&2
  exit 1
fi

run_suite "obsidian-bootstrap" "$THIS_DIR/test_obsidian_bootstrap.sh"
run_suite "upgrade"            "$THIS_DIR/test_upgrade.sh"
run_suite "pointer-layer"      "$THIS_DIR/test_pointer_layer.sh"
run_suite "pka-tools"          "$THIS_DIR/test_tools.sh"

if [ "$GIT_CONFIG_BEFORE" = "$(git_config_fingerprint)" ]; then
  SUITES_PASS+=("global git config untouched")
else
  echo "${RED}The test run changed your global git configuration.${RESET}" >&2
  SUITES_FAIL+=("global git config untouched")
fi

echo
echo "=============================="
echo "Final summary"
echo "=============================="
echo "${GREEN}Passed suites:${RESET} ${#SUITES_PASS[@]}"
for s in "${SUITES_PASS[@]:-}"; do [ -n "$s" ] && echo "  + $s"; done
if [ ${#SUITES_FAIL[@]} -gt 0 ]; then
  echo "${RED}Failed suites:${RESET} ${#SUITES_FAIL[@]}"
  for s in "${SUITES_FAIL[@]}"; do echo "  ! $s"; done
  exit 1
fi
echo "${GREEN}All suites passed.${RESET}"
exit 0
