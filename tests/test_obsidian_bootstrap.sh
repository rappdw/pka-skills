#!/usr/bin/env bash
# Obsidian mechanical retrofit scenarios (S3–S6), run against the shipped tool.
#
# Until v1.7 this suite drove tests/bootstrap_obsidian.py, a reference
# implementation that never shipped. It now runs
# `.pka/bin/pka-tools obsidian bootstrap`, which is what the pka-bootstrap
# skill runs. Deeper coverage (CRLF, byte-order marks, block-list tags,
# byte-for-byte bodies) is in tests/tools/test_obsidian.py.
#
#   S3 — cold vault        S4 — idempotent
#   S5 — partial pre-existing content is left alone
#   S6 — malformed frontmatter is skipped and listed

set -u
source "$(dirname "$0")/lib.sh"
configure_test_git_identity

new_vault() {
  local ws
  ws=$(make_workspace)
  mkdir -p "$ws/.pka" "$ws/knowledge/.obsidian"
  install_pka_tools "$ws"
  echo "$ws"
}

# ----------- S3 -----------
start_test "S3 — Obsidian bootstrap, cold vault"
ws=$(new_vault)
mkdir -p "$ws/knowledge/AI/azure" "$ws/knowledge/personnel/robin-smith" "$ws/knowledge/personnel/jane" \
         "$ws/knowledge/leadership" "$ws/knowledge/lab-notebook"
echo "ai content" > "$ws/knowledge/AI/foo.md"
echo "azure content" > "$ws/knowledge/AI/azure/notes.md"
echo "robin note" > "$ws/knowledge/personnel/robin-smith/2026-04-22-1on1.md"
echo "jane note" > "$ws/knowledge/personnel/jane/2026-04-21-1-1.md"
echo "slt meeting" > "$ws/knowledge/leadership/2026-04-22-slt-meeting.md"
echo "daily" > "$ws/knowledge/lab-notebook/2026-04-22.md"

out=$(pka_tools "$ws" obsidian bootstrap 2>&1)
echo "$out" | head -25 | sed 's/^/  > /'

assert_file_exists "$ws/knowledge/_MOC.md"                       "vault root MOC"
assert_file_exists "$ws/knowledge/AI/_MOC.md"                    "AI MOC stub"
assert_file_exists "$ws/knowledge/AI/azure/_MOC.md"              "AI/azure MOC stub (sub-domain)"
assert_file_exists "$ws/knowledge/personnel/_MOC.md"             "personnel MOC stub"
assert_file_exists "$ws/knowledge/leadership/_MOC.md"            "leadership MOC stub"
assert_file_exists "$ws/knowledge/lab-notebook/_MOC.md"          "lab-notebook MOC stub"
assert_file_exists "$ws/knowledge/personnel/robin-smith/index.md" "person index for robin-smith"
assert_file_exists "$ws/knowledge/personnel/jane/index.md"       "person index for jane"
assert_dir_absent  "$ws/knowledge/personnel/jane/_MOC.md"        "person folders get an index, not a MOC"

assert_file_contains "$ws/knowledge/personnel/robin-smith/index.md" "name: Robin Smith"
assert_file_contains "$ws/knowledge/personnel/jane/index.md"       "name: Jane"

assert_file_contains "$ws/knowledge/personnel/robin-smith/2026-04-22-1on1.md" "type: 1on1"
assert_file_contains "$ws/knowledge/personnel/robin-smith/2026-04-22-1on1.md" "date: 2026-04-22"
assert_file_contains "$ws/knowledge/personnel/robin-smith/2026-04-22-1on1.md" 'person: "[[personnel/robin-smith/index]]"'
assert_file_contains "$ws/knowledge/personnel/jane/2026-04-21-1-1.md"        "type: 1on1"
assert_file_contains "$ws/knowledge/leadership/2026-04-22-slt-meeting.md"     "type: meeting"
assert_file_contains "$ws/knowledge/leadership/2026-04-22-slt-meeting.md"     "topic: slt-meeting"
assert_file_contains "$ws/knowledge/leadership/2026-04-22-slt-meeting.md"     "tags: [meeting, leadership]"
assert_file_contains "$ws/knowledge/lab-notebook/2026-04-22.md"               "tags: [daily, lab-notebook]"
assert_file_contains "$ws/knowledge/lab-notebook/2026-04-22.md"               "date: 2026-04-22"
assert_file_contains "$ws/knowledge/AI/foo.md" "tags: [ai]" "ai domain tag added to foo.md"
assert_eq "ai content" "$(tail -1 "$ws/knowledge/AI/foo.md")" "the note's own text is still there"
cleanup_workspace "$ws"

