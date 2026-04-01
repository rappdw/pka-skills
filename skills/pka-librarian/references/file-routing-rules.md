# File Routing Rules

Heuristics for routing files from `team-inbox/` into the knowledge structure. Uses the Repo Map when available; falls back to folder name inference.

---

## Routing Priority

1. **Repo Map match** — if a Repo Map exists, use it as the primary routing guide
2. **Filename signals** — project slugs, person names, topic keywords in the filename
3. **Content signals** — first 500 characters of readable files for keyword extraction
4. **File type signals** — PDFs near research folders, scans near OCR-processed folders
5. **Ask the user** — when no confident match exists

---

## Routing Decision Tree

```
File arrives in team-inbox/
│
├─ Is it a transcript? (.vtt, .srt, *transcript*)
│  └─ YES → Hold for pka-meetings. Do NOT route.
│
├─ Does filename contain a project slug from Repo Map?
│  └─ YES → Ask: "This looks related to project <X>. Route to the project 
│           workspace, or to knowledge/?" Never auto-route to projects.
│
├─ Does filename contain a person's name matching personnel/?
│  └─ YES → Propose: knowledge/personnel/<person>/
│
├─ Does content/filename match a Repo Map folder's topic?
│  └─ YES → Propose that folder
│
├─ Is it a research document (PDF + topic structure)?
│  └─ YES → Propose: knowledge/research/<inferred-topic>/
│
├─ Is it a meeting note (date-slug filename pattern)?
│  └─ YES → Hand off to pka-meetings for routing
│
└─ No confident match
   └─ Move to team-inbox/unsorted/ and flag in report
```

---

## File Type Handling

| File type | Text extraction | Routing notes |
|-----------|----------------|---------------|
| `.md` | Direct read | Primary knowledge format |
| `.txt` | Direct read | Check if it's a transcript (content patterns) |
| `.pdf` | pdfplumber/pypdf (text layer) or tesseract (image) | Create OCR sidecar `.txt` |
| `.docx` | Python-docx or pandoc | Check if transcript (Teams export format) |
| `.html` | Strip tags, extract text | Rare in team-inbox |
| `.png`, `.jpg`, `.jpeg` | Tesseract OCR if available | Likely scanned documents |
| `.eml`, `.msg` | Skip by default (`.pkaignore`) | User must remove from ignore to process |
| `.vtt`, `.srt` | Transcript format — hold for pka-meetings | Never route directly |

---

## Routing Confirmation

**Ask-before-everything mode:** Confirm every routing proposal individually.

**Ask-before-destructive mode:** Confirm routing proposals. Creates (sidecar files, index entries) proceed without confirmation.

**Hands-off mode:** Route automatically based on highest-confidence match. Report results afterward. Still hold transcripts for pka-meetings.

---

## Unsorted Files

Files with no confident routing match go to `team-inbox/unsorted/`. They are:
- Listed in the librarian report
- Never silently discarded
- Never moved to a knowledge folder without explicit user instruction
- Reviewed at next session start by the orchestrator

---

## Project Slug Detection

A filename "contains a project slug" when:
1. The Repo Map lists active project workspaces
2. A project's folder name (slug) appears as a substring in the filename
3. Match is case-insensitive
4. Minimum slug length: 4 characters (avoids false positives on short names)

Example: File `satori-alignment-v2.pdf` matches project slug `satori`.

**Never auto-route to project workspaces.** Always ask.

---

## Batch Processing

When `team-inbox/` contains multiple files:
1. Inventory all files first (type, size, text availability)
2. Detect and separate transcripts
3. Group remaining files by proposed destination
4. Present grouped routing proposals: "I'd route these 3 files to knowledge/leadership/ and these 2 to knowledge/research/. Confirm?"
5. Process confirmed groups
6. Report results
