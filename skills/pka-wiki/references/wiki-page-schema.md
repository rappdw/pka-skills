# Wiki Page Schema

The structure of a topic wiki page. Every wiki page follows this schema so that
@researcher, librarian lint, and query enhancement can rely on consistent format.

---

## Folder Structure

Default location: `knowledge/topics/<topic-slug>/`

```
knowledge/topics/mcp/
├── wiki.md                 # the synthesis page (required)
├── sources/                # ingested source materials (optional)
│   ├── anthropic-mcp-spec.pdf
│   └── community-writeup.md
└── drafts/                 # work-in-progress before merging (optional)
    └── v2-rewrite.md
```

- `wiki.md` is required — it's the synthesis.
- `sources/` holds ingested materials that live alongside the wiki. Librarian may
  also route sources to other destinations; `sources/` is for topic-scoped material
  that belongs with the wiki.
- `drafts/` holds pre-merge work. Never cited by the wiki's Sources list until
  merged.

---

## Topic Slug Rules

- Lowercase, hyphen-separated
- Max 40 chars
- No punctuation except hyphen
- Derived from user phrasing: "Create a wiki on Model Context Protocol" → `mcp` or
  `model-context-protocol` (ask the user which they prefer if ambiguous)

---

## Page Structure

```markdown
---
topic: <slug>
last-updated: YYYY-MM-DD
source-count: N
status: active | retired
---

# <Topic Display Name>

## What it is
<1-2 paragraph synthesis. Every factual claim cites a source via footnote or
inline reference to a path in ## Sources.>

## Key concepts
<Bulleted or sub-headed breakdown of the topic's components. Cite as you go.>

## My current thinking
<Owner's opinion / conclusion / position. Distinct from synthesized facts.
May be empty on first creation; filled in via owner dialogue or elicitation.>

## Open questions
<What's unresolved. What sources haven't been read yet. What contradictions
remain unreconciled.>

## Related topics
- [[other-topic-slug]]
- [[another-topic-slug]]

## Sources
- `<path-to-authored-note>` — <what this source contributes>
- `<path-to-ingested-source>` — <what this source contributes>
- ...

## Changelog
- YYYY-MM-DD: <what changed> (source: <path if applicable>)
- YYYY-MM-DD: Initial synthesis from N sources
```

---

## Required vs. Optional Sections

| Section | Required | Notes |
|---------|----------|-------|
| Frontmatter | Yes | Lint reads this |
| `# <title>` | Yes | H1 |
| `## What it is` | Yes | Even if brief |
| `## Key concepts` | Yes | Can be empty initially |
| `## My current thinking` | Optional | Absent section is fine |
| `## Open questions` | Optional | Encouraged but not required |
| `## Related topics` | Optional | Empty list is OK |
| `## Sources` | Yes | Must have ≥1 entry |
| `## Changelog` | Yes | Append-only, chronological |

---

## Citation Conventions

**Inline citation:** Reference a path in a sentence:

> MCP supports resource, tool, and prompt primitives [see `knowledge/topics/mcp/sources/anthropic-mcp-spec.pdf`].

**Footnote citation:** For cleaner prose:

> MCP supports resource, tool, and prompt primitives.[^spec]
>
> [^spec]: `knowledge/topics/mcp/sources/anthropic-mcp-spec.pdf`

**Paragraph-level citation:** Acceptable when a whole paragraph derives from one source:

> (Drawing from `knowledge/personnel/aarav/2026-03-31-1-1-aarav.md`:)
>
> Aarav believes the Kong path is lower risk than AgentCore because ...

Every cited path must appear in `## Sources`. Lint flags mismatches.

---

## Wikilink Convention

Inter-wiki references use `[[topic-slug]]` format:

> Related to [[agents]] and [[llm-tooling]].

This renders natively in Obsidian and degrades to readable text elsewhere.

Lint verifies that every `[[link]]` target has a corresponding
`knowledge/topics/<link>/wiki.md`.

---

## Frontmatter Fields

| Field | Type | Purpose |
|-------|------|---------|
| `topic` | string (slug) | Matches folder name; used by query enhancement |
| `last-updated` | YYYY-MM-DD | Set on every modification |
| `source-count` | integer | Count of entries in `## Sources` |
| `status` | `active` \| `retired` | Retired wikis kept for history, excluded from query |

---

## Scaffold (created on first `create`)

```markdown
---
topic: {{slug}}
last-updated: {{date}}
source-count: 0
status: active
---

# {{title}}

## What it is
_(To be written as sources are ingested.)_

## Key concepts
_(To be filled in.)_

## Open questions
- What's the scope of this wiki?

## Sources
_(None yet — ingest your first source with: "Ingest `<path>` into my {{slug}} wiki".)_

## Changelog
- {{date}}: Wiki created
```
