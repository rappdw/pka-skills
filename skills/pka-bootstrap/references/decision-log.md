# Decision Log

A lightweight record of significant decisions made within the PKA system. Complements
the session log (which tracks *what happened*) by capturing *why* a choice was made
and what alternatives were considered.

---

## Purpose

The session log records actions. The decision log records reasoning. When a future
session needs context on why something is the way it is — why a project was archived
early, why a folder was reorganized, why a role was added — the decision log has the
answer without requiring the user to remember.

---

## File Location

`.pka/decision-log.md` — created at bootstrap alongside `session-log.md`.

---

## Entry Format

```markdown
## YYYY-MM-DD | <decision title>

**Context:** <what prompted this decision — 1-2 sentences>
**Decision:** <what was decided>
**Alternatives considered:** <what else was on the table, if anything>
**Decided by:** <owner / @role / mutual>
**Relates to:** <folder, project, or topic affected>
```

### Example Entries

```markdown
## 2026-03-31 | Archive the Lyra project

**Context:** No file changed in 60+ days, deliverables shipped, Sam confirmed it's done.
**Decision:** Transition to knowledge archive with full summary.
**Alternatives considered:** Keep active as reference workspace — rejected because
it clutters the Repo Map and the summary captures everything needed.
**Decided by:** Sam
**Relates to:** projects/lyra → knowledge/archive/lyra

## 2026-04-01 | Switch to index mode

**Context:** Knowledge base crossed 400 files after ingesting research backlog.
**Decision:** Enable SQLite index mode for faster search.
**Alternatives considered:** Stay markdown-only — rejected because search across
400+ files was noticeably slow.
**Decided by:** @orchestrator recommendation, Sam approved
**Relates to:** .pka/knowledge.db

## 2026-04-02 | Add @analyst role

**Context:** Sam is doing weekly data reviews and wants structured output.
**Decision:** Add a data analyst role specializing in metrics summaries.
**Alternatives considered:** Extend @researcher — rejected because the working
style (weekly cadence, dashboard-like output) is distinct enough.
**Decided by:** mutual
**Relates to:** .pka/roles/analyst.md
```

---

## When to Log a Decision

Not every action needs a decision log entry. Log when:

- **A structural change** is made (folder reorganization, archive/restore, mode switch)
- **A role is added or modified**
- **The autonomy level is changed** (`## Autonomy Level` in `CLAUDE.md` is updated in the same turn)
- **A non-obvious routing choice** is made (file could go to multiple destinations)
- **The user overrides a recommendation** (captures the reasoning for next time)
- **A policy is established** ("always route 1-1 notes to personnel, not meetings")

Do NOT log routine actions like filing a document to an obvious destination or
running a standard session start.

The entry is appended when the decision is made, in the same turn, not saved up
for session end. Entries go at the end of the file, oldest first. An earlier
entry is never edited or deleted: a reversal is a new entry that names the one
it replaces. In a workspace that has no `.pka/decision-log.md`, the first entry
creates it under a `# Decision Log` heading.

---

## Integration with Bootstrap

At bootstrap, the decision log is seeded with the initial setup decisions:

```markdown
## {{date}} | PKA bootstrap

**Context:** First-run setup of Personal Knowledge Assistance system.
**Decision:** {{storage_mode}} storage, {{autonomy_level}} autonomy, archive to `{{archive_destination}}`.
**Alternatives considered:** N/A — initial setup.
**Decided by:** {{name}}
**Relates to:** entire PKA system
```

---

## How Roles Use the Decision Log

The rules live in the role seeds (`role-definitions.md`, section "Owner profile and
decision log" of each role) and in the `CLAUDE.md` template; this is the summary.

| Role | Writes | Reads |
|---|---|---|
| **@orchestrator** | structural and lifecycle decisions, roles added or changed, autonomy changes, policies, a recommendation the owner overrode | before recommending a structural change, a lifecycle action or a policy; when the owner asks why something is the way it is |
| **@librarian** | a routing policy the owner sets, or an override of a routing proposal that should hold next time | before proposing where a kind of file goes: a recorded policy wins over inference |
| **@researcher** | nothing | when a brief covers the history of a project or a choice; it cites the entry by date and title |

The log is read on demand, never at session start: list the titles with
`grep -n '^## ' .pka/decision-log.md` and read the entries that bear on the question.
