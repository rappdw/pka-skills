#!/usr/bin/env bash
# Shell tests for the `bootstrap upgrade` target's mechanical primitives.
# Drives bootstrap-assets/scripts/upgrade-roles.py against fixture v1.5
# workspaces and verifies the structured-merge contract.
#
# Test scenarios:
#   U1 — v1.5 workspace upgrade: shared refs seeded, new H2 sections appended
#   U2 — Idempotent: re-running on already-upgraded state produces no role changes
#   U3 — Preserves customizations: user-modified sections are byte-identical after upgrade
#   U4 — Frontmatter preserved: role frontmatter is untouched
#   U5 — Backup created on every non-dry-run invocation
#   U6 — Dry-run mode: reports changes but doesn't write files
#   U7 — Refuses on workspace without .pka/roles/: exit 1, no files created
#   U8 — Headings inside fenced code blocks are not matched or used as anchors
#   U9 — Line endings preserved (CRLF stays CRLF, LF stays LF)
#   U10 — A role file with no anchor heading is appended to, and reported
#   U11 — Runs within the same second do not collide on the backup directory

set -u
source "$(dirname "$0")/lib.sh"

UPGRADE_SCRIPT="$(cd "$(dirname "$0")/../bootstrap-assets/scripts" && pwd)/upgrade-roles.py"
if [ ! -f "$UPGRADE_SCRIPT" ]; then
  echo "${RED}MISSING:${RESET} $UPGRADE_SCRIPT" >&2
  exit 1
fi

# Build a v1.5-style workspace: .pka/roles/ with three role files, no shared
# references, no v1.6 H2 sections.
make_v15_workspace() {
  local ws
  ws=$(make_workspace)
  mkdir -p "$ws/.pka/roles"
  cat > "$ws/.pka/roles/orchestrator.md" <<'EOF'
---
role: orchestrator
model: claude-opus-4-5
status: active
tools: [file_read, file_write, bash, web_search]
---

# @orchestrator

## Purpose
Route user requests to the right role.

## Specialty
System-level coordination.

## Key Competencies
- Repo Map maintenance and folder inference
- Session start/end protocol execution

## Working Style
Concise, status-oriented.

## Output Conventions
- Session log entries: standard format
- Greetings: open threads + inbox items + lifecycle flags

## Invocation
The orchestrator is always active.
EOF

  cat > "$ws/.pka/roles/librarian.md" <<'EOF'
---
role: librarian
model: claude-opus-4-5
status: active
tools: [file_read, file_write, bash]
---

# @librarian

## Purpose
Manage document ingestion and routing.

## Specialty
Document processing and classification.

## Key Competencies
- File type detection and text extraction
- Routing inference from Repo Map

## Working Style
Methodical. Inventories before acting.

## Output Conventions
- Saves reports to: owner-inbox/
- File naming: librarian-report-<date>.md

## Invocation
Delegate to @librarian when files are dropped in team-inbox.
EOF

  cat > "$ws/.pka/roles/researcher.md" <<'EOF'
---
role: researcher
model: claude-opus-4-5
status: active
tools: [web_search, file_read, file_write]
---

# @researcher

## Purpose
Conduct research, generate competency briefs.

## Specialty
Deep, structured analysis.

## Key Competencies
- Cross-knowledge-base synthesis
- Topic research with source evaluation

## Working Style
Thorough but bounded.

## Output Conventions
- Saves briefs to: owner-inbox/
- File naming: researcher-<topic>-<date>.md

## Invocation
Delegate to @researcher for synthesis tasks.
EOF
  echo "$ws"
}

run_upgrade() {
  local ws="$1"; shift
  python3 "$UPGRADE_SCRIPT" --workspace "$ws" "$@"
}

# ----------- U1: v1.5 → v1.6 upgrade -----------
start_test "U1 — v1.5 workspace upgrade: shared refs + new H2 sections"
ws=$(make_v15_workspace)
out=$(run_upgrade "$ws" 2>&1)
echo "$out" | head -25 | sed 's/^/  > /'

