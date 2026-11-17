#!/usr/bin/env bash
# Regression tests for the safety fixes in the vendored helper scripts
# (v1.6.3). Each test reproduces a defect that shipped in v1.6.2 or earlier
# and asserts the fixed behaviour. IDs (A1..A11) match the findings table in
# the v1.6.3 changelog entry.
#
#   A1  graduate.sh removed the project's history even when the backup failed
#   A2  reinit accepted "" / "." and wiped the workspace root's history
#   A3  an unchecked `git init` let later commands commit into the root repo
#   A4  commit failures were ignored and reported as success
#   A5  reinit destroyed history without adding LFS; dropped remotes/branches
#   A6  .gitignore without a final newline got two patterns fused together
#   A7  the graduation backup did not contain LFS objects
#   A8  graduation swept unrelated work in knowledge/ into its commit
#   A9  a symlinked project lost its external repo's history
#   A10 a child whose .git is a file got bootstrap commits added
#   A11 .meta and the real git remotes disagreed

set -u
source "$(dirname "$0")/lib.sh"

configure_test_git_identity

TRAILER="Co-Authored-By: Claude <noreply@anthropic.com>"
REAL_GIT=$(command -v git)

run_init()     { ( cd "$1" && WORKSPACE_ROOT="$1" bash .pka/init_project_repos.sh ); }
run_meta()     { ( cd "$1" && WORKSPACE_ROOT="$1" bash .pka/build-repo-list.sh ); }
run_graduate() { local ws="$1"; shift; ( cd "$ws" && WORKSPACE_ROOT="$ws" bash .pka/graduate.sh "$@" ); }
run_reinit()   { local ws="$1"; shift; ( cd "$ws" && WORKSPACE_ROOT="$ws" bash .pka/reinit-project-with-lfs.sh "$@" ); }
run_push()     { ( cd "$1" && WORKSPACE_ROOT="$1" bash .pka/push-all.sh ); }

head_of() { git -C "$1" rev-parse HEAD 2>/dev/null || echo "none"; }

assert_exit() {
  local expected="$1" actual="$2" msg="${3:-}"
  if [ "$expected" = "$actual" ]; then
    pass_step "exit code $expected ${msg:+— $msg}"
  else
    fail "expected exit code $expected, got $actual ${msg:+— $msg}"
  fi
}

assert_nonzero() {
  local actual="$1" msg="${2:-}"
  if [ "$actual" -ne 0 ]; then
    pass_step "non-zero exit ($actual) ${msg:+— $msg}"
  else
    fail "expected a non-zero exit code ${msg:+— $msg}"
  fi
}

assert_output_contains() {
  local out="$1" needle="$2" msg="${3:-}"
  if printf '%s\n' "$out" | grep -qiF -- "$needle"; then
    pass_step "output mentions '$needle' ${msg:+— $msg}"
  else
    fail "output does not mention '$needle' ${msg:+— $msg}
$out"
  fi
}

# A workspace with knowledge/ and projects/widget initialized as child repos,
# plus an uncommitted root repo.
make_ws() {
  local ws
  ws=$(make_workspace)
  mkdir -p "$ws/knowledge" "$ws/projects/widget"
  echo "knowledge readme" > "$ws/knowledge/README.md"
  echo "widget readme"    > "$ws/projects/widget/README.md"
  install_pka_assets "$ws"
  ( cd "$ws" && git init -b main >/dev/null 2>&1 )
  run_init "$ws" >/dev/null 2>&1
  run_meta "$ws" >/dev/null 2>&1
  echo "$ws"
}

# A `git` stand-in placed first on PATH.
#   old      reports version 2.25.1 and rejects `init -b`
#   noinit   current version, but every `init` fails
#   nocommit current version, but every `commit` fails
make_git_wrapper() {
  local dir="$1" mode="$2"
  cat > "$dir/git" <<EOF
#!/usr/bin/env bash
mode="$mode"
for a in "\$@"; do
  case "\$mode:\$a" in
    old:version|old:--version) echo "git version 2.25.1"; exit 0 ;;
    old:init|noinit:init)      echo "error: unknown switch \\\`b'" >&2; exit 129 ;;
    nocommit:commit)           echo "error: simulated commit failure" >&2; exit 1 ;;
  esac
