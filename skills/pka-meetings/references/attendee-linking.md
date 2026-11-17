# Attendee Linking

How to match attendee names from meeting notes to personnel folder entries and create cross-references.

---

## Extraction

Extract attendee names from:
1. The `## Attendees` section if present in the notes
2. The attendee list provided at meeting start (capture mode)
3. Speaker attributions in the notes body (e.g., "Priya said...", "@Priya", "**Priya:**")

---

## Matching Against the People Registry

Do not match names by hand. Ask the registry:

```
.pka/bin/pka-tools people resolve "Priya" "Dr. Nair" "Robin Smith" "@Sam"
```

Person folders are the subfolders of the Repo Map folder tagged `people-home` (fallback `knowledge/personnel/`); each may have an `index.md` with a `name` and `aliases`. For each name the command answers:

| Answer | When | What to do |
|---|---|---|
| **high** → slug | the name is exactly a person's slug, `name` or alias (ignoring case, accents, punctuation, `@` and titles such as Dr.); the slug's words in either order; a link to the person's folder; or a first name only one person has | Link it |
| **ambiguous** → candidates | the name fits more than one person, or is a last name only | Ask the user which one; never pick |
| **none** | nothing matches (people sharing the first name are listed as a hint, not a match) | List the name without a link |

**Nicknames are never guessed.** "Rob" does not match a `robin-smith` folder. If the user tells you who "Rob" is, offer to remember it:

```
.pka/bin/pka-tools people alias robin-smith "Rob"
```

From then on "Rob" resolves with high confidence. The command refuses an alias that already means someone else.

`people list` shows every person with their name and aliases.

---

## Link Format

When a match is found, add a relative path reference under `## Attendees` at the bottom of the notes file:

```markdown
## Attendees
- [Priya](../personnel/priya/) — matched
- [Sarah Chen](../personnel/sarah-chen/) — matched
- Marcus Johnson — no personnel folder found
```

### Path Calculation

The link path is relative from the note's destination to the personnel folder:
- Note at `knowledge/leadership/2026-03-31-slt-q2-planning.md`
- Person at `knowledge/personnel/priya/`
- Relative path: `../personnel/priya/`

- Note at `knowledge/personnel/priya/2026-03-31-1-1-priya.md`
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

- **Nicknames:** an unmatched nickname is listed without a link. If the user says who it is, offer `people alias` (above).
- **Multiple matches:** `people resolve` answers "ambiguous" with the candidates; ask the user which one.
- **External attendees:** People who don't work at the same organization typically won't have personnel folders. List them without links. Don't suggest creating folders for every meeting attendee.
- **Large meetings:** link only attendees with existing person folders, and don't present a long list of "no match" entries — summarize as "N attendees not in personnel records." Meetings with more than 8 resolved attendees are left off people's timelines (see below).

---

## Timelines

The links written under `## Attendees`, and the note's frontmatter `attendees` and `person`, are what put a note on people's timelines: `post-route` resolves them and adds one line to each person's `## Timeline` block. See "Step 5" of the pka-meetings skill. A note with `no-backref: true` in its frontmatter goes on nobody's timeline.
