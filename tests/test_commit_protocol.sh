#!/usr/bin/env bash
# Shell tests for the commit/push protocol PRIMITIVES.
#
# Maps to spec scenarios:
#   S17 — Child-repo auto-commit per unit (mechanics: commit lands in child
#         repo, message has Role: prefix and Co-Authored-By: Claude trailer,
#         root has no commit)
#   S18 — Root-repo no auto-commit (mechanics: root .meta change is staged,
#         not committed)
#   S19 — Session-end push: skipped/failed/pushed semantics from push-all.sh
#   S20 — Push failure surfaces, doesn't block (push-all.sh continues across
#         child repos when one push fails)
#   S21 — User "push now" mid-session: same primitive as session-end push
#
# These verify the SCRIPT primitives. The role behavior (when a role decides
# to invoke them) is covered in the JSON evals, not here.

set -u
source "$(dirname "$0")/lib.sh"

configure_test_git_identity

TRAILER="Co-Authored-By: Claude <noreply@anthropic.com>"

# Helper: a hybrid-monorepo workspace with knowledge/ and one project, no remotes.
make_hybrid_ws() {
  local ws
  ws=$(make_workspace)
  mkdir -p "$ws/knowledge" "$ws/projects/foo"
  install_pka_assets "$ws"
  ( cd "$ws" && git init -b main >/dev/null 2>&1 ) >/dev/null 2>&1
  WORKSPACE_ROOT="$ws" bash "$ws/.pka/init_project_repos.sh" >/dev/null 2>&1
  WORKSPACE_ROOT="$ws" bash "$ws/.pka/build-repo-list.sh" >/dev/null 2>&1
  echo "$ws"
}

# ----------- S17: child-repo auto-commit per unit -----------
start_test "S17 — Child-repo auto-commit per unit (Librarian routing simulation)"
ws=$(make_hybrid_ws)
# Simulate librarian routing: drop a file in knowledge/leadership/ and commit it as Librarian
mkdir -p "$ws/knowledge/leadership"
cat > "$ws/knowledge/leadership/2026-04-22-slt-meeting.md" <<'EOF'
---
type: meeting
date: 2026-04-22
topic: slt-meeting
attendees: []
tags: [meeting, leadership]
---

# SLT Meeting

(content)
EOF
# Imagine the librarian also touched _MOC.md as a side-effect of the route
mkdir -p "$ws/knowledge/leadership"
cat > "$ws/knowledge/leadership/_MOC.md" <<'EOF'
# Leadership

## Files
- [[leadership/2026-04-22-slt-meeting]]
EOF

# The mechanic: ONE commit in knowledge/, prefix "Librarian:", trailer present, NO root commit
(
  cd "$ws/knowledge"
  git add -A
  git commit -m "Librarian: Route 2026-04-22-slt-meeting.md to leadership/" -m "" -m "$TRAILER" >/dev/null
)

# Snapshot
assert_last_commit_message_starts_with "$ws/knowledge" "Librarian: Route"
assert_last_commit_has_trailer        "$ws/knowledge" "$TRAILER"
# Root has no new commits (still 0 — root was init'd, never committed)
assert_no_commit "$ws" "root has no commits — librarian must not auto-commit root"
# Number of file changes in this commit is exactly 2 (the routed file + the MOC update)
files_in_commit=$(cd "$ws/knowledge" && git show --name-only --format= HEAD | grep -v '^$' | wc -l | tr -d ' ')
assert_eq "2" "$files_in_commit" "single semantic unit groups routed file + MOC update"

cleanup_workspace "$ws"

# ----------- S18: root-repo no auto-commit -----------
start_test "S18 — Root-repo no auto-commit (graduation .meta side effect)"
ws=$(make_hybrid_ws)
# Add some content to widget so graduation has a payload
echo "widget content" > "$ws/projects/foo/README.md"
( cd "$ws/projects/foo" && git add -A && git commit -m "more content" -m "" -m "$TRAILER" >/dev/null 2>&1 )

# Run graduation
out=$(WORKSPACE_ROOT="$ws" bash "$ws/.pka/graduate.sh" foo reference 2>&1)

# After graduation:
#   - knowledge/ has +1 commit
#   - root has 0 commits (still pristine)
#   - root .meta has projects/foo removed
#   - root has staged changes (the .meta edit and the projects/foo deletion)
assert_no_commit "$ws" "root remains uncommitted — graduate.sh stages but never commits root"
assert_last_commit_message_starts_with "$ws/knowledge" "Graduate: foo"
assert_last_commit_has_trailer        "$ws/knowledge" "$TRAILER"

# .meta should no longer reference projects/foo
foo_origin=$(meta_origin_of "$ws/.meta" "projects/foo")
assert_eq "<MISSING>" "$foo_origin" "projects/foo removed from .meta"

