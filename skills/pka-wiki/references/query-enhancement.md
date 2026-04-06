# Query Enhancement

How query behavior changes when topic wikis exist. Strictly additive — users
without wikis see no change in query behavior.

---

## Detection

On any query that matches a topic (person, project, concept), check:

1. Is there a `wiki-home` folder in the Repo Map?
2. Does `<wiki-home>/<topic-slug>/wiki.md` exist? (with slug matching via
   frontmatter `topic:` field, not just folder name)
3. Is the wiki `status: active` (not `retired`)?

If yes → wiki-first response. If no → existing FTS behavior, unchanged.

---

## Slug Matching

Query phrases map to slugs via:

1. **Direct match:** "What do I know about MCP" → `mcp`
2. **Slugify match:** "Tell me about model context protocol" → `model-context-protocol`
3. **Frontmatter title match:** query matches `# <title>` H1 of any wiki
4. **Synonym via related topics:** if `[[mcp]]` is listed as related in another wiki, and query matches that wiki, surface the related wiki too

Ambiguity: if multiple wikis match, list them and ask.

---

## Response Shape

### With wiki present

```
Found topic wiki: knowledge/topics/mcp/wiki.md (last updated 2026-04-05, 8 sources)

**Summary from the wiki:**
[paraphrased ## What it is + ## Key concepts]

**Current thinking:**
[## My current thinking verbatim, if present]

**Open questions:**
[## Open questions bullets]

**Also surfaced from your authored notes** (not yet in wiki):
- knowledge/personnel/aarav/2026-04-02-1-1-aarav.md — recent mention
- knowledge/leadership/2026-q2-planning.md — strategic context

Want me to read the full wiki, ingest the new mentions, or something else?
```

The "also surfaced" section runs FTS to find notes mentioning the topic that
aren't yet in `## Sources`. Surfaces candidates for ingest.

### Without wiki

Existing PKA behavior — FTS search, ranked results, orchestrator summary.

---

## Query Types and Wiki Behavior

| Query type | With wiki | Without wiki |
|------------|-----------|--------------|
| "What do I know about X?" | Wiki summary + mentions not yet ingested | FTS summary |
| "Find everything about X" | Wiki + FTS results side by side | FTS results |
| "What did I decide about X?" | Wiki `## My current thinking` + decision-log entries | decision-log + FTS |
| "What's new on X since last month?" | Changelog entries since date + recent mentions | FTS filtered by date |

---

## When Wiki and FTS Conflict

If FTS returns a recent authored note that contradicts the wiki's `## What it is`,
flag it:

> ⚠️ A recent note in `knowledge/personnel/aarav/2026-04-02-1-1-aarav.md` mentions
> MCP and may contradict the wiki's current claim about transport. Consider ingesting.

Does not auto-resolve. Prompts user to ingest or reconcile.

---

## Retired Wikis

`status: retired` wikis are excluded from query responses but not deleted.
A retired wiki is reachable via:

> "Show me the retired wiki on `<topic>`"

Or by direct file read. Useful for history-preserving topic deprecation.

---

## No Wiki, User Expected One

If query strongly implies a topic that could have a wiki but doesn't:

> I don't have a topic wiki on `<topic>`. I found 7 mentions across your notes.
> Want me to summarize from those, or create a wiki?

Offers creation inline but never forces it.
