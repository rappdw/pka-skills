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
| `status` | Workspace root, vault, Obsidian and hybrid-monorepo predicates, storage mode and schema version, index roots, meeting and people folders | nothing |
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
| `pointers add FILE [--topic S] [--entities A,B] [--context T] [--moc M] [--dry-run]` | Record a routed file in its domain MOC's Pointers table | `_MOC.md` files |
| `pointers rename OLD NEW [--prefix] [--dry-run]` | Rewrite MOC links after a file or folder moved | `_MOC.md` files |
| `pointers check [--strict]` | Broken pointer links, unreadable tables, rows over the soft cap | nothing |
| `pointers list [MOC]` | Pointer rows as data | nothing |
| `obsidian bootstrap [--dry-run] [--commit]` | The one-time mechanical retrofit of `knowledge/` | MOC and index stubs, frontmatter |

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
3. **When unsure, skip and report.** Frontmatter outside the supported subset, a table with an unexpected header, a file that is not UTF-8 or is read-only: the file is left alone and named in the output.
4. **Idempotent.** Running a command twice changes nothing the second time.
5. **Atomic writes.** A file is written to a temporary name and renamed into place, so an interrupted run cannot leave half a note. The file keeps its permissions; extended attributes (Finder tags, for example) on an edited file are not carried over.
6. **Fenced code blocks are examples.** A `## Pointers` heading, a table or a `- [ ]` inside one is ignored.
7. **Bodies are not interpreted.** Pointer maintenance and the Obsidian retrofit use filenames, folders and frontmatter. (`index` reads bodies to index them; `actions` reads them for checkboxes.)

## Git rules

- `commit` stages and commits by path: `git add -- <paths>`, `git commit -- <paths>`. Never `-A`. The user's other modified, staged and untracked files are left as they were.
- Only child repositories (inside the workspace root) are committed. The root repository is the user's review gate; `--stage-only` is the most it gets.
- The trailer `Co-Authored-By: Claude <noreply@anthropic.com>` is always added.
- A failed commit exits 1 and leaves the files staged. Nothing is reset, retried or forced. There is no push.

## Database rules

- The schema version is `PRAGMA user_version` (currently 1). `index` and `search` refuse to run against an older schema and say how to migrate.
- `db migrate` without `--apply` is a dry run. `--apply` takes a verified backup first and runs in one transaction.
- Only `file_index`, `search_fts`, `project_lifecycle` and `pka_meta` are created or altered. Other tables are left alone.
- Text that a role stored in `search_fts` for a PDF or Office file is kept across re-indexing until the file changes or is removed.

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
    ├── pointers.py        pointers add / rename / check / list
    ├── obsidian.py        obsidian bootstrap
    └── install.py         install and the manifest
```

## Changing it

- Keep it to the standard library and to Python 3.9 syntax (`tests/tools/test_install.py` checks both).
- Every behaviour that writes has a test in `tests/tools/` that runs the vendored copy. Add one with any change.
- Bump `__version__` in `pka_tools/__init__.py` together with `.claude-plugin/plugin.json`; a test fails when they differ.