done
exec "$REAL_GIT" "\$@"
EOF
  chmod +x "$dir/git"
}

# ----------- A1 -----------
start_test "A1 — graduate.sh: trailing slash on the project name"
ws=$(make_ws)
widget_head=$(head_of "$ws/projects/widget")
out=$(run_graduate "$ws" widget/ reference 2>&1); rc=$?
assert_exit 0 "$rc" "trailing slash is accepted"
assert_dir_exists "$ws/knowledge/reference/widget" "project moved"
backup=$(ls -1d "$ws/.pka/graduate-backups"/widget-*.git 2>/dev/null | head -1)
if [ -n "$backup" ] && [ "$(git --git-dir="$backup" rev-parse HEAD 2>/dev/null)" = "$widget_head" ]; then
  pass_step "previous repository kept, HEAD intact"
else
  fail "previous repository missing or damaged (backup='$backup')"
fi
clone_dir=$(make_scratch_dir); register_cleanup "$clone_dir"
if git clone -q "$backup" "$clone_dir/restored" 2>/dev/null && [ -f "$clone_dir/restored/README.md" ]; then
  pass_step "history can be restored with git clone"
else
  fail "git clone of the kept repository failed"
fi
cleanup_workspace "$ws"

start_test "A1 — graduate.sh: backup cannot be written, nothing is lost"
ws=$(make_ws)
widget_head=$(head_of "$ws/projects/widget")
# A file where the backup directory should be: the backup cannot be made.
echo "in the way" > "$ws/.pka/graduate-backups"
out=$(run_graduate "$ws" widget reference 2>&1); rc=$?
assert_nonzero "$rc" "graduation refused"
assert_dir_exists "$ws/projects/widget/.git" "project .git still in place"
assert_eq "$widget_head" "$(head_of "$ws/projects/widget")" "project history intact"
assert_dir_absent "$ws/knowledge/reference/widget" "project not moved"
cleanup_workspace "$ws"

start_test "A1 — graduate.sh: path-like and empty names are usage errors"
ws=$(make_ws)
for bad in "" "." ".." "../knowledge" "a/b" "-x"; do
  out=$(run_graduate "$ws" "$bad" 2>&1); rc=$?
  assert_exit 64 "$rc" "name '$bad' rejected"
done
out=$(run_graduate "$ws" widget "../outside" 2>&1); rc=$?
assert_exit 64 "$rc" "subdir '../outside' rejected"
out=$(run_graduate "$ws" widget "/abs" 2>&1); rc=$?
assert_exit 64 "$rc" "absolute subdir rejected"
assert_dir_exists "$ws/projects/widget/.git" "project untouched"
cleanup_workspace "$ws"

# ----------- A2 -----------
start_test "A2 — reinit: empty, '.', and paths outside the child repos are rejected"
ws=$(make_ws)
( cd "$ws" && git add -A >/dev/null 2>&1 && git commit -q -m "root commit" )
root_head=$(head_of "$ws")
for bad in "" "." ".." "/" "projects" "projects/" "projects/.." "projects/../knowledge" "owner-inbox" "$ws/projects/widget"; do
  out=$(run_reinit "$ws" --yes "$bad" 2>&1); rc=$?
  assert_exit 64 "$rc" "path '$bad' rejected"
done
assert_eq "$root_head" "$(head_of "$ws")" "root history untouched"
assert_commit_count "$ws" 1 "root has no extra commits"
assert_dir_absent "$ws/.pka/reinit-backups" "no backup taken, nothing moved"
cleanup_workspace "$ws"

