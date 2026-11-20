# Tutorial Curriculum

Full scripts for each teaching module. Each module is designed to take 2-4 minutes
and end with a concrete prompt the user can try.

Use the user's **actual Repo Map folder names** when giving examples. The
placeholders below (`<personnel-folder>`, `<meeting-home-folder>`, etc.) should be
replaced with real folder names read from their `CLAUDE.md`. Names in the sample
conversations (Priya, Orion, Lyra) are fictional stand-ins.

These modules describe the installed release. For a workspace that has not been
upgraded on it, `upgrade-and-whats-new.md` comes first.

There are eleven modules. Each stands alone, so the user can skip around. Modules
10 and 11 were added after the first nine and keep their numbers so that earlier
references to "Module 9" and the like stay right. For a full tour, this order
reads best: 1, 2, 3, 4, 10, 5, 6, 7, 8, 11, 9.

Two modules depend on the workspace. Check with
`.pka/bin/pka-tools status --json` (it changes nothing) before teaching them:

| Module | Teach in full when | Otherwise |
|---|---|---|
| 10. People and Timelines | `people_home` is not null | Say what a people folder is and how to get one; skip the rest |
| 11. The Pointer Layer and Obsidian | `obsidian_present` is true, or `knowledge/` has `_MOC.md` files | Say in two sentences what the layer is and that it is opt-in |

---

## Module 1: Orientation

### Key ideas

1. **Your files are the source of truth.** PKA doesn't have a proprietary database.
   Every note is a plain file you can read with any text editor. SQLite, when
   present, is a fast index over files you already own — delete it and your
   knowledge stays intact; it can be rebuilt from the files.

2. **The Repo Map is the navigation layer.** At the bottom of your `CLAUDE.md`
   there's a table describing every folder — what it contains, how it's organized,
   its priority, and tags such as `people-home` and `meeting-home` that tell the
   skills where things go. Your AI reads this first to figure out where things live.

3. **Roles divide the labor.** The orchestrator (me) routes your requests. The
   researcher does deep synthesis. The librarian handles files, OCR, indexing.
   You delegate via @mentions or just describe what you want.

4. **A small tool does the mechanical steps.** Index updates, table edits and
   timeline lines are made by `pka-tools`, a helper in `.pka/bin/`, so they come
   out the same every time. It needs Python 3.9 or newer, makes no network calls,
   and changes only the lines it owns. You will rarely run it yourself.

5. **The session log is your work diary.** Every significant action goes to
   `.pka/session-log.md`. When you come back tomorrow, I read the open threads of
   the last 20 entries so we pick up where we left off.

6. **Your autonomy level controls confirmation.** You set this at bootstrap.
   It decides whether I ask before every move or just do things and report. A few
   things are asked at every level: ingesting into a wiki, approving a project
   summary, filing a meeting note into an active project.

7. **PKA never commits.** Nothing is staged, committed or pushed for you, in any
   repository. Filing a note changes files; if you keep the workspace in git,
   reviewing and committing them is yours to do.

### Show the user their Repo Map

Read their `CLAUDE.md` and display the first 3-4 rows of the Repo Map table.
Name one folder and explain what it means in plain language. If a row has a
tag, say what the tag does.

### When the plugin is updated

Updating the plugin does not change the workspace. Say this once: after an
update, "Do I need to upgrade?" shows what would change, and "bootstrap upgrade"
does it. The script for that is `upgrade-and-whats-new.md`, not a module.

### Try this

> "Show me my current Repo Map"
>
> "What's in `<actual-folder-name>`?"
>
> "What autonomy level am I on?"

---

## Module 2: Finding Things

### Key ideas

The most-used capability. You have documents scattered across folders — PKA
makes them accessible through conversation.

### Five types of queries

**1. Simple lookup — "What do I know about X?"**

I check the Repo Map, find the relevant folder, search, and surface results with
the paths I used. Works for people, topics, projects, decisions.

**2. Search across everything — "Find everything about X"**

Full-text search across your knowledge folders and the top level of each
project. Returns ranked results by folder.

**3. Project snapshot — "What's the state of project X?"**

I read the project's `CLAUDE.md` and top-level docs, give you a current summary.

**4. Date-scoped — "What did I decide about X in Q1?"**

Combines search with dates. Useful for retrospectives.

**5. Decision history — "Why did I archive X?"**

