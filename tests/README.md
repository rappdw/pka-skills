# pka-skills tests

Two layers:

| Layer                                      | Where                                          | Covers                                                       |
|--------------------------------------------|------------------------------------------------|---------------------------------------------------------------|
| **Behavioral evals** (Claude-driven)       | `evals/*.evals.json`                           | Spec scenarios as `prompt`/`expect` pairs the role definitions and skill descriptions are evaluated against. |
| **Mechanical tests**                       | `tests/` (this directory)                      | Everything deterministic: the helper scripts, and `pka-tools` (schema, index, search, pointer rows, the Obsidian retrofit, commits, the installer). |

The two layers are complementary. A skill change can pass the mechanical tests (the mechanics still work) and fail the evals (the role's decision-making is wrong), or vice versa. Run both before merging.

**The mechanical tests run the code that ships.** Every suite installs the plugin's assets into a temporary workspace with `pka-tools install` and then runs the workspace's own copies (`.pka/graduate.sh`, `.pka/bin/pka-tools`, …). Before v1.7 two suites drove reference implementations that lived only in this directory; those are gone.

## Run all tests

```
./tests/run-all.sh
```

Each suite exits 0 when all its tests pass. The runner aggregates and prints a final summary.

## Suites

| Suite                     | Script                              | Covers                                   |
|---------------------------|-------------------------------------|------------------------------------------|
| Git bootstrap             | `test_git_bootstrap.sh`             | S12, S13, S14, S15, S16, S22             |
| Obsidian bootstrap        | `test_obsidian_bootstrap.sh`        | S3, S4, S5, S6 via `pka-tools obsidian bootstrap` |
| Commit/push protocol      | `test_commit_protocol.sh`           | S17, S18, S19, S20, S21                  |
| Upgrade (v1.5 → v1.6+)    | `test_upgrade.sh`                   | U1–U11                                   |
| Pointer layer             | `test_pointer_layer.sh`             | PR1–PR6 + cross-MOC via `pka-tools pointers`, `index`, `search` |
| Script safety (v1.6.3)    | `test_script_safety.sh`             | A1–A11: one regression test per data-loss or mis-reporting bug fixed in the helper scripts |
| pka-tools (v1.7)          | `test_tools.sh` → `tools/test_*.py` | The toolkit, command by command (below)   |

The runner adds one more check of its own: it fingerprints your global git configuration before and after the run and fails if the suites changed it.

### The pka-tools tests

Python `unittest` modules, standard library only. Run them alone with `./tests/test_tools.sh`, or under another interpreter with `PKA_TEST_PYTHON=/path/to/python3.9 ./tests/test_tools.sh`.

| Module | Covers |
|---|---|
| `tools/test_text.py` | Line splitting, fences, table cells, wikilinks, frontmatter reading and line-level editing, `.pkaignore`, the Repo Map, the file walk |
| `tools/test_db_index_search.py` | `db init`, `db migrate` (plan, apply, backup, rollback, legacy layouts), `index` (incremental, sidecars, pointer rows, prune, dry run), `search` (quoting, pointer boost, fallback) |
| `tools/test_pointers.py` | The cluster rule (including the scenario the old Jaccard rule failed), edits to padded and CRLF tables, unreadable tables, rename, check |
| `tools/test_obsidian.py` | The retrofit, and the **round trip**: every mutating command over the fixture vault, asserting that no line changed that the tools do not own and that a second pass changes nothing |
| `tools/test_commit_actions.py` | `commit` (exact paths, root never committed, failures reported) and `actions` |
| `tools/test_install.py` | The installer and manifest; the tool's version matches the plugin's; Python 3.9 syntax; standard library only |
| `tools/test_postroute.py` | `post-route` (the whole pipeline in a hybrid monorepo, a meeting note filed the same as a librarian route, moves, refused commits, plain vaults), `moc add-link`, the pointer-layer opt-in and `pointers init`, `log add / open / check` |
| `tools/test_upgrade_refresh.py` | `upgrade-roles.py --refresh` (unedited old sections replaced, customised ones kept, CRLF, dry run), and the seed copies matching the references (`scripts/seeds.py --check`) |
| `tools/test_hardening.py` | One regression test per bug found in review: `GIT_DIR` in the environment, pathspec patterns, read-only and symlinked files, capture directories, unlinkable filenames, bare carriage returns, corrupt database, manifest keys that leave `.pka/` |

`tools/support.py` holds the shared test case. `fixtures/build_vault.py` generates the fixture workspace. It is generated rather than stored so that the awkward bytes survive git: CRLF line endings, a byte-order mark, a missing final newline, a non-UTF-8 file, and names with spaces, commas and non-ASCII letters.

## Why some scenarios are JSON-only

Scenarios that depend on Claude's natural-language understanding or decision-making (e.g., S1–2 detection-driven behavior, S7–11 per-route enhancements, S8 wikilink choice, S11 brief frontmatter generation) live in the JSON evals at `evals/`. The mechanical tests verify the deterministic commands those decisions end in.

## Adding a test

- Use `lib.sh` helpers (`make_workspace`, `install_pka_assets`, `assert_*`).
- Each test invokes `start_test "<name>"` once.
- End with `end_run` so the failure summary is printed.
- Clean up temp workspaces with `cleanup_workspace`. For anything else a test creates outside a workspace, use `d=$(make_scratch_dir); register_cleanup "$d"`. Do not set your own `EXIT` trap; `lib.sh` owns it.
- Stay portable between Linux and macOS: use `file_hash` (not `md5sum`), `replace_in_file` (not `sed -i`), and bash 3.2 syntax.
- When you fix a bug in a helper script, add a test that fails on the old script and passes on the new one.
- A `pka-tools` behaviour that writes anything gets a test in `tests/tools/` that runs the vendored copy (`self.tool(...)` in `support.ToolsCase`), not an import of an internal function.

## Examples use the fixture cast only

Every name in a test, fixture, eval or doc example must be invented. Use the existing cast — people such as Priya and Robin, the project Orion, the company Northwind, hosts under `example.com` — and never copy a person, project, company, meeting or folder name from a real workspace, including your own. This repository is public, and names lifted from a real vault have had to be scrubbed from its history once already.

## Requirements

- `bash` (3.2 or newer), `git` 2.32 or newer, `git-lfs`, `python3` 3.9 or newer on PATH.
- Tests create temp workspaces under `${TMPDIR:-/tmp}/pka-test.*` and `pka-tools-test.*` and clean them up unconditionally.
- Tests run with an **isolated git identity**: `configure_test_git_identity` points `HOME` and `GIT_CONFIG_GLOBAL` at a throwaway directory and ignores the system config. Nothing is written to your own `~/.gitconfig`. (Before v1.6.3 the helper wrote the test identity into the real global config.)
- CI runs the suite on Linux and macOS for every push and pull request, and the pka-tools tests again under Python 3.9 (`.github/workflows/tests.yml`).
