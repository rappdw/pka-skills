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
  or mentions a specific meeting like "1-1 with Aarav" or "SLT planning".
  Orchestrates thinkkit take-notes and resolve-against-transcript when available.
  Handles smart routing, attendee linking, and action item extraction. Works
  standalone for routing if thinkkit is not installed.
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
- Both absent: the skill functions as a PKA-aware meeting note router only

## Pre-Flight

1. Load `.pkaignore` and Repo Map from `CLAUDE.md`
2. Check for `take-notes`: `ls .claude/skills/take-notes/ 2>/dev/null`
3. Check for `resolve-against-transcript`: `ls .claude/skills/resolve-against-transcript/ 2>/dev/null`
4. Check for `.pka/knowledge.db`
5. Scan `team-inbox/` for transcript files (patterns in `references/transcript-patterns.md`)

If thinkkit skills are absent, report which modes are unavailable but proceed with route-only mode.

## Mode 1: Capture (Live Note-Taking)

**Trigger:** User says they're in a meeting, or says "take notes", or invokes `/thinkkit:take-notes` with PKA context active.

1. Ask: "What's this meeting?" and "Who's attending?"
2. Invoke `take-notes` — user feeds terse observations; skill expands into structured notes
3. Retrieve output notes file
4. Run Post-Processing Pipeline

## Mode 2: Reconcile Against Transcript

**Trigger:** User mentions a transcript, or a transcript file is detected in `team-inbox/`.

1. Identify transcript (from team-inbox/ detection or user-specified path)
2. Find matching notes (today's notes, or ask user to specify; if none: offer to generate notes from transcript directly)
3. Invoke `resolve-against-transcript` with notes + transcript
4. Run Post-Processing Pipeline
5. Ask about transcript disposition: keep in team-inbox/ / archive to knowledge destination / delete (confirm before delete)

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

See `references/attendee-linking.md` for matching logic.

For each attendee extracted from notes:
- Fuzzy match against Repo Map personnel folder names (first name, last name, slug)
- If match: add relative path reference under `## Attendees` at bottom of notes
- If no match: list name without link

### Step 3 — Action item extraction

See `references/action-item-patterns.md` for detection patterns.

Scan notes for:
- Lines starting with `- [ ]`, `→`, `AI:`, `Action:`, `TODO:`
- Sections `## Action Items`, `## Next Steps`, `## Follow-up`

Normalize into `## Action Items` section at bottom:
```
- [ ] <action> — @<owner if mentioned> — <due date if mentioned>
```

Surface to user: "Found N action items. Add to session log open threads?"

### Step 4 — Save to destination

File naming: `<YYYY-MM-DD>-<meeting-slug>.md`
- slug from title: lowercase, hyphens, max 40 chars
- Examples: `2026-03-31-1-1-aarav.md`, `2026-03-31-slt-q2-planning.md`
- Duplicate handling: append `-2`, `-3` suffix

### Step 5 — Update SQLite index

Insert into `file_index`, per-folder index table (if exists for destination), `search_fts` with full note content.

### Step 6 — Write to session-log.md

```
## YYYY-MM-DD HH:MM | pka-meetings | Filed: <title> → <path> | Action items: N | <open threads if any>
```

If action items added to log:
```
## YYYY-MM-DD HH:MM | pka-meetings | Open: <action> | — | —
```

### Step 7 — Confirm and summarize

Report: filed to path, attendees linked (N of M), action items found (list), transcript disposition.

## Transcript Detection at Session Start

The PKA orchestrator's session-start scan flags transcript files in `team-inbox/` and surfaces them:

> "Found a transcript in team-inbox: `GMT20260331-162935_Recording.transcript.vtt`. Do you have notes to reconcile against it, or should I generate notes from the transcript directly?"

## Key Constraints

- Transcript disposition always asked — never auto-deleted
- Project meeting routing always asks before routing to active project workspace
- Degrades gracefully when thinkkit skills are absent
- Never writes to project workspaces without asking
