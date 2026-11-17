# pka-skills addendum tests

Two layers of tests cover the addendum:

| Layer                                      | Where                                          | Covers                                                       |
|--------------------------------------------|------------------------------------------------|---------------------------------------------------------------|
| **Behavioral evals** (Claude-driven)       | `pka-skills/evals/*.evals.json`                | The 22 spec scenarios as `prompt`/`expect` pairs the role definitions and skill descriptions are evaluated against. |
| **Mechanical shell tests**                 | `pka-skills/tests/*.sh` (this directory)       | Determinstic primitives: bootstrap script behavior, commit and push mechanics, frontmatter merge, idempotency, no-network guarantees. |

The two layers are complementary. A skill change can pass the shell tests (the mechanics still work) and fail the evals (the role's decision-making is wrong), or vice versa. Run both before merging.

## Run all shell tests

```
./tests/run-all.sh
```

Each suite exits 0 when all its tests pass. The runner aggregates and prints a final summary.

## Suites

| Suite                     | Script                              | Spec scenarios covered                   |
|---------------------------|-------------------------------------|------------------------------------------|
| Git bootstrap             | `test_git_bootstrap.sh`             | S12, S13, S14, S15, S16, S22             |
| Obsidian bootstrap        | `test_obsidian_bootstrap.sh`        | S3, S4, S5, S6                           |
| Commit/push protocol      | `test_commit_protocol.sh`           | S17, S18, S19, S20, S21                  |
| Upgrade (v1.5 → v1.6+)    | `test_upgrade.sh`                   | U1, U2, U3, U4, U5, U6, U7               |
| Pointer layer (v1.6.1)    | `test_pointer_layer.sh`             | PR1, PR2, PR3, PR4, PR5, PR6 + PR-extra  |
| Script safety (v1.6.3)    | `test_script_safety.sh`             | A1–A11: one regression test per data-loss or mis-reporting bug fixed in the helper scripts |

`test_upgrade.sh` also carries U8–U11 (fenced code blocks, CRLF, missing anchor, same-second backups).

The runner adds one more check of its own: it fingerprints your global git configuration before and after the run and fails if the suites changed it.

## Why some scenarios are JSON-only

Scenarios that depend on Claude's natural-language understanding or decision-making (e.g., S1–2 detection-driven behavior, S7–11 per-route enhancements, S8 wikilink choice, S11 brief frontmatter generation) live in the JSON evals at `pka-skills/evals/`. The shell tests verify the deterministic primitives those decisions ultimately invoke (e.g., the commit format, the script behavior, frontmatter merging).

## What `bootstrap_obsidian.py` is

A reference implementation of the Obsidian mechanical-retrofit algorithm described in `pka-skills/skills/pka-bootstrap/references/obsidian-bootstrap.md`. Used by `test_obsidian_bootstrap.sh` to drive the algorithm against fixture vaults and verify the spec invariants (idempotency, malformed-frontmatter handling, merge-not-overwrite, etc.).

This is **not** a runtime artifact — it's a test companion. The actual bootstrap is executed by `pka-bootstrap` (i.e., Claude follows the algorithm in the reference document).

## Adding a test

- Use `lib.sh` helpers (`make_workspace`, `install_pka_assets`, `assert_*`).
- Each test invokes `start_test "<name>"` once.
- End with `end_run` so the failure summary is printed.
- Clean up temp workspaces with `cleanup_workspace`. For anything else a test creates outside a workspace, use `d=$(make_scratch_dir); register_cleanup "$d"`. Do not set your own `EXIT` trap; `lib.sh` owns it.
- Stay portable between Linux and macOS: use `file_hash` (not `md5sum`), `replace_in_file` (not `sed -i`), and bash 3.2 syntax.
- When you fix a bug in a helper script, add a test that fails on the old script and passes on the new one.

## Examples use the fixture cast only

Every name in a test, fixture, eval or doc example must be invented. Use the existing cast — people such as Priya and Robin, the project Orion, the company Northwind, hosts under `example.com` — and never copy a person, project, company, meeting or folder name from a real workspace, including your own. This repository is public, and names lifted from a real vault have had to be scrubbed from its history once already.

## Requirements

- `bash` (3.2 or newer), `git` 2.32 or newer, `git-lfs`, `python3` on PATH.
- Tests create temp workspaces under `${TMPDIR:-/tmp}/pka-test.*` and clean them up unconditionally.
- Tests run with an **isolated git identity**: `configure_test_git_identity` points `HOME` and `GIT_CONFIG_GLOBAL` at a throwaway directory and ignores the system config. Nothing is written to your own `~/.gitconfig`. (Before v1.6.3 the helper wrote the test identity into the real global config.)
- CI runs the suite on Linux and macOS for every push and pull request (`.github/workflows/tests.yml`).
