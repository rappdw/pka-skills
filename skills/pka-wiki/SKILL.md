---
name: pka-wiki
description: >
  ALWAYS use this skill when the user mentions topic wikis, synthesis pages,
  knowledge synthesis, maintaining understanding on a topic, creating or updating
  a wiki page, ingesting a source into a wiki, or asking what they know about a
  topic that might have a synthesis page. Triggers on: "create a wiki on X",
  "ingest this into my X wiki", "add this source to the X wiki", "what wikis do
  I have", "update my thinking on X", "show me my topic wikis", "synthesize X
  into Y", "retire the X wiki", or similar wiki-maintenance requests. Also
  enhances "what do I know about X" queries when a wiki exists for X. Topic
  wikis are LLM-maintained synthesis pages that sit alongside authored notes —
  they cite moments, never replace them. Optional layer; users without wikis
  see no change in PKA behavior.
user-invocable: true
argument-hint: "[create|ingest|list|query|retire] [topic or path]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# pka-wiki

Topic wiki lifecycle for Personal Knowledge Assistance. Creates and maintains
LLM-synthesized pages that cite your authored notes — a complementary synthesis
layer inspired by [Karpathy's LLM wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f),
adapted to PKA's files-are-source-of-truth model.

## Conceptual Model

PKA has two kinds of content:

- **Authored moments** — your meeting notes, 1-1s, research drafts, journal.
  Immutable records in your voice.
- **Synthesis pages** — topic wikis maintained by @researcher. They cite
  authored moments and evolve as understanding grows.

Wikis cite moments. Moments never cite wikis. Deleting a wiki loses no
underlying content.

## Storage Convention

Default wiki-home: `knowledge/topics/` (tagged `wiki-home` in the Repo Map).
Each topic lives in its own subfolder:

```
knowledge/topics/mcp/
├── wiki.md           # the synthesis page
├── sources/          # optional: ingested materials
└── drafts/           # optional: pre-merge work
```

Users can have multiple `wiki-home` folders. Detection is structural — any folder
with subfolders each containing `wiki.md` qualifies.

## Pre-Flight

1. Load `.pkaignore` and Repo Map from `CLAUDE.md`
2. Identify `wiki-home` folders (tag in Repo Map, or structural detection)
3. If no wiki-home exists, prepare to propose `knowledge/topics/` on first create

---

## Modes

### Mode 1: Create

Create a new topic wiki. See `references/wiki-lifecycle.md` (Create section).

Flow: derive slug → create folder → write scaffold → update Repo Map → log → prompt for first ingest.

### Mode 2: Ingest

Synthesize a source document into a topic wiki. The highest-stakes operation —
requires explicit confirmation regardless of autonomy level.

See `references/ingest-workflow.md` for the full 9-step flow.

Key guarantees:
- Every claim cites a source path
- Contradictions surfaced for user resolution, never auto-decided
- Full diff shown before write
- Changelog and decision-log entries on every ingest

### Mode 3: Query

Enhanced behavior on "what do I know about X" queries when a wiki exists for X.
See `references/query-enhancement.md`.

Flow: detect wiki → return wiki summary + mentions not yet ingested → offer
follow-up actions.

Strictly additive — users without wikis see existing PKA query behavior.

### Mode 4: List / Update thinking / Retire / Delete

See `references/wiki-lifecycle.md`.

- **List**: table of all wikis with status
- **Update thinking**: owner-sourced update to `## My current thinking`
- **Retire**: mark inactive, exclude from query, keep file
- **Delete**: rare, confirmation required even in hands-off mode

---

## Page Schema

Every wiki page has fixed structure: frontmatter, `## What it is`,
`## Key concepts`, `## Sources` (required), plus optional sections for thinking,
questions, related topics. See `references/wiki-page-schema.md`.

Citations use inline or footnote format. Inter-wiki links use `[[slug]]`
wikilink syntax (renders in Obsidian, degrades cleanly elsewhere).

---

## Interaction with Other Skills

- **@researcher** (from pka-bootstrap) — authors and updates wiki content; wiki
  output mode is part of researcher's role definition
- **pka-librarian** — lint verifies wiki sources exist, flags broken wikilinks,
  surfaces contradiction candidates
- **pka-meetings** — post-processing can optionally surface "this note mentions
  topic X which has a wiki — ingest?" (v1.1 feature, not in MVP)
- **pka-interface** — dashboard can render `wiki-home` sections as topic cards
  (future)

## Constraints

- **Ingest always confirms**, even in hands-off mode
- **Delete always confirms**, even in hands-off mode
- **Wikis never silently override authored notes** — contradictions surface for user decision
- **Every wiki claim must cite** — lint flags uncited claims
- **Source paths must exist** — lint flags dead sources
- **No auto-ingest** in v1.0.0 — user explicitly triggers every synthesis

## Session Log Entries

```
## YYYY-MM-DD HH:MM | pka-wiki | Created wiki: <slug> | — | Ingest first source
## YYYY-MM-DD HH:MM | pka-wiki | Ingested <source> into <slug> | N claims added, M refinements | Cross-wiki candidates: [agents]
## YYYY-MM-DD HH:MM | pka-wiki | Retired wiki: <slug> | — | —
```
