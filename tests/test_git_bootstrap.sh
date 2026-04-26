#!/usr/bin/env bash
# Shell tests for the git/meta hybrid monorepo bootstrap algorithm.
# Maps to spec scenarios S12 (cold), S13 (idempotent), S14 (partial), S15 (LFS-missing flagged), S16 (no remotes/push), S22 (graduation).

set -u
source "$(dirname "$0")/lib.sh"

configure_test_git_identity

# Helper: run init_project_repos.sh in a workspace and capture output
run_init() {
  local ws="$1"
  ( cd "$ws" && WORKSPACE_ROOT="$ws" bash .pka/init_project_repos.sh )
}

run_build_repo_list() {
  local ws="$1"
  ( cd "$ws" && WORKSPACE_ROOT="$ws" bash .pka/build-repo-list.sh )
}

# ----------- S12: cold workspace -----------
start_test "S12 — Git bootstrap, cold workspace"
ws=$(make_workspace)
mkdir -p "$ws/knowledge" "$ws/projects/foo" "$ws/projects/bar"
echo "knowledge content" > "$ws/knowledge/README.md"
echo "foo content"        > "$ws/projects/foo/README.md"
echo "bar content"        > "$ws/projects/bar/README.md"

install_pka_assets "$ws"

# Init child repos
init_out=$(run_init "$ws" 2>&1)

# Init root .git WITHOUT committing (this is the orchestrator's job per the spec)
( cd "$ws" && git init -b main >/dev/null 2>&1 )

