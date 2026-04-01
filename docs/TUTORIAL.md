# PKA System Tutorial

A practical walkthrough of your Personal Knowledge Assistance system after migration and setup. Written for daily use — not a reference document but a guided experience of how the system works in practice.

---

## Before You Start

Your system is set up. You have:
- `~/pka/` as your root, with `knowledge/` and `projects/` inside
- Four PKA skills installed: bootstrap, librarian, interface, meetings
- Thinkkit installed: take-notes, resolve-against-transcript
- `knowledge.db` indexed with your ~1,300 knowledge files
- `dashboard.html` at `~/pka/`

There are two ways to enter the system:

```bash
# PKA mode — full system, cross-repo, meeting docs, everything
cd ~/pka && claude

# Project mode — isolated context, exactly as before
cd ~/pka/projects/satori && claude
```

This tutorial covers PKA mode. Project mode is unchanged from how you worked before.

---

## Part 1: Your First Session

```bash
cd ~/pka
claude
```

The orchestrator wakes up, reads the last 20 session log entries, scans `team-inbox/`, does a quick folder diff against the Repo Map, and greets you. Something like:

> Good morning Dan. No items in team-inbox. Found 1 project with no activity in 67 days (operating_model). Ready — what are you working on?

That last line — the stale project flag — is the system being proactively useful. You didn't ask. It noticed.

If you have nothing urgent, just start. The system holds context across sessions via `session-log.md`, so you can pick up threads from previous days.

---

## Part 2: Finding What You Know

This is the most-used capability. You have 1,300+ files across decades of work. The system makes them accessible through conversation.

### Simple lookup

*"What do I know about Aarav?"*

The orchestrator looks at the Repo Map, sees `knowledge/personnel/` is where per-person notes live, searches the index for content matching Aarav, and surfaces:

> Found `knowledge/personnel/aarav/` — last modified 3 weeks ago. Here's a summary of what's there:
>
> [content summary]
>
> Also found 2 mentions in `knowledge/leadership/` — Q1 SLT doc and a February meeting note.

You didn't type a path. You didn't search a filename. You asked.

### Cross-repo search

*"Find everything I've written about MCP across all my work."*

The orchestrator searches `search_fts` across both `knowledge/` and `projects/` and returns:

> Found 23 references to MCP:
>
> **knowledge/**
> - `AI/agents/AgentGateway.md` — 8 mentions, architecture notes
> - `leadership/AI Strategy Council/Oct 2025.md` — 3 mentions
>
> **projects/**
> - `projects/satori/alignment.md` — 5 mentions
> - `projects/foundry/CLAUDE.md` — brief reference
>
> Want me to synthesize what you've written, or pull up a specific file?

This query was impossible before — you would have had to open files manually or use grep.

### Project status

*"What's the current state of the Satori project?"*

The orchestrator reads `projects/satori/CLAUDE.md` and the top-level markdown files:

> Satori is your agentic SOC automation platform. Last activity was 2 days ago. Top documents: alignment.md (last major update), AgentCoreResponse.md, several strategy PDFs. The CLAUDE.md describes it as targeting DLP Triage as the flagship capability.
>
> Want me to pull up any of these, or do a deeper synthesis?

You get a current snapshot without opening anything.

---

## Part 3: Dropping Files into the System

The `team-inbox/` folder is your input queue. Drop anything in there — PDFs, documents, scans — and the system routes them.

### The basic drop

Save a file to `~/pka/team-inbox/`:
```bash
# From Finder: drag to ~/pka/team-inbox/
# Or from terminal:
cp ~/Downloads/vendor-contract-2026.pdf ~/pka/team-inbox/
```

At your next session start the orchestrator notices it. Or right now:

*"Process my team-inbox."*

> I found 1 file in team-inbox:
>
> `vendor-contract-2026.pdf` — PDF, appears to be a legal contract
>
> Proposed routing: `knowledge/leadership/` — but I'm not certain. Does this belong somewhere more specific?

*"Route it to leadership."*

> Moving. Extracting text layer... done. Indexed. Searchable.

### What happens with transcripts

If you drop a Zoom or Teams transcript (`.vtt` file) into `team-inbox/`, the librarian treats it differently. At your next session:

> Found a transcript in team-inbox: `GMT20260331-162935_Recording.transcript.vtt`
>
> Do you have notes to reconcile against this, or should I generate notes from the transcript directly?

The transcript is held, not routed. It waits for `pka-meetings` to process it. This is intentional — you don't want raw transcript text buried in your knowledge base before reconciliation.

---

## Part 4: Capturing a Meeting

This is the meeting documentation workflow. Three tools working together: `take-notes` (capture), `resolve-against-transcript` (reconcile), and `pka-meetings` (route + index + link).

### Before the meeting

From `~/pka/`:

*"I'm about to start a 1-1 with Aarav."*

The system asks two quick questions:
- What's the meeting? ("1-1 with Aarav")
- Who's attending? ("Dan, Aarav")

Then invokes `take-notes` and opens a capture session.

### During the meeting

You're now in `take-notes` mode. Feed raw, terse observations. Don't worry about sentences — just capture the signal:

```
aarav taking on mcp adapter work
q2 deadline - kong vs agentcore decision - he needs my input
headcount question - told him hold until ipo clarity
send him the architecture comparison doc
```

`take-notes` expands this in real time into structured notes with proper formatting, complete sentences, and section headers. You just keep talking.

When the meeting ends, say *"done"* or *"end notes."*

### After the meeting — no transcript

`pka-meetings` takes over:

1. **Routes the notes** — detects this is a 1-1 with Aarav, finds `knowledge/personnel/aarav/` in the Repo Map, proposes that destination. Confirms if you're not in hands-off mode.

2. **Links attendees** — adds `[Aarav](../personnel/aarav/)` under `## Attendees` at the bottom of the note.

3. **Extracts action items** — finds "send him the architecture comparison doc", formats it as:
   ```
   - [ ] Send Aarav architecture comparison doc — @Dan
   ```
   Asks: "Found 1 action item. Add to session log open threads?"

4. **Files and indexes** — saves to `knowledge/personnel/aarav/2026-03-31-1-1-aarav.md`. Updates `search_fts`. Next time you search for Aarav or MCP or architecture comparison, this note surfaces.

5. **Reports**: "Filed to `knowledge/personnel/aarav/2026-03-31-1-1-aarav.md`. 1 attendee linked. 1 action item found."

Total post-meeting overhead: ~30 seconds of confirmation.

### After the meeting — with a Zoom/Teams transcript

You have a transcript. Drop it in `team-inbox/`:

```bash
cp ~/Downloads/GMT20260331-meeting.transcript.vtt ~/pka/team-inbox/
```

Then from `~/pka/`:

*"Reconcile my Aarav 1-1 notes against the transcript in team-inbox."*

`pka-meetings` finds both files and invokes `resolve-against-transcript`. That skill reads both documents and identifies:
- Things in the transcript not captured in your notes
- Things your notes got wrong (wrong attribution, wrong number, misremembered decision)
- Direct quotes worth adding

The reconciled notes come back corrected and complete. `pka-meetings` then runs the same post-processing: route, link, extract action items, file, index.

For the transcript: *"What do you want to do with it?"*
- Keep in team-inbox
- Archive to `knowledge/personnel/aarav/transcripts/`
- Delete (with confirmation)

### If you called take-notes directly

If you used `/thinkkit:take-notes` without going through `pka-meetings`, that's fine — the notes exist somewhere. Just say from `~/pka/`:

*"File my meeting notes from the Aarav 1-1."*

`pka-meetings` finds the file and runs the full post-processing pipeline from that point.

---

## Part 5: The Dashboard

No Claude Code session needed. Just open it:

```bash
open -a "Google Chrome" ~/pka/dashboard.html
```

What you see:
- **Personnel** section — card per person in `knowledge/personnel/`, sorted by last modified. Click a card to see their notes.
- **Leadership** section — timeline view (because it's tagged `meeting-home`) of meeting and strategy notes, sorted by date extracted from filenames.
- **Research** section — topic list from `knowledge/research/`, each topic linking to its `research.md` and `research.pdf`.
- **Projects** section — card per active project with status badge, days since last activity, and top-level doc count. Projects flagged as archiving appear prominently.
- **Activity** — last 20 entries from `session-log.md`. Your work diary, automatically maintained.
- **Search** — full-text search across everything indexed. Searches `search_fts` across both `knowledge/` and projects.

When it feels stale or you want something different:

From `~/pka/`, say: *"Update the dashboard — add a timeline view for my lab-notebook entries."*

The skill reads the existing `dashboard.html`, adds the lab-notebook section, leaves everything else alone. Double-click to see it updated.

---

## Part 6: Working Inside a Project

Nothing changes here from your current workflow.

```bash
cd ~/pka/projects/satori
claude
```

Satori's `CLAUDE.md` loads. That's the context. PKA is not active. You have the full thinkkit suite available here too — `/thinkkit:boardroom` to pressure-test a decision, `/thinkkit:ciso-review` on a vendor, `/thinkkit:explore-with-me` to think through a problem.

If you have a meeting specifically about Satori work, you have two routing choices:

1. **Route to the project:** *"File these Satori meeting notes in the project."* They go to `projects/satori/` for now — useful while work is active.

2. **Route to knowledge:** *"File these Satori meeting notes in knowledge."* They go to `knowledge/leadership/` or wherever your Repo Map says Satori-related leadership notes live. Better for 1-1s where Satori is one topic among many.

`pka-meetings` will ask when it detects a project match. You choose.

---

## Part 7: Transitioning a Completed Project

You've decided `operating_model` is done. The 90-day transition plan was presented to CTO staff and is now historical record.

From `~/pka/`:

*"Transition operating_model to knowledge."*

**Step 1: The summary**

The orchestrator reads `projects/operating_model/CLAUDE.md` and all the top-level markdown files. Generates:

```markdown
# Operating Model — Project Summary
**Period:** Oct 2025 – Feb 2026
**Transitioned:** 2026-03-31

## What It Was
Org design work for Satori/Foundry operating structure. Produced a suite of 
six executive documents: charter, RACI, social contract, 90-day transition plan.

## Key Decisions
- Matrix accountability model with ring-fenced resources
- Social contract between STO and product as governing document

## Outcomes
Six published documents. Presented to CTO staff.

## Documents Worth Reading
- `01-executive-brief.md` — the one-pager
- `04-sto-social-contract.md` — the binding governance doc

## Related Knowledge
- `knowledge/leadership/` — SLT context during this period
```

Saved to `owner-inbox/operating_model-summary-draft.md`. You review it. Add anything that's missing. Say *"approved."*

**Step 2: Cleanup and move**

> Found build artifacts to delete: `node_modules/` (274 files), `mermaid-filter.err`, 6 Word temp files. Delete these before moving? (12 MB)

*"Yes."*

> Deleted. Moving to `knowledge/projects/operating_model/`. Running content index pass... done. Repo Map updated. `operating_model` is now fully searchable in your knowledge base.

Six months from now, *"find everything I have on org design and social contracts"* will surface those six documents alongside everything else in your knowledge base. That's the payoff.

---

## Part 8: The Session Rhythm

Over time a natural rhythm develops.

**Morning:** `cd ~/pka && claude`. The orchestrator reads the last 20 session log entries and greets you with open threads, inbox items, and any stale project flags. Takes 20 seconds. You know where you are.

**During the day:** Drop files into `team-inbox/` as they arrive. Run `cd ~/pka/projects/<n>/ && claude` for project work, exactly as before. For meetings — capture with `pka-meetings`, let it handle the filing.

**End of week:** *"Give me a project status summary."* Optionally: *"What action items do I have from meetings this week?"* The session log is your work diary; you never had to write it.

**Occasionally:** *"Update my dashboard"* after structural changes. *"What projects are winding down?"* when you want to do maintenance. *"Re-index my knowledge base"* if search feels stale after adding a lot of new content.

---

## Part 9: Common Queries Reference

### Finding things

| You say | What happens |
|---------|-------------|
| "What do I know about `<person>`?" | Looks in personnel/ and finds all mentions |
| "Find everything about `<topic>` across all my work" | Full-text search across knowledge/ and projects/ |
| "What's the current state of `<project>`?" | Reads project's CLAUDE.md and top-level docs |
| "Show me everything from `<year>`" | Searches by date range in file metadata |
| "What did I decide about `<topic>`?" | FTS search + surfaces decision-language in results |

### Meetings

| You say | What happens |
|---------|-------------|
| "I'm in a meeting / take notes" | Opens capture session; routes on completion |
| "File my meeting notes" | Routes existing notes to correct knowledge/ location |
| "I have a transcript" | Reconcile + route pipeline |
| "What action items do I have this week?" | Surfaces `- [ ]` items from recent meeting notes |
| "Reconcile against the transcript in team-inbox" | Finds transcript + notes, runs resolution |

### Managing the system

| You say | What happens |
|---------|-------------|
| "Process my team-inbox" | Routes docs; holds transcripts for pka-meetings |
| "Re-index my knowledge base" | Incremental update of SQLite index |
| "Update my dashboard" | Surgical edit to dashboard.html |
| "Transition `<project>` to knowledge" | Full lifecycle workflow |
| "What projects are winding down?" | Surfaces 60+ day stale projects |
| "Add a `<role>` to my team" | Researcher profiles role; writes .pka/roles/ file |

---

## Part 10: What's Different

Before this system, you had files and you had to know where they were. The tool (Obsidian, Notion, Heptabase) sat in front of those files and made them look organized — but the tool owned the interface. When you wanted to search across a meeting note, a 1-1 note, and a strategy doc in three different apps, you couldn't.

Now you have files and you can just ask about them. The interface is conversation. The index is SQLite over files you own. The AI is the navigation layer, not a product you're locked into.

The meeting workflow specifically: before, notes from a 1-1 with Aarav might live in one app, the transcript in another, the action items maybe written on paper or in a third tool. Now they flow: capture → reconcile → file → index → link. One command surfaces everything connected to that person across two years of notes.

When Claude gets replaced by something better — and it will — you swap the brain. The files don't move. The index rebuilds in 30 seconds. The 1,300 notes you've accumulated stay exactly where they are and mean exactly what they meant.

That's the system.

