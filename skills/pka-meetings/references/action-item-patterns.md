# Action Item Patterns

Heuristics for extracting action items from meeting notes.

---

## Detection Patterns

### Line-Level Patterns

Scan each line of the notes for these patterns:

| Pattern | Example | Priority |
|---------|---------|----------|
| `- [ ]` | `- [ ] Send Priya the architecture doc` | High — explicit task checkbox |
| `→` or `->` | `→ Dan to follow up on headcount` | High — action arrow |
| `AI:` or `A/I:` | `AI: Schedule follow-up meeting` | High — explicit action item marker |
| `Action:` | `Action: Review the proposal by Friday` | High — explicit marker |
| `TODO:` or `Todo:` | `TODO: Update the RACI before next meeting` | High — explicit marker |
| `FOLLOW UP:` or `Follow up:` | `Follow up: Check with legal on compliance` | Medium — follow-up marker |
| `needs to` | `Dan needs to send the comparison doc` | Low — natural language |
| `will` (commitment) | `Priya will take the MCP adapter work` | Low — natural language |
| `by <date>` | `Complete the review by end of month` | Low — deadline signal |

### Section-Level Patterns

Entire sections treated as action item collections:

| Section heading | Treatment |
|----------------|-----------|
| `## Action Items` | Every bullet is an action item |
| `## Next Steps` | Every bullet is an action item |
| `## Follow-up` | Every bullet is an action item |
| `## To Do` or `## TODO` | Every bullet is an action item |
| `## Decisions` | Not action items — decisions are record, not tasks |

---

## Extraction Rules

1. **High-priority patterns** (explicit markers) are always extracted
2. **Medium-priority patterns** are extracted with a confidence note
3. **Low-priority patterns** (natural language) are extracted only if they contain a named person + action verb
4. **Section-level items** are extracted regardless of individual line patterns

---

## Normalization

All extracted action items are normalized into a consistent format in the `## Action Items` section:

```markdown
## Action Items
- [ ] <action description> — @<owner if mentioned> — <due date if mentioned>
```

### Owner Extraction
- Look for `@name`, "name to...", "name will...", "name needs to..."
- If no owner identified: omit the `@owner` field
- Normalize to first name only: `@Priya`, `@Dan`

### Due Date Extraction
- Look for explicit dates: "by March 31", "before Friday", "end of month", "by EOD"
- Convert relative dates to absolute: "by Friday" → "by 2026-04-04"
- If no due date: omit the date field

### Deduplication
- If the same action appears in both a line-level match and a section-level match, keep only one
- Prefer the version with more context (owner, due date)

---

## Action Item Section Placement

If notes don't have an `## Action Items` section:
- Create it at the bottom of the file
- After `## Attendees` if that section exists

If notes already have an `## Action Items` section:
- Append newly-extracted items that aren't already listed
- Don't duplicate existing items
- Don't modify manually-written items

---

## Session Log Integration

After extraction, surface to the user:
> "Found N action items. Add to session log open threads?"

If confirmed, append to `.pka/session-log.md`:
```
## YYYY-MM-DD HH:MM | pka-meetings | Open: <action item text> | — | —
```

One session log entry per action item. These appear as open threads in future session starts.

---

## Querying Action Items

When the user asks "What action items do I have from meetings this week?":

1. Search `session-log.md` for this week's `pka-meetings | Open:` entries.
2. Scan the meeting notes themselves for open checkboxes. Do **not** use `search_fts` for this: the tokenizer drops `- [ ]`, so the query is a syntax error unquoted and matches nothing quoted. Instead:
   - Take every folder tagged `meeting-home` in the Repo Map, plus the per-person folders (1-1 notes live there).
   - Keep the notes whose filename date prefix (`YYYY-MM-DD-`) falls in the week asked about. The filename date is the meeting date; file modification time is not (routing, indexing and sync all touch it).
   - In those files, collect lines matching an open checkbox:
     ```
     grep -n -E '^[[:space:]]*[-*] \[ \]' <file>
     ```
   - A line with `- [x]` is done; leave it out.
3. Combine and deduplicate. When a session-log `Open:` entry and a checkbox line describe the same item, the note is the truth: if the box is now `- [x]`, the item is closed even though the log entry still says open.
4. Surface with source file links:

```
Action items from meetings this week:
- [ ] Send Priya architecture comparison doc — @Dan
  Source: knowledge/personnel/priya/2026-03-31-1-1-priya.md

- [ ] Review Q2 budget proposal — @Dan — by 2026-04-07
  Source: knowledge/leadership/2026-03-31-slt-q2-planning.md
```
