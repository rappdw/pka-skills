# Commit Protocol — Librarian Specifics

Applies **only when** `hybrid_monorepo_present` is true. Conventions and full protocol live in `.pka/roles/_git-protocol.md`. This document specifies how the librarian implements them.

## When the librarian commits

After a routing operation **completes successfully** and lands the file inside a child repo (`knowledge/` or `projects/<name>/`):

```
.pka/bin/pka-tools commit -m "Librarian: Route <filename> to <destination-folder>/" -- \
    <routed-file> <each side-effect file this routing touched>
```

Paths are given relative to the workspace root (`knowledge/leadership/2026-04-22-slt-meeting.md`). The command finds the child repo the paths are in, runs `git add -- <paths>` and `git commit -- <paths>` there, and appends the trailer. It is the equivalent of:

```
cd <child-repo-path>
git add -- <paths>
git commit -m "Librarian: Route <filename> to <destination-folder>/" \
          -m "Co-Authored-By: Claude <noreply@anthropic.com>" \
          -- <paths>
```

What it reports, and what to do with it:

| Output | Meaning |
|---|---|
| `Committed <sha> in knowledge: …` | Done. |
| `Nothing to commit: the paths have no changes.` | A zero-diff routing. No commit, by design. |
| `Not committed: the paths are not inside a git repository.` | Not a hybrid monorepo, or the destination is outside any child repo. Nothing to do. |
| `Not committed: … is not a child repository.` | The paths are in the root repo. Root is never committed automatically; use `--stage-only` (below). |
| Exit code 1, `git commit failed …` | A hook, signing or identity problem. The files are still staged and nothing was reset. Put git's message in the routing report and carry on with the next file. |
| Exit code 64 | The arguments were wrong (no paths, paths in two repositories, a path outside the workspace). Fix the call. |

**Stage and commit by path. Never `git add -A`, `git add .` or `git commit -a`.** The child repo is also the user's working area (and, with Obsidian, a vault being edited live), so at any moment it can hold half-written notes and changes the user staged themselves. Naming the paths on both `git add` and `git commit` puts exactly this routing's files in the commit and leaves everything else as it was — modified files stay modified, the user's staged files stay staged.

The paths are the routed file plus every file the routing wrote as a side effect: the `_MOC.md` files that gained a link or pointer row, the person `index.md` files that gained a back-link, and so on. Keep the list as you go.

One commit per semantic unit. The unit is "this routing operation, including its Obsidian side-effects (frontmatter merge, MOC append, person backlink)". All side-effects ride along in the same commit.

## When the librarian does NOT commit

- The destination is **outside** any child repo (e.g., the file went to `owner-inbox/` or `team-inbox/`).
- The destination is **the root repo's working tree** (e.g., a new file in `.pka/` or a CLAUDE.md update).
- The routing failed mid-way (file moved but indexing failed): surface the error, leave the working tree as-is, do not commit a partial state.
- The routing was a **dry run** (the user said "tell me what's in the inbox, don't move anything").

## Bulk routing

When the librarian processes many files in one pass (`process my team-inbox`), produce **one commit per file** in each child repo. This preserves reviewability and enables targeted revert. Do **not** batch into a single mega-commit.

Exception: a single file with multiple side-effects (MOC update + person backlink + frontmatter) is **one** semantic unit and gets **one** commit, as described above.

## Root-tracked side effects

Some routing operations touch root-tracked files:

| Side effect                                                       | Handling                                            |
|-------------------------------------------------------------------|-----------------------------------------------------|
| Updating `CLAUDE.md`'s Repo Map (e.g., new domain folder discovered) | Stage in the **root** repo with `.pka/bin/pka-tools commit --stage-only CLAUDE.md` (or `git add CLAUDE.md`). **Do not commit.** Surface in the routing report. |
| Updating `.meta` (rare for routing — usually only for graduation)   | Same: stage, surface, do not commit.                 |
| Adding a new `.pka/` script or template                              | Same: stage, surface, do not commit.                 |
| Updating `.pka/session-log.md`                                       | Append; stage in root; **do not commit** (root is human-review only). The session-log entry survives across sessions in the root working tree until the user commits. |

## Idempotency

A semantic unit that produces no actual change must produce no commit. Specifically:

- If routing a file that's already at its destination (no-op move), and the Obsidian side-effects also produce no diff: **no commit**. `pka-tools commit` detects this itself and reports "Nothing to commit".
- If the user re-runs `process my team-inbox` on an already-processed inbox: each routed file produces zero-diff routings, hence zero commits.

## Failure handling

| Failure                                       | Behavior                                                                |
|-----------------------------------------------|-------------------------------------------------------------------------|
| `git commit` returns non-zero (hook failure, conflict, etc.) | Surface to the user. Leave files staged. Do not retry destructively. Continue with the next routing — but flag the failed commit in the report. |
| Working tree is dirty before routing (uncommitted or staged user changes) | Proceed. The user's changes are not entangled with our commit because both `git add` and `git commit` name only the paths this routing touched. If one of those paths already had uncommitted user edits (for example a `_MOC.md` the user was editing), their edits go into the commit with ours — say so in the routing report. |
| Pre-commit hook in the child repo modifies files | Re-stage and commit. Hook-modified content is a legitimate part of the unit. |
| LFS upload pending (commit succeeds locally but objects aren't pushed yet) | This is fine for commit. Push happens at session end (or on user "push now"). |

## Trailer

The trailer is **mandatory** and **verbatim**:

```
Co-Authored-By: Claude <noreply@anthropic.com>
```

`pka-tools commit` adds it. Never omit, never alter the spelling/case. The trailer signals to humans (and tooling) that this commit was machine-generated.

## Examples

### Single-file route

User: "process the inbox"
Result: 3 files routed.
Commits in `knowledge/`:
```
Librarian: Route 2026-04-22-slt-meeting.md to leadership/
Librarian: Route ai-strategy-2026.md to AI/
Librarian: Route robin-1-1-2026-04-21.md to personnel/robin/
```
Each commit has `Co-Authored-By: Claude` trailer. No commits in root.

### Route with new domain (root side effect)

User: "process the inbox"
Result: 1 file routed; routing required adding `archived/` as a new domain to the Repo Map.

Commit in `knowledge/`:
```
Librarian: Route legacy-doc.md to archived/
```

In the **root** working tree:
```
M CLAUDE.md   (Repo Map updated to include archived/)
```

Routing report includes:
```
Root-tracked side effects (STAGED, awaiting your review):
  - CLAUDE.md  (Repo Map: + archived/ Reference)
```

### Idempotent re-run

User: "process the inbox" (the inbox has already been processed)
Result: 0 files moved.
Commits: none.
Report: "Inbox is empty (0 files); no routing performed."

## When in doubt

Re-read `.pka/roles/_git-protocol.md`. The conventions document is the authority. This file describes the librarian's specific implementation; the conventions are the same across roles.