# Shared references seeded
assert_file_exists "$ws/.pka/roles/_obsidian.md"     "obsidian shared ref seeded"
assert_file_contains "$ws/.pka/roles/_obsidian.md"     "Obsidian Coexistence Conventions"
# The shared reference of the removed nested-repository layout is not seeded.
if [ -e "$ws/.pka/roles/_git-protocol.md" ]; then
  fail "_git-protocol.md was seeded; it belongs to a removed feature"
else
  pass_step "_git-protocol.md is not seeded"
fi

# Orchestrator new sections present
assert_file_contains "$ws/.pka/roles/orchestrator.md" "## Session-start checks (cached for the session)"
assert_file_contains "$ws/.pka/roles/orchestrator.md" "## File references in responses"
assert_file_contains "$ws/.pka/roles/orchestrator.md" "## Bootstrap dispatch"
assert_file_lacks "$ws/.pka/roles/orchestrator.md" "## Session-end protocol (extended)"
assert_file_lacks "$ws/.pka/roles/orchestrator.md" "## Mid-session push handling"

# Librarian new sections
assert_file_contains "$ws/.pka/roles/librarian.md" "## Obsidian coexistence (gated on \`obsidian_present\`)"
assert_file_lacks "$ws/.pka/roles/librarian.md" "## Commit/push protocol"

# Researcher new sections
assert_file_contains "$ws/.pka/roles/researcher.md" "## Obsidian coexistence (gated on \`obsidian_present\`)"
assert_file_contains "$ws/.pka/roles/researcher.md" "## Filing a brief"
assert_file_lacks "$ws/.pka/roles/researcher.md" "## Commit/push protocol"

# Original orchestrator sections still present
assert_file_contains "$ws/.pka/roles/orchestrator.md" "## Purpose"
assert_file_contains "$ws/.pka/roles/orchestrator.md" "## Output Conventions"
assert_file_contains "$ws/.pka/roles/orchestrator.md" "## Invocation"

# Insertion happened BEFORE Output Conventions (anchor)
# Find line numbers; new sections must come before
boot_dispatch_line=$(grep -n "## Bootstrap dispatch" "$ws/.pka/roles/orchestrator.md" | head -1 | cut -d: -f1)
output_conv_line=$(grep -n "## Output Conventions" "$ws/.pka/roles/orchestrator.md" | head -1 | cut -d: -f1)
if [ -n "$boot_dispatch_line" ] && [ -n "$output_conv_line" ] && [ "$boot_dispatch_line" -lt "$output_conv_line" ]; then
  pass_step "new section inserted BEFORE Output Conventions anchor (line $boot_dispatch_line < $output_conv_line)"
else
  fail "new section ordering wrong (boot=$boot_dispatch_line, output=$output_conv_line)"
fi

cleanup_workspace "$ws"

# ----------- U2: idempotent -----------
start_test "U2 — Idempotent: second run produces no role changes"
ws=$(make_v15_workspace)
run_upgrade "$ws" >/dev/null 2>&1

snap_orch=$(file_hash "$ws/.pka/roles/orchestrator.md")
snap_lib=$(file_hash "$ws/.pka/roles/librarian.md")
snap_res=$(file_hash "$ws/.pka/roles/researcher.md")
snap_obs=$(file_hash "$ws/.pka/roles/_obsidian.md")

# Second run
run_upgrade "$ws" >/dev/null 2>&1

assert_eq "$snap_orch" "$(file_hash "$ws/.pka/roles/orchestrator.md")" "orchestrator unchanged on second run"
assert_eq "$snap_lib"  "$(file_hash "$ws/.pka/roles/librarian.md")" "librarian unchanged on second run"
assert_eq "$snap_res"  "$(file_hash "$ws/.pka/roles/researcher.md")" "researcher unchanged on second run"
assert_eq "$snap_obs"  "$(file_hash "$ws/.pka/roles/_obsidian.md")" "_obsidian.md unchanged on second run"

cleanup_workspace "$ws"

