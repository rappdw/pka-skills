---
name: pka-tutorial
description: >
  ALWAYS use this skill when the user is new to PKA, asks for a tour, walkthrough,
  tutorial, onboarding, or says they don't know how to use their PKA system.
  Triggers on: "I just installed PKA", "how do I use this", "what can I do with this",
  "walk me through PKA", "teach me how this works", "give me a tour", "I'm new here",
  "what are my options", "how do I find things", "show me the ropes", "help me get
  started", or any confusion about where to begin. Also use when a user asks how to
  do a specific PKA task for the first time (how to capture meetings, drop files,
  use the dashboard, transition a project) — the skill teaches the workflow with
  concrete examples rather than just executing. Adapts to the user's current PKA
  state: offers a full tour if bootstrapped, points to pka-bootstrap if not.
user-invocable: true
argument-hint: "[topic or 'tour']"
allowed-tools: Read, Bash, Glob, Grep
---

# pka-tutorial

Conversational onboarding and capability walkthrough for a Personal Knowledge
Assistance system. Teaches new users how PKA works through concrete examples
grounded in their actual repo, and answers "how do I…" questions with hands-on
guidance.

## Purpose

The static tutorial at `docs/TUTORIAL.md` is a reference document. This skill is
the **interactive** counterpart: it meets the user where they are, figures out
what they want to learn, and walks them through with prompts they can try right
now. It never executes destructive actions — it teaches by demonstration and
hand-off.

## Trigger Phrases

- "I just installed PKA / I'm new to this"
- "Give me a tour / walk me through PKA"
- "How do I use this system?"
- "What can PKA do?"
- "Teach me how to capture meetings / find things / use the dashboard"
- "How do I drop files into the system?"
- "What are my options here?"
- Any question that starts with "how do I…" about PKA functionality

---

## Pre-Flight

Before teaching anything, detect the user's state:

1. **Is PKA bootstrapped?** Check for `.pka/` and `CLAUDE.md` at cwd or parent.
2. **Which skills are available?** Check for `pka-bootstrap`, `pka-librarian`, `pka-interface`, `pka-meetings` in the environment.
3. **Is thinkkit installed?** Check for `take-notes` and `resolve-against-transcript`.
4. **What's in the Repo Map?** If bootstrapped, read `CLAUDE.md` to ground examples in the user's actual folder names.
5. **Storage mode?** Index or markdown-only — affects what the user can do.

### State-based entry

| State | Opening |
|-------|---------|
| Not bootstrapped | "PKA isn't set up yet in this folder. Want me to hand you off to `pka-bootstrap` to get started? Once that's done, come back and I'll give you the tour." |
| Bootstrapped, first session | "Welcome. I can give you the full tour (about 7 minutes of reading, with prompts you can try as we go), or jump to something specific — finding things, dropping files, meetings, the dashboard, project lifecycle, roles, topic wikis, or health checks. What sounds useful?" |
| Bootstrapped, returning user | "What would you like to learn about? I can cover: finding things, the team-inbox, meeting capture, the dashboard, project lifecycle, the role system, topic wikis, or health checks." |

---

## The Curriculum

Organized into 9 modules. Each is independently useful — users can skip around.
See `references/curriculum.md` for full module scripts with example prompts.

### Module 1: Orientation (2 min)

**Goal:** User understands what PKA is and how it's different from Obsidian/Notion.

Covers: files-first philosophy, the Repo Map, roles, session log, autonomy level,
vendor-agnostic output. Uses the user's actual Repo Map as a concrete example.

### Module 2: Finding Things (3 min)

**Goal:** User can ask questions of their knowledge base in natural language.

Covers: simple lookup, cross-repo search, project status, date-range queries.
Shows 3-4 example prompts using folder names from the user's Repo Map. Offers:
"Want to try one now?"

### Module 3: The Inbox Pattern (2 min)

**Goal:** User understands how to get files into the system.

Covers: `team-inbox/` as input queue, `owner-inbox/` as output queue, routing
proposals, transcript special-casing, batch processing. Walks through what
happens when a PDF is dropped.

### Module 4: Meeting Capture (4 min)

**Goal:** User can capture, reconcile, and file a meeting end-to-end.

Covers the three modes (capture, reconcile, route-only), the take-notes flow
with terse observations, post-meeting routing, attendee linking, action item
extraction. If thinkkit isn't installed, explains route-only mode and points
the user to thinkkit for full capture.

### Module 5: The Dashboard (2 min)

**Goal:** User knows how to generate and update their dashboard.

Covers: `dashboard.html` at root, view types (cards, timeline, topics,
calendar), the update pattern, search. Shows how to ask for a new section.

### Module 6: Project Lifecycle (3 min)

**Goal:** User understands how projects transition from active work to archived
knowledge.

Covers: active project workspaces, stale detection, transition workflow,
summary generation, the reverse-transition case. Emphasizes the "payoff" —
archived projects become searchable alongside knowledge.

### Module 7: The Role System (2 min)

**Goal:** User knows how to delegate work and extend their team.

Covers: seed roles (orchestrator, researcher, librarian), @mention syntax,
role files in `.pka/roles/`, how to add a new role, communication style
adaptation from the owner profile.

### Module 8: Topic Wikis (3 min)

**Goal:** User understands the synthesis layer and knows when to use it.

Covers: authored moments vs. synthesis pages, when to create a wiki, the
ingest workflow (source → synthesis diff → user review → merge),
query-with-wiki behavior, `[[wikilinks]]`, `knowledge/topics/` convention.
Emphasizes that wikis cite notes, never replace them.

If `pka-wiki` isn't installed, flags it: "Topic wikis require `pka-wiki` —
install it and come back for this module."

### Module 9: Health Checks (2 min)

**Goal:** User can run lint and act on the report.

Covers: what lint catches (orphans, broken links, stale wiki sources,
contradiction candidates, uncited claims), weekly/monthly cadence, reading
the report in `owner-inbox/`, lint is never destructive. Points to
`pka-librarian` for execution.

---

## Teaching Style

- **Ground every example in the user's actual Repo Map.** Don't say "search for 'Aarav'" — say "search for someone in your `<personnel-folder-name>/` folder". Use real folder names.
- **Keep it conversational.** No walls of text. Present one idea, give an example prompt, ask "want to try it?" before moving on.
- **Hand off, don't execute.** When the user wants to actually do something, describe the prompt they should say next. Don't perform the action inside the tutorial.
- **Respect abandonment.** If the user asks a real question mid-tutorial, stop teaching and answer it. The tour is optional.
- **Short modules.** Each module should be completable in 2-4 minutes of reading.

## What This Skill Does NOT Do

- **Does not execute destructive actions.** Never moves files, deletes anything, or modifies CLAUDE.md. It can read files to ground examples, nothing more.
- **Does not replace `pka-bootstrap`.** If PKA isn't set up, hands off.
- **Does not replicate `docs/TUTORIAL.md` verbatim.** That file is a reading reference. This skill is an interactive guide that adapts to user state and answers follow-up questions.

---

## Closing

At the end of any tour or module, offer:

> Want to try what we just covered? Or should I explain a different part? You can also say *"show me the reference tutorial"* and I'll open `docs/TUTORIAL.md` for a full written walkthrough.

Log the tutorial session to `session-log.md`:

```
## YYYY-MM-DD HH:MM | pka-tutorial | Walkthrough: <modules covered> | — | User ready for <next action>
```

See `references/example-prompts.md` for the full library of try-this prompts by module.