# ----------- A3 -----------
start_test "A3 — init: git older than 2.28 stops before touching anything"
ws=$(make_workspace)
mkdir -p "$ws/knowledge" "$ws/projects/foo"
echo "k" > "$ws/knowledge/README.md"
echo "f" > "$ws/projects/foo/README.md"
install_pka_assets "$ws"
( cd "$ws" && git init -b main >/dev/null 2>&1 )
wrap=$(make_scratch_dir); register_cleanup "$wrap"
make_git_wrapper "$wrap" old
out=$(PATH="$wrap:$PATH" run_init "$ws" 2>&1); rc=$?
assert_exit 2 "$rc" "old git is a hard stop"
assert_output_contains "$out" "2.28"
assert_dir_absent "$ws/knowledge/.git" "knowledge not initialized"
assert_dir_absent "$ws/projects/foo/.git" "projects/foo not initialized"
assert_no_commit "$ws" "nothing committed into the root repo"
assert_eq "" "$(git -C "$ws" diff --cached --name-only)" "nothing staged in the root repo"
out=$(PATH="$wrap:$PATH" run_reinit "$ws" --yes knowledge 2>&1); rc=$?
assert_exit 2 "$rc" "reinit also refuses old git"
cleanup_workspace "$ws"

start_test "A3 — init: a failed 'git init' never commits into the root repo"
ws=$(make_workspace)
mkdir -p "$ws/knowledge" "$ws/projects/foo"
echo "k" > "$ws/knowledge/README.md"
echo "f" > "$ws/projects/foo/README.md"
install_pka_assets "$ws"
( cd "$ws" && git init -b main >/dev/null 2>&1 )
wrap=$(make_scratch_dir); register_cleanup "$wrap"
make_git_wrapper "$wrap" noinit
out=$(PATH="$wrap:$PATH" run_init "$ws" 2>&1); rc=$?
assert_exit 1 "$rc" "failure is reported in the exit code"
assert_output_contains "$out" "Failed"
assert_no_commit "$ws" "nothing committed into the root repo"
assert_eq "" "$(git -C "$ws" diff --cached --name-only)" "nothing staged in the root repo"
assert_dir_absent "$ws/knowledge/.git" "no half-made repo left behind"
cleanup_workspace "$ws"

# ----------- A4 -----------
start_test "A4 — init: a failed commit is reported and the next run retries"
ws=$(make_workspace)
mkdir -p "$ws/knowledge"
echo "k" > "$ws/knowledge/README.md"
install_pka_assets "$ws"
wrap=$(make_scratch_dir); register_cleanup "$wrap"
make_git_wrapper "$wrap" nocommit
out=$(PATH="$wrap:$PATH" run_init "$ws" 2>&1); rc=$?
assert_exit 1 "$rc" "commit failure is not reported as success"
assert_output_contains "$out" "Failed"
assert_dir_absent "$ws/knowledge/.git" "half-made repo removed"
out=$(run_init "$ws" 2>&1); rc=$?
assert_exit 0 "$rc" "second run succeeds"
assert_commit_count "$ws/knowledge" 2 "second run really initialized the repo"
cleanup_workspace "$ws"

start_test "A4 — init: no git identity is caught before anything is created"
ws=$(make_workspace)
mkdir -p "$ws/knowledge"
echo "k" > "$ws/knowledge/README.md"
install_pka_assets "$ws"
noid_home=$(make_scratch_dir); register_cleanup "$noid_home"
printf '[user]\n\tuseConfigOnly = true\n' > "$noid_home/.gitconfig"
out=$(HOME="$noid_home" GIT_CONFIG_GLOBAL="$noid_home/.gitconfig" run_init "$ws" 2>&1); rc=$?
assert_exit 1 "$rc" "missing identity stops the run"
assert_output_contains "$out" "identity"
assert_dir_absent "$ws/knowledge/.git" "nothing initialized"
cleanup_workspace "$ws"

