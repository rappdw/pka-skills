#!/usr/bin/env bash
# The test harness must never remove a directory it did not create.
#
# Regression: with TMPDIR set to a folder that did not exist, tests/lib.sh
# registered the CURRENT directory for removal and deleted it on exit.
#
# Every case below runs a tiny script in a sacrificial directory holding a
# canary file, with a COPY of lib.sh, so that a regression here deletes the
# sacrificial directory and nothing else.
set -u

HERE=$(cd "$(dirname "$0")" && pwd -P)
BASE="${TMPDIR:-/tmp}"
if [ ! -d "$BASE" ] || [ ! -w "$BASE" ]; then
  echo "tests: the temp folder '$BASE' (TMPDIR) is not a writable directory. Create it, or unset TMPDIR." >&2
  exit 1
fi
SACRIFICE=$(mktemp -d "$BASE/pka-harness-check.XXXXXX") || exit 1
case "${SACRIFICE##*/}" in pka-harness-check.*) ;; *) echo "unexpected temp name"; exit 1 ;; esac

fails=0
pass() { printf '  ok    %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

run_case() {   # NAME  TMPDIR-VALUE  BODY  -> sets RC, leaves the case dir in CASE
  CASE="$SACRIFICE/$1"
  mkdir -p "$CASE"
  cp "$HERE/lib.sh" "$CASE/lib.sh"
  echo canary > "$CASE/canary.txt"
  printf '%s\n' '#!/usr/bin/env bash' 'source ./lib.sh' "$3" > "$CASE/case.sh"
  (cd "$CASE" && TMPDIR="$2" bash ./case.sh >"$CASE.out" 2>&1)
  RC=$?
}

echo "== harness safety"

run_case missing-tmpdir "$SACRIFICE/does-not-exist" 'configure_test_git_identity; echo reached'
[ "$RC" -ne 0 ] && pass "a missing TMPDIR stops the script" || fail "a missing TMPDIR did not stop the script"
[ -f "$CASE/canary.txt" ] && pass "the current directory survives a missing TMPDIR" || fail "the current directory was removed"
grep -q "not a writable directory" "$CASE.out" && pass "the message names the problem" || fail "no clear message"
grep -q reached "$CASE.out" && fail "the script carried on after the failure" || pass "nothing ran after the failure"

mkdir -p "$SACRIFICE/tmp-ok"
run_case register-cwd "$SACRIFICE/tmp-ok" 'register_cleanup "$(pwd -P)"; register_cleanup ""; register_cleanup "/"; echo done'
[ -f "$CASE/canary.txt" ] && pass "the current directory cannot be registered for removal" || fail "the current directory was removed"
grep -q "refusing to register" "$CASE.out" && pass "a refused registration is reported" || fail "refusal not reported"

run_case scratch-and-home "$SACRIFICE/tmp-ok" 'd=$(make_scratch_dir); register_cleanup "$d"; configure_test_git_identity; echo "$d" > made.txt; echo "$PKA_TEST_HOME" >> made.txt'
[ "$RC" -eq 0 ] && pass "normal use still works" || fail "normal use failed"
left=0
while IFS= read -r made; do [ -n "$made" ] && [ -e "$made" ] && left=$((left + 1)); done < "$CASE/made.txt"
[ "$left" -eq 0 ] && pass "its own directories are removed on exit" || fail "$left directories were left behind"
[ -f "$CASE/canary.txt" ] && pass "the current directory survives normal use" || fail "the current directory was removed"

mkdir -p "$SACRIFICE/tmp-ok/pka-test.fake"
run_case inside-own-dir "$SACRIFICE/tmp-ok" 'cd "$TMPDIR/pka-test.fake"; register_cleanup "$(pwd -P)"; echo done'
[ -d "$SACRIFICE/tmp-ok/pka-test.fake" ] && pass "a directory the script is standing in is not removed" || fail "the directory under the script was removed"

rm -rf "$SACRIFICE"
echo
if [ "$fails" -eq 0 ]; then echo "harness safety: all checks passed"; exit 0; fi
echo "harness safety: $fails check(s) FAILED"; exit 1
