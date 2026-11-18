# pka-tools

The deterministic half of pka-skills. The skills decide what a note is about and where it belongs; `pka-tools` makes the edit. It exists because path arithmetic, table edits, SQL and commit mechanics were previously written as prose for a model to re-derive each session, and the tests ran against reference code that never shipped.

- Python 3.9 or newer, standard library only. Nothing to install.
- No network calls.
- Vendored into a workspace at `.pka/bin/pka-tools` by `pka-tools install` (see [`../README.md`](../README.md)). Roles run the workspace's copy.

```
.pka/bin/pka-tools <command> [--workspace DIR] [--json]
```

The workspace is `--workspace`, else `$WORKSPACE_ROOT`, else the nearest folder above the current one that contains `.pka/`. Paths given to commands are relative to the workspace root. A `knowledge/` that is a symbolic link to a vault kept elsewhere works; symbolic links *inside* the folders being walked are skipped. `--json` prints the result as data.

## Commands

| Command | What it does | Writes |
|---|---|---|
| `status` | Workspace root, vault, Obsidian and hybrid-monorepo predicates, what timelines can reach (`timeline_reach`), storage mode and schema version, index roots, meeting and people folders | nothing |
| `install [--git] [--dry-run]` | Vendor the plugin's helpers into `.pka/` by manifest. Run from the plugin's copy | `.pka/bin/`, `.pka/manifest.json`, helper scripts |
| `db init` | Create `.pka/knowledge.db` at the current schema | the database |
| `db migrate` | Print the migration plan. Changes nothing | nothing |
| `db migrate --apply` | Back up, migrate in one transaction, verify, roll back on failure | the database, `.pka/db-backups/` |
| `db backup` | Copy the database to `.pka/db-backups/` | a backup file |
| `db schema` | Tables, columns and row counts | nothing |
| `index [PATH…] [--rebuild] [--prune] [--dry-run]` | Index new and changed files, drop rows for removed ones | the database |
| `search TERM… [--limit N] [--any]` | Full-text search with quoted terms and the pointer-row boost | nothing |
| `actions [--since D] [--until D] [--all-dates] [--scope meetings\|all] [--under F]` | Open checkboxes in dated notes | nothing |
| `commit -m SUBJECT [--body T] -- PATH…` | Commit exactly those paths in their child repo, with the trailer | a git commit |
| `commit --stage-only PATH…` | `git add` the paths and stop (for root-repo side effects) | the git index |
| `post-route FILE [--role R] [-m SUBJECT] [--topic S] [--section H] [--also P]… [--no-commit] [--dry-run]` | Everything after filing a note: frontmatter and MOC link (Obsidian), pointer row, index, one commit | the note, `_MOC.md` files, the database, a git commit |
| `moc add-link FILE [--section H]` | Add a `- [[note]]` bullet to the nearest `_MOC.md` | one `_MOC.md` |
| `pointers add FILE [--topic S] [--entities A,B] [--context T] [--moc M] [--dry-run]` | Record a routed file in its domain MOC's Pointers table | `_MOC.md` files |
| `pointers init [FOLDER…]` | Opt in to the pointer layer without Obsidian: a `_MOC.md` with an empty Pointers table per folder | new `_MOC.md` files |
| `pointers rename OLD NEW [--prefix] [--notes] [--dry-run]` | Rewrite links after a file or folder moved (MOCs; with `--notes`, every note) | `_MOC.md` files, notes |
| `pointers check [--strict]` | Broken pointer links, unreadable tables, rows over the soft cap | nothing |
| `pointers list [MOC]` | Pointer rows as data | nothing |
| `obsidian bootstrap [--dry-run] [--commit]` | The one-time mechanical retrofit of `knowledge/` | MOC and index stubs, frontmatter |
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
| `timeline apply PLAN [--no-commit] [--dry-run]` | Backfill: write a plan's lines, back up and verify; one commit in a hybrid monorepo | person `index.md` files, `.pka/backups/<id>/`, a git commit |
| `timeline restore ID [--force] [--dry-run]` | Put the person pages back as they were before an apply | person `index.md` files |
| `log add --role R --summary S [--open T] [--next N]` | Append one well-formed session-log entry | `.pka/session-log.md` |
| `log open [--last N]` | Open threads of recent entries, newest first | nothing |
| `log check [--strict]` | Entries that do not follow the grammar | nothing |

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
| `commit` | the note, every file changed above, every MOC that already links to the note, and every `--also` path, by path, with the trailer | hybrid monorepo, and not `--no-commit` |

Arguments are checked before anything is written: a bad `--section`, `--topic` or `--also` exits 64 with every file as it was. An `--also` path must be a file, in the same repository as the note, and either exist or be known to git; one that git already has as removed (the old location of a note that was moved and committed) is noted and left out of the commit, so re-running after a move is a no-op.

The commit includes the MOCs the note is recorded in even when this run did not change them, so a change left uncommitted by an earlier run (a refused commit, `--no-commit`) is committed with the note. If the user had their own uncommitted edits in one of those MOCs, they go into the same commit.

A step that cannot do its work reports why and the later steps still run. The exit code is 1 only when git refused the commit. Running it twice changes nothing and makes no second commit. It refuses MOCs, files under `.pka/`, and anything inside an earshot capture directory.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Done, including "nothing to do" and "nothing to commit" |
| 1 | The operation was attempted and failed (a commit was refused, a migration rolled back) |
| 2 | A prerequisite is missing: Python older than 3.9, no `git`, SQLite without FTS5 |
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
7. **Bodies are not interpreted.** Pointer maintenance and the Obsidian retrofit use filenames, folders and frontmatter. (`index` reads bodies to index them; `actions` reads them for checkboxes.)

