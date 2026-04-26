#!/usr/bin/env bash
# Shell tests for the v1.6.1 pointer-layer addition.
#
# Drives tests/pointer_maintainer.py (deterministic reference impl) against
# fixture vaults and verifies the pointer-row contract.
#
# Spec scenarios covered:
#   PR1 — New domain, no MOC: librarian routes a meeting note. Assert MOC
#         is created with a `## Pointers` section containing one row.
#   PR2 — Existing MOC with two pointer rows: librarian routes a file matching
#         the first row's topic. Assert file appended to first row's Files;
#         entities merged; second row untouched.
#   PR3 — File with topic that doesn't match any existing row. New row
#         appended at bottom; existing rows unchanged.
#   PR4 — FTS query that matches both a pointer row and several body rows.
#         Pointer row ranks above body matches (Python sqlite3 in-memory test).
#   PR5 — Rename: every Pointers-table row referencing the old path is
#         updated to the new path across all MOCs.
#   PR6 — Lint catches a Pointers-table wikilink to a file that no longer
#         exists.

set -u
source "$(dirname "$0")/lib.sh"

MAINTAINER="$(dirname "$0")/pointer_maintainer.py"
if [ ! -f "$MAINTAINER" ]; then
  echo "${RED}MISSING:${RESET} $MAINTAINER" >&2
  exit 1
fi

run_route() {
  local ws="$1" file="$2" fm="$3" ctx="${4:-}" tags="${5:-}"
  python3 "$MAINTAINER" route --workspace "$ws" --file "$file" --frontmatter "$fm" \
    --routing-context "$ctx" --domain-tags "$tags"
}

# ----------- PR1: new domain, no MOC -----------
start_test "PR1 — New domain, no MOC: pointer section created with first row"
ws=$(make_workspace)
mkdir -p "$ws/knowledge/anthropic"
# Drop a meeting file (its content doesn't matter for pointer maintenance —
# we only use the path + frontmatter passed via the helper)
echo "body" > "$ws/knowledge/anthropic/2026-04-23-gcn-partnership-meeting.md"

fm='{"type":"meeting","date":"2026-04-23","topic":"anthropic-partnership-2026","attendees":["sam-werboff","jordan-josloff","tom-turvey"],"tags":["meeting","ai"]}'
run_route "$ws" "anthropic/2026-04-23-gcn-partnership-meeting" "$fm" \
  "GCN partnership meeting prep notes" "" >/dev/null

# Assertions
moc="$ws/knowledge/anthropic/_MOC.md"
assert_file_exists "$moc"                                            "anthropic/_MOC.md created"
assert_file_contains "$moc" "## Pointers"                            "Pointers section present"
assert_file_contains "$moc" "| Topic | Entities | Files |"           "table header present"
assert_file_contains "$moc" "anthropic-partnership-2026"             "topic slug present"
assert_file_contains "$moc" "[[anthropic/2026-04-23-gcn-partnership-meeting]]"  "wikilink present"
# Entities should be alphabetized
assert_file_contains "$moc" "jordan-josloff, sam-werboff, tom-turvey" "entities alphabetized"

cleanup_workspace "$ws"

# ----------- PR2: existing MOC, matching topic → row extended -----------
start_test "PR2 — Existing MOC with two rows: matching route extends first row"
ws=$(make_workspace)
mkdir -p "$ws/knowledge/anthropic"
# Pre-seed an MOC with two pointer rows
cat > "$ws/knowledge/anthropic/_MOC.md" <<'EOF'
# Anthropic

## Pointers

Compact retrieval rows maintained by the librarian. Format: one row per concept cluster. FTS-indexed for fast lookup before expanding to file bodies.

| Topic | Entities | Files |
|---|---|---|
| anthropic-partnership-2026 | sam-werboff, tom-turvey | [[anthropic/anthropic_partnership_proposal]] |
| glasswing-research | claude-mythos, vitaly-gudanets | [[anthropic/revised_glasswing]] |
EOF

