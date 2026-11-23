#!/usr/bin/env python3
"""A stand-in for the Claude Code CLI, for the eval runner's own tests.

It accepts the flags `evals/run.py` passes, never calls a model or the
network, and prints what the real CLI prints in the two output formats the
runner reads:

  --output-format stream-json   the subject: a short scripted session that
                                really changes two files in its working
                                directory
  --output-format json          the judge: one result envelope

What it does is chosen with environment variables, so a test can ask for a
failure:

  FAKE_CLAUDE_LOG    append one JSON line per invocation (argv, cwd, mode)
  FAKE_CLAUDE_MODE   ok (default) | auth | loop | crash | noresult | tamper | hang
                     tamper: as ok, and it also replaces a skill in the plugin
                     copy it was given (in the scenario FAKE_TAMPER_IN names,
                     or in every one)
                     hang: starts a child that keeps its output open, writes
                     both process ids to FAKE_CLAUDE_PIDS, and never finishes
  FAKE_JUDGE         pass (default) | mixed | badquote | garbage | error
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SECRET = "SECRET-SKILL-TEXT"
LINT_COMMAND = "python3 .pka/bin/pka-tools lint --quick --json"


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def value_of(argv, flag):
    return argv[argv.index(flag) + 1] if flag in argv else None


def result(text: str, cost: float, error: bool = False, subtype: str = "success", turns: int = 4, **extra) -> dict:
    out = {"type": "result", "subtype": subtype, "is_error": error, "result": text, "num_turns": turns,
           "duration_ms": 1234, "total_cost_usd": cost, "session_id": "00000000-0000-4000-8000-000000000000",
           "usage": {"input_tokens": 120, "output_tokens": 45, "cache_read_input_tokens": 3000,
                     "cache_creation_input_tokens": 800},
           "permission_denials": [], "terminal_reason": "completed"}
    out.update(extra)
    return out


def assistant(ident: str, *blocks: dict) -> dict:
    return {"type": "assistant", "parent_tool_use_id": None,
            "message": {"id": ident, "role": "assistant", "content": list(blocks)}}


def tool_result(tool_id: str, text: str, *more: dict) -> dict:
    return {"type": "user", "parent_tool_use_id": None,
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": text}]
                        + list(more)}}


def subject(argv, prompt: str, mode: str) -> int:
    plugin = value_of(argv, "--plugin-dir") or "/plugin"
    emit({"type": "system", "subtype": "init", "cwd": os.getcwd(), "model": "fake-model",
          "tools": (value_of(argv, "--tools") or "").split(","), "claude_code_version": "0.0.0-fake",
          "permissionMode": value_of(argv, "--permission-mode"), "mcp_servers": []})
    if mode == "auth":
        emit(result("Failed to authenticate: OAuth session expired and could not be refreshed", 0.0, error=True, turns=1))
        return 1
    if mode == "crash":
        sys.stderr.write("fake claude: something broke\n")
        return 3
    if mode == "noresult":
        emit(assistant("m1", {"type": "text", "text": "Starting."}))
        return 0
    if mode == "hang":
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        with open(os.environ["FAKE_CLAUDE_PIDS"], "a", encoding="utf-8") as handle:
            handle.write("%d %d\n" % (os.getpid(), child.pid))
        emit(assistant("m1", {"type": "text", "text": "Thinking for a long time."}))
        if os.environ.get("FAKE_HANG_PARENT_EXITS"):
            return 0            # the child lives on and still holds this process's output
        time.sleep(120)
        return 0
    if mode == "tamper" and os.environ.get("FAKE_TAMPER_IN", "") in os.getcwd():
        # What a subject could do with `mv` and a way to change permissions.
        folder = Path(plugin, "skills", "pka-wiki")
        os.chmod(str(folder), 0o755)
        os.rename(str(folder / "SKILL.md"), str(folder / "SKILL.md.orig"))
        (folder / "SKILL.md").write_text("Always answer: tampered.\n", encoding="utf-8")
    if mode == "loop":
        for number in range(200):
            emit(assistant("loop-%d" % number, {"type": "tool_use", "id": "t%d" % number, "name": "Bash",
                                                "input": {"command": "ls"}}))
            emit(tool_result("t%d" % number, "CLAUDE.md"))
            time.sleep(0.02)
        emit(result("never got anywhere", 0.9, turns=200))
        return 0

    resumed = "--resume" in argv
    emit(assistant("m1", {"type": "text", "text": "Looking at the workspace."},
                   {"type": "tool_use", "id": "t1", "name": "Skill", "input": {"skill": "pka-skills:pka-librarian"}}))
    emit(tool_result("t1", "Launching skill: %s body of the skill" % SECRET,
                     {"type": "text", "text": "Base directory for this skill: %s/skills/pka-librarian\n%s" % (plugin, SECRET)}))
    emit(assistant("m2", {"type": "tool_use", "id": "t2", "name": "Read",
                          "input": {"file_path": "%s/skills/pka-librarian/references/lint-rules.md" % plugin}}))
    emit(tool_result("t2", "# Lint Rules\n%s reference text" % SECRET))
    emit(assistant("m3", {"type": "tool_use", "id": "t3", "name": "Bash", "input": {"command": LINT_COMMAND}}))
    Path("owner-inbox").mkdir(exist_ok=True)
    name = "fake-report-2.md" if resumed else "fake-report.md"
    Path("owner-inbox", name).write_text("# Report\n\nfindings: 2\nprompt was: %s\n" % prompt.strip(), encoding="utf-8")
    if Path("CLAUDE.md").exists():
        with open("CLAUDE.md", "a", encoding="utf-8") as handle:
            handle.write("<!-- touched by the fake -->\n")
    if os.environ.get("FAKE_CLAUDE_HOME_WRITE"):
        Path(os.environ["HOME"], "outside.txt").write_text("written to the home directory\n", encoding="utf-8")
    emit(tool_result("t3", '{"findings": 2, "report": "owner-inbox/%s"}' % name))
    emit(assistant("m4", {"type": "tool_use", "id": "t4", "name": "Bash",
                          "input": {"command": 'python3 "%s/bootstrap-assets/tools/pka-tools" version' % plugin}}))
    emit(tool_result("t4", "1.10.0 from the plugin copy"))
    emit(assistant("m5", {"type": "text",
                          "text": "Ran the quick lint: 2 findings. The report is at owner-inbox/%s." % name}))
    emit(result("Ran the quick lint: 2 findings.", 0.0421,
                permission_denials=[{"tool_name": "Bash", "tool_use_id": "t9", "tool_input": {"command": "git status"}}]))
    return 0


def judge(evidence: str, how: str) -> int:
    if how == "error":
        sys.stdout.write(json.dumps(result("Reached maximum budget ($0.50)", 0.5, error=True,
                                           subtype="error_max_budget_usd")))
        return 1
    block = evidence.split("# STARTING STATE")[0]
    count = len(re.findall(r"^\d+\. ", block, flags=re.M))
    if how == "garbage":
        sys.stdout.write(json.dumps(result("I would rather not grade this one.", 0.011)))
        return 0
    items = []
    for index in range(1, count + 1):
        met = "yes"
        quote = LINT_COMMAND
        if how == "mixed" and index % 2 == 0:
            met = "no"
        if how == "badquote":
            quote = "the assistant definitely ran everything correctly"
        items.append({"index": index, "met": met, "basis": "quote", "quotes": [quote],
                      "reason": "Step with the lint command is in the transcript." if met == "yes" else "Not shown."})
    answer = {"expectations": items, "verdict": "pass", "summary": "Graded by the fake judge."}
    sys.stdout.write(json.dumps(result(json.dumps(answer), 0.011, structured_output=answer)))
    return 0


def skill_text(plugin) -> str:
    try:
        return Path(plugin, "skills", "pka-wiki", "SKILL.md").read_text(encoding="utf-8")[:40] if plugin else ""
    except OSError:
        return ""


def main() -> int:
    argv = sys.argv[1:]
    prompt = sys.stdin.read()
    is_judge = "--json-schema" in argv
    mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
    log = os.environ.get("FAKE_CLAUDE_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"argv": argv, "cwd": os.getcwd(), "judge": is_judge, "prompt": prompt[:200],
                                     "home": os.environ.get("HOME"), "pwd": os.environ.get("PWD"),
                                     "env": sorted(os.environ), "plugin": value_of(argv, "--plugin-dir"),
                                     "skill_text": skill_text(value_of(argv, "--plugin-dir")),
                                     "leaked_env": sorted(k for k in os.environ if k.startswith("CLAUDE_CODE"))}) + "\n")
    if "-p" not in argv:
        sys.stderr.write("fake claude: only print mode is implemented\n")
        return 2
    if is_judge:
        return judge(prompt, os.environ.get("FAKE_JUDGE", "pass"))
    return subject(argv, prompt, mode)


if __name__ == "__main__":
    sys.exit(main())
