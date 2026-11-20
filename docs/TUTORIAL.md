# PKA Tutorial

The long-form written reference for pka-skills v1.10.0: what each part does, what you say to use it, and what ends up on disk. It follows one fictional workspace from setup to a weekly health check.

Two shorter routes cover the same ground:

- The [walkthrough site](https://rappdw.github.io/pka-skills/) shows one concept per screen.
- Inside your own workspace, say *"Give me a tour"*. The `pka-tutorial` skill teaches the same material with your folder names.

**About the examples.** Sam is the owner of the workspace at `~/pka/`. Priya and Robin Smith are colleagues, Orion and Lyra are projects, Northwind is a vendor. All of them are made up. The conversations are illustrations, and the wording you see will differ. File formats and `pka-tools` output are shown as v1.10.0 writes them.

## Contents

1. [Before you start](#1-before-you-start)
2. [Setting up a workspace](#2-setting-up-a-workspace)
3. [A session, start to finish](#3-a-session-start-to-finish)
4. [The Repo Map](#4-the-repo-map)
5. [Roles](#5-roles)
6. [Finding what you know](#6-finding-what-you-know)
7. [Dropping files in](#7-dropping-files-in)
8. [Meetings](#8-meetings)
9. [People and timelines](#9-people-and-timelines)
10. [MOCs, the pointer layer and Obsidian](#10-mocs-the-pointer-layer-and-obsidian)
11. [Topic wikis](#11-topic-wikis)
12. [The dashboard](#12-the-dashboard)
13. [Project lifecycle](#13-project-lifecycle)
14. [Health checks](#14-health-checks)
15. [`pka-tools`, and why PKA never commits](#15-pka-tools-and-why-pka-never-commits)
16. [Upgrading](#16-upgrading)
17. [The guided tour](#17-the-guided-tour)
18. [A working rhythm](#18-a-working-rhythm)
19. [Prompt reference](#19-prompt-reference)
20. [Where things live](#20-where-things-live)

---

## 1. Before you start

pka-skills is a Claude Code plugin with six skills:

| Skill | What it does |
|---|---|
| `pka-bootstrap` | First-run setup, the Repo Map, roles, upgrades, project lifecycle |
| `pka-librarian` | Routes dropped files, extracts text from PDFs, indexes, backfills timelines, runs health checks |
| `pka-meetings` | Files meeting notes: routes them, links attendees, extracts action items |
| `pka-wiki` | Topic pages that cite your notes |
| `pka-interface` | A single-file browser dashboard |
| `pka-tutorial` | A guided tour inside your own workspace, and the upgrade walkthrough |

The skills are prose that Claude follows. The mechanical steps (index updates, table edits, timeline lines, health checks) are done by a small bundled command, `pka-tools`, so they come out the same every time. Section 15 covers it.

### You need

- Claude Code.
- `python3` 3.9 or newer on your PATH. `pka-tools` uses the standard library only, so there is nothing to `pip install`. If Python is missing or too old, the skills stop and tell you. They do not do the tool's work by hand.
- No git. PKA never stages, commits or pushes. Keep the folder in a repository or not, as you prefer.

### Optional

- **To make PDFs searchable:** `pdfplumber` or `pypdf` (Python packages) for PDFs that contain text, `tesseract` for scans. Without them a PDF is still filed, but its contents are not searchable.
- **For a search index:** a Python whose built-in SQLite includes FTS5. The tool tells you if yours does not.
- **For the dashboard without an index:** Chrome or Edge.
- **thinkkit**, a separate plugin, for taking notes live during a meeting and for checking notes against a transcript. Without it PKA still files notes you wrote yourself. See section 8.
- **Obsidian** is not required for anything here. If `knowledge/` is an Obsidian vault, PKA works alongside it. See section 10.

### Install

In Claude Code:

```
/plugin marketplace add https://github.com/rappdw/pka-skills
/plugin install pka-skills

# optional: meeting capture and transcript reconciliation
/plugin marketplace add https://github.com/rappdw/thinkkit
/plugin install thinkkit
```

### Two ways in

```bash
# PKA mode: the whole workspace, everything in this tutorial
cd ~/pka && claude

# Project mode: one project, with its own context
cd ~/pka/projects/orion && claude
```

Start Claude Code at the workspace root and its `CLAUDE.md` makes Claude act as your orchestrator. Start it inside a project that has its own `CLAUDE.md` and that file loads instead; PKA is not active there, and project work goes on as it did before. This tutorial covers PKA mode.

---

## 2. Setting up a workspace

Open Claude Code in the folder that holds your notes and say:

*"Set up my PKA"*

Bootstrap reads what is there before it asks anything.

1. **It scans the folder**, skipping what `.pkaignore` lists. If you have no `.pkaignore`, it writes a default one first.
2. **It drafts a Repo Map**: one row per folder, saying what the folder holds and how sure the inference is.
3. **It picks a storage mode** from the number of knowledge files. Under 300, Claude reads the files directly ("markdown-only"). From 300 up, it recommends a SQLite index at `.pka/knowledge.db`. You can override either way by saying *"change storage mode"*.
4. **It asks three questions:**
   - Your first name, plus a short profile: what you do and how you like things written. This can add follow-ups, but the whole interview is never more than five questions.
   - Your autonomy level (below).
   - Whether the draft map is right. It asks specifically about rows it was unsure of, and confirms the folder where finished projects should be archived.

> **You:** Set up my PKA
>
> **Claude (pka-bootstrap):** I scanned this folder and drafted a Repo Map: 7 folders, 412 indexable files. At that size I recommend index mode, so full-text search stays fast. What's your first name?

### Autonomy levels

| Level | What it means |
|---|---|
| Ask before everything | Every file write, move and delete is confirmed first |
| Ask before destructive actions (recommended) | Creates and reads go ahead. Moves, overwrites and deletes are confirmed |
| Hands-off | It acts and reports afterwards. Press Escape to interrupt |

Some things are asked at every level, hands-off included: ingesting into a topic wiki or deleting one, approving a project summary before a project is archived, filing a meeting note into an active project, migrating the search index during an upgrade, and overwriting a `CLAUDE.md` that PKA did not write.

### What it writes

```
~/pka/
├── CLAUDE.md             instructions and the Repo Map
├── .pkaignore            what scans skip
├── team-inbox/           you drop files here
├── owner-inbox/          reports and drafts arrive here
├── .pka/
│   ├── bin/
│   │   ├── pka-tools     the helper the skills run
│   │   └── pka_tools/
│   ├── manifest.json     which release the helpers came from
│   ├── upgrade-roles.py
│   ├── roles/
│   │   ├── roster.md
│   │   ├── orchestrator.md
│   │   ├── researcher.md
│   │   ├── librarian.md
│   │   └── _obsidian.md  conventions; inert without an Obsidian vault
│   ├── owner-profile.md
│   ├── session-log.md
│   ├── decision-log.md
│   └── knowledge.db      index mode only
├── knowledge/            yours, left as it was
└── projects/             yours, left as it was
```

When bootstrap adapts to an existing structure it adds this infrastructure and does not move your content.

Two offers follow the summary. You can decline both and take them up later.

- **Pointer tables**, if you do not use Obsidian: a small `_MOC.md` per knowledge folder so filed notes get a searchable topic row. Useful once there are hundreds of notes. See section 10.
- **A weekly health check.** Bootstrap shows you a schedule entry for a quick lint every Monday. It installs nothing; installing it is yours to do. See section 14.

### If you already have a `CLAUDE.md`

Bootstrap shows you a diff and waits for your confirmation before overwriting a `CLAUDE.md` it did not write, whatever autonomy level you chose.

### `.pkaignore`

`.pkaignore` uses gitignore syntax, with one addition: a `# @pka-section: <folder>` comment starts rules that apply only inside that folder. The default file:

- always skips `.pka/`, `.git/`, Office lock files (`~$*`), `.DS_Store` and `Thumbs.db`;
- skips build output anywhere: `node_modules/`, `dist/`, `build/`, `target/`, `__pycache__/`, `_output/`, and files such as `*.map` and `*.pyc`;
- indexes knowledge folders in full;
- indexes each project one level deep. The rule is `projects/*/*/*`, so `projects/orion/alignment.md` is indexed and `projects/orion/docs/overview.md` is not;
- does not ignore transcripts, on purpose: a `.vtt` or `.srt` has to stay visible so it can be held for `pka-meetings`.

Edit it to suit your folder. Bootstrap uses your version if one exists.

### Running it again

Bootstrap runs only when you ask for it, and running it again changes nothing that is already in place.

**Try this**

- *"Set up my PKA"*
- *"What autonomy level am I on?"*

---

## 3. A session, start to finish

```bash
cd ~/pka
claude
```

At the start of a session the orchestrator:

1. reads the open threads of the last 20 session-log entries;
2. scans `team-inbox/` for new files and flags transcripts;
3. compares your top-level folders with the Repo Map and flags new ones;
4. checks project folders for 60 or more days without a file change;
5. looks at the newest health-check report. If it is at most 7 days old and still has findings, the greeting gets one line about it. No lint is run at session start;
6. greets you with what it found.

> **Claude (orchestrator):** Good morning, Sam. Two threads are open: `vendor-contract.pdf` still needs OCR, and you owe Priya the architecture comparison today. 1 new file in `team-inbox/`. Lyra has had no file changes in 67 days. Last health check (2026-11-20): 4 findings, in `owner-inbox/librarian-lint-2026-11-20.md`. What are you working on?

You did not ask for any of that. If nothing is urgent, just start.

### The session log

`.pka/session-log.md` is a work diary you never write. Each significant action adds one line with five fields: date and time, the role, a summary, open threads, and the next action. Every role writes the same form through one command, `pka-tools log add`.

```
## date time | role | summary | open threads | next action

## 2026-11-17 15:40 | pka-meetings | Filed Northwind proposal review → knowledge/leadership/2026-11-17-northwind-proposal-review.md | — | —
## 2026-11-17 15:41 | pka-meetings | Action item from 2026-11-17-northwind-proposal-review.md | Send Priya the architecture comparison — @Sam — by 2026-11-21 | —
## 2026-11-20 11:18 | librarian | Routed 2 files: 1 to leadership/, 1 to personnel/priya/ | vendor-contract.pdf needs OCR | Install tesseract
```

The fourth field holds only what is still open. Counts and results go in the summary. That is why the greeting can show things still to do:

```
$ .pka/bin/pka-tools log open
2 open thread(s) in the last 3 entries
- vendor-contract.pdf needs OCR (librarian, 2026-11-20 11:18)
- Send Priya the architecture comparison — @Sam — by 2026-11-21 (pka-meetings, 2026-11-17 15:41)
```

There is no "close" command. The greeting reads the last 20 entries, so an old thread ages out as new entries are written. For an action item the note is the truth: once its box is ticked (`- [x]`), the item is closed, even if a log entry still lists it.

### The decision log

A second file, `.pka/decision-log.md`, records decisions with their context and the alternatives considered: the storage mode chosen at setup, why a project was archived, why a role was added. It is what answers *"Why did I archive Lyra?"*

**Try this**

- *"What did I leave open last time?"*
- *"Why did I archive `<project>`?"*

---

## 4. The Repo Map

A table at the bottom of `CLAUDE.md` describes every folder. It is the first thing read when you ask where something lives.

```markdown
## Repo Map
<!-- Last updated: 2026-11-20 -->
<!-- Priority: Active | Reference | Archive -->
<!-- Status: active | archiving | archived -->
<!-- Archive destination: knowledge/archive -->

| Folder | Contents | Organization | Priority | Status | Confidence | Tags |
|--------|----------|-------------|----------|--------|------------|------|
| `knowledge/personnel/` | Notes per person: 1-1s, reviews | By person | Active | active | High | people-home |
| `knowledge/leadership/` | Meeting and strategy notes | By date | Active | active | High | meeting-home |
| `knowledge/topics/` | Topic wikis | By topic | Reference | active | High | wiki-home |
| `knowledge/research/` | Research outputs | By topic | Reference | active | Medium | |
| `knowledge/archive/` | Completed projects | By project | Archive | active | High | |
| `projects/orion/` | Orion project workspace | Flat | Active | active | High | |
| `projects/lyra/` | Lyra project workspace | Flat | Active | active | High | |
```

**Priority.** Active and Reference folders are the ones indexed and shown on the dashboard. Archive marks the folder that finished projects move into; each archived project gets its own Reference row.

**Confidence.** Low-confidence rows are the ones bootstrap asks you about before it writes the map.

**Tags** tell the skills where things go:

| Tag | Meaning |
|---|---|
| `people-home` | One subfolder per person. At most one folder has this tag |
| `meeting-home` | Dated meeting notes. `pka-meetings` routes here |
| `wiki-home` | Topic wikis, one subfolder per topic |
| `daily-home` | A journal of `YYYY-MM-DD.md` notes |

**The vault.** One folder name has a fixed meaning: `knowledge/`. PKA calls it the vault. Obsidian support, MOCs and pointer tables apply to notes inside it.

**Project workspaces.** A folder with its own `CLAUDE.md`, such as `projects/orion/`, is a project workspace: live work with its own context. PKA indexes it one level deep and never files into it without asking.

**Keeping it current.** The orchestrator maintains the table; it is marked "do not hand-edit". At the start of each session new top-level folders are flagged, and archiving a project or creating a wiki updates the row. To change it yourself, say *"Update my repo map"*.

The rest of `CLAUDE.md` records your autonomy level, communication style, storage mode, archive destination, and what to do at the start and end of a session. It is plain markdown, so another tool that accepts markdown context can read it too.

**Try this**

- *"Show me my current Repo Map"*
- *"What's in `knowledge/leadership/`?"*

---

## 5. Roles

Three roles ship with PKA. Name one with an @mention, or describe what you want and let the orchestrator route it.

| Role | What it does |
|---|---|
| `@orchestrator` | Always active. Routes requests, keeps the Repo Map, runs the session start and end, handles project lifecycle |
| `@librarian` | Takes files in: inventory, text extraction, routing, indexing, health checks. Shows a routing proposal before it moves anything, unless you chose hands-off |
| `@researcher` | Synthesizes across your notes. Says what it searched, cites sources, separates findings from inferences. Also maintains topic wikis |

> **You:** @researcher synthesize what I know about build versus buy for Orion
>
> **Claude (researcher):** I read 9 notes in `knowledge/leadership/`, `knowledge/personnel/priya/` and the top level of `projects/orion/`. The brief is in `owner-inbox/`, with Sources, Confidence and Open Questions sections. Short version: the vendor decision was deferred on 2026-11-14 and is waiting on Priya's adapter spike. I found nothing on pricing; that is an open question, not a finding.

**Roles and skills are different things.** Skills are what the plugin installs. Roles are markdown files that bootstrap writes into your folder, in `.pka/roles/`. You can read and edit them, and `roster.md` lists them. An upgrade adds new sections to those files and never rewrites a section you edited (section 16).

**Adding a role.** Say *"Add a data analyst to my team"*. The researcher writes a competency brief to `owner-inbox/research-<role>-<date>.md`, a role file is written to `.pka/roles/`, the roster gains a row, and you are shown the definition to confirm before it is final.

**Writing for you.** `.pka/owner-profile.md` holds your communication style, and roles read it. If summaries run long, say *"Update my communication style, I prefer shorter summaries"* and the profile is updated.

**Try this**

- *"Show me my role roster"*
- *"@researcher synthesize `<topic>`"*
- *"Add a `<role>` to my team"*

---

## 6. Finding what you know

This is the most-used capability. You ask a question; the orchestrator uses the Repo Map to decide where to look, searches, and answers with the paths it used.

### Five kinds of question

| You ask | What happens |
|---|---|
| *"What do I know about Priya?"* | A lookup. Works for people, topics, projects and decisions |
| *"Find everything I've written about the Northwind partnership"* | A search across everything indexed, ranked and grouped by folder |
| *"What's the state of Orion?"* | Reads the project's own `CLAUDE.md` and top-level documents |
| *"What did I decide about hiring last quarter?"* | A search scoped by date |
| *"Why did I archive Lyra?"* | Reads the decision log, which records the reasons |

> **You:** What do I know about Priya?
>
> **Claude (orchestrator):** Found `knowledge/personnel/priya/`. Her timeline has 3 entries. The latest is the SLT sync on 2026-11-14: she owns the adapter spike, and the vendor decision was deferred. Also 2 mentions in `knowledge/leadership/` and 1 in `projects/orion/`. Want a synthesis, or a specific note?

### What the role ran

In index mode a question becomes a `pka-tools search`:

```
$ .pka/bin/pka-tools search vendor decision
2 result(s) for: vendor decision
 1. knowledge/leadership/2026-11-14-slt-sync.md
      … [Vendor] [decision] and Q1 planning ## Notes **Priya**: Will take the adapter spike. The [vendor] [decision] was deferred to December. **Robin**: Will draft the Q1 …
 2. knowledge/personnel/priya/index.md
      … leadership/2026-11-14-slt-sync.md) — Owns the adapter spike; [vendor] [decision] deferred - 2026-11-10 · 1on1 · [1-1](2026-11-10-1 …
```

### What search covers

- **Knowledge folders** are indexed in full.
- **Active projects** are indexed one level deep: the project's top-level documents, not its subfolders. A project becomes fully searchable once it is archived (section 13).
- **PDFs and Office files** are searchable through a text sidecar the librarian writes beside them (`report.pdf.txt` next to `report.pdf`).
- **Pointer rows**, if you use them, rank above body matches (section 10).

### Keeping the index current

A note that a skill files is indexed as part of filing. A note you add or edit by hand is not searchable until you say *"Re-index my knowledge base"*. Re-indexing is incremental: unchanged files are skipped, changed files are re-read, and deleted files drop out.

```
$ .pka/bin/pka-tools index
Index: 10 added, 1 updated, 0 removed, 6 unchanged (0.00s)
Scope: knowledge/leadership, knowledge/personnel, knowledge/research, knowledge/topics, projects/lyra, projects/orion
Documents with no searchable text (write an OCR sidecar `<file>.txt`, then re-index) (1):
  - knowledge/topics/mcp/sources/mcp-spec.pdf
```

The last lines are worth reading: the index does not extract text from PDFs itself. It lists the documents that have none yet, and the librarian extracts it.

In a markdown-only workspace there is no index. Claude reads the files directly, guided by the Repo Map.

If a topic has a wiki, its summary is shown first (section 11).

**Try this**

- *"What do I know about `<person>`?"*
- *"Find everything I've written about `<topic>` across all my work"*
- *"Re-index my knowledge base"*

---

## 7. Dropping files in

Two folders, two directions. You drop files into `team-inbox/`. Reports, briefs and drafts come back to you in `owner-inbox/`.

```bash
cp ~/Downloads/northwind-proposal.pdf ~/pka/team-inbox/
```

A scanner profile or a phone's scan-to-folder can point straight at that folder. The next session notices the file, or you can say it now:

> **You:** Process my team-inbox
>
> **Claude (librarian):** 2 files in `team-inbox/`:
>
> - `northwind-proposal.pdf`: a PDF with a text layer. Proposed destination: `knowledge/leadership/`.
> - `GMT20261114-160512_Recording.transcript.vtt`: looks like a meeting transcript. Held. Process it with `pka-meetings`, or route it somewhere specific?
>
> Move the proposal?

### What happens to one file

1. **Inventory.** File type, whether a PDF has a text layer, date hints.
2. **Propose.** A destination from the Repo Map. Unless you chose hands-off, the librarian waits for your yes.
3. **Extract and move.** Text extracted from a PDF goes in a sidecar file beside it: `knowledge/leadership/northwind-proposal.pdf` and `knowledge/leadership/northwind-proposal.pdf.txt`.
4. **Post-route.** One `pka-tools` command does everything that follows a filing: the index entry, a line on the timeline of each person the file is about, and a row in the folder's topic table if you use them. In an Obsidian vault it also adds frontmatter and a MOC link.
5. **Log and report.** A session-log entry, and `owner-inbox/librarian-report-<date>.md` with counts, destinations and anything that needs you.

### Rules it keeps

- **Originals are never modified.** The one change it may make is to the name: `:` and `/` in a filename are replaced when the file is moved.
- **Nothing is silently skipped.** A file with no clear home goes to `team-inbox/unsorted/` and is named in the report.
- **Nothing is routed into a project workspace without asking**, and nothing is deleted from the inbox without confirmation.
- **Nothing is committed.** The moved file and everything the filing touched are left for you to review.

### Transcripts wait

A meeting transcript is recognised by its name: a Zoom `GMT…transcript.vtt`, a Teams `…_transcript.docx` or `.txt`, or any `.vtt` or `.srt`. It is held: it stays in `team-inbox/` until you reconcile it with your notes (section 8) or name a destination for it. That keeps raw transcript text out of your knowledge base until it has been checked.

### PDFs and scans

Making a PDF searchable needs a tool you install: `pdfplumber` or `pypdf` for PDFs that contain text, `tesseract` for scans. If none is there, the file is still filed, the report says its text could not be read and what to install, and it is not searchable until then.

**Try this**

- *"Process my team-inbox"*
- *"Show me what's in owner-inbox"*

---

## 8. Meetings

After a meeting, `pka-meetings` files the notes. With the optional thinkkit plugin it also takes the notes with you during the meeting and checks them against a transcript afterwards.

| Mode | You have | Needs thinkkit |
|---|---|---|
| Capture | A meeting about to start | Yes (`take-notes`) |
| Reconcile | Notes and a transcript | Yes (`resolve-against-transcript`) |
| Route only | Notes you already wrote | No |

Without thinkkit you still get everything under "Filing the note" below. PKA says which modes are unavailable and carries on; a transcript stays held in `team-inbox/`.

### Capture live

*"I'm about to start a 1-1 with Priya"*, or just *"take notes"*.

PKA asks what the meeting is and who is attending, then starts thinkkit's `take-notes`. It creates `meeting-notes/YYYY-MM-DD-<title>.md` at the workspace root. You type fragments:

```
priya: taking the adapter spike
vendor decision deferred to december
robin: drafts q1 hiring plan
which vendors make the shortlist? not settled
```

Each fragment is expanded into a sentence or two and appended to the file at once. Start a line with `name:` to attribute it; without that it is recorded as an observation, and a speaker is never guessed. A commitment is added under Action Items. A question left unanswered goes under Open Questions. Say *"end notes"* or *"done"* to finish.

What the file holds then:

```markdown
# SLT sync

**Date**: 2026-11-14
**Attendees**: Priya, Robin Smith, Sam
**Purpose**: Vendor decision and Q1 planning

## Notes

**Priya**: Will take the adapter spike.

The vendor decision was deferred to December.

**Robin**: Will draft the Q1 hiring plan.

## Action Items

- [ ] **Priya**: Run the adapter spike
- [ ] **Robin**: Draft the Q1 hiring plan

## Open Questions

- Which vendors make the shortlist was not settled.
```

The structure is thinkkit's own: the header lines, the three sections, and action items as `- [ ] **Owner**: …`. The wording of the expanded sentences is illustrative.

### Reconcile against a transcript

Use this when the meeting was recorded. Drop the transcript in `team-inbox/` and ask:

*"Reconcile my SLT sync notes against the transcript in team-inbox"*

The transcript is treated as the truth, and the notes are what get corrected. thinkkit's `resolve-against-transcript` shows one discrepancy at a time: a statement that contradicts what was said, a paraphrase that shifts the meaning, a wrong speaker, a decision or a commitment missing from the notes. You answer accept, modify or skip, and an accepted change is written immediately.

> **Claude (resolve-against-transcript):** **Discrepancy 1 of 2** | Missing action items
>
> **Transcript excerpt:** Robin Smith: I'll also get the interview panel list to Priya by the twentieth.
>
> **Notes (current):** [not present]
>
> **Proposed resolution:** `- [ ] **Robin**: Send Priya the interview panel list (due: 2026-11-20)`
>
> Accept, modify, or skip?

If you have a transcript and no notes, PKA offers to generate notes from the transcript.

Reconcile before filing. Capture and reconciliation both work on the note while it is still in `meeting-notes/`.

### If you record with earshot

earshot is a separate, local recording and transcription tool. It writes each meeting into a capture directory (audio, transcripts, sometimes a `narrative.md`) marked by a `meeting.json` file, usually under `meeting-notes/`. PKA's rules for those directories:

- A capture directory is never routed, moved, renamed or deleted. Only the notes file is filed.
- `take-notes` links the notes to the recording with a `**Recording**:` line. That line is kept exactly as written when the note is filed, and it stays valid because the directory does not move.
- A capture with a `transcript.md` and no reconciled note is flagged at session start, like a transcript in `team-inbox/`, and the reconcile step reads it in place.
- If the capture has a `narrative.md`, it is indexed where it is.
- Lint and the timeline backfill leave capture directories alone.

### Filing the note

However the notes were written, the same things happen. For a note you wrote yourself, say *"File these meeting notes: `<path>`"*.

1. **Route.** A 1-1 goes to that person's folder, if they have one. A leadership or general meeting goes to a `meeting-home` folder; with several, or none, you are asked. A meeting about an active project always gets a question, at every autonomy level: file it in the project, or in knowledge?
2. **Link attendees.** Each name is checked against your people folders with `pka-tools people resolve`. A certain match is linked under `## Attendees`. An ambiguous one is asked about. No match is listed without a link.
3. **Extract action items** and ask: "Found N action items. Add to session log open threads?" On a yes they appear in the next session's greeting.
4. **Save.** The note is saved in the destination as `YYYY-MM-DD-meeting-slug.md`. A 1-1 is `YYYY-MM-DD-1-1-<person>.md`. Existing 1-1 notes named another way are recognised as they are and never renamed.
5. **Post-route.** The step every filed note gets (section 7), including a line on each attendee's timeline with a summary written from the note.
6. **Log and report** the path, attendees linked (N of M), action items, and what happened to the transcript.

The post-route step, as the tool reports it in Sam's workspace (no Obsidian, pointer tables opted in):

```
$ .pka/bin/pka-tools post-route knowledge/leadership/2026-11-14-slt-sync.md \
    --topic northwind-partnership-2026 \
    --summary-for priya="Owns the adapter spike; vendor decision deferred" \
    --summary-for robin-smith="Drafts the Q1 hiring plan"
post-route knowledge/leadership/2026-11-14-slt-sync.md
  frontmatter  not-applicable — not an Obsidian vault
  moc-link     not-applicable — not an Obsidian vault
  pointers     written — knowledge/leadership/_MOC.md: extended
  timeline     written — priya: added; robin-smith: added
  index        indexed — 4 added, 0 updated
Files changed besides the note: knowledge/leadership/_MOC.md, knowledge/personnel/priya/index.md, knowledge/personnel/robin-smith/index.md
```

A step that cannot do its work says why and the later steps still run. Running it twice changes nothing.

### The transcript afterwards

You choose: keep it in `team-inbox/`, archive it beside the note, or delete it after confirming. It is never deleted automatically.

### Action items later

*"What action items do I have this week?"* scans the dated notes in your meeting folders and people folders for unticked `- [ ]` boxes. It goes by the date in the filename (by default the last 7 days) and lists each item with its source file. Checkboxes inside code blocks are not picked up.

```
$ .pka/bin/pka-tools actions
4 open action item(s), since 2026-11-13, in 3 note(s) under: knowledge/leadership, knowledge/personnel
- [ ] **Priya**: Run the adapter spike
      knowledge/leadership/2026-11-14-slt-sync.md:17
- [ ] **Robin**: Draft the Q1 hiring plan
      knowledge/leadership/2026-11-14-slt-sync.md:18
- [ ] **Robin**: Send Priya the interview panel list (due: 2026-11-20)
      knowledge/leadership/2026-11-14-slt-sync.md:19
- [ ] Send Priya the architecture comparison — @Sam — by 2026-11-21
      knowledge/leadership/2026-11-17-northwind-proposal-review.md:5
```

An owner is read from `@name` and a due date from `by YYYY-MM-DD`, as in the last item. Items captured by thinkkit use a different form (`**Owner**: … (due: date)`). In v1.10.0 they are listed as written, but an owner or due date is not read from them. Tick the box in the note to close an item.

**Try this**

- *"I'm about to start a 1-1 with `<name>`"* (with thinkkit)
- *"File these meeting notes: `<path>`"*
- *"What action items do I have this week?"*

---

## 9. People and timelines

A person you keep a folder for has a page, `index.md`. Filing a note that involves them adds one line to the `## Timeline` on that page, newest first.

```markdown
---
type: person
name: Priya
---
# Priya

## Timeline
<!-- pka:timeline v1 — maintained by pka-tools; newest first; edit summaries freely, leave links alone -->
- 2026-11-14 · meeting · [SLT sync](../../leadership/2026-11-14-slt-sync.md) — Owns the adapter spike; vendor decision deferred
- 2026-11-10 · 1on1 · [1-1](2026-11-10-1-1-priya.md)
- 2026-10-02 · doc · [Orion kickoff](../../../projects/orion/2026-10-02-orion-kickoff.md)
<!-- /pka:timeline -->
```

The top line was written when the meeting note was filed, with a summary. The two below were added by a backfill of older notes, which adds no summaries.

**Line format.** `- date · kind · link — summary`. Kind is `meeting`, `1on1` or `doc`. A summary is at most 140 characters: the decisions, and what that person owns. For a 1-1 it lists topics only. You can edit a summary freely. A line you edited is never rewritten, except to follow a note that was renamed.

**Links.** Without Obsidian they are relative markdown links, as above. In an Obsidian vault they are wikilinks.

### Who counts as a person

Someone you have a folder for, under the folder tagged `people-home` (`knowledge/personnel/` if none is tagged). PKA does not create person folders unasked: make one, or ask for it. Inside an existing person folder, a missing `index.md` is created the first time a line is added.

An attendee without a folder is listed in the note without a link and gets no timeline. With no people folder at all, nothing in this section happens.

### Who goes on a note's timeline

Evidence in the note decides, never a guess:

- the note is in the person's folder;
- its `person` or `attendees` frontmatter (the fields between `---` lines at the top of a note), or a link under `## Attendees`, names them;
- their folder name appears in the filename.

A name that appears only in the body does not count. A meeting with more than 8 matched attendees adds none of them unless you ask. `no-backref: true` in a note's frontmatter keeps it off every timeline.

You can ask the tool why:

```
$ .pka/bin/pka-tools timeline who knowledge/leadership/2026-11-14-slt-sync.md
knowledge/leadership/2026-11-14-slt-sync.md belongs to: priya, robin-smith
  priya: T2: ## Attendees link '[Priya](../personnel/priya/)'
  robin-smith: T2: ## Attendees link '[Robin Smith](../personnel/robin-smith/)'
```

### Names are matched carefully

A full name, a saved alias, or a first name only one person has is a match. A last name alone, or a first name two people share, gets a question. Nicknames are never guessed: tell PKA once and it is saved as an alias.

```
$ .pka/bin/pka-tools people resolve "Priya" "Rob" "Smith"
Priya -> priya (slug, name or alias)
Rob -> no match (no person folder matches)
Smith -> AMBIGUOUS: robin-smith (last name only)

# you say: "Rob is Robin Smith"
$ .pka/bin/pka-tools people alias robin-smith "Rob"
robin-smith: added 'Rob'
```

In conversation: *"From now on, 'Rob' means Robin Smith."*

### Backfill: putting older notes on timelines

Timelines start empty and fill in as you file new notes. The backfill puts the notes you already had on them. It plans first, applies only when you approve, and can be undone with one command.

1. **Plan.** Say *"Backfill the timelines from my old notes"*. The librarian works out whose timeline each dated note belongs on, by the same evidence rules as a newly filed note. A link in an old "Mentioned in", "Related meetings" or "References" section on a person's own page also counts. It writes a report to `owner-inbox/timeline-backfill-plan-<date>.md` and a plan file under `.pka/backfill/`. Nothing else changes.
2. **Settle names.** The report lists what it could not place: ambiguous names, frequent names with no person folder, notes with no date, large meetings. You confirm an alias or leave it, then it plans again. Planning is cheap.
3. **Apply.** Only when you approve. Every page it will touch is backed up to `.pka/backups/` first. It adds only lines for notes not already on the timeline, then checks that every link resolves and that nothing else changed. If a check fails, the pages are put back.
4. **Undo** if you want to. The apply prints the restore command. It refuses to overwrite a page you edited after the backfill unless you force it.

```
$ .pka/bin/pka-tools timeline apply .pka/backfill/plan-<id>.json
Added 2 line(s) to 1 file(s); verified. Backup: .pka/backups/20261120-135744-949bac
Nothing was committed: review the changed pages and commit them yourself.
Undo:   pka-tools timeline restore 20261120-135744-949bac
```

Your notes are never changed; only the people's `index.md` pages are. Backfilled lines have no summaries. Ask for them one person at a time.

**How much it will find.** For notes written before PKA, the evidence is mostly notes inside a person's folder or with their name in the filename. A short plan is not a failure. A note with no date in its filename or frontmatter is reported, never dated from when the file was last modified.

**Notes you write by hand** are not on a timeline until a skill files them or the next backfill picks them up. A full health check tells you how many are waiting (section 14).

### How far a timeline reaches

Without Obsidian, a timeline can link to a note anywhere in the workspace, such as `projects/` or a meeting folder at the root. The inboxes and hidden folders are left out. In an Obsidian vault, timelines link only inside the vault (`knowledge/`), because a wikilink cannot leave it. Nothing is moved to make a note reachable; the person page links to the note where it is.

**Try this**

- *"File a 1-1 note for `<person>`"*, then open their `index.md` and look at the Timeline
- *"From now on, '`<nickname>`' means `<person>`"*
- *"Backfill the timelines from my old notes"*

---

## 10. MOCs, the pointer layer and Obsidian

A `_MOC.md` is a map of content for one knowledge folder. Its `## Pointers` table groups files into topics, so a search can land on the topic first and read only the few files in it.

```markdown
# leadership

<!-- MOC stub created by pka-tools. Reorganise freely. -->

## Pointers

Compact retrieval rows maintained by the librarian. Format: one row per concept cluster. FTS-indexed for fast lookup before expanding to file bodies.

| Topic | Entities | Files |
|---|---|---|
| orion-build-vs-buy | orion, priya | [[leadership/2026-09-18-orion-build-vs-buy]], [[leadership/2026-08-01-offsite]] |
| northwind-partnership-2026 | northwind | [[leadership/northwind-proposal.pdf]], [[leadership/2026-11-14-slt-sync]], [[leadership/2026-11-17-northwind-proposal-review]] |
```

The second link in the first row points at a note Sam later deleted. The librarian does not remove pointer links by itself; the health check in section 14 reports it.

### Why, and when

In a large folder, searching note bodies returns a lot of noise. A pointer row is dense with the right words, and in index mode it is ranked above body matches. A question over 1,500 files becomes a look at a few dozen topic rows, then three to five files read in full. There is no vector store and there are no embeddings. It is a markdown table.

It starts to pay off once you have hundreds of notes. In a small workspace you can skip it.

### How rows are kept

- One row per topic, three columns: a topic slug, the entities involved, links to the files.
- The librarian adds to the table as files are routed. It names the topic when it can see which one a file belongs to. Otherwise the tool derives one from the note's frontmatter, tags or filename; it never reads the body for this.
- Rows are extended, never deleted, reordered or merged. Your edits to a row are kept as you wrote them.
- A row that reaches 8 files is reported. Splitting it is your call.

### Without Obsidian: opt-in

- Filing a note never creates a `_MOC.md`.
- Rows are written only into MOCs that already exist.
- To get them, say *"Set up pointer tables for my knowledge folders"*. That creates a `_MOC.md` with a title and an empty table per folder (`pka-tools pointers init`).
- Notes get no frontmatter and no MOC bullet. Links between notes are plain markdown.

### With Obsidian: on by default

PKA looks for `knowledge/.obsidian/`. The vault has to be the `knowledge/` folder; a vault at the workspace root or elsewhere is not detected.

In a vault, the roles enhance the files they touch:

- A missing `_MOC.md` is created when a note is filed.
- Filed notes get missing frontmatter keys and a bullet under `## Files` in the MOC. Existing frontmatter fields are never overwritten.
- Links inside the vault are wikilinks, and so are timeline links.

Frontmatter added to a 1-1 note in a vault:

```markdown
---
type: 1on1
date: 2026-11-10
person: "[[personnel/priya/index]]"
tags: [1on1, personnel]
---
```

*"bootstrap obsidian"* is an optional one-time retrofit of an existing vault: MOC stubs, person indexes, and frontmatter derived from filenames and folders. It does not read note bodies, it never edits an existing `_MOC.md` or person `index.md`, it skips and lists any note whose frontmatter it cannot read safely, and it runs only when you ask. Nothing is committed, so in a repository you can review the diff first.

**Try this**

- *"Set up pointer tables for my knowledge folders"* (without Obsidian)
- *"bootstrap obsidian"* (with a vault at `knowledge/`)

---

## 11. Topic wikis

A topic wiki is a maintained summary of what you know about one subject. It cites your notes. It never replaces them.

PKA holds two kinds of content apart:

- **Authored moments**: your meeting notes, 1-1s, drafts, journal. Records of a specific moment, in your voice.
- **Synthesis pages**: topic wikis, kept by the researcher, that change as your understanding does.

Wikis cite moments. Moments never cite wikis. Delete a wiki and you lose no underlying content.

**When to make one.** When material on a subject is piling up and you want a maintained picture of it. Not for a one-off question, a person or a project; those have their own homes.

**Creating one.** *"Create a topic wiki on MCP"* writes an empty scaffold at `knowledge/topics/mcp/wiki.md` and asks for a first source.

```markdown
---
topic: mcp
last-updated: 2026-11-18
source-count: 2
status: active
---

# MCP

## What it is
MCP supports resource, tool, and prompt primitives.[^spec]

## Key concepts

## My current thinking

## Open questions
- Build the adapter or buy one? Waiting on Priya's spike.

## Sources
- `knowledge/topics/mcp/sources/mcp-spec.pdf` — the primitives
- `knowledge/personnel/priya/2026-11-10-1-1-priya.md` — the adapter question

## Changelog
- 2026-11-18: Added the adapter question (source: knowledge/personnel/priya/2026-11-10-1-1-priya.md)
- 2026-11-12: Initial synthesis from 1 source

[^spec]: `knowledge/topics/mcp/sources/mcp-spec.pdf`
```

**Ingest is always reviewed.** A wiki changes only when you ingest something. Say *"Ingest this paper into my MCP wiki"*. The researcher reads the source and the current page, sorts what it found into new claims, confirmations, contradictions and refinements, and shows you a section-by-section diff:

```
## Key concepts

- [UNCHANGED] MCP supports resource, tool, and prompt primitives...
+ [ADD] Clients negotiate capabilities at connection time, not per-request [source: new]
- [REFINE] Previously: "Servers expose tools." → "Servers expose tools, resources, and prompts as distinct primitives." [source: new]
```

Nothing is written until you approve, even in hands-off mode. A contradiction is yours to resolve. A PDF source needs its text sidecar first. A source ingested from `team-inbox/` moves to the wiki's `sources/` folder.

**Asking changes.** Once a wiki exists, *"What do I know about MCP?"* returns the wiki's summary first, then notes that mention the topic and are not in it yet.

**Also.** *"Show me my topic wikis"* lists them. *"Update my thinking on MCP"* edits the "My current thinking" section from what you say. A wiki you are done with can be retired (kept, but left out of answers) or deleted, which always asks first.

**Try this**

- *"Create a topic wiki on `<topic>`"*
- *"Ingest `<path>` into my `<topic>` wiki"*

---

## 12. The dashboard

*"Generate my dashboard"* writes a single HTML file, `dashboard.html`, at the root of your workspace. Open it in a browser. No server is set up and there is no build step.

```bash
open dashboard.html        # macOS
xdg-open dashboard.html    # Linux
```

Sections are generated from the Active and Reference folders in your Repo Map. Each folder gets the view that suits its content:

| Folder holds | View |
|---|---|
| Per-person notes | Card per person, most recent first |
| Meeting notes (`meeting-home`) | Timeline by date in the filename |
| Research outputs | Topic list with linked files |
| Journal or lab notes | Calendar heatmap and entry list |
| Project workspaces | Card with status and days since activity |
| Anything else | File table with search |

Two sections are always there: **Activity**, the last 20 session-log entries, and **Search**.

### Two ways it reads your data

- **With an index**, the page is built to read `.pka/knowledge.db` in the browser for full-text search. To do that it loads the sql.js library from a public CDN, so opening it makes a network request for that script.
- **Without an index**, it needs Chrome or Edge, and asks you to pick the workspace folder when it opens. Search covers file and folder names, with a slower "deep search" for contents.

If the page cannot load the index, which a browser may refuse for a page opened from disk, it works the second way.

### Keeping it useful

Ask for an update after structural changes, such as a new folder in the Repo Map: *"Update the dashboard"*, or *"Add a timeline view for `<folder>`"*. The skill edits the existing file in place and keeps your customizations.

File links are absolute paths on your disk. A dashboard generated in one location has dead links if the workspace moves or is opened on another machine; regenerate it there.

**Try this**

- *"Generate my dashboard"*
- *"Add a timeline view for `<folder>`"*

---

## 13. Project lifecycle

A project folder is a workspace while the work is live. When it is done, a transition moves it into your knowledge base, with a summary, so it turns up in later searches.

**Why archive.** An active project is indexed one level deep. After the transition the whole folder is indexed, so a search six months later finds its documents next to everything else.

**Noticing.** At the start of a session, the orchestrator flags project folders with no file changes in 60 days or more. It only tells you. Nothing is moved.

> **You:** What projects are winding down?
>
> **Claude (orchestrator):** Lyra has had no file changes in 67 days. Transition it to knowledge, or leave it?
>
> **You:** Transition Lyra to knowledge
>
> **Claude (orchestrator):** Draft summary saved to `owner-inbox/lyra-summary-draft.md`. Review it and tell me when it is approved; I will not move anything before that.

### The transition

1. **Summary.** A draft is written to `owner-inbox/<project>-summary-draft.md`: what it was, key decisions, outcomes, documents worth reading, related knowledge.
2. **Pause.** It waits for your approval, whatever your autonomy level.
3. **Cleanup.** Build leftovers (what `.pkaignore` matches) are listed. You confirm before they are deleted.
4. **Move.** The folder goes to your archive destination, here `knowledge/archive/lyra/`. Wikilinks that pointed at the old location are rewritten. Anything else that still names the old path, such as relative markdown links or mentions in `CLAUDE.md`, is shown to you to fix. The approved summary is copied into the moved folder as `project-summary.md`.
5. **Re-index and update the map.** Status becomes `archived`, priority `Reference`.

If the project folder is its own git repository, the move stops and asks first. What happens to that history is your decision. Nothing is committed for you at any step.

```markdown
# Lyra — Project Summary
**Period:** Jan 2026 – Sep 2026
**Transitioned:** 2026-11-20

## What It Was
## Key Decisions
## Outcomes
## Documents Worth Reading
## Related Knowledge
- `knowledge/personnel/robin-smith/` — primary stakeholder notes
```

**Not ready to move it?** *"Archive Lyra"* marks it `archiving` in the Repo Map for a later transition.

**Changing your mind.** *"Restore Lyra to active"* moves it back, and its links follow.

### Meetings about a live project

When `pka-meetings` sees that a meeting is about an active project, it asks where the note should go: into the project now, or into knowledge. A 1-1 where the project is one topic among several usually belongs in knowledge.

**Try this**

- *"What projects are winding down?"*
- *"Transition `<project>` to knowledge"*

---

## 14. Health checks

Any knowledge base drifts: files move, links rot, the same note is saved twice, a wiki falls behind newer notes. A health check, also called lint, finds these and writes a report. It never edits, moves or deletes anything. You decide what to do about each finding.

Since v1.10.0 most of lint is done by `pka-tools lint`, with no model and no network. It gives the same result every run and takes seconds.

*"Run a health check"*

### What it looks for

| Rule | Finds | In a quick lint |
|---|---|---|
| 1. Left in the unsorted inbox | Things in `team-inbox/unsorted/` not changed for more than 14 days | yes |
| 2. Broken links | A `[[wikilink]]` or relative markdown link whose file is not there, including links in pointer rows | yes |
| 3. Stale wiki sources | A path in a wiki's `## Sources` list that no longer exists | yes |
| 4. Empty Repo Map folders | A Repo Map row whose folder is missing or holds no documents | yes |
| 5. Notes not on a timeline | Dated notes that belong on someone's timeline and are not on it. One informational line, not a finding | no |
| 6. Contradiction candidates | A wiki not updated for 30 days, with 3 or more newer notes on its topic that it does not cite | no |
| 7. Uncited wiki claims | Wiki paragraphs with no citation | no |
| 8a. Identical files | Files that are byte for byte the same, of any type | yes |
| 8b. The same text | The same text once frontmatter, upper and lower case and spacing are set aside | yes |
| 8c. Near-copies | Notes of 200 words or more that are at least 80% alike, or where one holds at least 90% of the other. Often raw notes beside a reconciled version, or a `-2` copy | no |
| 8d. Duplicate people and topics | Two person folders that answer to the same name, or where one folder name is contained in the other; two wikis with the same topic; one topic on two rows of the same pointer table | no |

Rules 6 and 7 need judgement, so the librarian works them out in a session and appends them to the report the tool wrote. Everything else is the tool's.

### Quick and full

- **Quick** (*"quick lint"*): rules 1 to 4, 8a and 8b. About a second for a few thousand notes.
- **Full** (the default): everything. A few seconds, plus the time the two wiki rules take.

```
$ .pka/bin/pka-tools lint --quick
Lint (quick): 4 finding(s), 0 informational, 0 suppressed; 20 files scanned
  rule 2  Broken links                         2 findings
  rule 4  Empty Repo Map folders               1 finding
  rule 8a Byte-identical files                 1 finding
Report: owner-inbox/librarian-lint-2026-11-20.md
Nothing was changed. Rules 6 and 7 are the librarian's to add.

$ .pka/bin/pka-tools lint
Lint (full): 5 finding(s), 1 informational, 0 suppressed; 20 files scanned
  rule 2  Broken links                         2 findings
  rule 4  Empty Repo Map folders               1 finding
  rule 5  Notes not on a person's timeline     1 informational
  rule 8a Byte-identical files                 1 finding
  rule 8c Near-duplicates and contained notes  1 finding
Report: owner-inbox/librarian-lint-2026-11-20.md
Nothing was changed. Rules 6 and 7 are the librarian's to add.
```

The full lint found one thing the quick one could not: a near-copy. A quick lint run later the same day does not replace a full report; it prints its results and leaves the report as it is.

### Reading the report

The report lands in `owner-inbox/librarian-lint-<date>.md`: counts at the top, then one section per rule with a hint about what to do. Every finding ends with an id. This is the full report from Sam's workspace, shortened where marked:

```markdown
# Knowledge Base Health — 2026-11-20

Written by `pka-tools lint`. Nothing was changed: lint reports, you decide.

- Scanned: 20 files (17 markdown)
- Checks run: rule 1, rule 2, rule 3, rule 4, rule 5, rule 8a, rule 8b, rule 8c, rule 8d
- Findings: 5
- Informational: 1
- Suppressed: 0

## 2. Broken links (2 findings)

Fix or remove these references. The librarian does not remove pointer-row links by itself.

- `knowledge/leadership/2026-09-18-orion-build-vs-buy.md:4` → `../research/orion-costs.md` (missing) [id: 2-db1720de]
- `knowledge/leadership/_MOC.md:11` → `[[leadership/2026-08-01-offsite]]` (missing; in the Pointers row for topic 'orion-build-vs-buy') [id: 2-4b4dd24f]

## 4. Empty Repo Map folders (1 finding)

Remove the row from the Repo Map, or archive the folder.

- `knowledge/archive/` — nothing indexable in it [id: 4-e29a9656]

## 5. Notes not on a person's timeline (1 informational)

Ask the librarian to "backfill timelines". It plans first and writes nothing until you approve. […]

- Information: 1 note (1 timeline line) across 1 person are not on the timeline of someone they involve [id: 5-timelines, information]
  - `knowledge/personnel/priya/2026-11-19-1-1-priya.md` → priya

## 8a. Byte-identical files (1 finding)

Keep one copy and delete or move the others yourself; links to a removed copy will then show as broken.

### 2 files, byte for byte the same: `knowledge/research/vendor-landscape/research.md`, `projects/orion/vendor-landscape.md` [id: 8a-130ebf71]

| File | Size | Modified | Links to it | Compared with the keeper |
|---|---|---|---|---|
| `knowledge/research/vendor-landscape/research.md` | 283 B | 2026-11-20 | 0 | suggested keeper |
| `projects/orion/vendor-landscape.md` | 283 B | 2026-11-20 | 0 | identical bytes |

## 8c. Near-duplicates and contained notes (1 finding)

Often raw notes beside a reconciled version, or a `-2` copy. Keep the fuller one, or suppress the group.

### 2 files, up to 92% alike: `knowledge/leadership/2026-11-17-northwind-proposal-review-2.md`, `knowledge/leadership/2026-11-17-northwind-proposal-review.md` [id: 8c-c13af50b]

| File | Size | Modified | Links to it | Compared with the keeper |
|---|---|---|---|---|
| `knowledge/leadership/2026-11-17-northwind-proposal-review-2.md` | 1.7 KB | 2026-11-20 | 0 | near copy |
| `knowledge/leadership/2026-11-17-northwind-proposal-review.md` | 1.5 KB | 2026-11-20 | 1 | suggested keeper |

## Librarian checks (rules 6 and 7)

<!-- librarian:rules-6-7 -->
Not run by the tool: […]
```

What each of these is, in Sam's workspace:

- **The broken links.** A note links to a cost sheet that was never filed, and a pointer row still lists an offsite note that was deleted.
- **The empty folder.** `knowledge/archive/` is in the Repo Map and nothing has been archived yet.
- **The timeline line.** Sam wrote a 1-1 note by hand on the 19th, after the backfill. It is information, not a finding, and it cannot be hidden. It goes away at the next backfill.
- **The identical files.** The research brief was copied into the Orion project.
- **The near-copy.** The proposal review was filed twice, the second time with a paragraph added.

### How duplicates are reported

One set of copies is one finding, filed under the broadest rule that holds for it. If a note has an identical copy and a near copy, that is a single 8c finding listing all three files.

Each set is a table: path, size, last-modified date, how many files link to each copy, and how each compares with the **suggested keeper**. The keeper is the file with the most links to it, then one that is not in an inbox, then the oldest. It is a starting point. In the near-copy above the suggestion is the shorter original, because a pointer row links to it; the fuller note is the `-2` file. You decide.

Not reported as duplicates: a PDF's text sidecar beside its source, anything in an earshot capture directory, `_MOC.md` files, the same topic in two different MOCs, anything `.pkaignore` matches, and very short notes (two files holding only the same headings). A copy in a wiki's `sources/` folder of a file filed elsewhere is listed once as information.

Two limits. Near-copy detection compares text, not meaning: a note rewritten in other words is not found. And it compares five-word passages, so it does not work on text written without spaces between words; exact and re-saved copies of such notes are still found.

### Acting on a finding

Lint fixes nothing, and neither does the librarian unless you ask, one finding at a time.

- **A duplicate.** *"Keep the `-2` note and delete the other."* The librarian confirms which copy stays, deletes or moves the others on your yes, and rewrites links to the removed copy so they point at the keeper.
- **Duplicate people.** Merging two person folders is your decision. If they are two different people, hide the finding.
- **A broken link.** Fix the link in the note. A link in a pointer row is edited only when you ask for that row to be fixed.

### When a finding is fine as it is

Orion keeps its own copy of the research brief on purpose. Say so:

*"That duplicate is on purpose, hide it"*

The librarian records it with your reason:

```
$ .pka/bin/pka-tools lint suppress 8a-130ebf71 --reason "Orion keeps its own copy of the brief"
Suppressed: 8a-130ebf71
  2 files, byte for byte the same: `knowledge/research/vendor-landscape/research.md`, `projects/orion/vendor-landscape.md`

$ .pka/bin/pka-tools lint suppressions
1 suppressed finding(s) in .pka/lint-suppressions.json
- 8a-130ebf71  2 files, byte for byte the same: `knowledge/research/vendor-landscape/research.md`, `projects/orion/vendor-landscape.md`  — Orion keeps its own copy of the brief

$ .pka/bin/pka-tools lint
Lint (full): 4 finding(s), 1 informational, 1 suppressed; 20 files scanned
  …
```

- The id can come from any report of the last 30 days. An id that no report has is refused.
- An id belongs to the exact files or link it names. If a set of duplicates gains or loses a file, it is a new finding with a new id.
- *"What have I hidden from lint?"* lists them. `lint unsuppress <id>` brings one back.
- Suppressions live in `.pka/lint-suppressions.json`.

### Running it every week

Because lint needs no model, it can run unattended. Ask *"Show me the weekly lint schedule"*, and the librarian shows what `pka-tools lint schedule` prints:

```
$ .pka/bin/pka-tools lint schedule
Nothing was installed. To run a quick lint every Monday at 09:00, install ONE of these yourself.

Output goes to .pka/lint-cron-log.txt, so a run that fails leaves a trace.

cron (run `crontab -e` and add this line):

0 9 * * 1 /usr/bin/env python3 '/home/sam/pka/.pka/bin/pka-tools' lint --quick --workspace '/home/sam/pka' >> '/home/sam/pka/.pka/lint-cron-log.txt' 2>&1

launchd on macOS (save as ~/Library/LaunchAgents/org.pka-skills.lint.pka-<hash>.plist, then `launchctl load` that file):

<?xml version="1.0" encoding="UTF-8"?>
…
```

It prints a cron line and a launchd file. It installs neither, and no skill will: adding the entry is yours to do, and you can ignore it. A scheduled run is a quick lint, so it does not include near-copies, duplicate people or the two wiki rules.

When the newest report is at most 7 days old and has open findings, the next session's greeting mentions it once (section 3). Findings you have hidden since are not counted.

### When to run it

On demand, after a large import or a reorganization, and weekly if you installed the schedule. Not every session.

**Try this**

- *"Run a health check"*
- *"Find duplicate notes"*
- *"That finding is fine, hide it"*
- *"Show me the weekly lint schedule"*

---

## 15. `pka-tools`, and why PKA never commits

### The mechanical half

The skills decide what a note is about and where it belongs. `pka-tools` makes the edit, the same way every time. You will rarely type a command yourself; the roles run it.

- Python 3.9 or newer, standard library only.
- No network calls.
- No git.
- A copy lives in your workspace at `.pka/bin/pka-tools`, so a workspace keeps working with the release it was set up on until you upgrade it.

```
$ .pka/bin/pka-tools status
Workspace:        ~/pka
pka-tools:        1.10.0 (vendored: 1.10.0)
Vault:            knowledge
Obsidian:         not present
Timelines reach:  .
Storage:          index, schema version 1
Index roots:      knowledge/leadership, knowledge/personnel, knowledge/research, knowledge/topics, projects/lyra, projects/orion
Meeting homes:    knowledge/leadership
People home:      knowledge/personnel
```

| When you | The tool |
|---|---|
| file any note | `post-route`: frontmatter and MOC link (Obsidian), pointer row, timeline, index |
| ask a question | `search`: full-text search, pointer rows first |
| re-index | `index`: new and changed files in, removed files out |
| name an attendee | `people resolve` and `people alias` |
| ask what is open | `actions`: unchecked boxes in dated notes; `log open`: open threads |
| move a project | `pointers rename`: links follow the folder |
| backfill timelines | `timeline plan`, `apply`, `restore` |
| run a health check | `lint`, `lint suppress`, `lint schedule` |
| upgrade | `install` and `db migrate`, with backups |

Every command, exit code and rule is in [`bootstrap-assets/tools/README.md`](../bootstrap-assets/tools/README.md).

### How it edits your files

- **Only the lines it owns.** A pointer row, a `tags:` line, a line it inserts. Everything else stays byte for byte, line endings included.
- **Never re-renders.** Frontmatter is not parsed and written back; tables are not rebuilt or sorted.
- **When unsure, it skips and reports.** Malformed frontmatter, a read-only file or an unexpected table is left alone and named.
- **Safe to repeat.** Running a command twice changes nothing the second time.
- **Whole writes.** A file is written to a temporary name and renamed into place.
- **Its own reports never go through a link.** If a lint report's path is a symbolic link, lint stops with one line and writes nothing.

### PKA never commits

No skill, role or tool stages, commits or pushes, in any repository. Filing a note changes files in your workspace. Committing them is yours to do, in one ordinary repository or none.

- After a note is filed, the note and every file the filing touched are left in the working tree. The report names them.
- An upgrade, a backfill, an Obsidian retrofit and a project transition end the same way: changes to review, nothing committed.
- A project folder that is its own repository is never moved without asking you first.

```
$ git status --short
 M knowledge/leadership/_MOC.md
 M knowledge/personnel/priya/index.md
 M knowledge/personnel/robin-smith/index.md
?? knowledge/leadership/2026-11-14-slt-sync.md
```

That is you, in your own terminal, after the SLT sync was filed.

Releases v1.6.0 to v1.7.0 could set a workspace up with nested repositories and commit into them after each filed note. That was removed in v1.8.0. If your workspace has that layout, section 16 says what changes for you.

---

## 16. Upgrading

Updating the plugin does not change your workspace. Its copy of `pka-tools` and its role files stay on the release that set them up until you ask.

**Two steps.** First update the plugin: in Claude Code, `/plugin`, then update `pka-skills`. Then, in the workspace, say:

*"bootstrap upgrade"*

### A preview first

If you would rather look before anything changes, ask *"Do I need to upgrade?"* The tutorial compares your workspace with the installed release, shows a preview that changes no file, explains each step, and hands over to `pka-bootstrap` when you say so.

This is the preview for a workspace last set up before v1.7.0:

```
$ python3 "<plugin root>/bootstrap-assets/tools/pka-tools" install --workspace ~/pka --dry-run
pka-tools install (dry run) — plugin version 1.10.0
  installed: 23   updated: 1   current: 0   kept: 0   conflicts: 0
Installed (23):
  - bin/pka-tools
  - bin/pka_tools/__init__.py
  …
Updated (1):
  - upgrade-roles.py (previous copy saved)
```

| In the preview | Means |
|---|---|
| Installed | New files that will appear under `.pka/` |
| Updated, "previous copy saved" | Before v1.7.0 the tool cannot tell whether you edited a helper, so it replaces it and saves the old one under `.pka/upgrade-backups/` |
| Updated | You never edited the file, so it is replaced |
| Conflicts | You edited the file and the plugin changed it too. Yours is kept and stays in use; the new one is written beside it as `<name>.new` |
| Kept | Edited by you, unchanged in the plugin. Nothing happens |
| Current | Already up to date |

### What the upgrade does, in order

1. **Helper files**, as the preview showed. Nothing is deleted: a file the plugin no longer ships is moved to `.pka/upgrade-backups/` if you never edited it, and left in place if you did.
2. **The index**, if you have one and its schema is older. You are shown a plan and asked, at every autonomy level. On a yes, the database is copied to `.pka/db-backups/`, migrated, checked and re-indexed; a failure rolls back. On a no, the rest of the upgrade still runs, but search and indexing wait until you migrate.
3. **Role files.** `.pka/roles/` is backed up. New sections are added. Sections you already have are not rewritten. Sections an earlier release wrote and you never edited can be refreshed in one step, if you say yes. A section you customised is shown as a difference and replaced only if you say so for that section.
4. **Follow-ups.** It shows the weekly lint schedule entry (section 14) and suggests what else applies: the Obsidian retrofit if you have a vault, pointer tables if you have none.

Throughout: your notes are not touched (the upgrade changes `.pka/` only), nothing is committed, and it needs `python3` 3.9 or newer.

**More than one machine.** Each needs the plugin updated. The index is per machine, so each migrates and indexes its own.

**If the plugin is behind the workspace** (you upgraded from another machine), update the plugin rather than running the upgrade here: an older plugin would replace the workspace's newer tool with its own.

### What recent releases added

| Release | You can now |
|---|---|
| v1.7.0 | See a timeline on each person's page. Teach a nickname once. Have every filed note treated the same way. List open action items by date range. Get a greeting that shows what is actually open |
| v1.8.0 | Rely on PKA not committing or pushing. Clear the old commit and push instructions out of your role files. Move a finished project and keep its links working |
| v1.9.0 | Put the notes you already had on people's timelines. Without Obsidian, have timelines reach notes anywhere in the workspace |
| v1.10.0 | Find duplicate notes and duplicate people in a health check. Hide a finding that is fine as it is. Run a quick lint every week without a session. Have every form of link checked |

After the upgrade, the tutorial teaches the ones that apply to your workspace: *"What's new in this release?"*

### If an earlier release committed for you

Your repositories, their `.meta` file and their history are untouched by the upgrade. What changes:

- Until you run *"bootstrap upgrade"*, the old helper in your workspace behaves as its own release did, which means it still commits.
- The upgrade lists the commit and push sections of your role files as obsolete. The ones you never edited are removed when you accept the refresh; edited ones are left for you. Until they are gone, they still tell the roles to commit and push.
- The old helper scripts in `.pka/` (`push-all.sh`, `graduate.sh` and the others) are no longer shipped or maintained. Unedited copies are moved to the backup folder; edited ones stay where they are.
- After that, filing a note in a workspace that still has that layout ends with a "not committed" line as a reminder.

If an old role instruction still asks the tool to commit, this is what happens:

```
$ .pka/bin/pka-tools commit -m "Filed SLT sync"
Not committed: pka-tools no longer commits (`commit` is deprecated and does nothing).
Nothing was staged or committed; the changes are left for the user to commit. Do not run git.
```

**Try this**

- *"Do I need to upgrade?"*
- *"bootstrap upgrade"*
- *"What's new in this release?"*

---

## 17. The guided tour

`pka-tutorial` covers this material inside your workspace, with your folder names and prompts you can try as you go. Say *"Give me a tour"*, or ask how to do one thing.

It first works out where you are:

- **Not set up yet:** it points you to `pka-bootstrap`.
- **Workspace behind the installed release:** it offers the upgrade walkthrough first (section 16), because some of what it would show does not work until then.
- **Up to date:** the full tour, or any single module.

It teaches one idea at a time, gives a prompt, and asks whether you want to try it. It hands off instead of acting: it never moves or deletes files, and it does not perform the upgrade. Ask a real question in the middle and it stops teaching and answers.

| Module | In this tutorial |
|---|---|
| 1. Orientation | Sections 1 to 4 |
| 2. Finding things | Section 6 |
| 3. The inbox pattern | Section 7 |
| 4. Meeting capture | Section 8 |
| 5. The dashboard | Section 12 |
| 6. Project lifecycle | Section 13 |
| 7. The role system | Section 5 |
| 8. Topic wikis | Section 11 |
| 9. Health checks | Section 14 |
| 10. People and timelines | Section 9 |
| 11. The pointer layer and Obsidian | Section 10 |

---

## 18. A working rhythm

**Morning.** `cd ~/pka && claude`. The greeting shows open threads, new inbox items, stale projects and a recent health-check report if it has findings.

**During the day.** Drop files into `team-inbox/` as they arrive. For meetings, capture or write notes and let `pka-meetings` file them. For project work, start Claude Code inside the project.

**End of week.** *"What action items do I have this week?"* and *"Give me a project status summary."* Then, if the workspace is in a repository, review and commit what changed. PKA has not.

**Occasionally.** *"Run a health check"* after a large import. *"Update the dashboard"* after structural changes. *"What projects are winding down?"* when you want to tidy up. *"Re-index my knowledge base"* after editing notes by hand. *"Backfill timelines"* when the health check says notes are waiting.

**After a plugin update.** *"Do I need to upgrade?"*

---

## 19. Prompt reference

### Finding things

| You say | What happens |
|---|---|
| "What do I know about `<person or topic>`?" | Lookup; a wiki summary first if the topic has one |
| "Find everything about `<topic>` across all my work" | Search across knowledge folders and the top level of projects |
| "What's the state of `<project>`?" | Reads the project's `CLAUDE.md` and top-level documents |
| "What did I decide about `<topic>` last quarter?" | Search scoped by date |
| "Why did I archive `<project>`?" | Reads the decision log |
| "Re-index my knowledge base" | Incremental index update |

### Files and meetings

| You say | What happens |
|---|---|
| "Process my team-inbox" | Routes documents; holds transcripts |
| "I'm about to start a 1-1 with `<name>`" | Live capture (thinkkit), then filing |
| "Reconcile my `<meeting>` notes against the transcript in team-inbox" | Corrects the notes from the transcript (thinkkit), then filing |
| "File these meeting notes: `<path>`" | Routes, links attendees, extracts action items, updates timelines |
| "What action items do I have this week?" | Open checkboxes in dated notes of the last 7 days |

### People, pointers and wikis

| You say | What happens |
|---|---|
| "From now on, '`<nickname>`' means `<person>`" | Saves an alias on the person's page |
| "Backfill the timelines from my old notes" | Plans, reports, and applies only when you approve |
| "Set up pointer tables for my knowledge folders" | Creates a `_MOC.md` with an empty table per folder (without Obsidian) |
| "bootstrap obsidian" | One-time retrofit of a vault at `knowledge/` |
| "Create a topic wiki on `<topic>`" | Writes the scaffold and asks for a first source |
| "Ingest `<path>` into my `<topic>` wiki" | Shows a diff; writes only on approval |

### Looking after the system

| You say | What happens |
|---|---|
| "Run a health check" / "quick lint" | Writes a lint report to `owner-inbox/` |
| "Find duplicate notes" | The duplicate rules of a full lint |
| "That finding is fine, hide it" | Records a suppression with your reason |
| "Show me the weekly lint schedule" | Prints a cron line and a launchd file; installs nothing |
| "Generate my dashboard" / "Update the dashboard" | Writes or edits `dashboard.html` |
| "What projects are winding down?" | Projects with no file changes in 60 days or more |
| "Transition `<project>` to knowledge" | Summary, approval, cleanup, move, re-index |
| "Restore `<project>` to active" | Reverses a transition |
| "Add a `<role>` to my team" | Brief, role file, roster row, your confirmation |
| "Do I need to upgrade?" / "bootstrap upgrade" | Preview, then the upgrade |
| "Give me a tour" | The guided tour |

---

## 20. Where things live

| Path | What it is | Written by |
|---|---|---|
| `CLAUDE.md` | Instructions and the Repo Map | bootstrap; the orchestrator keeps the map |
| `.pkaignore` | What scans, the index and lint skip | bootstrap, then you |
| `team-inbox/` | Files you drop in | you |
| `team-inbox/unsorted/` | Files with no clear home | the librarian |
| `owner-inbox/` | Reports, briefs, drafts | the roles |
| `owner-inbox/librarian-report-<date>.md` | What a routing run did | the librarian |
| `owner-inbox/librarian-lint-<date>.md` | A health-check report | `pka-tools lint`, plus the librarian for rules 6 and 7 |
| `owner-inbox/timeline-backfill-plan-<date>.md` | A backfill plan to review | `pka-tools timeline plan` |
| `meeting-notes/` | Notes being captured, and earshot capture directories | thinkkit and earshot |
| `<people folder>/<person>/index.md` | A person's page and timeline | you; `pka-tools` owns the timeline block |
| `knowledge/**/_MOC.md` | A folder's map of content and pointer table | `pka-tools`; yours to reorganise |
| `knowledge/topics/<topic>/wiki.md` | A topic wiki | the researcher, on your approval |
| `dashboard.html` | The dashboard | `pka-interface` |
| `.pka/bin/` | `pka-tools` | the installer |
| `.pka/roles/` | Role files and the roster | bootstrap and upgrades; yours to edit |
| `.pka/session-log.md` | The work diary | every role |
| `.pka/decision-log.md` | Decisions and their reasons | the roles |
| `.pka/owner-profile.md` | Who you are and how you like things written | bootstrap; the roles keep it current |
| `.pka/knowledge.db` | The search index (index mode) | `pka-tools`; rebuilt from the files at any time |
| `.pka/lint-suppressions.json` | Findings you have hidden, with reasons | `pka-tools lint suppress` |
| `.pka/lint-cron-log.txt` | Output of scheduled lints | the schedule entry, if you install it |
| `.pka/backfill/`, `.pka/backups/` | Backfill plans, and the pages as they were before an apply | `pka-tools timeline` |
| `.pka/upgrade-backups/`, `.pka/db-backups/` | What an upgrade replaced | the upgrade |

Everything outside `.pka/` and the two inboxes is your content. The index, the dashboard and every report can be deleted and made again from it.
