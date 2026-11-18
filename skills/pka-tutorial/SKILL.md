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
  concrete examples rather than just executing. Also use for "what's new", "what
  changed in this release", "I just updated the plugin", "do I need to upgrade".
  Adapts to the user's current PKA state: points to pka-bootstrap if not set up;
  walks through `bootstrap upgrade` and then what is new if the workspace has not
  been upgraded on the installed release; otherwise offers the tour.
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
- "What's new? / What changed? / I just updated the plugin / Do I need to upgrade?"

---

## Pre-Flight

Before teaching anything, detect the user's state:

1. **Is PKA bootstrapped?** Check for `.pka/` and `CLAUDE.md` at cwd or parent.
2. **Which skills are available?** Check for `pka-bootstrap`, `pka-librarian`, `pka-interface`, `pka-meetings` in the environment.
3. **Is thinkkit installed?** Check for `take-notes` and `resolve-against-transcript`.
4. **What's in the Repo Map?** If bootstrapped, read `CLAUDE.md` to ground examples in the user's actual folder names.
5. **Storage mode?** Index or markdown-only — affects what the user can do.
6. **Has the workspace been upgraded on the installed release?** Only when bootstrapped. Ask the **plugin's** copies of the tools; neither command changes a file:
   ```
   python3 "<plugin root>/bootstrap-assets/tools/pka-tools" status --workspace <root> --json
   python3 "<plugin root>/bootstrap-assets/scripts/upgrade-roles.py" --workspace <root> --dry-run
   ```
   `<plugin root>` is the folder that holds this plugin's `skills/` and `bootstrap-assets/` — `${CLAUDE_PLUGIN_ROOT}` when the environment provides it, otherwise two directories above this skill's folder. `<root>` is the workspace root found in step 1; pass it explicitly, never `.` unless cwd is that root (from a subfolder, `.` describes the subfolder). Do not use the copies under `.pka/` for this check: they can only speak for their own version.
   - **Toolkit.** `tool_version` is the installed release. `vendored_version` is the release whose installer last ran here; `null` means no manifest (a workspace from before v1.7.0) or one that cannot be read. `null` or older: **behind**. Newer: **the plugin is behind** (the workspace was upgraded from another machine).
   - **Role files.** Equal versions say the toolkit is current, not that the upgrade ran: the librarian installs a missing toolkit on its own. If the `upgrade-roles.py` preview would seed a shared reference or add a section, the workspace is **behind** even when the versions are equal. Sections it lists only as "can be refreshed", or as obsolete and "can be removed", do not make it behind; mention them.
   - **Index.** `schema_current: false` with a `schema_version` lower than the tool expects means the migration was declined or never offered: **index not migrated**. A higher `schema_version` means the plugin is behind.
   - **Current** is: versions equal, nothing for the role preview to seed or add, and `schema_current` not `false`.
   - If `status` fails, relay its message. If it fails, or `python3` is missing or older than 3.9, compare `version` in `<plugin root>/.claude-plugin/plugin.json` with `plugin_version` in `.pka/manifest.json` (no file: before v1.7.0) by reading them. Tell the user that the upgrade itself needs Python 3.9 or newer.

### State-based entry

| State | Opening |
|-------|---------|
| Not bootstrapped | "PKA isn't set up yet in this folder. Want me to hand you off to `pka-bootstrap` to get started? Once that's done, come back and I'll give you the tour." |
| Bootstrapped, workspace behind the installed release | Before any tour: "Your workspace was last set up on `<vendored_version or 'a release before v1.7.0'>`; the installed PKA is `<tool_version>`. Some of what I would show you does not work here until it is upgraded. Want me to walk you through the upgrade first? It takes a few minutes and nothing changes until you say so." When the versions are equal and only the role files are behind, say that instead: "The toolkit here is current, but the role files have not been upgraded to `<tool_version>`." Then follow **Upgrade Walkthrough and What's New** below. |
| Bootstrapped, toolkit and roles current, index not migrated | "Your index was not migrated when this workspace was upgraded, so search and indexing are off. Say **bootstrap upgrade** and it will offer the migration again; it shows a plan and backs the database up first." No preview, no walkthrough. Then carry on as a returning user. |
| Bootstrapped, plugin behind the workspace | "This workspace was upgraded on `<vendored_version>`, but the PKA plugin installed here is `<tool_version>`. Update the plugin (`/plugin`, then update `pka-skills`) so the skills match the workspace." Do not suggest `bootstrap upgrade`: it would replace the workspace's newer toolkit with this older one. Then carry on as a returning user. |
| Bootstrapped, first session | "Welcome. I can give you the full tour (about 7 minutes of reading, with prompts you can try as we go), or jump to something specific — finding things, dropping files, meetings, the dashboard, project lifecycle, roles, topic wikis, or health checks. What sounds useful?" |
| Bootstrapped, returning user | "What would you like to learn about? I can cover: finding things, the team-inbox, meeting capture, the dashboard, project lifecycle, the role system, topic wikis, or health checks." When the workspace has been upgraded at some point (`.pka/upgrade-backups/` exists) and `.pka/session-log.md` has no `pka-tutorial` entry with `What's new in v<tool_version>`, put "what's new in v<tool_version>" first in that list. A workspace first set up on this release is not offered it; the tour covers everything. |