start_test "A4 — graduate.sh: a failed commit rolls everything back"
ws=$(make_ws)
mkdir -p "$ws/knowledge/AI"
printf '# AI\n\n## Pointers\n\n| Topic | Entities | Files |\n| --- | --- | --- |\n| widget-design | Priya | [[projects/widget/README]] |\n' > "$ws/knowledge/AI/_MOC.md"
( cd "$ws/knowledge" && git add -A && git commit -q -m "Librarian: add MOC" -m "$TRAILER" )
knowledge_head=$(head_of "$ws/knowledge")
widget_head=$(head_of "$ws/projects/widget")
moc_before=$(cksum < "$ws/knowledge/AI/_MOC.md")
mkdir -p "$ws/knowledge/.git/hooks"
printf '#!/bin/sh\necho "hook says no" >&2\nexit 1\n' > "$ws/knowledge/.git/hooks/pre-commit"
chmod +x "$ws/knowledge/.git/hooks/pre-commit"
out=$(run_graduate "$ws" widget reference 2>&1); rc=$?
assert_exit 1 "$rc" "failed commit is not reported as success"
assert_dir_exists "$ws/projects/widget/.git" "project repo restored"
assert_eq "$widget_head" "$(head_of "$ws/projects/widget")" "project history intact"
assert_file_exists "$ws/projects/widget/README.md" "project content back in place"
assert_dir_absent "$ws/knowledge/reference" "destination removed again"
assert_eq "$knowledge_head" "$(head_of "$ws/knowledge")" "knowledge HEAD unchanged"
assert_clean_worktree "$ws/knowledge" "knowledge left clean"
assert_eq "$moc_before" "$(cksum < "$ws/knowledge/AI/_MOC.md")" "MOC restored byte for byte"
assert_eq "" "$(meta_origin_of "$ws/.meta" "projects/widget")" ".meta still lists the project"
# With the hook gone the same graduation goes through.
rm -f "$ws/knowledge/.git/hooks/pre-commit"
out=$(run_graduate "$ws" widget reference 2>&1); rc=$?
assert_exit 0 "$rc" "graduation succeeds once the cause is fixed"
assert_file_contains "$ws/knowledge/AI/_MOC.md" "[[reference/widget/README]]" "pointer link rewritten"
cleanup_workspace "$ws"

start_test "A4 — reinit: a failed commit puts the old repository back"
ws=$(make_ws)
legacy="$ws/projects/legacy"
mkdir -p "$legacy"
echo "legacy" > "$legacy/README.md"
( cd "$legacy" && git init -b main >/dev/null 2>&1 && git add -A && git commit -q -m "legacy initial" )
legacy_head=$(head_of "$legacy")
wrap=$(make_scratch_dir); register_cleanup "$wrap"
make_git_wrapper "$wrap" nocommit
out=$(PATH="$wrap:$PATH" run_reinit "$ws" --yes projects/legacy 2>&1); rc=$?
assert_exit 1 "$rc" "failed reinit is not reported as success"
assert_eq "$legacy_head" "$(head_of "$legacy")" "old history back in place"
assert_dir_absent "$legacy/.gitattributes" ".gitattributes removed again"
assert_dir_absent "$legacy/.gitignore" ".gitignore removed again"
assert_clean_worktree "$legacy" "working tree as before"
cleanup_workspace "$ws"

# ----------- A5 -----------
start_test "A5 — reinit: existing .gitattributes gains LFS; remotes and old branches survive"
ws=$(make_ws)
legacy="$ws/projects/legacy"
mkdir -p "$legacy"
echo "legacy" > "$legacy/README.md"
printf '%%PDF-1.4 fake pdf body\n' > "$legacy/report.pdf"
printf '*.txt text\n' > "$legacy/.gitattributes"
(
  cd "$legacy" && git init -b main >/dev/null 2>&1 && git add -A && git commit -q -m "legacy initial" \
    && git branch feature \
    && git remote add origin "https://git.example.com/dan/legacy.git" \
    && git remote add upstream "https://git.example.com/team/legacy.git" \
    && git remote set-url --push upstream "https://git.example.com/team/legacy-push.git"
)
legacy_head=$(head_of "$legacy")
out=$(run_reinit "$ws" --yes projects/legacy 2>&1); rc=$?
assert_exit 0 "$rc"
assert_file_contains "$legacy/.gitattributes" "*.txt text" "user's attribute line kept"
assert_file_contains "$legacy/.gitattributes" "*.pdf filter=lfs" "LFS filters merged in"
lfs_files=$(git -C "$legacy" lfs ls-files | wc -l | tr -d ' ')
assert_eq "1" "$lfs_files" "the PDF is now LFS-tracked"
assert_commit_count "$legacy" 2 "fresh two-commit history"
assert_eq "https://git.example.com/dan/legacy.git"  "$(git -C "$legacy" remote get-url origin)"   "origin preserved"
assert_eq "https://git.example.com/team/legacy.git" "$(git -C "$legacy" remote get-url upstream)" "second remote preserved"
assert_eq "https://git.example.com/team/legacy-push.git" "$(git -C "$legacy" remote get-url --push upstream)" "push URL preserved"
backup=$(ls -1d "$ws/.pka/reinit-backups"/projects-legacy-*.git 2>/dev/null | head -1)
if [ -n "$backup" ] && [ "$(git --git-dir="$backup" rev-parse feature 2>/dev/null)" = "$legacy_head" ]; then
  pass_step "old repository kept with its other branch"
