#!/usr/bin/env bash
# Shell tests for the Obsidian mechanical retrofit's PRIMITIVES.
#
# The full Obsidian bootstrap is executed by the pka-bootstrap skill (i.e.,
# Claude follows the algorithm in references/obsidian-bootstrap.md). These
# shell tests verify the deterministic primitives that algorithm uses:
#
#   - frontmatter merge (existing fields preserved, missing fields added)
#   - malformed-YAML detection (skip + flag, never repair)
#   - filename-pattern matching (1on1, meeting, daily)
#   - de-slugification of person folder names
#
# Maps to spec scenarios S3 (cold mechanical retrofit), S4 (idempotent),
# S5 (partial pre-existing), S6 (malformed frontmatter).
#
# We provide a small Python helper `bootstrap_obsidian.py` co-located here
# that implements the algorithm reference verbatim, so the harness can drive it.

set -u
source "$(dirname "$0")/lib.sh"

HELPER="$(dirname "$0")/bootstrap_obsidian.py"
if [ ! -f "$HELPER" ]; then
  echo "${RED}MISSING:${RESET} $HELPER (the algorithm reference must have a runnable companion for testing)" >&2
  exit 1
fi

run_obsidian_bootstrap() {
  local ws="$1"
  python3 "$HELPER" --workspace "$ws"
}

# ----------- S3: cold vault mechanical retrofit -----------
start_test "S3 — Obsidian bootstrap, cold vault"
ws=$(make_workspace)
mkdir -p "$ws/knowledge/.obsidian"
mkdir -p "$ws/knowledge/AI/azure"
mkdir -p "$ws/knowledge/personnel/alec-smith"
mkdir -p "$ws/knowledge/personnel/jane"
mkdir -p "$ws/knowledge/leadership"
mkdir -p "$ws/knowledge/lab-notebook"

echo "ai content" > "$ws/knowledge/AI/foo.md"
echo "azure content" > "$ws/knowledge/AI/azure/notes.md"
echo "alec note" > "$ws/knowledge/personnel/alec-smith/2026-04-22-1on1.md"
echo "jane note" > "$ws/knowledge/personnel/jane/2026-04-21-1-1.md"
echo "slt meeting" > "$ws/knowledge/leadership/2026-04-22-slt-meeting.md"
echo "daily" > "$ws/knowledge/lab-notebook/2026-04-22.md"

out=$(run_obsidian_bootstrap "$ws" 2>&1)
echo "$out" | head -25 | sed 's/^/  > /'

assert_file_exists "$ws/knowledge/_MOC.md"                       "vault root MOC"
assert_file_exists "$ws/knowledge/AI/_MOC.md"                    "AI MOC stub"
assert_file_exists "$ws/knowledge/AI/azure/_MOC.md"              "AI/azure MOC stub (sub-domain)"
assert_file_exists "$ws/knowledge/personnel/_MOC.md"             "personnel MOC stub"
assert_file_exists "$ws/knowledge/leadership/_MOC.md"            "leadership MOC stub"
assert_file_exists "$ws/knowledge/lab-notebook/_MOC.md"          "lab-notebook MOC stub"
assert_file_exists "$ws/knowledge/personnel/alec-smith/index.md" "person index for alec-smith"
assert_file_exists "$ws/knowledge/personnel/jane/index.md"       "person index for jane"

# Person index has de-slugified name
assert_file_contains "$ws/knowledge/personnel/alec-smith/index.md" "name: Alec Smith"
assert_file_contains "$ws/knowledge/personnel/jane/index.md"       "name: Jane"

# Filename-pattern frontmatter
assert_file_contains "$ws/knowledge/personnel/alec-smith/2026-04-22-1on1.md" "type: 1on1"
assert_file_contains "$ws/knowledge/personnel/alec-smith/2026-04-22-1on1.md" "date: 2026-04-22"
assert_file_contains "$ws/knowledge/personnel/alec-smith/2026-04-22-1on1.md" "person:"
assert_file_contains "$ws/knowledge/personnel/jane/2026-04-21-1-1.md"        "type: 1on1"
assert_file_contains "$ws/knowledge/leadership/2026-04-22-slt-meeting.md"     "type: meeting"
assert_file_contains "$ws/knowledge/leadership/2026-04-22-slt-meeting.md"     "topic: slt-meeting"
assert_file_contains "$ws/knowledge/leadership/2026-04-22-slt-meeting.md"     "tags: [meeting, leadership]"
assert_file_contains "$ws/knowledge/lab-notebook/2026-04-22.md"               "daily" "tags include 'daily' (domain tag merged is fine)"
assert_file_contains "$ws/knowledge/lab-notebook/2026-04-22.md"               "date: 2026-04-22"

