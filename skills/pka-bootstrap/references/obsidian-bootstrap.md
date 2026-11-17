# Obsidian Mechanical Retrofit — Procedure

Procedure for the `obsidian` bootstrap target. Invoked when the user explicitly requests "bootstrap obsidian", "bootstrap the vault", "MOC stubs", "frontmatter retrofit", or similar. Never auto-runs.

From v1.7 the retrofit is carried out by `pka-tools`, not by a role editing files one at a time. The skill checks the preconditions, runs the command, and relays its summary.

## Inputs

- `WORKSPACE_ROOT/knowledge/` — the Obsidian vault. Must contain `.obsidian/` (any state, including empty).

## Outputs

A vault diff with:
- One `_MOC.md` in the vault root, in each top-level domain folder and in each folder one level below (created only if absent). Person folders get an index instead of a MOC.
- One `<people-home>/<name>/index.md` per person folder (created only if absent).
- A frontmatter block on notes that have none: the schema for the note's kind when its name and folder match a known pattern, and the folder's domain tag in every case.
- Missing schema keys, and the domain tag, added to notes that already have frontmatter. Existing keys are never changed.
- A list of notes that were **skipped** because their frontmatter could not be read safely.

## Hard rules

1. **No body reading.** Inputs are filename, folder structure, and existing frontmatter only. A note's body is carried through byte for byte: same line endings, same byte-order mark, same missing-or-present final newline.
2. **Merge, never overwrite.** Existing frontmatter lines are not rewritten, reordered or re-quoted. New keys are inserted as new lines above the closing `---`. The one line that can change is `tags:`, which gains the domain tag.
3. **Skip what cannot be read safely.** A note whose frontmatter is malformed, or uses YAML the tool does not handle, is listed and left untouched. So are notes that are not UTF-8 or are read-only.
4. **Idempotent.** Re-running produces no further changes.
5. **Existing MOCs and person indexes are never edited** by the retrofit.

## Steps

### Step 0 — Preflight

- Verify `knowledge/.obsidian/` exists. If absent, stop with: *"No Obsidian vault detected at `knowledge/.obsidian/`. The Obsidian bootstrap is a no-op outside an Obsidian vault."* (The command refuses too, with exit code 3.)
- Verify `.pka/roles/_obsidian.md` exists. If absent, seed it from `references/obsidian-conventions.md` first.
- Verify `.pka/bin/pka-tools` exists. If absent, install it (see "Installing the toolkit" in `SKILL.md`).
- Note `hybrid_monorepo_present`.

### Step 1 — Preview (recommended)

```
.pka/bin/pka-tools obsidian bootstrap --dry-run
```

Prints the same summary as a real run and writes nothing. Show the counts to the user; in "ask before everything" mode, wait for a yes.

### Step 2 — Run

```
.pka/bin/pka-tools obsidian bootstrap --commit      # hybrid monorepo: one commit in knowledge/
.pka/bin/pka-tools obsidian bootstrap               # otherwise: the diff is left for the user
```

With `--commit`, the files the run created or changed are staged and committed **by path** in the `knowledge/` child repo with the message `Bootstrap (obsidian): N MOCs, M person indexes, K frontmatter additions` and the standard trailer. Notes the user is in the middle of editing are not swept in. The root repo is untouched. Without a child repo at `knowledge/`, `--commit` reports that nothing was committed and why.

### Step 3 — Summary

Relay the command's summary:

```
Obsidian bootstrap summary
------------------------------
MOC stubs created:        N (M already present)
Person indexes created:   N (M already present)
Files given frontmatter:  N
Frontmatter merged:       K files
Total notes in vault:     T
Total files touched:      P
Files SKIPPED (malformed or unsupported frontmatter, left untouched): J
  - <path>: <reason>
Notes (…):
  - <path>: tags are not a simple list; domain tag not added
Commit: <sha> in knowledge        OR   No commit …
```

Always pass on the skipped list and the notes: those are the files the user may want to fix by hand.

## What the command does

### Which folders play which role

| Role | Folder |
|---|---|
| People home | The Repo Map folder tagged `people-home`; without the tag, `knowledge/personnel/` |
| Meeting homes | Repo Map folders tagged `meeting-home`; without any, `knowledge/leadership/` and `knowledge/ArchCouncil/` if they exist |
| Daily notes | Repo Map folders tagged `daily-home`; without any, `knowledge/lab-notebook/` |

`.pkaignore` applies. Dot-folders, symbolic links and earshot capture directories are skipped.

### MOC stubs

```markdown
# <folder name>

<!-- MOC stub created by pka-bootstrap (obsidian). User can reorganize freely. -->

## Files
- [[<path>|<filename>]]            (each note directly in this folder)

## Subdomains
- [[<subfolder>/_MOC|<subfolder>]] (each immediate subfolder)
```

A section with nothing to list is left out.

### Person index stubs

The folder name becomes the display name: `robin-smith` → `Robin Smith`.

```markdown
---
type: person
name: <Display Name>
role: ""
org: ""
tags: [person]
---

# <Display Name>

## Notes
- [[<each note in this folder, excluding index.md>]]
```

### Frontmatter by pattern

| Note | Keys written when missing |
|---|---|
| `<people-home>/<person>/YYYY-MM-DD-1on1*.md`, `…-1-1*.md`, `…-1-on-1*.md` | `type: 1on1`, `date`, `person: "[[<people-home>/<person>/index]]"`, `tags: [1on1, <domain-tag>]` |
| `<meeting-home>/YYYY-MM-DD-<topic>.md` | `type: meeting`, `date`, `topic: <the rest of the filename>`, `attendees: []`, `tags: [meeting, <domain-tag>]` |
| `<daily-home>/YYYY-MM-DD.md` | `date`, `tags: [daily, <domain-tag>]` |
| Any other note in a top-level folder | `tags: [<domain-tag>]` |

The `topic` comes from the filename only. Values that YAML would misread (a colon, a number, `true`) are quoted.

### Domain tag

The tag for a top-level folder is its name in lower case with spaces and underscores as hyphens: `AI/` → `ai`, `ArchCouncil/` → `archcouncil`, `Dev Process/` → `dev-process`.

For a note that already has `tags`:

- `tags: [a, b]` → the tag is added inside the brackets.
- A block list (`tags:` followed by `- a` lines) → one `- <tag>` line is added after the last item, with the same indentation.
- `tags:` with no value → becomes `tags: [<tag>]`.
- Anything else (a plain string, a list spread over several lines, a `Tags:` or `tag:` key) → left alone and reported under "Notes".

### What counts as unreadable frontmatter

No closing `---`; a line that is not `key: value`, a list item or an indented continuation; a tab used for indentation; the same key twice; an unquoted value containing `: ` (for example `topic: budget: second pass`); an unterminated quote or bracket. The note is skipped whole — no keys, no tags.

## What NOT to do

- Do not edit notes by hand to "finish" what the command skipped. Report them.
- Do not attempt to fix malformed frontmatter.
- Do not invent attendees, topics (beyond the filename) or `related` links.
- Do not modify files outside `knowledge/`. Repo Map updates in `CLAUDE.md` are a separate orchestrator concern.
- Do not rename existing files.

## Idempotency check

Running the command a second time reports zero files touched. `tests/test_obsidian_bootstrap.sh` (S4) and `tests/tools/test_obsidian.py` check this against the shipped tool.