Reads `.pka/decision-log.md`, which records decisions with their reasons.

### What search covers, and when it is current

- Knowledge folders are indexed in full. An active project is indexed one level
  deep; it becomes fully searchable once it is archived (Module 6).
- PDFs and Office files are searchable through the text sidecar the librarian
  writes beside them. A PDF with no sidecar is filed but not searchable.
- A note a skill files is indexed as part of filing. A note the user adds or
  edits by hand is not searchable until they say "re-index my knowledge base".
  Re-indexing re-reads only changed files, and deleted files drop out.
- In a markdown-only workspace there is no index: I read the files directly,
  guided by the Repo Map.

### Show the user their scale

In index mode, `.pka/bin/pka-tools db schema` gives the row counts (it changes
nothing). Otherwise count files via glob.
"You have N indexed files across M top-level folders."

### Try this (adapted to their folders)

> "What do I know about `<person-or-topic-they-mention>`?"
>
> "Find everything I've written about `<topic>`"
>
> "What's the state of `<project-folder-name>`?" (if they have a project folder)

---

## Module 3: The Inbox Pattern

### Key ideas

Two folders, two directions:
- `team-inbox/` — **your drop zone.** Files you put here get routed into the
  knowledge base.
- `owner-inbox/` — **my output zone.** Research briefs, summaries, drafts and
  reports go here for you to review.

### What happens when you drop a file

1. At next session start, I scan `team-inbox/` and flag what's new
2. For each file, I propose a routing destination based on content and Repo Map
3. You confirm (or override) — the librarian moves it
4. One step then does everything that follows a filing: the index entry, a line
   on the timeline of each person the file is about (Module 10), and a row in the
   folder's topic table if you use them (Module 11)
5. A report lands in `owner-inbox/librarian-report-<date>.md`

### Rules the librarian keeps

- **Originals are never modified.** Text extracted from a PDF goes in a sidecar
  file beside it (`report.pdf.txt`).
- **Nothing is silently skipped.** A file with no clear home goes to
  `team-inbox/unsorted/` and is named in the report.
- **Nothing is routed into a project workspace without asking**, and nothing is
  deleted from the inbox without confirmation.
- **Transcripts (`.vtt`, `.srt`, Zoom and Teams transcript files) are held, not
  routed.** They wait in `team-inbox/` for `pka-meetings` to process them
  alongside notes.
- **An earshot capture directory** (a folder with a `meeting.json` in it) is
  never routed, moved or deleted.

### PDFs and scans

Making a PDF searchable needs a tool the user installs: `pdfplumber` or `pypdf`
for PDFs that contain text, `tesseract` for scans. Without one the file is still
filed, and the report says its text could not be read and what to install.

### Batch processing

If you dump 20 files at once, I route the obvious ones, ask about the ambiguous
ones, and never silently skip.

### Try this

> "Process my team-inbox"
>
> "Show me what's in team-inbox"
>
> "What did you put in owner-inbox today?"

---

## Module 4: Meeting Capture

### Key ideas

Three working modes. Pick based on what you have.

### Mode A: Capture live (thinkkit required)

You say "I'm in a 1-1 with `<name>`" or "take notes." I ask two quick questions
(what's the meeting, who's attending), then invoke `take-notes`. It creates a
note in `meeting-notes/` at the workspace root. You feed terse observations:

```
priya: taking the adapter spike
vendor decision deferred to december
which vendors make the shortlist? not settled
```

`take-notes` expands these into structured notes in real-time. Start a line
with `name:` to attribute it; a speaker is never guessed. Commitments go under
Action Items, unanswered questions under Open Questions. When the meeting
ends, say "done." `pka-meetings` takes over and runs the pipeline.

### Mode B: Reconcile against a transcript (thinkkit required)

You have a Zoom/Teams transcript AND your notes. Drop the transcript in
`team-inbox/`, then say "reconcile my `<meeting>` notes against the transcript."
The transcript is treated as the truth. `resolve-against-transcript` shows one
discrepancy at a time (a wrong statement, a shifted meaning, a wrong speaker, a
missing decision or commitment) and you answer accept, modify or skip. Then the
pipeline runs. Reconcile before filing, while the note is still in
`meeting-notes/`.

### Mode C: Route only (no thinkkit needed)

You already wrote notes somewhere. Say "file these meeting notes" and point me
at the file. Skip capture, skip reconcile, just route + link + index.

