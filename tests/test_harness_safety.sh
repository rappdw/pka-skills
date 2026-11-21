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
# An absolute path: the cases below change directory, and a relative TMPDIR
# would then name a different folder.
BASE=$(cd "$BASE" && pwd -P) || exit 1
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

# A directory with a name like ours, which the harness did not create: at the
# top of the temp folder and deeper inside it. Neither may be registered, and
# neither may be removed, whatever its name.
mkdir -p "$SACRIFICE/tmp-ok/pka-test.keep" "$SACRIFICE/tmp-ok/elsewhere/pka-test.keep" \
         "$SACRIFICE/tmp-ok/pka-scratch.keep" "$SACRIFICE/tmp-ok/pka-test-home.keep"
echo precious > "$SACRIFICE/tmp-ok/elsewhere/pka-test.keep/file.txt"
run_case not-created-here "$SACRIFICE/tmp-ok" 'cd /; for d in pka-test.keep elsewhere/pka-test.keep pka-scratch.keep pka-test-home.keep; do register_cleanup "$TMPDIR/$d"; cleanup_workspace "$TMPDIR/$d"; PKA_TEST_CLEANUP+=("$TMPDIR/$d"); done; echo done'
kept=0
for d in pka-test.keep elsewhere/pka-test.keep pka-scratch.keep pka-test-home.keep; do
  [ -d "$SACRIFICE/tmp-ok/$d" ] && kept=$((kept + 1))
done
[ "$kept" -eq 4 ] && pass "a directory the harness did not create is never removed, whatever its name" || fail "$((4 - kept)) directories the harness did not create were removed"
[ -f "$SACRIFICE/tmp-ok/elsewhere/pka-test.keep/file.txt" ] && pass "its content is untouched" || fail "content of a foreign directory was removed"
[ "$(grep -c "refusing to register" "$CASE.out")" -eq 4 ] && pass "each refusal is reported" || fail "refusals not reported: $(cat "$CASE.out")"

# What it did create is removed, and the record of it too.
run_case record "$SACRIFICE/tmp-ok" 'a=$(make_workspace) || exit 1; b=$(make_scratch_dir) || exit 1; register_cleanup "$b"; echo "$a" > made.txt; echo "$b" >> made.txt; echo "$PKA_TEST_CREATED" > record.txt; grep -Fxq "$a" "$PKA_TEST_CREATED" && grep -Fxq "$b" "$PKA_TEST_CREATED" && echo recorded; cleanup_workspace "$a"; [ -d "$a" ] || echo workspace-removed'
grep -q recorded "$CASE.out" && pass "every directory it creates is on its record" || fail "a created directory is not on the record"
grep -q workspace-removed "$CASE.out" && pass "cleanup_workspace removes a workspace it created" || fail "cleanup_workspace left its own workspace"
left=0
while IFS= read -r made; do [ -n "$made" ] && [ -e "$made" ] && left=$((left + 1)); done < "$CASE/made.txt"
[ "$left" -eq 0 ] && pass "what it created is removed on exit" || fail "$left of its directories were left behind"
[ ! -e "$(cat "$CASE/record.txt")" ] && pass "the record is removed on exit" || fail "the record was left behind"
[ -z "$(ls "$SACRIFICE/tmp-ok" | grep "pka-test-created")" ] && pass "no record file is left in the temp folder" || fail "record files left in the temp folder"

# A record that names a foreign directory (edited, or a stale path that was
# reused) is still not enough: the name and the position are checked too.
mkdir -p "$SACRIFICE/tmp-ok/not-ours"
run_case record-is-not-enough "$SACRIFICE/tmp-ok" 'printf "%s\n" "$TMPDIR/not-ours" "$(pwd -P)" >> "$PKA_TEST_CREATED"; register_cleanup "$TMPDIR/not-ours"; register_cleanup "$(pwd -P)"; PKA_TEST_CLEANUP+=("$TMPDIR/not-ours" "$(pwd -P)"); echo done'
[ -d "$SACRIFICE/tmp-ok/not-ours" ] && pass "a recorded path without one of the harness's names is not removed" || fail "a directory without a harness name was removed"
[ -f "$CASE/canary.txt" ] && pass "a recorded current directory is not removed" || fail "the current directory was removed"

