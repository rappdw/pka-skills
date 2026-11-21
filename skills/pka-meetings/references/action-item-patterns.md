# Action Item Patterns

Heuristics for extracting action items from meeting notes.

---

## Detection Patterns

### Line-Level Patterns

Scan each line of the notes for these patterns:

| Pattern | Example | Priority |
|---------|---------|----------|
| `- [ ]` | `- [ ] Send Priya the architecture doc` | High — explicit task checkbox |
| `→` or `->` | `→ Sam to follow up on headcount` | High — action arrow |
| `AI:` or `A/I:` | `AI: Schedule follow-up meeting` | High — explicit action item marker |
| `Action:` | `Action: Review the proposal by Friday` | High — explicit marker |
| `TODO:` or `Todo:` | `TODO: Update the RACI before next meeting` | High — explicit marker |
| `FOLLOW UP:` or `Follow up:` | `Follow up: Check with legal on compliance` | Medium — follow-up marker |
| `needs to` | `Sam needs to send the comparison doc` | Low — natural language |
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

## What Filing Writes

**An item that is already a checkbox is never rewritten.** Any `- [ ]` or `- [x]` line in the note stays byte for byte as it is: its wording, its form, its place. That covers items the user typed and items thinkkit's `take-notes` wrote:

```markdown
- [ ] **Robin**: Draft the Q1 hiring plan (due: 2026-12-01)
```

Filing does not convert that line into PKA's form. `pka-tools actions` reads both forms (see "Forms `actions` reads" below), so a converted copy would add nothing and would change a note the user or another plugin owns.

Filing **adds** lines only for items found by the other patterns above (an `Action:` line, a `→` line, a bullet under `## Next Steps`, a commitment in prose). Each is added once to the `## Action Items` section, in PKA's form:

```markdown
## Action Items
- [ ] <action description> — @<owner if mentioned> — by <YYYY-MM-DD if a due date was mentioned>
```

The line it was extracted from is left where it is.

### Owner Extraction
- Look for `@name`, "name to...", "name will...", "name needs to..."
- If no owner identified: omit the `@owner` field
- Normalize to first name only: `@Priya`, `@Sam`

### Due Date Extraction
- Look for explicit dates: "by March 31", "before Friday", "end of month", "by EOD"
- Convert relative dates to absolute, counting from the meeting's date: "by Friday" → `by 2026-04-03`
- Write the date as `by YYYY-MM-DD`. The word `by` is what marks it as a due date wherever it stands in the line
- If no due date: omit the date field

### Deduplication
- If the same action appears in both a line-level match and a section-level match, keep only one
- Prefer the version with more context (owner, due date)

---

## Action Item Section Placement

If notes don't have an `## Action Items` section:
- Append it at the end of the file. When this filing also created `## Attendees`, that section was appended first (attendee linking runs before extraction), so `## Action Items` follows it
- Never insert it between existing sections

If notes already have an `## Action Items` section:
- Leave the section where it is
- Append newly-extracted items that aren't already listed, in any form (an item thinkkit wrote as `**Robin**: Draft the plan` is already listed)
- Never modify, reorder or re-format a line that is already there

---

## Session Log Integration

After extraction, surface to the user:
> "Found N action items. Add to session log open threads?"

If confirmed, append one entry per item with the item in the open-threads field (the field the session-start greeting reads):
```
.pka/bin/pka-tools log add --role pka-meetings --summary "Action item from <note filename>" --open "<action item text>"
```
which writes:
```
## YYYY-MM-DD HH:MM | pka-meetings | Action item from <note filename> | <action item text> | —
```

One session log entry per action item. These appear as open threads in future session starts.

---

## Forms `actions` reads

`pka-tools actions` is read-only. It reads an open checkbox in whichever of these forms it was written and returns `owners`, `due` (a `YYYY-MM-DD` date, or nothing) and `due_text` (the due date as written, or nothing):

