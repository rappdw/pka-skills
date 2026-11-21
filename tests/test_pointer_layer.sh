#!/usr/bin/env bash
# Pointer-layer scenarios (PR1–PR6), run against the shipped tool.
#
# Until v1.7 this suite drove tests/pointer_maintainer.py, a reference
# implementation that never shipped. It now installs pka-tools into a
# workspace and runs `.pka/bin/pka-tools pointers ...`, the same code a
# workspace runs. Deeper coverage (cluster rule, line-by-line edits, CRLF,
# padded tables) is in tests/tools/test_pointers.py.
#
#   PR1 — New domain, no MOC: a `## Pointers` section with one row is created.
#   PR2 — Existing MOC with two rows: a matching file extends the first row;
#         the second row is byte-identical; re-running changes nothing.
#   PR3 — A file whose topic matches no row: a new row at the bottom.
#   PR4 — Search: a pointer row outranks body matches (real index, real query).
#   PR5 — Rename: links are rewritten in every MOC.
#   PR6 — Check: a pointer link to a missing file is reported.
#   PR7 — Without Obsidian the layer is opt-in: no MOC is created until
#         `pointers init`; existing MOCs still get rows.

set -u
source "$(dirname "$0")/lib.sh"
configure_test_git_identity

# An Obsidian vault: pointer MOCs are created on demand there. Without
# Obsidian the pointer layer is opt-in (PR7).
new_vault() {
  local ws
  ws=$(make_workspace) || return 1
  mkdir -p "$ws/.pka" "$ws/knowledge/.obsidian"
  install_pka_tools "$ws"
  echo "$ws"
}

# write_note <file> <frontmatter line>...
write_note() {
  local file="$1"; shift
  mkdir -p "$(dirname "$file")"
  {
    echo "---"
    for line in "$@"; do echo "$line"; done
    echo "---"
    echo
    echo "body"
  } > "$file"
}

# ----------- PR1 -----------
start_test "PR1 — New domain, no MOC: pointer section created with first row"
ws=$(new_vault) || exit 1
write_note "$ws/knowledge/northwind/2026-04-23-joint-partnership-meeting.md" \
  "type: meeting" "date: 2026-04-23" "topic: northwind-partnership-2026" \
  "attendees: [sasha-ortega, jamie-lin, taylor-brooks]" "tags: [meeting, ai]"
pka_tools "$ws" pointers add knowledge/northwind/2026-04-23-joint-partnership-meeting.md \
  --context "Joint partnership meeting prep notes" >/dev/null

moc="$ws/knowledge/northwind/_MOC.md"
assert_file_exists "$moc"                                            "northwind/_MOC.md created"
assert_file_contains "$moc" "## Pointers"                            "Pointers section present"
assert_file_contains "$moc" "| Topic | Entities | Files |"           "table header present"
assert_file_contains "$moc" "northwind-partnership-2026"             "topic slug present"
assert_file_contains "$moc" "[[northwind/2026-04-23-joint-partnership-meeting]]"  "wikilink present"
assert_file_contains "$moc" "sasha-ortega, jamie-lin, taylor-brooks" "entities in the order the note lists them"
cleanup_workspace "$ws"

# ----------- PR2 -----------
start_test "PR2 — Existing MOC with two rows: matching route extends first row"
ws=$(new_vault) || exit 1
mkdir -p "$ws/knowledge/northwind"
cat > "$ws/knowledge/northwind/_MOC.md" <<'EOF'
# Northwind

## Pointers

Compact retrieval rows maintained by the librarian. Format: one row per concept cluster. FTS-indexed for fast lookup before expanding to file bodies.

| Topic | Entities | Files |
|---|---|---|
| northwind-partnership-2026 | sasha-ortega, taylor-brooks | [[northwind/northwind_partnership_proposal]] |
| lighthouse-research | atlas-model, victor-hale | [[northwind/revised_lighthouse]] |
EOF
moc="$ws/knowledge/northwind/_MOC.md"
row2_before=$(grep "^| lighthouse-research" "$moc")
rows_before=$(grep -c "^| " "$moc")

write_note "$ws/knowledge/northwind/2026-04-23-joint-partnership-meeting.md" \
  "type: meeting" "date: 2026-04-23" "topic: northwind-partnership-2026" \
  "attendees: [jamie-lin, casey-dunn]" "tags: [meeting, ai]"
pka_tools "$ws" pointers add knowledge/northwind/2026-04-23-joint-partnership-meeting.md >/dev/null