# Root staged changes include .meta and the projects/foo deletion
staged=$(cd "$ws" && git diff --cached --name-only)
if echo "$staged" | grep -qE "^\.meta$"; then
  pass_step "root has .meta staged"
else
  fail "root .meta change not staged. Staged: $staged"
fi

cleanup_workspace "$ws"

# ----------- S19/S20: push-all.sh skip/failure semantics -----------
start_test "S19/S20 — push-all.sh: skipped (no origin) reported as skipped, not failure"
ws=$(make_hybrid_ws)
# All entries in .meta have empty origin URLs after init.
out=$(WORKSPACE_ROOT="$ws" bash "$ws/.pka/push-all.sh" 2>&1)
exit_code=$?

# Should exit 0 (skipped, not failed)
assert_eq "0" "$exit_code" "no failures when origins are empty"
if echo "$out" | grep -qi "skip"; then
  pass_step "push-all reports child repos as skipped"
else
  fail "push-all output does not mention 'skip'"
fi
if echo "$out" | grep -qE "Failed:[[:space:]]+0|^Failed:.*0"; then
  pass_step "push-all reports zero failures"
else
  # Allow absence of failed line if all skipped
  if echo "$out" | grep -qE "^Failed:"; then
    fail "push-all reports failures when there should be none"
  else
    pass_step "push-all has no Failed line (none failed)"
  fi
fi

cleanup_workspace "$ws"

start_test "S20 — push-all.sh: one failed push surfaces but doesn't block others"
ws=$(make_hybrid_ws)
# Set up a remote that exists for projects/foo and one that DOESN'T for knowledge.
mkdir -p /tmp/pka-fake-remotes
foo_bare=$(mktemp -d /tmp/pka-fake-remotes/foo-bare.XXXX)
( cd "$foo_bare" && git init --bare -b main >/dev/null 2>&1 )
( cd "$ws/projects/foo" && git remote add origin "$foo_bare" )
# unreachable origin for knowledge: a path that doesn't exist
( cd "$ws/knowledge" && git remote add origin "/tmp/pka-fake-remotes/nonexistent-$(date +%s).bare" )

# Make a new commit in each child so there's something to push
echo "more content for foo" >> "$ws/projects/foo/README.md"
( cd "$ws/projects/foo" && git add -A && git commit -m "Librarian: foo route" -m "" -m "$TRAILER" >/dev/null )
echo "more content for knowledge" >> "$ws/knowledge/README.md" 2>/dev/null || echo "kn" > "$ws/knowledge/README.md"
( cd "$ws/knowledge" && git add -A && git commit -m "Librarian: kn route" -m "" -m "$TRAILER" >/dev/null )

# Update .meta with the (now-real) origins
WORKSPACE_ROOT="$ws" bash "$ws/.pka/build-repo-list.sh" >/dev/null 2>&1

# Run push-all.sh
out=$(WORKSPACE_ROOT="$ws" bash "$ws/.pka/push-all.sh" 2>&1)
exit_code=$?

# foo should have pushed; knowledge should have failed.
# Exit code 1 = at least one failure
assert_eq "1" "$exit_code" "exit 1 when at least one push fails"
if echo "$out" | grep -q "Pushed:"; then
  pass_step "summary has Pushed: section"
else
  fail "summary missing Pushed: section"
fi
if echo "$out" | grep -q "Failed:"; then
  pass_step "summary has Failed: section"
else
  fail "summary missing Failed: section"
fi
if echo "$out" | grep -q "knowledge"; then
  pass_step "knowledge mentioned in failures"
else
  fail "knowledge not in failure list"
fi
# Verify the bare repo got the push (foo was pushed despite knowledge failing)
foo_pushed=$(cd "$foo_bare" && git rev-list --count main 2>/dev/null || echo "0")
if [ "${foo_pushed:-0}" -ge 1 ]; then
  pass_step "projects/foo successfully pushed despite knowledge failure ($foo_pushed commits)"
else
  fail "projects/foo did NOT push (failure in knowledge blocked others)"
fi

cleanup_workspace "$ws"
rm -rf "$foo_bare"

# ----------- S21: mid-session "push now" uses same primitive -----------
start_test "S21 — mid-session push uses same primitive (push-all.sh runs and returns)"
ws=$(make_hybrid_ws)
# Empty origins — should all skip, exit 0, return summary
start=$(date +%s)
out=$(WORKSPACE_ROOT="$ws" bash "$ws/.pka/push-all.sh" 2>&1)
exit_code=$?
end=$(date +%s)

assert_eq "0" "$exit_code" "mid-session push returns success when nothing to push"
elapsed=$((end - start))
if [ "$elapsed" -lt 10 ]; then
  pass_step "push completes quickly ($elapsed s) — does not block session"
else
  fail "push took too long ($elapsed s)"
fi
if echo "$out" | grep -qE "summary|Pushed|Skipped"; then
  pass_step "push returns a summary"
else
  fail "push lacks summary structure"
fi

cleanup_workspace "$ws"

end_run
