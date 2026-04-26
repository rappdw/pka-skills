# Upgrade Existing Bootstrap — Algorithm

Procedure for the `upgrade` bootstrap target. Invoked when a user with an already-bootstrapped workspace (typically pre-v1.6) requests the addendum behavior. Examples: "upgrade my pka", "bootstrap upgrade", "update my role files".

## When to use this vs other targets

| Workspace state                                                   | Right target          |
|-------------------------------------------------------------------|-----------------------|
| No `.pka/`, no `CLAUDE.md`                                        | base bootstrap        |
| `.pka/` exists, role files present, but `_obsidian.md` is missing | `upgrade`             |
| `.pka/` exists with v1.6 role files already (re-running)          | `upgrade` (idempotent — no changes) |
| `.pka/` not present                                               | NOT this target — refuse |

`upgrade` is also safe to combine with `obsidian` and `git` targets: a user who runs `bootstrap all` on an already-bootstrapped v1.5 workspace gets upgrade + obsidian retrofit + git monorepo init.

## What it does

1. **Backup `.pka/roles/`** to `.pka/upgrade-backups/<timestamp>/roles/`.
2. **Seed shared references** if absent:
   - `.pka/roles/_obsidian.md` ← `references/obsidian-conventions.md`
   - `.pka/roles/_git-protocol.md` ← `references/git-protocol.md`
   Skipped silently if the user already has them (e.g., from a partial earlier run).
3. **Structured-merge new H2 sections** into existing role files (orchestrator, librarian, researcher).
   - Inserts BEFORE the first `## Output Conventions` or `## Invocation` heading found.
   - Only adds sections whose H2 heading text is not already present.
   - Never modifies the body of existing sections.
4. **Print a summary** listing:
   - Backup path
   - Shared references seeded vs. already present
   - Per-role: sections added vs. already present
   - A note about manual merges that this script does NOT perform.

## What it does NOT do

- **Never modifies the body of existing H2 sections.** If the user has customized `## Working Style` or `## Output Conventions`, those bytes stay byte-identical. The v1.6 additions to those sections (e.g., the new "never auto-commits root" bullet on orchestrator's Output Conventions) are NOT applied automatically — they're documented in `references/role-definitions.md` for the user to merge manually.
- **Never modifies frontmatter** in role files. Existing `model:`, `tools:`, etc. are preserved.
- **Never deletes** content. The whole upgrade is additive.
- **Never auto-commits.** Even when run inside a hybrid monorepo, the upgrade leaves changes in the working tree for human review.
- **Never touches files outside `.pka/`.** Only the role files and shared references are modified.

## Implementation

The merge is implemented in `bootstrap-assets/scripts/upgrade-roles.py`, vendored at `.pka/upgrade-roles.py` on first run. The script is deterministic — every line of new content is hardcoded into the helper, so the same input file always produces the same output. No LLM-driven merging.

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
- **Existing role file has no anchor section** (`## Output Conventions` or `## Invocation`): the new sections are appended at the end of the file. The summary notes this.
- **Filesystem errors** (permission, disk full): surface the error verbatim, abort, leave the backup intact. Partial role files are not written — Python's `Path.write_text` is atomic on most filesystems but the backup is the safety net regardless.

## Vendoring

`upgrade-roles.py` is installed to `.pka/upgrade-roles.py` as part of:
- Base bootstrap (so future workspaces have it ready)
- `bootstrap upgrade` itself (so users on v1.5 who upgrade the plugin can run upgrade without first re-running base bootstrap)

It's a Python file (the only Python in the asset bundle), kept in sync with the seeds it uses. When the seeds change, the embedded copies in this script must change too — that's the trade-off for not depending on the plugin's reference docs at runtime (the script needs to work even if the plugin's source isn't accessible from the user's workspace).

## Manual follow-up the user may want

After running `upgrade`, the user may want to:

1. **Add new bullets to existing sections.** The v1.6 seed adds bullets to `## Key Competencies` (orchestrator: "Bootstrap dispatch", "Session-end push") and `## Output Conventions` (all three roles: greeting line, never-auto-commit-root). The upgrade does not touch these. Compare against `references/role-definitions.md` and add them if desired.
2. **Update role frontmatter** if a new model is preferred. Upgrade preserves existing frontmatter; users decide whether to switch (`claude-opus-4-5` → `claude-opus-4-7` etc.).
3. **Re-run `bootstrap obsidian`** if they want the mechanical retrofit on an existing vault.
4. **Run `bootstrap git`** if they want the hybrid monorepo and haven't yet.

The summary output should suggest these as next steps when relevant (e.g., when `_obsidian.md` was just seeded and the workspace has `knowledge/.obsidian/`).