# Snapshot the second row before
row2_before=$(grep "^| glasswing-research" "$ws/knowledge/anthropic/_MOC.md")

# Route a new file matching the first row's topic
fm='{"type":"meeting","date":"2026-04-23","topic":"anthropic-partnership-2026","attendees":["jordan-josloff","cat-de-jong"],"tags":["meeting","ai"]}'
run_route "$ws" "anthropic/2026-04-23-gcn-partnership-meeting" "$fm" >/dev/null

moc="$ws/knowledge/anthropic/_MOC.md"
# First row should have new file appended
assert_file_contains "$moc" "[[anthropic/2026-04-23-gcn-partnership-meeting]]"     "new file appended to first row"
assert_file_contains "$moc" "[[anthropic/anthropic_partnership_proposal]]"          "original file still in first row"
# New entities merged (jordan-josloff, cat-de-jong)
assert_file_contains "$moc" "cat-de-jong"                                          "new entity 'cat-de-jong' merged"
assert_file_contains "$moc" "jordan-josloff"                                       "new entity 'jordan-josloff' merged"
assert_file_contains "$moc" "sam-werboff"                                          "original entity preserved"

# Second row untouched
row2_after=$(grep "^| glasswing-research" "$ws/knowledge/anthropic/_MOC.md")
assert_eq "$row2_before" "$row2_after" "second row byte-identical"

# Idempotency: re-route the same file → no diff
md5_before=$(md5sum "$moc" | awk '{print $1}')
run_route "$ws" "anthropic/2026-04-23-gcn-partnership-meeting" "$fm" >/dev/null
md5_after=$(md5sum "$moc" | awk '{print $1}')
assert_eq "$md5_before" "$md5_after" "re-routing same file produces no diff (idempotent)"

cleanup_workspace "$ws"

# ----------- PR3: file with non-matching topic → new row appended -----------
start_test "PR3 — File with non-matching topic: new row appended at bottom"
ws=$(make_workspace)
mkdir -p "$ws/knowledge/anthropic"
cat > "$ws/knowledge/anthropic/_MOC.md" <<'EOF'
# Anthropic

## Pointers

Compact retrieval rows maintained by the librarian.

| Topic | Entities | Files |
|---|---|---|
| anthropic-partnership-2026 | sam-werboff | [[anthropic/anthropic_partnership_proposal]] |
EOF
row1_before=$(grep "^| anthropic-partnership" "$ws/knowledge/anthropic/_MOC.md")

fm='{"type":"brief","topic":"glasswing-research","tags":["brief","ai"],"related":["[[mythos]]"]}'
run_route "$ws" "anthropic/revised_glasswing" "$fm" >/dev/null

moc="$ws/knowledge/anthropic/_MOC.md"
assert_file_contains "$moc" "glasswing-research"                          "new topic row appended"
assert_file_contains "$moc" "[[anthropic/revised_glasswing]]"             "new file in new row"

# First row unchanged
row1_after=$(grep "^| anthropic-partnership" "$ws/knowledge/anthropic/_MOC.md")
assert_eq "$row1_before" "$row1_after" "existing row unchanged"

# New row should be at the bottom
last_row=$(grep "^| " "$ws/knowledge/anthropic/_MOC.md" | grep -v "^| Topic" | tail -1)
if echo "$last_row" | grep -q "glasswing-research"; then
  pass_step "new row appended at bottom"
else
  fail "new row not at bottom: $last_row"
fi

cleanup_workspace "$ws"

