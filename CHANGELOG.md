# Changelog

## v1.7.1 — unreleased

Backfill: put the notes a workspace already has on people's timelines. Phase 5 of the v1.7 plan.

**Existing workspaces:** run `bootstrap upgrade` to get the new `pka-tools`; it offers to refresh the "Person timeline" section of `.pka/roles/_obsidian.md` if you never edited it. Then ask the librarian to "backfill timelines".

### Added — `timeline plan`, `apply`, `restore`

- **`timeline plan`** walks the vault and works out, for every dated note, whose timeline it belongs on, with the same evidence rules as a newly filed note. A link in the old back-link sections of a person's own page (`## Mentioned in`, `## Related meetings`, `## Inbound References`, `## References`) also counts. It writes a review report, `owner-inbox/timeline-backfill-plan-<date>.md`, and the exact lines, `.pka/backfill/plan-<id>.json`, and changes nothing else. The report has entries per person with first and last dates, a sample of 20 entries with their evidence, ambiguous names with candidates, names with no person folder that appear in 3 or more notes, undated notes, skipped large meetings, people whose page cannot be written, and the `index.md` stubs it would create. `--since`, `--person`, `--include-large`, `--no-write`.
- **`timeline apply <plan>`** refuses if a person page changed since the plan (or a planned stub appeared), or if the workspace gained or lost Obsidian. It backs every page up to `.pka/backups/<id>/` and adds only lines whose note is not already on the timeline, so hand-edited lines stay as they are. Then it verifies: every planned line is present, every link resolves, and a hash of every file in the workspace shows nothing outside those pages changed. A failed check puts the pages back. In a hybrid monorepo it makes one commit with exactly those pages.
- **`timeline restore <id>`** puts the pages back and removes stubs the apply created. It refuses a page edited after the backfill unless `--force`.
- An independent review of the first build found 1 high and 10 medium or low issues (9 reproduced, 2 found by reading the code). All are fixed, with regression tests (`ReviewFindings` in `test_backfill.py`, each failing on the first build). The high one: an interrupted apply (Ctrl-C, a crash) left pages half-written, and a later `restore` then overwrote the user's edits without `--force`. Now any interruption puts every page back, each page's new hash is recorded before it is written, and restore refuses a page whose state it cannot vouch for. The others: one note with an upper-case `.MD` (or `<`/`>` without Obsidian) failed every apply; plan and backup ids collided within one second; Obsidian writing `.obsidian/workspace.json` failed the check (it now covers the vault outside dot-folders, not the whole workspace); a note edited after planning (say, `no-backref: true` added) did not make the plan stale; a failed put-back stopped half way; a hand-edited plan or backup record could copy or delete files outside person pages; a malformed plan crashed with a traceback; a refused commit exited 0, and the user's own uncommitted edits to a page went into the backfill commit; a `wiki.md` near the vault root hid every note under it.
- The librarian has a "Backfill person timelines" procedure: plan, help the user settle names (aliases only when they confirm), apply only on approval, report the undo command. Three new librarian eval scenarios.

### Changed — what a timeline can link to, without Obsidian

- **Without Obsidian, a timeline reaches the whole workspace.** v1.7.0 linked only to notes inside `knowledge/`, a rule that exists because an Obsidian wikilink cannot leave the vault. Plain relative links have no such limit, and in a workspace where most notes live in `projects/` or a root `meeting-notes/` the old rule left timelines nearly empty. Now `post-route`, `timeline add` and the backfill reach any note in the workspace except `owner-inbox/`, `team-inbox/` (not filed yet) and hidden folders. **Obsidian vaults are unchanged.** Existing timelines need no migration: their links are relative paths and read the same.
- Keys (what `timeline list` shows) are workspace-relative without Obsidian: `knowledge/leadership/2026-11-14-sync` rather than `leadership/2026-11-14-sync`. A wikilink typed by hand is still read relative to the vault.
- `timeline rename` and `pointers rename` take workspace paths; a vault-relative path still works.
- When a filed note and the person pages it touches are in different repositories (a project with its own repo), `post-route` makes one commit in each.
- `graduate.sh` prints the `timeline rename … --prefix` to run when person pages link into the graduated project.
- No notes are moved to make them reachable: person pages link to notes where they are.
- `status` reports `timeline_reach`: the vault with Obsidian, `.` (the workspace) without.

### Changed

- `timeline.add_to` and the backfill share one insertion routine (`timeline.place`) and one set of checks on a person page (`timeline.prepare_index`).
- The `_obsidian.md` "Person timeline" seed gains a Backfill bullet.

### Tests

- `tests/tools/test_backfill.py`: planning changes nothing but its two files; apply touches only person pages and is repeatable; hand-edited lines survive; stale plans are refused; restore (and its refusal after an edit); back-link sections as evidence; ambiguous, undated, large, opted-out and unmatched notes are reported, not added; MOCs, person pages and wikis are not candidates; `--since` / `--person`; an unwritable page is left out; Obsidian and plain-markdown links; one commit in a hybrid monorepo; a failed verification rolls back.
- `tests/tools/test_timeline_scope.py`: without Obsidian, project and root meeting notes go on timelines with relative links; the inboxes and hidden folders are refused; hand-written wikilinks still match; rename follows a graduated project and accepts vault-relative paths; the backfill reaches project notes but not the inboxes or `node_modules/`; `post-route` commits the note and the person page in their own repositories. With Obsidian, notes outside the vault are still refused. 15 of its 18 tests fail on the code before the change (the other 3 pin the unchanged Obsidian behaviour).
- `tests/test_git_bootstrap.sh` S22/S23: `graduate.sh` names the timeline follow-up only when a person page links into the project.

## v1.7.0 — 2026-11-17

