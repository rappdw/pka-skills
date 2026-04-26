#!/usr/bin/env bash
# Run all shell-based tests for the pka-skills addendum.
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

run_suite "git-bootstrap"      "$THIS_DIR/test_git_bootstrap.sh"
run_suite "obsidian-bootstrap" "$THIS_DIR/test_obsidian_bootstrap.sh"
run_suite "commit-protocol"    "$THIS_DIR/test_commit_protocol.sh"

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