# ----------- PR4: FTS rank boost (inline Python sqlite3 test) -----------
start_test "PR4 — FTS rank boost: pointer row ranks above body matches"
python3 - <<'PY'
import sqlite3, sys
conn = sqlite3.connect(":memory:")
c = conn.cursor()
c.execute(
    "CREATE VIRTUAL TABLE search_fts USING fts5(path, content, is_pointer UNINDEXED, tokenize='porter unicode61')"
)
# A body match: the word "anthropic" appears alongside ~50 other words
body = "anthropic " + " ".join(f"word{i}" for i in range(50))
c.execute("INSERT INTO search_fts(path, content, is_pointer) VALUES(?, ?, 0)",
          ("anthropic/long_meeting_notes.md", body))
# Five distractor body rows
for i in range(5):
    c.execute("INSERT INTO search_fts(path, content, is_pointer) VALUES(?, ?, 0)",
              (f"anthropic/distractor{i}.md", "anthropic " + " ".join(f"filler{j}" for j in range(50))))
# A pointer row: anthropic appears in a dense, short row
c.execute(
    "INSERT INTO search_fts(path, content, is_pointer) VALUES(?, ?, 1)",
    ("knowledge/AI/_MOC.md",
     "anthropic-partnership-2026 sam-werboff jordan-josloff [[anthropic/proposal]]"),
)

# Query without boost: pointer row may or may not win depending on raw BM25
q = "anthropic"
c.execute(
    "SELECT path, is_pointer, rank FROM search_fts WHERE search_fts MATCH ? ORDER BY rank LIMIT 5",
    (q,)
)
no_boost = c.fetchall()

# With 3× boost via the documented formula. SQLite FTS5 BM25 returns
# NEGATIVE values where MORE NEGATIVE = better match. To rank pointer rows
# higher, multiply their rank by 3 (making them more negative); body rows
# stay at 1×.
c.execute(
    """SELECT path, is_pointer, rank * (CASE is_pointer WHEN 1 THEN 3.0 ELSE 1.0 END) AS adj
       FROM search_fts WHERE search_fts MATCH ? ORDER BY adj LIMIT 5""",
    (q,)
)
with_boost = c.fetchall()

# Assertion: with the boost, the pointer row is the top result
top_path, top_is_ptr, _ = with_boost[0]
if top_is_ptr == 1 and "_MOC.md" in top_path:
    print(f"  ok  pointer row ranks first with 3x boost: {top_path}")
else:
    print(f"  FAIL  expected pointer row to rank first; got {top_path} (is_pointer={top_is_ptr})", file=sys.stderr)
    print("  no-boost ranking:", no_boost, file=sys.stderr)
    print("  with-boost ranking:", with_boost, file=sys.stderr)
    sys.exit(1)
PY
if [ $? -eq 0 ]; then
  pass_step "FTS rank boost verified (pointer row ranks first)"
else
  fail "FTS rank boost test failed"
fi

# ----------- PR5: rename propagation -----------
start_test "PR5 — Rename: pointer-row wikilinks updated across all MOCs"
ws=$(make_workspace)
mkdir -p "$ws/knowledge/AI" "$ws/knowledge/leadership"
# Two MOCs both reference the same file
cat > "$ws/knowledge/AI/_MOC.md" <<'EOF'
# AI

## Pointers

| Topic | Entities | Files |
|---|---|---|
| anthropic-partnership-2026 | sam-werboff | [[anthropic/old_meeting_name]] |
EOF
cat > "$ws/knowledge/leadership/_MOC.md" <<'EOF'
# Leadership

## Pointers

| Topic | Entities | Files |
|---|---|---|
| anthropic-partnership-2026 | sam-werboff | [[anthropic/old_meeting_name]] |
EOF

mapping='{"anthropic/old_meeting_name":"anthropic/2026-04-23-gcn-partnership-meeting"}'
out=$(python3 "$MAINTAINER" rename --workspace "$ws" --mapping "$mapping")
echo "$out" | sed 's/^/  > /'