# Generate root .gitignore (mimics step 4 of the bootstrap procedure)
cat > "$ws/.gitignore" <<'EOF'
knowledge/
projects/
owner-inbox/
team-inbox/
.pka/knowledge.db
.pka/knowledge.db-*
.pka/*-log.txt
EOF

# Build .meta
build_out=$(run_build_repo_list "$ws" 2>&1)

# Stage everything in root (no commit)
( cd "$ws" && git add -A )

# Assertions
assert_dir_exists "$ws/.git"               "root .git initialized"
assert_no_commit  "$ws"                    "root has no commits (human review gate)"
assert_dir_exists "$ws/knowledge/.git"     "knowledge/ initialized"
assert_dir_exists "$ws/projects/foo/.git"  "projects/foo initialized"
assert_dir_exists "$ws/projects/bar/.git"  "projects/bar initialized"
assert_file_exists "$ws/.gitignore"
assert_file_exists "$ws/.meta"
assert_file_exists "$ws/knowledge/.gitattributes"
assert_file_exists "$ws/knowledge/.gitignore"
assert_file_contains "$ws/knowledge/.gitattributes" "filter=lfs" "LFS filters present"
# init creates a two-commit history per child repo: (1) LFS+gitignore config,
# (2) initial content. Each carries the role-prefixed message + trailer.
assert_commit_count "$ws/knowledge"        2 "knowledge/ has two-commit init history"
assert_commit_count "$ws/projects/foo"     2 "projects/foo has two-commit init history"
assert_commit_count "$ws/projects/bar"     2 "projects/bar has two-commit init history"
assert_last_commit_message_starts_with "$ws/knowledge"     "Bootstrap (git):"
assert_last_commit_has_trailer        "$ws/knowledge"     "Co-Authored-By: Claude <noreply@anthropic.com>"
assert_last_commit_message_starts_with "$ws/projects/foo" "Bootstrap (git):"
assert_last_commit_has_trailer        "$ws/projects/foo" "Co-Authored-By: Claude <noreply@anthropic.com>"

# .meta has 3 entries with empty origins
count=$(meta_count "$ws/.meta")
assert_eq "3" "$count" ".meta has 3 entries"
assert_eq "" "$(meta_origin_of "$ws/.meta" "knowledge")"        "knowledge origin empty"
assert_eq "" "$(meta_origin_of "$ws/.meta" "projects/foo")"     "projects/foo origin empty"
assert_eq "" "$(meta_origin_of "$ws/.meta" "projects/bar")"     "projects/bar origin empty"

cleanup_workspace "$ws"

# ----------- S13: idempotency -----------
start_test "S13 — Git bootstrap, idempotent"
ws=$(make_workspace)
mkdir -p "$ws/knowledge" "$ws/projects/foo"
echo "k" > "$ws/knowledge/README.md"
echo "f" > "$ws/projects/foo/README.md"
install_pka_assets "$ws"
run_init "$ws" >/dev/null 2>&1
run_build_repo_list "$ws" >/dev/null 2>&1

# Snapshot state
meta_before=$(cat "$ws/.meta")
foo_head_before=$(cd "$ws/projects/foo" && git rev-parse HEAD)
knowledge_head_before=$(cd "$ws/knowledge" && git rev-parse HEAD)

# Re-run
run_init "$ws" >/dev/null 2>&1
run_build_repo_list "$ws" >/dev/null 2>&1

# Snapshot after
meta_after=$(cat "$ws/.meta")
foo_head_after=$(cd "$ws/projects/foo" && git rev-parse HEAD)
knowledge_head_after=$(cd "$ws/knowledge" && git rev-parse HEAD)

assert_eq "$meta_before" "$meta_after"               ".meta unchanged on re-run"
assert_eq "$foo_head_before" "$foo_head_after"       "projects/foo HEAD unchanged"
assert_eq "$knowledge_head_before" "$knowledge_head_after" "knowledge HEAD unchanged"
assert_clean_worktree "$ws/knowledge"   "knowledge worktree clean after re-run"
assert_clean_worktree "$ws/projects/foo" "projects/foo worktree clean after re-run"

cleanup_workspace "$ws"

# ----------- S14: partial pre-existing -----------
start_test "S14 — Git bootstrap, partial pre-existing"
ws=$(make_workspace)
mkdir -p "$ws/knowledge" "$ws/projects/newbie"
echo "k" > "$ws/knowledge/README.md"
echo "n" > "$ws/projects/newbie/README.md"
install_pka_assets "$ws"

# Pre-init knowledge with LFS
cp "$ws/.pka/gitattributes-template" "$ws/knowledge/.gitattributes"
cp "$ws/.pka/gitignore-template"     "$ws/knowledge/.gitignore"
( cd "$ws/knowledge" && git init -b main >/dev/null 2>&1 && git lfs install --local >/dev/null 2>&1 \
    && git add -A && git commit -m "preexisting" -m "" -m "Co-Authored-By: Claude <noreply@anthropic.com>" >/dev/null 2>&1 )
knowledge_head_before=$(cd "$ws/knowledge" && git rev-parse HEAD)

# Now run init
run_init "$ws" >/dev/null 2>&1
run_build_repo_list "$ws" >/dev/null 2>&1

knowledge_head_after=$(cd "$ws/knowledge" && git rev-parse HEAD)

assert_eq "$knowledge_head_before" "$knowledge_head_after" "preexisting knowledge HEAD untouched"
assert_dir_exists "$ws/projects/newbie/.git"               "newbie initialized"
assert_commit_count "$ws/projects/newbie" 2                "newbie has two-commit init history"
assert_file_contains "$ws/projects/newbie/.gitattributes" "filter=lfs" "newbie has LFS filters"

cleanup_workspace "$ws"

# ----------- S15: LFS-missing project flagged -----------
start_test "S15 — Git bootstrap, LFS-missing project flagged"
ws=$(make_workspace)
mkdir -p "$ws/projects/legacy"
echo "legacy" > "$ws/projects/legacy/README.md"
install_pka_assets "$ws"

# Pre-init legacy with .git but NO LFS filters
( cd "$ws/projects/legacy" && git init -b main >/dev/null 2>&1 \
    && git add -A && git commit -m "legacy initial" >/dev/null 2>&1 )
legacy_head_before=$(cd "$ws/projects/legacy" && git rev-parse HEAD)

# Capture init output
out=$(run_init "$ws" 2>&1)

legacy_head_after=$(cd "$ws/projects/legacy" && git rev-parse HEAD)
assert_eq "$legacy_head_before" "$legacy_head_after" "legacy HEAD unchanged (not reinit'd)"
assert_file_lacks "$ws/projects/legacy/.gitattributes" "filter=lfs" "legacy still lacks LFS filters"
# The summary should mention legacy as a flagged project
if echo "$out" | grep -q "projects/legacy"; then
  pass_step "init output mentions projects/legacy in flagged list"
else
  fail "init output does not flag projects/legacy"
fi
if echo "$out" | grep -qi "reinit"; then
  pass_step "init output references reinit-project-with-lfs.sh"
else
  fail "init output does not reference reinit-project-with-lfs.sh"
fi

cleanup_workspace "$ws"

# ----------- S16: no remotes, no push -----------
start_test "S16 — Git bootstrap does not create remotes or push"
ws=$(make_workspace)
mkdir -p "$ws/knowledge" "$ws/projects/foo"
install_pka_assets "$ws"

# Trace executed git commands by wrapping git via PATH.
# CRITICAL: the wrapper must dispatch to the absolute git binary, NOT to
# `/usr/bin/env git`, otherwise PATH (which still has the wrapper first)
# would re-resolve back to the wrapper -> infinite recursion.
real_git=$(command -v git)
trace=$(mktemp)
trap 'rm -f "$trace"' EXIT
trace_dir=$(mktemp -d)
cat > "$trace_dir/git" <<EOF
#!/usr/bin/env bash
echo "git \$*" >> "$trace"
exec "$real_git" "\$@"
EOF
chmod +x "$trace_dir/git"

PATH="$trace_dir:$PATH" run_init "$ws" >/dev/null 2>&1
PATH="$trace_dir:$PATH" run_build_repo_list "$ws" >/dev/null 2>&1

# Assert no `git push` and no `git remote add` invocations
if grep -q "git push" "$trace"; then
  fail "init invoked 'git push' (should never)"
else
  pass_step "no 'git push' invoked"
fi
if grep -qE "git remote add( |$)" "$trace"; then
  fail "init invoked 'git remote add' (should never)"
else
  pass_step "no 'git remote add' invoked"
fi

# Also: confirm child repos have NO origin set
foo_origin=$(cd "$ws/projects/foo" && git remote get-url origin 2>/dev/null || echo "")
knowledge_origin=$(cd "$ws/knowledge" && git remote get-url origin 2>/dev/null || echo "")
assert_eq "" "$foo_origin"        "projects/foo has no origin"
assert_eq "" "$knowledge_origin"  "knowledge has no origin"

cleanup_workspace "$ws"

# ----------- S22: graduation commit sequence -----------
start_test "S22 — Graduation commit sequence"
ws=$(make_workspace)
mkdir -p "$ws/knowledge" "$ws/projects/widget"
echo "widget feature 1" > "$ws/projects/widget/README.md"
echo "widget docs"      > "$ws/projects/widget/DOC.md"
install_pka_assets "$ws"

# Bootstrap state: knowledge with LFS and an initial commit; widget with .git
run_init "$ws" >/dev/null 2>&1

# Set a fake origin on widget so we can verify the archival message
( cd "$ws/projects/widget" && git remote add origin "https://gitea.example.com/dan/widget.git" )
run_build_repo_list "$ws" >/dev/null 2>&1

# Init root .git so the graduation can stage there
( cd "$ws" && git init -b main >/dev/null 2>&1 )
( cd "$ws" && git add -A 2>/dev/null )

# Snapshot
knowledge_count_before=$(cd "$ws/knowledge" && git rev-list --count HEAD)

# Run graduation
out=$(cd "$ws" && WORKSPACE_ROOT="$ws" bash .pka/graduate.sh widget reference 2>&1)
echo "$out" | sed 's/^/  > /'

# Assertions
assert_dir_absent "$ws/projects/widget"               "source directory removed"
assert_dir_exists "$ws/knowledge/reference/widget"    "destination created"
assert_file_exists "$ws/knowledge/reference/widget/README.md" "content moved"
assert_file_exists "$ws/knowledge/reference/widget/DOC.md"

# Knowledge has exactly one new commit
knowledge_count_after=$(cd "$ws/knowledge" && git rev-list --count HEAD)
assert_eq "$((knowledge_count_before + 1))" "$knowledge_count_after" "knowledge has +1 commit"
assert_last_commit_message_starts_with "$ws/knowledge" "Graduate: widget"
assert_last_commit_has_trailer        "$ws/knowledge" "Co-Authored-By: Claude <noreply@anthropic.com>"

# Root: .meta updated, projects/widget/ removal staged, BUT NO ROOT COMMIT
assert_no_commit "$ws" "root has no commits after graduation"
# Backup created — graduate.sh prefers `git bundle` (more portable than tar);
# falls back to tar only on truly-empty repos. Either format is acceptable.
backup_count=$(ls -1 "$ws/.pka/graduate-backups"/*.bundle "$ws/.pka/graduate-backups"/*.tar 2>/dev/null | wc -l | tr -d ' ')
if [ "$backup_count" -ge 1 ]; then
  pass_step "graduation backup created (bundle or tar)"
else
  fail "no backup bundle or tar in .pka/graduate-backups/"
fi
# Archival instructions printed
if echo "$out" | grep -q "https://gitea.example.com/dan/widget.git"; then
  pass_step "graduation output references previous origin"
else
  fail "graduation output does not reference previous origin"
fi
if echo "$out" | grep -qE "Gitea|GitHub|archive"; then
  pass_step "graduation output includes archival hint"
else
  fail "graduation output lacks archival hint"
fi

cleanup_workspace "$ws"

end_run