### The post-processing pipeline (all modes)

1. **Route** — detects meeting type (1-1, project, leadership, general) and
   proposes a destination from the Repo Map. A meeting about an active project
   always gets a question: file it in the project, or in knowledge?
2. **Link attendees** — each name is checked against your people folders. A
   certain match is linked under `## Attendees`; an ambiguous one is asked
   about, never guessed; no match is listed without a link
3. **Extract action items** — finds `- [ ]`, `AI:`, `TODO:`, `→` markers,
   normalizes them, and offers to add them to the session log's open threads
4. **File** — saves as `YYYY-MM-DD-meeting-slug.md` in the destination; a 1-1 is
   `YYYY-MM-DD-1-1-<person>.md` in the person's folder. Existing notes named
   another way are never renamed
5. **Post-route** — the same step every filed note gets: a line on each
   attendee's timeline with a short summary (Module 10), the index entry, and a
   topic row where the workspace uses them (Module 11)
6. **Report** — tells you what got filed where, attendees linked, action
   items found, and asks what to do with the transcript (keep, archive, or
   delete after confirming)

Nothing is committed; the report names the files that changed.

Post-meeting overhead: ~30 seconds of confirmation.

### Action items later

"What action items do I have this week?" lists unticked `- [ ]` boxes in the
dated notes of the last 7 days, each with its source file. An owner is read
from `@name` and a due date from `by YYYY-MM-DD`. Items in thinkkit's own form
(`**Owner**: …`) are listed as written. Tick the box in the note to close one.

### If the user records with earshot

earshot is a separate local recording tool. Its capture directories (marked by
`meeting.json`, usually under `meeting-notes/`) are never moved or deleted; only
the notes file is filed, and its `**Recording**:` line is kept as written. A
capture with a transcript and no reconciled note is offered for Mode B.

### If thinkkit isn't installed

Modes A and B won't work. Mode C still handles everything. To get full capture,
install thinkkit:

```
/plugin marketplace add https://github.com/rappdw/thinkkit
/plugin install thinkkit
```

### Try this

> "I'm about to start a 1-1 with `<name>`" (if thinkkit installed)
>
> "File these meeting notes: `<path>`"
>
> "What action items do I have from this week's meetings?"

---

## Module 5: The Dashboard

### Key ideas

A single-file HTML dashboard at `<pka-root>/dashboard.html`. No server, no
build step. Opens directly:

```bash
open dashboard.html    # macOS
xdg-open dashboard.html    # Linux
```

### View types (auto-selected by folder type)

| Folder type | View |
|-------------|------|
| Personnel (per-person subfolders) | Card grid, sorted by last activity |
| Meeting-home (tagged in Repo Map) | Timeline sorted by date-in-filename |
| Research (topic subfolders) | Topic list with links to each topic's docs |
| Journal (date-named files) | Calendar heatmap |
| Projects (folders with CLAUDE.md) | Project cards with status badges, age, doc count |
| Generic | File table with search |

Two sections are always there: Activity (the last 20 session-log entries) and
Search.

### How it reads your data

- **Index mode:** the page reads `.pka/knowledge.db` in the browser and search
  is full-text. It loads the sql.js library from a public CDN to do that, so
  opening it makes one network request.
- **Markdown-only:** it needs Chrome or Edge and asks you to pick the workspace
  folder when it opens. Search covers file and folder names, with a slower
  "deep search" for contents.

File links are absolute paths on this disk: regenerate the dashboard if the
workspace moves.

### Updating the dashboard

Say what you want added or changed:

> "Update the dashboard — add a timeline for my `<journal-folder>` entries"
>
> "Add a section showing my action items"
>
> "Refresh the activity log"

The skill reads the existing HTML, edits surgically, leaves everything else alone.

### Try this

