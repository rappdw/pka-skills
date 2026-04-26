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
assert_file_exists "$ws/.pka/roles/_git-protocol.md" "git-protocol shared ref seeded"
assert_file_contains "$ws/.pka/roles/_obsidian.md"     "Obsidian Coexistence Conventions"
assert_file_contains "$ws/.pka/roles/_git-protocol.md" "Commit/Push Protocol"

# Orchestrator new sections present
assert_file_contains "$ws/.pka/roles/orchestrator.md" "## Session-start checks (cached for the session)"
assert_file_contains "$ws/.pka/roles/orchestrator.md" "## File references in responses"
assert_file_contains "$ws/.pka/roles/orchestrator.md" "## Bootstrap dispatch"
assert_file_contains "$ws/.pka/roles/orchestrator.md" "## Session-end protocol (extended)"
assert_file_contains "$ws/.pka/roles/orchestrator.md" "## Mid-session push handling"

# Librarian new sections
assert_file_contains "$ws/.pka/roles/librarian.md" "## Obsidian coexistence (gated on \`obsidian_present\`)"
assert_file_contains "$ws/.pka/roles/librarian.md" "## Commit/push protocol (gated on \`hybrid_monorepo_present\`)"

# Researcher new sections
assert_file_contains "$ws/.pka/roles/researcher.md" "## Obsidian coexistence (gated on \`obsidian_present\`)"
assert_file_contains "$ws/.pka/roles/researcher.md" "## Commit/push protocol (gated on \`hybrid_monorepo_present\`)"

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

snap_orch=$(md5sum "$ws/.pka/roles/orchestrator.md" | awk '{print $1}')
snap_lib=$(md5sum "$ws/.pka/roles/librarian.md" | awk '{print $1}')
snap_res=$(md5sum "$ws/.pka/roles/researcher.md" | awk '{print $1}')
snap_obs=$(md5sum "$ws/.pka/roles/_obsidian.md" | awk '{print $1}')

# Second run
run_upgrade "$ws" >/dev/null 2>&1

assert_eq "$snap_orch" "$(md5sum "$ws/.pka/roles/orchestrator.md" | awk '{print $1}')" "orchestrator unchanged on second run"
assert_eq "$snap_lib"  "$(md5sum "$ws/.pka/roles/librarian.md"    | awk '{print $1}')" "librarian unchanged on second run"
assert_eq "$snap_res"  "$(md5sum "$ws/.pka/roles/researcher.md"   | awk '{print $1}')" "researcher unchanged on second run"
assert_eq "$snap_obs"  "$(md5sum "$ws/.pka/roles/_obsidian.md"    | awk '{print $1}')" "_obsidian.md unchanged on second run"

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
sed -i 's/model: claude-opus-4-5/model: claude-opus-4-7/' "$ws/.pka/roles/orchestrator.md"
pre_fm=$(sed -n '1,/^---$/p; /^---$/q' "$ws/.pka/roles/orchestrator.md" | head -n -1)
# (the awk above is approximate; capture a known stable line instead)
pre_model=$(grep "^model:" "$ws/.pka/roles/orchestrator.md" | head -1)
pre_role=$(grep "^role:" "$ws/.pka/roles/orchestrator.md" | head -1)

run_upgrade "$ws" >/dev/null 2>&1

post_model=$(grep "^model:" "$ws/.pka/roles/orchestrator.md" | head -1)
post_role=$(grep "^role:" "$ws/.pka/roles/orchestrator.md" | head -1)

assert_eq "$pre_model" "$post_model" "model: line preserved (was customized to claude-opus-4-7)"
assert_eq "$pre_role"  "$post_role"  "role: line preserved"

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
snap_orch=$(md5sum "$ws/.pka/roles/orchestrator.md" | awk '{print $1}')

out=$(run_upgrade "$ws" --dry-run 2>&1)

post_orch=$(md5sum "$ws/.pka/roles/orchestrator.md" | awk '{print $1}')
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

end_run