| Written as | `owners` | `due` | Written by |
|---|---|---|---|
| `- [ ] Send the comparison — @Sam — by 2026-05-01` | Sam | 2026-05-01 | pka-meetings |
| `- [ ] Send the comparison — @Sam — 2026-05-01` | Sam | 2026-05-01 | pka-meetings up to v1.10.0, by hand |
| `- [ ] **Robin**: Draft the hiring plan (due: 2026-12-01)` | Robin | 2026-12-01 | thinkkit `take-notes` |
| `- [ ] **Robin and Sam**: Agree the panel (due: Dec 1)` | Robin, Sam | 1 December on or after the note's date | thinkkit `take-notes` |
| `- [ ] **Sam**: Book the rooms (due: Friday)` | Sam | none; `due_text` is `Friday` | thinkkit `take-notes` |
| `- [ ] Circulate the notes` | none | none | anyone |

**Owners.** Every `@name` in the item, and a bold name followed by a colon at the very start of it (`**Robin**:` or `**Robin:**`). Several names in the bold part are split on commas, `and`, `&` and `/`. The bold part counts only when each piece looks like a name: at most four words, each capitalised, no digits, and not a label such as `Note`, `TODO`, `Decision` or `Owner`. `**Robin** to draft the plan` (no colon) and `**Draft the plan**: …` give no owner.

**Due date.** In this order:

1. `by` or `due` followed by an ISO date, with or without a colon or brackets: `by 2026-05-01`, `(due: 2026-05-01)`.
2. Bracketed `(due: …)` or `(by: …)` with other text. A month-name date (`Dec 1`, `1 December 2026`) becomes a date; without a year it is the first such day on or after the note's date. Anything else (`Friday`, `end of month`, `12/1`) is returned in `due_text` only: the tool does not guess weekdays, and cannot tell day from month in `12/1`.
3. An ISO date that **ends** the item after a dash: `— @Sam — 2026-05-01`. This is accepted because it is the form this skill told roles to write up to v1.10.0, so filed notes contain it.

An ISO date anywhere else is part of the sentence, not a due date: `Review the 2026-11-21 minutes` has none, and neither has `Send it — 2026-11-21 — @Sam`. When in doubt write `by`.

---

## Querying Action Items

When the user asks "What action items do I have from meetings this week?":

1. Run the scan. It reads the notes themselves, because full-text search cannot find `- [ ]` (the tokenizer drops the punctuation):
   ```
   .pka/bin/pka-tools actions [--since <YYYY-MM-DD>] [--until <YYYY-MM-DD>] [--json]
   ```
   - **"This week" means the last 7 days**, which is the default window: run the command with no `--since`. It does not mean "since Monday": on a Monday that would hide everything from the meetings of the days before. Pass `--since` only when the user names another period ("since the offsite", "this month" → the first day of it). `--all-dates` removes the window.
   - Scope: the folders tagged `meeting-home` in the Repo Map plus the people folder (1-1 notes live there). `--scope all` scans every index root; `--under <folder>` scans just that folder.
   - A note's date is its filename prefix (`YYYY-MM-DD-`), else its frontmatter `date`. File modification time is never used (routing, indexing and sync all touch it). Notes with no date are left out unless `--include-undated` is given.
   - Open boxes (`- [ ]`, `* [ ]`, nested or numbered) are returned with file, line number, owners and due date, read as described under "Forms `actions` reads". A ticked box (`- [x]`) is closed and not returned. Boxes inside fenced code blocks are examples and are ignored.
   - An item whose `due` is empty and whose `due_text` is not ("Friday", "end of month") has a due date the tool would not guess: work it out from the note's `date`, and say that you did.
2. List the open threads in the session log: `.pka/bin/pka-tools log open --last 100` (entries before v1.7 put the item in the summary as `Open: <item>`; read those too).
3. Combine and deduplicate. When a session-log open thread and a checkbox line describe the same item, the note is the truth: if the box is now `- [x]`, the item is closed even though the log entry still says open.
4. Surface with source file links:

```
Action items from meetings in the last 7 days:
- [ ] Send Priya architecture comparison doc — @Sam
  Source: knowledge/personnel/priya/2026-03-31-1-1-priya.md

- [ ] Review Q2 budget proposal — @Sam — by 2026-04-07
  Source: knowledge/leadership/2026-03-31-slt-q2-planning.md

- [ ] Draft the Q1 hiring plan — Robin — by 2026-04-10
  Source: knowledge/leadership/2026-04-01-hiring-sync.md
```

The list you show may use one form for readability. The notes keep theirs.
