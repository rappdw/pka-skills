# Behavioural evals

`evals/*.evals.json` describe how Claude should behave when it follows the skills: one file per skill, 94 scenarios in all. `evals/run.py` runs them. The mechanical side of the plugin (`pka-tools`, `upgrade-roles.py`) is covered by `tests/`; these evals cover the decisions a model makes around those commands.

An eval run calls a model and costs money. Nothing runs it automatically: not `tests/run-all.sh`, not CI.

## Running

```
python3 evals/run.py --validate                 # check the eval files
python3 evals/run.py --list                     # ids, expectation counts, tags
python3 evals/run.py --dry-run                  # build every workspace, print every command, call no model
python3 evals/run.py --tag smoke --max-total-usd 15
python3 evals/run.py --skill pka-wiki --jobs 2
python3 evals/run.py --scenario 'librarian-backfill-*'
python3 evals/run.py --resume evals/results/20261120-141500     # carry on a run that stopped
python3 evals/run.py --rejudge evals/results/20261120-141500    # grade the stored transcripts again
```

Requirements: Python 3.9+, the Claude Code CLI (`claude` on `PATH`, or `--claude PATH`), and a login the CLI can use non-interactively. On Linux the default isolation also needs `bubblewrap` and `socat`.

| Option | Default | |
|---|---|---|
| `--skill`, `--scenario`, `--tag`, `--limit` | everything | Which scenarios. `--scenario` takes shell wildcards |
| `--include-needs` | off | Also run scenarios marked `needs` (see below) |
| `--model`, `--judge-model` | `sonnet`, `sonnet` | Any alias or model id the CLI accepts |
| `--max-turns` | 40 | Agentic turns per user message |
| `--max-usd` | 1.50 | Spend cap per subject call (`--max-budget-usd`) |
| `--judge-max-usd` | 0.50 | Spend cap per judge call |
| `--max-total-usd` | 25 | No new scenario starts once the run has cost this much |
| `--timeout` | 900 | Seconds per model call |
| `--jobs` | 1 | Scenarios at once |
| `--sandbox` | `require` | `off` runs without the OS sandbox (see "Isolation") |
| `--home` | `scratch` | `real` if the CLI cannot find its login with a scratch home |
| `--work-dir` | system temp | Where scratch workspaces are made |
| `--keep-workspaces` | off | Leave the workspaces for inspection |

Exit code: 0 when every scenario passed (or the dry run prepared all of them), 1 when any was partial or failed, 2 when something could not be run or graded.