# ----------- S4 -----------
start_test "S4 — Obsidian bootstrap, idempotent"
ws=$(new_vault)
mkdir -p "$ws/knowledge/AI" "$ws/knowledge/personnel/robin"
echo "ai" > "$ws/knowledge/AI/foo.md"
echo "robin" > "$ws/knowledge/personnel/robin/2026-04-22-1on1.md"
pka_tools "$ws" obsidian bootstrap >/dev/null 2>&1
snap1=$(find "$ws/knowledge" -type f -exec cksum {} + | sort)
pka_tools "$ws" obsidian bootstrap >/dev/null 2>&1
snap2=$(find "$ws/knowledge" -type f -exec cksum {} + | sort)
if [ "$snap1" = "$snap2" ]; then
  pass_step "vault state unchanged after second bootstrap run"
else
  fail "second bootstrap run produced changes — not idempotent"
  diff <(echo "$snap1") <(echo "$snap2") | head -10 >&2
fi
cleanup_workspace "$ws"

# ----------- S5 -----------
start_test "S5 — Obsidian bootstrap, partial pre-existing"
ws=$(new_vault)
mkdir -p "$ws/knowledge/AI" "$ws/knowledge/personnel/robin" "$ws/knowledge/personnel/jane"
echo "ai" > "$ws/knowledge/AI/foo.md"
echo "robin" > "$ws/knowledge/personnel/robin/note.md"
echo "jane" > "$ws/knowledge/personnel/jane/note.md"
cat > "$ws/knowledge/AI/_MOC.md" <<'EOF'
# AI

## My thematic group
- [[AI/foo]]
EOF
preauth_moc=$(file_hash "$ws/knowledge/AI/_MOC.md")
cat > "$ws/knowledge/personnel/robin/index.md" <<'EOF'
---
type: person
name: Robin Hartley
role: Director
org: Acme
tags: [person]
---

# Robin Hartley

## Notes
- something the user wrote
EOF
preauth_robin=$(file_hash "$ws/knowledge/personnel/robin/index.md")

pka_tools "$ws" obsidian bootstrap >/dev/null 2>&1
assert_eq "$preauth_moc"   "$(file_hash "$ws/knowledge/AI/_MOC.md")"              "pre-existing AI MOC unchanged"
assert_eq "$preauth_robin" "$(file_hash "$ws/knowledge/personnel/robin/index.md")" "pre-existing robin/index.md unchanged"
assert_file_exists "$ws/knowledge/personnel/jane/index.md" "missing person index created"
cleanup_workspace "$ws"

# ----------- S6 -----------
start_test "S6 — Obsidian bootstrap, malformed frontmatter"
ws=$(new_vault)
mkdir -p "$ws/knowledge/AI"
cat > "$ws/knowledge/AI/broken.md" <<'EOF'
---
type: brief
topic: this: has an unquoted colon
tags: [research, ai]
---

body content
EOF
broken_hash=$(file_hash "$ws/knowledge/AI/broken.md")
echo "good" > "$ws/knowledge/AI/good.md"

out=$(pka_tools "$ws" obsidian bootstrap 2>&1)
assert_eq "$broken_hash" "$(file_hash "$ws/knowledge/AI/broken.md")" "malformed file unchanged"
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
assert_file_contains "$ws/knowledge/AI/good.md" "tags: [ai]" "non-malformed file got domain tag"
cleanup_workspace "$ws"

# ----------- no vault -----------
start_test "S-extra — No .obsidian/: refuses and changes nothing"
ws=$(make_workspace)
mkdir -p "$ws/.pka" "$ws/knowledge/AI"
install_pka_tools "$ws"
echo "ai" > "$ws/knowledge/AI/foo.md"
before=$(find "$ws/knowledge" -type f -exec cksum {} + | sort)
pka_tools "$ws" obsidian bootstrap >/dev/null 2>&1
assert_eq "3" "$?" "exit code 3 (workspace not ready)"
assert_eq "$before" "$(find "$ws/knowledge" -type f -exec cksum {} + | sort)" "vault untouched"
cleanup_workspace "$ws"

end_run