# ----------- U3: preserves customizations -----------
start_test "U3 — Preserves customizations: user-modified sections byte-identical"
ws=$(make_v15_workspace)
# Customize orchestrator: add a user section + tweak Output Conventions
cat >> "$ws/.pka/roles/orchestrator.md" <<'EOF'

## My Custom Notes
- I prefer terse responses
- Always show a status emoji in greetings
EOF

# Capture pre-upgrade content of "## Purpose" and "## Output Conventions"
pre_purpose=$(awk '/^## Purpose$/{flag=1; next} /^##/{flag=0} flag' "$ws/.pka/roles/orchestrator.md")
pre_output=$(awk '/^## Output Conventions$/{flag=1; next} /^##/{flag=0} flag' "$ws/.pka/roles/orchestrator.md")
pre_custom=$(awk '/^## My Custom Notes$/{flag=1; next} /^##/{flag=0} flag' "$ws/.pka/roles/orchestrator.md")

run_upgrade "$ws" >/dev/null 2>&1

post_purpose=$(awk '/^## Purpose$/{flag=1; next} /^##/{flag=0} flag' "$ws/.pka/roles/orchestrator.md")
post_output=$(awk '/^## Output Conventions$/{flag=1; next} /^##/{flag=0} flag' "$ws/.pka/roles/orchestrator.md")
post_custom=$(awk '/^## My Custom Notes$/{flag=1; next} /^##/{flag=0} flag' "$ws/.pka/roles/orchestrator.md")

assert_eq "$pre_purpose" "$post_purpose" "## Purpose body byte-identical"
assert_eq "$pre_output"  "$post_output"  "## Output Conventions body byte-identical"
assert_eq "$pre_custom"  "$post_custom"  "## My Custom Notes (user section) preserved verbatim"

# And new sections still got added
assert_file_contains "$ws/.pka/roles/orchestrator.md" "## Bootstrap dispatch"

cleanup_workspace "$ws"

# ----------- U4: frontmatter preserved -----------
start_test "U4 — Frontmatter preserved (role, model, tools fields untouched)"
ws=$(make_v15_workspace)
# Customize frontmatter
replace_in_file "$ws/.pka/roles/orchestrator.md" "model: claude-opus-4-5" "model: claude-opus-4-7"
pre_fm=$(sed -n '1,/^---$/p; /^---$/q' "$ws/.pka/roles/orchestrator.md" | head -n -1)
# (the awk above is approximate; capture a known stable line instead)
pre_model=$(grep "^model:" "$ws/.pka/roles/orchestrator.md" | head -1)
pre_role=$(grep "^role:" "$ws/.pka/roles/orchestrator.md" | head -1)

out=$(run_upgrade "$ws" 2>&1)

post_model=$(grep "^model:" "$ws/.pka/roles/orchestrator.md" | head -1)
post_role=$(grep "^role:" "$ws/.pka/roles/orchestrator.md" | head -1)

assert_eq "$pre_model" "$post_model" "model: line preserved (was customized to claude-opus-4-7)"
assert_eq "$pre_role"  "$post_role"  "role: line preserved"

# Seeds no longer pin a model; an existing pin is reported, not removed.
echo "$out" | grep -q "orchestrator.md: model: claude-opus-4-7  — left alone" \
  && pass_step "summary lists the pinned model and leaves it" || fail "pinned model not reported"
echo "$out" | grep -q "librarian.md: model: claude-opus-4-5  — left alone" \
  && pass_step "summary lists the model an earlier release seeded" || fail "seeded model not reported"
echo "$out" | grep -q "can now be removed by hand" \
  && pass_step "summary says a pinned model can be removed by hand" || fail "no removal hint"
assert_eq "3" "$(grep -c "^model:" "$ws"/.pka/roles/orchestrator.md "$ws"/.pka/roles/librarian.md "$ws"/.pka/roles/researcher.md | awk -F: '{n+=$2} END {print n}')" "all three model: lines still there"

