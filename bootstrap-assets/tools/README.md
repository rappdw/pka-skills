# pka-tools

The deterministic half of pka-skills. The skills decide what a note is about and where it belongs; `pka-tools` makes the edit. It exists because path arithmetic, table edits and SQL were previously written as prose for a model to re-derive each session, and the tests ran against reference code that never shipped.

- Python 3.9 or newer, standard library only. Nothing to install.
- No network calls.
- No git. Nothing is staged, committed or pushed; a command's changes are left in the working tree.
- Vendored into a workspace at `.pka/bin/pka-tools` by `pka-tools install` (see [`../README.md`](../README.md)). Roles run the workspace's copy.

```
.pka/bin/pka-tools <command> [--workspace DIR] [--json]
```

The workspace is `--workspace`, else `$WORKSPACE_ROOT`, else the nearest folder above the current one that contains `.pka/`. Paths given to commands are relative to the workspace root. A `knowledge/` that is a symbolic link to a vault kept elsewhere works; symbolic links *inside* the folders being walked are skipped. `--json` prints the result as data.

## Commands

| Command | What it does | Writes |
|---|---|---|
| `status` | Workspace root, vault, the Obsidian predicate, what timelines can reach (`timeline_reach`), storage mode and schema version, index roots, meeting and people folders | nothing |
| `install [--dry-run]` | Vendor the plugin's helpers into `.pka/` by manifest. Run from the plugin's copy | `.pka/bin/`, `.pka/upgrade-roles.py`, `.pka/manifest.json` |
| `db init` | Create `.pka/knowledge.db` at the current schema | the database |
| `db migrate` | Print the migration plan. Changes nothing | nothing |
| `db migrate --apply` | Back up, migrate in one transaction, verify, roll back on failure | the database, `.pka/db-backups/` |
| `db backup` | Copy the database to `.pka/db-backups/` | a backup file |
| `db schema` | Tables, columns and row counts | nothing |
| `index [PATH…] [--rebuild] [--prune] [--dry-run]` | Index new and changed files, drop rows for removed ones | the database |
| `search TERM… [--limit N] [--any]` | Full-text search with quoted terms and the pointer-row boost | nothing |
| `actions [--since D] [--until D] [--all-dates] [--scope meetings\|all] [--under F]` | Open checkboxes in dated notes, with owners and due dates (see "`actions`") | nothing |
| `post-route FILE [--topic S] [--section H] [--also P]… [--dry-run]` | Everything after filing a note: frontmatter and MOC link (Obsidian), pointer row, timeline, index | the note, `_MOC.md` files, person `index.md` files, the database |
| `moc add-link FILE [--section H]` | Add a `- [[note]]` bullet to the nearest `_MOC.md` | one `_MOC.md` |
| `pointers add FILE [--topic S] [--entities A,B] [--context T] [--moc M] [--dry-run]` | Record a routed file in its domain MOC's Pointers table | `_MOC.md` files |
| `pointers init [FOLDER…]` | Opt in to the pointer layer without Obsidian: a `_MOC.md` with an empty Pointers table per folder | new `_MOC.md` files |
| `pointers rename OLD NEW [--prefix] [--notes] [--dry-run]` | Rewrite links after a file or folder moved (MOCs; with `--notes`, every note in the vault, and every note of OLD or NEW when that folder is outside the vault). Wikilinks only | `_MOC.md` files, notes |
| `pointers check [--strict]` | Broken pointer links, unreadable tables, rows over the soft cap | nothing |
| `pointers list [MOC]` | Pointer rows as data | nothing |
| `obsidian bootstrap [--dry-run]` | The one-time mechanical retrofit of `knowledge/` | MOC and index stubs, frontmatter |
| `people list` | Every person folder, with name and aliases | nothing |
| `people resolve NAME…` | Which person a name, link or slug means: high, ambiguous or none | nothing |
| `people alias SLUG ALIAS` | Record a name the user says means this person | the person's `index.md` |
| `timeline add FILE [--person S]… [--summary T] [--summary-for S=T]… [--kind K] [--label L] [--date D] [--include-large]` | Put a note on the timelines of the people it belongs to | person `index.md` files |
| `timeline who FILE` | Whose timeline a note belongs on, with the evidence | nothing |
| `timeline list SLUG` | A person's timeline entries | nothing |
| `timeline rename OLD NEW [--prefix]` | Follow a moved note in every timeline (`pointers rename` does this too) | person `index.md` files |
| `timeline check [--strict]` | Unreadable blocks, links to missing notes, lines out of order | nothing |
| `timeline strip [--person S]` | Remove timeline blocks (rollback) | person `index.md` files |
| `timeline plan [--since D] [--person S] [--include-large] [--no-write]` | Backfill: the timeline lines existing notes would get, as a review report and a plan file | `owner-inbox/timeline-backfill-plan-<date>.md`, `.pka/backfill/plan-<id>.json` |
| `timeline apply PLAN [--dry-run]` | Backfill: write a plan's lines, back up and verify | person `index.md` files, `.pka/backups/<id>/` |
| `timeline restore ID [--force] [--dry-run]` | Put the person pages back as they were before an apply | person `index.md` files |
| `log add --role R --summary S [--open T] [--next N]` | Append one well-formed session-log entry | `.pka/session-log.md` |
| `log open [--last N]` | Open threads of recent entries, newest first | nothing |
| `log check [--strict]` | Entries that do not follow the grammar | nothing |
| `lint [--quick] [--strict] [--no-report]` | Health checks (see "Lint"). `--strict` exits 1 when there are unsuppressed findings | `owner-inbox/librarian-lint-<date>.md` |
| `lint suppress ID [--reason T]`, `lint unsuppress ID` | Hide a finding from later reports, or bring it back | `.pka/lint-suppressions.json` |
| `lint suppressions` | What is suppressed, and why | nothing |
| `lint latest` | The newest report: path, date, age in days, finding count, and whether session start should mention it | nothing |
| `lint schedule` | Print a weekly cron line and a launchd file for a quick lint. Installs nothing | nothing |

