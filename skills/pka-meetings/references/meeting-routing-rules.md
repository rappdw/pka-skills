# Meeting Routing Rules

Logic for routing meeting notes to the correct destination in the knowledge base. Uses meeting title, attendees, and the Repo Map.

---

## Routing Priority Order

Evaluate in order. Stop at first match.

### 1. One-on-One Meeting

**Detection:**
- Title contains "1-1", "1:1", "one-on-one", "one on one"
- OR only one attendee besides the PKA owner

**Routing:**
- Look up the other attendee's name in the Repo Map
- If `<personnel-folder>/<person-slug>/` exists → route there
- Person slug matching: try first name, last name, `firstname-lastname`, all lowercase
- If no matching personnel folder: route to the general `meeting-home`-tagged folder and suggest creating a personnel subfolder

**Example:**
- Title: "1-1 with Aarav", Attendees: Dan, Aarav
- Repo Map has `knowledge/personnel/aarav/`
- Route to: `knowledge/personnel/aarav/2026-03-31-1-1-aarav.md`

### 2. Active Project Meeting

**Detection:**
- Title or attendee list contains a project slug from the Repo Map's project workspaces
- Match is case-insensitive, minimum slug length 4 characters

**Routing:**
- **Always ask** — never auto-route to project workspace
- Present two options:
  1. "Route to `projects/<project>/` (project workspace) — good if the notes are project-specific work artifacts"
  2. "Route to `knowledge/` — better for 1-1s where the project is one topic among many, or for meetings you'll want to find after the project completes"

**Example:**
- Title: "Satori architecture review"
- Repo Map has `projects/satori/`
- Ask: "This looks like a Satori project meeting. Route to `projects/satori/` or to `knowledge/leadership/`?"

### 3. Leadership / Strategy Meeting

**Detection:**
- Title contains strategic keywords: `slt`, `leadership`, `strategy`, `planning`, `quarterly`, `q1`–`q4`, `board`, `executive`, `all-hands`, `town hall`, `offsite`, `review`, `budget`, `roadmap`, `okr`
- OR attendees include names recognized as executive-level (matched against Repo Map leadership folder contents)

**Routing:**
- Route to the `meeting-home`-tagged folder that is in a leadership/strategy area of the Repo Map
- If multiple `meeting-home` folders exist, prefer the one whose Repo Map description includes leadership/strategy keywords

**Example:**
- Title: "SLT Q2 Planning"
- Repo Map has `knowledge/leadership/` tagged `meeting-home`
- Route to: `knowledge/leadership/2026-03-31-slt-q2-planning.md`

### 4. General Meeting

**Detection:**
- None of the above patterns match

**Routing:**
- Route to any folder tagged `meeting-home` in the Repo Map
- If multiple `meeting-home` folders: ask user to choose
- If no `meeting-home` folder: ask user for destination

---

## Filename Convention

All meeting notes use the date-slug pattern:

```
<YYYY-MM-DD>-<meeting-slug>.md
```

### Slug Generation
1. Start with the meeting title
2. Lowercase
3. Replace spaces and special characters with hyphens
4. Remove consecutive hyphens
5. Truncate to 40 characters max
6. Remove trailing hyphens

### Examples
| Title | Filename |
|-------|----------|
| 1-1 with Aarav | `2026-03-31-1-1-aarav.md` |
| SLT Q2 Planning | `2026-03-31-slt-q2-planning.md` |
| Architecture Review — Satori DLP | `2026-03-31-architecture-review-satori-dlp.md` |
| Weekly Team Sync | `2026-03-31-weekly-team-sync.md` |

### Duplicate Handling
If a file with the generated name already exists at the destination:
- Append `-2` before `.md`: `2026-03-31-1-1-aarav-2.md`
- If `-2` exists: `-3`, `-4`, etc.

---

## Confirmation Behavior

| Autonomy level | Routing behavior |
|----------------|-----------------|
| Ask before everything | Show proposed destination, confirm before moving |
| Ask before destructive | Show proposed destination, confirm before moving |
| Hands-off | Route automatically, report after completion |

**Exception:** Project meeting routing always asks, regardless of autonomy level. Auto-routing to an active project workspace risks cluttering the project with non-essential files.