# Without the line there is nothing to report.
for f in orchestrator librarian researcher; do
  grep -v "^model:" "$ws/.pka/roles/$f.md" > "$ws/.pka/roles/$f.md.tmp" && mv "$ws/.pka/roles/$f.md.tmp" "$ws/.pka/roles/$f.md"
done
out=$(run_upgrade "$ws" 2>&1)
echo "$out" | grep -q "Pinned models" && fail "pinned models reported when no role has a model: line" \
  || pass_step "nothing reported once the lines are gone"

cleanup_workspace "$ws"

# ----------- U5: backup created -----------
start_test "U5 — Backup created on every non-dry-run invocation"
ws=$(make_v15_workspace)
run_upgrade "$ws" >/dev/null 2>&1

backup_count=$(find "$ws/.pka/upgrade-backups" -mindepth 2 -maxdepth 2 -name roles -type d 2>/dev/null | wc -l | tr -d ' ')
if [ "$backup_count" -ge 1 ]; then
  pass_step "backup created in .pka/upgrade-backups/<ts>/roles/"
else
  fail "no backup found"
fi

# Backup has the original (pre-upgrade) content
backup_dir=$(find "$ws/.pka/upgrade-backups" -mindepth 2 -maxdepth 2 -name roles -type d | head -1)
if [ -d "$backup_dir" ]; then
  if [ -f "$backup_dir/orchestrator.md" ] && ! grep -q "## Bootstrap dispatch" "$backup_dir/orchestrator.md"; then
    pass_step "backup contains pre-upgrade orchestrator.md (no v1.6 sections)"
  else
    fail "backup orchestrator.md is wrong"
  fi
fi

cleanup_workspace "$ws"

# ----------- U6: dry-run mode -----------
start_test "U6 — --dry-run: reports changes but does not write files"
ws=$(make_v15_workspace)
snap_orch=$(file_hash "$ws/.pka/roles/orchestrator.md")

out=$(run_upgrade "$ws" --dry-run 2>&1)

post_orch=$(file_hash "$ws/.pka/roles/orchestrator.md")
assert_eq "$snap_orch" "$post_orch" "orchestrator.md unchanged in dry-run"
[ ! -f "$ws/.pka/roles/_obsidian.md" ] && pass_step "_obsidian.md NOT created in dry-run" || fail "_obsidian.md was created in dry-run mode"
[ ! -d "$ws/.pka/upgrade-backups" ] && pass_step "no backup directory in dry-run" || fail "backup created in dry-run"
echo "$out" | grep -qi "DRY RUN" && pass_step "summary indicates DRY RUN" || fail "summary missing DRY RUN marker"

cleanup_workspace "$ws"

# ----------- U7: refuses without .pka/roles/ -----------
start_test "U7 — Refuses on workspace without .pka/roles/: exit 1, no files created"
ws=$(make_workspace)
out=$(run_upgrade "$ws" 2>&1) && exit_code=0 || exit_code=$?

assert_eq "1" "$exit_code" "exit 1 when .pka/roles/ absent"
[ ! -d "$ws/.pka" ] && pass_step ".pka/ NOT created" || fail ".pka/ was created"
echo "$out" | grep -qiE "not found|bootstrap" && pass_step "error message mentions bootstrap" || fail "unhelpful error"

cleanup_workspace "$ws"

# ----------- U8: fenced code blocks are not structure -----------
start_test "U8 — Headings inside a fenced code block are ignored"
ws=$(make_v15_workspace)
# Put an example block ABOVE the real sections: it shows both an anchor
# heading and one of the headings the upgrade adds.
python3 - "$ws/.pka/roles/orchestrator.md" <<'PY'
import sys
p = sys.argv[1]
text = open(p, encoding="utf-8").read()
example = (
    "## Examples\n"
    "A role file is laid out like this:\n"
    "```markdown\n"
    "## Bootstrap dispatch\n"
    "## Output Conventions\n"
    "- example bullet\n"
    "```\n"
    "\n"
)
open(p, "w", encoding="utf-8").write(text.replace("## Purpose\n", example + "## Purpose\n", 1))
PY
run_upgrade "$ws" >/dev/null 2>&1
f="$ws/.pka/roles/orchestrator.md"
count=$(grep -c "^## Bootstrap dispatch" "$f")
assert_eq "2" "$count" "section added even though the heading appears in an example block"
fence_close=$(grep -n '^```$' "$f" | head -1 | cut -d: -f1)
real_section=$(grep -n "^## Bootstrap dispatch" "$f" | tail -1 | cut -d: -f1)
real_anchor=$(grep -n "^## Output Conventions" "$f" | tail -1 | cut -d: -f1)
if [ "$real_section" -gt "$fence_close" ] && [ "$real_section" -lt "$real_anchor" ]; then
  pass_step "new sections sit before the real anchor, not inside the code block"