assert_file_contains "$ws/knowledge/AI/_MOC.md" "[[anthropic/2026-04-23-gcn-partnership-meeting]]" "AI MOC updated"
assert_file_contains "$ws/knowledge/leadership/_MOC.md" "[[anthropic/2026-04-23-gcn-partnership-meeting]]" "leadership MOC updated"
assert_file_lacks    "$ws/knowledge/AI/_MOC.md" "[[anthropic/old_meeting_name]]" "AI MOC no longer has old name"
assert_file_lacks    "$ws/knowledge/leadership/_MOC.md" "[[anthropic/old_meeting_name]]" "leadership MOC no longer has old name"

# Idempotency: re-running with the same mapping is a no-op
md5_a_before=$(md5sum "$ws/knowledge/AI/_MOC.md" | awk '{print $1}')
md5_l_before=$(md5sum "$ws/knowledge/leadership/_MOC.md" | awk '{print $1}')
python3 "$MAINTAINER" rename --workspace "$ws" --mapping "$mapping" >/dev/null
assert_eq "$md5_a_before" "$(md5sum "$ws/knowledge/AI/_MOC.md" | awk '{print $1}')"             "AI MOC unchanged on re-run"
assert_eq "$md5_l_before" "$(md5sum "$ws/knowledge/leadership/_MOC.md" | awk '{print $1}')"     "leadership MOC unchanged on re-run"

cleanup_workspace "$ws"

# ----------- PR6: lint catches broken pointer wikilinks -----------
start_test "PR6 — Lint flags broken pointer-row wikilinks"
ws=$(make_workspace)
mkdir -p "$ws/knowledge/AI"
# Create a real file...
echo "body" > "$ws/knowledge/AI/exists.md"
# ...and a pointer-table row that references both a real file and a missing one
cat > "$ws/knowledge/AI/_MOC.md" <<'EOF'
# AI

## Pointers

| Topic | Entities | Files |
|---|---|---|
| ai-strategy | none | [[AI/exists]], [[AI/missing-file]] |
EOF

out=$(python3 "$MAINTAINER" lint --workspace "$ws")
echo "$out" | sed 's/^/  > /'

# The output is JSON; verify it lists the broken link and not the real one
echo "$out" | python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
broken = data.get('broken', [])
for b in broken:
    print(f\"  reported: {b['moc']}: '{b['topic']}' -> {b['broken_link']}\")
links = [b['broken_link'] for b in broken]
real_links = [b for b in broken if 'AI/exists' in b['broken_link']]
missing_links = [b for b in broken if 'AI/missing-file' in b['broken_link']]
assert not real_links, f'false positive: existing file flagged: {real_links}'
assert missing_links, f'true negative: missing file not flagged'
print('  ok  exactly the missing link reported')
"
if [ $? -eq 0 ]; then
  pass_step "lint correctly identifies broken pointer wikilink"
else
  fail "lint missed or false-flagged a pointer wikilink"
fi

cleanup_workspace "$ws"

# ----------- Bonus: cross-MOC duplication -----------
start_test "PR-extra — Cross-MOC duplication: row added to multiple domain MOCs"
ws=$(make_workspace)
mkdir -p "$ws/knowledge/AI" "$ws/knowledge/leadership"

fm='{"type":"meeting","date":"2026-04-23","topic":"anthropic-partnership-2026","tags":["meeting","ai","leadership"]}'
run_route "$ws" "AI/anthropic/2026-04-23-meeting" "$fm" "" "ai,leadership" >/dev/null

# Both AI/_MOC.md and leadership/_MOC.md should have the row
ai_moc="$ws/knowledge/AI/_MOC.md"
ld_moc="$ws/knowledge/leadership/_MOC.md"
assert_file_exists "$ai_moc"
assert_file_exists "$ld_moc"
assert_file_contains "$ai_moc" "anthropic-partnership-2026" "AI MOC has the cluster"
assert_file_contains "$ld_moc" "anthropic-partnership-2026" "leadership MOC has the cluster (cross-MOC duplication)"

cleanup_workspace "$ws"

end_run