The mechanics move into a tool, every skill files notes the same way, and people get timelines. This release includes the two pre-releases below (v1.7.0-alpha.1 and v1.7.0-beta.1), which were not released separately; read all three entries.

- **`pka-tools`** (alpha.1): one Python command, vendored to `.pka/bin/pka-tools`, does the indexing, search, pointer rows, Obsidian retrofit and commits that the skills used to describe in prose.
- **One filing pipeline** (beta.1): every skill that files a note runs `pka-tools post-route`; one session-log grammar; role seeds have a single source and can be refreshed where you never edited them.
- **People and timelines** (this entry): a people registry that links a name only when it is certain, and a `## Timeline` in each person's `index.md`, written as notes are filed.

**Requires Python 3.9 or newer** (`python3` on PATH). Standard library only; no network calls.

**Existing workspaces:** run `bootstrap upgrade` once. It installs `.pka/bin/pka-tools`, refreshes the helper scripts, offers to migrate the index (nothing is migrated without a yes, and the database is backed up first), adds the new role-file sections, and reports seeded sections you can refresh. Sections you edited are left alone unless you name them. Timelines fill in as notes are filed; the history comes with the Phase 5 backfill.

**People and their timelines** — Phase 4 of the v1.7 plan. The sections below, up to v1.7.0-beta.1, are this part.

### Added — the people registry

- `pka-tools people list | resolve | alias`. A person is a subfolder of the folder tagged `people-home` (fallback `knowledge/personnel/`). `index.md` may carry `name` and the new `aliases` field.
- `people resolve` says **high** only for an exact slug, name or alias (case, accents, punctuation, `@` and titles ignored), the slug's words in either order, a link to the person's folder, or a first name only one person has. A last name alone, or a name two people share, is **ambiguous**: the skills ask, never pick. Nicknames are never guessed; when the user settles one, `people alias` records it, and it refuses an alias that already means someone else.
- This replaces the three different name-matching specs in `attendee-linking.md`, `obsidian-routing.md` and the librarian role (finding C7).

### Added — person timelines

A managed `## Timeline` block in each person's `index.md`, newest first:

```
- 2026-11-14 · meeting · [[leadership/2026-11-14-slt-sync|SLT sync]] — deferred the vendor decision; Priya owns the adapter spike
```

- **Written by `post-route`** (its reserved step 4), so the line rides in the note's commit. Works with or without Obsidian (relative markdown links without it).
- **Who:** the person whose folder holds the note; people the note's `person` / `attendees` frontmatter or `## Attendees` links name with high confidence; a person whose slug is in the filename. Body mentions do not count. Ambiguous names are reported, not added. Meetings with more than 8 resolved attendees add none of them (`--include-large`). `no-backref: true` opts a note out (the flag `cross-reference-maintenance.md` had already promised).
- **Summaries** come from the role: at most 140 characters, from the note only; decisions and what that person owns, topics only for a 1-1. `--summary` / `--summary-for <slug>=…`.
- **Safe to re-run:** a note already linked in the block is never added again, and an existing line is never rewritten, so hand-edited summaries survive. `pointers rename` (and `timeline rename`) follow a moved note in every timeline. `timeline check` reports problems; `timeline strip` removes the blocks.
- The `## Mentioned in` back-links are no longer written. Existing ones stay, for the Phase 5 backfill to read.

Decided with Dan on 2026-11-17: newest first, the 8-attendee cutoff, topics-only 1-1 summaries.

### Changed

- `pka-meetings` resolves attendees with `people resolve`, offers to save a settled nickname as an alias, and passes per-person timeline summaries to `post-route`.
- The librarian's per-route "person backlinks" step is now the timeline; the librarian role seed, `_obsidian.md` seed (person schema gains `aliases`, new "Person timeline" section) and `obsidian-routing.md` say so. `bootstrap obsidian` person stubs include `aliases: []`.
- `frontmatter.merge_list_item` generalises the tag merge to any list key.
- Evals: five `pka-meetings` scenarios for a nickname, an ambiguous name, a large meeting, an attendee with no person folder, and a workspace without Obsidian.

### Tests

- `tests/tools/test_timeline.py`, including the Phase 4 acceptance tests: filing a note twice changes nothing; a hand-edited summary (and text the user typed inside the block) survives ten further routes; a rename updates every timeline that cites the note. 273 tests in `tests/tools/`.
- An independent review of the first build reproduced 1 high and 10 medium issues, all fixed with regression tests (`ReviewFindings` in `test_timeline.py`, each failing on the first build). The high one: `pointers rename --prefix --notes` into a subfolder of the old folder rewrote timeline links twice (`archive/archive/…`). The others: a link inside a summary made its note count as present; a symlinked person folder was written through; a `## Timeline` heading inside an HTML comment was used; a one-word slug won over someone else's identical first name; without Obsidian a `#` in a filename added a duplicate line on every run; a short `[[name]]` the user wrote was not recognised; `strip` deleted a heading the user wrote; a timeline line left by an earlier `--person` run was not committed; `timeline list` crashed on a non-UTF-8 index; `people alias` accepted a name that could mean someone else. Also: summary truncation split characters, decomposed Unicode slugs did not resolve, and a `people-home` tag on the vault root made every folder a person.

## v1.7.0-beta.1 — not released separately (part of v1.7.0)

One filing pipeline for every skill, one session-log grammar, single-source seeds. Phase 3 of the v1.7 plan.

**Existing workspaces:** run `bootstrap upgrade`. It installs the new `pka-tools`, then reports role-file sections seeded by an earlier version and offers to refresh the ones you never edited. Edited sections are left alone unless you name them.

### Added — `pka-tools post-route`