assert_file_contains "$moc" "[[northwind/northwind_partnership_proposal]], [[northwind/2026-04-23-joint-partnership-meeting]]" "new file appended to first row"
assert_file_contains "$moc" "sasha-ortega, taylor-brooks, jamie-lin, casey-dunn" "new entities added after the existing ones (nothing re-sorted)"
assert_eq "$rows_before" "$(grep -c "^| " "$moc")" "no extra row was coined"
assert_eq "$row2_before" "$(grep "^| lighthouse-research" "$moc")" "second row byte-identical"

hash_before=$(file_hash "$moc")
pka_tools "$ws" pointers add knowledge/northwind/2026-04-23-joint-partnership-meeting.md >/dev/null
assert_eq "$hash_before" "$(file_hash "$moc")" "re-routing same file produces no diff (idempotent)"
cleanup_workspace "$ws"

# ----------- PR3 -----------
start_test "PR3 — File with non-matching topic: new row appended at bottom"
ws=$(new_vault) || exit 1
mkdir -p "$ws/knowledge/northwind"
cat > "$ws/knowledge/northwind/_MOC.md" <<'EOF'
# Northwind

## Pointers

Compact retrieval rows maintained by the librarian.

| Topic | Entities | Files |
|---|---|---|
| northwind-partnership-2026 | sasha-ortega | [[northwind/northwind_partnership_proposal]] |
EOF
moc="$ws/knowledge/northwind/_MOC.md"
row1_before=$(grep "^| northwind-partnership" "$moc")

write_note "$ws/knowledge/northwind/revised_lighthouse.md" \
  "type: brief" "topic: lighthouse-research" "tags: [brief, ai]" 'related: ["[[atlas]]"]'
pka_tools "$ws" pointers add knowledge/northwind/revised_lighthouse.md >/dev/null

assert_file_contains "$moc" "[[northwind/revised_lighthouse]]"             "new file in new row"
assert_eq "$row1_before" "$(grep "^| northwind-partnership" "$moc")" "existing row unchanged"
last_row=$(grep "^| " "$moc" | tail -1)
assert_eq "| lighthouse-research | atlas | [[northwind/revised_lighthouse]] |" "$last_row" "new row appended at bottom"
cleanup_workspace "$ws"

# ----------- PR4 -----------
start_test "PR4 — Search: pointer row ranks above body matches"
ws=$(new_vault) || exit 1
mkdir -p "$ws/knowledge/AI/northwind"
python3 - "$ws" <<'PY'
import sys
from pathlib import Path
ws = Path(sys.argv[1])
filler = " ".join("word%d" % i for i in range(60))
(ws / "knowledge/AI/northwind/long_meeting_notes.md").write_text("northwind " + filler + "\n")
for n in range(5):
    (ws / ("knowledge/AI/northwind/distractor%d.md" % n)).write_text("northwind " + filler + "\n")
(ws / "knowledge/AI/northwind/proposal.md").write_text("the proposal\n")
(ws / "knowledge/AI/_MOC.md").write_text(
    "# AI\n\n## Pointers\n\n| Topic | Entities | Files |\n|---|---|---|\n"
    "| northwind-partnership-2026 | sasha-ortega, jamie-lin | [[AI/northwind/proposal]] |\n")