### Deprecated, accepted and ignored

`pka-tools` used to commit what it filed into the nested repositories of a "hybrid monorepo". That support was removed. Role files written for earlier releases still name the commands and flags below, so they are accepted for now and do nothing. Do not use them in new text; a later release may reject them.

| Still accepted | What it does now |
|---|---|
| `commit [-m S] [--body T] [--stage-only] [PATH…]` | Nothing. Exits 0 and says pka-tools no longer commits. Never runs git |
| `post-route … --role R`, `-m SUBJECT`, `--body T`, `--no-commit` | Ignored. `post-route` commits nothing either way |
| `obsidian bootstrap --commit` | Ignored. The summary says nothing was committed |
| `install --git` | Ignored. The nested-repository scripts are no longer shipped |

In a workspace whose root still has a `.meta` file, `post-route` adds a note to its result (`notes` in JSON, a `Note:` line in text) saying the note was not committed, because routes there used to end in a commit.

`pointers add`, `moc add-link` and `post-route` also take `--create-moc` / `--no-create-moc`. By default a missing `_MOC.md` is created only in an Obsidian vault: without Obsidian the pointer layer and MOC links are opt-in (`pointers init`).

### `post-route`

The one command a skill runs after it has put a note in place. Its steps, each reported on its own line:

| Step | Does | Runs when |
|---|---|---|
| `frontmatter` | missing schema keys and the domain tag | Obsidian vault, a markdown note (`.md`, `.markdown`) inside the vault |
| `moc-link` | a `- [[note]]` bullet in the nearest `_MOC.md` | Obsidian vault (or `--create-moc`) |
| `pointers` | a pointer row in the domain MOC(s) | note inside the vault; without Obsidian only into existing MOCs |
| `timeline` | a line on the timeline of each person the note belongs to (`--summary`, `--summary-for`, `--person`, `--include-large`, `--no-timeline`) | a people folder exists, and the note is one a timeline can link to: in the vault with Obsidian; anywhere but the inboxes and hidden folders without |
| `index` | the note, every MOC changed above, and every `--also` path | index mode |