The last two rows are for a current workspace. For one that is behind, the upgrade comes first, with two exceptions:

- **The user asked one specific how-do-I question** ("how do I capture a meeting?"). Say in one sentence that the workspace is behind and that you can walk through the upgrade afterwards, then answer the question. Where the answer depends on something the workspace does not have yet, say so. "What's new?" and "do I need to upgrade?" are not exceptions: they are answered by the walkthrough.
- **The user says not now.** Carry on with what they asked for, name the modules that depend on the upgrade as you reach them, and do not raise it again this session.

---

## Upgrade Walkthrough and What's New

For a workspace that is behind. Full script in `references/upgrade-and-whats-new.md`. The tutorial explains and previews; `pka-bootstrap` performs the upgrade when the user asks for it.

1. **Say where they are.** The two versions, in one sentence (or that only the role files are behind).
2. **Preview, changing nothing.** Run the plugin's installer with `--dry-run` and read the result with the user, together with the role preview from pre-flight:
   ```
   python3 "<plugin root>/bootstrap-assets/tools/pka-tools" install --workspace <root> --dry-run
   ```
   Then describe the three things `bootstrap upgrade` does, in order, and what protects them at each one: the toolkit and helper scripts (in a workspace from before v1.7.0 the scripts it replaces are saved first; later, only files they never edited are replaced), the index migration (it asks first; the database is backed up), the role files (backed up; sections are added, theirs are not rewritten). Nothing is committed. It needs Python 3.9 or newer. If the preview fails, relay its message and stop the walkthrough there.
3. **Hand off.** "When you are ready, say **bootstrap upgrade**." If the user answers "go ahead" or "just do it", that is the request: say you are switching to `pka-bootstrap` and follow its Upgrade procedure, including the questions it asks. The tutorial's own steps never run the installer without `--dry-run`, `db migrate --apply`, or `upgrade-roles.py` without `--dry-run`.
4. **Read the result with them.** When the upgrade has run, run both pre-flight checks again and confirm the workspace is now current. Explain each line of the summary they were shown: where the backups are, any `<name>.new` files (their edited copy was kept; the new one is beside it), sections that can be refreshed, an index migration they declined. If the workspace is in git, tell them the changes are uncommitted and theirs to review.
5. **What's new.** Teach the capabilities that arrived between the release they were on and the installed one, from `references/upgrade-and-whats-new.md`. For a release that file has no section for, read its entry in `<plugin root>/CHANGELOG.md`. Leave out what does not apply to this workspace (no Obsidian vault, no index, no people folder), put each capability as what the user can now do, and give one prompt to try for each, using their folder names.
6. **Offer the rest.** The normal menu of modules.

If the user upgraded without the tutorial, steps 5 and 6 are the "what's new" item in the returning-user menu.

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

- **Ground every example in the user's actual Repo Map.** Don't say "search for 'Priya'" — say "search for someone in your `<personnel-folder-name>/` folder". Use real folder names.
- **Keep it conversational.** No walls of text. Present one idea, give an example prompt, ask "want to try it?" before moving on.
- **Hand off, don't execute.** When the user wants to actually do something, describe the prompt they should say next. Don't perform the action inside the tutorial.
- **Respect abandonment.** If the user asks a real question mid-tutorial, stop teaching and answer it. The tour is optional.
- **Short modules.** Each module should be completable in 2-4 minutes of reading.

## What This Skill Does NOT Do

- **Does not execute destructive actions.** Never moves files, deletes anything, or modifies CLAUDE.md. It reads files to ground examples; the one thing it writes is its session-log entry (see Closing).
- **Does not perform the upgrade.** It runs the three preview commands above (`status`, `upgrade-roles.py --dry-run`, `install --dry-run`), none of which changes a file, and hands off to `pka-bootstrap` for `bootstrap upgrade`.
- **Does not replace `pka-bootstrap`.** If PKA isn't set up, hands off.
- **Does not replicate `docs/TUTORIAL.md` verbatim.** That file is a reading reference. This skill is an interactive guide that adapts to user state and answers follow-up questions.

---

## Closing

At the end of any tour or module, offer:

> Want to try what we just covered? Or should I explain a different part? You can also say *"show me the reference tutorial"* and I'll open `docs/TUTORIAL.md` for a full written walkthrough.

Log the tutorial session to `.pka/session-log.md` with `log add --role pka-tutorial --summary "…" [--open "…"] --next "…"`: through `.pka/bin/pka-tools` when it exists, otherwise through the plugin's copy with `--workspace <root>`. One entry per session; when both a tour and the what's-new step were covered, write the what's-new form and name the modules after it.

```
## YYYY-MM-DD HH:MM | pka-tutorial | Walkthrough: <modules covered> | — | User ready for <next action>
## YYYY-MM-DD HH:MM | pka-tutorial | What's new in v<tool_version>: <capabilities covered> | — | User ready for <next action>
```

The second form must begin with those exact words: pre-flight looks for it to decide whether to offer what's new again. If the user declined the upgrade, put `bootstrap upgrade not run (workspace on <version>)` in the fourth field so the next session's greeting shows it as open.

See `references/example-prompts.md` for the full library of try-this prompts by module.
