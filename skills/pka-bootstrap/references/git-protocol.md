# Git/Push Protocol Conventions (seed)

This file is the **source of truth** for the `_git-protocol.md` shared-reference that `pka-bootstrap` writes to `.pka/roles/_git-protocol.md` in a user's workspace. The content below is what gets seeded verbatim.

`.pka/roles/_git-protocol.md` is **shared reference** for pka roles (orchestrator, librarian, researcher). It is not a role itself. Roles link here instead of duplicating these rules.

The protocol applies whether or not Obsidian is present. It activates only in a workspace that has been bootstrapped as a hybrid monorepo (root `.git` + child repos coordinated via `.meta`). In a single-repo or no-repo workspace, roles continue their pre-protocol behavior.

---

## Seed content (copied verbatim into `.pka/roles/_git-protocol.md`)

```markdown
---
title: Commit/Push Protocol
type: shared-reference
status: active when workspace is a hybrid monorepo (root .git + .meta + child repos)
---

# Commit/Push Protocol

Shared reference for pka roles. Roles link here instead of duplicating commit-and-push rules.

This protocol activates only when the workspace is a **hybrid monorepo**: a root `.git`, a `.meta` manifest at the root, and one or more child repos (`knowledge/`, `projects/<name>/`) each with their own `.git`. In a single-repo or no-repo workspace, roles continue their pre-protocol behavior — no auto-commit, no session-end push.

## Detection

```
hybrid_monorepo_present := file_exists("./.meta") AND directory_exists("./.git")
```

Evaluate once at session start, cache for the session.

## Commit triggers

### Child repos (`knowledge/`, `projects/*`)

**Auto-commit per semantic unit** after a role completes meaningful work.

A "unit" is a coherent, reviewable change — not every file-write, but one commit per *thing accomplished*. The role decides the unit boundary.

Examples:
- Librarian routing a file into `knowledge/` → one commit after the route completes (including any MOC/frontmatter/backlink side-effects).
- Researcher finalizing a brief → one commit when the brief is saved.
- Obsidian bootstrap → one commit in `knowledge/` summarizing the batch.
- Graduation → see "Graduation commit sequence" below.

### Root repo

**No auto-commit. Ever.**

Root repo changes (`CLAUDE.md` updates, `.meta` changes, new/updated `.pka/` scripts or templates, git-bootstrap scaffolding) accumulate in the working tree. The role:

1. Stages obviously-related changes with `git add` (best-effort grouping).
2. Lists them in the session summary.
3. Hands off to the user for review and manual commit.

Rationale: the root is the system's own configuration. Its blast radius is larger than any single child repo. Bad auto-commits there are harder to notice and unwind. Human review is the gate.

## Commit message structure

Commits carry a role prefix and a short description, followed by a Claude trailer:

```
<Role>: <short description>

<optional body>

Co-Authored-By: Claude <noreply@anthropic.com>
```

Examples:
- `Librarian: Route 2026-04-22-slt-meeting.md to leadership/`
- `Researcher: Add brief on AI adoption tier productivity gap`
- `Bootstrap (obsidian): 7 MOC stubs, 12 person indexes, 41 frontmatter additions`
- `Bootstrap (git): Initial hybrid monorepo setup`
- `Graduate: widget → knowledge/reference/`

The trailer is mandatory. Do not omit. The exact trailer string is `Co-Authored-By: Claude <noreply@anthropic.com>`.

## Push triggers

### Session end (auto)

At session end, the orchestrator runs a consolidated push across all child repos with unpushed commits. Implementation: `meta git push` if `meta` is on PATH, else iterate `.meta` entries and run `git push` in each child repo directory.

The session-end push is part of the session-end protocol — it runs after the final session-log entry is written.

### Mid-session on user request

If the user says "push", "push now", "push the changes", or similar natural phrasing, push immediately across all child repos with unpushed commits and report a summary. Session continues.

### Root repo push

The root is pushed only after the user has committed it. The auto-push uses `meta git push` (or equivalent), which operates on registered child repos; if the root is also tracked in the manifest, it pushes only committed state — same gate as commit.

If the root has uncommitted changes at session end, surface them in the summary. Do not commit; do not push.

## Push behavior — never silent failures

Any push failure (auth error, conflict, network unreachable, LFS upload disconnect) surfaces explicitly in the session summary with the failing repo and the error message. Do not hide. Do not retry destructively (no `--force`, no rebase).

If a child repo has no remote configured (placeholder `.meta` URL or empty `origin`), report it as a **skipped** push, not a failure.

## Graduation commit sequence

When a project is graduated from `projects/<name>/` to `knowledge/<subdir>/<name>/` via `graduate.sh`:

1. In `knowledge/` (child repo): auto-commit the new content with message `Graduate: <name> → knowledge/<subdir>/`.
2. In root repo: `.meta` update removing `projects/<name>` is **staged, not committed**. Flagged in the session summary for user review.
3. The old project repo on the remote (if any): the graduation script prints instructions for archiving (e.g., a Gitea/GitHub API call). The role does not call remote APIs.

## Failure behavior

- **Commit failure** (merge conflict, pre-commit hook failure, unexpected working-tree state): surface to the user, pause further automatic commits in that repo, continue with other work. Do not force, amend, or retry destructively.
- **Push failure at session end**: record in session log and summary; continue (don't block session close). User can re-invoke push next session.
- **LFS-specific failures** (missing `git-lfs` binary, oversized object, remote-side disconnect mid-upload): surface with a remediation hint (e.g., install lfs, retry push — LFS uploads are resumable, prior objects are already on the server).

## Interaction with the Obsidian bootstrap

The Obsidian bootstrap produces changes inside `knowledge/` only. Under this protocol it is a single child-repo commit (`Bootstrap (obsidian): ...`), auto-committed per the child-repo rule above. The user reviews the diff in `knowledge/` before (or after) the session-end push.

## Interaction with the git bootstrap

The git bootstrap is a special case:

- Initial commits in `knowledge/` and each `projects/*` are mechanical and safe to auto-commit (`Bootstrap (git): Initial hybrid monorepo setup`).
- Root-repo scaffolding (root `.gitignore`, `.meta`, `.pka/` templates and scripts) is **staged but not committed**. The user reviews and commits.
- No remotes are set; no push is attempted.

## Invariants

Things that MUST hold:

1. **Root never auto-commits.** Every code path that touches root files must stop at "staged, ready for review" and surface the changes in the session summary.
2. **Auto-commits in child repos are idempotent at the unit level.** A repeated semantic action (e.g., re-routing the same file with no change) does not produce an empty or duplicate commit.
3. **Trailer is always `Co-Authored-By: Claude <noreply@anthropic.com>`** (verbatim) on auto-commits.
4. **Session-end push is non-blocking.** Failures surface; session close still proceeds.
5. **No remote operations during git bootstrap.** No `git push`, no `curl`, no origin URLs to user-specific orgs.
```

---

## Notes for `pka-bootstrap`

- This seed is written by `pka-bootstrap` during base bootstrap (Phase 3f) **and** as part of `bootstrap git` / `bootstrap all` (so users on older base bootstraps get it backfilled).
- **Do not overwrite** if the file already exists in the target workspace — the user may have customized it. Skip silently and report "already present" in the summary.
- The seed has no placeholders. Copy verbatim from the fenced block above.
- After seeding, the orchestrator/librarian/researcher role files reference this file by path: `.pka/roles/_git-protocol.md`. Do not duplicate the rules in the role files.
- This file is **inert** when the workspace is not a hybrid monorepo (`hybrid_monorepo_present` is false). Its presence in `.pka/roles/` is harmless until detection turns true.