Arguments are checked before anything is written: a bad `--section` or `--topic`, or an `--also` that names a folder, exits 64 with every file as it was. An `--also` path that no longer exists is fine: naming the old location of a moved note is how its rows leave the index.

A step that cannot do its work reports why and the later steps still run. Running it twice changes nothing. It refuses MOCs, files under `.pka/`, and anything inside an earshot capture directory. Nothing is committed: `touched` in the result lists the files it changed, for the caller to report.

### Index roots

`index` reads, and `search` therefore finds, what is under the index roots; `status` lists them. They are the Repo Map folders whose Priority is Active or Reference and that exist. With no such row: `knowledge/` if there is one, else every top-level folder except the inboxes, `projects/`, `meeting-notes/` and `.pkaignore` matches.

- A row inside another root is folded into it. Priority is not an exclusion that reaches downwards: with `knowledge/` Active and `knowledge/archive/` Archive, the archive folder is indexed because it is inside a root. An Archive row keeps a folder out only when nothing above it is a root.
- **Archived projects.** The archive destination's row is Archive, so the destination is not a root. A project moved into it is indexed when it has its own row with Priority Reference (the transition workflow in the pka-bootstrap skill adds it before running `index`); `status` then lists the project's folder as a root. Without that row, `index` drops the project's old `projects/…` rows and adds none, and `search` no longer finds it. Once it is a root, every file in it is indexed at any depth: the default `.pkaignore` rule `projects/*/*/*`, which limits an active project to its top-level files, does not match the new path.
- **A folder that stops being a root** keeps its rows. A plain `index` removes rows for missing files only under the roots it reads; rows outside them whose file is gone are counted as `stale_elsewhere` and removed by `index --prune`. That is what a project restored from the archive needs: its row is taken out of the Repo Map, the folder is back under `projects/`, and `--prune` clears the rows left at the archive path. Rows for files that still exist in a folder that left the map are not removed by either.

### `actions`

