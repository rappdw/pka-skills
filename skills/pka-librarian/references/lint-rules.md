# Lint Rules

Health-check rules for the PKA knowledge base. Lint produces a non-destructive
report; the user reviews and acts. Lint never modifies files automatically.

---

## When to Run

- **Weekly or monthly cadence** — not every session
- On demand: "run a health check", "lint my knowledge base", "what needs attention?"
- Recommended after large imports or structural changes

---

## Rules

### 1. Orphan files

**Detects:** Files in `team-inbox/unsorted/` older than 14 days.

**Why:** Unsorted files represent routing decisions the user deferred. After
two weeks they're likely forgotten.

**Output:**
```
## N orphan files in team-inbox/unsorted/
- `<path>` (added 21 days ago)
- ...
```

**Action hint:** "Route these or delete. Say: 'process team-inbox/unsorted'."

---

### 2. Broken links

**Detects:** Markdown links `[text](path)` or `[[wikilink]]` pointing at
nonexistent paths within the knowledge base.

**Scope:**
- Relative paths within PKA root
- `[[wikilinks]]` resolved against the vault root (`knowledge/`) — covers
  wiki-home folders, MOC files, and **pointer-row Files columns inside
  `_MOC.md` files**
- Absolute paths outside PKA root are skipped (user's responsibility)

**Why:** File moves and deletions leave dangling references. Pointer rows in
particular accumulate over time and are append-only by the librarian, so
broken pointer wikilinks need the user's attention to clean up.

**Output:**
```
## N broken links
- `<source-file>:line` → `<target-path>` (missing)
- `<source-MOC>:line` → `<target-path>` (missing — in Pointers row, topic '<slug>')
- ...
```

When a broken link is inside a `_MOC.md` Pointers table, the report annotates
the row's topic slug to make the cleanup target clear.

**Action hint:** "Fix or remove these references. For broken pointer-row
wikilinks: edit the MOC manually — the librarian is append-only and will not
remove them on its own."

---

### 3. Stale wiki sources

**Detects:** Paths listed in a wiki's `## Sources` section where the target
file no longer exists.

**Scope:** All `wiki.md` files in `wiki-home` folders.

**Why:** Wikis cite authored notes. When notes are moved or deleted, citations
rot.

**Output:**
```
## N stale wiki sources
- `knowledge/topics/mcp/wiki.md` cites `<path>` (missing)
- ...
```

**Action hint:** "Update the wiki or restore the source."

---

### 4. Empty Repo Map folders

**Detects:** Folders listed in `CLAUDE.md` Repo Map with zero indexable files
(`.md`, `.pdf`, `.docx`, `.txt`).

**Why:** Empty folders in the map may indicate completed workflows or
stale entries.

**Output:**
```
## N empty Repo Map folders
- `<folder>` — last file removed ~ <date guessed from git or mtime>
```

**Action hint:** "Remove from Repo Map or archive the folder."

---

### 5. Missing back-references (low priority)

**Detects:** Meeting notes or authored files mentioning a person/topic where
the person's folder or topic wiki has no inbound link to this file.

**Method:**
- For each entity in Repo Map (personnel folders, topic wikis), grep the
  knowledge base for mentions
- Compare mentions to actual links in the entity's folder/wiki
- Report discrepancies

**Why:** Cross-referencing improves discoverability. Manual maintenance gets
missed.

**Output:**
```
## N missing back-references
- `<note-path>` mentions Maria but `personnel/maria/` has no inbound link
- ...
```

**Action hint:** "Add a References section to each entity file, or defer."

**Priority:** Low — surface in report, don't warn loudly.

---

### 6. Contradiction candidates

**Detects:** Wiki claims older than 30 days with 3+ newer authored notes on
the same topic that haven't been ingested into the wiki.

**Method:**
- For each wiki, get `last-updated` from frontmatter
- FTS search for topic slug across knowledge base with modified-after filter
- Exclude notes already in wiki's Sources list
- Flag if ≥3 new matches

**Why:** Surfaces wikis drifting from current understanding without making
claims about specific contradictions.

**Output:**
```
## N contradiction candidates (review)
- `knowledge/topics/mcp/wiki.md` (updated 45 days ago) — 5 newer mentions not yet ingested
  - `knowledge/personnel/aarav/2026-04-02-1-1-aarav.md`
  - ...
```

**Action hint:** "Consider ingesting these into the wiki."

**Priority:** Medium — worth reviewing but not urgent.

---

### 7. Uncited wiki claims (wiki-specific)

**Detects:** Wiki pages where `## Sources` list is empty OR where paragraphs
in `## What it is` or `## Key concepts` don't reference any path.

**Method:** Regex for path-like strings in synthesis sections; compare to
Sources list.

**Why:** PKA wiki pages are required to cite sources. Uncited claims erode
trust.

**Output:**
```
## N uncited wiki sections
- `knowledge/topics/agents/wiki.md` — ## Key concepts has 2 paragraphs without citations
```

**Action hint:** "Add citations or rewrite with sources."

---

## Report Format

```markdown
# Knowledge Base Health — YYYY-MM-DD

Scanned: N files, M wiki pages, P Repo Map folders
Checks run: orphans, broken-links, stale-sources, empty-folders, back-refs, contradictions, uncited-claims

## Summary
- 3 broken links
- 2 stale wiki sources
- 5 missing back-references (low priority)
- 1 contradiction candidate (review)

## Details

[Each section as defined above, only included if it has findings]

## Suggested next actions
1. Fix 3 broken links — highest priority
2. Review contradiction candidate in mcp wiki
3. (Optional) Add back-references
```

Saved to `owner-inbox/librarian-lint-<YYYY-MM-DD>.md`.

---

## What Lint Does NOT Do

- **Does not auto-fix anything.** Report only.
- **Does not re-index.** That's a separate librarian capability.
- **Does not decide contradictions.** Only surfaces candidates for user review.
- **Does not move/delete files.** User acts on the report manually or invokes
  other librarian modes.

---

## Performance

- Orphan/broken-link/stale-source checks: fast, pure file operations
- Back-reference check: slower (FTS per entity); skip on "quick lint" variant
- Contradiction check: medium (date filter + FTS)

"Quick lint" = rules 1-4 only. "Full lint" = all rules. Default: full.