PY
pka_tools "$ws" db init >/dev/null
pka_tools "$ws" index >/dev/null
top=$(pka_tools "$ws" search northwind --json | python3 -c '
import json, sys
data = json.load(sys.stdin)
first = data["results"][0]
print("%s|%s|%s|%d" % (first["is_pointer"], first["path"], first["files"][0]["path"], data["count"]))')
# 8 hits: the pointer row, six notes with the word in their text, and
# proposal.md, which matches through its folder name.
assert_eq "True|knowledge/AI/_MOC.md|knowledge/AI/northwind/proposal.md|8" "$top" \
  "the pointer row is the first of 8 hits and expands to its file"
slug_hit=$(pka_tools "$ws" search northwind-partnership-2026 --json | python3 -c '
import json, sys
print(json.load(sys.stdin)["count"])')
assert_eq "1" "$slug_hit" "a hyphenated slug is a valid query (it was a syntax error unquoted)"
cleanup_workspace "$ws"

# ----------- PR5 -----------
start_test "PR5 — Rename: pointer-row wikilinks updated across all MOCs"
ws=$(new_vault) || exit 1
mkdir -p "$ws/knowledge/AI" "$ws/knowledge/leadership"
for d in AI leadership; do
cat > "$ws/knowledge/$d/_MOC.md" <<'EOF'
# Domain

## Pointers

| Topic | Entities | Files |
|---|---|---|
| northwind-partnership-2026 | sasha-ortega | [[northwind/old_meeting_name]] |
EOF
done

out=$(pka_tools "$ws" pointers rename knowledge/northwind/old_meeting_name.md \
  knowledge/northwind/2026-04-23-joint-partnership-meeting.md)
echo "$out" | sed 's/^/  > /'
assert_file_contains "$ws/knowledge/AI/_MOC.md" "[[northwind/2026-04-23-joint-partnership-meeting]]" "AI MOC updated"
assert_file_contains "$ws/knowledge/leadership/_MOC.md" "[[northwind/2026-04-23-joint-partnership-meeting]]" "leadership MOC updated"
assert_file_lacks    "$ws/knowledge/AI/_MOC.md" "[[northwind/old_meeting_name]]" "AI MOC no longer has old name"
assert_file_lacks    "$ws/knowledge/leadership/_MOC.md" "[[northwind/old_meeting_name]]" "leadership MOC no longer has old name"

hash_a=$(file_hash "$ws/knowledge/AI/_MOC.md")
hash_l=$(file_hash "$ws/knowledge/leadership/_MOC.md")
pka_tools "$ws" pointers rename knowledge/northwind/old_meeting_name.md \
  knowledge/northwind/2026-04-23-joint-partnership-meeting.md >/dev/null
assert_eq "$hash_a" "$(file_hash "$ws/knowledge/AI/_MOC.md")"         "AI MOC unchanged on re-run"
assert_eq "$hash_l" "$(file_hash "$ws/knowledge/leadership/_MOC.md")" "leadership MOC unchanged on re-run"
cleanup_workspace "$ws"

# ----------- PR6 -----------
start_test "PR6 — Check flags broken pointer-row wikilinks"
ws=$(new_vault) || exit 1
mkdir -p "$ws/knowledge/AI"
echo "body" > "$ws/knowledge/AI/exists.md"
cat > "$ws/knowledge/AI/_MOC.md" <<'EOF'
# AI

## Pointers

| Topic | Entities | Files |
|---|---|---|
| ai-strategy | none | [[AI/exists]], [[AI/missing-file]] |
EOF
broken=$(pka_tools "$ws" pointers check --json | python3 -c '
import json, sys
print(",".join(item["broken_link"] for item in json.load(sys.stdin)["broken"]))')
assert_eq "[[AI/missing-file]]" "$broken" "exactly the missing link is reported"
pka_tools "$ws" pointers check --strict >/dev/null 2>&1
assert_eq "1" "$?" "--strict exits 1 when a link is broken"
cleanup_workspace "$ws"

# ----------- cross-MOC -----------
start_test "PR-extra — Cross-MOC duplication: row added to each tagged domain's MOC"
ws=$(new_vault) || exit 1
mkdir -p "$ws/knowledge/AI/northwind" "$ws/knowledge/leadership"
write_note "$ws/knowledge/AI/northwind/2026-04-23-meeting.md" \
  "type: meeting" "date: 2026-04-23" "topic: northwind-partnership-2026" "tags: [meeting, ai, leadership]"
pka_tools "$ws" pointers add knowledge/AI/northwind/2026-04-23-meeting.md >/dev/null
assert_file_contains "$ws/knowledge/AI/_MOC.md" "northwind-partnership-2026" "AI MOC has the cluster"
assert_file_contains "$ws/knowledge/leadership/_MOC.md" "northwind-partnership-2026" "leadership MOC has the cluster (cross-MOC duplication)"
cleanup_workspace "$ws"

# ----------- PR7 -----------
start_test "PR7 — Without Obsidian: no MOC is created until the user opts in"
ws=$(make_workspace) || exit 1
mkdir -p "$ws/.pka" "$ws/knowledge/AI" "$ws/knowledge/leadership"
install_pka_tools "$ws"
write_note "$ws/knowledge/AI/2026-04-23-meeting.md" \
  "type: meeting" "topic: northwind-partnership-2026" "tags: [meeting, ai, leadership]"
cat > "$ws/knowledge/leadership/_MOC.md" <<'EOF'
# Leadership
EOF
out=$(pka_tools "$ws" pointers add knowledge/AI/2026-04-23-meeting.md)
echo "$out" | sed 's/^/  > /'
assert_dir_absent "$ws/knowledge/AI/_MOC.md" "no MOC created in a plain-markdown vault"
assert_file_contains "$ws/knowledge/leadership/_MOC.md" "northwind-partnership-2026" "an existing MOC still gets the row"
pka_tools "$ws" pointers init >/dev/null
assert_file_exists "$ws/knowledge/AI/_MOC.md" "pointers init created the MOC"
pka_tools "$ws" pointers add knowledge/AI/2026-04-23-meeting.md >/dev/null
assert_file_contains "$ws/knowledge/AI/_MOC.md" "[[AI/2026-04-23-meeting]]" "after opting in, the row is written"
cleanup_workspace "$ws"

end_run