else
  fail "old repository or its 'feature' branch is missing (backup='$backup')"
fi
assert_file_contains "$ws/.pka/reinit-backups/.gitignore" "*" "backup directory ignores itself"
cleanup_workspace "$ws"

start_test "A5 — reinit: typed confirmation is still required without --yes"
ws=$(make_ws)
knowledge_head=$(head_of "$ws/knowledge")
out=$(printf 'nope\n' | run_reinit "$ws" knowledge 2>&1); rc=$?
assert_exit 1 "$rc" "wrong confirmation aborts"
assert_eq "$knowledge_head" "$(head_of "$ws/knowledge")" "history untouched"
out=$(run_reinit "$ws" knowledge </dev/null 2>&1); rc=$?
assert_exit 1 "$rc" "no input aborts"
assert_eq "$knowledge_head" "$(head_of "$ws/knowledge")" "history untouched"
cleanup_workspace "$ws"

# ----------- A6 -----------
start_test "A6 — .gitignore without a final newline is not corrupted"
ws=$(make_workspace)
mkdir -p "$ws/projects/app/node_modules/dep"
echo "app" > "$ws/projects/app/README.md"
echo "dependency" > "$ws/projects/app/node_modules/dep/index.js"
printf 'node_modules' > "$ws/projects/app/.gitignore"     # no trailing newline
install_pka_assets "$ws"
out=$(run_init "$ws" 2>&1); rc=$?
assert_exit 0 "$rc"
if grep -qxF "node_modules" "$ws/projects/app/.gitignore"; then
  pass_step "user's pattern is still on its own line"
else
  fail "user's pattern was fused with another line: $(head -2 "$ws/projects/app/.gitignore" | tr '\n' '|')"
fi
tracked=$(git -C "$ws/projects/app" ls-files | grep -c '^node_modules/' || true)
assert_eq "0" "$tracked" "node_modules/ was not committed"
# Same merge in the reinit script.
legacy="$ws/projects/legacy"
mkdir -p "$legacy/node_modules"
echo "x" > "$legacy/README.md"
echo "y" > "$legacy/node_modules/y.js"
printf 'node_modules' > "$legacy/.gitignore"
( cd "$legacy" && git init -b main >/dev/null 2>&1 && git add README.md .gitignore && git commit -q -m "legacy initial" )
out=$(run_reinit "$ws" --yes projects/legacy 2>&1); rc=$?
assert_exit 0 "$rc"
tracked=$(git -C "$legacy" ls-files | grep -c '^node_modules/' || true)
assert_eq "0" "$tracked" "reinit did not commit node_modules/ either"
cleanup_workspace "$ws"

# ----------- A7 -----------
start_test "A7 — graduate.sh: the kept repository includes LFS objects"
ws=$(make_ws)
widget="$ws/projects/widget"
printf '%%PDF-1.4 version one\n' > "$widget/spec.pdf"
( cd "$widget" && git add -A && git commit -q -m "spec v1" )
printf '%%PDF-1.4 version two, longer\n' > "$widget/spec.pdf"
( cd "$widget" && git add -A && git commit -q -m "spec v2" )
lfs_before=$(find "$widget/.git/lfs/objects" -type f 2>/dev/null | wc -l | tr -d ' ')
assert_eq "2" "$lfs_before" "fixture has two LFS objects (old and new version)"
out=$(run_graduate "$ws" widget reference 2>&1); rc=$?
assert_exit 0 "$rc"
backup=$(ls -1d "$ws/.pka/graduate-backups"/widget-*.git 2>/dev/null | head -1)
lfs_after=$(find "$backup/lfs/objects" -type f 2>/dev/null | wc -l | tr -d ' ')
assert_eq "2" "$lfs_after" "both LFS objects are in the kept repository"
assert_eq "%PDF-1.4 version two, longer" "$(cat "$ws/knowledge/reference/widget/spec.pdf")" "current file content moved, not a pointer stub"
assert_eq "1" "$(git -C "$ws/knowledge" lfs ls-files | wc -l | tr -d ' ')" "file is LFS-tracked in knowledge/"
cleanup_workspace "$ws"