The one command a skill runs after it has put a note in place: frontmatter and a `- [[note]]` bullet in its folder's MOC (Obsidian vaults), a pointer row, the index, and one path-scoped commit in the child repo (hybrid monorepo). A step that cannot do its work says why and the rest still run; only a refused commit exits 1. `--also` adds other paths to the same commit (a moved note's old location, a person page that gained a back-link). Earshot capture directories are refused.

Before this, frontmatter, MOC entries, pointer rows and commits happened only when the librarian routed a file. Meeting notes filed by `pka-meetings` and pages written by `pka-wiki` got none of them and stayed uncommitted (finding C1). `pka-meetings`, `pka-wiki`, the librarian and the researcher role now all run `post-route`. A meeting note and a routed document end up the same.

### Added — other commands

| Command | Does |
|---|---|
| `moc add-link FILE [--section H]` | A `- [[note]]` bullet at the end of `## Files` (or a named section, or `## Unsorted`) in the nearest `_MOC.md`. A note already linked in the MOC's prose gets no second bullet. |
| `pointers init [FOLDER…]` | Opt in to the pointer layer without Obsidian: a `_MOC.md` with an empty Pointers table per folder. Existing MOCs are not touched. |
| `pointers rename … --notes` | Also rewrite links in every note of the vault, not only in MOCs. |
| `log add / open / check` | Write a well-formed session-log entry; list open threads of recent entries; report malformed entries (never rewrites them). |

### Changed — pointer layer without Obsidian is opt-in

Decided 2026-11-17. Without `knowledge/.obsidian/`, pointer rows are written only into `_MOC.md` files that already exist, and routing never creates a MOC. The README always promised that a workspace without Obsidian behaves as before (finding C9); it now does. Base bootstrap offers `pointers init`; `--create-moc` and `--no-create-moc` override per call. With Obsidian, nothing changes.

### Changed — session log (C8)

One grammar for every role: `## YYYY-MM-DD HH:MM | role | summary | open threads | next action`. `pka-meetings` used to put "Action items: N" in the open-threads field and log action items as `Open: …` in the summary; `pka-wiki` put claim counts there. The greeting reads that field, so it showed counts as open threads. Both skills now write through `log add`, counts go in the summary, and action items go in the open-threads field. The session-start protocol reads open threads with `log open`.

### Changed — seeds have one source (B7)

- The role, `_obsidian.md` and `_git-protocol.md` seeds live in the pka-bootstrap references. The copies inside `upgrade-roles.py` are generated by `scripts/seeds.py --write`; `--check` (run by the tests) fails when they differ. They had drifted both ways: the copies lacked newer pointer wording, and the reference seed had lost the orchestrator's `upgrade` dispatch target (C10), now restored.
- Seeds no longer cite `pka-skills/skills/...` paths, which do not exist in a workspace.
- **`upgrade-roles.py --refresh`** replaces a seeded section whose text is exactly a version an earlier release shipped (so the user never edited it) with the current text. `upgrade-roles.py` records a hash of every shipped version, taken from this repository's history. Anything else is reported as customised and left alone; `--refresh-section 'FILE:## Heading'` replaces one on request; `--diff` shows the difference. Without `--refresh` the helper only reports. Before this, a workspace seeded before v1.7 kept the old pointer-row rule in its librarian role file indefinitely.

### Changed — names and tags (C2, C6)

- 1-1 notes: every existing form is recognised (`-1on1`, `-1-1`, `-1-on-1`, with or without a name after the marker) and never renamed. New 1-1 notes are written as `YYYY-MM-DD-1-1-<person>.md` (decided 2026-11-17).
- Bootstrap infers and writes `people-home` and `daily-home` Repo Map tags alongside `meeting-home`; the routing references use the tags instead of fixed folder names. The old names remain as the fallback.
- Wiki pages link to each other as `[[topics/<slug>/wiki|Title]]`. Bare `[[slug]]` links resolved to nothing in Obsidian, because every page is named `wiki.md`, and lint rule 2 reported them as broken. Lint rule 2 now spells out how a link resolves (aliases, `#heading`, `.md` suffixes, non-markdown targets).

### Tests

- `tests/tools/test_postroute.py` and `tests/tools/test_upgrade_refresh.py`; the round trip over the fixture vault now includes `post-route` and `moc add-link`. 232 tests in `tests/tools/`.
- An independent review of the first Phase 3 build reproduced 1 high and 7 medium issues: `post-route` wrote frontmatter into non-markdown files (CSV, `.canvas`, OCR sidecars); a bad `--section`, `--topic` or `--also` failed only after the note was edited; a second run did not commit what a failed first run had changed; re-running after a move failed; `moc add-link` put the bullet inside an HTML comment, under a trailing `###` subsection or after a setext heading, and added a duplicate when the MOC used Obsidian's short `[[name]]` links; `pointers init <folder>` wrote into capture directories and dot-folders. Also fixed: `rename --notes` edits inside multi-line comments and in files with an unclosed fence; a session log with a byte-order mark; `--at` accepting impossible dates; `--refresh-section` silently ignoring a heading it cannot refresh. Each has a regression test (`ReviewFindings` in `test_postroute.py`), all of which fail on the first build.
- The pointer-layer shell suite runs in an Obsidian vault and adds PR7 for the plain-markdown case.

### Not changed

- `graduate.sh` keeps its own link rewrite: it is covered by the rollback tests, and it already preserves aliases and anchors.
- Person back-links (`## Mentioned in`) are still written by the librarian by hand; the person timeline replaces them in v1.7.0.

## v1.7.0-alpha.1 — not released separately (part of v1.7.0)

Toolkit foundation: the first step of v1.7. No change to what the skills are for; a change to how the mechanical parts get done.

