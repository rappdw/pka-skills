# pka-skills addendum tests

Two layers of tests cover the addendum:

| Layer                                      | Where                                          | Covers                                                       |
|--------------------------------------------|------------------------------------------------|---------------------------------------------------------------|
| **Behavioral evals** (Claude-driven)       | `pka-skills/evals/*.evals.json`                | The 22 spec scenarios as `prompt`/`expect` pairs the role definitions and skill descriptions are evaluated against. |
| **Mechanical shell tests**                 | `pka-skills/tests/*.sh` (this directory)       | Determinstic primitives: bootstrap script behavior, commit and push mechanics, frontmatter merge, idempotency, no-network guarantees. |

The two layers are complementary. A skill change can pass the shell tests (the mechanics still work) and fail the evals (the role's decision-making is wrong), or vice versa. Run both before merging.

## Run all shell tests

```
bash pka-skills/tests/run-all.sh
```

Each suite exits 0 when all its tests pass. The runner aggregates and prints a final summary.

## Suites

| Suite                     | Script                              | Spec scenarios covered                   |
|---------------------------|-------------------------------------|------------------------------------------|
| Git bootstrap             | `test_git_bootstrap.sh`             | S12, S13, S14, S15, S16, S22             |
| Obsidian bootstrap        | `test_obsidian_bootstrap.sh`        | S3, S4, S5, S6                           |
| Commit/push protocol      | `test_commit_protocol.sh`           | S17, S18, S19, S20, S21                  |

## Why some scenarios are JSON-only

Scenarios that depend on Claude's natural-language understanding or decision-making (e.g., S1–2 detection-driven behavior, S7–11 per-route enhancements, S8 wikilink choice, S11 brief frontmatter generation) live in the JSON evals at `pka-skills/evals/`. The shell tests verify the deterministic primitives those decisions ultimately invoke (e.g., the commit format, the script behavior, frontmatter merging).

## What `bootstrap_obsidian.py` is

A reference implementation of the Obsidian mechanical-retrofit algorithm described in `pka-skills/skills/pka-bootstrap/references/obsidian-bootstrap.md`. Used by `test_obsidian_bootstrap.sh` to drive the algorithm against fixture vaults and verify the spec invariants (idempotency, malformed-frontmatter handling, merge-not-overwrite, etc.).

This is **not** a runtime artifact — it's a test companion. The actual bootstrap is executed by `pka-bootstrap` (i.e., Claude follows the algorithm in the reference document).

## Adding a test

- Use `lib.sh` helpers (`make_workspace`, `install_pka_assets`, `assert_*`).
- Each test invokes `start_test "<name>"` once.
- End with `end_run` so the failure summary is printed.
- Clean up temp workspaces with `cleanup_workspace`.

## Requirements

- `bash`, `git`, `git-lfs`, `python3` on PATH.
- Tests create temp workspaces under `/tmp/pka-test.*` and clean them up unconditionally.
- Tests configure a transient git identity via `configure_test_git_identity` so they work in CI.