# ----------- A8 -----------
start_test "A8 — graduate.sh: unrelated work in knowledge/ stays out of the commit"
ws=$(make_ws)
k="$ws/knowledge"
echo "draft one" > "$k/notes.md"
echo "second"    > "$k/staged.md"
( cd "$k" && git add -A && git commit -q -m "Librarian: notes" -m "$TRAILER" )
echo "half-finished edit" >> "$k/notes.md"          # modified, not staged
echo "staged edit"        >> "$k/staged.md"
( cd "$k" && git add staged.md )                    # staged by the user
echo "scratch" > "$k/untracked.md"                  # untracked
out=$(run_graduate "$ws" widget reference 2>&1); rc=$?
assert_exit 0 "$rc"
committed=$(git -C "$k" show --name-only --format= HEAD | grep -v '^$')
other=$(printf '%s\n' "$committed" | grep -v '^reference/widget/' || true)
assert_eq "" "$other" "commit contains only the graduated project"
assert_eq " M notes.md" "$(git -C "$k" status --porcelain -- notes.md)" "unstaged edit still unstaged"
assert_eq "M  staged.md" "$(git -C "$k" status --porcelain -- staged.md)" "user's staged edit still staged, not committed"
assert_eq "?? untracked.md" "$(git -C "$k" status --porcelain -- untracked.md)" "untracked file still untracked"
cleanup_workspace "$ws"

# ----------- A9 -----------
start_test "A9 — symlinked project: external repo is never touched"
ws=$(make_ws)
ext=$(make_scratch_dir); register_cleanup "$ext"
mkdir "$ext/outside"
echo "external" > "$ext/outside/README.md"
( cd "$ext/outside" && git init -b main >/dev/null 2>&1 && git add -A && git commit -q -m "external initial" )
ext_head=$(head_of "$ext/outside")
ln -s "$ext/outside" "$ws/projects/linked"
out=$(run_graduate "$ws" linked reference 2>&1); rc=$?
assert_exit 1 "$rc" "graduating a symlink is refused"
assert_output_contains "$out" "symbolic link"
assert_eq "$ext_head" "$(head_of "$ext/outside")" "external history intact"
if [ -L "$ws/projects/linked" ]; then pass_step "symlink left in place"; else fail "symlink was moved or removed"; fi
out=$(run_reinit "$ws" --yes projects/linked 2>&1); rc=$?
assert_exit 1 "$rc" "reinit of a symlink is refused"
assert_eq "$ext_head" "$(head_of "$ext/outside")" "external history intact after reinit attempt"
out=$(run_init "$ws" 2>&1); rc=$?
assert_exit 0 "$rc"
assert_output_contains "$out" "projects/linked: symbolic link"
assert_eq "$ext_head" "$(head_of "$ext/outside")" "external history intact after init"
assert_dir_absent "$ext/outside/.gitattributes" "no templates written through the link"
cleanup_workspace "$ws"

# ----------- A10 -----------
start_test "A10 — child whose .git is a file (linked worktree) is left alone"
ws=$(make_ws)
ext=$(make_scratch_dir); register_cleanup "$ext"
mkdir "$ext/main-repo"
echo "main" > "$ext/main-repo/README.md"
( cd "$ext/main-repo" && git init -b main >/dev/null 2>&1 && git add -A && git commit -q -m "main initial" \
    && git worktree add -q "$ws/projects/wt" -b wt-branch >/dev/null 2>&1 )
if [ -f "$ws/projects/wt/.git" ]; then pass_step "fixture: projects/wt/.git is a file"; else fail "fixture: worktree not created"; fi
wt_count=$(git -C "$ws/projects/wt" rev-list --count HEAD)
out=$(run_init "$ws" 2>&1); rc=$?
assert_exit 0 "$rc"
assert_output_contains "$out" "projects/wt: .git is a file"
assert_eq "$wt_count" "$(git -C "$ws/projects/wt" rev-list --count HEAD)" "no commits added to the worktree's history"
assert_dir_absent "$ws/projects/wt/.gitattributes" "no templates written"
out=$(run_reinit "$ws" --yes projects/wt 2>&1); rc=$?
assert_exit 1 "$rc" "reinit refused"
out=$(run_graduate "$ws" wt reference 2>&1); rc=$?
assert_exit 1 "$rc" "graduate refused"
assert_file_exists "$ws/projects/wt/.git" "worktree link intact"
cleanup_workspace "$ws"

