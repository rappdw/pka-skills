# Cross-Reference Maintenance

What links a filed note back to the people, projects and topics it is about, and
what does not.

The rule throughout: a wrong link is worse than no link, so a back-reference is
written only on structured evidence, by the tool. The librarian never adds one
by reading a note's body.

---

## What is maintained, and what is not

| A note is about | What is written | By |
|---|---|---|
| A person | One line on the `## Timeline` of their `index.md` | `pka-tools post-route` when the note is filed; `pka-tools timeline plan` / `apply` for older notes |
| A project | Nothing | — |
| A topic with a wiki | Nothing. A wiki gains a source only through an ingest the user approves | `pka-wiki` |

A name that only appears in the body of a note ("Priya", "Orion", "MCP") creates
no link and is not tracked anywhere. Nothing records "mentions" for later use.

---

## People: the timeline

When a note is filed, `.pka/bin/pka-tools post-route` adds one line to the `## Timeline` block in the `index.md` of each person the note belongs to:

```markdown
## Timeline
<!-- pka:timeline v1 — maintained by pka-tools; newest first; edit summaries freely, leave links alone -->
- 2026-11-14 · meeting · [[leadership/2026-11-14-slt-sync|SLT sync]] — deferred the vendor decision; Priya owns the adapter spike
<!-- /pka:timeline -->
```

Only certain or high-confidence evidence counts: the note is in the person's folder, or its `person` / `attendees` frontmatter or `## Attendees` links resolve to them, or the person's slug is part of the filename. A mention in the body does not put a note on a timeline, and lint does not report it. File renames are followed (`pointers rename` rewrites timeline links too).

`pka-meetings` writes the `## Attendees` links that this evidence comes from (see its `references/attendee-linking.md`); it does not write the timeline line itself.

The older `## Mentioned in`, `## Related meetings` and `## Inbound References` sections are no longer written. Existing ones are left as they are; the backfill reads the links in them as evidence.

---

## What lint says about cross-references

- **Rule 5** (the tool, full lint): one informational line counting the dated notes that belong on someone's timeline, by the evidence above, and are not on it. It is the number of lines a backfill would add. It never lists a note because a name appears in its body.
- **Rule 6** (yours, full lint): a wiki not updated for 30 days with 3 or more newer notes on its topic that it does not cite. This is the one place a search for a topic's name is used, and it produces a suggestion to ingest, never a link.
- **Rule 2** (the tool): links that exist and point at nothing.

See `lint-rules.md` for each.

---

## Keeping a note off every timeline

Add a frontmatter flag to the note:

```yaml
no-backref: true
```

A note with this flag goes on nobody's timeline, at filing and in a backfill, and rule 5 does not count it.