Until now the mechanics (the SQLite schema, indexing, search queries, pointer-table edits, the Obsidian retrofit, commits) were written as prose for a model to re-derive each session, and two of the test suites exercised reference code that never shipped. This release moves those mechanics into one command, `pka-tools`, that the skills call and the tests run.

**Requires Python 3.9 or newer** (`python3` on PATH). Standard library only; no network calls.

**Existing workspaces:** run `bootstrap upgrade`. It installs `.pka/bin/pka-tools`, refreshes the helper scripts, and offers to migrate the index. Nothing is migrated without a yes, and the database is backed up first. Until a workspace is upgraded, its skills will ask for the tool rather than fall back to hand-written SQL or table edits.

### Added — `pka-tools`

Vendored into each workspace at `.pka/bin/pka-tools`. Full reference in `bootstrap-assets/tools/README.md`.

| Command | Replaces |
|---|---|
| `install` | Copying helper scripts by hand "if absent". Writes `.pka/manifest.json` (plugin version and a hash per file), so an untouched file is updated, an edited file is kept, and a file edited on both sides gets the plugin's copy beside it as `<name>.new`. In a pre-v1.7 workspace the old scripts are replaced and saved under `.pka/upgrade-backups/`. |
| `db init`, `db migrate`, `db backup`, `db schema` | Schema DDL written from a description. The schema now has a version (`PRAGMA user_version = 1`), a unique `file_index.path` and a `content_hash` column. `migrate` prints its plan by default; `--apply` backs up, migrates in one transaction, verifies and rolls back on failure. |
| `index` | Hand-written `INSERT`s. Incremental by size and mtime; SHA-256 per file; OCR sidecars indexed under their source file; pointer rows as separate boosted rows; rows for deleted files removed; text a role stored for a PDF kept. |
| `search` | Hand-built `MATCH` strings. Terms are always quoted; pointer rows rank 3× higher and come back with their file lists resolved. |
| `actions` | A `grep` recipe. Open checkboxes in dated notes, by filename or frontmatter date, skipping fenced examples. |
| `commit` | `git add` / `git commit` typed out per route. Stages and commits exactly the named paths in their child repo, adds the trailer, never commits the root, exits 1 when git refuses. |
| `pointers add / rename / check / list` | The per-route pointer algorithm followed from prose. |
| `obsidian bootstrap` | The retrofit carried out file by file by a role. |
| `status` | Detection predicates worked out per session. |

### Changed — pointer rows: the cluster rule, and how rows are edited

- **The rule the spec stated did not pass its own example.** "Jaccard similarity ≥ 0.5 against the candidate tokens" scores 0.33 on the documented scenario and coined a duplicate row. The reference code had quietly switched to a looser measure that merged unrelated clusters (any file tagged with one word of a two-word topic). The rule is now: a row with the file's topic slug; else a row whose topic has at least two distinctive words, all present in the file's frontmatter, filename and folders; else a new row. The librarian passes `--topic` when it can see the cluster. Spec, seeds and code say the same thing.
- **Rows are edited in place.** A new file or entity is added at the end of its cell. Entities are no longer re-sorted, the section is no longer re-rendered, and text the user wrote around or inside the table is untouched. Padded tables, extra columns, `| --- |`-style separators, CRLF files and `[[target\|alias]]` links are handled; a table with an unexpected header is skipped and reported.
- Entities come from frontmatter people fields and `--entities` only. `[[personnel/priya/index]]` becomes `priya` (it used to become `index`).
- `pointers rename` also updates `## Files` bullets in MOCs and keeps aliases and `#heading` anchors.

### Changed — Obsidian retrofit

- Runs as `pka-tools obsidian bootstrap` (`--dry-run` to preview, `--commit` for the single path-scoped commit).
- Frontmatter is edited line by line, never parsed and re-rendered: comments, key order, quoting and block-style lists survive. Bodies are byte-identical, including CRLF endings, a byte-order mark and a missing final newline.
- Meeting, people and daily folders come from Repo Map tags (`meeting-home`, `people-home`, `daily-home`) when present; the previous folder names remain as the fallback.
- Notes that are not UTF-8 or are read-only are skipped and listed, alongside malformed frontmatter.
- The domain tag for `ArchCouncil/` is `archcouncil`, as the conventions document always said (the reference code produced `arch-council`).

### Changed — skills and references

- `pka-bootstrap`: installs the toolkit; `db init` + `index` at bootstrap (markdown content is indexed immediately; there is no separate metadata-only pass); `bootstrap git` and `bootstrap upgrade` vendor through `install`; `bootstrap upgrade` offers the index migration and asks first.
- `pka-librarian`: index, pointer and commit steps call the tool; search goes through `pka-tools search`.
- `pka-meetings`: indexing and the action-item query call the tool.
- `sqlite-modes.md`, `pointer-layer.md`, `obsidian-bootstrap.md`, `commit-protocol.md`, `upgrade.md`, `git-bootstrap.md` rewritten to describe the commands. Per-folder index tables are documented as optional; the tool neither creates nor alters them.
- Root `.gitignore` list gains `.pka/db-backups/`, `.pka/bin/**/__pycache__/` and `.pka/**/*.new`.

### Tests and CI

