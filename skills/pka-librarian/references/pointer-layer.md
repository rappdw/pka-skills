# Pointer-Layer Maintenance — Per-Route Procedure

Applies to **every** routing operation that lands a file inside the vault (`knowledge/`). **Not** gated on `obsidian_present` — pointer-row maintenance runs in plain-markdown workspaces too. The retrieval value comes from FTS, not from rendering.

Conventions (file location, row schema, retrieval behavior, invariants) live in `.pka/roles/_obsidian.md` (the "Pointer Layer" section). This document is the **procedure**.

From v1.7 the edit itself is made by `pka-tools`. The librarian decides *which cluster a file belongs to* when that takes judgment; the tool does the matching it can do mechanically and makes every change to the `_MOC.md` files. Do not edit a Pointers table by hand, and do not re-implement the steps below.

## The command

After the file is at its destination (and its frontmatter is in place):

```
.pka/bin/pka-tools pointers add <path-to-routed-file> [--topic <slug>] [--entities <a,b>] [--context "<routing directive>"]
```

It prints, per MOC, what it did: `created-moc`, `created-section`, `created-table`, `appended` (a new row), `extended` (an existing row), `noop` (already recorded) or `skipped` with the reason. `--json` gives the same as data, including `changed` — the `_MOC.md` paths to add to this route's commit and to re-index. `--dry-run` shows the outcome without writing.

## What the librarian decides

- **`--topic`** — pass it when you can see which cluster the file belongs to and the file's own `topic` frontmatter would not say so: an existing row's slug (list them with `.pka/bin/pka-tools pointers list <moc>`), or a new slug for an event-bound cluster. Slugs are lowercase and hyphenated; add the year when the cluster is one event (`northwind-partnership-2026`), not when it is ongoing (`ai-adoption-research`). An explicit topic is taken as a decision: the tool uses that row, or creates it, and skips its own matching.
- **`--entities`** — organisations, products or people that the frontmatter does not already carry. Frontmatter `attendees`, `person` and `related` are picked up automatically.
- **`--context`** — the user's routing directive, when there was one ("file this with the Northwind partnership material"). Its words join the file's tokens for matching.

When none of these applies, run the command with just the path.

## What the tool does

Inputs are the file's path and its frontmatter (`topic`, `type`, `tags`, `attendees` / `person` / `related`). **The body is never read.**

### 1. Tokens

Lowercased words of three or more characters, stop-words removed, from: the `topic`, the `type`, every tag, every entity, the filename stem without its date prefix, the folders between the vault root and the file, and the `--context` text.

### 2. Choosing the row

In the destination MOC's Pointers table:

1. **Same topic.** A row whose Topic equals the file's topic slug (`--topic` if given, else frontmatter `topic`) is the file's cluster.
2. **Tokens.** Otherwise a row matches when its Topic has **at least two distinctive tokens and every one of them is among the file's tokens**. Numbers (years) are not distinctive. Of several matching rows the one with the most distinctive tokens wins; a tie goes to the earlier row. This step is skipped when `--topic` was given.
3. **New row.** Otherwise a slug is coined — the frontmatter `topic`; else `<first tag that is not the type>-<type>`; else the filename stem without its date — and a new row is added. If a row already carries the coined slug, that row is used instead, so running the command twice never produces two rows.

Rule 2 is deliberately strict. A row named `lighthouse-research` does not absorb every file with "research" in its name; a one-word slug never matches by tokens at all. When in doubt the tool makes a new row, and the user or the librarian (with `--topic`) can direct the next file.

### 3. The edit

Only the lines the tool owns change. Everything else in the MOC is left byte for byte, including line endings.

- **Extending a row**: the file's wikilink is added at the end of the Files cell and new entities at the end of the Entities cell. Nothing is re-sorted or re-spaced; other cells, extra columns and the cell padding stay as the user left them. A placeholder (`—`, `-`, `none`) in the Entities cell is replaced.
- **New row**: one line inserted directly after the table's last row.
- **No table yet**: the header, separator and first row are added inside the existing `## Pointers` section, after any text already there.
- **No section**: a `## Pointers` section is appended at the end of the file.
- **No MOC**: a minimal `_MOC.md` (a title and the Pointers section) is created.
- A `## Pointers` heading or table inside a fenced code block is an example and is ignored.

Running the same command again changes nothing.

### 4. Cross-MOC duplication

The primary MOC is the destination's top-level domain (`knowledge/<domain>/_MOC.md`). For every tag on the file that names another top-level folder of the vault (compared without case or punctuation: tag `ai` ↔ folder `AI/`), the same file is recorded in that folder's MOC too. The same cluster appearing in two MOCs is intentional — it doubles the FTS hit rate. Add another MOC explicitly with `--moc <path>`.

### 5. Wikilink format

Files-column links are vault-relative without `.md`: `[[northwind/2026-04-23-joint-partnership-meeting]]`. Non-markdown files keep their extension: `[[reference/report.pdf]]`.

### 6. Soft cap

A row that reaches 8 files is listed under "Rows at or over the 8-file soft cap". Put that in the routing report for the user to split if they wish. Rows are never split automatically.

## After the command

1. Re-index the changed MOCs together with the routed file: `.pka/bin/pka-tools index <routed-file> <changed MOC>...`
2. Include the changed MOCs in the route's commit (see `commit-protocol.md`).

## Failure handling

Pointer maintenance never blocks routing. Per `.pka/roles/_obsidian.md`'s error-handling rules, a problem is reported and the route completes.

- **Unreadable table** (the first table row under `## Pointers` is not a `Topic | Entities | Files` header, or no `|---|` row follows it): that MOC is `skipped` with the reason and left untouched. Report it; do not repair it.
- **A row with too few cells**: that row is left alone; other rows work normally.
- **MOC not writable or not UTF-8**: `skipped` with the reason.
- **No frontmatter and no directive**: the slug comes from the filename. The cluster may be coarse; the user can redirect later files with a topic.

## Rename / move propagation

When a file that may be listed in a MOC is renamed or moved:

```
.pka/bin/pka-tools pointers rename <old path> <new path>
.pka/bin/pka-tools pointers rename <old folder> <new folder> --prefix     # a whole folder moved
```

Every wikilink to the old path in every `_MOC.md` (pointer rows and `## Files` bullets) gets the new target. An alias (`[[old|Name]]`) or heading (`[[old#Decisions]]`) is kept. Fenced examples are not touched. Running it twice changes nothing. Rows are never deleted, even when a file leaves the domain.

Links in ordinary notes are not rewritten by this command.

## Graduation propagation

When `graduate.sh` moves a project from `projects/<name>/` to `knowledge/<subdir>/<name>/`, every pointer-row wikilink under `[[projects/<name>/...]]` is rewritten to `[[<subdir>/<name>/...]]` by `graduate.sh` itself, in the same commit as the move.

## Checking

```
.pka/bin/pka-tools pointers check
```

Lists pointer links whose file no longer exists, tables it cannot read, and rows over the soft cap. The lint health check (rule 2) uses this for Pointers tables. It reports; it never removes a row or a link.

## What is never done

- **Rows are not split, merged, reordered or deleted.** Two similar rows stay separate until the user merges them.
- **Hand edits are kept.** Topic slugs, entity order, extra columns and surrounding text survive every route.
- **A row whose files are all gone stays**, with its broken links visible to `pointers check`, until the user removes it.