Results go to `evals/results/<timestamp>/` (git-ignored): `summary.md` (the table, then every expectation that was not met with the judge's evidence), `summary.json`, one `<skill>/<id>.json` per scenario with the full transcript, the workspace diff and the judgement, and `raw/` with the CLI's own output.

## What it costs

The CLI reports a cost and token counts for every call, and the runner adds them up; `summary.md` leads with the totals.

No run has been measured yet: the runner was built in an environment where the CLI could not log in. Until one has, the only firm numbers are the caps. A full run is 94 scenarios, 128 subject calls (some scenarios have follow-up messages) and 94 judge calls, so the caps allow at most $239, and the run-level cap of $25 stops it long before that. Run the smoke set first (`--tag smoke`, 13 single-message scenarios, at most $26 by the per-call caps), read the cost per scenario in its summary, and multiply.

## A scenario

```json
{
  "id": "librarian-reindex",
  "scenario": "Re-index after one file was added, one changed and one removed",
  "tags": ["smoke"],
  "needs": "PR #24",
  "setup": {"index": true, "steps": [{"write": "knowledge/AI/new-note.md", "text": ["# A new note"]}]},
  "prompt": "Re-index my knowledge base.",
  "followups": ["Yes, go ahead."],
  "expect": "runs `.pka/bin/pka-tools index` without --rebuild; reports the counts the tool printed"
}
```

- `id` is stable: lower-case words joined by hyphens, starting with the skill's short name. Results are filed under it.
- `prompt` is what the user types. `followups` are further user messages, sent one at a time into the same session; they are scripted, so write them to make sense whatever the reply was.
- `expect` is a list of expectations separated by `;` (a semicolon inside backticks or brackets does not split). Each is graded separately. Write each one so that a transcript or a diff can settle it: name the command, the file, or the words to look for. Say what must not happen as its own expectation.
- `tags`: `smoke` marks the small set to run first.
- `needs`: the scenario describes behaviour that is not in this checkout yet (another branch or pull request has it). A real run leaves it out unless `--include-needs` is given; `--dry-run` and the tests still build its workspace. Remove the field when the change has merged.
- `{{today}}`, `{{today-3}}`, `{{today+1}}`, `{{monday}}` (this week's; offsets such as `{{monday+4}}` work as for `today`) and `{{plugin_version}}` are filled in everywhere.

### `setup`

Every scenario starts in a fresh workspace. With no `setup` that is the `vault` fixture, bootstrapped and current.

| Key | Values | Default | |
|---|---|---|---|
| `fixture` | `vault` | yes | The fixture from `tests/fixtures/build_vault.py`, bootstrapped: `CLAUDE.md` rendered from the plugin's own template, role files from the plugin's seeds, toolkit installed |
| | `lint` | | `vault` plus the seeded lint problems (`build_vault.lint_cases`) |
| | `existing` | | The same folders, never bootstrapped: no `CLAUDE.md`, `.pka/`, `.pkaignore` or inboxes |
| | `empty` | | An empty folder |
| `obsidian` | `true`, `false` | `true` | `false` removes `knowledge/.obsidian/` |
| `toolkit` | `current`, `absent` | `current` | `absent`: no `.pka/bin/`, no manifest (a workspace from before v1.7.0) |
| `roles` | `current`, `v1.7.0`, `absent` | `current` | `v1.7.0`: the role files of that release, with the obsolete commit sections and `_git-protocol.md` |
| `index` | `false`, `true`, `"legacy"` | `false` | `true`: `db init` and `index`. `"legacy"`: the same, then schema version 0 |
| `autonomy` | `ask-before-everything`, `ask-before-destructive`, `hands-off` | `ask-before-destructive` | The autonomy level written into `CLAUDE.md` |
| `cwd` | a folder in the workspace | the root | Where the session starts |
| `steps` | a list, applied in order after everything above | | See below |

Steps, one verb each; every path is relative to the workspace and may not leave it:

| Step | |
|---|---|
| `{"write": path, "text": …}` | Write a file. `text` is a string, or a list of lines |
| `{"append": path, "text": …}` | Add to the end of an existing file |
| `{"replace": path, "old": …, "new": …}` | Replace text that must be there |
| `{"remove": path}` | Delete a file or folder |
| `{"copy": path, "to": path}` | Copy within the workspace |
| `{"mkdir": path}` | An empty folder |
| `{"symlink": path, "to": path}` | A symbolic link to another path in the workspace |
| `{"age": path, "days": N}` | Set modification times N days back, recursively |
| `{"fixture_file": name, "to": path}` | Copy a file from `evals/fixtures/` |
| `{"tool": [args…]}` | Run the workspace's `pka-tools` (`"allow_fail": true` if it is meant to refuse) |
| `{"lint_report": {"days_ago": N, "quick": true}}` | Run a lint and date its report N days back |
| `{"git_repo": path}` | Make the folder look like a git repository (a `.git/` skeleton, written without running git) |

A setup that cannot be built is an error, not a skipped step. `tests/evals/test_runner.py` builds every scenario's workspace, so a step that stops applying fails in the free tests.

### Adding one

1. Read the skill text the scenario is about, and run the `pka-tools` commands it ends in against a scratch workspace to see what they print.
2. Add the scenario to the skill's file. Use the fixture's cast only (see `tests/README.md`): in the text of a scenario that means Priya, Robin and Sam, the projects Orion and Lyra, and Northwind. When a scenario needs more people than that (a large meeting), give the extra person folders role names (`head-of-finance`), not invented names.
3. `python3 evals/run.py --dry-run --scenario <id> --keep-workspaces` and look at the workspace.
4. `./tests/test_evals.sh`.
5. Run it for real: `python3 evals/run.py --scenario <id>`. Read the transcript in the result file before trusting the verdict.

## Isolation

What a subject run can and cannot do:

- **Workspace.** A new folder per scenario under the work folder. It is the only place the file tools (`Edit`, `Write`) may write; reads are limited to it and the plugin copy.
- **Plugin.** The subject loads a read-only copy of this checkout, without `evals/` and `tests/`, so it cannot change the plugin and cannot read the expectations. The runner compares the copy before and after and records the result.
- **Tools.** `Bash, Read, Edit, Write, Glob, Grep, Skill`. No web tools, no subagents, no MCP servers.
- **Permissions.** `--permission-mode dontAsk` with an allow list: whatever is not on the list is denied and nobody is asked. Shell commands on the list: the workspace's and the plugin's `pka-tools` and `upgrade-roles.py`, `ls cat head tail wc grep stat which date pwd echo test cd mkdir mv cp`, the two OCR import checks, and `rm` only when the OS sandbox is on. Not on it: `git`, `curl`, `pip`, `python3 -c`, `find`, `sh`. A denied attempt appears in the transcript and counts as an attempt.
- **OS sandbox.** `--sandbox require` (the default) turns on Claude Code's sandbox for shell commands and tells the CLI to refuse to start without it: shell writes are confined to the workspace and temp folders and there is no network. Needs `bubblewrap` and `socat` on Linux; built in on macOS. The runner checks first and stops with one line if it is missing.
- **`--sandbox off`** runs with the allow list only. The list matches command text, not paths: `mv`, `cp` and `mkdir` could reach outside the workspace if the model asked for a path there, and `pka-tools --workspace <elsewhere>` could write elsewhere. Use it only on a machine where that is acceptable.
- **Home.** `HOME` and `TMPDIR` point into the run folder, so `~/…` is scratch space; whatever a run writes there is listed in the evidence. The CLI's own configuration folder is passed by name so that it can log in. User and local settings, the user's `CLAUDE.md`, plugins and MCP servers are not loaded; the parent session's `CLAUDE_*` variables are not passed on.
- **What still lands outside.** The CLI keeps its own records in its configuration folder: for a scenario with follow-ups, the session transcript (removed by the runner afterwards), and an empty per-project folder (removed if empty). Anything left is listed in the result under `isolation`.
- **The judge** has no tools, no plugin and no settings, and runs in an empty folder.

## Grading, and its limits

The judge is a second, separate model call. It gets: the expectations, numbered; a description of the starting state; the user's messages; the transcript (the assistant's text, every tool call with its arguments, every tool result); what the harness denied; the list of files added, removed and changed; a diff of the text files; and the final listing with hashes.

It does not get the skill text. The result of every `Skill` call, of every read of a plugin file, and every message the harness injects into the conversation is replaced by `[withheld]` before the judge sees the transcript. Output of the plugin's own `pka-tools` is kept: that is evidence.

For each expectation it answers `yes`, `no` or `unverifiable`, with quotes from the evidence and a reason. Its instructions: a claim is not evidence ("I ran the lint" counts only with the tool call or the file to show for it); an action is proved by a tool call or the diff, a statement by the assistant's text; "does not happen" needs the whole transcript and diff to show nothing; anything the evidence cannot settle is `unverifiable`, never the benefit of the doubt.

The runner then checks the judge:

- every quote behind a `yes` is looked up in the evidence (ignoring whitespace); a `yes` with no quote that is really there becomes `unverifiable`;
- an expectation the judge skipped is `unverifiable`;
- the verdict is worked out by the runner, not taken from the judge: **pass** when every expectation is met, **fail** when fewer than half are, **partial** otherwise.

Limits to keep in mind:

- The judge is a model. It can misread a transcript; read the evidence for anything surprising. `--rejudge` grades again without re-running the subject.
- An absence ("runs no git command") cannot be quoted, so it rests on the judge having read everything. Long tool results and long diffs are clipped before the judge sees them (the result file has them in full).
- Follow-ups are scripted. If the subject asks something the script did not foresee, the follow-up may not fit, and the scenario will look worse than the behaviour was.
- One run is one sample. A scenario that passes once can fail the next time.
- thinkkit is not loaded, so `take-notes` and `resolve-against-transcript` are always absent: the meeting scenarios test the route-only paths.
- Web search is not available to the subject, so researcher scenarios work from the notes in the workspace.
- A session start cannot be simulated exactly: the session-start scenarios send "Good morning." and rely on `CLAUDE.md`.
- The harness denies what is not on its allow list. When a skill legitimately needs such a command, the expectation comes out `unverifiable` and the denial is in the evidence.
