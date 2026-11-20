# Lint Rules

Health checks for the PKA knowledge base. Lint produces a report; the user
reviews it and acts. Lint never edits, moves or deletes a file.

Most of lint is mechanical, so a tool does it:

```
.pka/bin/pka-tools lint            # full: rules 1-5 and 8
.pka/bin/pka-tools lint --quick    # rules 1-4, 8a and 8b
```

It needs no model and no network, writes `owner-inbox/librarian-lint-<YYYY-MM-DD>.md`
(replacing the same day's report, but keeping what you appended to it) and
changes nothing else. It never writes through a symbolic link: if the report's
path or `owner-inbox/` is a link, it stops and says so. Two rules need
judgement and are yours: **6** and **7**. On a full lint you run the tool
first, then add your findings for those two to the report it wrote.

---

## When to Run

- On demand: "run a health check", "lint my knowledge base", "what needs attention?"
- After large imports or structural changes
- Weekly, unattended, if the user installed the schedule entry (see "Scheduling")

---

## How to run a lint

1. Run `.pka/bin/pka-tools lint --json` ("quick lint": add `--quick`). Do not
   re-derive rules 1-5 or 8 by reading files; take them from the result.
2. **Full lint only:** work out rules 6 and 7 (below) and append them to the
   report, under the line `<!-- librarian:rules-6-7 -->` in the section
   "Librarian checks (rules 6 and 7)", replacing the sentence that says they
   were not run. Change nothing above that line. A later run the same day
   rewrites what is above the line and keeps what you put below it. A quick
   lint never replaces a full report from the same day: it prints its results
   and leaves the report as it is.
3. Tell the user the counts per rule, the report path, and the two or three
   findings most worth acting on. Do not paste the report.
4. Act on a finding only when the user asks, one finding at a time (see "Acting
   on a finding").

If `.pka/bin/pka-tools` is missing or older than the plugin, ask for
`bootstrap upgrade` first, as for any other mechanical step.

---

## Rules the tool runs

Every finding in the report ends with its id, like `[id: 8a-3f9c21d0]`.

### 1. Left in the unsorted inbox

**Detects:** things in `team-inbox/unsorted/` that were last changed more than 14
days ago. "Last changed" is the later of the file's modification time and the
time it arrived or was renamed, so an old PDF dropped in today is new. An
earshot capture directory there counts as one item.

**Action hint:** "Route these or delete them. Say: 'process team-inbox/unsorted'."

### 2. Broken links

**Detects:** a link whose file is not there, in any markdown file lint scans.

- `[[wikilinks]]`, with or without an alias (`|Title`, or `\|Title` in a table),
  a heading or block anchor, or a `.md` suffix; targets that name a PDF, image
  or other non-markdown file; the wiki form `[[<wiki-home>/<slug>/wiki|Title]]`.
  A wikilink is read relative to the vault (`knowledge/`).
- Relative markdown links `[text](path)`, including `%20`, `<path with spaces>`
  and parentheses in a name, and reference-style links (`[text][ref]` with a
  `[ref]: path` line; the path on that line is what is checked). They are read
  relative to the file they are in.
- **Names must match exactly**, including upper and lower case, so the same
  report comes out on a Mac and on Linux. A link that is right except for its
  case is reported as "differs only in upper and lower case".
- **Bare names.** In an Obsidian vault `[[Target Note]]` is fine when exactly
  one note in the vault has that name (Obsidian's own short form); it is
  reported when no note has it, or when several do ("ambiguous"). Without
  Obsidian a bare name is reported, with the full link to use when exactly one
  note has that name.
- **Not checked:** web and mail links, `#anchor`-only links, absolute paths and
  paths that leave the workspace; a markdown link whose path has a raw space
  and no `<…>` around it; HTML `<a href>`; and anything inside code spans,
  fenced or indented code blocks, HTML comments, Obsidian `%% comments %%` or
  `$$ math $$`.

A link inside a `_MOC.md` Pointers table is marked with its row's topic.

**Action hint:** "Fix or remove these references." The librarian is append-only
in Pointers tables: remove a dead pointer link only when the user asks for that
row to be fixed.

### 3. Stale wiki sources

**Detects:** a path in backticks in a `wiki.md`'s `## Sources` list that is not
there (tried from the workspace root, the vault, and the wiki's own folder).
Bulleted and numbered items are read; a `#section` after the path is ignored;
backticked words that are not paths are left alone.

**Action hint:** "Update the wiki's Sources list or restore the file."

### 4. Empty Repo Map folders

**Detects:** a Repo Map row whose folder is missing, or holds no `.md`,
`.markdown`, `.txt`, `.pdf` or `.docx` file.

**Action hint:** "Remove the row from the Repo Map, or archive the folder."

### 5. Notes not on a person's timeline (information)

**Detects:** dated notes that belong on someone's timeline and are not on it. It
uses the same evidence rules as filing a note and as the timeline backfill (the
note is in the person's folder, or names them in `person` / `attendees`
frontmatter or `## Attendees`, with certainty). A name in the body does not
count, and a note with `no-backref: true` is left out.

This is **one informational line** with a count and up to 20 examples, not one
finding per note. It replaces the old "missing back-references" rule. It does
not count as a finding, and it **cannot be suppressed**: hiding it would hide
every note left off a timeline from then on. It goes away when the timelines
are backfilled; one note can be kept off every timeline with `no-backref: true`.

**Action hint:** "Ask the librarian to 'backfill timelines'." That plans first
and writes nothing until the user approves (see the librarian's "Backfill person
timelines").

Skipped, with a note in the report, when the workspace has no people folder.
Full lint only.

### 8. Duplicates

| Rule | Detects | In quick lint |
|---|---|---|
| 8a | Files that are byte-for-byte the same, of any type | yes |
| 8b | The same text once frontmatter, upper and lower case and spacing are set aside | yes |
| 8c | Near-duplicates (at least 80% of their five-word passages in common) and one note contained in another (at least 90% of the shorter one), for notes of 200 words or more | no |
| 8d | Duplicate entities: two person folders that answer to the same name or alias, or where one folder name is contained in the other (`priya`, `priya-nair`); two wikis with the same `topic`; one topic on two rows of the same MOC's Pointers table | no |

**One set of copies is one finding**, filed under the broadest rule that holds
for it. If a note has an identical copy, a re-saved copy and a near copy, that
is a single 8c finding listing all four files, not three findings.

For 8a to 8c the report shows each set as a table: path, size, last-modified
date, how many files link to it, and how each file compares with the
**suggested keeper** ("identical bytes", "same text", "near copy"). The keeper
is the file with the most links to it, then one that is not in an inbox, then
the oldest. The suggestion is a starting point; the user decides.

**Not reported:**

- an OCR sidecar (`report.pdf.txt`) beside its source: the sidecar stands in for
  the source's text and is never listed itself;
- anything in an earshot capture directory;
- the same topic in two different MOCs (that is intended);
- anything under `.pka/`, in a dot-folder, or matched by `.pkaignore`;
- lint's own reports and the backfill's plan reports in `owner-inbox/`;
- `_MOC.md` files, as duplicates of each other;
- text with fewer than about 80 characters outside its headings (two notes
  holding only the same headings, two `# TODO` files), and notes under 200
  words for 8c;
- files other than text that are smaller than 16 bytes.

**Known limit:** 8c compares five-word passages, so it does not compare text
written without spaces between words (Chinese, Japanese). Exact and re-saved
copies of such notes are still found by 8a and 8b.

**Information only:** a copy in a wiki's `sources/` folder of a file that is
also filed elsewhere. That is how a wiki keeps its sources; it is listed once so
the user knows, and it does not count as a finding.

**Action hints:** keep one copy and delete or move the others (links to a copy
that goes will then show under rule 2); for near-duplicates it is often raw
notes beside a reconciled version, or a `-2` copy; for entities, merge the two
or record that they are different by suppressing the finding.

---

## Rules you run (full lint only)

### 6. Contradiction candidates

**Detects:** a wiki not updated for 30 days or more, with 3 or more newer
authored notes on its topic that are not in its `## Sources`.

**Method:** for each `wiki.md`, read `last-updated`; search for the topic slug
(`.pka/bin/pka-tools search "<topic>"` in index mode) among notes modified
later; leave out notes already cited. Report when 3 or more remain.

**Why:** it surfaces a wiki that has fallen behind, without claiming a specific
contradiction.

```
### Contradiction candidates (N)
- `knowledge/topics/mcp/wiki.md` (updated 45 days ago): 5 newer notes not yet ingested
  - `knowledge/personnel/priya/2026-04-02-1-1-priya.md`
```

**Action hint:** "Consider ingesting these into the wiki."

### 7. Uncited wiki claims

**Detects:** a wiki whose `## Sources` list is empty, or paragraphs in
`## What it is` or `## Key concepts` that cite no path.

```
### Uncited wiki sections (N)
- `knowledge/topics/agents/wiki.md`: ## Key concepts has 2 paragraphs without citations
```

**Action hint:** "Add citations or rewrite with sources."

---

## Acting on a finding

Lint never fixes anything by itself, and neither do you without being asked.
When the user asks:

- **Duplicates.** Show the group, confirm which copy stays, then delete or move
  the others as the user directs (deleting always needs a yes). If a removed
  copy had links to it, rewrite them to the keeper with
  `.pka/bin/pka-tools pointers rename <removed> <keeper> --notes`, then
  `.pka/bin/pka-tools index`.
- **Duplicate people.** Merging two person folders is the user's decision. Move
  the notes, then `pointers rename <old folder> <new folder> --prefix --notes`.
  If the two are different people, suppress the finding.
- **Broken links.** Fix the link text in the note. In a Pointers row, edit the
  row only when asked.
- **A finding that is fine as it is.** Suppress it.

## Suppressing a finding

```
.pka/bin/pka-tools lint suppress <id> --reason "why this is fine"
.pka/bin/pka-tools lint suppressions          # what is suppressed, and why
.pka/bin/pka-tools lint unsuppress <id>
```

- Suppress only when the user says a finding is fine, and record their reason.
- The id comes from a lint report of the last 30 days (so an id from
  yesterday's full lint still works after today's quick one). An id no report
  has is refused, with the nearest ones listed.
- Rule 5's line cannot be suppressed (see rule 5).
- Running `suppress` again with a new `--reason` replaces the reason.
- A suppressed finding is left out of later reports and counted on the
  "Suppressed" line. Suppressions live in `.pka/lint-suppressions.json`.
- An id belongs to the exact files or link it names. A set of duplicates that
  gains or loses a file is a new finding with a new id. A **full** lint then
  notes the old suppression as no longer matching anything; a quick lint does
  not look at every rule, so it does not say.

---

## Scheduling

`.pka/bin/pka-tools lint schedule` prints a cron line and a macOS launchd file
that run a quick lint every Monday morning and append their output to
`.pka/lint-cron-log.txt`, so a run that fails leaves a trace. **It installs
nothing**, and neither do you: show the user the entry and let them install it.

At session start, `.pka/bin/pka-tools lint latest` says how old the newest
report is and how many of its findings are still open (findings suppressed
since are not counted). When it is 7 days old or newer and has open findings,
the orchestrator mentions it once in the greeting.

---

## What Lint Does NOT Do

- **Does not fix anything.** Report only.
- **Does not re-index.** That is a separate librarian capability.
- **Does not decide contradictions.** It surfaces candidates.
- **Does not move or delete files.** The user acts on the report, or asks you to.

## Performance

A quick lint of a few thousand notes takes about a second and a full lint a few
seconds; twenty thousand notes take about 5 and 20 seconds. Rules 6 and 7 take
as long as your searches do.