- `tests/pointer_maintainer.py` and `tests/bootstrap_obsidian.py` are removed. `test_pointer_layer.sh` and `test_obsidian_bootstrap.sh` now run the shipped tool; PR4 runs a real index and a real search instead of an in-memory table.
- New suite `tests/test_tools.sh` (`tests/tools/`, 182 tests) drives the vendored `.pka/bin/pka-tools`. It includes a round trip over a fixture vault (`tests/fixtures/build_vault.py`: CRLF, byte-order mark, no final newline, non-UTF-8, spaces, commas and non-ASCII names) asserting that no line changed that the tools do not own and that a second pass changes nothing.
- Every shell suite installs its workspace through `pka-tools install`.
- CI adds a job that runs the toolkit tests on Python 3.9 (in the official container) and a macOS step that runs them under `/usr/bin/python3`.
- An independent review of the first build found 3 high-severity and 11 medium issues (a commit redirected by `GIT_DIR`, git pathspec patterns in `commit`, invalid YAML after a trailing comma in `tags`, read-only and symlinked MOCs overwritten, capture directories edited by the retrofit, tracebacks on a corrupt database or a non-UTF-8 filename, and others). All are fixed; `tests/tools/test_hardening.py` has one regression test per finding, 29 of which fail on the first build.

### Known gaps (later v1.7 phases)

- Role files and `.pka/roles/_obsidian.md` in an existing workspace keep their earlier wording about pointer rows; `bootstrap upgrade` only adds missing sections. The skills' own references are current.
- Per-route frontmatter, MOC `## Files` bullets and person back-links are still done by the librarian from `obsidian-routing.md`. `pka-meetings` and `pka-wiki` do not yet run the pointer or commit steps.
- `pointers rename` rewrites links in MOCs only, not in ordinary notes.

## v1.6.3 — 2026-11-17

Repair and safety. No new features. Every item below was reproduced against v1.6.2 first, and each script fix has a regression test that fails on the old script and passes on the new one.

