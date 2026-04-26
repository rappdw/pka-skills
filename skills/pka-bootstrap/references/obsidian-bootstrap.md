# Obsidian Mechanical Retrofit — Algorithm

Procedure for the `obsidian` bootstrap target. Invoked when the user explicitly requests "bootstrap obsidian", "bootstrap the vault", "MOC stubs", "frontmatter retrofit", or similar. Never auto-runs.

## Inputs

- `WORKSPACE_ROOT/knowledge/` — the Obsidian vault. Must contain `.obsidian/` (any state, including empty).

## Outputs

A vault diff with:
- One `_MOC.md` per top-level domain folder (created only if absent).
- One `personnel/<name>/index.md` per personnel subfolder (created only if absent).
- Filename-pattern frontmatter on files matching known patterns (added only if absent or merged into existing frontmatter; never overwriting user-authored fields).
- Domain tags on files in known top-level folders (merged into existing `tags:` lists).
- A summary listing of files with malformed frontmatter that were **skipped** (not modified).

## Hard rules (revisit before every step)

1. **No body reading.** Inputs are filename, folder structure, and existing frontmatter only. Never parse, summarize, or infer from file content.
2. **Merge, never overwrite.** Existing frontmatter fields the user authored are preserved verbatim. Add only missing schema fields.
3. **Skip malformed frontmatter.** If a file's frontmatter doesn't parse as YAML, list the file in the summary and leave it unmodified.
4. **Idempotent.** Re-running produces no further changes.
5. **Failure soft.** Any per-file error logs and continues; the bootstrap as a whole completes. Errors land in the summary.

## Steps

### Step 0 — Preflight

- Verify `WORKSPACE_ROOT/knowledge/.obsidian/` exists. If absent, abort with: *"No Obsidian vault detected at `knowledge/.obsidian/`. The Obsidian bootstrap is a no-op outside an Obsidian vault."*
- Verify `.pka/roles/_obsidian.md` exists. If absent, seed it from `references/obsidian-conventions.md` first.
- Note `hybrid_monorepo_present`. If true, the bootstrap will end with one consolidated commit in `knowledge/`. If false, the diff is left for the user to commit manually (or not).

### Step 1 — Walk the vault

Single pass through `knowledge/`, applying `.pkaignore` for noise filtering. Collect:

- **Top-level domain folders**: every immediate subdirectory of `knowledge/` (e.g., `AI/`, `personnel/`, `leadership/`, `lab-notebook/`).
- **Personnel subfolders**: every immediate subdirectory of `knowledge/personnel/` (e.g., `personnel/alec/`, `personnel/jane/`).
- **Files** matching one of the known patterns:
  - `personnel/<person>/YYYY-MM-DD-1on1.md` (or `*1-1*.md`, `*1on1*.md`)
  - `leadership/YYYY-MM-DD-*.md`
  - `TechCouncil/YYYY-MM-DD-*.md`
  - `<any>/YYYY-MM-DD-*.md` (generic dated content in known meeting folders)
  - `lab-notebook/YYYY-MM-DD.md`
- **Files in known top-level folders** for domain-tag merging.

No content reading. The walk produces only filenames, paths, and the first-line check for frontmatter presence (`---` on line 1).

### Step 2 — Create MOC stubs

For each top-level domain folder that **lacks** `_MOC.md`:

- Filename: `<domain>/_MOC.md`
- Content (template):

```markdown
# <Domain>

<!-- MOC stub created by pka-bootstrap (obsidian). User can reorganize freely. -->

## Files
- [[<each file in this folder, alphabetical>]]

## Subdomains
- [[<each immediate subfolder>/_MOC|<Subfolder>]]
```

The "Files" list and "Subdomains" list are populated from the walk. Subfolder MOC links use the display-text form `[[path/_MOC|Display]]`.

If a domain folder has only one of (files, subfolders), include only that section. If both empty, omit the headings entirely (just the `# <Domain>` heading and the comment).

If `_MOC.md` already exists: skip silently. Per-domain idempotency.

### Step 3 — Create person index stubs

For each `personnel/<name>/` subfolder that **lacks** `index.md`:

