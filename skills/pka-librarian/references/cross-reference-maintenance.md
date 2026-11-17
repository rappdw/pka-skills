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
- File mentions "Orion" → candidate back-ref to `projects/orion/`
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

## Automatic back-references for people: the timeline (v1.7)

For people, the back-reference is now automatic. When a note is filed, `.pka/bin/pka-tools post-route` adds one line to the `## Timeline` block in the `index.md` of each person the note belongs to:

```markdown
## Timeline
<!-- pka:timeline v1 — maintained by pka-tools; newest first; edit summaries freely, leave links alone -->
- 2026-11-14 · meeting · [[leadership/2026-11-14-slt-sync|SLT sync]] — deferred the vendor decision; Priya owns the adapter spike
<!-- /pka:timeline -->
```

Only certain or high-confidence evidence counts: the note is in the person's folder, or its `person` / `attendees` frontmatter or `## Attendees` links resolve to them, or the person's slug is part of the filename. A mention in the body does not put a note on a timeline; lint rule 5 reports those as candidates. File renames are followed (`pointers rename` rewrites timeline links too).

The older `## Mentioned in`, `## Related meetings` and `## Inbound References` sections are no longer written. Existing ones are left as they are.

For entities other than people (projects, topics, wikis), back-references remain lint-only as described above.

---

## User Can Always Override

If a user doesn't want a particular file cross-referenced:

- Add a frontmatter flag: `no-backref: true`
- Lint skips files with this flag

The timeline honours this flag: a note with `no-backref: true` goes on nobody's timeline. Lint skips it too.
