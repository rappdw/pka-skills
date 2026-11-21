"""Tests for the eval runner (evals/run.py). No model and no network: the
Claude Code CLI is replaced by tests/evals/fake_claude.py."""
from __future__ import annotations

import importlib.util
import io
import json
import re
import os
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SAMPLES = HERE / "samples"
FAKE = HERE / "fake_claude.py"
sys.dont_write_bytecode = True

_spec = importlib.util.spec_from_file_location("pka_eval_run", str(REPO / "evals" / "run.py"))
run = importlib.util.module_from_spec(_spec)
sys.modules["pka_eval_run"] = run
_spec.loader.exec_module(run)


def sample(name: str) -> str:
    return (SAMPLES / name).read_text(encoding="utf-8")


class Case(unittest.TestCase):
    def setUp(self) -> None:
        base = tempfile.mkdtemp(prefix="pka-evals-test.", dir=os.environ.get("TMPDIR") or None)
        self.base = Path(os.path.realpath(base))
        self.addCleanup(run.remove_tree, self.base)
        self.home = self.base / "home"
        self.home.mkdir()
        self._env = dict(os.environ)
        self.addCleanup(self._restore_env)

    def _restore_env(self) -> None:
        os.environ.clear()
        os.environ.update(self._env)

    def build(self, setup: dict, name: str = "ws") -> Path:
        ws = self.base / name
        run.build_workspace(setup, ws, self.home)
        return ws

    def tool(self, ws: Path, *args: str, plugin: bool = False):
        tool = run.PLUGIN_TOOL if plugin else ws / ".pka" / "bin" / "pka-tools"
        proc = subprocess.run([sys.executable, str(tool)] + list(args), cwd=str(ws), env=run.tool_env(self.home),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def status(self, ws: Path) -> dict:
        code, out, err = self.tool(ws, "status", "--workspace", str(ws), "--json", plugin=True)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def role_preview(self, ws: Path) -> str:
        script = REPO / "bootstrap-assets" / "scripts" / "upgrade-roles.py"
        proc = subprocess.run([sys.executable, str(script), "--workspace", str(ws), "--dry-run"],
                              env=run.tool_env(self.home), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout


# ------------------------------------------------------------------ the eval files

def waiting(*ids_or_skills, label="PR #99"):
    """Mark scenarios as waiting on another change. No shipped scenario waits,
    so the tests for that feature mark their own."""
    from unittest import mock
    real = run.load_scenarios

    def fake(evals_dir=run.EVALS_DIR):
        out = real(evals_dir)
        for scenario in out:
            if scenario["id"] in ids_or_skills or scenario["skill"] in ids_or_skills:
                scenario["needs"] = label
        return out
    return mock.patch.object(run, "load_scenarios", fake)


class EvalFiles(unittest.TestCase):
    def test_every_file_loads_and_ids_are_unique(self) -> None:
        scenarios = run.load_scenarios()
        self.assertGreaterEqual(len(scenarios), 80)
        self.assertEqual(len({s["id"] for s in scenarios}), len(scenarios))
        self.assertEqual({s["skill"] for s in scenarios}, set(run.SKILLS))
        for scenario in scenarios:
            self.assertTrue(scenario["expectations"], scenario["id"])
            self.assertTrue(scenario["id"].startswith(scenario["skill"][4:] + "-"), scenario["id"])

    def test_smoke_set_covers_every_skill(self) -> None:
        smoke = [s for s in run.load_scenarios() if "smoke" in s["tags"]]
        self.assertTrue(10 <= len(smoke) <= 14, len(smoke))
        self.assertFalse([s["id"] for s in smoke if s["needs"]], "the smoke set runs against this checkout")
        runnable = {s["skill"] for s in run.load_scenarios() if not s["needs"]}
        self.assertEqual({s["skill"] for s in smoke}, runnable)

    def test_scenarios_that_wait_for_another_change_are_left_out_on_request(self) -> None:
        self.assertFalse([s["id"] for s in run.load_scenarios() if s["needs"]],
                         "a release ships no scenario that waits on another change")
        with waiting("pka-interface"):
            scenarios = run.load_scenarios()
        waiting_now = [s for s in scenarios if s["needs"]]
        self.assertTrue(waiting_now)
        self.assertTrue(all(s["needs"].startswith("PR #") for s in waiting_now))
        self.assertEqual(len(run.select(scenarios, [], [], [], None)), len(scenarios))
        kept = run.select(scenarios, [], [], [], None, include_needs=False)
        self.assertEqual(len(kept), len(scenarios) - len(waiting_now))
        self.assertEqual(run.select(scenarios, [], [waiting_now[0]["id"]], [], None, include_needs=False), [])

    def test_no_eval_expects_a_commit_or_a_push(self) -> None:
        # pka-skills stopped running git in v1.8.0; an expectation may only say that it does not.
        for scenario in run.load_scenarios():
            for text in scenario["expectations"]:
                low = text.lower()
                if re.search(r"\b(commit\w*|push\w*|git (add|commit|push|init|mv))\b", low):
                    self.assertRegex(low, r"\b(no|not|never|neither|nor|nothing|without|uncommitted|removed|obsolete|"
                                          r"although|left|user|themselves)\b", "%s: %s" % (scenario["id"], text))

    def test_expectations_split_on_semicolons_outside_brackets_and_code(self) -> None:
        text = "runs `a; b` once; says (one; two) things; keeps [x; y]; done"
        self.assertEqual(run.split_expectations(text), ["runs `a; b` once", "says (one; two) things", "keeps [x; y]", "done"])
        self.assertEqual(run.split_expectations(" one ;; two; "), ["one", "two"])

    def test_placeholders(self) -> None:
        os.environ["PKA_EVAL_TODAY"] = "2026-11-20"       # a Friday
        try:
            self.assertEqual(run.fill("{{today}} {{today-3}} {{today+1}} {{monday}} {{monday-10}}"),
                             "2026-11-20 2026-11-17 2026-11-21 2026-11-16 2026-11-06")
            self.assertEqual(run.fill("v{{plugin_version}}"), "v" + run.plugin_version())
            self.assertEqual(run.fill("{{other}}"), "{{other}}")
        finally:
            del os.environ["PKA_EVAL_TODAY"]

    def test_bad_eval_files_are_reported_in_plain_words(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "pka-wiki.evals.json"
            path.write_text(json.dumps([
                {"id": "Wiki One", "prompt": "p", "expect": "e"},
                {"id": "wiki-two", "prompt": "p", "expect": "e", "extra": 1},
                {"id": "wiki-two", "prompt": "", "expect": "e"},
                {"id": "wiki-three", "prompt": "p", "expect": "e",
                 "setup": {"fixture": "castle", "steps": [{"write": "../out.md", "text": "x"}, {"write": "a", "append": "b"},
                                                         {"replace": "a.md", "old": "x"}, {"tool": "index"}], "colour": 1}},
                {"id": "wiki-four", "prompt": "p", "expect": "e", "setup": {"fixture": "empty", "index": True}},
            ]), encoding="utf-8")
            with self.assertRaises(run.RunnerError) as caught:
                run.load_scenarios(Path(folder))
        message = str(caught.exception)
        for part in ("needs an id", "unknown key 'extra'", "id already used", "non-empty 'prompt'", "unknown fixture 'castle'",
                     "unknown setup key 'colour'", "must stay inside the workspace", "needs exactly one of",
                     "(replace) needs 'new'", "tool takes a list", "has no meaning with the 'empty' fixture"):
            self.assertIn(part, message)

    def test_selection(self) -> None:
        scenarios = run.load_scenarios()
        wiki = run.select(scenarios, ["wiki"], [], [], None)
        self.assertTrue(wiki and all(s["skill"] == "pka-wiki" for s in wiki))
        self.assertEqual([s["id"] for s in run.select(scenarios, [], ["wiki-list"], [], None)], ["wiki-list"])
        self.assertTrue(all(s["id"].startswith("tutorial-") for s in run.select(scenarios, [], ["tutorial-*"], [], None)))
        self.assertEqual(len(run.select(scenarios, [], [], [], 3)), 3)
        self.assertEqual(len(run.select(scenarios, ["pka-wiki"], [], ["smoke"], None)), 2)
        with self.assertRaises(run.RunnerError):
            run.select(scenarios, [], ["no-such-scenario"], [], None)
        with self.assertRaises(run.RunnerError):
            run.select(scenarios, ["pka-nothing"], [], [], None)


# ------------------------------------------------------------------ the setup vocabulary

class Setup(Case):
    def test_default_is_a_current_bootstrapped_workspace(self) -> None:
        ws = self.build({})
        text = (ws / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertNotIn("{{", text)
        self.assertIn("<!-- PKA", text)
        self.assertIn("# Sam's Personal Knowledge Assistance", text)
        self.assertIn("Ask before destructive actions", text)
        self.assertIn("Markdown-only", text)
        self.assertIn("Completed projects archive to: `knowledge/archived/`", text)
        self.assertIn("| `knowledge/leadership/` | Leadership meeting notes | by date | Active | active | High | meeting-home |", text)
        self.assertTrue(text.rstrip("\n").split("\n")[-1].startswith("| `projects/`"), "the Repo Map table ends the file")
        for name in ("orchestrator.md", "researcher.md", "librarian.md", "roster.md", "_obsidian.md"):
            self.assertTrue((ws / ".pka" / "roles" / name).is_file(), name)
        self.assertTrue((ws / ".pka" / "roles" / "orchestrator.md").read_text(encoding="utf-8").startswith("---\nrole: orchestrator"))
        self.assertTrue((ws / "knowledge" / ".obsidian").is_dir())
        self.assertFalse((ws / ".pka" / "knowledge.db").exists())
        status = self.status(ws)
        self.assertEqual(status["vendored_version"], status["tool_version"])
        self.assertTrue(status["obsidian_present"])
        self.assertEqual(status["people_home"], "knowledge/personnel")
        preview = self.role_preview(ws)
        self.assertNotIn("  + ", preview, "a current workspace has nothing for the role upgrade to add")
        self.assertNotIn("can be refreshed", preview)
        self.assertNotIn("Obsolete", preview)

    def test_obsidian_autonomy_and_index(self) -> None:
        ws = self.build({"obsidian": False, "autonomy": "hands-off", "index": True})
        self.assertFalse((ws / "knowledge" / ".obsidian").exists())
        text = (ws / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("**Hands-off:**", text)
        self.assertIn("Index mode", text)
        self.assertIn(".pka/knowledge.db", text)
        status = self.status(ws)
        self.assertFalse(status["obsidian_present"])
        self.assertEqual(status["storage_mode"], "index")
        self.assertTrue(status["schema_current"])
        code, out, _ = self.tool(ws, "search", "lighthouse")
        self.assertEqual(code, 0)
        self.assertIn("narrative.md", out)

    def test_legacy_index_needs_migrating(self) -> None:
        status = self.status(self.build({"index": "legacy"}))
        self.assertIs(status["schema_current"], False)
        self.assertEqual(status["schema_version"], 0)

    def test_toolkit_absent_and_old_roles(self) -> None:
        ws = self.build({"toolkit": "absent", "roles": "v1.7.0"})
        self.assertFalse((ws / ".pka" / "bin").exists())
        self.assertFalse((ws / ".pka" / "manifest.json").exists())
        self.assertIsNone(self.status(ws)["vendored_version"])
        roles = ws / ".pka" / "roles"
        self.assertTrue((roles / "_git-protocol.md").is_file())
        self.assertFalse((roles / "_obsidian.md").exists())
        self.assertIn("## Commit/push protocol", (roles / "librarian.md").read_text(encoding="utf-8"))
        preview = self.role_preview(ws)
        self.assertIn("+ _obsidian.md", preview)
        self.assertIn("Obsolete", preview)

    def test_roles_absent(self) -> None:
        self.assertFalse((self.build({"roles": "absent"}) / ".pka" / "roles").exists())

    def test_existing_and_empty_fixtures(self) -> None:
        existing = self.build({"fixture": "existing"}, "existing")
        self.assertEqual(sorted(p.name for p in existing.iterdir()), ["knowledge", "meeting-notes", "projects"])
        self.assertTrue((existing / "knowledge" / ".obsidian").is_dir())
        empty = self.build({"fixture": "empty"}, "empty")
        self.assertEqual(list(empty.iterdir()), [])

    def test_lint_fixture(self) -> None:
        ws = self.build({"fixture": "lint"})
        self.assertIn("wiki-home", (ws / "CLAUDE.md").read_text(encoding="utf-8"))
        self.assertTrue((ws / "team-inbox" / "charter copy.md").is_file())
        code, out, err = self.tool(ws, "lint", "--json")
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertGreater(data["counts"]["8a"], 0)
        self.assertTrue(any("priya-nair" in item["text"] for item in data["items"] if item["rule"] == "8d"))

    def test_steps(self) -> None:
        ws = self.build({"steps": [
            {"write": "team-inbox/note.md", "text": ["# Note", "", "body"]},
            {"write": "team-inbox/raw.bin", "text": "exact"},
            {"append": "team-inbox/note.md", "text": "more\n"},
            {"replace": "team-inbox/note.md", "old": "body", "new": "text"},
            {"copy": "team-inbox/note.md", "to": "knowledge/AI/copied.md"},
            {"mkdir": "knowledge/clients"},
            {"remove": "knowledge/archived"},
            {"remove": "knowledge/AI/build.log"},
            {"age": "projects/orion", "days": 95},
            {"git_repo": "knowledge"},
            {"git_repo": "."},
            {"fixture_file": "dashboard.html", "to": "dashboard.html"},
            {"symlink": "dashboard-data.js", "to": "knowledge/reference/empty.md"},
            {"tool": ["timeline", "plan"]},
            {"tool": ["timeline", "apply", "no-such-plan.json"], "allow_fail": True},
        ]})
        self.assertEqual((ws / "team-inbox" / "note.md").read_text(encoding="utf-8"), "# Note\n\ntext\nmore\n")
        self.assertEqual((ws / "team-inbox" / "raw.bin").read_bytes(), b"exact")
        self.assertEqual((ws / "knowledge" / "AI" / "copied.md").read_text(encoding="utf-8"), "# Note\n\ntext\nmore\n")
        self.assertTrue((ws / "knowledge" / "clients").is_dir())
        self.assertFalse((ws / "knowledge" / "archived").exists())
        self.assertFalse((ws / "knowledge" / "AI" / "build.log").exists())
        age = time.time() - (ws / "projects" / "orion" / "src" / "main.rs").stat().st_mtime
        self.assertGreater(age, 94 * 86400)
        self.assertEqual((ws / "knowledge" / ".git" / "HEAD").read_text(encoding="utf-8"), "ref: refs/heads/main\n")
        self.assertTrue((ws / ".git" / "config").is_file())
        self.assertEqual((ws / "dashboard.html").read_bytes(), (REPO / "evals" / "fixtures" / "dashboard.html").read_bytes())
        self.assertEqual(len(list((ws / ".pka" / "backfill").glob("plan-*.json"))), 1)
        self.assertEqual(os.readlink(str(ws / "dashboard-data.js")), "knowledge/reference/empty.md")

    def test_lint_report_step_is_dated_in_the_past(self) -> None:
        recent = self.build({"steps": [{"lint_report": {"days_ago": 3, "quick": True}}]}, "recent")
        code, out, _ = self.tool(recent, "lint", "latest", "--json")
        latest = json.loads(out)
        self.assertEqual((latest["age_days"], latest["mention"], latest["mode"]), (3, True, "quick"))
        self.assertGreater(latest["findings"], 0)
        self.assertEqual(len(list((recent / "owner-inbox").glob("librarian-lint-*.md"))), 1)
        old = self.build({"steps": [{"lint_report": {"days_ago": 20}}]}, "old")
        latest = json.loads(self.tool(old, "lint", "latest", "--json")[1])
        self.assertEqual((latest["age_days"], latest["mention"], latest["mode"]), (20, False, "full"))

    def test_cwd_must_exist(self) -> None:
        self.build({"cwd": "projects/orion"}, "ok")
        with self.assertRaises(run.RunnerError):
            self.build({"cwd": "projects/nowhere"}, "bad")

    def test_a_step_that_cannot_work_says_why(self) -> None:
        cases = [
            ({"append": "nope.md", "text": "x"}, "cannot append to nope.md"),
            ({"replace": "CLAUDE.md", "old": "not in the file", "new": "x"}, "does not contain the text to replace"),
            ({"remove": "nope.md"}, "cannot remove nope.md"),
            ({"copy": "nope.md", "to": "a.md"}, "cannot copy nope.md"),
            ({"age": "nope.md", "days": 1}, "cannot age nope.md"),
            ({"tool": ["timeline", "apply", "no-such-plan.json"]}, "exited"),
        ]
        for number, (step, expected) in enumerate(cases):
            with self.assertRaises(run.RunnerError) as caught:
                self.build({"steps": [step]}, "ws%d" % number)
            self.assertIn(expected, str(caught.exception))
            self.assertNotIn("\n", str(caught.exception))

    def test_no_step_writes_outside_the_workspace(self) -> None:
        for step in ({"write": "../escaped.md", "text": "x"}, {"write": "/tmp/escaped.md", "text": "x"},
                     {"copy": "CLAUDE.md", "to": "../../escaped.md"}, {"mkdir": "~/escaped"},
                     {"fixture_file": "../run.py", "to": "x"}, {"git_repo": "../.."},
                     {"symlink": "link", "to": "/etc/hostname"}, {"symlink": "../link", "to": "CLAUDE.md"}):
            with self.assertRaises(run.RunnerError):
                self.build({"steps": [step]}, "inner/ws")
        self.assertEqual(sorted(p.name for p in self.base.iterdir()), ["home"])

    def test_every_scenario_builds(self) -> None:
        # Each eval's setup against the real fixture and the real tool: a step that
        # no longer applies fails here, not in a paid run.
        for scenario in run.load_scenarios():
            ws = self.base / "all" / scenario["id"]
            try:
                run.build_workspace(scenario["setup"], ws, self.home)
            except run.RunnerError as exc:
                self.fail("%s: %s" % (scenario["id"], exc))
            run.remove_tree(ws)


# ------------------------------------------------------------------ snapshot and diff

class SnapshotAndDiff(Case):
    def test_diff_reports_added_removed_and_changed(self) -> None:
        start, final = self.base / "start", self.base / "final"
        (final / ".pka" / "bin").mkdir(parents=True)
        for root in (start, final):
            (root / "notes").mkdir(parents=True)
            (root / "notes" / "same.md").write_text("same\n", encoding="utf-8")
            (root / "notes" / "edited.md").write_text("line one\nline two\n", encoding="utf-8")
            (root / "data.bin").write_bytes(b"\x00\x01\x02")
        (start / "notes" / "gone.md").write_text("bye\n", encoding="utf-8")
        (final / "notes" / "edited.md").write_text("line one\nline 2\nline three\n", encoding="utf-8")
        (final / "notes" / "new file.md").write_text("# New\n", encoding="utf-8")
        (final / "data.bin").write_bytes(b"\x00\x01\x02\x03")
        (final / "latin1.md").write_bytes(b"caf\xe9\n")
        (final / ".pka" / "bin" / "pka-tools").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        (final / "empty-folder").mkdir()
        os.symlink("/etc/hostname", str(final / "link"))
        diff = run.diff_workspace(start, final)
        self.assertEqual(diff["added"], [".pka/bin/pka-tools", "empty-folder/", "latin1.md", "link", "notes/new file.md"])
        self.assertEqual(diff["removed"], ["notes/gone.md"])
        self.assertEqual(diff["changed"], ["data.bin", "notes/edited.md"])
        self.assertEqual(diff["vendored"], 1)
        text = diff["text"]
        self.assertIn("-line two", text)
        self.assertIn("+line 2", text)
        self.assertIn("+line three", text)
        self.assertIn("+# New", text)
        self.assertIn("-bye", text)
        self.assertIn("data.bin (changed; not text", text)
        self.assertIn("latin1.md (added; not text", text)
        self.assertNotIn("pka-tools", text, "the vendored toolkit is counted, not shown")
        self.assertEqual(diff["final"]["link"]["link"], "/etc/hostname")
        self.assertEqual(diff["final"]["notes/same.md"]["sha256"], diff["start"]["notes/same.md"]["sha256"])
        self.assertEqual(len(diff["final"]["notes/same.md"]["sha256"]), 64)
        listing = run.listing_text(diff["final"])
        self.assertIn("notes/new file.md", listing)
        self.assertIn(".pka/bin/ (the vendored toolkit, 1 files)", listing)
        self.assertIn("(empty dir)", listing)
        self.assertIn("link -> /etc/hostname", listing)

    def test_an_unchanged_tree_has_no_diff(self) -> None:
        ws = self.build({})
        copy = self.base / "copy"
        shutil.copytree(str(ws), str(copy), symlinks=True)
        diff = run.diff_workspace(ws, copy)
        self.assertEqual((diff["added"], diff["removed"], diff["changed"], diff["text"]), ([], [], [], ""))

    def test_long_diffs_are_cut_with_a_note(self) -> None:
        start, final = self.base / "a", self.base / "b"
        start.mkdir()
        final.mkdir()
        (final / "big.md").write_text("".join("line %d\n" % n for n in range(1000)), encoding="utf-8")
        text = run.diff_workspace(start, final, per_file_lines=50)["text"]
        self.assertIn("more diff line(s) of big.md not shown", text)
        self.assertLess(len(text.split("\n")), 60)


# ------------------------------------------------------------------ transcript capture

def fake_stream(mode: str = "ok", plugin: str = "/plugin", cwd: Path = None, resume: bool = False):
    env = dict(os.environ, FAKE_CLAUDE_MODE=mode)
    env.pop("FAKE_CLAUDE_LOG", None)
    argv = [sys.executable, str(FAKE), "-p", "--output-format", "stream-json", "--plugin-dir", plugin,
            "--tools", run.SUBJECT_TOOLS, "--permission-mode", "dontAsk"] + (["--resume", "x"] if resume else [])
    proc = subprocess.run(argv, input="Quick lint.", cwd=str(cwd) if cwd else None, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return proc.stdout.splitlines(True)


class Transcript(Case):
    def test_stream_becomes_events(self) -> None:
        events, result, init = run.parse_stream(fake_stream(cwd=self.base))
        self.assertEqual([e["kind"] for e in events],
                         ["assistant_text", "tool_call", "tool_result", "injected", "tool_call", "tool_result",
                          "tool_call", "tool_result", "tool_call", "tool_result", "assistant_text"])
        calls = [e for e in events if e["kind"] == "tool_call"]
        self.assertEqual([c["name"] for c in calls], ["Skill", "Read", "Bash", "Bash"])
        self.assertEqual(calls[2]["input"], {"command": "python3 .pka/bin/pka-tools lint --quick --json"})
        self.assertEqual(events[7]["id"], calls[2]["id"])
        self.assertEqual(init["model"], "fake-model")
        self.assertEqual(result["total_cost_usd"], 0.0421)
        metrics = run.turn_metrics(result, None, 0)
        self.assertEqual(metrics["usage"], {"input_tokens": 120, "output_tokens": 45, "cache_read_input_tokens": 3000,
                                            "cache_creation_input_tokens": 800})
        self.assertEqual(metrics["permission_denials"][0]["tool_input"], {"command": "git status"})
        self.assertFalse(metrics["is_error"])
        self.assertEqual(run.count_turns(fake_stream(cwd=self.base)), 4)

    def test_a_recorded_failure_parses(self) -> None:
        events, result, init = run.parse_stream(sample("stream-auth-failed.jsonl").splitlines(True))
        self.assertEqual(init["tools"], ["Bash", "Edit", "Glob", "Grep", "Read", "Skill", "Write"])
        self.assertEqual(init["permissionMode"], "dontAsk")
        self.assertEqual(init["mcp_servers"], [])
        self.assertEqual([p["name"] for p in init["plugins"]], ["pka-skills"])
        self.assertTrue(result["is_error"])
        self.assertTrue(run.looks_like_auth_failure(result["result"]))
        self.assertEqual(run.turn_metrics(result, None, 1)["cost_usd"], 0.0)
        envelope = json.loads(sample("result-auth-failed.json"))
        self.assertTrue(run.looks_like_auth_failure(envelope["result"]))

    def test_lines_that_are_not_events_are_ignored(self) -> None:
        events, result, init = run.parse_stream(["not json\n", "\n", "[1, 2]\n", '{"type": "assistant"}\n',
                                                 '{"type": "assistant", "parent_tool_use_id": "t1", "message": '
                                                 '{"content": [{"type": "text", "text": "from a subagent"}]}}\n'])
        self.assertEqual((events, result, init), ([], None, {}))
        self.assertTrue(run.turn_metrics(None, "timeout", -9)["is_error"])

    def test_the_judge_never_sees_skill_text(self) -> None:
        plugin = self.base / "plugin"
        events, result, _ = run.parse_stream(fake_stream(plugin=str(plugin), cwd=self.base))
        turns = [{"prompt": "Quick lint.", "events": events, "metrics": run.turn_metrics(result, None, 0)}]
        text = run.render_transcript(turns, plugin)
        self.assertNotIn("SECRET-SKILL-TEXT", text)
        self.assertIn("=== USER MESSAGE 1 ===\nQuick lint.", text)
        self.assertEqual(text.count("[withheld:"), 3, text)       # the Skill result, the injected body, the reference read
        self.assertIn('TOOL CALL Bash: {"command": "python3 .pka/bin/pka-tools lint --quick --json"}', text)
        self.assertIn('{"findings": 2, "report": "owner-inbox/fake-report.md"}', text)
        self.assertIn("1.10.0 from the plugin copy", text, "output of the plugin's own tool is evidence, not skill text")
        self.assertIn("ASSISTANT SAYS:\nRan the quick lint: 2 findings.", text)
        self.assertIn('the harness denied: Bash {"command": "git status"}', text)

    def test_reading_a_plugin_file_through_the_shell_is_withheld_too(self) -> None:
        plugin = "/run/plugin"
        yes = [{"name": "Skill", "input": {"skill": "x"}},
               {"name": "Read", "input": {"file_path": plugin + "/skills/pka-wiki/SKILL.md"}},
               {"name": "Grep", "input": {"pattern": "lint", "path": plugin}},
               {"name": "Bash", "input": {"command": "cat %s/CHANGELOG.md" % plugin}},
               {"name": "Bash", "input": {"command": "python3 %s/bootstrap-assets/tools/pka-tools status | head -3; "
                                                     "grep -n x %s/skills/pka-wiki/SKILL.md" % (plugin, plugin)}},
               {"name": "Bash", "input": {"command": "ls %s/skills" % plugin}}]
        no = [{"name": "Read", "input": {"file_path": "/ws/CLAUDE.md"}},
              {"name": "Bash", "input": {"command": 'python3 "%s/bootstrap-assets/tools/pka-tools" status --workspace . --json' % plugin}},
              {"name": "Bash", "input": {"command": "python3 %s/bootstrap-assets/scripts/upgrade-roles.py --workspace . --dry-run" % plugin}},
              {"name": "Bash", "input": {"command": "python3 .pka/bin/pka-tools lint"}}]
        for call in yes:
            self.assertTrue(run._reads_plugin_text(call, plugin), call)
        for call in no:
            self.assertFalse(run._reads_plugin_text(call, plugin), call)

    def test_long_output_is_clipped(self) -> None:
        events = [{"kind": "tool_call", "id": "t", "name": "Bash", "input": {"command": "cat big"}},
                  {"kind": "tool_result", "id": "t", "text": "A" * 5000 + "MIDDLE" + "Z" * 5000, "is_error": False}]
        text = run.render_transcript([{"prompt": "p", "events": events, "metrics": run.turn_metrics(None, "turn-cap", -9)}],
                                     Path("/plugin"))
        self.assertIn("characters not shown", text)
        self.assertNotIn("MIDDLE", text)
        self.assertIn("the runner stopped this turn early (turn-cap)", text)


# ------------------------------------------------------------------ the judge's answer

EXPECT = ["runs the quick lint", "reports the number of findings", "edits no note"]
EVIDENCE = ('[3] TOOL CALL Bash: {"command": "python3 .pka/bin/pka-tools lint --quick --json"}\n'
            "[5] ASSISTANT SAYS:\nRan the quick   lint:\n2 findings.\n")


class JudgeParser(unittest.TestCase):
    def test_structured_output(self) -> None:
        got = run.parse_judge_response(sample("judge-structured.json"), EXPECT, EVIDENCE)
        self.assertEqual((got["verdict"], got["met"], got["total"]), ("pass", 3, 3))
        self.assertEqual([g["met"] for g in got["expectations"]], ["yes", "yes", "yes"])
        self.assertEqual(got["expectations"][0]["expectation"], "runs the quick lint")
        self.assertEqual(got["expectations"][1]["quotes_found"], [True], "whitespace differences do not matter")
        self.assertEqual(got["expectations"][2]["basis"], "absence")
        self.assertEqual(got["cost_usd"], 0.0312)
        self.assertEqual(got["usage"]["input_tokens"], 5120)

    def test_answer_inside_prose_or_a_fence(self) -> None:
        got = run.parse_judge_response(sample("judge-fenced-text.json"), EXPECT, EVIDENCE)
        self.assertEqual(got["verdict"], "pass")
        bare = json.dumps(json.loads(sample("judge-structured.json"))["structured_output"])
        self.assertEqual(run.parse_judge_response(bare, EXPECT, EVIDENCE)["verdict"], "pass")
        self.assertEqual(run.parse_judge_response("Sure. " + bare + " Hope that helps.", EXPECT, EVIDENCE)["met"], 3)

    def test_a_claim_without_evidence_is_thrown_out(self) -> None:
        got = run.parse_judge_response(sample("judge-unverified-claim.json"), EXPECT, EVIDENCE)
        first, second, third = got["expectations"]
        self.assertEqual(first["met"], "unverifiable")
        self.assertIn("none of its quotes is in the evidence", first["downgraded"])
        self.assertEqual(first["quotes_found"], [False])
        self.assertEqual(second["met"], "no")
        self.assertEqual(third["met"], "unverifiable")
        self.assertEqual(third["downgraded"], "no answer")
        self.assertEqual(got["judge_verdict"], "pass")
        self.assertEqual(got["verdict"], "fail", "the runner works the verdict out itself")

    def test_yes_needs_a_quote_unless_it_is_an_absence(self) -> None:
        def answer(**item):
            base = {"index": 1, "met": "yes", "basis": "quote", "quotes": [], "reason": "r"}
            base.update(item)
            return json.dumps({"expectations": [base], "verdict": "pass", "summary": ""})
        parse = lambda text: run.parse_judge_response(text, ["one"], EVIDENCE)["expectations"][0]
        self.assertEqual(parse(answer())["met"], "unverifiable")
        self.assertEqual(parse(answer(quotes=["lint"]))["met"], "unverifiable", "a quote of a few letters proves nothing")
        self.assertEqual(parse(answer(quotes=["2 findings."]))["met"], "yes")
        self.assertEqual(parse(answer(basis="absence"))["met"], "yes")
        self.assertEqual(parse(answer(met="probably"))["met"], "unverifiable")
        self.assertEqual(parse(answer(met="no"))["met"], "no")
        self.assertEqual(parse(answer(index="1", quotes=["2 findings."]))["met"], "yes")
        extra = json.dumps({"expectations": [{"index": 7, "met": "yes", "basis": "absence", "quotes": [], "reason": ""},
                                             "junk", {"met": "yes"}], "verdict": "pass", "summary": ""})
        self.assertEqual(parse(extra)["met"], "unverifiable")

    def test_no_usable_answer(self) -> None:
        for text in (sample("judge-no-json.json"), "", "   ", "{}", '{"expectations": "none"}', "not json at all"):
            with self.assertRaises(run.JudgeError):
                run.parse_judge_response(text, EXPECT, EVIDENCE)
        with self.assertRaises(run.JudgeError) as caught:
            run.parse_judge_response(sample("judge-budget-error.json"), EXPECT, EVIDENCE)
        self.assertIn("Reached maximum budget", str(caught.exception))
        with self.assertRaises(run.AuthError):
            run.parse_judge_response(sample("result-auth-failed.json"), EXPECT, EVIDENCE)

    def test_verdict_thresholds(self) -> None:
        self.assertEqual([run.verdict_for(m, 4) for m in range(5)], ["fail", "fail", "partial", "partial", "pass"])
        self.assertEqual([run.verdict_for(m, 3) for m in range(4)], ["fail", "fail", "partial", "pass"])
        self.assertEqual(run.verdict_for(1, 1), "pass")
        self.assertEqual(run.verdict_for(0, 0), "fail")

    def test_the_judge_is_told_to_distrust_claims(self) -> None:
        for phrase in ("A claim is not evidence", "there is no tool call or file change", "unverifiable",
                       "Never give the benefit of the doubt", "You have not seen the assistant's instructions",
                       "checked mechanically"):
            self.assertIn(phrase, run.JUDGE_SYSTEM)


# ------------------------------------------------------------------ aggregation

def record(ident, skill, verdict, met, total, cost=0.1, status="graded", **extra):
    items = [{"index": n, "expectation": "expectation %d of %s" % (n, ident), "met": "yes" if n <= met else "no",
              "basis": "quote", "quotes": ["evidence | with a bar"] if n > met else [], "quotes_found": [True] if n > met else [],
              "reason": "because", "downgraded": None} for n in range(1, total + 1)]
    out = {"id": ident, "skill": skill, "status": status, "verdict": verdict, "met": met, "total": total,
           "cost_usd": cost, "subject_cost_usd": cost * 0.8, "judge_cost_usd": cost * 0.2, "wall_seconds": 30.0,
           "tokens": {"input_tokens": 100, "output_tokens": 50, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 10},
           "judge_tokens": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
           "turns": [{"num_turns": 4}, {"num_turns": 2}], "error": None,
           "judgement": {"expectations": items, "summary": "summary of %s" % ident}}
    out.update(extra)
    return out


class Aggregation(Case):
    RECORDS = [record("wiki-a", "pka-wiki", "pass", 3, 3), record("wiki-b", "pka-wiki", "partial", 2, 4, cost=0.25),
               record("librarian-a", "pka-librarian", "fail", 0, 2),
               record("librarian-b", "pka-librarian", None, 0, 3, cost=0.05, status="judge-error",
                      error="the judge printed nothing", judgement=None)]

    def test_totals(self) -> None:
        summary = run.summarise(self.RECORDS)
        totals = summary["totals"]
        self.assertEqual((totals["scenarios"], totals["graded"], totals["pass"], totals["partial"], totals["fail"], totals["error"]),
                         (4, 3, 1, 1, 1, 1))
        self.assertEqual(totals["cost_usd"], 0.5)
        self.assertEqual((totals["expectations_met"], totals["expectations"]), (5, 9))
        self.assertEqual(totals["tokens"]["input_tokens"], 440)
        self.assertEqual(totals["wall_seconds"], 120.0)
        self.assertEqual(list(summary["by_skill"]), ["pka-librarian", "pka-wiki"])
        self.assertEqual(summary["by_skill"]["pka-wiki"], {"scenarios": 2, "pass": 1, "partial": 1, "fail": 0, "error": 0,
                                                           "cost_usd": 0.35})

    def test_summary_table_and_evidence(self) -> None:
        text = run.render_summary(self.RECORDS, {"name": "20261120", "plugin_version": "1.10.0", "model": "m", "judge_model": "j",
                                                 "sandbox": "require", "home": "scratch"})
        self.assertIn("- Verdicts: 1 pass, 1 partial, 1 fail; expectations met: 5 of 9", text)
        self.assertIn("- Cost as reported by the CLI: $0.5000", text)
        self.assertIn("| wiki-b | pka-wiki | partial | 2/4 | 6 | $0.2500 | 30 | 3. expectation 3 of wiki-b (no) |", text)
        self.assertIn("| librarian-b | pka-librarian | judge-error | 0/3 |", text)
        self.assertIn("## wiki-b — partial (2/4)", text)
        self.assertIn("- **3. expectation 3 of wiki-b** — no. because", text)
        self.assertIn("  - Evidence: `evidence | with a bar`", text)
        self.assertIn("## librarian-b — judge-error", text)
        self.assertNotIn("## wiki-a", text, "a pass needs no detail")
        self.assertEqual(run.first_unmet(self.RECORDS[0]), "")

    def test_results_round_trip(self) -> None:
        results = self.base / "results"
        for item in self.RECORDS:
            run.write_result(results, item)
        (results / "raw").mkdir()
        (results / "raw" / "wiki-a.judge.json").write_text("{}", encoding="utf-8")
        (results / "pka-wiki" / "broken.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(sorted(r["id"] for r in run.read_results(results)), ["librarian-a", "librarian-b", "wiki-a", "wiki-b"])
        summary, text = run.write_summary(results, {"name": "x"})
        self.assertEqual(json.loads((results / "summary.json").read_text(encoding="utf-8"))["totals"]["pass"], 1)
        self.assertEqual((results / "summary.md").read_text(encoding="utf-8"), text)


# ------------------------------------------------------------------ the commands

class Commands(Case):
    CFG = {"claude": "claude", "model": "sonnet", "judge_model": "opus", "max_turns": 12, "max_usd": 0.75,
           "judge_max_usd": 0.2, "home": "scratch", "config_dir": "/cfg"}

    def test_subject_command(self) -> None:
        cmd = run.subject_command(self.CFG, Path("/run/plugin"), Path("/run/s/settings.json"), None, False)
        text = " ".join(cmd)
        for part in ("-p", "--output-format stream-json", "--plugin-dir /run/plugin", "--model sonnet",
                     "--setting-sources project", "--strict-mcp-config", "--tools Bash,Read,Edit,Write,Glob,Grep,Skill",
                     "--permission-mode dontAsk", "--permission-prompts none", "--settings /run/s/settings.json",
                     "--max-turns 12", "--max-budget-usd 0.75", "--no-session-persistence"):
            self.assertIn(part, text)
        for never in ("bypassPermissions", "dangerously", "--add-dir", "acceptEdits", str(run.REPO)):
            self.assertNotIn(never, text)
        first = run.subject_command(self.CFG, Path("/p"), Path("/s"), "abc", False)
        later = run.subject_command(self.CFG, Path("/p"), Path("/s"), "abc", True)
        self.assertEqual(first[-2:], ["--session-id", "abc"])
        self.assertEqual(later[-2:], ["--resume", "abc"])
        self.assertNotIn("--no-session-persistence", first + later)

    def test_judge_command_has_no_tools_and_no_plugin(self) -> None:
        cmd = run.judge_command(self.CFG)
        self.assertEqual(cmd[cmd.index("--tools") + 1], "")
        self.assertEqual(cmd[cmd.index("--model") + 1], "opus")
        self.assertEqual(cmd[cmd.index("--setting-sources") + 1], "")
        self.assertNotIn("--plugin-dir", cmd)
        self.assertIn("--disable-slash-commands", cmd)
        self.assertEqual(json.loads(cmd[cmd.index("--json-schema") + 1])["required"], ["expectations", "verdict", "summary"])
        line = run.shell_line(cmd)
        self.assertIn("'<judge instructions,", line)
        self.assertNotIn("A claim is not evidence", line)

    def test_permission_rules(self) -> None:
        ws, plugin = Path("/run/s/ws"), Path("/run/plugin")
        off = run.subject_settings(ws, plugin, sandbox=False)
        rules = off["permissions"]["allow"]
        self.assertNotIn("sandbox", off)
        self.assertIn("Read(//run/s/ws/**)", rules)
        self.assertIn("Read(//run/plugin/**)", rules)
        self.assertIn("Edit(//run/s/ws/**)", rules)
        self.assertNotIn("Edit(//run/plugin/**)", rules)
        self.assertIn("Bash(python3 .pka/bin/pka-tools *)", rules)
        self.assertIn('Bash(python3 "/run/plugin/bootstrap-assets/tools/pka-tools" *)', rules)
        self.assertIn("Bash(python3 /run/plugin/bootstrap-assets/scripts/upgrade-roles.py *)", rules)
        self.assertIn("Bash(mv *)", rules)
        self.assertNotIn("Bash(rm *)", rules)
        joined = "\n".join(rules)
        for never in ("git", "curl", "wget", "pip", "ssh", "sudo", "Bash(*)", "Bash(python3 *)", "Bash(sh ", "Bash(bash",
                      "WebFetch", "Write(", "find"):
            self.assertNotIn(never, joined)
        self.assertTrue(all(rule.startswith(("Read(", "Edit(", "Bash(")) or rule in ("Glob", "Grep", "Skill") for rule in rules))
        on = run.subject_settings(ws, plugin, sandbox=True)
        self.assertIn("Bash(rm *)", on["permissions"]["allow"])
        self.assertEqual(on["sandbox"], {"enabled": True, "failIfUnavailable": True, "allowUnsandboxedCommands": False,
                                         "autoAllowBashIfSandboxed": False, "network": {"allowedDomains": []}})

    SECRETS = {"GH_TOKEN": "gh-secret", "GITHUB_TOKEN": "gh-secret", "AWS_SECRET_ACCESS_KEY": "aws-secret",
               "AWS_ACCESS_KEY_ID": "aws-id", "GOOGLE_APPLICATION_CREDENTIALS": "/creds.json",
               "SSH_AUTH_SOCK": "/tmp/agent.sock", "OPENAI_API_KEY": "other-secret", "NPM_TOKEN": "npm-secret",
               "CLAUDE_CODE_SESSION_ID": "parent", "CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "cli",
               "GIT_AUTHOR_NAME": "someone", "OLDPWD": str(REPO), "PWD": str(REPO), "XDG_CONFIG_HOME": "/xdg",
               "ANTHROPIC_CUSTOM_HEADERS": "x-secret: 1", "HTTPS_PROXY": "http://user:pw@proxy.example.com",
               "USER": "sam", "SHELL": "/bin/zsh", "PKA_DIR": "/home/sam/notes"}

    def test_child_environment_is_built_from_a_list(self) -> None:
        for name in [key for key in os.environ if key.startswith("LC_")]:
            del os.environ[name]
        os.environ.update(self.SECRETS)
        os.environ.update({"CLAUDE_CONFIG_DIR": "/elsewhere", "LANG": "en_GB.UTF-8", "LC_TIME": "de_DE.UTF-8",
                           "TERM": "xterm", "TZ": "Europe/Zurich", "ANTHROPIC_API_KEY": "key",
                           "ANTHROPIC_AUTH_TOKEN": "bearer", "ANTHROPIC_BASE_URL": "https://gateway.example.com",
                           "CLAUDE_CODE_OAUTH_TOKEN": "oauth"})
        env = run.child_env(self.CFG, Path("/run/s/home"), Path("/run/s/tmp"), Path("/run/s/ws/projects/orion"))
        self.assertEqual(sorted(env), sorted([
            "PATH", "LANG", "LC_TIME", "TERM", "TZ", "HOME", "TMPDIR", "PWD", "CLAUDE_CONFIG_DIR",
            "PYTHONDONTWRITEBYTECODE", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM",
            "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_OAUTH_TOKEN"]))
        for name in self.SECRETS:
            if name != "PWD":
                self.assertNotIn(name, env)
        self.assertEqual(env["CLAUDE_CONFIG_DIR"], "/cfg")
        self.assertEqual((env["HOME"], env["TMPDIR"]), ("/run/s/home", "/run/s/tmp"))
        self.assertEqual(env["PWD"], "/run/s/ws/projects/orion", "PWD is the folder the call starts in, not the checkout")
        self.assertEqual(env["GIT_CONFIG_GLOBAL"], "/run/s/home/.gitconfig")
        self.assertEqual(env["CLAUDE_CODE_OAUTH_TOKEN"], "oauth", "a token login is passed, though it starts with CLAUDE")
        self.assertNotIn(str(REPO), json.dumps(env), "nothing in the environment names the checkout")
        real = run.child_env(dict(self.CFG, home="real"), Path("/h"), Path("/t"), Path("/w"))
        self.assertEqual(real["HOME"], self._env["HOME"])
        self.assertEqual((real["TMPDIR"], real["PWD"]), ("/t", "/w"))
        self.assertNotIn("GH_TOKEN", real)

    def test_login_variables_that_are_not_set_are_not_invented(self) -> None:
        for name in run.AUTH_ENV:
            os.environ.pop(name, None)
        env = run.child_env(self.CFG, Path("/h"), Path("/t"), Path("/w"))
        self.assertFalse([name for name in run.AUTH_ENV if name in env])

    def test_a_variable_reaches_the_child_only_when_named(self) -> None:
        os.environ.update({"HTTPS_PROXY": "http://proxy.example.com", "GH_TOKEN": "gh-secret"})
        env = run.child_env(dict(self.CFG, pass_env=["HTTPS_PROXY", "NOT_SET_ANYWHERE"]), Path("/h"), Path("/t"), Path("/w"))
        self.assertEqual(env["HTTPS_PROXY"], "http://proxy.example.com")
        self.assertNotIn("GH_TOKEN", env)
        self.assertNotIn("NOT_SET_ANYWHERE", env)

    def test_setup_steps_get_no_secrets_either(self) -> None:
        os.environ.update(self.SECRETS)
        os.environ["ANTHROPIC_API_KEY"] = "key"
        env = run.tool_env(Path("/run/s/home"))
        for name in list(self.SECRETS) + ["ANTHROPIC_API_KEY"]:
            self.assertNotIn(name, env)
        self.assertEqual(env["HOME"], "/run/s/home")

    def test_the_plugin_copy_is_read_only_and_holds_no_answers(self) -> None:
        plugin = run.prepare_plugin(self.base)
        names = sorted(p.name for p in plugin.iterdir())
        self.assertEqual(names, [".claude-plugin", "CHANGELOG.md", "bootstrap-assets", "skills"])
        skill = plugin / "skills" / "pka-wiki" / "SKILL.md"
        self.assertFalse(skill.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
        before = run.tree_digest(plugin)
        os.chmod(str(skill), 0o644)
        skill.write_text("changed", encoding="utf-8")
        self.assertNotEqual(run.tree_digest(plugin), before)

    def test_the_plugin_copy_matches_what_git_tracks(self) -> None:
        plugin = run.prepare_plugin(self.base)
        copied = sorted(rel for rel, info in run.snapshot(plugin).items() if not info.get("dir"))
        proc = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z", "--", ".claude-plugin", "skills",
                               "bootstrap-assets", "CHANGELOG.md"], stdout=subprocess.PIPE, check=True)
        tracked = sorted(name for name in proc.stdout.decode("utf-8").split("\0")
                         if name and (REPO / name).is_file() and not (REPO / name).is_symlink())
        self.assertEqual(copied, tracked)
        self.assertTrue((plugin / "skills" / "pka-tutorial" / "SKILL.md").is_file())
        self.assertTrue((plugin / "bootstrap-assets" / "tools" / "pka_tools" / "cli.py").is_file())

    def checkout(self, tracked: bool) -> Path:
        """A small stand-in checkout, with files that must never reach a subject."""
        repo = self.base / "checkout"
        files = {
            ".claude-plugin/plugin.json": '{"name": "pka-skills", "version": "0.0.0"}\n',
            "skills/pka-wiki/SKILL.md": "# the skill\n",
            "bootstrap-assets/tools/pka-tools": "#!/usr/bin/env python3\n",
            "CHANGELOG.md": "# Changelog\n",
            "README.md": "# readme\n",
            "docs/index.html": "<p>the site</p>\n",
            "evals/pka-wiki.evals.json": "[]\n",
            "tests/test_tools.sh": "#!/bin/sh\n",
        }
        for rel, text in files.items():
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text(text, encoding="utf-8")
        if tracked:
            env = dict(os.environ, HOME=str(self.home), GIT_CONFIG_GLOBAL=str(self.home / ".gitconfig"),
                       GIT_CONFIG_NOSYSTEM="1")
            subprocess.run(["git", "init", "-q", str(repo)], env=env, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "-C", str(repo), "add", "--", "."], env=env, check=True)
        # What a working checkout also holds: none of this is tracked.
        for rel in ("docs/private-plan.md", "skills/untracked-notes.md", "skills/pka-wiki/draft.md", "PRIVATE.md",
                    "bootstrap-assets/tools/__pycache__/x.pyc", "pka-bench/results.json", ".claude-plugin/secret.json"):
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text("PRIVATE-TEXT\n", encoding="utf-8")
        os.symlink(str(repo / "docs" / "private-plan.md"), str(repo / "skills" / "link-to-plan.md"))
        return repo

    def copied(self, plugin: Path):
        return sorted(rel for rel, info in run.snapshot(plugin).items() if not info.get("dir"))

    def test_an_untracked_file_never_reaches_the_plugin_copy(self) -> None:
        repo = self.checkout(tracked=True)
        plugin = run.prepare_plugin(self.base / "run", repo)
        self.assertEqual(self.copied(plugin), [".claude-plugin/plugin.json", "CHANGELOG.md",
                                               "bootstrap-assets/tools/pka-tools", "skills/pka-wiki/SKILL.md"])
        for path in plugin.rglob("*"):
            if path.is_file() and not path.is_symlink():
                self.assertNotIn("PRIVATE-TEXT", path.read_text(encoding="utf-8"), path)
        # A tracked file is copied as it is in the working tree; one removed from it is left out.
        os.chmod(str(repo / "skills" / "pka-wiki" / "SKILL.md"), 0o644)
        (repo / "skills" / "pka-wiki" / "SKILL.md").write_text("# edited, not committed\n", encoding="utf-8")
        (repo / "CHANGELOG.md").unlink()
        again = run.prepare_plugin(self.base / "run2", repo)
        self.assertEqual((again / "skills" / "pka-wiki" / "SKILL.md").read_text(encoding="utf-8"), "# edited, not committed\n")
        self.assertFalse((again / "CHANGELOG.md").exists())

    def test_outside_git_only_the_named_parts_are_copied(self) -> None:
        repo = self.checkout(tracked=False)
        plugin = run.prepare_plugin(self.base / "run", repo)
        copied = self.copied(plugin)
        self.assertIn("skills/pka-wiki/SKILL.md", copied)
        self.assertIn("CHANGELOG.md", copied)
        for rel in copied:
            self.assertIn(rel.split("/")[0], (".claude-plugin", "skills", "bootstrap-assets", "CHANGELOG.md"), rel)
            self.assertNotIn("__pycache__", rel)
        self.assertNotIn("skills/link-to-plan.md", copied, "a symbolic link is not followed out of the parts")
        for name in ("docs", "evals", "tests", "pka-bench", "README.md", "PRIVATE.md"):
            self.assertFalse((plugin / name).exists(), name)

    def test_a_path_outside_the_parts_is_refused(self) -> None:
        for rel in ("docs/v1.7-plan.md", "docs/index.html", "evals/pka-wiki.evals.json", "tests/lib.sh", "README.md",
                    "PRIVATE.md", "pka-bench/x.json", "../outside.md", "/etc/hostname", "skills/../docs/x.md",
                    ".git/config", "skills", "", "skills//x.md", "skills/__pycache__/x.pyc", "x/skills/SKILL.md"):
            self.assertFalse(run.plugin_path_allowed(rel), rel)
        for rel in ("skills/pka-wiki/SKILL.md", "bootstrap-assets/tools/pka_tools/cli.py", ".claude-plugin/plugin.json",
                    "CHANGELOG.md", "skills/pka-interface/references/docs/x.md"):
            self.assertTrue(run.plugin_path_allowed(rel), rel)
        original = run.tracked_files
        run.tracked_files = lambda repo: ["skills/pka-wiki/SKILL.md", "docs/private-plan.md"]
        try:
            with self.assertRaises(run.RunnerError) as caught:
                run.plugin_files(REPO)
        finally:
            run.tracked_files = original
        self.assertIn("refusing to copy 'docs/private-plan.md'", str(caught.exception))

    def test_a_checkout_whose_files_git_cannot_list_is_an_error_not_a_guess(self) -> None:
        repo = self.checkout(tracked=False)
        (repo / ".git").write_text("gitdir: /nowhere/at/all\n", encoding="utf-8")
        with self.assertRaises(run.RunnerError) as caught:
            run.prepare_plugin(self.base / "run", repo)
        self.assertIn("cannot list the tracked files", str(caught.exception))
        self.assertNotIn("\n", str(caught.exception))
        self.assertFalse((self.base / "run" / "plugin" / "skills").exists())

    def test_nothing_in_the_plugin_copy_can_be_changed_without_a_chmod(self) -> None:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root ignores permission bits")
        plugins = run.PluginCopies(self.base)
        copy = plugins.copy_for(self.base / "one")
        self.assertEqual(run.tree_digest(copy), plugins.digest)
        skill = copy / "skills" / "pka-wiki"
        for attempt in (lambda: (skill / "SKILL.md").write_text("tampered", encoding="utf-8"),
                        lambda: os.rename(str(skill / "SKILL.md"), str(skill / "x")),
                        lambda: (skill / "SKILL.md").unlink(),
                        lambda: (skill / "new.md").write_text("added", encoding="utf-8"),
                        lambda: os.rename(str(skill), str(copy / "skills" / "moved")),
                        lambda: (copy / "extra.md").write_text("added", encoding="utf-8")):
            with self.assertRaises(OSError):
                attempt()
        self.assertTrue(plugins.unchanged(copy))
        self.assertEqual(plugins.rebuilt, 0)

    def test_a_changed_copy_is_noticed_and_the_next_one_is_fresh(self) -> None:
        plugins = run.PluginCopies(self.base)
        copy = plugins.copy_for(self.base / "one")
        skill = copy / "skills" / "pka-wiki"
        os.chmod(str(skill), 0o755)
        os.rename(str(skill / "SKILL.md"), str(skill / "x"))
        (skill / "SKILL.md").write_text("tampered\n", encoding="utf-8")
        self.assertFalse(plugins.unchanged(copy))
        fresh = plugins.copy_for(self.base / "two")
        self.assertTrue(plugins.unchanged(fresh))
        self.assertNotEqual((fresh / "skills" / "pka-wiki" / "SKILL.md").read_text(encoding="utf-8"), "tampered\n")
        # The run's own copy is never given out; if it is changed all the same, it is rebuilt.
        os.chmod(str(plugins.master / "skills" / "pka-wiki"), 0o755)
        os.chmod(str(plugins.master / "skills" / "pka-wiki" / "SKILL.md"), 0o644)
        (plugins.master / "skills" / "pka-wiki" / "SKILL.md").write_text("tampered\n", encoding="utf-8")
        self.assertFalse(plugins.unchanged(fresh), "a scenario during which the run's copy changed is not trusted")
        self.assertEqual(plugins.rebuilt, 1)
        third = plugins.copy_for(self.base / "three")
        self.assertTrue(plugins.unchanged(third))
        self.assertNotEqual((third / "skills" / "pka-wiki" / "SKILL.md").read_text(encoding="utf-8"), "tampered\n")

    def test_the_runner_is_standard_library_only_and_never_runs_git(self) -> None:
        source = (REPO / "evals" / "run.py").read_text(encoding="utf-8")
        import ast
        allowed = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else None
        for node in ast.walk(ast.parse(source)):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [(node.module or "").split(".")[0]]
            for name in names:
                self.assertNotIn(name, ("urllib", "http", "socket", "requests", "ssl", "ftplib", "smtplib"))
                if allowed is not None:
                    self.assertIn(name, allowed | {"__future__"})
        # One git command, and it only reads: the list of tracked files for the plugin copy.
        self.assertEqual(source.count('"ls-files"'), 1)
        self.assertEqual(len(re.findall(r"\[git,", source)), 1)
        self.assertNotIn('["git"', source)
        self.assertNotIn("'git'", source)
        for verb in ("commit", "push", "add", "reset", "checkout", "stash", "clean", "config", "clone", "fetch", "pull"):
            self.assertNotRegex(source, r"""\[git,[^\]]*["']%s["']""" % verb)
        compile(source, "run.py", "exec", flags=0, dont_inherit=True, optimize=0)


# ------------------------------------------------------------------ whole runs, with the fake CLI

class Runs(Case):
    def setUp(self) -> None:
        super().setUp()
        self.shim = self.base / "bin" / "claude"
        self.shim.parent.mkdir()
        self.log = self.base / "calls.jsonl"
        self.work = self.base / "work"
        self.work.mkdir()
        self.results = self.base / "results"
        self.config = self.base / "claude-config"
        (self.config / "projects").mkdir(parents=True)
        for key in list(os.environ):
            if key.startswith(("FAKE_", "PKA_EVAL")):
                del os.environ[key]
        os.environ.update({"FAKE_CLAUDE_LOG": str(self.log), "CLAUDE_CONFIG_DIR": str(self.config),
                           "CLAUDE_CODE_SESSION_ID": "the-parent-session"})
        self.write_shim()

    def write_shim(self) -> None:
        """The stand-in CLI. The runner builds the child's environment from a
        list, so the FAKE_* settings of a test cannot travel through it: they
        are written into the shim instead."""
        settings = "".join("export %s=%s\n" % (key, shlex.quote(value)) for key, value in sorted(os.environ.items())
                           if key.startswith("FAKE_"))
        self.shim.write_text('#!/bin/sh\n%sexec "%s" "%s" "$@"\n' % (settings, sys.executable, FAKE), encoding="utf-8")
        os.chmod(str(self.shim), 0o755)

    def go(self, *args: str, sandbox: str = "off"):
        self.write_shim()
        out, err = io.StringIO(), io.StringIO()
        argv = list(args) + ["--claude", str(self.shim), "--work-dir", str(self.work), "--sandbox", sandbox]
        stderr, sys.stderr = sys.stderr, err
        try:
            code = run.main(argv, out)
        finally:
            sys.stderr = stderr
        return code, out.getvalue(), err.getvalue()

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def result(self, skill: str, ident: str) -> dict:
        return json.loads((self.results / skill / (ident + ".json")).read_text(encoding="utf-8"))

    def test_dry_run_builds_and_prints_and_calls_nothing(self) -> None:
        code, out, err = self.go("--dry-run", "--scenario", "librarian-quick-lint", "--scenario", "wiki-retire", sandbox="require")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(self.calls(), [], "a dry run must not start the CLI")
        self.assertIn("Dry run: 2 scenario(s)", out)
        self.assertIn("librarian-quick-lint  (pka-librarian; 4 expectation(s); 1 user message(s))", out)
        self.assertIn("wiki-retire  (pka-wiki; 5 expectation(s); 2 user message(s))", out)
        self.assertIn("--permission-mode dontAsk", out)
        self.assertIn("--no-session-persistence", out)
        self.assertIn("--resume ", out)
        self.assertIn("message 2: Yes, retire it.", out)
        self.assertIn("judge:     ", out)
        self.assertIn("OS sandbox  required", out)
        self.assertIn("2 scenario(s) prepared, 0 failed to set up.", out)
        self.assertEqual(list(self.work.iterdir()), [], "the scratch workspaces are removed")
        self.assertFalse(self.results.exists())

    def test_dry_run_can_keep_the_workspaces(self) -> None:
        with waiting("interface-old-dashboard-migration"):
            code, out, _ = self.go("--dry-run", "--scenario", "interface-old-dashboard-migration", "--keep-workspaces")
        self.assertEqual(code, 0)
        self.assertIn("OS sandbox  OFF", out)
        self.assertIn("needs PR #99", out, "a dry run prepares the waiting scenarios too, and says what they wait for")
        kept = list(self.work.glob("pka-evals.*/interface-old-dashboard-migration"))
        self.assertEqual(len(kept), 1)
        self.assertTrue((kept[0] / "ws" / "dashboard.html").is_file())
        self.assertTrue((kept[0] / "start" / "dashboard.html").is_file())
        settings = json.loads((kept[0] / "settings.json").read_text(encoding="utf-8"))
        self.assertIn("Edit(/%s/**)" % (kept[0] / "ws"), settings["permissions"]["allow"])
        self.assertTrue((kept[0].parent / "plugin" / "skills" / "pka-interface" / "SKILL.md").is_file())

    def test_a_graded_run(self) -> None:
        os.environ["FAKE_CLAUDE_HOME_WRITE"] = "1"
        code, out, err = self.go("--scenario", "librarian-quick-lint", "--scenario", "wiki-retire",
                                 "--results-dir", str(self.results), "--max-turns", "9", "--max-usd", "0.6")
        self.assertEqual(err, "")
        self.assertEqual(code, 0, out)
        calls = self.calls()
        self.assertEqual([c["judge"] for c in calls], [False, True, False, False, True])
        subject = calls[0]
        self.assertEqual(subject["leaked_env"], [], "the parent session's variables do not reach the child")
        self.assertTrue(subject["home"].endswith("/librarian-quick-lint/home"))
        self.assertTrue(subject["cwd"].endswith("/librarian-quick-lint/ws"))
        self.assertEqual(subject["prompt"], "Quick lint.")
        self.assertIn("--max-turns", subject["argv"])
        self.assertEqual(subject["argv"][subject["argv"].index("--max-budget-usd") + 1], "0.60")
        self.assertTrue(calls[1]["cwd"].endswith("/librarian-quick-lint/judge"))
        self.assertIn("--resume", calls[3]["argv"])
        self.assertEqual(calls[3]["prompt"], "Yes, retire it. I've moved on to an MCP wiki.")

        one = self.result("pka-librarian", "librarian-quick-lint")
        self.assertEqual((one["status"], one["verdict"], one["met"], one["total"]), ("graded", "pass", 4, 4))
        self.assertEqual(one["subject_cost_usd"], 0.0421)
        self.assertEqual(one["judge_cost_usd"], 0.011)
        self.assertAlmostEqual(one["cost_usd"], 0.0531)
        self.assertEqual(one["tokens"]["cache_read_input_tokens"], 3000)
        self.assertEqual(one["subject_model"], "fake-model")
        self.assertEqual([e["kind"] for e in one["transcript"]][:3], ["assistant_text", "tool_call", "tool_result"])
        self.assertEqual(one["transcript"][6]["input"], {"command": "python3 .pka/bin/pka-tools lint --quick --json"})
        workspace = one["workspace"]
        self.assertEqual(workspace["added"], ["owner-inbox/fake-report.md"])
        self.assertEqual(workspace["changed"], ["CLAUDE.md"])
        self.assertEqual(workspace["removed"], ["owner-inbox/.keep"] if False else [])
        self.assertIn("+<!-- touched by the fake -->", workspace["text"])
        self.assertIn("+findings: 2", workspace["text"])
        self.assertEqual(len(workspace["final"]["CLAUDE.md"]["sha256"]), 64)
        self.assertNotEqual(workspace["final"]["CLAUDE.md"], workspace["start"]["CLAUDE.md"])
        self.assertEqual(one["home_changes"], ["~/outside.txt"])
        self.assertEqual(one["isolation"], {"sandbox": "off", "home": "scratch", "plugin_copy_unchanged": True,
                                            "left_in_cli_config": []})
        self.assertIs(one["plugin_copy_changed"], False)
        self.assertTrue(subject["plugin"].endswith("/librarian-quick-lint/plugin"), "each scenario loads its own copy")
        self.assertEqual(subject["pwd"], subject["cwd"])
        self.assertEqual(one["turns"][0]["permission_denials"][0]["tool_input"], {"command": "git status"})
        evidence = one["evidence"]
        self.assertNotIn("SECRET-SKILL-TEXT", evidence)
        self.assertNotIn("SECRET-SKILL-TEXT", json.dumps(one["judgement"]))
        for part in ("# EXPECTATIONS (grade each one)\n1. runs `.pka/bin/pka-tools lint --quick --json`", "# STARTING STATE",
                     "seeded lint problems", "# TRANSCRIPT", "# WORKSPACE CHANGES", "added (1): owner-inbox/fake-report.md",
                     "~/outside.txt", "# DIFF OF TEXT FILES", "# FINAL FILE LISTING", "the harness denied: Bash"):
            self.assertIn(part, evidence)
        self.assertNotIn("pka-librarian/SKILL.md", evidence.split("# TRANSCRIPT")[0])
        self.assertEqual(one["judgement"]["expectations"][0]["quotes_found"], [True])

        two = self.result("pka-wiki", "wiki-retire")
        self.assertEqual(len(two["turns"]), 2)
        self.assertEqual(two["subject_cost_usd"], 0.0842)
        self.assertEqual(sorted(two["workspace"]["added"]), ["owner-inbox/fake-report-2.md", "owner-inbox/fake-report.md"])
        self.assertIn("=== USER MESSAGE 2 ===\nYes, retire it.", two["evidence"])

        summary = (self.results / "summary.md").read_text(encoding="utf-8")
        self.assertIn("- Verdicts: 2 pass, 0 partial, 0 fail; expectations met: 9 of 9", summary)
        self.assertIn("| librarian-quick-lint | pka-librarian | pass | 4/4 |", summary)
        self.assertIn("OS sandbox off", summary)
        self.assertIn(summary, out)
        self.assertTrue((self.results / "raw" / "librarian-quick-lint.turn1.jsonl").is_file())
        self.assertTrue((self.results / "run.json").is_file())
        self.assertEqual(list(self.work.iterdir()), [])
        self.assertEqual(list((self.config / "projects").iterdir()), [])

    def test_partial_verdict_and_exit_code(self) -> None:
        os.environ["FAKE_JUDGE"] = "mixed"
        code, out, _ = self.go("--scenario", "librarian-quick-lint", "--results-dir", str(self.results))
        self.assertEqual(code, 1)
        got = self.result("pka-librarian", "librarian-quick-lint")
        self.assertEqual((got["verdict"], got["met"], got["total"]), ("partial", 2, 4))
        self.assertIn("# Expectations not met", out)
        self.assertIn("- **2. reports rules 1-4, 8a and 8b only** — no. Not shown.", out)

    def test_a_judge_that_quotes_what_is_not_there_fails_the_scenario(self) -> None:
        os.environ["FAKE_JUDGE"] = "badquote"
        code, out, _ = self.go("--scenario", "librarian-quick-lint", "--results-dir", str(self.results))
        self.assertEqual(code, 1)
        got = self.result("pka-librarian", "librarian-quick-lint")
        self.assertEqual((got["verdict"], got["met"]), ("fail", 0))
        self.assertEqual(got["judgement"]["judge_verdict"], "pass")
        self.assertIn("Downgraded by the runner", out)

    def test_judge_failure_then_rejudge(self) -> None:
        os.environ["FAKE_JUDGE"] = "garbage"
        code, out, _ = self.go("--scenario", "librarian-quick-lint", "--results-dir", str(self.results))
        self.assertEqual(code, 2)
        got = self.result("pka-librarian", "librarian-quick-lint")
        self.assertEqual(got["status"], "judge-error")
        self.assertIn("no JSON object", got["error"])
        self.assertTrue(got["evidence"])
        before = len(self.calls())
        os.environ["FAKE_JUDGE"] = "pass"
        code, out, err = self.go("--rejudge", str(self.results))
        self.assertEqual((code, err), (0, ""))
        after = self.calls()[before:]
        self.assertEqual([c["judge"] for c in after], [True], "rejudging does not run the subject again")
        got = self.result("pka-librarian", "librarian-quick-lint")
        self.assertEqual((got["status"], got["verdict"]), ("graded", "pass"))
        self.assertEqual(got["subject_cost_usd"], 0.0421)

    def test_resume_skips_what_is_graded(self) -> None:
        code, _, _ = self.go("--scenario", "librarian-quick-lint", "--results-dir", str(self.results))
        self.assertEqual(code, 0)
        before = len(self.calls())
        code, out, _ = self.go("--scenario", "librarian-quick-lint", "--scenario", "wiki-list", "--resume", str(self.results))
        self.assertEqual(code, 0)
        self.assertIn("2 scenario(s) selected, 1 already graded", out)
        new = self.calls()[before:]
        self.assertEqual(len(new), 2)
        self.assertTrue(all("wiki-list" in c["cwd"] for c in new))
        self.assertIn("- Scenarios: 2 (graded 2, not graded 0)", (self.results / "summary.md").read_text(encoding="utf-8"))

    def test_total_cap_stops_new_scenarios_and_resume_continues(self) -> None:
        code, out, _ = self.go("--skill", "wiki", "--limit", "3", "--results-dir", str(self.results), "--max-total-usd", "0.05")
        self.assertEqual(code, 2)
        self.assertIn("2 scenario(s) were not run: the run reached its cap of $0.05", out)
        self.assertEqual(len(run.read_results(self.results)), 1)
        code, out, _ = self.go("--skill", "wiki", "--limit", "3", "--resume", str(self.results), "--max-total-usd", "5")
        self.assertEqual(code, 0)
        self.assertEqual(len(run.read_results(self.results)), 3)

    def test_jobs_run_scenarios_side_by_side(self) -> None:
        code, out, _ = self.go("--skill", "wiki", "--jobs", "3", "--results-dir", str(self.results))
        self.assertEqual(code, 0, out)
        records = run.read_results(self.results)
        self.assertEqual(len(records), 8)
        self.assertTrue(all(r["verdict"] == "pass" for r in records))
        self.assertEqual(len({c["cwd"] for c in self.calls() if not c["judge"]}), 8)

    def test_a_real_run_leaves_out_scenarios_that_wait_for_another_change(self) -> None:
        with waiting("pka-interface"):
            code, out, err = self.go("--skill", "interface", "--results-dir", str(self.results))
            self.assertEqual(code, 2)
            self.assertIn("every selected scenario is marked `needs`", err)
            self.assertEqual(self.calls(), [])
            code, out, err = self.go("--scenario", "interface-refresh", "--scenario", "wiki-list", "--results-dir", str(self.results))
            self.assertEqual(code, 0, err)
            self.assertIn("Left out, waiting for another change (run them with --include-needs): interface-refresh (PR #99)", out)
            self.assertEqual([r["id"] for r in run.read_results(self.results)], ["wiki-list"])
            code, out, err = self.go("--scenario", "interface-refresh", "--include-needs", "--resume", str(self.results))
            self.assertEqual(code, 0, err)
            self.assertEqual(sorted(r["id"] for r in run.read_results(self.results)), ["interface-refresh", "wiki-list"])
            self.assertEqual(json.loads((self.results / "pka-interface" / "interface-refresh.json").read_text(encoding="utf-8"))["needs"], "PR #99")

    def test_turn_cap_stops_a_runaway_subject(self) -> None:
        os.environ["FAKE_CLAUDE_MODE"] = "loop"
        started = time.time()
        code, out, _ = self.go("--scenario", "librarian-quick-lint", "--results-dir", str(self.results), "--max-turns", "3")
        self.assertLess(time.time() - started, 30)
        got = self.result("pka-librarian", "librarian-quick-lint")
        self.assertEqual(got["turns"][0]["stopped"], "turn-cap")
        self.assertLess(len([e for e in got["transcript"] if e["kind"] == "tool_call"]), 20)
        self.assertIn("the runner stopped this turn early (turn-cap)", got["evidence"])
        self.assertEqual(got["status"], "graded", "what happened before the cap is still graded")

    def test_timeout_stops_a_slow_subject(self) -> None:
        os.environ["FAKE_CLAUDE_MODE"] = "loop"
        code, out, _ = self.go("--scenario", "librarian-quick-lint", "--results-dir", str(self.results),
                               "--max-turns", "500", "--timeout", "1")
        self.assertEqual(self.result("pka-librarian", "librarian-quick-lint")["turns"][0]["stopped"], "timeout")

    def test_authentication_failure_stops_the_run_with_one_line(self) -> None:
        os.environ["FAKE_CLAUDE_MODE"] = "auth"
        code, out, err = self.go("--skill", "wiki", "--results-dir", str(self.results))
        self.assertEqual(code, 2)
        self.assertEqual(err.count("\n"), 1, err)
        self.assertIn("could not authenticate", err)
        self.assertIn("OAuth session expired", err)
        self.assertNotIn("Traceback", out + err)
        self.assertEqual(len([c for c in self.calls() if not c["judge"]]), 1, "the first failure stops the run")
        self.assertEqual(run.read_results(self.results), [])
        self.assertEqual(list(self.work.iterdir()), [])

    def test_what_the_cli_leaves_in_its_own_folder_is_removed_even_when_a_run_fails(self) -> None:
        ws = self.work / "pka-evals.x" / "wiki-list" / "ws"
        slug = re.sub(r"[^A-Za-z0-9]", "-", str(ws))
        mine = self.config / "projects" / (slug + "-projects-orion")
        (mine / "memory").mkdir(parents=True)
        (mine / "abc-123.jsonl").write_text("{}", encoding="utf-8")
        other = self.config / "projects" / "-home-someone-else"
        (other / "memory").mkdir(parents=True)
        (other / "notes.md").write_text("keep", encoding="utf-8")
        cfg = {"config_dir": str(self.config)}
        self.assertEqual(run.forget_session(cfg, "abc-123", ws), [])
        self.assertFalse(mine.exists())
        self.assertTrue((other / "notes.md").is_file(), "only this run's own folder is touched")
        kept = self.config / "projects" / slug
        kept.mkdir()
        (kept / "someone-elses-session.jsonl").write_text("{}", encoding="utf-8")
        self.assertEqual(run.forget_session(cfg, None, ws), [str(kept)])
        self.assertTrue((kept / "someone-elses-session.jsonl").is_file(), "a folder that is not empty is reported, not deleted")

    def test_a_subject_that_dies_is_an_error_not_a_verdict(self) -> None:
        for mode, expected in (("crash", "fake claude: something broke"), ("noresult", "no result event")):
            os.environ["FAKE_CLAUDE_MODE"] = mode
            results = self.base / ("results-" + mode)
            code, out, _ = self.go("--scenario", "wiki-list", "--results-dir", str(results))
            self.assertEqual(code, 2)
            got = json.loads((results / "pka-wiki" / "wiki-list.json").read_text(encoding="utf-8"))
            self.assertEqual((got["status"], got["verdict"]), ("error", None))
            self.assertIn(expected, got["error"])
            self.assertIn("| wiki-list | pka-wiki | error | 0/5 |", out)

    def test_the_sandbox_is_required_by_default(self) -> None:
        original = run.sandbox_available
        run.sandbox_available = lambda: "bwrap not installed (on Linux the sandbox needs bubblewrap and socat)"
        try:
            code, out, err = self.go("--scenario", "wiki-list", "--results-dir", str(self.results), sandbox="require")
        finally:
            run.sandbox_available = original
        self.assertEqual(code, 2)
        self.assertIn("the OS sandbox is required and is not available: bwrap not installed", err)
        self.assertIn("--sandbox off", err)
        self.assertEqual(err.count("\n"), 1)
        self.assertEqual(self.calls(), [])
        run.sandbox_available = lambda: None
        try:
            code, out, err = self.go("--scenario", "wiki-list", "--results-dir", str(self.results), sandbox="require")
        finally:
            run.sandbox_available = original
        self.assertEqual(code, 0, err)
        settings_call = self.calls()[0]["argv"]
        self.assertIn("--settings", settings_call)
        self.assertEqual(json.loads((self.results / "run.json").read_text(encoding="utf-8"))["sandbox"], "require")

    def test_a_work_folder_inside_a_workspace_is_refused(self) -> None:
        (self.work / "CLAUDE.md").write_text("# someone's instructions\n", encoding="utf-8")
        code, out, err = self.go("--dry-run", "--scenario", "wiki-list")
        self.assertEqual(code, 2)
        self.assertIn("exists above the work folder", err)
        self.assertEqual([p.name for p in self.work.iterdir()], ["CLAUDE.md"])

    def test_usage_errors_are_one_line(self) -> None:
        for args, expected in ((["--scenario", "nope"], "no scenario matches 'nope'"), (["--max-turns", "0"], "--max-turns must be at least 1"),
                               (["--resume", str(self.base / "nowhere")], "no results folder"),
                               (["--tag", "no-such-tag"], "no scenario selected"),
                               (["--rejudge", str(self.work)], "no stored transcripts")):
            code, out, err = self.go(*args)
            self.assertEqual(code, 2, args)
            self.assertIn(expected, err)
            self.assertEqual(err.count("\n"), 1, err)
        out, err = io.StringIO(), io.StringIO()
        stderr, sys.stderr = sys.stderr, err
        try:
            code = run.main(["--scenario", "wiki-list", "--claude", str(self.base / "no-such-cli"), "--sandbox", "off"], out)
        finally:
            sys.stderr = stderr
        self.assertEqual(code, 2)
        self.assertIn("cannot find the Claude Code CLI", err.getvalue())

    # ---- what reaches the subject and the judge

    def test_no_secret_of_the_parent_reaches_the_subject_or_the_judge(self) -> None:
        secrets = dict(Commands.SECRETS)
        del secrets["PWD"]
        os.environ.update(secrets)
        os.environ.update({"ANTHROPIC_API_KEY": "key-for-the-cli", "CLAUDE_CODE_OAUTH_TOKEN": "token-for-the-cli"})
        code, out, err = self.go("--skill", "wiki", "--limit", "2", "--results-dir", str(self.results))
        self.assertEqual((code, err), (0, ""), out)
        calls = self.calls()
        self.assertEqual({c["judge"] for c in calls}, {False, True})
        allowed = {"PATH", "LANG", "TERM", "TZ", "HOME", "TMPDIR", "PWD", "CLAUDE_CONFIG_DIR", "PYTHONDONTWRITEBYTECODE",
                   "GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
                   "ANTHROPIC_BASE_URL", "CLAUDE_CODE_OAUTH_TOKEN"}
        for call in calls:
            names = {name for name in call["env"] if not name.startswith(("FAKE_", "LC_"))}
            # A shell adds a few of its own to whatever it is given.
            names -= {"SHLVL", "_", "OLDPWD", "IFS", "OPTIND", "PS1", "PS2", "PS4", "MAILCHECK", "PPID"}
            self.assertEqual(names - allowed, set(), "judge" if call["judge"] else "subject")
            self.assertTrue({"ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"} <= names, "the CLI can still log in")
            for name in secrets:
                if name != "OLDPWD":
                    self.assertNotIn(name, call["env"], name)
            self.assertEqual(call["pwd"], call["cwd"])
            self.assertNotIn(str(REPO), call["pwd"])
        self.assertIn("environment built from a list", out)
        self.assertNotIn("--pass-env", out.split("How a run is confined")[1].split("\n\n")[0])

    def test_pass_env_is_explicit_and_recorded(self) -> None:
        os.environ.update({"HTTPS_PROXY": "http://proxy.example.com", "GH_TOKEN": "gh-secret"})
        code, out, err = self.go("--scenario", "wiki-list", "--results-dir", str(self.results), "--pass-env", "HTTPS_PROXY")
        self.assertEqual((code, err), (0, ""), out)
        for call in self.calls():
            self.assertIn("HTTPS_PROXY", call["env"])
            self.assertNotIn("GH_TOKEN", call["env"])
        self.assertIn("because you asked (--pass-env): HTTPS_PROXY", out)
        self.assertEqual(json.loads((self.results / "run.json").read_text(encoding="utf-8"))["pass_env"], ["HTTPS_PROXY"])
        self.assertIn("extra variables passed to the CLI: HTTPS_PROXY", (self.results / "summary.md").read_text(encoding="utf-8"))
        code, out, err = self.go("--scenario", "wiki-list", "--results-dir", str(self.results), "--pass-env", "A=B")
        self.assertEqual(code, 2)
        self.assertIn("--pass-env takes the name of an environment variable", err)

    # ---- the plugin copy

    def test_a_scenario_that_changes_its_plugin_copy_is_invalid_and_the_next_gets_a_fresh_one(self) -> None:
        os.environ.update({"FAKE_CLAUDE_MODE": "tamper", "FAKE_TAMPER_IN": "/wiki-list/"})
        three = ["--scenario", "wiki-list", "--scenario", "wiki-create", "--scenario", "wiki-retire"]
        code, out, err = self.go(*three, "--results-dir", str(self.results))
        self.assertEqual(code, 2, out)
        records = {r["id"]: r for r in run.read_results(self.results)}
        self.assertEqual(len(records), 3)
        bad = records["wiki-list"]
        self.assertEqual((bad["status"], bad["verdict"], bad["plugin_copy_changed"]), ("invalid", None, True))
        self.assertIs(bad["isolation"]["plugin_copy_unchanged"], False)
        self.assertIn("was changed during it", bad["error"])
        self.assertIsNone(bad["judgement"])
        self.assertTrue(bad["evidence"], "what happened is kept for whoever looks into it")
        subjects = [c for c in self.calls() if not c["judge"]]
        self.assertEqual(len([c for c in self.calls() if c["judge"] and "/wiki-list/" in c["cwd"]]), 0,
                         "an invalid run is not sent to the judge")
        for call in subjects:
            self.assertNotIn("tampered", call["skill_text"], "every scenario starts from an unchanged copy: %s" % call["cwd"])
        self.assertEqual(len({c["plugin"] for c in subjects}), 3)
        for ident, record in records.items():
            if ident != "wiki-list":
                self.assertEqual((record["status"], record["plugin_copy_changed"]), ("graded", False), ident)
                self.assertIs(record["isolation"]["plugin_copy_unchanged"], True)
        summary = (self.results / "summary.md").read_text(encoding="utf-8")
        self.assertIn("- INVALID: 1 scenario(s) changed the plugin copy they were given and were not graded: wiki-list.", summary)
        self.assertIn("| wiki-list | pka-wiki | invalid |", summary)
        self.assertIn("- Scenarios: 3 (graded 2, not graded 1)", summary)
        self.assertEqual(json.loads((self.results / "summary.json").read_text(encoding="utf-8"))["totals"]["invalid"], ["wiki-list"])
        self.assertIn("invalid ", out)
        # --resume runs the invalid one again; --rejudge does not grade it.
        os.environ["FAKE_CLAUDE_MODE"] = "ok"
        before = len(self.calls())
        code, out, err = self.go(*three, "--rejudge", str(self.results))
        self.assertEqual([c["cwd"].split("/")[-2] for c in self.calls()[before:] if c["judge"]].count("wiki-list"), 0)
        code, out, err = self.go(*three, "--resume", str(self.results))
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.result("pka-wiki", "wiki-list")["status"], "graded")

    def test_an_invalid_scenario_is_caught_even_when_the_subject_then_fails(self) -> None:
        os.environ["FAKE_CLAUDE_MODE"] = "tamper"
        original = run.parse_stream
        run.parse_stream = lambda lines: ([], None, {})         # as if the CLI printed no result
        try:
            code, out, err = self.go("--scenario", "wiki-list", "--results-dir", str(self.results))
        finally:
            run.parse_stream = original
        got = self.result("pka-wiki", "wiki-list")
        self.assertEqual((got["status"], got["plugin_copy_changed"]), ("invalid", True))

    # ---- setup that cannot be built

    BAD_STEPS = (
        ({"write": "CLAUDE.md/x", "text": "x"}, "step 1 (write CLAUDE.md/x) cannot be applied"),
        ({"write": "n" * 300, "text": "x"}, "…) cannot be applied: File name too long"),
        ({"copy": "knowledge/AI", "to": "knowledge/leadership"}, "step 1 (copy knowledge/AI) cannot be applied: File exists"),
        ({"mkdir": "CLAUDE.md"}, "cannot be applied"),
    )
    BAD_FILES = (
        ({"write": ".", "text": "x"}, "not the workspace itself"),
        ({"age": "CLAUDE.md", "days": "abc"}, "'days' must be a number"),
        ({"age": "CLAUDE.md", "days": True}, "'days' must be a number"),
        ({"replace": "CLAUDE.md", "old": 5, "new": "x"}, "'old' must be a string or a list of strings"),
        ({"write": "a.md", "text": {"a": 1}}, "'text' must be a string or a list of strings"),
        ({"write": 7, "text": "x"}, "setup path must be relative"),
        ({"lint_report": {"days_ago": "3"}}, "lint_report takes an object"),
        ({"tool": ["status"], "allow_fail": "yes"}, "'allow_fail' must be true or false"),
    )

    def test_a_step_that_fails_is_one_line_never_a_traceback(self) -> None:
        for number, (step, expected) in enumerate(self.BAD_STEPS):
            with self.assertRaises(run.RunnerError) as caught:
                self.build({"steps": [step]}, "bad%d" % number)
            self.assertIn(expected, str(caught.exception))
            self.assertNotIn("\n", str(caught.exception))
            self.assertNotIn(str(self.base), str(caught.exception), "no absolute path in the message")
        for step, expected in self.BAD_FILES:
            problems = run.validate_setup({"steps": [step]}, "x")
            self.assertTrue(any(expected in problem for problem in problems), (step, problems))

    def with_scenarios(self, *scenarios):
        """Run with these scenarios in place of the shipped files."""
        from unittest import mock
        evals = self.base / "evals"
        evals.mkdir(exist_ok=True)
        (evals / "pka-wiki.evals.json").write_text(json.dumps(list(scenarios)), encoding="utf-8")
        return mock.patch.object(run, "EVALS_DIR", evals)

    def test_a_setup_that_fails_does_not_cost_the_run_its_summary(self) -> None:
        good = {"id": "wiki-good", "prompt": "List the wikis.", "expect": "lists them"}
        scenarios = [{"id": "wiki-bad-%d" % n, "prompt": "x", "expect": "y", "setup": {"steps": [step]}}
                     for n, (step, _expected) in enumerate(self.BAD_STEPS)] + [good]
        with self.with_scenarios(*scenarios):
            code, out, err = self.go("--dry-run")
            self.assertEqual(code, 2)
            self.assertNotIn("Traceback", out + err)
            self.assertEqual(out.count("SETUP FAILED: setup: step 1"), len(self.BAD_STEPS), out)
            self.assertIn("1 scenario(s) prepared, %d failed to set up." % len(self.BAD_STEPS), out)
            code, out, err = self.go("--results-dir", str(self.results))
            self.assertEqual((code, err), (2, ""), out)
        self.assertTrue((self.results / "summary.md").is_file(), "the scenario that ran is summarised")
        records = {r["id"]: r for r in run.read_results(self.results)}
        self.assertEqual(records["wiki-good"]["status"], "graded")
        self.assertEqual(records["wiki-bad-0"]["status"], "error")
        self.assertIn("step 1 (write CLAUDE.md/x) cannot be applied", records["wiki-bad-0"]["error"])
        self.assertEqual(len([c for c in self.calls() if not c["judge"]]), 1, "only the good scenario reached the CLI")
        self.assertEqual(list(self.work.iterdir()), [])

    def test_an_eval_file_with_a_wrong_type_is_refused_before_anything_runs(self) -> None:
        for step, expected in self.BAD_FILES:
            with self.with_scenarios({"id": "wiki-bad", "prompt": "x", "expect": "y", "setup": {"steps": [step]}}):
                code, out, err = self.go("--dry-run")
            self.assertEqual(code, 2, step)
            self.assertIn(expected, err)
            self.assertNotIn("Traceback", err)
        with self.with_scenarios({"id": "wiki-empty", "prompt": "x", "expect": ";;"}):
            code, out, err = self.go("--validate")
        self.assertEqual(code, 2)
        self.assertIn("'expect' holds no expectation", err)
        self.assertEqual(self.calls(), [])

    def test_damaged_result_files_are_one_line_or_ignored(self) -> None:
        code, _, _ = self.go("--scenario", "wiki-list", "--results-dir", str(self.results))
        self.assertEqual(code, 0)
        # A result file without its skill is not a result: --resume carries on without it.
        (self.results / "pka-wiki" / "stray.json").write_text('{"id": "stray", "status": "graded"}', encoding="utf-8")
        (self.results / "pka-wiki" / "broken.json").write_text("{not json", encoding="utf-8")
        code, out, err = self.go("--scenario", "wiki-list", "--resume", str(self.results))
        self.assertEqual((code, err), (0, ""), out)
        self.assertIn("1 scenario(s) selected, 1 already graded", out)
        for damaged in ("{not json", "[1, 2]"):
            (self.results / "run.json").write_text(damaged, encoding="utf-8")
            before = len(self.calls())
            code, out, err = self.go("--scenario", "wiki-list", "--rejudge", str(self.results))
            self.assertEqual(code, 2)
            self.assertEqual(err.count("\n"), 1, err)
            self.assertIn("run.json", err)
            self.assertNotIn("Traceback", err)
            self.assertEqual(len(self.calls()), before, "nothing is sent to the judge before the problem is reported")

    # ---- where scratch folders may be made

    def test_a_work_folder_in_the_checkout_or_at_the_root_is_refused(self) -> None:
        for folder in (REPO, REPO / "evals", REPO / "tests" / "evals", Path("/")):
            out, err = io.StringIO(), io.StringIO()
            stderr, sys.stderr = sys.stderr, err
            try:
                code = run.main(["--dry-run", "--scenario", "wiki-list", "--work-dir", str(folder)], out)
            finally:
                sys.stderr = stderr
            self.assertEqual(code, 2, folder)
            self.assertEqual(err.getvalue().count("\n"), 1, err.getvalue())
            self.assertIn("filesystem root" if folder == Path("/") else "inside this checkout", err.getvalue())
            self.assertEqual(sorted(REPO.glob("**/pka-evals.*")), [], "nothing was created in the checkout")

    # ---- stopping

    def pids(self, path: Path, wait: float = 20.0):
        deadline = time.time() + wait
        while time.time() < deadline:
            if path.exists() and path.read_text(encoding="utf-8").strip():
                return [int(part) for part in path.read_text(encoding="utf-8").split()]
            time.sleep(0.05)
        self.fail("the stand-in CLI never started")

    def alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        # A zombie still has an entry; it is gone for every purpose that matters here.
        try:
            with open("/proc/%d/stat" % pid, encoding="utf-8") as handle:
                return handle.read().rsplit(")", 1)[1].split()[0] != "Z"
        except OSError:
            return True

    def gone(self, pids, wait: float = 10.0) -> bool:
        deadline = time.time() + wait
        while time.time() < deadline:
            if not any(self.alive(pid) for pid in pids):
                return True
            time.sleep(0.05)
        return False

    @unittest.skipUnless(hasattr(os, "killpg"), "needs process groups")
    def test_a_timeout_stops_whatever_the_cli_started(self) -> None:
        pid_file = self.base / "pids.txt"
        os.environ.update({"FAKE_CLAUDE_MODE": "hang", "FAKE_CLAUDE_PIDS": str(pid_file), "FAKE_HANG_PARENT_EXITS": "1"})
        started = time.time()
        code, out, err = self.go("--scenario", "wiki-list", "--results-dir", str(self.results), "--timeout", "2")
        self.assertLess(time.time() - started, 20, "the run does not wait for a process that kept the output open")
        self.assertTrue(self.gone(self.pids(pid_file)), "nothing the CLI started is left running")
        self.assertEqual(self.result("pka-wiki", "wiki-list")["turns"][0]["stopped"], "timeout")
        self.assertEqual(list(self.work.iterdir()), [])

    @unittest.skipUnless(hasattr(os, "killpg") and hasattr(signal, "SIGTERM"), "needs process groups and SIGTERM")
    def test_sigterm_stops_the_model_call_and_removes_the_run_folder(self) -> None:
        for number, (signum, expected) in enumerate(((signal.SIGTERM, 128 + signal.SIGTERM), (signal.SIGINT, 130))):
            pid_file = self.base / ("pids-%d.txt" % number)
            os.environ.update({"FAKE_CLAUDE_MODE": "hang", "FAKE_CLAUDE_PIDS": str(pid_file)})
            self.write_shim()
            results = self.base / ("results-%d" % number)
            runner = subprocess.Popen(
                [sys.executable, str(REPO / "evals" / "run.py"), "--skill", "wiki", "--limit", "2", "--claude", str(self.shim),
                 "--work-dir", str(self.work), "--sandbox", "off", "--results-dir", str(results), "--timeout", "100"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
            try:
                pids = self.pids(pid_file)
                self.assertTrue(all(self.alive(pid) for pid in pids))
                self.assertEqual(len(list(self.work.glob("pka-evals.*"))), 1)
                runner.send_signal(signum)
                out, err = runner.communicate(timeout=30)
            finally:
                if runner.poll() is None:
                    runner.kill()
                    runner.communicate()
            self.assertEqual(runner.returncode, expected, err)
            self.assertNotIn("Traceback", err)
            self.assertEqual(err.count("\n"), 1, err)
            self.assertIn("--resume", err)
            self.assertTrue(self.gone(pids), "the model call and what it started are stopped, not orphaned")
            self.assertEqual(list(self.work.iterdir()), [], "the run folder is removed")
            self.assertEqual(len(pid_file.read_text(encoding="utf-8").splitlines()), 1, "no further scenario was started")
            self.assertEqual(run.read_results(results), [], "a scenario cut short leaves no result to mistake for one")

    def test_list_and_validate(self) -> None:
        code, out, _ = self.go("--list", "--tag", "smoke")
        self.assertEqual(code, 0)
        self.assertIn("[smoke]", out)
        self.assertRegex(out, r"1[0-4] scenario\(s\)")
        code, out, _ = self.go("--validate")
        self.assertEqual(code, 0)
        self.assertRegex(out, r"^\d+ scenarios in 6 files, \d+ expectations: no problems\.\n$")
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