- De-slugify the folder name to a display name: `alec-smith` → `Alec Smith`, `jane` → `Jane`. Heuristic: split on `-`, capitalize each token.
- Filename: `personnel/<name>/index.md`
- Content:

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
- [[<each file in this folder, alphabetical, excluding index.md>]]
```

If `index.md` already exists: skip silently.

### Step 4 — Add filename-pattern frontmatter

For each file matching a known pattern that does **not** already have frontmatter (no `---` on line 1):

| Pattern                                                          | Frontmatter to write                              |
|------------------------------------------------------------------|---------------------------------------------------|
| `personnel/<person>/YYYY-MM-DD-1on1.md` or `*1-1*.md`/`*1on1*.md` | `type: 1on1`, `date: YYYY-MM-DD`, `person: "[[personnel/<person>/index]]"`, `tags: [1on1]` |
| `leadership/YYYY-MM-DD-*.md` or `TechCouncil/YYYY-MM-DD-*.md`     | `type: meeting`, `date: YYYY-MM-DD`, `topic: <slug from filename>`, `attendees: []`, `tags: [meeting, <domain-tag>]` |
| `lab-notebook/YYYY-MM-DD.md`                                       | `date: YYYY-MM-DD`, `tags: [daily]`                |

Insertion: prepend the YAML block (fenced by `---`) to the file. Preserve the original content verbatim after the closing `---`.

The `topic` field for meetings is derived **only from the filename slug** — never from the file body. `2026-04-22-slt-meeting.md` → `topic: slt-meeting`.

### Step 5 — Merge domain tags into existing frontmatter

For each file in a known top-level folder that **has** existing frontmatter:

- Parse the frontmatter as YAML.
- If the `tags:` key is absent: add it with `[<domain-tag>]`.
- If `tags:` exists but doesn't include the domain tag: append the domain tag.
- All other fields are preserved verbatim.

If parsing fails (malformed frontmatter): **skip the file**. Add it to the malformed-frontmatter list in the summary.

### Step 6 — Commit (if hybrid monorepo)

If `hybrid_monorepo_present` is true:

```
cd knowledge
git add -A
git commit -m "Bootstrap (obsidian): N MOCs, M person indexes, K frontmatter additions" \
          -m "" \
          -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

The commit lives in the `knowledge/` child repo. The root repo is untouched.

If `hybrid_monorepo_present` is false: leave the diff in the working tree. The user inspects with their tool of choice and commits (or not).

### Step 7 — Summary

Print to the user:

```
Obsidian bootstrap complete.

MOC stubs created:        N (M already present, skipped)
Person indexes created:   N (M already present, skipped)
Files given frontmatter:  N
Domain tags merged:       K files
Files SKIPPED (malformed frontmatter — listed below): J
  - <path>: <error>
  ...
Total files touched:      P

Commit: knowledge/.git  ("Bootstrap (obsidian): ...")
        OR  No commit (workspace is not a hybrid monorepo — diff is in knowledge/ working tree)
```

## Failure modes

- **No `.obsidian/`**: abort with the message in Step 0.
- **Malformed YAML in an existing file**: skip and list. Do not attempt repair.
- **Filesystem permission error on a single file**: log, continue.
- **Cannot write a new `_MOC.md`**: log, continue. Skip backlinks/MOC updates that depend on it for the rest of this run.

## What NOT to do

- Do not read file bodies for any inference. The only reads allowed are: filenames (from the walk), frontmatter parsing (only the YAML between the first two `---` lines).
- Do not attempt to **fix** malformed frontmatter. Skip the file.
- Do not reorganize MOC files — only add bullets to bottom or to existing sections.
- Do not invent attendees, topics (beyond filename slug), or `related` links from content.
- Do not modify files **outside** `knowledge/`. Even Repo Map updates in `CLAUDE.md` for new domains are out of scope here — that's an orchestrator concern, separate from this bootstrap.
- Do not rename existing files.

## Idempotency check

After running the bootstrap, immediately re-running it must produce no further file changes. Confirm this in tests (see `pka-skills/tests/`).
