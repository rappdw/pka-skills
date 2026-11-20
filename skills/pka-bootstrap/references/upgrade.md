# Upgrade Existing Bootstrap — Algorithm

Procedure for the `upgrade` bootstrap target. Invoked when a user with an already-bootstrapped workspace (typically pre-v1.6) requests the addendum behavior. Examples: "upgrade my pka", "bootstrap upgrade", "update my role files".

## When to use this vs other targets

| Workspace state                                                   | Right target          |
|-------------------------------------------------------------------|-----------------------|
| No `.pka/`, no `CLAUDE.md`                                        | base bootstrap        |
| `.pka/` exists, role files present, but `_obsidian.md` is missing | `upgrade`             |
| `.pka/` exists with v1.6 role files already (re-running)          | `upgrade` (idempotent — no changes) |
| `.pka/` not present                                               | NOT this target — refuse |

`upgrade` is also safe to combine with the `obsidian` target: a user who runs `bootstrap all` on an already-bootstrapped v1.5 workspace gets upgrade + obsidian retrofit.

## What it does

1. **Backup `.pka/roles/`** to `.pka/upgrade-backups/<timestamp>/roles/` (a second run in the same second gets `<timestamp>-2`). The backup directory carries its own `.gitignore`, so backups never show up as changes in a repository that holds the workspace.
2. **Seed the shared reference** if absent:
   - `.pka/roles/_obsidian.md` ← `references/obsidian-conventions.md`
   Skipped silently if the user already has it (e.g., from a partial earlier run). `.pka/roles/_git-protocol.md` is no longer seeded (see "Obsolete sections and files").
