# Ingest Workflow

How a source document is synthesized into a topic wiki. This is the highest-stakes
operation in `pka-wiki` — it modifies a curated synthesis page, so it requires
explicit user review regardless of autonomy level.

---

## Trigger Phrases

- "Ingest `<path>` into my `<topic>` wiki"
- "Add this `<source>` to the `<topic>` wiki"
- "Synthesize `<path>` into `<topic>`"
- "Read `<path>` and update my wiki on `<topic>`"

---

## Pre-Flight

1. Resolve the **source path** — a file path, or a document in `team-inbox/`
2. Resolve the **target wiki** — `knowledge/topics/<topic>/wiki.md`
3. If target wiki doesn't exist, ask: "No wiki on `<topic>` yet. Create one and ingest, or cancel?"
4. Verify source is readable (markdown, text, or has OCR sidecar if PDF)
5. Load the Repo Map to identify related topic wikis for cross-reference prompts

---

## Synthesis Steps

### Step 1 — Read both documents

- Read the source (or its `.txt` sidecar if PDF)
- Read the current `wiki.md` in full
- Note existing `## Sources` entries

### Step 2 — Identify contributions

@researcher analyzes the source relative to the wiki and categorizes content as:

| Category | Meaning |
|----------|---------|
| **New claim** | Source asserts something the wiki doesn't cover |
| **Confirmation** | Source supports an existing wiki claim (strengthens citation) |
| **Contradiction** | Source disagrees with an existing wiki claim |
| **Refinement** | Source adds nuance or qualification to an existing claim |
| **Irrelevant** | Source content doesn't belong in this wiki |

### Step 3 — Propose section-level diffs

For each affected section, propose an update as a diff:

```markdown
## Key concepts

- [UNCHANGED] MCP supports resource, tool, and prompt primitives...
+ [ADD] Clients negotiate capabilities at connection time, not per-request [source: new]
- [REFINE] Previously: "Servers expose tools." → "Servers expose tools, resources, and prompts as distinct primitives." [source: new]
```

### Step 4 — Flag contradictions separately

If contradictions exist, surface them explicitly before the diff:

> ⚠️ This source contradicts an existing wiki claim:
>
> **Wiki says:** "MCP is transport-agnostic" (from `knowledge/personnel/aarav/2026-03-31.md`)
> **Source says:** "MCP is tightly coupled to JSON-RPC" (from `.../anthropic-mcp-spec.pdf`)
>
> How should I reconcile? Options:
> 1. Keep wiki claim, note source disagreement in Open questions
> 2. Update wiki claim, supersede old source
> 3. Keep both as qualified statements with context

User resolves — never auto-decided.

### Step 5 — Present full diff to user

Show the proposed updated wiki in a readable diff format. Mandatory pause for
approval **regardless of autonomy level** — synthesis overwrites are always
high-stakes.

### Step 6 — Apply approved diff

- Write updated `wiki.md`
- Append new entry to `## Sources` with path and one-line contribution note
- Increment `source-count` in frontmatter
- Update `last-updated` in frontmatter
- Append `## Changelog` entry:

```markdown
- 2026-04-05: Added client-side capability negotiation concept (source: `knowledge/topics/mcp/sources/anthropic-mcp-spec.pdf`)
```

### Step 7 — Route the source

If the source is in `team-inbox/`, move it to the wiki's `sources/` folder
(or elsewhere per user preference). If the source is already filed, leave it.

### Step 8 — Cross-wiki mention scan

Scan the source for mentions of other topic slugs present in `wiki-home` folders.
Surface suggestions, don't auto-update:

> This source also mentions `[[agents]]` and `[[llm-tooling]]`. Want me to
> ingest into those wikis too, or note as related topics only?

### Step 9 — Log to session-log and decision-log

```
## 2026-04-05 HH:MM | pka-wiki | Ingested source into mcp wiki | 3 new claims, 1 refinement | —
```

If a contradiction was resolved, also log to `decision-log.md`:

```markdown
## 2026-04-05 | Reconcile MCP transport claim

**Context:** New source (`.../anthropic-mcp-spec.pdf`) contradicted wiki claim about transport.
**Decision:** Updated wiki — MCP is JSON-RPC-specific. Superseded claim from Aarav 1-1.
**Decided by:** Dan
**Relates to:** `knowledge/topics/mcp/wiki.md`
```

---

## Failure Modes

| Case | Behavior |
|------|----------|
| Source unreadable (no OCR) | Skip ingest, suggest running librarian OCR first |
| User rejects diff | No changes written; log abandoned attempt |
| Wiki doesn't exist | Offer to create, then ingest |
| Source already cited | Warn user, ask if re-ingest intended (may be useful for updates) |
| Empty synthesis (source irrelevant) | Report "nothing to add" and suggest routing source elsewhere |

---

## Confirmation Overrides

Ingest always requires confirmation, even in hands-off mode. This is the explicit
exception to autonomy level behavior — wikis are synthesis artifacts and silent
overwrites erode trust in the content.
