# Cross-Reference Maintenance

How librarian surfaces and (minimally) maintains back-references between
authored notes, personnel folders, project workspaces, and topic wikis.

---

## Scope for v1.0

**In scope (MVP):**
- Surfacing missing back-references via lint (see `lint-rules.md`)
- Recording entity mentions when files are filed (for future use)

**Deferred to future versions:**
- Automatic back-reference insertion when files are filed
- Bidirectional link maintenance on file moves/renames
- Cross-wiki automatic linking

The v1.0 model: **librarian surfaces, user decides**. Cross-reference automation
is high-risk (wrong links are worse than no links) — defer until lint reports
prove the patterns are reliable.

---

## What Gets Back-Referenced

When a new file is filed (by librarian or pka-meetings), the following entity
mentions are worth tracking:

| Entity type | Detection method | Back-reference target |
|-------------|------------------|----------------------|
| Person | Matches personnel folder name/slug | `personnel/<person>/` |
| Project | Matches project folder slug | `projects/<project>/` |
| Topic wiki | Matches `wiki-home/<topic>/` slug | `knowledge/topics/<topic>/wiki.md` |
| Meeting series | Matches date-slug pattern of another file | `meeting-home/` folders |

---

## Mention Detection Method

Simple string matching against Repo Map entries. Not NER.

Examples:
- File mentions "Maria" or "maria" → candidate back-ref to `personnel/maria/`
- File mentions "Satori" → candidate back-ref to `projects/satori/`
- File contains `MCP` → candidate back-ref to `knowledge/topics/mcp/wiki.md`

False positives are acceptable because lint *surfaces candidates*, doesn't act.

---

## Integration with Meetings Attendee Linking

`pka-meetings` already does targeted back-ref insertion for attendees in meeting
notes. That's the template — narrow scope, confirmed matches, explicit placement.

Librarian lint generalizes the *detection* of missing back-refs without
expanding the *automatic insertion*. If you've been using meetings, you'll
already have back-refs for people who attend meetings. Lint surfaces the gap
for people mentioned but not attending.

---

## Future: Automatic Back-Reference Maintenance (v1.1+)

Design sketch for a future release:

**Trigger:** File is filed into knowledge base via librarian or meetings.

**Flow:**
1. Extract entity mentions from new file
2. For each confirmed match (high-confidence only):
   - Locate entity's folder or wiki
   - Find or create a `## Inbound References` section
   - Append: `- [<new-file>](relative/path) — <date>`
3. Log back-refs added to session-log

**Risks to resolve first:**
- False positives polluting entity pages
- Back-ref section placement conventions
- Handling of file renames (need to update back-refs too)
- User control over which entity types get auto-backref'd

Lint in v1.0 proves out the detection quality before committing to automation.

---

## User Can Always Override

If a user doesn't want a particular file cross-referenced:

- Add a frontmatter flag: `no-backref: true`
- Lint skips files with this flag

(Implementation detail for v1.1.)