# A relative TMPDIR means the folder it named when the script started.
mkdir -p "$SACRIFICE/relative/tmp" "$SACRIFICE/relative/case"
cp "$HERE/lib.sh" "$SACRIFICE/relative/case/lib.sh"
echo canary > "$SACRIFICE/relative/case/canary.txt"
printf '%s\n' '#!/usr/bin/env bash' 'source ./lib.sh' 'd=$(make_scratch_dir) || exit 1; register_cleanup "$d"; echo "$d" > made.txt; cd /; echo done' > "$SACRIFICE/relative/case/case.sh"
(cd "$SACRIFICE/relative/case" && TMPDIR="../tmp" bash ./case.sh > "$SACRIFICE/relative/out" 2>&1)
RC=$?
[ "$RC" -eq 0 ] && grep -q done "$SACRIFICE/relative/out" && pass "a relative TMPDIR works" || fail "a relative TMPDIR failed: $(cat "$SACRIFICE/relative/out")"
made=$(cat "$SACRIFICE/relative/case/made.txt" 2>/dev/null)
case "$made" in "$SACRIFICE"/relative/tmp/pka-scratch.*) pass "its directories are made in the folder TMPDIR named" ;; *) fail "made '$made', not under relative/tmp" ;; esac
[ -n "$made" ] && [ ! -e "$made" ] && pass "and removed from there after the script changed directory" || fail "the scratch directory was left behind"
[ -f "$SACRIFICE/relative/case/canary.txt" ] && pass "the current directory survives a relative TMPDIR" || fail "the current directory was removed"
[ -z "$(ls "$SACRIFICE/relative/tmp")" ] && pass "nothing is left in the relative temp folder" || fail "left in the temp folder: $(ls "$SACRIFICE/relative/tmp")"

# This suite itself, started with a relative TMPDIR (it used to fail three checks).
if [ -z "${PKA_HARNESS_SAFETY_NESTED:-}" ]; then
  mkdir -p "$SACRIFICE/nested/tmp"
  (cd "$SACRIFICE/nested" && PKA_HARNESS_SAFETY_NESTED=1 TMPDIR="tmp" bash "$HERE/test_harness_safety.sh" > "$SACRIFICE/nested.out" 2>&1)
  [ $? -eq 0 ] && pass "this suite passes when TMPDIR is relative" || fail "this suite fails when TMPDIR is relative: $(grep FAIL "$SACRIFICE/nested.out")"
fi

# When a workspace cannot be created, a test script must stop: it must not go
# on with an empty path (`mkdir -p "$ws/.pka"` would then write to /.pka).
mkdir -p "$SACRIFICE/shim"
printf '%s\n' '#!/bin/sh' 'exit 1' > "$SACRIFICE/shim/mktemp"
chmod +x "$SACRIFICE/shim/mktemp"
run_case no-mktemp "$SACRIFICE/tmp-ok" 'echo sourced; ws=$(make_workspace) || exit 1; echo "reached with [$ws]"'
grep -q sourced "$CASE.out" && pass "a working mktemp lets the script start" || fail "the script did not start"
CASE="$SACRIFICE/mktemp-fails"; mkdir -p "$CASE"; cp "$HERE/lib.sh" "$CASE/lib.sh"
printf '%s\n' '#!/usr/bin/env bash' 'source ./lib.sh' 'PATH="'"$SACRIFICE/shim"':$PATH"' 'ws=$(make_workspace) || exit 1' 'echo "reached with [$ws]"' > "$CASE/case.sh"
(cd "$CASE" && TMPDIR="$SACRIFICE/tmp-ok" bash ./case.sh > "$CASE.out" 2>&1); RC=$?
[ "$RC" -ne 0 ] && pass "a script stops when its workspace cannot be created" || fail "the script carried on without a workspace"
grep -q "reached" "$CASE.out" && fail "the script ran on with an empty workspace path" || pass "nothing ran with an empty workspace path"
grep -q "could not create a workspace" "$CASE.out" && pass "and says why" || fail "no message about the workspace"
unguarded=$(grep -nE '=\$\((make_workspace|make_scratch_dir|make_v15_workspace|new_vault)\)' "$HERE"/test_*.sh \
            | grep -v "test_harness_safety.sh" | grep -vE '\|\| (exit|return) 1' || true)
[ -z "$unguarded" ] && pass "every test script stops when a workspace cannot be created" || fail "unguarded workspace creation: $unguarded"

rm -rf "$SACRIFICE"
echo
if [ "$fails" -eq 0 ]; then echo "harness safety: all checks passed"; exit 0; fi
echo "harness safety: $fails check(s) FAILED"; exit 1