else
  fail "sections misplaced (fence closes at $fence_close, section at $real_section, real anchor at $real_anchor)"
fi
block=$(sed -n '/^```markdown$/,/^```$/p' "$f" | wc -l | tr -d ' ')
assert_eq "5" "$block" "example block is byte-for-byte the same length"
cleanup_workspace "$ws"

# ----------- U9: line endings preserved -----------
start_test "U9 — CRLF role files stay CRLF"
ws=$(make_v15_workspace)
f="$ws/.pka/roles/librarian.md"
python3 - "$f" <<'PY'
import sys
p = sys.argv[1]
data = open(p, "rb").read().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
open(p, "wb").write(data)
PY
run_upgrade "$ws" >/dev/null 2>&1
bare_lf=$(python3 - "$f" <<'PY'
import sys
data = open(sys.argv[1], "rb").read()
print(data.count(b"\n") - data.count(b"\r\n"))
PY
)
assert_eq "0" "$bare_lf" "no bare LF line endings introduced"
assert_file_contains "$f" "## Obsidian coexistence" "sections were added to the CRLF file"
# LF files stay LF.
bare_cr=$(python3 - "$ws/.pka/roles/researcher.md" <<'PY'
import sys
print(open(sys.argv[1], "rb").read().count(b"\r"))
PY
)
assert_eq "0" "$bare_cr" "LF file gained no CR characters"
cleanup_workspace "$ws"

# ----------- U10: missing anchor is reported -----------
start_test "U10 — Role file without an anchor heading: appended and reported"
ws=$(make_v15_workspace)
cat > "$ws/.pka/roles/researcher.md" <<'EOF'
---
role: researcher
---

# @researcher

## Purpose
A heavily customized role file with neither anchor heading.
EOF
out=$(run_upgrade "$ws" 2>&1); rc=$?
assert_eq "0" "$rc" "upgrade still succeeds"
if echo "$out" | grep -q "WARNING" && echo "$out" | grep -q "researcher.md"; then
  pass_step "summary warns that researcher.md had no anchor"
else
  fail "no warning about the missing anchor"
fi
if echo "$out" | grep "WARNING" -A6 | grep -q "orchestrator.md"; then
  fail "warning wrongly lists a file that has an anchor"
else
  pass_step "files with an anchor are not listed in the warning"
fi
assert_file_contains "$ws/.pka/roles/researcher.md" "A heavily customized role file" "existing content kept"
cleanup_workspace "$ws"

# ----------- U11: two runs in the same second -----------
start_test "U11 — Two runs in the same second both succeed with separate backups"
ws=$(make_v15_workspace)
run_upgrade "$ws" >/dev/null 2>&1; rc1=$?
run_upgrade "$ws" >/dev/null 2>&1; rc2=$?
run_upgrade "$ws" >/dev/null 2>&1; rc3=$?
assert_eq "0 0 0" "$rc1 $rc2 $rc3" "no run crashed"
backup_count=$(find "$ws/.pka/upgrade-backups" -mindepth 2 -maxdepth 2 -name roles -type d | wc -l | tr -d ' ')
assert_eq "3" "$backup_count" "each run kept its own backup"
assert_file_contains "$ws/.pka/upgrade-backups/.gitignore" "*" "backup directory ignores itself"
cleanup_workspace "$ws"

end_run
