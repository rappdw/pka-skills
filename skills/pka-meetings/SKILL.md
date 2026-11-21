---
name: pka-meetings
description: >
  ALWAYS use this skill when the user mentions meetings, meeting notes, taking
  notes, transcripts, action items from meetings, or filing/routing meeting
  documentation. Triggers on: starting a meeting, taking notes during a meeting,
  1-1s with anyone, reconciling notes against a transcript, filing or routing
  meeting notes to the right folder, processing a Zoom/Teams transcript,
  extracting action items from meetings, asking what action items they have,
  capturing meeting decisions, or any meeting-related documentation task. Use
  this even when the user just says "I'm in a meeting", "take notes", "file
  these notes", "I have a transcript", "what are my action items this week",
  or mentions a specific meeting like "1-1 with Priya" or "SLT planning".
  Orchestrates thinkkit take-notes and resolve-against-transcript when available.
  Works standalone for routing if thinkkit is not installed. A question about
  how meeting capture works goes to pka-tutorial.
user-invocable: true
argument-hint: "[meeting context or file]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# pka-meetings

Full meeting documentation pipeline for a Personal Knowledge Assistance system.

## Integration Boundary

`pka-meetings` orchestrates thinkkit skills when available, but the boundary is clear: thinkkit handles *capture and reconciliation*; PKA handles *routing, indexing, attendee linking, and persistence*. Neither repo modifies the other. thinkkit remains fully functional without PKA installed.

```
thinkkit                              PKA
────────                              ───
take-notes ──────────────────────▶  pka-meetings ──▶ knowledge/
                                          │
resolve-against-transcript ──────▶        ├──▶ .pka/session-log.md
                                          └──▶ .pka/knowledge.db
```

## Prerequisites

Both thinkkit and pka-skills should be installed. `pka-meetings` checks for thinkkit skills at startup and degrades gracefully if absent:
- No `take-notes`: the skill still handles routing, indexing, and logging of manually-written notes
- No `resolve-against-transcript`: the skill skips reconciliation and routes notes as-is
- Both absent: the skill functions as a PKA-aware meeting note router, and can still write notes from a transcript when the user asks (below)

Writing notes from a transcript when there are none does **not** need thinkkit. thinkkit has no skill for it (`take-notes` works from what the user types during the meeting; `resolve-against-transcript` needs notes to check), so this is PKA's own step and works the same with or without thinkkit. See "Notes from a transcript" under Mode 2.

## Pre-Flight

1. Load `.pkaignore` and Repo Map from `CLAUDE.md`
2. Check for `take-notes`: look in this session's list of available skills for `take-notes` or `thinkkit:take-notes`. Plugin-installed skills carry the plugin prefix and are **not** copied under `.claude/skills/`, so the skill list is the source of truth. Only if the list cannot be consulted, fall back to the filesystem: `ls .claude/skills/take-notes/ ~/.claude/skills/take-notes/ 2>/dev/null`.
3. Check for `resolve-against-transcript` the same way (`resolve-against-transcript` or `thinkkit:resolve-against-transcript`).
4. Check for `.pka/knowledge.db`
5. Scan `team-inbox/` for transcript files (patterns in `references/transcript-patterns.md`)
6. Scan for earshot capture directories — any directory containing a `meeting.json` marker file (typically under `meeting-notes/`, but the check is marker-based, not path-based; see `references/transcript-patterns.md`). A capture containing `transcript.md` with no reconciled note yet is a Mode 2 candidate, same as a detected Zoom transcript.

If thinkkit skills are absent, report which modes are unavailable but proceed with route-only mode.

## Mode 1: Capture (Live Note-Taking)

**Trigger:** User says they're in a meeting, or says "take notes", or invokes `/thinkkit:take-notes` with PKA context active.

1. Ask: "What's this meeting?" and "Who's attending?"
2. Invoke `take-notes` — user feeds terse observations; skill expands into structured notes
3. Retrieve output notes file
4. Run Post-Processing Pipeline

## Mode 2: Reconcile Against Transcript

**Trigger:** User mentions a transcript, a transcript file is detected in `team-inbox/`, or an earshot capture directory with an unreconciled `transcript.md` is detected.