# Domain tag merged on a generic file with no pattern match
assert_file_contains "$ws/knowledge/AI/foo.md" "tags: [ai]" "ai domain tag added to foo.md"

cleanup_workspace "$ws"

# ----------- S4: idempotent -----------
start_test "S4 — Obsidian bootstrap, idempotent"
ws=$(make_workspace)
mkdir -p "$ws/knowledge/.obsidian/" "$ws/knowledge/AI" "$ws/knowledge/personnel/alec"
echo "ai" > "$ws/knowledge/AI/foo.md"
echo "alec" > "$ws/knowledge/personnel/alec/2026-04-22-1on1.md"

run_obsidian_bootstrap "$ws" >/dev/null 2>&1

# Snapshot every file
snap1=$(find "$ws/knowledge" -type f -exec md5sum {} + | sort)

# Re-run
run_obsidian_bootstrap "$ws" >/dev/null 2>&1
snap2=$(find "$ws/knowledge" -type f -exec md5sum {} + | sort)

if [ "$snap1" = "$snap2" ]; then
  pass_step "vault state unchanged after second bootstrap run"
else
  fail "second bootstrap run produced changes — not idempotent"
  diff <(echo "$snap1") <(echo "$snap2") | head -10 >&2
fi

cleanup_workspace "$ws"

# ----------- S5: partial pre-existing -----------
start_test "S5 — Obsidian bootstrap, partial pre-existing"
ws=$(make_workspace)
mkdir -p "$ws/knowledge/.obsidian/" "$ws/knowledge/AI" "$ws/knowledge/personnel/alec" "$ws/knowledge/personnel/jane"
echo "ai" > "$ws/knowledge/AI/foo.md"
echo "alec" > "$ws/knowledge/personnel/alec/note.md"
echo "jane" > "$ws/knowledge/personnel/jane/note.md"

# Pre-author MOC and one person index
cat > "$ws/knowledge/AI/_MOC.md" <<'EOF'
# AI

## My thematic group
- [[AI/foo]]
EOF
preauth_moc=$(md5sum "$ws/knowledge/AI/_MOC.md" | awk '{print $1}')

cat > "$ws/knowledge/personnel/alec/index.md" <<'EOF'
---
type: person
name: Alec Cuthbertson
role: Director
org: Acme
tags: [person]
---

# Alec Cuthbertson

## Notes
- something the user wrote
EOF
preauth_alec=$(md5sum "$ws/knowledge/personnel/alec/index.md" | awk '{print $1}')

run_obsidian_bootstrap "$ws" >/dev/null 2>&1

post_moc=$(md5sum "$ws/knowledge/AI/_MOC.md" | awk '{print $1}')
post_alec=$(md5sum "$ws/knowledge/personnel/alec/index.md" | awk '{print $1}')

assert_eq "$preauth_moc"  "$post_moc"  "pre-existing AI MOC unchanged"
assert_eq "$preauth_alec" "$post_alec" "pre-existing alec/index.md unchanged"
assert_file_exists "$ws/knowledge/personnel/jane/index.md" "missing person index created"

cleanup_workspace "$ws"

# ----------- S6: malformed frontmatter -----------
start_test "S6 — Obsidian bootstrap, malformed frontmatter"
ws=$(make_workspace)
mkdir -p "$ws/knowledge/.obsidian/" "$ws/knowledge/AI"
# Malformed YAML: unquoted colon in topic
cat > "$ws/knowledge/AI/broken.md" <<'EOF'
---
type: brief
topic: this: has an unquoted colon
tags: [research, ai]
---

body content
EOF
broken_md5=$(md5sum "$ws/knowledge/AI/broken.md" | awk '{print $1}')

# Non-malformed file in same domain
echo "good" > "$ws/knowledge/AI/good.md"

out=$(run_obsidian_bootstrap "$ws" 2>&1)

# Malformed file unchanged
post_broken_md5=$(md5sum "$ws/knowledge/AI/broken.md" | awk '{print $1}')
assert_eq "$broken_md5" "$post_broken_md5" "malformed file unchanged"

# Mentioned in summary
if echo "$out" | grep -qiE "skip|malformed"; then
  pass_step "summary mentions skipped/malformed file"
else
  fail "summary lacks malformed-frontmatter notice"
  echo "$out" | head -20 >&2
fi
if echo "$out" | grep -q "broken.md"; then
  pass_step "summary lists broken.md by path"
else
  fail "summary does not list broken.md"
fi

# Other files still processed
assert_file_contains "$ws/knowledge/AI/good.md" "tags:" "non-malformed file got domain tag"

cleanup_workspace "$ws"

end_run