> "Generate my dashboard" (if it doesn't exist yet)
>
> "Update the dashboard"
>
> "Add a `<new section>` to the dashboard"

---

## Module 6: Project Lifecycle

### Key ideas

Projects have a natural lifecycle: **active → archiving → archived**. PKA
surfaces this rhythm instead of letting projects sit in limbo.

A folder with its own `CLAUDE.md` is a project workspace. Starting Claude Code
inside it loads that project's context instead of PKA; from the workspace root,
PKA sees the project one level deep and never files into it without asking.

### Stale detection

At every session start, I check project workspaces for 60+ days of inactivity
and flag them:

> Found 1 project with no activity in 60+ days: lyra

No action is taken — it's just a prompt for you to decide.

### The transition workflow

You say "transition `<project>` to knowledge." What happens:

1. **Summary generation.** I read the project's `CLAUDE.md` and top-level docs,
   generate a `project-summary.md` draft in `owner-inbox/` for you to review
2. **Mandatory pause.** Regardless of your autonomy level, I wait for approval
3. **Artifact cleanup.** I list build artifacts (`node_modules/`, temp files)
   and confirm before deleting
4. **Move.** Directory moves from `projects/<name>/` to your archive destination,
   and every wikilink that pointed at the old location is rewritten to the new
   one. Anything else that still names the old path is shown to you to fix.
   If the project folder is its own git repository, I stop and ask first: what
   happens to that history is your decision. Nothing is committed for you
5. **Re-index.** Librarian runs a full content index pass on the moved directory
6. **Map update.** Repo Map status changes to `archived`, priority to Reference

"Archive `<project>`" without a transition just marks it `archiving` for later.

### Why it matters

Once archived, the project's content becomes **searchable alongside your
knowledge base**. Six months later, a search surfaces documents from
that project as naturally as any other reference material.

### Reverse transition

If a "done" project turns out not to be done:

> "Restore `<project>` to active"

Moves it back, its links follow, the Repo Map is updated, and it returns to the
one-level project index.

### Try this

> "What projects are winding down?"
>
> "Transition `<project-name>` to knowledge" (if you have a project ready)

---

## Module 7: The Role System

### Key ideas

PKA ships with three seed roles; you add more as you need them.

### Seed roles

| Role | What it does |
|------|-------------|
| `@orchestrator` | Routes requests, maintains Repo Map, handles lifecycle. Always active. |
| `@researcher` | Deep synthesis, role briefs, cross-knowledge-base analysis, topic wikis. |
| `@librarian` | File ingestion, OCR, routing, indexing, health checks. |

### Roles and skills

Skills are what the plugin installs. Roles are markdown files in `.pka/roles/`
in your own folder: you can read and edit them, and `roster.md` lists them. An
upgrade adds new sections to them and never rewrites a section you edited.

### How to delegate

You can @mention explicitly:

> "@researcher synthesize what I know about distributed consensus"

Or just describe what you need — the orchestrator routes:

> "What do I know about distributed consensus?"
> → orchestrator routes to @researcher

### Adding a role

> "Add a `<role>` to my team"

What happens:
1. `@researcher` generates a competency brief in `owner-inbox/`
2. New role file written to `.pka/roles/`
3. `roster.md` updated
4. You confirm before finalizing

### Communication style

Your `.pka/owner-profile.md` (created at bootstrap) includes a communication
style — concise, narrative, mixed. Roles read this and adapt. If my outputs
don't match your preference, say:

> "Update my communication style — I prefer shorter summaries"

And the profile updates.

### Try this

> "Show me my role roster"
>
> "What roles do I have?"
>
> "Add a `<role>` to my team"

---

## Module 8: Topic Wikis

### Key ideas

PKA has two kinds of content and it's important to hold them distinct:

1. **Authored moments** — your meeting notes, 1-1s, drafts, journal. These are
   your voice. They record what happened at a specific moment and don't change.
2. **Synthesis pages (topic wikis)** — LLM-maintained pages about a topic. They
   cite your moments. They evolve.

Wikis cite moments. Moments never cite wikis. Delete a wiki, lose no underlying
content.

### When to create a wiki

Not every topic deserves a wiki. Create one when:
- You're accumulating material (papers, notes, conversations) on a specific area
- You want a *maintained* synthesis, not just searchable moments
- You want to track "what I know" distinct from "what was said in that meeting"

Don't create a wiki for: one-off questions, people (use the people folder),
projects (use projects/).

### Where they live

`knowledge/topics/<topic-slug>/wiki.md` by default (the folder tagged
`wiki-home`). Each topic gets its own folder; sources and drafts sit alongside:

```
knowledge/topics/mcp/
├── wiki.md
├── sources/
└── drafts/
```

### The ingest workflow

You have a paper. You want to synthesize it into your MCP wiki.

1. You say: *"Ingest this paper into my MCP wiki"*
2. @researcher reads the source + current wiki
3. Categorizes content: new claims, confirmations, contradictions, refinements
4. Presents a section-level diff for you to review
5. **You approve** — this step always requires confirmation, even in hands-off
   mode. Synthesis is high-stakes.
6. Wiki updated: Sources list grows, changelog appended, cross-wiki mentions
   flagged

If the source contradicts the wiki, you decide how to reconcile — never auto-resolved.

### Query behavior changes when wiki exists

Without a wiki, "what do I know about X" searches your notes.

With a wiki, the orchestrator surfaces the wiki summary first, THEN the
mentions not yet ingested. So you see:

> Summary from wiki: [synthesized understanding]
>
> Also surfaced from your notes (not yet in wiki):
> - [path] — recent mention, worth ingesting

### Wikilinks

Use `[[slug]]` format to link between wikis. Renders in Obsidian; degrades
cleanly elsewhere. Lint verifies targets exist.

### Try this

> "Create a topic wiki on `<topic-you-care-about>`"
>
> "Show me my topic wikis"
>
> "Ingest `<path>` into my `<topic>` wiki"

---

## Module 9: Health Checks

### Key ideas

Over time, any knowledge base drifts: files move, links rot, the same note gets
saved twice, wikis fall behind newer notes. Lint surfaces these. It writes a
report and changes nothing; you decide what to do about each finding.

### What lint catches

| Rule | What it flags |
|------|---------------|
| 1. Orphans | Files sitting in `team-inbox/unsorted/` for more than 14 days |
| 2. Broken links | `[[wikilinks]]` and markdown links pointing at files that are gone |
| 3. Stale wiki sources | Wiki citations to files that no longer exist |
| 4. Empty folders | Folders in your Repo Map with nothing in them |
| 5. Timelines | Notes that involve someone and are not on their timeline (one line, with the fix) |
| 6. Contradiction candidates | Wikis with several newer notes they have not taken in |
| 7. Uncited wiki claims | Wiki paragraphs without citations |
| 8. Duplicates | Identical files, the same text saved twice, near-copies, one note inside another, and two folders for one person |

For duplicates the report shows each group with sizes, dates and how many notes
link to each copy, and suggests which one to keep. It never deletes anything.

Rules 1 to 5 and 8 are run by a tool, so they come out the same every time.
Rules 6 and 7 need judgement: the librarian adds them to the report in a
session.

### Quick vs. full

- **Quick** — rules 1 to 4 and exact duplicates. About a second.
- **Full** — everything, including near-duplicates and the two wiki rules. A few seconds, plus the wiki checks.

Default: full. Say "quick lint" if you're in a hurry.

### Reading the report

The report lands in `owner-inbox/librarian-lint-<date>.md`: counts at the top,
then one section per rule. Every finding ends with an id such as
`[id: 8a-3f9c21d0]`.

### When a finding is fine as it is

Two people really do share a name; you keep a copy in two places on purpose.
Tell me, and I record it so it stops coming up:

> "That duplicate is on purpose, hide it"

You can see what is hidden, and bring one back, at any time. The line about
timelines (rule 5) is information and cannot be hidden; a backfill clears it
(Module 10).

### Running it every week

Lint needs no AI for most of its rules, so it can run unattended. Ask and I
will show you a schedule entry (cron, or launchd on a Mac) that runs a quick
lint every Monday. I never install it; that is yours to do. When a recent
report has findings, I mention it when you start a session.

### Try this

> "Run a health check"
>
> "Find duplicate notes"
>
> "Show me the weekly lint schedule"

---

## Module 10: People and Timelines

*Teach in full when the workspace has a people folder (see the table at the
top). Without one: a people folder is the folder tagged `people-home` in the
Repo Map, with one subfolder per person; the user can make one, or ask for it,
and come back to this module.*

### Key ideas

A person you keep a folder for has a page, `index.md`. Filing a note that
involves them adds one line to the `## Timeline` on that page, newest first:

```
- 2026-11-14 · meeting · [SLT sync](../../leadership/2026-11-14-slt-sync.md) — Owns the adapter spike; vendor decision deferred
```

Date, kind (`meeting`, `1on1` or `doc`), a link to the note, and a summary of at
most 140 characters. So "what do I know about `<person>`?" starts from a dated
list of everything that involved them.

### Show the user one

Pick a person folder that has an `index.md` with a Timeline and show its first
few lines. If no page has one yet, say so: timelines start empty and fill in as
notes are filed, or all at once with a backfill (below).

### Who goes on a timeline

Evidence in the note decides, never a guess:

- the note is in the person's folder;
- its `person` or `attendees` frontmatter, or a link under `## Attendees`, names
  them;
- their folder name is in the filename.

A name that appears only in the body does not count. A meeting with more than
8 matched attendees adds none of them unless you ask. `no-backref: true` in a
note's frontmatter keeps it off every timeline.

### Names

A full name, a saved alias, or a first name only one person has is a match. A
last name alone, or a first name two people share, gets a question. Nicknames
are never guessed; tell me once and it is saved:

> "From now on, '`<nickname>`' means `<person>`"

### What is yours

Edit a summary freely; a line you edited is not rewritten. PKA does not create
person folders unasked. An attendee without a folder is listed in the note
without a link and gets no timeline.

### Backfill: the notes you already had

Timelines only gain lines as new notes are filed. The backfill puts older
notes on them:

1. **Plan.** A report lands in `owner-inbox/` listing what would be added and
   what could not be placed (ambiguous names, notes with no date). Nothing else
   changes.
2. **Settle names.** Confirm an alias or leave it, then plan again.
3. **Apply**, only when you approve. The pages it touches are backed up first
   and checked afterwards.
4. **Undo** with one command, which the apply prints.

Notes themselves are never changed, and nothing is committed. Backfilled lines
have no summaries; ask for them one person at a time.

### How far a timeline reaches

*Say the one that applies (`obsidian_present` in `status`).* Without Obsidian, a
timeline can link to a note anywhere in the workspace, such as a project folder
or a meeting folder at the root; the inboxes are left out. In an Obsidian vault
it links only to notes inside `knowledge/`.

### Try this

> "File a 1-1 note for `<a person in their people folder>`" — then open
> `<people folder>/<person>/index.md` and look at the Timeline
>
> "From now on, '`<nickname>`' means `<person>`"
>
> "Backfill the timelines from my old notes"

---

## Module 11: The Pointer Layer and Obsidian

*Teach the part that applies (see the table at the top). With neither an
Obsidian vault nor any `_MOC.md`, give only "Key ideas" and the opt-in prompt.*

### Key ideas

A `_MOC.md` is a map of content for one knowledge folder. Its `## Pointers`
table has one row per topic: a topic slug, the entities involved, and links to
the files. A search lands on the topic row first and then reads the few files
in it, instead of wading through every note that mentions a word. It is a
markdown table; there are no embeddings.

It starts to pay off with hundreds of notes. In a small workspace it can be
skipped.

### How rows are kept

- The librarian adds to the table as files are filed.
- Rows are extended, never deleted, reordered or merged. Your edits to a row
  are kept.
- A row that reaches 8 files is reported; splitting it is your call.

### Without Obsidian: opt-in

Filing a note never creates a `_MOC.md`, and rows are written only into MOCs
that already exist. To get the layer:

> "Set up pointer tables for my knowledge folders"

That creates one `_MOC.md`, with an empty table, per folder.

### With Obsidian: on by default

*Only when `obsidian_present` is true.* PKA recognises a vault at
`knowledge/.obsidian/` and works alongside it:

- Filed notes get missing frontmatter keys (existing fields are never
  overwritten), a bullet in the folder's `_MOC.md`, and a pointer row.
- Links inside the vault are `[[wikilinks]]`, including timeline links.
- "bootstrap obsidian" is an optional one-time retrofit of the existing vault:
  MOC stubs, person indexes, and frontmatter derived from filenames and
  folders. It does not read note bodies, never edits an existing MOC or person
  page, and runs only when asked. Nothing is committed.

A vault somewhere other than `knowledge/` is not detected.

### Show the user theirs

If a `_MOC.md` exists, show two or three rows of its Pointers table and name
the topic of one.

### Try this

> "Set up pointer tables for my knowledge folders" (no Obsidian)
>
> "bootstrap obsidian" (a vault at `knowledge/`)
>
> "What do I know about `<a topic slug from their Pointers table>`?"

---

## Ending any module

> That's `<module name>`. Want me to cover another, or try one of these
> prompts right now? You can also open `docs/TUTORIAL.md` for the full
> written walkthrough.
