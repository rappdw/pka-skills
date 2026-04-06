# Wiki Lifecycle

Create, maintain, retire. Topic wikis are additive — they can be removed
without losing any authored content.

---

## Create

### Trigger Phrases

- "Create a topic wiki on `<topic>`"
- "Start a wiki for `<topic>`"
- "I want to track my thinking on `<topic>`"

### Flow

1. **Identify or create wiki-home folder.** Look for a folder tagged `wiki-home`
   in the Repo Map. If none exists, propose creating `knowledge/topics/`:
   > "You don't have a wiki-home folder yet. I'll create `knowledge/topics/` as
   > the default. OK?"
2. **Derive slug.** Lowercase-hyphenate the topic name. Confirm if ambiguous
   (e.g., "MCP" → `mcp` or `model-context-protocol`?).
3. **Check for existing wiki.** If `knowledge/topics/<slug>/wiki.md` exists, ask
   whether to open the existing one or use a different slug.
4. **Create folder** `knowledge/topics/<slug>/`.
5. **Write `wiki.md`** using scaffold from `wiki-page-schema.md`.
6. **Update Repo Map.** Add `topics/` with `wiki-home` tag if not already tagged.
7. **Log to session-log + decision-log:**
   ```
   ## <date> | Create wiki: <slug>
   **Context:** User wants to track <topic>.
   **Decision:** Created topic wiki at knowledge/topics/<slug>/wiki.md.
   **Decided by:** <owner>
   ```
8. **Prompt for first ingest:**
   > Wiki created. Want to ingest a source now? Drop a path or say
   > "ingest X into my `<slug>` wiki."

---

## List

### Trigger Phrases

- "Show me my topic wikis"
- "What wikis do I have?"
- "List my topics"

### Flow

1. Read all `wiki-home` tagged folders from Repo Map
2. For each wiki, read frontmatter + H1 title
3. Present as table:

| Topic | Last updated | Sources | Status |
|-------|--------------|---------|--------|
| mcp | 2026-04-05 | 8 | active |
| agents | 2026-03-22 | 12 | active |
| llm-tooling | 2025-11-04 | 3 | retired |

---

## Update Thinking

### Trigger Phrases

- "Update my thinking on `<topic>`"
- "Add my opinion on `<topic>` to the wiki"
- "My view has changed on `<topic>`"

### Flow

1. Read current `## My current thinking` section
2. Show it to user, ask what changed
3. Rewrite section (or append, per user preference)
4. Append changelog: "Updated current thinking (source: owner dialogue)"
5. Update `last-updated` frontmatter

Unlike ingest, this doesn't require `## Sources` update — the source is the owner.

---

## Retire

### Trigger Phrases

- "Retire my `<topic>` wiki"
- "I'm done with `<topic>`"

### Flow

1. Confirm intent — retired wikis are excluded from query but kept as files
2. Set frontmatter `status: retired`
3. Append changelog: "Retired: no longer actively maintained"
4. Update Repo Map (optional tag update)
5. Log to decision-log with reasoning

Retired wikis can be restored with "restore the `<topic>` wiki" — reverses the flag.

---

## Delete (rare)

### Trigger Phrases

- "Delete the `<topic>` wiki"

### Flow

Wiki deletion requires explicit confirmation regardless of autonomy level.
Only the `wiki.md` + folder is deleted. Sources in `sources/` are preserved
(routed to librarian's generic destination if user wants).

Strongly prefer retire over delete. Deletion is irreversible.

---

## Split / Merge (v1.1+)

Not in v1.0.0. Flagged here as anticipated future ops:

- **Split**: wiki grows too large → extract a subsection into its own wiki
- **Merge**: two wikis have converged → combine, redirect one slug

For now, users perform these manually and ask librarian to lint afterward.