## People and timelines

- A person is a subfolder of the people home (Repo Map tag `people-home`; fallback `knowledge/personnel/`). `index.md` may give `name` and `aliases`. A symbolically linked folder is not a person (its notes live elsewhere). A `people-home` tag on the vault root itself is refused.
- `people resolve` answers **high** only for an exact slug, name or alias (case, accents, punctuation, `@` and titles ignored), the slug's words in either order, a link to the person's folder, or a first name only one person has. A last name alone, or a name that fits two people, is **ambiguous** — including a one-word slug that is also someone else's first name (`priya` and `priya-orion`). Nothing is guessed: nicknames become aliases when the user says so, and `people alias` refuses a name that already means, or could mean, someone else.
- A timeline is a block between `<!-- pka:timeline v1 … -->` and `<!-- /pka:timeline -->` under `## Timeline` in the person's `index.md`. Lines are `- <date> · <kind> · <link>[ — <summary>]`, newest first. A note is on a timeline when a line's own link points at it (links inside summaries do not count; a short `[[name]]` that can only mean the note does), so adding is idempotent; an existing line is never changed except to follow a renamed note. A missing `index.md` is created as a stub, only inside an existing person folder.
- Evidence: the note is in the person's folder (T1); or its `person` / `attendees` frontmatter, an `## Attendees` link, or a filename containing the slug names them with high confidence (T2). Body mentions do not count. More than 8 resolved attendees: none are added unless `--include-large`. `no-backref: true` opts a note out.
- Summaries are at most 140 characters (cut without splitting a character); the role writes them from the note.
- Without Obsidian the links are relative markdown links; `%` and `#` in a filename are percent-encoded.
- **Reach** (`Workspace.link_root`). With Obsidian a timeline links only to notes in the vault, and keys are vault-relative. Without it a timeline links to any note in the workspace (`projects/`, a root meeting folder) except `owner-inbox/`, `team-inbox/` and hidden folders, and keys are workspace-relative; a wikilink typed by hand is still read relative to the vault, as Obsidian would. `timeline rename` and `pointers rename` take workspace paths (a vault-relative one still works). When a filed note and the person pages it touches are in different repositories, `post-route` commits each repository separately. `graduate.sh` prints the `timeline rename` to run when person pages link into the graduated project.
- **Backfill** (`timeline plan`, `apply`, `restore`). Planning walks what a timeline can link to (not MOCs, person pages, wiki folders, capture directories or `.pkaignore` matches; markdown and office documents), decides who each note belongs to exactly as for a newly filed note, and also counts a link in the old back-link sections of a person's own page (`## Mentioned in`, `## Related meetings`, `## Inbound References`, `## References`) as T2 evidence. A note with no date (filename prefix or frontmatter `date`) is reported, never dated from its modification time; so is a note whose name a link cannot carry (an upper-case `.MD`, angle brackets without Obsidian). Lines get no summary. Plan and backup ids are unique even within one second. The plan records a hash of every page it will write and every note it cites. `apply` first checks the plan file (every target must be the page of a person folder and every line a timeline line linking to its note; anything else is a usage error, exit 64), then refuses if a page or note changed or a planned stub appeared (plan again), or if the plan was made with Obsidian in a workspace without it (or the reverse). It backs the pages up, records each page's new hash before writing it, adds only lines whose note is not already on the timeline, then checks that every planned line is there, every link resolves, and nothing else in that scope changed (dot-folders such as `.obsidian`, and the inboxes, excepted). A failed check, an exception or an interrupt puts every page back. In a hybrid monorepo the commit is skipped, and said so, when a page had uncommitted edits of the user's; a refused commit exits 1. `restore` checks that every file in the record is still the page of its person folder (all or nothing), removes stubs the apply created, and refuses a page edited after the apply, or one whose state after the apply was not recorded, unless `--force`; a backup that was rolled back has nothing to restore.
- `timeline strip` removes the blocks, the `## Timeline` heading when nothing else is under it, and an `index.md` that was only the stub the tool created. Text the user typed inside a block goes with it. Whitespace next to the block may differ by a line from before the first `add`.

## Git rules

- `commit` stages and commits by path: `git add -- <paths>`, `git commit -- <paths>`. Never `-A`. The user's other modified, staged and untracked files are left as they were.
- A path is a path. `*`, `?`, `[` and git's `:(magic)` prefixes are taken literally, a folder is refused (it would sweep in everything under it), and a path that neither exists nor is tracked is a usage error.
- `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE` and the other variables that redirect git are removed from the environment, so a commit made from inside a hook of the root repository still lands in the child repository.
- Only child repositories (inside the workspace root) are committed. The root repository is the user's review gate; `--stage-only` is the most it gets.
- The trailer `Co-Authored-By: Claude <noreply@anthropic.com>` is always added.
- A failed commit exits 1 and leaves the files staged. Nothing is reset, retried or forced. There is no push.

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
    ├── gitops.py          commit
    ├── pointers.py        pointers add / init / rename / check / list
    ├── mocs.py            moc add-link
    ├── postroute.py       post-route
    ├── sessionlog.py      log add / open / check
    ├── people.py          people list / resolve / alias
    ├── timeline.py        timeline add / who / list / rename / check / strip
    ├── obsidian.py        obsidian bootstrap
    └── install.py         install and the manifest
```

## Changing it

- Keep it to the standard library and to Python 3.9 syntax (`tests/tools/test_install.py` checks both).
- Every behaviour that writes has a test in `tests/tools/` that runs the vendored copy. Add one with any change.
- Bump `__version__` in `pka_tools/__init__.py` together with `.claude-plugin/plugin.json`; a test fails when they differ.
