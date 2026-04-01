# Inference Guide

How to infer folder semantics from structure and content. Used by the librarian for standalone routing when no Repo Map is available, and as a shared reference for understanding folder structure.

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

| Pattern | Signal | Likely content |
|---------|--------|---------------|
| Subfolders named after people | Per-person folder structure | Personnel notes, 1-1s |
| Subfolders named by topic/project | Topic-organized reference | Research, documentation |
| Flat folder of date-named `.md` files | Chronological entries | Journal, lab notebook, meeting log |
| Flat folder of mixed file types | Unstructured collection | Inbox-like, needs routing |
| Subfolders with `CLAUDE.md` each | Project workspaces | Active work |
| Subfolders with `project-summary.md` | Archived projects | Reference material |

---

## Routing Inference for Standalone Use

When no Repo Map exists, the librarian infers routing from folder names and structure:

### Step 1 — Identify destination candidates
Scan top-level folders. For each, apply the content type inference rules below.

### Step 2 — Match incoming file to destination
For each file in `team-inbox/`:
- Extract keywords from filename and (if readable) first 500 characters of content
- Match against folder names and inferred content types
- Score candidates by relevance

### Step 3 — Present proposals
Show the user: "I'd route `<file>` to `<destination>` because `<reason>`." Never move without confirmation in standalone mode.

---

## Content Type Inference Rules

### Per-Person Notes
**Signals:** Subfolders named after people. Parent folder named `personnel`, `people`, `team`, `reports`, `directs`, `1-1s`.
**Routing match:** Files mentioning a person's name → that person's subfolder

### Meeting / Strategy Notes
**Signals:** Folder named `leadership`, `strategy`, `meetings`, `slt`, `executive`. Date-slug files present.
**Routing match:** Files with meeting keywords, executive names, strategic topics

### Research Outputs
**Signals:** Folder named `research`, `studies`, `analysis`. Subfolders by topic with consistent structure.
**Routing match:** Files with research/analysis keywords, PDF papers, source documents

### Journal / Lab Notebook
**Signals:** Folder named `journal`, `diary`, `log`, `lab-notebook`, `notes`. Date-named files.
**Routing match:** Date-stamped personal notes, working observations

### Project Workspaces
**Signals:** Contains `CLAUDE.md`. May contain code project markers.
**Routing match:** **Never auto-route to project workspaces.** If a filename contains a project slug, ask the user.

### Archive
**Signals:** Folder named `archived`, `archive`, `completed`, `historical`.
**Routing match:** Only via explicit user instruction — never auto-route to archive.

---

## Confidence Levels

| Level | Meaning | Routing behavior |
|-------|---------|-----------------|
| **High** | Multiple confirming signals | Present proposal with confidence |
| **Medium** | Single signal or name-only match | Present proposal, note uncertainty |
| **Low** | Guess from folder name only | List as option but ask explicitly |