1. Identify transcript (from team-inbox/ detection, an earshot capture's `transcript.md`, or user-specified path)
2. Find matching notes (today's notes, or ask user to specify; if none: offer to write notes from the transcript, see "Notes from a transcript" below). For earshot captures, prefer the notes file whose `**Recording**:` header points at the capture directory.
3. Invoke `resolve-against-transcript` with notes + transcript. Without that skill, say that reconciliation needs thinkkit and is being skipped, and go on with the notes as they are. Skip this step too when the notes were just written from the transcript: there is nothing independent to check them against.
4. Run Post-Processing Pipeline
5. Ask about transcript disposition: keep in team-inbox/ / archive to knowledge destination / delete (confirm before delete). **Applies to loose team-inbox/ transcripts only** — earshot capture artifacts stay inside their capture directory; never offer to move or delete them.

### Notes from a transcript

For a transcript with no notes. PKA does this itself; thinkkit is not needed and not involved.

1. **Offer, never assume.** "There are no notes for this transcript. Shall I write them from it?" A detected transcript is not a request.
2. On a yes, read the transcript and write the notes in the structure thinkkit uses, so everything downstream treats them like any other notes: a title, `**Date**`, `**Attendees**` and `**Purpose**` header lines, then `## Notes`, `## Action Items` and `## Open Questions`.
3. Add one header line that says where they came from: `**Source**: written from transcript <transcript filename>, not checked against notes taken in the meeting`.
4. Keep to the transcript. Attribute a statement to a speaker only as the transcript labels them; where it says "Speaker 2", write that and ask the user who it is rather than guessing. An action item needs someone in the transcript committing to it. Leave out what cannot be made out.
5. Save to `meeting-notes/<YYYY-MM-DD>-<slug>.md` (the date is the transcript's), show the user the draft, and run the Post-Processing Pipeline when they are happy with it.

On a no, leave the transcript where it is and ask about its disposition only if the user wants to deal with it now.

**Ordering:** reconciliation (and narration, if the user runs earshot's `/meeting-narrative`) happens **before** routing, while the notes are still in `meeting-notes/` — meeting-narrative finds notes by globbing there. If the user wants a narrative, suggest generating it now, before Step 4 moves the notes.

## Mode 3: Route Only

**Trigger:** User provides an existing notes file or says "file these meeting notes".

Skip directly to Post-Processing Pipeline with the provided notes file.

## Post-Processing Pipeline

Runs after any capture or reconciliation, or directly for route-only mode.

### Step 1 — Infer meeting type and routing destination

Using meeting title, attendees, and Repo Map. See `references/meeting-routing-rules.md` for full logic.

Priority order:
1. **1-1 meeting** (title contains "1-1"/"one-on-one", or single attendee other than user) → `<personnel-folder>/<person>/` if that folder exists per Repo Map
2. **Active project meeting** (title or attendees match a known project slug) → ask: "Route to `projects/<n>/` now, or to knowledge/ after the project wraps up?"
3. **Leadership/strategy** (strategic keywords in title, or executive attendees) → `meeting-home`-tagged leadership folder per Repo Map
4. **General** → any `meeting-home`-tagged folder; if none, ask

Present proposed destination. Confirm before moving (except hands-off autonomy).

### Step 2 — Attendee linking

See `references/attendee-linking.md`.

Resolve every attendee name with the registry, never by eye:

```
.pka/bin/pka-tools people resolve "<name>" "<name>" …
```

- **high** → link it under `## Attendees` (`- [Priya](../personnel/priya/)`), and use the slug in the frontmatter `attendees` list. A new `## Attendees` section is appended at the end of the note, after every section already there; an existing one is used where it is.
- **ambiguous** → ask the user which of the candidates they mean. Never pick.
- **none** → list the name without a link.

When the user settles a nickname or an ambiguous name ("Rob is Robin Smith"), offer once to remember it: `.pka/bin/pka-tools people alias robin-smith "Rob"`.

### Step 3 — Action item extraction

See `references/action-item-patterns.md` for detection patterns.

Scan notes for:
- Lines starting with `- [ ]`, `→`, `AI:`, `Action:`, `TODO:`
- Sections `## Action Items`, `## Next Steps`, `## Follow-up`

**Items that are already checkboxes are never rewritten.** A `- [ ]` line stays byte for byte as it was written, wherever it is in the note and whichever form it uses, including thinkkit's `- [ ] **Robin**: Draft the Q1 hiring plan (due: 2026-12-01)`. `pka-tools actions` reads that form and PKA's own, so there is nothing to convert.

Only items found in the other patterns (an `Action:` line, a `→` line, a bullet under `## Next Steps`) are added, to the `## Action Items` section (created at the bottom if the note has none), one line each, in PKA's form:
```
- [ ] <action> — @<owner if mentioned> — by <YYYY-MM-DD if a due date was mentioned>
```
Skip an item the section already lists in any form.

Surface to user: "Found N action items. Add to session log open threads?"

### Step 4 — Save to destination

File naming: `<YYYY-MM-DD>-<meeting-slug>.md`
- slug from title: lowercase, hyphens, max 40 chars
- 1-1 notes: `<YYYY-MM-DD>-1-1-<person-slug>.md`, in the person's folder. Existing 1-1 notes in other forms (`-1on1`, `-1-on-1`, with or without a name) are recognised as they are and never renamed.
- Examples: `2026-03-31-1-1-priya.md`, `2026-03-31-slt-q2-planning.md`
- Duplicate handling: append `-2`, `-3` suffix

**Never move earshot capture directories.** Routing files the notes only; the capture directory (audio, `transcript.*`, `narrative.md`) stays where earshot wrote it. If the notes carry a `**Recording**: <capture-dir>` header (added by thinkkit's take-notes), preserve that line verbatim when moving or rewriting the notes — it stays valid precisely because the capture directory doesn't move.

### Step 5 — Post-route: frontmatter, MOC, pointer row, timeline, index

Once the note is saved, run the same command the librarian runs after a route, so a meeting note gets exactly what a routed document gets:

```
.pka/bin/pka-tools post-route <path to the filed note> [--topic <slug>]
```

In order: frontmatter and a `- [[note]]` bullet in its folder's `_MOC.md` (when `obsidian_present`), a pointer row, **a line on each attendee's timeline**, and the index (index mode). Nothing is committed: the note and the files `post-route` changed are left in the working tree for the user. Pass `--topic` when the meeting belongs to a known pointer cluster (an ongoing series, a project).

**Timeline summaries.** You have the note in front of you, so write the summary for each person's line: at most 140 characters, drawn only from the note — the decisions, and what *that person* owns. For a 1-1, list the topics only (no judgements about the person). Pass them as `--summary-for <slug>="…"` per person, or `--summary "…"` for one summary for everyone:

```
.pka/bin/pka-tools post-route knowledge/leadership/2026-11-14-slt-sync.md \
    --summary-for priya="Owns the adapter spike; vendor decision deferred" \
    --summary-for robin-smith="Drafts the Q1 hiring plan"
```

Who goes on a timeline is decided by the tool from the note (the person's folder, `person` / `attendees` frontmatter, `## Attendees` links, the filename) — see `.pka/bin/pka-tools timeline who <note>`. Meetings with more than 8 resolved attendees add none of them unless the user asks (`--include-large`). In "ask before everything" mode, run `post-route … --dry-run` first and show the timeline lines in the confirmation. Relay any step that reports `skipped` or `nobody` with its reason (a large meeting reports `timeline nobody`), and a `Note: not committed…` line if the summary has one.

If the meeting has an earshot capture with a `narrative.md`, index the narrative in place as well — it is the richest artifact for the meeting, and its capture directory never moves:

```
.pka/bin/pka-tools index <capture-dir>/narrative.md
```

(`post-route` refuses files inside a capture directory, by design: captures are never routed.) In markdown-only mode the index steps are skipped by the tool. If the tool is missing, or reports that the index needs `db migrate`, say so and suggest `bootstrap upgrade`; do not fall back to manual inserts, table edits or `git add`.

### Step 6 — Write to session-log.md

One entry for the note:

```
.pka/bin/pka-tools log add --role pka-meetings --summary "Filed <title> → <path>" [--next "<next action>"]
```

Add `Narrative: <capture-dir>/narrative.md` to the summary when a narrative was indexed.

If the user agreed to add action items to the log, one entry per item, with the item in the **open-threads** field — that is the field the session-start greeting reads:

```
.pka/bin/pka-tools log add --role pka-meetings --summary "Action item from <note filename>" --open "<action> — @<owner>[ — by <date>]"
```

The tool writes the grammar (`## YYYY-MM-DD HH:MM | role | summary | open threads | next action`) and escapes any `|` in the text.

### Step 7 — Confirm and summarize

Report: filed to path, attendees linked (N of M), action items found (list), transcript disposition.

## Transcript Detection at Session Start

The PKA orchestrator's session-start scan flags transcript files in `team-inbox/` and surfaces them:

> "Found a transcript in team-inbox: `GMT20260331-162935_Recording.transcript.vtt`. Do you have notes to reconcile against it, or should I write notes from the transcript?"

Without thinkkit's `resolve-against-transcript` the first half of that offer cannot be kept, so say what is possible: "…I can file notes you already have as they are (checking them against the transcript needs thinkkit), or write notes from the transcript."

Unreconciled earshot captures are surfaced the same way:

> "Found an earshot capture with an unreconciled transcript: `meeting-notes/2026-07-02_140000_slt-sync/`. Reconcile your notes against it?"

## Key Constraints

- Transcript disposition always asked — never auto-deleted
- Earshot capture directories (marked by `meeting.json`) are never moved, renamed, or deleted — only the notes file routes
- `**Recording**:` header pointers in notes are preserved verbatim through routing and rewrites
- Reconcile (and narrate) before routing — notes must still be in `meeting-notes/` for earshot's meeting-narrative to find them
- Project meeting routing always asks before routing to active project workspace
- Degrades gracefully when thinkkit skills are absent: no live capture and no reconciliation, but routing, and notes written from a transcript on request, work without it
- Notes written from a transcript say so in a `**Source**:` header line and are never produced without the user's yes
- Never writes to project workspaces without asking
