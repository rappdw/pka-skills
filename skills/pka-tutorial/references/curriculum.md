# Tutorial Curriculum

Full scripts for each teaching module. Each module is designed to take 2-4 minutes
and end with a concrete prompt the user can try.

Use the user's **actual Repo Map folder names** when giving examples. The
placeholders below (`<personnel-folder>`, `<meeting-home-folder>`, etc.) should be
replaced with real folder names read from their `CLAUDE.md`.

---

## Module 1: Orientation

### Key ideas

1. **Your files are the source of truth.** PKA doesn't have a proprietary database.
   Every note is a markdown file you can read with any text editor. SQLite, when
   present, is a fast index over files you already own — nuke it and your knowledge
   stays intact.

2. **The Repo Map is the navigation layer.** At the bottom of your `CLAUDE.md`
   there's a table describing every folder — what it contains, how it's organized,
   its priority. Your AI reads this first to figure out where things live.

3. **Roles divide the labor.** The orchestrator (me) routes your requests. The
   researcher does deep synthesis. The librarian handles files, OCR, indexing.
   You delegate via @mentions or just describe what you want.

4. **The session log is your work diary.** Every significant action goes to
   `.pka/session-log.md`. When you come back tomorrow, I read the last 20 entries
   so we pick up where we left off.

5. **Your autonomy level controls confirmation.** You set this at bootstrap.
   It decides whether I ask before every move or just do things and report.

### Show the user their Repo Map

Read their `CLAUDE.md` and display the first 3-4 rows of the Repo Map table.
Name one folder and explain what it means in plain language.

### Try this

> "Show me my current Repo Map"
>
> "What's in `<actual-folder-name>`?"

---

## Module 2: Finding Things

### Key ideas

The most-used capability. You have documents scattered across folders — PKA
makes them accessible through conversation.

### Four types of queries

**1. Simple lookup — "What do I know about X?"**

I check the Repo Map, find the relevant folder, search the index, and surface
results. Works for people, topics, projects, decisions.

**2. Cross-repo search — "Find everything about X"**

Full-text search across your entire knowledge base (and project folders if you
want). Returns ranked results by folder.

**3. Project snapshot — "What's the state of project X?"**

I read the project's `CLAUDE.md` and top-level docs, give you a current summary.

**4. Date-scoped — "What did I decide about X in Q1?"**

Combines FTS with date metadata. Useful for retrospectives.

### Show the user their scale

Read the count from `.pka/knowledge.db` if present, or count files via glob.
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
- `owner-inbox/` — **my output zone.** Research briefs, summaries, drafts go
  here for you to review.

### What happens when you drop a file

1. At next session start, I scan `team-inbox/` and flag what's new
2. For each file, I propose a routing destination based on content and Repo Map
3. You confirm (or override) — I move, index, and report
4. Transcripts (`.vtt`, `.srt`) are held, not routed. They wait for `pka-meetings`
   to process them alongside notes

### Batch processing

If you dump 20 files at once, I route the obvious ones, ask about the ambiguous
ones, and never silently skip. Ambiguous files land in `team-inbox/unsorted/`
for a second pass.

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
(what's the meeting, who's attending), then invoke `take-notes`. You feed terse
observations:

```
aarav on mcp adapter work
q2 kong vs agentcore decision needs input
send architecture doc
```

`take-notes` expands these into structured notes in real-time. When the
meeting ends, say "done." `pka-meetings` takes over and runs the pipeline.

### Mode B: Reconcile against a transcript (thinkkit required)

You have a Zoom/Teams transcript AND your notes. Drop the transcript in
`team-inbox/`, then say "reconcile my `<meeting>` notes against the transcript."
`resolve-against-transcript` finds discrepancies, corrections, and missing
items. Then pipeline runs.

### Mode C: Route only (no thinkkit needed)

You already wrote notes somewhere. Say "file these meeting notes" and point me
at the file. Skip capture, skip reconcile, just route + index + link.

### The post-processing pipeline (all modes)

1. **Route** — detects meeting type (1-1, project, leadership, general) and
   proposes a destination from the Repo Map
2. **Link attendees** — fuzzy matches names against your personnel folders,
   adds relative links under `## Attendees`
3. **Extract action items** — finds `- [ ]`, `AI:`, `TODO:`, `→` markers and
   normalizes them
