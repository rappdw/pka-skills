# Inference Guide

How to infer folder semantics from structure and content. Used by bootstrap during pre-flight scan and by the librarian for standalone routing.

---

## Scan Protocol

For each top-level folder, collect:

1. **Folder name** — the primary inference signal
2. **Children count** — immediate files vs. subdirectories
3. **Organization pattern** — flat vs. subfolder-organized
4. **Subfolder names** (if organized) — up to 10, used for content inference
5. **File sample** (if flat) — up to 10 filenames
6. **Dominant extensions** — `.md`, `.pdf`, `.docx`, mixed
7. **Special file presence:**
   - `CLAUDE.md` → project workspace
   - `project-summary.md` → transitioned (completed) project
   - `Cargo.toml`, `package.json`, `go.mod`, `pyproject.toml` → code-primary project
   - Date-slug filenames (e.g., `2026-03-15-1-1-aarav.md`) → meeting notes home

---

## Organization Patterns

The flat vs. subfolder distinction is critical for inference quality.

| Pattern | Signal | Likely content |
|---------|--------|---------------|
| Subfolders named after people | Per-person folder structure | Personnel notes, 1-1s |
| Subfolders named by topic/project | Topic-organized reference | Research, documentation |
| Flat folder of date-named `.md` files | Chronological entries | Journal, lab notebook, meeting log |
| Flat folder of mixed file types | Unstructured collection | Inbox-like, needs routing |
| Subfolders with `CLAUDE.md` each | Project workspaces | Active work |
| Subfolders with `project-summary.md` | Archived projects | Reference material |

---

## Content Type Inference Rules

### Per-Person Notes
**Signals:** Subfolders named after people (first names, last names, or `firstname-lastname` slugs). Parent folder named `personnel`, `people`, `team`, `reports`, `directs`, `1-1s`, `one-on-ones`.

**Inferred:** "Per-person notes — one subfolder per individual"
**Organization:** By person
**Priority:** Active
**Confidence:** High if folder name matches; Medium if only subfolder names match

### Meeting / Strategy Notes
**Signals:** Folder named `leadership`, `strategy`, `meetings`, `slt`, `executive`, `board`. Contains files with date-slug names (`YYYY-MM-DD-*.md`). May contain subfolders by topic or date range.

**Inferred:** "Meeting and strategy notes"
**Organization:** By topic/date
**Priority:** Active
**Tags:** `meeting-home` if date-slug files detected
**Confidence:** High if date-slug files present; Medium if only folder name matches

### Research Outputs
**Signals:** Folder named `research`, `studies`, `analysis`, `investigations`. Subfolders by topic. Each subfolder typically contains `research.md` + supporting files (`.pdf`, `.docx`).

**Inferred:** "Systematic research outputs — one subfolder per topic"
**Organization:** By topic
**Priority:** Reference
**Confidence:** High if consistent subfolder structure; Medium otherwise

### Journal / Lab Notebook
**Signals:** Folder named `journal`, `diary`, `log`, `lab-notebook`, `notes`, `daily`. Contains date-named files or monthly files.

**Inferred:** "Chronological working notes"
**Organization:** By date
**Priority:** Active
**Confidence:** High if date-named files; Medium if only folder name

### Project Workspaces
**Signals:** Contains `CLAUDE.md` at root. May contain code project markers (`package.json`, `Cargo.toml`, etc.).

**Inferred:** "Active project workspace"
**Organization:** Project-specific
**Priority:** Active
**Status:** active
**Confidence:** High (CLAUDE.md is definitive)

**Special handling for code projects:** If `Cargo.toml`, `package.json`, `go.mod`, or `pyproject.toml` present at root, index only top-level `.md/.txt/.pdf/.docx` files. Skip all subdirectories for indexing.

### Archived / Transitioned Projects
**Signals:** Contains `project-summary.md`. Located inside a folder that also contains other project folders.

**Inferred:** "Completed project — transitioned to knowledge base"
**Organization:** Original project structure preserved
**Priority:** Reference
**Status:** archived
**Confidence:** High (project-summary.md is definitive)

### Archive Destination
**Signals:** Folder named `archived`, `archive`, `completed`, `historical`, or a folder that contains multiple project-summary.md subfolders. Also: a folder named `projects` inside a knowledge-domain parent.

**Inferred:** "Archive destination for completed projects"
**Priority:** Archive
**Confidence:** High if contains archived projects; Medium if only name matches

### Generic / Unclassifiable
**Signals:** None of the above patterns match clearly.

**Inferred:** Best-effort one-sentence description based on folder name and file sample
**Priority:** Active (default)
**Confidence:** Low — flag for user correction at Q3

---

## Meeting-Home Detection

A folder qualifies for the `meeting-home` tag when:

1. It contains 3+ files matching the date-slug pattern: `YYYY-MM-DD-*.md`
2. The date-slug files span at least 2 different months (not a one-time dump)
3. The folder is Active or Reference priority

Multiple folders can be tagged `meeting-home`. Common combinations:
- `personnel/` subfolders for 1-1 meeting notes (detected at subfolder level)
- `leadership/` for group/strategy meeting notes
- A dedicated `meetings/` folder

The `meeting-home` tag is used by `pka-meetings` for routing. It does not affect bootstrap behavior otherwise.

---

## Confidence Levels

| Level | Meaning | Bootstrap behavior |
|-------|---------|-------------------|
| **High** | Multiple confirming signals | Include in map without flagging |
| **Medium** | Single signal or name-only match | Include in map, note for review |
| **Low** | Guess from folder name only | Flag explicitly at Q3 for user correction |

---

## Edge Cases

- **Empty folders:** Include in map as "Empty — purpose unclear", Low confidence
- **Hidden folders (`.name`):** Skip entirely (`.pka/`, `.git/`, etc. handled by `.pkaignore`)
- **Symlinks:** Follow if they point inside the PKA root; skip if external
- **Very deep nesting (>3 levels):** Only scan to depth 2 for inference; deeper content indexed by librarian later
- **Mixed content folders:** Describe the dominant pattern; note mixed nature in contents description