**Existing workspaces:** the helper scripts in `.pka/` are copies. Re-run `bootstrap git` or `bootstrap upgrade` to replace them with the fixed versions (both now refresh a helper that differs from the plugin's copy; before this release an existing copy was never updated).

### Fixed — helper scripts could lose data

| ID | What was wrong | Now |
|---|---|---|
| A1 | `graduate.sh` deleted the project's `.git` even when the history backup had not been written. `graduate.sh widget/` (a trailing slash) printed "Saved to", removed the history and exited 0 with an empty backup directory. | The `.git` directory is **moved** to `.pka/graduate-backups/<name>-<timestamp>.git/`, never deleted. Names are validated: a trailing slash is accepted, anything that is not a single folder name is a usage error. |
| A2 | `reinit-project-with-lfs.sh --yes ""` or `--yes .` wiped the workspace root's history and committed the root. | Only `knowledge` or `projects/<name>` is accepted; everything else is a usage error before anything is touched. |
| A3 | `git init -b main` was unchecked. On git older than 2.28 it failed, and the commands after it committed into the enclosing root repo. | git 2.28+ is required (exit 2 otherwise), each `git init` is checked, and the child is verified to be its own repository before any commit. |
| A4 | Commit failures (no identity, signing, hooks) were ignored and reported as success; re-runs then said "already initialized". | Identity is checked up front. A failed step is reported and the script exits 1. `graduate.sh` and the reinit script roll back completely; `init_project_repos.sh` removes the half-made `.git` so a re-run retries. |
| A5 | Reinit destroyed the history without adding LFS when a `.gitattributes` already existed; it also dropped every remote but `origin`, dropped other branches, and took no backup. | LFS filter lines are merged into the existing `.gitattributes`; all remotes (and push URLs) are carried over; the old repository, with every branch, is kept under `.pka/reinit-backups/`. |
| A6 | Appending to a `.gitignore` that had no final newline fused two patterns (`node_modules.DS_Store`), after which `node_modules/` was committed. | A missing final newline is repaired before appending. |
| A7 | The graduation backup was a `git bundle`, which contains no LFS objects — so "full history saved" was false for PDFs, images and Office files. | The backup is the whole repository directory, LFS objects included. Projects with LFS files that were never downloaded are refused with a hint to run `git lfs pull`. |
| A8 | `git add -A` in `knowledge/` swept unrelated uncommitted work into the "Graduate:" commit. | Staged and committed by path: only the graduated project and the `_MOC.md` files the script rewrote. The user's modified, staged and untracked files are left as they were. |
| A9 | Graduating a symlinked project deleted the external repo's `.git` and moved only the link. | Symbolic links are refused by `graduate.sh` and the reinit script, and skipped (and listed) by `init_project_repos.sh`. |
| A10 | A child whose `.git` is a file (linked worktree, submodule) got bootstrap commits added to its existing history. | Left alone and listed in the summary. |
| A11 | `.meta` and the real git remotes disagreed: `push-all.sh` decided what to skip from `.meta` but pushed with the repo's remote, and `build-repo-list.sh` overwrote hand-edited `.meta` URLs. Following the documented "set origin URLs in `.meta`" led to pushes that failed or were skipped forever. | The child repo's own `origin` is the single source of truth. `push-all.sh` uses it and points out a stale `.meta`; `build-repo-list.sh` rebuilds `.meta` from the repos (atomically, preserving other keys, refusing to overwrite invalid JSON). Docs now say `git -C <child> remote add origin <url>`, then `.pka/build-repo-list.sh`. |
| A13 | `upgrade-roles.py` matched headings inside fenced code blocks (and could insert sections into one), converted CRLF files to LF, appended silently when no anchor heading was found, and crashed when run twice in one second. | Fence-aware; line endings preserved; a missing anchor produces a `WARNING` naming the file; backup directories get unique names; role files are written atomically. |

Also: the scripts no longer use a fixed, shared path under `$TMPDIR` for the empty git template (private `mktemp -d`, removed on exit), and the backup directories under `.pka/` ignore themselves so they never show up in the root repo.

**Behaviour change to note:** the graduation backup is now a directory (`<name>-<timestamp>.git/`) rather than a `.bundle` file. Restore with `git clone <that path>`. Backups made by earlier versions are untouched.

### Fixed — the test suite changed your git identity (A12)

`tests/lib.sh` ran `git config --global user.name "PKA Test Runner"`, overwriting the developer's real identity. The suite now runs against a throwaway `HOME` / `GIT_CONFIG_GLOBAL`, and `run-all.sh` fails if the real global configuration changed during a run.

### Fixed — skills and references

- **Stage by path, everywhere.** `commit-protocol.md` prescribed `git add -A` for every routing commit (while warning against it 44 lines later). Routing, Obsidian-bootstrap and root-scaffolding staging now name their paths, so half-written notes in a live vault are never swept into an automatic commit.
- **"Transition `<project>` to knowledge"** was a plain `mv`, which in a hybrid monorepo moved a whole child repo, `.git` included, into the `knowledge/` repo. It now runs `.pka/graduate.sh` whenever child repos are involved (C3).
- **thinkkit detection** looked for `.claude/skills/take-notes/`, which a plugin install never creates, so capture and reconcile were reported unavailable. `pka-meetings` now consults the session's skill list first (C4).
- **Earshot leftovers from v1.6.2**: `meeting-notes/` is in the root ignore list (raw audio was being staged at the root), and the session-start protocol now looks for unreconciled captures (C5). `.pka/reinit-backups/` and `.pka/upgrade-backups/` are ignored too.
- **Search queries are quoted.** The documented `MATCH ?` query failed on exactly the hyphenated slugs pointer rows are made of (`no such column: partnership`) and on a trailing `?`. `sqlite-modes.md` now specifies how to build the query string, and the dashboard search does it (B4).
- **"What action items do I have this week"** searched the full-text index for `- [ ]`, which is a syntax error unquoted and matches nothing quoted. It now scans meeting notes for open checkboxes, by filename date (B5).
- **Helper scripts are refreshed.** `bootstrap git` and `bootstrap upgrade` replace a `.pka/` helper that differs from the plugin's copy instead of leaving a stale one in place.
- Corrected: "four skills" → six in the plugin and marketplace descriptions; the `CLAUDE.md` template stamp (`PKA v1.2` → `v1.6`).

### Tests and CI

- New suite `tests/test_script_safety.sh`: 21 tests, one or more per fix A1–A11. `tests/test_upgrade.sh` gains U8–U11 for A13.
- The suite is portable to macOS (no `md5sum`, no GNU-only `sed -i`).
- GitHub Actions runs the suite on Linux and macOS for every push and pull request, including a pass under macOS's bash 3.2.
- `tests/README.md`: examples must use the fictional fixture cast only.

### Skills

- `pka-bootstrap` v1.6.3, `pka-librarian` v1.6.3, `pka-meetings` v1.6.3, `pka-interface` v1.6.3 (reference and procedure corrections above; no new capabilities)

## v1.6.2 — 2026-07-03

### Added — earshot capture directory awareness (closes #3)

[earshot](https://github.com/rappdw/earshot) records meetings locally into capture directories (`YYYY-MM-DD_HHMMSS[_<title>]/`, marked by a `meeting.json` file) containing audio, diarized `transcript.json`/`transcript.md`, machine `notes.md`, and `narrative.md`. `pka-meetings` and `pka-librarian` now recognize them.

- **Detection**: any directory containing `meeting.json` is an earshot capture — marker-based, not path-based. Added to the `pka-meetings` pre-flight scan alongside the existing `team-inbox/` transcript patterns. A capture with `transcript.md` and no reconciled note is a Mode 2 candidate, same as a detected Zoom transcript. New "Earshot Capture Directories" section in `references/transcript-patterns.md` documents contents, detection logic, and handling rules.
- **Capture directories never move.** Routing files notes (`YYYY-MM-DD-<slug>.md`); capture directories stay where earshot wrote them. The `**Recording**: <capture-dir>` header pointer that thinkkit v0.8.0's take-notes adds is preserved verbatim through routing and rewrites — it stays valid precisely because the notes move and the directory doesn't. The transcript-disposition question (keep/archive/delete) never applies to capture artifacts. The librarian treats captures as off-limits: never routed, moved, renamed, or deleted (new guard in the routing decision tree and key constraints).
- **Pipeline ordering**: reconcile (and narrate, if the user runs earshot's `/meeting-narrative`) **before** routing, while notes are still in `meeting-notes/` — meeting-narrative finds notes by globbing there.
- **Indexing**: when a capture has a `narrative.md`, it is indexed into `search_fts` at its in-place path and referenced from the session-log entry.

Cross-references: thinkkit v0.8.0 (earshot-aware take-notes / resolve-against-transcript, Meeting-Artifacts Contract); rappdw/earshot#1 (meeting-narrative honors the `**Recording**:` pointer).

### Skills

- `pka-meetings` v1.6.2 (earshot pre-flight detection; Mode 2 capture support; routing/indexing/session-log updates; 2 new eval scenarios)
- `pka-librarian` v1.6.2 (capture directories off-limits in transcript awareness and routing decision tree)

## v1.6.1 — 2026-04-26

### Added — Pointer layer for MOC files (closet pattern)

A small set of curated, dense, machine-readable rows inside each `_MOC.md` — one row per concept cluster — that the librarian maintains as files are routed. Sits between FTS queries and file bodies, converting "1,500-file haystack" queries into "30-cluster summary, then 3–5 targeted file reads". No vector store, no embeddings — just markdown table rows that FTS5's BM25 ranks above sparse body matches.

- **New section in `.pka/roles/_obsidian.md`**: "Pointer Layer" — file location, three-column row schema (Topic, Entities, Files), librarian behavior, retrieval behavior, behavior-without-Obsidian, invariants. Layered onto the existing MOC convention; works in plain-markdown workspaces too (the retrieval value comes from FTS, not Obsidian rendering).
- **Librarian per-route step**: after every route into a domain, identify the cluster (slug-coverage similarity ≥ 0.5 against existing topic slugs), update the matching row append-only, OR coin a new slug from frontmatter and append a new row. Cross-MOC duplication when the file's tags imply multiple top-level domains. 8-file soft cap surfaced in the routing summary; the librarian never auto-splits.
- **Indexing tweak**: pointer-table rows tagged `is_pointer = 1` in `search_fts`; retrieval applies `rank * 3.0` to those rows (FTS5 BM25 returns negatives where more negative = better match, so `× 3` makes pointer matches more negative and ranks them above body-level matches).
- **Rename / graduate propagation**: when a file is moved or a project is graduated, every pointer-row wikilink referencing the old path is rewritten across all `_MOC.md` files in the vault. `graduate.sh` does the rewrite as part of the same graduation commit in `knowledge/`.
- **Lint coverage**: existing "broken links" rule (rule 2) now explicitly covers wikilinks inside `_MOC.md` Pointers tables; output annotates the row's topic slug for cleanup targeting.
- **Upgrade path**: `bootstrap upgrade` (introduced in 1.6.0) now also adds the v1.6.1 pointer-layer sections to existing `.pka/roles/_obsidian.md` and `.pka/roles/librarian.md` files. Idempotent and append-only at the section level — never modifies content the user has customized.

### Tests

- Shell suite `tests/test_pointer_layer.sh` covering scenarios PR1–PR6 + cross-MOC duplication: 7 mechanical tests, all passing.
- Python reference impl `tests/pointer_maintainer.py` for deterministic per-route maintenance, rename propagation, and lint scanning.

### Backward compatibility

A workspace bootstrapped on v1.6.0 continues to work identically. The Pointers section is invisible to existing MOC behavior; adding a `## Pointers` section to a v1.6.0 MOC produces a clean diff that the user can commit. No 1.6.0 test scenarios changed.

### Skills

- `pka-bootstrap` v1.6.1 (new sqlite-modes section for pointer indexing; updated obsidian-conventions seed; upgrade-roles helper extended for v1.6.1)
- `pka-librarian` v1.6.1 (pointer-layer routing step; new references `pointer-layer.md`)

Spec: [`docs/specification-addendum.md`](docs/specification-addendum.md) plus the 1.6.1 pointer-layer additions documented inline in `skills/pka-bootstrap/references/obsidian-conventions.md` and `skills/pka-librarian/references/pointer-layer.md`.

## v1.6.0 — 2026-04-26

### Added — Obsidian coexistence (additive; opt-in via bootstrap)

- **Detection**: `obsidian_present := directory_exists("./knowledge/.obsidian")` evaluated once per session. When true, the orchestrator surfaces a one-line greeting and roles enable additive Obsidian-aware behavior. When false, behavior is identical to v1.5.
- **Shared-reference seed**: new `.pka/roles/_obsidian.md` documenting frontmatter schemas (daily, meeting, 1on1, brief, person), wikilink rules, MOC policy, tag conventions, and error handling. Roles link here rather than duplicate.
- **`bootstrap obsidian` target**: one-time mechanical retrofit of an existing vault. Creates `_MOC.md` stubs per top-level domain, person index stubs at `personnel/<name>/index.md`, filename-pattern frontmatter (1on1, meeting, daily). No body reading; idempotent; merges, never overwrites.
- **Librarian per-route enhancements** when `obsidian_present`: frontmatter merge on routed files, MOC append, person backlinks (high-confidence only), wikilink hygiene.
- **Researcher brief frontmatter** (`type: brief`) when briefs land in vault.

### Added — Hybrid monorepo bootstrap (additive; opt-in)

- **`bootstrap git` target**: one-time setup of a `meta`-coordinated hybrid monorepo. Initializes root `.git` (no commit — human-review gate), `knowledge/.git` and each `projects/*/.git` with LFS, generates `.meta` JSON manifest, installs `.pka/` templates and helper scripts.
- **Vendored `bootstrap-assets/`**: `gitattributes-template`, `gitignore-template`, plus scripts `graduate.sh`, `init_project_repos.sh`, `reinit-project-with-lfs.sh`, `push-all.sh`, `build-repo-list.sh`. All are idempotent, network-free, root-no-commit, with typed-confirmation gates on destructive operations.
- **Optional opt-in origin**: `init_project_repos.sh` accepts `ORIGIN_BASE` env var when the user wants to set origin URLs at init time. Default: no origin set.

### Added — Commit/push protocol

- **Shared-reference seed**: new `.pka/roles/_git-protocol.md` documenting commit triggers, message format (`<Role>:` prefix + `Co-Authored-By: Claude` trailer), push triggers, graduation sequence, failure behavior. Activates only when `hybrid_monorepo_present`.
- **Per-role auto-commits** in child repos when `hybrid_monorepo_present`: librarian commits one routing unit per route, researcher commits one brief per save. Each side-effect (MOC update, frontmatter, backlink) rides along in the same commit.
- **Root never auto-commits**. Hard rule across all paths: root-tracked changes are staged for human review and surfaced in the session summary.
- **Session-end consolidated push** via `meta git push` (or fallback `.pka/push-all.sh` iterating `.meta`). Failures surface; session close still proceeds. Empty origins reported as skipped.
- **Mid-session "push now"** uses the same primitive.

### Added — Bootstrap upgrade (`bootstrap upgrade`)

- **`upgrade` target** for users on v1.5 who want the v1.6 additions without losing customizations. Implementation: `bootstrap-assets/scripts/upgrade-roles.py` performs deterministic structured merge (no LLM in the loop) — backs up `.pka/roles/`, seeds missing shared references, appends new H2 sections to existing role files anchored before `## Output Conventions`. Idempotent. Never modifies the body of existing sections; never modifies frontmatter.

### Added — Tests

- **JSON evals** for the 22 spec scenarios (1–11 Obsidian, 12–16 git bootstrap, 17–22 commit/push protocol).
- **Shell test harness** under `tests/`: 4 suites (git-bootstrap, obsidian-bootstrap, commit-protocol, upgrade) totalling 22 mechanical tests. Includes a Python reference implementation of the Obsidian retrofit algorithm for testability.

### Added — Documentation

- `docs/specification-addendum.md` — full spec for the addendum.
- `bootstrap-assets/README.md` — vendored asset contract and provenance.
- New algorithm references in `skills/pka-bootstrap/references/`: `obsidian-conventions.md`, `git-protocol.md`, `obsidian-bootstrap.md`, `git-bootstrap.md`, `upgrade.md`.
- New librarian references: `obsidian-routing.md`, `commit-protocol.md`.

### Backward compatibility

A user with no Obsidian vault (`knowledge/.obsidian/` absent) and no hybrid monorepo (`.meta` + `.git` at root absent) sees output identical to v1.5. Every new behavior is gated on the relevant detection predicate or explicit user invocation. Bootstraps never auto-run on detection.

### Skills

- `pka-bootstrap` v1.6.0 (Obsidian, git, upgrade targets; vendored assets)
- `pka-librarian` v1.6.0 (per-route Obsidian behavior; commit-per-unit)

## v1.5.0 — 2026-04-05

### Added
- **pka-wiki** skill — topic wiki lifecycle (create, ingest, query, list, retire). LLM-maintained synthesis pages that cite authored notes. Inspired by Karpathy's LLM wiki pattern, adapted to PKA's files-are-source-of-truth model. Ingest always requires confirmation regardless of autonomy level.
- **Librarian lint** — 7-rule non-destructive health check (orphan files, broken links, stale wiki sources, empty Repo Map folders, missing back-references, contradiction candidates, uncited wiki claims). Reports to `owner-inbox/librarian-lint-<date>.md`; never auto-fixes.
- **`wiki-home` Repo Map tag** — structural detection of topic wiki folders (subfolders containing `wiki.md`); default location `knowledge/topics/`.
- **@researcher wiki mode** — role now maintains topic wikis with section-level diffs, not one-shot rewrites. Every wiki claim cites a source.
- **Tutorial modules 8 and 9** — Topic Wikis and Health Checks added to onboarding curriculum.

### Changed
- Bootstrap inference guide detects wiki-home folders during scan
- CLAUDE.md template documents `wiki-home` tag alongside `meeting-home`
- Librarian description and capabilities expanded to include lint
- @researcher role definition adds topic wiki maintenance as competency

### Skills
- `pka-wiki` v1.0.0 (new)
- `pka-librarian` v1.5.0 (lint capability added)
- `pka-bootstrap` v1.5.0 (wiki-home inference, researcher wiki-mode)
- `pka-tutorial` v1.1.0 (modules 8 and 9)

## v1.4.0 — 2026-04-05

### Added
- **pka-tutorial** skill — conversational onboarding and capability walkthrough for new users. 7 teaching modules (orientation, finding things, inbox pattern, meeting capture, dashboard, project lifecycle, role system) grounded in the user's actual Repo Map. Complements `docs/TUTORIAL.md` (reference doc) as the interactive counterpart.

### Skills
- `pka-tutorial` v1.0.0 (new)

## v1.3.0 — 2026-04-03

### Added
- **Owner profile** — bootstrap now captures role, domain expertise, communication style, and goals during Q1 interview; generates `.pka/owner-profile.md` referenced by all roles
- **Communication style** in CLAUDE.md template — roles adapt output format and depth to owner preferences
- **Decision log** — `.pka/decision-log.md` captures reasoning behind structural decisions (archive, mode switch, role additions); complements the action-oriented session log
- **Personal context portfolio** concept — documented in README; the owner profile, decision log, session history, and Repo Map form a portable, agent-maintained representation of the owner
- **Future scope: pka-mcp** — README notes MCP server as natural evolution for exposing PKA as a tool surface

### Changed
- Bootstrap Phase 2 Q1 expanded from name-only to lightweight profile interview (max 5 questions total)
- Bootstrap Phase 3 output steps renumbered to include owner profile (3e) and decision log (3h)
- `.pka/` directory structure now includes `owner-profile.md` and `decision-log.md`

### Skills
- `pka-bootstrap` v1.3.0

## v1.2.0 — 2026-04-01

### Added
- **pka-meetings** skill — full meeting documentation pipeline
  - Four modes: capture, reconcile, route-only, full pipeline
  - Orchestrates thinkkit's `take-notes` and `resolve-against-transcript` when available
  - Smart routing into knowledge base using Repo Map meeting-home tags
  - Attendee linking against personnel records
  - Action item extraction and session log integration
  - Graceful degradation when thinkkit is not installed
- Bootstrap inference now detects `meeting-home` folders from date-slug filenames
- Librarian transcript awareness — holds `.vtt`/`.srt` files for pka-meetings instead of auto-routing
- CLAUDE.md template includes transcript handling conventions in inbox section
- Repo Map `meeting-home` tag for meeting note destination folders
- Tutorial documentation at `docs/TUTORIAL.md`

### Changed
- Repo Map table now includes Tags column for meeting-home and future tags
- Session start protocol scans for transcript files in team-inbox
- Librarian pre-flight includes transcript detection before any routing

### Skills
- `pka-bootstrap` v1.2.0
- `pka-librarian` v1.2.0
- `pka-interface` v1.2.0
- `pka-meetings` v1.0.0 (new)