Read-only: it never edits a note, and an item is read in the form it was written. Each open checkbox (`- [ ]`, `* [ ]`, `1. [ ]`, at any indentation, outside fenced code blocks) is returned with `path`, `line`, `date` (the note's), `text` (the item as written), `owners`, `due` and `due_text`. A ticked box counts under `closed` and is not returned.

| Form | Example | Written by |
|---|---|---|
| `@owner`, `by <date>` | `- [ ] Send the comparison — @Sam — by 2026-05-01` | pka-meetings |
| bold lead-in, `(due: …)` | `- [ ] **Robin**: Draft the hiring plan (due: 2026-12-01)` | thinkkit `take-notes` |

- **`owners`**: every `@name`, and the names in a bold lead-in followed by a colon at the start of the item (`**Robin**:`, `**Robin:**`, `**Robin and Sam**:`; split on `,`, `and`, `&`, `/`). A lead-in is taken as owners only when every piece looks like a name: one to four words, each starting with a letter that is not lower case (particles such as `de` and `van` aside), no digits, not a label (`Note`, `TODO`, `Action`, `Decision`, `Owner`, `TBD` and the like). Bold without a colon, or not at the start, is not an owner. Each owner is listed once, in the order written.
- **`due`** is `YYYY-MM-DD` or null; **`due_text`** is the due date as written, or null. Read in this order: (1) `by` or `due`, an optional colon, and an ISO date, anywhere in the item; (2) bracketed `(due: …)` / `(by: …)` holding other text, where a month-name date (`Dec 1`, `December 1st, 2026`, `1 Dec 2026`) is resolved, a missing year being the first such day on or after the note's date (unresolved in an undated note), and everything else (`Friday`, `end of month`, `12/1`) leaves `due` null with the words in `due_text`; (3) an ISO date that ends the item after a dash (`— @Sam — 2026-05-01`). An ISO date elsewhere in the item is not a due date, and a date after a dash that follows another date (`2026-11-01 — 2026-11-21`) is a period.
- Nothing is guessed: no weekday arithmetic, no day/month order for numeric dates, no owner from prose ("Robin to draft…").

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Done, including "nothing to do" |
| 1 | The operation was attempted and failed (a migration rolled back), or a `--strict` check found something |
| 2 | A prerequisite is missing: Python older than 3.9, SQLite without FTS5 |
| 3 | The workspace is not ready: no `.pka/`, no index, index needs `db migrate`, no Obsidian vault |
| 64 | Bad arguments. Nothing was touched |

A caller should treat anything other than 0 as "did not happen" and relay the message on stderr.

## Editing rules

Every command that writes to a user's file follows these. The tests in `tests/tools/` hold them to it against a fixture vault with CRLF files, a byte-order mark, a file with no final newline, non-UTF-8 bytes, and names with spaces, commas and non-ASCII letters.

1. **Change only owned lines.** A pointer-table row, a `tags:` line, a line the tool inserts. Everything else stays byte for byte: line endings, the byte-order mark, trailing whitespace, a missing final newline.
2. **Never re-render.** Frontmatter is not parsed into a document and written back; tables are not rebuilt. New entries go at the end of a cell or a list. Nothing is sorted, re-spaced or re-quoted.
3. **When unsure, skip and report.** The file is left alone and named in the output when: its frontmatter is outside the supported subset; a Pointers table has an unexpected header; it is not UTF-8; it is read-only; it uses bare carriage returns as line endings; it has a code fence that is never closed; or its name contains a character a wikilink cannot express (`[ ] | # ^`).
4. **Idempotent.** Running a command twice changes nothing the second time.
5. **Atomic writes.** A file is written to a temporary name and renamed into place, so an interrupted run cannot leave half a note. The file keeps its permissions; extended attributes (Finder tags, for example) on an edited file are not carried over. A file that is a symbolic link is written through the link, not replaced by a regular file.
6. **Fenced code blocks and HTML comments are not structure.** A `## Pointers` heading, a table, a `## Files` heading or a link inside a fenced block or a multi-line `<!-- … -->` comment is ignored. `pointers rename` and `moc add-link` also ignore links inside `inline code` and escaped `\[[...]]`. Setext headings (`Title` over `-----`) end a section like `## Title` does.
7. **Bodies are not interpreted.** Pointer maintenance and the Obsidian retrofit use filenames, folders and frontmatter. (`index` reads bodies to index them; `actions` reads them for checkboxes and never writes.)

## People and timelines

- A person is a subfolder of the people home (Repo Map tag `people-home`; fallback `knowledge/personnel/`). `index.md` may give `name` and `aliases`. A symbolically linked folder is not a person (its notes live elsewhere). A `people-home` tag on the vault root itself is refused.
- `people resolve` answers **high** only for an exact slug, name or alias (case, accents, punctuation, `@` and titles ignored), the slug's words in either order, a link to the person's folder, or a first name only one person has. A last name alone, or a name that fits two people, is **ambiguous** — including a one-word slug that is also someone else's first name (`priya` and `priya-orion`). Nothing is guessed: nicknames become aliases when the user says so, and `people alias` refuses a name that already means, or could mean, someone else.
- A timeline is a block between `<!-- pka:timeline v1 … -->` and `<!-- /pka:timeline -->` under `## Timeline` in the person's `index.md`. Lines are `- <date> · <kind> · <link>[ — <summary>]`, newest first. A note is on a timeline when a line's own link points at it (links inside summaries do not count; a short `[[name]]` that can only mean the note does), so adding is idempotent; an existing line is never changed except to follow a renamed note. A missing `index.md` is created as a stub, only inside an existing person folder.
- Evidence: the note is in the person's folder (T1); or its `person` / `attendees` frontmatter, an `## Attendees` link, or a filename containing the slug names them with high confidence (T2). Body mentions do not count. More than 8 resolved attendees: none are added unless `--include-large`. `no-backref: true` opts a note out.
- Summaries are at most 140 characters (cut without splitting a character); the role writes them from the note.
- Without Obsidian the links are relative markdown links; `%` and `#` in a filename are percent-encoded.
- **Reach** (`Workspace.link_root`). With Obsidian a timeline links only to notes in the vault, and keys are vault-relative. Without it a timeline links to any note in the workspace (`projects/`, a root meeting folder) except `owner-inbox/`, `team-inbox/` and hidden folders, and keys are workspace-relative; a wikilink typed by hand is still read relative to the vault, as Obsidian would. `timeline rename` and `pointers rename` take workspace paths (a vault-relative one still works). When a filed note and the person pages it touches are in different repositories, `post-route` commits each repository separately. `graduate.sh` prints the `timeline rename` to run when person pages link into the graduated project.
- **Backfill** (`timeline plan`, `apply`, `restore`). Planning walks what a timeline can link to (not MOCs, person pages, wiki folders, capture directories or `.pkaignore` matches; markdown and office documents), decides who each note belongs to exactly as for a newly filed note, and also counts a link in the old back-link sections of a person's own page (`## Mentioned in`, `## Related meetings`, `## Inbound References`, `## References`) as T2 evidence. A note with no date (filename prefix or frontmatter `date`) is reported, never dated from its modification time; so is a note whose name a link cannot carry (an upper-case `.MD`, angle brackets without Obsidian). Lines get no summary. Plan and backup ids are unique even within one second. The plan records a hash of every page it will write and every note it cites. `apply` first checks the plan file (every target must be the page of a person folder and every line a timeline line linking to its note; anything else is a usage error, exit 64), then refuses if a page or note changed or a planned stub appeared (plan again), or if the plan was made with Obsidian in a workspace without it (or the reverse). It backs the pages up, records each page's new hash before writing it, adds only lines whose note is not already on the timeline, then checks that every planned line is there, every link resolves, and nothing else in that scope changed (dot-folders such as `.obsidian`, and the inboxes, excepted). A failed check, an exception or an interrupt puts every page back. Nothing is committed. `restore` checks that every file in the record is still the page of its person folder (all or nothing), removes stubs the apply created, and refuses a page edited after the apply, or one whose state after the apply was not recorded, unless `--force`; a backup that was rolled back has nothing to restore.
- `timeline strip` removes the blocks, the `## Timeline` heading when nothing else is under it, and an `index.md` that was only the stub the tool created. Text the user typed inside a block goes with it. Whitespace next to the block may differ by a line from before the first `add`.

## Lint

`lint` reads the workspace and writes one file, the report. It never edits, moves or deletes a note, and it runs with no model and no network.

- **Scope.** Every file under the workspace root that `walk` yields (and a `knowledge/` that is a symbolic link): not dot-folders (so not `.pka/`), not `.pkaignore` matches, not the contents of earshot capture directories, not dotfiles, and not the reports the tools themselves write into `owner-inbox/` (`librarian-lint-*.md`, `timeline-backfill-plan-*.md`). Files that are not UTF-8, and files whose name is not, are counted in the report under "Not read".
- **Rule 1.** Things in `team-inbox/unsorted/` whose last change (the later of mtime and ctime, so a file copied in with an old date counts from its arrival) is more than 14 days ago. A capture directory there is one item.
- **Rule 2.** Broken links in markdown files. Wikilinks: alias, anchor, `.md`, non-markdown targets, a leading `/`; read relative to the vault, then the workspace root; a folder counts as present. Markdown links: inline (percent-decoded, `<…>` form, nested parentheses) and reference definitions (`[ref]: path`); read relative to the file. Existence is decided from directory listings with an exact, Unicode-normalised name match, so a case-insensitive filesystem gives the same report as a case-sensitive one; a match that differs only in case is reported with `"reason": "case"`. In an Obsidian vault a bare `[[name]]` matching exactly one vault file (by file name, or note name without `.md`, ignoring case) resolves; several matches are `"reason": "ambiguous"`. Without Obsidian a bare name is reported with the full link as `suggestion`. Skipped: links with a scheme, anchors, absolute paths, paths leaving the workspace, and `[` directly after a word character (`f[i](x)`). Ignored: code spans, fenced and indented code blocks, HTML comments, `%%…%%` and `$$…$$`. Not checked: a destination with a raw space, and HTML `<a href>`. A link in a Pointers row carries its topic.
- **Rule 3.** Path-like backticked spans in bulleted or numbered items of a `wiki.md` `## Sources` list that exist nowhere (root, vault, the wiki's folder); a `#fragment` is dropped.
- **Rule 4.** Repo Map folders that are missing or hold no `.md`, `.markdown`, `.txt`, `.pdf` or `.docx`.
- **Rule 5.** One informational finding, id `5-timelines`: the count of timeline lines `timeline plan` would add. Skipped without a people folder. It cannot be suppressed, and an entry for it in the suppressions file is ignored.
- **Rule 8a-8c.** Files are joined into sets: by SHA-256 (8a), by normalised text (frontmatter the parser accepts dropped, case-folded, whitespace collapsed; 8b), and by near-duplication of one representative per distinct text (8c: notes of 200 or more words whose five-word shingles are at least 80% alike, or where the shorter is at least 90% contained in the longer). Each set is **one finding under the broadest rule that holds**, and each member has a `relation` to the keeper: `keeper`, `bytes`, `text` or `near`. Text files (and files read through an OCR sidecar) need 80 characters outside headings to take part; other files need 16 bytes; `_MOC.md`, empty files, dotfiles and sidecars never take part.
- **Rule 8d.** Two person folders sharing a name, slug or alias (compared as `people resolve` compares), or one slug's words a proper subset of the other's; two `wiki.md` with the same `topic`; one topic slug on two rows of one MOC's Pointers table.
- **`--quick`** runs 1 to 4, 8a and 8b. Rules 6 and 7 are the librarian's; the report ends with a section and a marker line, `<!-- librarian:rules-6-7 -->`. A later run the same day carries over whatever is below that line. A quick run never replaces a same-day full report: it returns `"report": null` and `"report_kept": "<path>"`.
- **How 8c finds pairs.** Shingles are hashed with CRC-32 (the same on every machine; `hash()` is salted). Candidates come from a one-permutation MinHash signature (64 bins, 16 bands of 4) for similar pairs, and from an index of sampled shingles (hash ending in four zero bits) for containment, which banding cannot find when one note is much longer than the other. An estimate from the signatures or the samples decides whether a pair is worth reading both files for; the files then settle it exactly. Notes that share a band or a sample with more than a few others are compared against a representative, so a family of near-copies costs one comparison per member and is still found whole. Passages shared by more than 50 otherwise different notes are noted as boilerplate. Text without spaces between words (Chinese, Japanese) is not near-compared.
- **Keeper.** Most inbound links, then not in `owner-inbox/` or `team-inbox/`, then oldest; applied once over the whole set. A set with at most one member outside a wiki's `sources/` folder is informational (`"wiki_source_copy": true`).
- **Ids.** `<rule>-<8 hex digits>`, a hash of the rule and its subject: the sorted member paths of a set, the source file and target of a link, the folder of a Repo Map row. The same problem has the same id on every run. A set that gains or loses a member is a different finding; so is a set a quick lint files under 8b that a full lint finds to be part of a larger 8c set.
- **Suppressions.** `.pka/lint-suppressions.json`: `{"version": 1, "suppressed": {"<id>": {"at", "reason", "rule", "subject"}}}`. Read-modify-write happens under an exclusive lock (`flock` on `.pka/`; a lock file where `fcntl` is missing). Keys and entries this version does not know are kept; a byte-order mark is accepted. A file with a higher `version` is read and never rewritten (`suppress` and `unsuppress` exit 1). A file that is not valid JSON, is nested too deeply, or is not an object stops every lint command with exit 1 and is left as it is. `suppress` takes the id from any report of the last 30 days and refuses one that none has (exit 64, with near matches); a second `suppress` with `--reason` updates the reason. In a full lint, suppressions that match nothing are listed as `stale_suppressions`.
- **Report.** `owner-inbox/librarian-lint-<YYYY-MM-DD>.md`. Its first line is `<!-- pka-lint {…} -->` with `version`, `date`, `mode`, `findings`, `info`, `suppressed` and `scanned`. Findings end with `[id: …]`, informational ones with `[id: …, information]`. At most 200 items per rule are shown; the ids of the rest are in `<!-- pka-lint-ids: … -->` lines so they can still be suppressed, and `--json` has everything. Section headings, the summary, the command's text output and `counts` / `info_counts` agree. Two runs over the same workspace on the same day write the same bytes. Informational items do not count as findings, for `--strict` or for `latest`.
- **`lint latest`** reads the newest report with a real date that is not in the future; `findings` is that report's findings less what has been suppressed since. `recent` is 0 to 7 days old; `mention` is recent with open findings.
- **`lint schedule`** prints a cron line (with `%` escaped) and a launchd file that append to `.pka/lint-cron-log.txt`; the launchd label ends in a hash of the workspace path. It never writes a crontab or a launchd file.
- **`PKA_LINT_TODAY=YYYY-MM-DD`** makes lint take that as today (for tests and rehearsals).

### Generated files are never written through a link

A user's note is written through a symbolic link, as an editor would write it. A file the tools generate is not: the lint report, `.pka/lint-suppressions.json`, the backfill's plan (`.pka/backfill/`), its report in `owner-inbox/` and its backups (`.pka/backups/`). If the file's path is a link or not a regular file, or a folder on the way to it is a link or not a folder, the command exits 1 with a one-line message naming the workspace-relative path, and writes nothing. (`.pka/session-log.md` is a file the user owns and keeps the write-through rule.)

## Git rules

There is one: `pka-tools` does not run git. No command stages, commits, resets or pushes, in any repository, and the package has no code that invokes `git`. A workspace may be a repository, contain repositories, or be neither; the tool only edits files. `tests/tools/test_install.py` fails if the package gains a `subprocess` import.

## Database rules

- The schema version is `PRAGMA user_version` (currently 1). `index` and `search` refuse to run against an older schema and say how to migrate.
- `db migrate` without `--apply` is a dry run. `--apply` takes a verified backup first and runs in one transaction.
- Only `file_index`, `search_fts`, `project_lifecycle` and `pka_meta` are created or altered. Other tables are left alone.
- Text that a role stored in `search_fts` for a PDF or Office file is kept across re-indexing until the file is removed. `--prune` removes only rows whose file no longer exists, whatever form the stored path takes.

## Layout

```
tools/
├── pka-tools              launcher (checks the Python version, no bytecode)
└── pka_tools/
    ├── cli.py             argument parsing and output
    ├── workspace.py       root, vault, Repo Map, index roots, walking
    ├── pkaignore.py       .pkaignore matching
    ├── textio.py          byte-faithful reading and atomic writing
    ├── markdown.py        fences, headings, table cells, wikilinks
    ├── frontmatter.py     line-level frontmatter reading and editing
    ├── db.py              schema, migration, backup
    ├── indexer.py         index
    ├── search.py          search
    ├── actions.py         actions
    ├── pointers.py        pointers add / init / rename / check / list
    ├── mocs.py            moc add-link
    ├── postroute.py       post-route
    ├── sessionlog.py      log add / open / check
    ├── people.py          people list / resolve / alias
    ├── timeline.py        timeline add / who / list / rename / check / strip
    ├── obsidian.py        obsidian bootstrap
    ├── backfill.py        timeline plan / apply / restore
    ├── lint.py            lint, its suppressions, latest and schedule
    └── install.py         install and the manifest
```

## Changing it

- Keep it to the standard library and to Python 3.9 syntax (`tests/tools/test_install.py` checks both).
- Every behaviour that writes has a test in `tests/tools/` that runs the vendored copy. Add one with any change.
- Bump `__version__` in `pka_tools/__init__.py` together with `.claude-plugin/plugin.json`; a test fails when they differ.
