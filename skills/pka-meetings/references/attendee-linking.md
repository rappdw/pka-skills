# Attendee Linking

How to match attendee names from meeting notes to personnel folder entries and create cross-references.

---

## Extraction

Extract attendee names from:
1. The `## Attendees` section if present in the notes
2. The attendee list provided at meeting start (capture mode)
3. Speaker attributions in the notes body (e.g., "Aarav said...", "@Aarav", "**Aarav:**")

---

## Matching Against Repo Map

For each extracted attendee name, attempt to find a matching folder in the Repo Map's personnel section.

### Match Order (stop at first match)

1. **Exact slug match:** attendee name lowercased = folder name
   - "Aarav" → `aarav/` (match)

2. **First name match:** attendee first name lowercased = folder name
   - "Aarav Patel" → `aarav/` (match)

3. **Last name match:** attendee last name lowercased = folder name
   - "Dr. Patel" → check for `patel/`

4. **Full name slug match:** `firstname-lastname` lowercased = folder name
   - "Aarav Patel" → `aarav-patel/` (match)

5. **Reversed slug match:** `lastname-firstname` lowercased = folder name
   - "Aarav Patel" → `patel-aarav/` (match)

6. **Partial match:** folder name starts with or contains the attendee's first name
   - "Aarav" → `aarav-engineering/` (match, but lower confidence)

### Match Confidence

| Match type | Confidence | Action |
|------------|-----------|--------|
| Exact slug | High | Link automatically |
| First name | High (if unique) | Link automatically; if multiple matches, ask |
| Last name | Medium | Link if unique; ask if ambiguous |
| Full name slug | High | Link automatically |
| Partial | Low | Include in list but don't auto-link |
| No match | — | List name without link |

---

## Link Format

When a match is found, add a relative path reference under `## Attendees` at the bottom of the notes file:

```markdown
## Attendees
- [Aarav](../personnel/aarav/) — matched
- [Sarah Chen](../personnel/sarah-chen/) — matched
- Marcus Johnson — no personnel folder found
```

### Path Calculation

The link path is relative from the note's destination to the personnel folder:
- Note at `knowledge/leadership/2026-03-31-slt-q2-planning.md`
- Person at `knowledge/personnel/aarav/`
- Relative path: `../personnel/aarav/`

- Note at `knowledge/personnel/aarav/2026-03-31-1-1-aarav.md`
- Person is the folder itself
- Link: `./` or omit (the note is already in the person's folder)

---

## Creating the Attendees Section

If the notes don't already have an `## Attendees` section:
- Create one at the bottom of the file, after any existing content
- Before `## Action Items` if that section exists (attendees before actions)

If the notes already have an `## Attendees` section:
- Append linked entries that aren't already listed
- Don't duplicate existing entries
- Don't modify manually-written attendee entries

---

## PKA Owner Handling

The PKA owner's name (from bootstrap Q1) is always an attendee of meetings they capture. Options:
- Include in the attendee list but don't link (the owner doesn't typically have a personnel subfolder for themselves)
- If `knowledge/<owner-name>/` exists (self-notes folder), link there
- Never create a personnel subfolder for the owner automatically

---

## Edge Cases

- **Nicknames:** If "Mike" doesn't match but "michael" does, don't auto-link — the fuzzy match isn't confident enough. List as unmatched.
- **Multiple matches:** If "Alex" matches both `alex-chen/` and `alex-kumar/`, ask the user which one.
- **External attendees:** People who don't work at the same organization typically won't have personnel folders. List them without links. Don't suggest creating folders for every meeting attendee.
- **Large meetings (10+ attendees):** Link only attendees with existing personnel folders. Don't present a long list of "no match" entries — summarize as "N attendees not in personnel records."