3. **Structured-merge new H2 sections** into existing role files (orchestrator, librarian, researcher).
   - Inserts BEFORE the first `## Output Conventions` or `## Invocation` heading found.
   - Only adds sections whose H2 heading text is not already present.
   - Headings inside fenced code blocks (``` or ~~~) are examples, not structure: they are neither counted as "already present" nor used as the insertion point.
   - Keeps each file's line endings (a CRLF file stays CRLF).
   - Never modifies the body of existing sections.
4. **Report sections seeded by an earlier version** (see "Refreshing seeded sections" below) **and obsolete ones** (see "Obsolete sections and files"). Nothing is replaced or removed unless `--refresh` is given.
5. **Print a summary** listing:
   - Backup path
   - Shared references seeded vs. already present
   - Per-role: sections added vs. already present
   - A note about manual merges that this script does NOT perform.

## What it does NOT do

- **Never modifies the body of existing H2 sections.** If the user has customized `## Working Style` or `## Output Conventions`, those bytes stay byte-identical. Changes to those sections (e.g., the "never commits, stages or pushes" bullet on orchestrator's Output Conventions) are NOT applied automatically — they're documented in `references/role-definitions.md` for the user to merge manually.
- **Never modifies frontmatter** in role files. Existing `model:`, `tools:`, etc. are preserved. That includes the `model: claude-opus-4-5` line releases up to v1.10.0 seeded: role files are now seeded without a model (see "Pinned models").
- **Never deletes** content without `--refresh`. A plain run is additive. `--refresh` replaces unedited seeded sections and removes unedited obsolete ones, after the backup.
- **Never commits.** The upgrade leaves changes in the working tree for human review.
- **Never touches files outside `.pka/`.** Only the role files and shared references are modified.

## Refreshing seeded sections

Adding missing sections is not enough on its own: a section seeded by an earlier version keeps its wording, including instructions a later version replaced (before v1.7 the librarian's "Pointer-row maintenance" section described a cluster rule the code no longer uses). So the helper also compares every seeded section a workspace has with the current seed:

| The section's text | Reported as | With `--refresh` |
|---|---|---|
| Same as the current seed (ignoring trailing spaces and blank lines) | nothing | nothing |
| Exactly a version an earlier pka-skills release shipped | can be refreshed | replaced with the current text |
| Anything else (the user edited it) | customised — left alone | left alone, unless named with `--refresh-section 'FILE:## Heading'` |

"Seeded sections" are the sections the helper itself adds to role files (the list in `upgrade-roles.py`) and every section of `_obsidian.md`. Other sections of a role file (`## Purpose`, `## Output Conventions`, …) are never compared or touched.

The record of shipped versions is `KNOWN_SECTION_HASHES` in `upgrade-roles.py`: one SHA-256 per version of each section, taken from this repository's history. It is maintained by `scripts/seeds.py` (see below) and only ever grows.

```
python3 .pka/upgrade-roles.py                         # report
python3 .pka/upgrade-roles.py --diff                  # report, with what changed in each section
python3 .pka/upgrade-roles.py --refresh               # replace the unedited ones, remove unedited obsolete ones (backup first)
python3 .pka/upgrade-roles.py --refresh --refresh-section 'librarian.md:## Indexing pointer rows'
```

`--refresh-section` accepts only seeded and obsolete sections; any other heading is an error that lists the ones it can take.

The skill asks before `--refresh`, and passes `--refresh-section` only for a section the user has said yes to.

## Obsolete sections and files

Earlier releases seeded instructions for a nested-repository layout (a root repository coordinating repositories at `knowledge/` and each `projects/<name>/`) and its commit/push protocol. pka-skills no longer sets that layout up, commits or pushes, so these are no longer seeded:

| Where | What |
|---|---|
| `.pka/roles/_git-protocol.md` | the whole file |
| `orchestrator.md` | `## Session-end protocol (extended)`, `## Mid-session push handling` |
| `librarian.md` | ``## Commit/push protocol (gated on `hybrid_monorepo_present`)`` |
| `researcher.md` | ``## Commit/push protocol (gated on `hybrid_monorepo_present`)`` |

In a workspace that has them, the helper reports each under "Obsolete":

| Its text | Reported as | With `--refresh` |
|---|---|---|
| Exactly a version an earlier release shipped | can be removed | removed (the backup taken at the start of the run has it) |
| Anything else (the user edited it) | customised — left alone | left alone; a section can be named with `--refresh-section 'FILE:## Heading'`, a customised `_git-protocol.md` is the user's to delete |

Until they are removed, the role files still tell the roles to commit and push. The commands they name are accepted and do nothing (`pka-tools commit`, `post-route --role … -m …`), so nothing fails, but the instructions are wrong: recommend the refresh.

The researcher's commit section also carried the instruction to run `post-route` on a saved brief. That now lives in a new seeded section, `## Filing a brief`, which a plain run adds.

The sections that remain but mentioned the layout (the orchestrator's "Session-start checks" and "Bootstrap dispatch", the librarian's "Obsidian coexistence" and "Rename / graduate propagation", the Pointer Layer invariants in `_obsidian.md`) are ordinary refreshable sections with new text.

Not touched by any run: a workspace's `.meta`, its nested repositories, its root `.gitignore`, and the lines about pushing in the orchestrator's unseeded sections (see "Manual follow-up").

## Pinned models

Role seeds used to carry `model: claude-opus-4-5` in their frontmatter. They no longer pin a model: a role without a `model:` line runs on the session's model. The helper does not apply that change to an existing workspace, because it never edits frontmatter and cannot tell a line the user chose from one a seed wrote. Instead its summary lists every role file in `.pka/roles/` that has a `model:` line, with the value, under "Pinned models", and says the line can be removed by hand.

Relay that list. Offer to remove the lines; remove one only on the user's yes for that file, and when you do, change that role's Model cell in `.pka/roles/roster.md` to `session`. A user who pinned a model on purpose keeps it. Nothing is listed when no role file has the line.

## Implementation

The merge is implemented in `bootstrap-assets/scripts/upgrade-roles.py`, vendored at `.pka/upgrade-roles.py` by the installer (see "Vendoring" below). The script is deterministic — every line of new content is hardcoded into the helper, so the same input file always produces the same output. No LLM-driven merging.

Invocation:
```
python3 .pka/upgrade-roles.py [--workspace <root>] [--dry-run]
```

`--dry-run` reports what would change without touching files. Useful for previewing.

## Idempotency

The script checks for the presence of each new H2 by exact heading-text match. Re-running on a workspace where the upgrade has already been applied:
- Reports each new section as "already present"
- Does not re-write any role file
- Does not create another backup (the `--dry-run` use case is the no-effect variant)

In practice, the second run is detectable because all the `role_sections_added` lists are empty.

Note: a fresh backup IS created on every non-dry-run invocation, even if no role files end up being modified. This is by design — the operation is auditable; the cost is a few KB.

## Failure modes

- **`.pka/roles/` doesn't exist**: refuse with a message pointing to base bootstrap. Exit 1.
- **A role file is missing** (e.g., user deleted `librarian.md`): report it as "skipped — file not found" in the summary; continue with the others. Do not attempt to re-create from a seed (that's a different operation).
- **Existing role file has no anchor section** (`## Output Conventions` or `## Invocation`): the new sections are appended at the end of the file, and the summary prints a `WARNING` naming each such file. Relay that warning to the user so they can check the placement.
- **Filesystem errors** (permission, disk full): surface the error verbatim, abort, leave the backup intact. Each role file is written to a temporary name and renamed into place, so a half-written role file cannot be left behind.

## Vendoring

Every vendored helper is installed and refreshed by one command, run from the plugin's copy:

```
python3 "<plugin root>/bootstrap-assets/tools/pka-tools" install --workspace .
```

It runs as the first step of `bootstrap upgrade` (and of base bootstrap). It maintains `.pka/manifest.json`, which records the plugin version and a SHA-256 for each vendored file as last offered. Comparing the plugin's copy, the file on disk and the manifest tells an untouched file from an edited one:

| File on disk | What happens |
|---|---|
| Absent | Installed |
| Identical to the plugin's copy | Nothing |
| Unchanged since it was installed | Replaced with the plugin's copy |
| Edited by the user; plugin's copy unchanged | Kept |
| Edited by the user; plugin's copy changed too | Kept; the plugin's copy is written beside it as `<name>.new` and reported as a conflict |
| No manifest entry (workspace from before v1.7), a file the plugin still ships | Replaced; the previous copy is saved under `.pka/upgrade-backups/<timestamp>/vendored/` |
| No longer shipped by the plugin, recorded in the manifest | Moved to the same backup folder if untouched; left in place if edited |
| A helper of the removed nested-repository layout with no manifest entry (`graduate.sh`, `init_project_repos.sh`, `reinit-project-with-lfs.sh`, `push-all.sh`, `build-repo-list.sh`, `gitattributes-template`, `gitignore-template`) | Left in place and listed: nothing says whether the user edited it |

Nothing is deleted. Relay the kept, conflict and backup lines to the user.

**Why first:** the section list is hardcoded in `upgrade-roles.py`, so an old copy reports "already present" for everything it knows and never adds what later versions introduced. 

## Index migration

`bootstrap upgrade` also brings an existing index up to the current schema, with the user's consent:

1. `.pka/bin/pka-tools status` — if it reports the index "needs `db migrate`":
2. `.pka/bin/pka-tools db migrate` — prints the numbered plan and changes nothing. Show it.
3. **Ask.** A migration is a schema change; ask regardless of autonomy level.
4. `.pka/bin/pka-tools db migrate --apply` — copies the database to `.pka/db-backups/` first, migrates in one transaction, verifies, and rolls back on any failure.
5. `.pka/bin/pka-tools index` — fills in content hashes and picks up anything new.

To undo: replace `.pka/knowledge.db` with the backup file named in the output. Details in `references/sqlite-modes.md`.

`upgrade-roles.py` carries copies of the seeds because it runs inside a workspace, where the plugin's reference files may not be readable. The copies are generated, never edited by hand: edit the seed in `references/role-definitions.md` or `references/obsidian-conventions.md`, then run `python3 scripts/seeds.py --write` from the plugin repository. `scripts/seeds.py --check` (run by the test suite) fails when a copy differs from its reference or a current section is missing from `KNOWN_SECTION_HASHES`.

## Manual follow-up the user may want

After running `upgrade`, the user may want to:

1. **Bring the unseeded sections up to date by hand.** The upgrade never touches `## Key Competencies`, `## Output Conventions` or `## Invocation`. Compare them against `references/role-definitions.md`. In a workspace bootstrapped on v1.6 or v1.7.0 the orchestrator's copies still mention the removed push protocol: "Session-end consolidated push for hybrid-monorepo workspaces" (Key Competencies), "Bootstrap dispatch (obsidian / git / all)…" (Key Competencies), "Never auto-commits root repo…" (Output Conventions) and "push coordination" (Invocation). A customised section that was kept may also still point at `.pka/roles/_git-protocol.md`, which a refresh removes. Offer to show the user those lines; they delete or reword them.
2. **Remove a pinned model** from role frontmatter. A `model:` line makes that role ask for one specific model whatever the session runs on; without the line the role uses the session's model. The upgrade lists the lines and leaves them (see "Pinned models"); the user deletes them, or keeps one they set on purpose.
3. **Re-run `bootstrap obsidian`** if they want the mechanical retrofit on an existing vault.

The summary output should suggest these as next steps when relevant (e.g., when `_obsidian.md` was just seeded and the workspace has `knowledge/.obsidian/`).