4. **File** — saves as `YYYY-MM-DD-meeting-slug.md` in the destination
5. **Index** — updates SQLite so the note is searchable immediately
6. **Report** — tells you what got filed where, attendees linked, action
   items found

Post-meeting overhead: ~30 seconds of confirmation.

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
> "File these meeting notes — I wrote them in Obsidian"
>
> "What action items do I have from this week's meetings?"

---

## Module 5: The Dashboard

### Key ideas

A single-file HTML dashboard at `<pka-root>/dashboard.html`. No server, no
dependencies beyond a browser. Opens directly:

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

### Updating the dashboard

Say what you want added or changed:

> "Update the dashboard — add a timeline for my `<journal-folder>` entries"
>
> "Add a section showing my action items"
>
> "Refresh the activity log"

The skill reads the existing HTML, edits surgically, leaves everything else alone.

### Search

The dashboard has a search box that queries `search_fts` across your whole
knowledge base. Results link to the source files.

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

### Stale detection

At every session start, I check project workspaces for 60+ days of inactivity
and flag them:

> Found 2 projects with no activity in 60+ days: operating_model, alpha-redesign

No action is taken — it's just a prompt for you to decide.

### The transition workflow

You say "transition `<project>` to knowledge." What happens:

1. **Summary generation.** I read the project's `CLAUDE.md` and top-level docs,
   generate a `project-summary.md` draft in `owner-inbox/` for you to review
2. **Mandatory pause.** Regardless of your autonomy level, I wait for approval
3. **Artifact cleanup.** I list build artifacts (`node_modules/`, temp files)
   and confirm before deleting
4. **Move.** Directory moves from `projects/<name>/` to your archive destination
5. **Re-index.** Librarian runs a full content index pass on the moved directory
6. **Map update.** Repo Map status changes to `archived`, priority to Reference

### Why it matters

Once archived, the project's content becomes **searchable alongside your
knowledge base**. Six months later, a cross-repo search surfaces documents from
that project as naturally as any other reference material.

### Reverse transition

If a "done" project turns out not to be done:

> "Restore `<project>` to active"

Moves it back, updates the Repo Map, removes from full-text index.

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
| `@researcher` | Deep synthesis, role briefs, cross-knowledge-base analysis. |
| `@librarian` | File ingestion, OCR, routing, indexing. |

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

Don't create a wiki for: one-off questions, people (use personnel/), projects
(use projects/).

### Where they live

`knowledge/topics/<topic-slug>/wiki.md` by default. Each topic gets its own
folder; sources and drafts sit alongside:

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

Without a wiki, "what do I know about X" runs FTS over your notes.

With a wiki, the orchestrator surfaces the wiki summary first, THEN the FTS
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

Over time, any knowledge base drifts: files move, links rot, wikis fall behind
newer notes. Lint surfaces these issues. It produces a report — it never
auto-fixes.

### What lint catches

| Rule | What it flags |
|------|---------------|
| Orphans | Files sitting in `team-inbox/unsorted/` > 14 days |
| Broken links | Markdown links and `[[wikilinks]]` pointing nowhere |
| Stale wiki sources | Wiki citations to files that no longer exist |
| Empty folders | Folders in your Repo Map with no content |
| Missing back-refs | Notes mentioning someone whose folder doesn't link back |
| Contradiction candidates | Wikis with many newer uningested mentions |
| Uncited wiki claims | Wiki paragraphs without citations |

### Cadence

Weekly or monthly. Not every session. Run after big imports or structural
changes.

### Quick vs. full lint

- **Quick** — rules 1-4 only, fast (just file operations)
- **Full** — all 7 rules, slower (runs FTS for entity mentions)

Default: full. Say "quick lint" if you're in a hurry.

### Reading the report

Report lands in `owner-inbox/librarian-lint-<date>.md` with a Summary at the top
and Details below. Suggested next actions at the bottom.

You act manually — lint never modifies files.

### Try this

> "Run a health check"
>
> "Check for broken links in my notes"
>
> "What needs attention?"

---

## Ending any module

> That's `<module name>`. Want me to cover another, or try one of these
> prompts right now? You can also open `docs/TUTORIAL.md` for the full
> written walkthrough.