# ----------- A11 -----------
start_test "A11 — push-all.sh: pushes by the repo's real remote, not the copy in .meta"
ws=$(make_ws)
remotes=$(make_scratch_dir); register_cleanup "$remotes"
mkdir "$remotes/widget.git"
( cd "$remotes/widget.git" && git init --bare -b main >/dev/null 2>&1 )
# Remote set on the repo; .meta NOT refreshed (still records an empty URL).
git -C "$ws/projects/widget" remote add origin "$remotes/widget.git"
assert_eq "" "$(meta_origin_of "$ws/.meta" "projects/widget")" "fixture: .meta is stale"
out=$(run_push "$ws" 2>&1); rc=$?
assert_exit 0 "$rc"
pushed=$(git --git-dir="$remotes/widget.git" rev-list --count main 2>/dev/null || echo 0)
assert_eq "2" "$pushed" "repo with a real remote was pushed despite the stale .meta"
assert_output_contains "$out" "build-repo-list.sh" "stale .meta is pointed out"
cleanup_workspace "$ws"

start_test "A11 — push-all.sh: a URL typed into .meta is a skip with a hint, not a failure"
ws=$(make_ws)
python3 - "$ws/.meta" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
d["projects"]["knowledge"] = "https://git.example.com/dan/knowledge.git"
json.dump(d, open(p, "w"), indent=2)
PY
out=$(run_push "$ws" 2>&1); rc=$?
assert_exit 0 "$rc" "no failed push"
assert_output_contains "$out" "git -C knowledge remote add origin https://git.example.com/dan/knowledge.git" "tells the user the command that works"
cleanup_workspace "$ws"

start_test "A11 — build-repo-list.sh: keeps other keys, refuses to overwrite invalid JSON"
ws=$(make_ws)
python3 - "$ws/.meta" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
d["ignore"] = [".DS_Store"]
d["projects"]["projects/gone"] = "https://git.example.com/dan/gone.git"
json.dump(d, open(p, "w"), indent=2)
PY
git -C "$ws/knowledge" remote add origin "https://git.example.com/dan/knowledge.git"
out=$(run_meta "$ws" 2>&1); rc=$?
assert_exit 0 "$rc"
assert_file_contains "$ws/.meta" '".DS_Store"' "unrelated top-level key preserved"
assert_eq "https://git.example.com/dan/knowledge.git" "$(meta_origin_of "$ws/.meta" "knowledge")" "origin read from the repo"
assert_eq "<MISSING>" "$(meta_origin_of "$ws/.meta" "projects/gone")" "entry for a repo that no longer exists removed"
first=$(cat "$ws/.meta"); run_meta "$ws" >/dev/null 2>&1
assert_eq "$first" "$(cat "$ws/.meta")" "second run produces an identical file"
printf '{ "projects": { broken' > "$ws/.meta"
out=$(run_meta "$ws" 2>&1); rc=$?
assert_exit 1 "$rc" "invalid JSON is an error"
assert_eq '{ "projects": { broken' "$(cat "$ws/.meta")" "invalid file left untouched"
cleanup_workspace "$ws"

# ----------- shared temp path -----------
start_test "Scripts leave nothing behind in the shared temp directory"
ws=$(make_ws)
leftovers=$(ls -1d "${TMPDIR:-/tmp}"/pka-empty-git-template "${TMPDIR:-/tmp}"/pka-init.* "${TMPDIR:-/tmp}"/pka-graduate.* "${TMPDIR:-/tmp}"/pka-reinit.* "${TMPDIR:-/tmp}"/pka-meta.* 2>/dev/null || true)
assert_eq "" "$leftovers" "no fixed-name or leftover temp paths"
cleanup_workspace "$ws"

end_run
