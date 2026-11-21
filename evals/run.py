#!/usr/bin/env python3
"""Run the behavioural evals in evals/*.evals.json.

    python3 evals/run.py --dry-run                    build every workspace, print the commands
    python3 evals/run.py --tag smoke --max-total-usd 15
    python3 evals/run.py --skill pka-wiki --jobs 2
    python3 evals/run.py --resume evals/results/<timestamp>
    python3 evals/run.py --rejudge evals/results/<timestamp>

For each scenario the runner

  1. builds a scratch workspace from the scenario's `setup`,
  2. runs Claude Code headlessly in it with a read-only copy of this checkout
     loaded as the plugin (the subject),
  3. records the transcript and how the workspace changed,
  4. hands the expectations, the transcript and the diff to a second model
     call (the judge), which never sees the skill text,
  5. writes one JSON result per scenario and a summary table.

Standard library only, Python 3.9+. See evals/README.md.
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import fnmatch
import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parent.parent
EVALS_DIR = REPO / "evals"
RESULTS_DIR = EVALS_DIR / "results"
REFS = REPO / "skills" / "pka-bootstrap" / "references"
PLUGIN_TOOL = REPO / "bootstrap-assets" / "tools" / "pka-tools"
OLD_ROLES = REPO / "tests" / "fixtures" / "v1.7.0-roles"
FIXTURE_FILES = EVALS_DIR / "fixtures"

# What the subject's plugin copy holds: what a plugin needs to work, and of
# that only the files git tracks. docs/, evals/, tests/ and anything else in
# the checkout are never copied: the subject must not be able to read the
# expected answers, or a file the owner keeps untracked beside the sources.
# CHANGELOG.md is there because the tutorial skill reads it.
PLUGIN_DIRS = (".claude-plugin", "skills", "bootstrap-assets")
PLUGIN_FILES = ("CHANGELOG.md",)
NEVER_COPIED = ("docs", "evals", "tests", "pka-bench", ".git", ".github", ".claude")
PLUGIN_SKIP_NAMES = ("__pycache__", ".DS_Store")

# The environment of a `claude` child is built from these names and nothing
# else. PASSED_ENV is copied from the parent when set; so is every LC_*.
# AUTH_ENV is what the CLI reads to authenticate without a browser (its
# documentation, "Authentication precedence"): an API key, a bearer token
# with the endpoint it belongs to, or a long-lived token from
# `claude setup-token`. A login stored by `/login` is found through
# CLAUDE_CONFIG_DIR, which the runner sets itself.
PASSED_ENV = ("PATH", "LANG", "TERM", "TZ")
AUTH_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_OAUTH_TOKEN")

SUBJECT_TOOLS = "Bash,Read,Edit,Write,Glob,Grep,Skill"
SKILLS = ("pka-bootstrap", "pka-interface", "pka-librarian", "pka-meetings", "pka-tutorial", "pka-wiki")

FIXTURES = ("vault", "lint", "existing", "empty")
AUTONOMY = ("ask-before-everything", "ask-before-destructive", "hands-off")
SETUP_KEYS = {"fixture", "obsidian", "toolkit", "roles", "index", "autonomy", "cwd", "steps"}
STEP_VERBS = ("write", "append", "replace", "remove", "copy", "mkdir", "age", "tool", "lint_report", "git_repo",
              "fixture_file", "symlink")
SCENARIO_KEYS = {"id", "scenario", "setup", "prompt", "followups", "expect", "tags", "needs"}
ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

DEFAULTS = {
    "model": "sonnet",
    "judge_model": "sonnet",
    "max_turns": 40,
    "max_usd": 1.50,
    "judge_max_usd": 0.50,
    "max_total_usd": 25.0,
    "timeout": 900,
}


class RunnerError(Exception):
    """Something the user has to fix. Printed as one line."""


class AuthError(RunnerError):
    """The CLI could not authenticate; nothing else will work either."""


class InvalidRun(RunnerError):
    """The scenario ran, and its result cannot be trusted."""


# --------------------------------------------------------------------- small helpers

def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RunnerError("cannot load %s" % path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


_MODULES: Dict[str, Any] = {}
_MODULES_LOCK = threading.Lock()


def build_vault():
    with _MODULES_LOCK:
        if "build_vault" not in _MODULES:
            _MODULES["build_vault"] = _load_module("pka_eval_build_vault", REPO / "tests" / "fixtures" / "build_vault.py")
        return _MODULES["build_vault"]


def seeds():
    with _MODULES_LOCK:
        if "seeds" not in _MODULES:
            _MODULES["seeds"] = _load_module("pka_eval_seeds", REPO / "scripts" / "seeds.py")
        return _MODULES["seeds"]


def plugin_version() -> str:
    data = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    return str(data["version"])


def today() -> dt.date:
    override = os.environ.get("PKA_EVAL_TODAY")
    if override:
        return dt.date.fromisoformat(override)
    return dt.date.today()


_PLACEHOLDER = re.compile(r"\{\{(today|monday|plugin_version)(?:([+-])(\d+))?\}\}")


def fill(text: str) -> str:
    """Replace {{today}}, {{today-3}}, {{today+1}}, {{monday}} and {{plugin_version}}."""
    def sub(match: "re.Match[str]") -> str:
        name, sign, amount = match.group(1), match.group(2), match.group(3)
        if name == "plugin_version":
            return plugin_version()
        day = today()
        if name == "monday":
            day = day - dt.timedelta(days=day.weekday())
        if sign:
            delta = dt.timedelta(days=int(amount))
            day = day + delta if sign == "+" else day - delta
        return day.isoformat()
    return _PLACEHOLDER.sub(sub, text)


def fill_deep(value: Any) -> Any:
    if isinstance(value, str):
        return fill(value)
    if isinstance(value, list):
        return [fill_deep(item) for item in value]
    if isinstance(value, dict):
        return {fill(key) if isinstance(key, str) else key: fill_deep(item) for key, item in value.items()}
    return value


def as_text(value: Any) -> str:
    """Setup text is a string, or a list of lines (easier to read in JSON)."""
    if isinstance(value, list):
        return "\n".join(str(line) for line in value) + "\n"
    return str(value)


def inside(root: Path, rel: str) -> Path:
    """`rel` resolved under `root`; a path that leaves it is refused."""
    if not isinstance(rel, str) or not rel or rel.startswith(("/", "~")) or "\\" in rel:
        raise RunnerError("setup path must be relative to the workspace: %r" % (rel,))
    parts = Path(rel).parts
    if ".." in parts:
        raise RunnerError("setup path must stay inside the workspace: %r" % (rel,))
    if not parts:
        raise RunnerError("setup path must name a file or folder in the workspace, not the workspace itself: %r" % (rel,))
    return root / rel


def make_writable(root: Path) -> None:
    for folder, dirs, files in os.walk(str(root)):
        for name in dirs + files:
            path = os.path.join(folder, name)
            if not os.path.islink(path):
                try:
                    extra = stat.S_IXUSR if os.path.isdir(path) else 0
                    os.chmod(path, os.stat(path).st_mode | stat.S_IWUSR | stat.S_IRUSR | extra)
                except OSError:
                    pass
    try:
        os.chmod(str(root), os.stat(str(root)).st_mode | stat.S_IWUSR | stat.S_IRUSR | stat.S_IXUSR)
    except OSError:
        pass


def remove_tree(root: Path) -> None:
    if root.exists():
        make_writable(root)
        shutil.rmtree(str(root), ignore_errors=True)


# --------------------------------------------------------------------- scenarios

def split_expectations(expect: str) -> List[str]:
    """One expectation per `;` that is not inside parentheses or backticks."""
    out: List[str] = []
    depth = 0
    in_code = False
    current: List[str] = []
    for char in expect:
        if char == "`":
            in_code = not in_code
        elif not in_code and char in "([":
            depth += 1
        elif not in_code and char in ")]":
            depth = max(0, depth - 1)
        if char == ";" and depth == 0 and not in_code:
            out.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    out.append("".join(current).strip())
    return [item for item in out if item]


def _is_text(value: Any) -> bool:
    return isinstance(value, str) or (isinstance(value, list) and all(isinstance(line, str) for line in value))


def _is_number(value: Any, whole: bool = False) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int,) if whole else (int, float)):
        return False
    return value == value and 0 <= value < 1_000_000


def validate_setup(setup: Any, where: str) -> List[str]:
    errors: List[str] = []
    if not isinstance(setup, dict):
        return ["%s: setup must be an object" % where]
    for key in setup:
        if key not in SETUP_KEYS:
            errors.append("%s: unknown setup key %r (known: %s)" % (where, key, ", ".join(sorted(SETUP_KEYS))))
    fixture = setup.get("fixture", "vault")
    if fixture not in FIXTURES:
        errors.append("%s: unknown fixture %r (known: %s)" % (where, fixture, ", ".join(FIXTURES)))
    if "obsidian" in setup and not isinstance(setup["obsidian"], bool):
        errors.append("%s: obsidian must be true or false" % where)
    if setup.get("toolkit", "current") not in ("current", "absent"):
        errors.append("%s: toolkit must be \"current\" or \"absent\"" % where)
    if setup.get("roles", "current") not in ("current", "v1.7.0", "absent"):
        errors.append("%s: roles must be \"current\", \"v1.7.0\" or \"absent\"" % where)
    if setup.get("index", False) not in (True, False, "legacy"):
        errors.append("%s: index must be true, false or \"legacy\"" % where)
    if setup.get("autonomy", "ask-before-destructive") not in AUTONOMY:
        errors.append("%s: autonomy must be one of %s" % (where, ", ".join(AUTONOMY)))
    if fixture in ("existing", "empty"):
        for key in ("toolkit", "roles", "index", "autonomy"):
            if key in setup:
                errors.append("%s: %r has no meaning with the %r fixture (it is not bootstrapped)" % (where, key, fixture))
    if setup.get("index") and setup.get("toolkit") == "absent":
        errors.append("%s: an index needs the toolkit" % where)
    cwd = setup.get("cwd")
    if cwd is not None:
        try:
            inside(Path("/x"), cwd)
        except RunnerError as exc:
            errors.append("%s: cwd: %s" % (where, exc))
    steps = setup.get("steps", [])
    if not isinstance(steps, list):
        return errors + ["%s: steps must be a list" % where]
    for number, step in enumerate(steps, 1):
        label = "%s: step %d" % (where, number)
        if not isinstance(step, dict):
            errors.append("%s must be an object" % label)
            continue
        verbs = [verb for verb in STEP_VERBS if verb in step]
        if len(verbs) != 1:
            errors.append("%s needs exactly one of: %s" % (label, ", ".join(STEP_VERBS)))
            continue
        verb = verbs[0]
        need = {"write": ("text",), "append": ("text",), "replace": ("old", "new"), "copy": ("to",),
                "age": ("days",), "fixture_file": ("to",), "symlink": ("to",)}.get(verb, ())
        allowed = set(need) | {verb} | ({"allow_fail"} if verb == "tool" else set())
        for key in need:
            if key not in step:
                errors.append("%s (%s) needs %r" % (label, verb, key))
        for key in step:
            if key not in allowed:
                errors.append("%s (%s) has an unknown key %r" % (label, verb, key))
        if verb == "tool" and not (isinstance(step[verb], list) and all(isinstance(a, str) for a in step[verb])):
            errors.append("%s: tool takes a list of arguments" % label)
        if verb == "lint_report":
            spec = step[verb]
            if not isinstance(spec, dict) or set(spec) - {"days_ago", "quick"} \
                    or not _is_number(spec.get("days_ago", 0), whole=True) \
                    or not isinstance(spec.get("quick", False), bool):
                errors.append("%s: lint_report takes an object: {\"days_ago\": N, \"quick\": true|false}" % label)
        for key in ("text", "old", "new"):
            if key in step and key in need and not _is_text(step[key]):
                errors.append("%s (%s): %r must be a string or a list of strings" % (label, verb, key))
        if verb == "age" and "days" in step and not _is_number(step["days"]):
            errors.append("%s (age): 'days' must be a number of days, 0 or more" % label)
        if "allow_fail" in step and not isinstance(step["allow_fail"], bool):
            errors.append("%s (tool): 'allow_fail' must be true or false" % label)
        if verb == "fixture_file" and not (isinstance(step[verb], str) and (FIXTURE_FILES / step[verb]).is_file()
                                           and "/" not in step[verb]):
            errors.append("%s: no file %r in evals/fixtures/" % (label, step[verb]))
        if verb in ("write", "append", "replace", "remove", "copy", "mkdir", "age", "git_repo", "fixture_file", "symlink"):
            values = [] if verb == "fixture_file" else [step[verb]]
            for value in values + ([step["to"]] if "to" in step else []):
                if value == "." and verb == "git_repo":
                    continue
                try:
                    inside(Path("/x"), value)
                except RunnerError as exc:
                    errors.append("%s: %s" % (label, exc))
    return errors


def load_scenarios(evals_dir: Path = EVALS_DIR) -> List[dict]:
    """Every scenario, with `skill`, `file` and the split `expectations` added.
    Raises RunnerError listing every problem found."""
    scenarios: List[dict] = []
    errors: List[str] = []
    seen: Dict[str, str] = {}
    files = sorted(evals_dir.glob("*.evals.json"))
    if not files:
        raise RunnerError("no *.evals.json files in %s" % evals_dir)
    for path in files:
        skill = path.name[: -len(".evals.json")]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append("%s: not readable JSON (%s)" % (path.name, exc))
            continue
        if not isinstance(data, list):
            errors.append("%s: the top level must be a list of scenarios" % path.name)
            continue
        for number, item in enumerate(data, 1):
            where = "%s #%d" % (path.name, number)
            if not isinstance(item, dict):
                errors.append("%s: must be an object" % where)
                continue
            ident = item.get("id")
            if not isinstance(ident, str) or not ID_RE.match(ident):
                errors.append("%s: needs an id of lower-case words joined by hyphens" % where)
                continue
            where = "%s %s" % (path.name, ident)
            if ident in seen:
                errors.append("%s: id already used in %s" % (where, seen[ident]))
            seen[ident] = path.name
            for key in item:
                if key not in SCENARIO_KEYS:
                    errors.append("%s: unknown key %r" % (where, key))
            for key in ("prompt", "expect"):
                if not isinstance(item.get(key), str) or not item[key].strip():
                    errors.append("%s: needs a non-empty %r" % (where, key))
            if isinstance(item.get("expect"), str) and item["expect"].strip() and not split_expectations(item["expect"]):
                errors.append("%s: 'expect' holds no expectation, only separators" % where)
            followups = item.get("followups", [])
            if not isinstance(followups, list) or not all(isinstance(f, str) and f.strip() for f in followups):
                errors.append("%s: followups must be a list of strings" % where)
                followups = []
            tags = item.get("tags", [])
            if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
                errors.append("%s: tags must be a list of strings" % where)
                tags = []
            needs = item.get("needs")
            if needs is not None and not (isinstance(needs, str) and needs.strip()):
                errors.append("%s: needs must say what the scenario waits for, e.g. \"PR #24\"" % where)
                needs = None
            setup = item.get("setup", {})
            errors.extend(validate_setup(setup, where))
            expectations = split_expectations(item["expect"]) if isinstance(item.get("expect"), str) else []
            scenarios.append({
                "id": ident, "skill": skill, "file": path.name,
                "scenario": item.get("scenario", ""),
                "setup": setup if isinstance(setup, dict) else {},
                "prompt": item.get("prompt", ""), "followups": list(followups),
                "expect": item.get("expect", ""), "expectations": expectations,
                "tags": list(tags), "needs": needs,
            })
    if errors:
        raise RunnerError("the eval files have %d problem(s):\n  %s" % (len(errors), "\n  ".join(errors)))
    return scenarios


def select(scenarios: List[dict], skills: List[str], ids: List[str], tags: List[str],
           limit: Optional[int], include_needs: bool = True) -> List[dict]:
    """The scenarios the arguments pick. A scenario marked `needs` describes
    behaviour that is not in this checkout yet; with include_needs False it is
    left out."""
    wanted_skills = set()
    for name in skills:
        full = name if name.startswith("pka-") else "pka-" + name
        if full not in {s["skill"] for s in scenarios}:
            raise RunnerError("no eval file for skill %r" % name)
        wanted_skills.add(full)
    out = []
    for scenario in scenarios:
        if wanted_skills and scenario["skill"] not in wanted_skills:
            continue
        if ids and not any(fnmatch.fnmatchcase(scenario["id"], pattern) for pattern in ids):
            continue
        if tags and not set(tags) & set(scenario["tags"]):
            continue
        if scenario.get("needs") and not include_needs:
            continue
        out.append(scenario)
    for pattern in ids:
        if not any(fnmatch.fnmatchcase(s["id"], pattern) for s in scenarios):
            raise RunnerError("no scenario matches %r (see --list)" % pattern)
    if limit is not None:
        out = out[: max(0, limit)]
    return out


# --------------------------------------------------------------------- workspace setup

def _reference_block(path: Path, heading: str) -> List[str]:
    """The lines of the first fenced block after `heading`."""
    lines = path.read_text(encoding="utf-8").split("\n")
    try:
        start = lines.index(heading)
    except ValueError:
        raise RunnerError("%s has no %r heading; the eval fixtures are built from it" % (path.name, heading))
    opener = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("```")), None)
    if opener is None:
        raise RunnerError("%s: no fenced block after %r" % (path.name, heading))
    closer = next((i for i in range(opener + 1, len(lines)) if lines[i].strip() == "```"), None)
    if closer is None:
        raise RunnerError("%s: the block after %r is never closed" % (path.name, heading))
    return lines[opener + 1:closer]


def repo_map_rows(claude_md: str) -> List[str]:
    return [line for line in claude_md.split("\n") if line.startswith("| `")]


def render_claude_md(rows: List[str], autonomy: str, index: bool) -> str:
    """The workspace CLAUDE.md, from the template bootstrap itself uses."""
    path = REFS / "claude-md-template.md"
    lines = _reference_block(path, "## Template")
    labels = {"ask-before-everything": "Ask before everything",
              "ask-before-destructive": "Ask before destructive actions (recommended)",
              "hands-off": "Hands-off"}
    described = {}
    for line in path.read_text(encoding="utf-8").split("\n"):
        match = re.match(r"^- \*\*(.+?):\*\* (.+)$", line)
        if match:
            described[match.group(1)] = match.group(2)
    if labels[autonomy] not in described:
        raise RunnerError("claude-md-template.md no longer describes the autonomy level %r" % labels[autonomy])
    values = {
        "name": "Sam",
        "autonomy_level_description": "**%s:** %s" % (labels[autonomy], described[labels[autonomy]]),
        "communication_style": "Direct and brief.",
        "communication_guidance": "lead with the answer and keep paragraphs short.",
        "storage_mode": "Index mode" if index else "Markdown-only",
        "storage_mode_description": ("Files are the source of truth; a SQLite index gives full-text search."
                                     if index else "Files only; there is no index."),
        "archive_destination": "knowledge/archived/",
        "date": today().isoformat(),
    }
    out: List[str] = []
    skipping = False
    for line in lines:
        if line.startswith("{{#each"):
            out.extend(rows)
            skipping = True
            continue
        if line.startswith("{{/each"):
            skipping = False
            continue
        if skipping:
            continue
        conditional = re.match(r"^\{\{#if index_mode\}\}(.*)\{\{/if\}\}$", line)
        if conditional:
            if index:
                out.append(conditional.group(1))
            continue
        out.append(re.sub(r"\{\{(\w+)\}\}", lambda m: values.get(m.group(1), m.group(0)), line))
    text = "\n".join(out) + "\n"
    left = sorted(set(re.findall(r"\{\{[^}]*\}\}", text)))
    if left:
        raise RunnerError("claude-md-template.md has placeholders the eval runner does not fill: %s" % ", ".join(left))
    return text


def write_current_roles(ws: Path) -> None:
    roles = ws / ".pka" / "roles"
    roles.mkdir(parents=True, exist_ok=True)
    module = seeds()
    for name in ("orchestrator", "researcher", "librarian"):
        (roles / (name + ".md")).write_text("\n".join(module.role_seed(name)) + "\n", encoding="utf-8")
    shared = module.shared_seed(REFS / "obsidian-conventions.md")
    (roles / "_obsidian.md").write_text("\n".join(shared) + "\n", encoding="utf-8")
    roster = _reference_block(REFS / "role-definitions.md", "## Roster File")
    (roles / "roster.md").write_text("\n".join(roster).replace("{{bootstrap_date}}", "2026-11-01") + "\n",
                                     encoding="utf-8")


def base_env() -> Dict[str, str]:
    """PATH, LANG, LC_*, TERM and TZ from the parent; nothing else."""
    return {key: value for key, value in os.environ.items() if key in PASSED_ENV or key.startswith("LC_")}


def tool_env(home: Path) -> Dict[str, str]:
    """The environment of a setup step (the plugin's own `pka-tools`)."""
    env = base_env()
    if os.environ.get("TMPDIR"):
        env["TMPDIR"] = os.environ["TMPDIR"]
    env.update({"HOME": str(home), "GIT_CONFIG_GLOBAL": str(home / ".gitconfig"),
                "GIT_CONFIG_NOSYSTEM": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    return env


def run_tool(tool: Path, args: List[str], cwd: Path, home: Path, allow_fail: bool = False) -> str:
    proc = subprocess.run([sys.executable, str(tool)] + list(args), cwd=str(cwd), env=tool_env(home),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0 and not allow_fail:
        detail = (proc.stderr or proc.stdout).strip().split("\n")[-1:]
        raise RunnerError("setup: %s %s exited %d: %s" % (tool.name, " ".join(args), proc.returncode,
                                                         detail[0] if detail else ""))
    return proc.stdout


def _fake_git_repo(path: Path) -> None:
    """A directory that looks like a repository, made without running git.
    The evals only need it to exist and to be left alone."""
    git = path / ".git"
    (git / "objects").mkdir(parents=True, exist_ok=True)
    (git / "refs" / "heads").mkdir(parents=True, exist_ok=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git / "config").write_text("[core]\n\trepositoryformatversion = 0\n\tbare = false\n", encoding="utf-8")


def _age(path: Path, days: float) -> None:
    when = time.time() - days * 86400
    targets = [path]
    if path.is_dir():
        for folder, dirs, files in os.walk(str(path)):
            targets.extend(Path(folder) / name for name in dirs + files)
    for target in targets:
        if not target.is_symlink():
            os.utime(str(target), (when, when))


def _lint_report(ws: Path, home: Path, spec: dict) -> None:
    days = int(spec.get("days_ago", 0))
    args = ["lint"] + (["--quick"] if spec.get("quick") else [])
    run_tool(ws / ".pka" / "bin" / "pka-tools", args, ws, home)
    if not days:
        return
    # The tool dates its report with the real clock, so the report is re-dated
    # from the real date, not from PKA_EVAL_TODAY.
    written = dt.date.today()
    then = written - dt.timedelta(days=days)
    source = ws / "owner-inbox" / ("librarian-lint-%s.md" % written.isoformat())
    if not source.exists():
        raise RunnerError("setup: lint wrote no report at %s" % source.relative_to(ws))
    text = source.read_text(encoding="utf-8").replace(written.isoformat(), then.isoformat())
    (ws / "owner-inbox" / ("librarian-lint-%s.md" % then.isoformat())).write_text(text, encoding="utf-8")
    source.unlink()


def apply_step(ws: Path, home: Path, step: dict) -> None:
    verb = next(v for v in STEP_VERBS if v in step)
    if verb == "tool":
        tool = ws / ".pka" / "bin" / "pka-tools"
        if not tool.exists():
            raise RunnerError("setup: a tool step needs the toolkit, and this workspace has none")
        run_tool(tool, step["tool"], ws, home, allow_fail=bool(step.get("allow_fail")))
        return
    if verb == "lint_report":
        _lint_report(ws, home, step["lint_report"])
        return
    if verb == "git_repo":
        _fake_git_repo(ws if step[verb] == "." else inside(ws, step[verb]))
        return
    if verb == "symlink":
        link, target = inside(ws, step[verb]), inside(ws, step["to"])
        link.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(os.path.relpath(str(target), str(link.parent)), str(link))
        return
    if verb == "fixture_file":
        target = inside(ws, step["to"])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(FIXTURE_FILES / step[verb]), str(target))
        return
    path = inside(ws, step[verb])
    if verb == "write":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(as_text(step["text"]).encode("utf-8"))
    elif verb == "append":
        if not path.exists():
            raise RunnerError("setup: cannot append to %s: no such file" % step[verb])
        with open(str(path), "ab") as handle:
            handle.write(as_text(step["text"]).encode("utf-8"))
    elif verb == "replace":
        if not path.exists():
            raise RunnerError("setup: cannot edit %s: no such file" % step[verb])
        data = path.read_bytes()
        old = as_text(step["old"]).encode("utf-8") if isinstance(step["old"], list) else step["old"].encode("utf-8")
        new = as_text(step["new"]).encode("utf-8") if isinstance(step["new"], list) else step["new"].encode("utf-8")
        if old not in data:
            raise RunnerError("setup: %s does not contain the text to replace: %r" % (step[verb], step["old"]))
        path.write_bytes(data.replace(old, new))
    elif verb == "remove":
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(str(path))
        elif path.exists() or path.is_symlink():
            path.unlink()
        else:
            raise RunnerError("setup: cannot remove %s: no such file" % step[verb])
    elif verb == "copy":
        if not path.exists():
            raise RunnerError("setup: cannot copy %s: no such file" % step[verb])
        target = inside(ws, step["to"])
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.is_dir():
            shutil.copytree(str(path), str(target))
        else:
            shutil.copyfile(str(path), str(target))
    elif verb == "mkdir":
        path.mkdir(parents=True, exist_ok=True)
    elif verb == "age":
        if not path.exists():
            raise RunnerError("setup: cannot age %s: no such file" % step[verb])
        _age(path, float(step["days"]))


def _plain_error(exc: BaseException) -> str:
    """One line for an exception, without the absolute path the system adds."""
    if isinstance(exc, OSError) and exc.strerror:
        return exc.strerror
    text = str(exc).strip().split("\n")[0]
    return text or type(exc).__name__


def effective_setup(setup: dict) -> dict:
    """The setup with every default written out."""
    fixture = setup.get("fixture", "vault")
    bootstrapped = fixture in ("vault", "lint")
    return {
        "fixture": fixture,
        "obsidian": bool(setup.get("obsidian", fixture != "empty")),
        "toolkit": setup.get("toolkit", "current") if bootstrapped else "absent",
        "roles": setup.get("roles", "current") if bootstrapped else "absent",
        "index": setup.get("index", False) if bootstrapped else False,
        "autonomy": setup.get("autonomy", "ask-before-destructive") if bootstrapped else None,
        "cwd": setup.get("cwd", "."),
        "steps": list(setup.get("steps", [])),
    }


def build_workspace(setup: dict, ws: Path, home: Path) -> dict:
    """Create the starting state in `ws`. Returns the effective setup."""
    problems = validate_setup(setup, "setup")
    if problems:
        raise RunnerError("; ".join(problems))
    setup = fill_deep(setup)
    plan = effective_setup(setup)
    ws.mkdir(parents=True, exist_ok=True)
    home.mkdir(parents=True, exist_ok=True)
    vault = build_vault()
    fixture = plan["fixture"]
    if fixture != "empty":
        vault.build(ws)
    if fixture == "lint":
        vault.lint_cases(ws)
    if fixture == "existing":
        for name in ("CLAUDE.md", ".pkaignore"):
            (ws / name).unlink()
        for name in (".pka", "owner-inbox", "team-inbox"):
            shutil.rmtree(str(ws / name))
    if fixture != "empty" and not plan["obsidian"]:
        shutil.rmtree(str(ws / "knowledge" / ".obsidian"))
    if fixture in ("vault", "lint"):
        rows = repo_map_rows(vault.LINT_CLAUDE_MD if fixture == "lint" else vault.CLAUDE_MD)
        (ws / "CLAUDE.md").write_text(render_claude_md(rows, plan["autonomy"], bool(plan["index"])), encoding="utf-8")
        (ws / ".pka" / "owner-profile.md").write_text(
            "# Owner Profile\n\n- Name: Sam\n- Role: Engineering manager\n- Style: direct and brief\n", encoding="utf-8")
        (ws / ".pka" / "decision-log.md").write_text(
            "# Decision Log\n\n## 2026-11-01 | Bootstrap\n**Decision:** %s; autonomy: %s; archive destination "
            "knowledge/archived/.\n**Decided by:** Sam\n" % ("index mode" if plan["index"] else "markdown-only mode",
                                                             plan["autonomy"]), encoding="utf-8")
        if plan["roles"] == "current":
            write_current_roles(ws)
        elif plan["roles"] == "v1.7.0":
            (ws / ".pka" / "roles").mkdir(parents=True, exist_ok=True)
            for path in sorted(OLD_ROLES.iterdir()):
                shutil.copyfile(str(path), str(ws / ".pka" / "roles" / path.name))
            write_roster = _reference_block(REFS / "role-definitions.md", "## Roster File")
            (ws / ".pka" / "roles" / "roster.md").write_text(
                "\n".join(write_roster).replace("{{bootstrap_date}}", "2026-06-01") + "\n", encoding="utf-8")
        if plan["toolkit"] == "current":
            run_tool(PLUGIN_TOOL, ["install", "--workspace", str(ws)], ws, home)
        if plan["index"]:
            tool = ws / ".pka" / "bin" / "pka-tools"
            run_tool(tool, ["db", "init"], ws, home)
            run_tool(tool, ["index"], ws, home)
            if plan["index"] == "legacy":
                conn = sqlite3.connect(str(ws / ".pka" / "knowledge.db"))
                try:
                    conn.execute("PRAGMA user_version = 0")
                    conn.commit()
                finally:
                    conn.close()
    for number, step in enumerate(plan["steps"], 1):
        try:
            apply_step(ws, home, step)
        except RunnerError:
            raise
        except (OSError, ValueError, TypeError, AttributeError, shutil.Error) as exc:
            verb = next(v for v in STEP_VERBS if v in step)
            shown = step[verb] if isinstance(step[verb], str) else verb
            raise RunnerError("setup: step %d (%s %s) cannot be applied: %s" % (
                number, verb, shown if len(str(shown)) <= 80 else str(shown)[:79] + "…", _plain_error(exc)))
    cwd = inside(ws, plan["cwd"]) if plan["cwd"] != "." else ws
    if not cwd.is_dir():
        raise RunnerError("setup: cwd %r is not a folder in the workspace" % plan["cwd"])
    return plan


# --------------------------------------------------------------------- snapshot and diff

TEXT_LIMIT = 200_000


def snapshot(root: Path) -> Dict[str, dict]:
    """{relative path: {sha256, size}} for every file under `root`. Symbolic
    links are recorded by their target and never followed."""
    out: Dict[str, dict] = {}
    if not root.exists():
        return out
    for folder, dirs, files in os.walk(str(root), followlinks=False):
        dirs.sort()
        for name in sorted(files) + [d for d in dirs if os.path.islink(os.path.join(folder, d))]:
            path = Path(folder) / name
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                out[rel] = {"link": os.readlink(str(path)), "sha256": None, "size": 0}
                continue
            try:
                data = path.read_bytes()
            except OSError as exc:
                out[rel] = {"sha256": None, "size": 0, "unreadable": str(exc.strerror or exc)}
                continue
            out[rel] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        empty = [d for d in dirs if not os.path.islink(os.path.join(folder, d))
                 and not os.listdir(os.path.join(folder, d))]
        for name in empty:
            out[(Path(folder) / name).relative_to(root).as_posix() + "/"] = {"sha256": None, "size": 0, "dir": True}
    return out


def _decode(data: bytes) -> Optional[str]:
    if len(data) > TEXT_LIMIT or b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _is_vendored(rel: str) -> bool:
    return rel.startswith(".pka/bin/")


def diff_workspace(start: Path, final: Path, per_file_lines: int = 200) -> dict:
    """What changed between two trees: added, removed and changed paths, and a
    unified diff of every text file among them."""
    before, after = snapshot(start), snapshot(final)
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(rel for rel in set(before) & set(after) if before[rel] != after[rel])
    chunks: List[str] = []
    vendored = [rel for rel in added + removed + changed if _is_vendored(rel)]
    for rel in added + removed + changed:
        if _is_vendored(rel) or rel.endswith("/"):
            continue
        old = (start / rel).read_bytes() if rel in before and before[rel].get("sha256") else b""
        new = (final / rel).read_bytes() if rel in after and after[rel].get("sha256") else b""
        old_text, new_text = _decode(old), _decode(new)
        state = "added" if rel in added else "removed" if rel in removed else "changed"
        if old_text is None or new_text is None:
            chunks.append("--- %s (%s; not text, or too large to show: %d -> %d bytes)\n" % (rel, state, len(old), len(new)))
            continue
        lines = list(difflib.unified_diff(old_text.splitlines(), new_text.splitlines(),
                                          "a/" + rel, "b/" + rel, lineterm="", n=2))
        if len(lines) > per_file_lines:
            cut = len(lines) - per_file_lines
            lines = lines[:per_file_lines] + ["[... %d more diff line(s) of %s not shown ...]" % (cut, rel)]
        chunks.append("\n".join(lines) + "\n")
    return {"added": added, "removed": removed, "changed": changed, "vendored": len(vendored),
            "text": "\n".join(chunks), "start": before, "final": after}


def listing_text(snap: Dict[str, dict]) -> str:
    """A compact listing: one line per file, the vendored toolkit as one line."""
    lines: List[str] = []
    vendored = 0
    for rel in sorted(snap):
        if _is_vendored(rel):
            vendored += 1
            continue
        info = snap[rel]
        if info.get("dir"):
            lines.append("%-12s %8s  %s" % ("(empty dir)", "", rel))
        elif "link" in info:
            lines.append("%-12s %8s  %s -> %s" % ("(link)", "", rel, info["link"]))
        else:
            lines.append("%-12s %8d  %s" % ((info["sha256"] or "unreadable")[:12], info["size"], rel))
    if vendored:
        lines.append("%-12s %8s  .pka/bin/ (the vendored toolkit, %d files)" % ("", "", vendored))
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------- the commands

def allowed_rules(ws: Path, plugin: Path, sandbox: bool) -> List[str]:
    """Permission allow rules for the subject. Everything else is denied
    (`--permission-mode dontAsk`)."""
    rules = ["Read(/%s/**)" % ws, "Read(/%s/**)" % plugin, "Edit(/%s/**)" % ws, "Glob", "Grep", "Skill"]
    tools = [".pka/bin/pka-tools", "./.pka/bin/pka-tools", "%s/.pka/bin/pka-tools" % ws,
             "%s/bootstrap-assets/tools/pka-tools" % plugin]
    scripts = [".pka/upgrade-roles.py", "./.pka/upgrade-roles.py", "%s/.pka/upgrade-roles.py" % ws,
               "%s/bootstrap-assets/scripts/upgrade-roles.py" % plugin]
    for path in tools + scripts:
        rules.append("Bash(python3 %s *)" % path)
        rules.append('Bash(python3 "%s" *)' % path)
    for path in tools[:3]:
        rules.append("Bash(%s *)" % path)
    rules += ["Bash(python3 --version)", 'Bash(python3 -c "import pdfplumber"*)', 'Bash(python3 -c "import pypdf"*)']
    for name in ("ls", "cat", "head", "tail", "wc", "grep", "stat", "which", "date", "pwd", "echo", "test", "cd",
                 "mkdir", "mv", "cp") + (("rm",) if sandbox else ()):
        rules += ["Bash(%s)" % name, "Bash(%s *)" % name]
    return rules


def subject_settings(ws: Path, plugin: Path, sandbox: bool) -> dict:
    settings: dict = {"permissions": {"allow": allowed_rules(ws, plugin, sandbox), "deny": []}}
    if sandbox:
        settings["sandbox"] = {"enabled": True, "failIfUnavailable": True, "allowUnsandboxedCommands": False,
                               "autoAllowBashIfSandboxed": False, "network": {"allowedDomains": []}}
    return settings


def subject_command(cfg: dict, plugin: Path, settings_file: Path, session: Optional[str], resume: bool) -> List[str]:
    cmd = [cfg["claude"], "-p", "--output-format", "stream-json", "--verbose",
           "--plugin-dir", str(plugin), "--model", cfg["model"],
           "--setting-sources", "project", "--strict-mcp-config",
           "--tools", SUBJECT_TOOLS,
           "--permission-mode", "dontAsk", "--permission-prompts", "none",
           "--settings", str(settings_file),
           "--max-turns", str(cfg["max_turns"]), "--max-budget-usd", "%.2f" % cfg["max_usd"]]
    if session is None:
        cmd.append("--no-session-persistence")
    elif resume:
        cmd += ["--resume", session]
    else:
        cmd += ["--session-id", session]
    return cmd


JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "expectations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "met": {"type": "string", "enum": ["yes", "no", "unverifiable"]},
                    "basis": {"type": "string", "enum": ["quote", "absence"]},
                    "quotes": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
                "required": ["index", "met", "basis", "quotes", "reason"],
            },
        },
        "verdict": {"type": "string", "enum": ["pass", "partial", "fail"]},
        "summary": {"type": "string"},
    },
    "required": ["expectations", "verdict", "summary"],
}

JUDGE_SYSTEM = """\
You grade one run of an AI assistant against a numbered list of expectations. You are given the user's \
message(s), the state the workspace started in, a transcript of what the assistant said and every tool it \
called with the result, what the test harness denied, and how the files changed. That is all the evidence \
there is. You have not seen the assistant's instructions and you must not guess at them: grade what happened \
against the expectations exactly as written.

Rules of evidence:
- A claim is not evidence. "I ran the lint", "I've updated the index" or "the file was moved" counts only \
when the transcript shows the tool call that did it, or the workspace diff shows the result. If the assistant \
says it did something and there is no tool call or file change to show for it, the expectation is NOT met.
- An expectation about what the assistant says (it asks, it explains, it reports a number) is met by the \
assistant's own text. Quote it.
- An expectation about what the assistant does (runs a command, writes or moves a file) is met only by a tool \
call or by the diff. Quote the call or the diff line.
- An expectation that something does NOT happen is met when the whole transcript and the whole diff show no \
such thing; use basis "absence" and say in the reason what you looked for. An attempt the harness denied still \
counts as the assistant doing it.
- If the evidence cannot settle an expectation (the run was cut off before that point, the harness blocked a \
step the expectation depends on, the relevant output was withheld or truncated), answer "unverifiable". Never \
give the benefit of the doubt, and never answer "yes" because the behaviour is likely.
- An expectation with several parts is met only when every part is.
- Text marked [withheld] was hidden from you on purpose. Do not infer its content.

For every expectation return: its index; met: "yes", "no" or "unverifiable"; basis: "quote" or "absence"; \
quotes: one to three short passages copied character for character from the evidence (empty only for \
"absence", or when nothing relevant exists); and a one or two sentence reason. Quotes are checked \
mechanically against the evidence: a "yes" whose quotes are not found verbatim is thrown out, so copy, do not \
paraphrase, and keep each quote on one line of the evidence.

Then give the verdict (pass: every expectation met; fail: fewer than half met; partial: anything else) and a \
two or three sentence summary that names the expectations that were not met.

Answer with one JSON object and nothing else."""


def judge_command(cfg: dict) -> List[str]:
    return [cfg["claude"], "-p", "--output-format", "json",
            "--model", cfg["judge_model"],
            "--setting-sources", "", "--strict-mcp-config", "--disable-slash-commands",
            "--no-session-persistence", "--tools", "",
            "--permission-mode", "dontAsk", "--permission-prompts", "none",
            "--max-budget-usd", "%.2f" % cfg["judge_max_usd"],
            "--system-prompt", JUDGE_SYSTEM,
            "--json-schema", json.dumps(JUDGE_SCHEMA, separators=(",", ":"))]


def child_env(cfg: dict, home: Path, tmp: Path, cwd: Path) -> Dict[str, str]:
    """The environment of a `claude` child, subject or judge. It is built
    from a list, not filtered from the parent's:

      from the parent   PATH, LANG, LC_*, TERM, TZ; the variables in AUTH_ENV
                        that are set; and any name given with --pass-env
      set here          HOME and TMPDIR (inside the scratch run folder; HOME
                        is the real one with --home real), PWD (the folder
                        the call starts in), CLAUDE_CONFIG_DIR (where the CLI
                        keeps a stored login), PYTHONDONTWRITEBYTECODE, and
                        with a scratch home the two variables that keep git
                        away from the user's configuration

    Nothing else reaches the child: no token for another service, no cloud
    key, no agent socket, none of the parent session's CLAUDE_* variables."""
    env = base_env()
    for name in AUTH_ENV + tuple(cfg.get("pass_env") or ()):
        if os.environ.get(name):
            env[name] = os.environ[name]
    env.update({"TMPDIR": str(tmp), "PWD": str(cwd), "CLAUDE_CONFIG_DIR": cfg["config_dir"],
                "PYTHONDONTWRITEBYTECODE": "1"})
    if cfg["home"] == "scratch":
        env.update({"HOME": str(home), "GIT_CONFIG_GLOBAL": str(home / ".gitconfig"), "GIT_CONFIG_NOSYSTEM": "1"})
    else:
        env["HOME"] = os.environ.get("HOME") or str(Path.home())
    return env


def shell_line(cmd: List[str], shorten: bool = True) -> str:
    parts = []
    skip_value = False
    for index, arg in enumerate(cmd):
        if skip_value:
            skip_value = False
            continue
        if shorten and arg in ("--system-prompt", "--json-schema") and index + 1 < len(cmd):
            parts += [arg, "'<%s, %d characters>'" % ("judge instructions" if arg == "--system-prompt" else "schema",
                                                     len(cmd[index + 1]))]
            skip_value = True
            continue
        parts.append(shlex.quote(arg))
    return " ".join(parts)


# --------------------------------------------------------------------- running the CLI

AUTH_HINTS = ("failed to authenticate", "oauth session expired", "invalid api key", "not logged in",
              "please run /login", "authentication_error")


def looks_like_auth_failure(text: str) -> bool:
    low = (text or "").lower()
    return any(hint in low for hint in AUTH_HINTS)


def _result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, dict):
                parts.append("[%s block]" % block.get("type", "unknown"))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return "" if content is None else json.dumps(content, ensure_ascii=False)


def parse_stream(lines: List[str]) -> Tuple[List[dict], Optional[dict], dict]:
    """Turn `--output-format stream-json` lines into transcript events.

    Returns (events, the final `result` object or None, the `init` object or {}).
    Events: {"kind": "assistant_text", "text"} | {"kind": "tool_call", "id",
    "name", "input"} | {"kind": "tool_result", "id", "text", "is_error"} |
    {"kind": "injected", "text"} (text the harness put into the conversation,
    such as a skill's body)."""
    events: List[dict] = []
    result: Optional[dict] = None
    init: dict = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind == "system" and item.get("subtype") == "init":
            init = item
        elif kind == "result":
            result = item
        elif kind in ("assistant", "user"):
            if item.get("parent_tool_use_id"):
                continue
            message = item.get("message") or {}
            content = message.get("content")
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            for block in content or []:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if kind == "assistant" and btype == "text" and str(block.get("text", "")).strip():
                    events.append({"kind": "assistant_text", "text": block["text"]})
                elif kind == "assistant" and btype == "tool_use":
                    events.append({"kind": "tool_call", "id": block.get("id"), "name": block.get("name"),
                                   "input": block.get("input") or {}})
                elif kind == "user" and btype == "tool_result":
                    events.append({"kind": "tool_result", "id": block.get("tool_use_id"),
                                   "text": _result_text(block.get("content")),
                                   "is_error": bool(block.get("is_error"))})
                elif kind == "user" and btype == "text":
                    events.append({"kind": "injected", "text": str(block.get("text", ""))})
    return events, result, init


def count_turns(lines: List[str]) -> int:
    """Assistant messages that call a tool (one agentic turn each)."""
    seen = set()
    for line in lines:
        if '"tool_use"' not in line:
            continue
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if item.get("type") == "assistant" and not item.get("parent_tool_use_id"):
            seen.add((item.get("message") or {}).get("id") or len(seen))
    return len(seen)


# Every `claude` child runs in a process group of its own, so that stopping it
# also stops whatever it started. The calls in flight are kept here so that a
# signal to the runner can stop them all.
_LIVE: Dict[int, Tuple["subprocess.Popen[bytes]", List[str]]] = {}
_LIVE_LOCK = threading.RLock()
_STOP = {"signal": None}       # the signal that ended the run, once one has arrived


def _kill_group(proc: "subprocess.Popen[bytes]") -> None:
    """Kill the child and everything in its process group."""
    try:
        if hasattr(os, "killpg"):
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except (OSError, ProcessLookupError):
        try:
            proc.kill()
        except OSError:
            pass


def stop_children(reason: str = "terminated") -> None:
    with _LIVE_LOCK:
        live = list(_LIVE.values())
    for proc, stopped in live:
        stopped.append(reason)
        _kill_group(proc)


def _on_signal(signum, _frame) -> None:
    """SIGINT, SIGTERM or SIGHUP: stop every model call, then unwind through
    the `finally` blocks that remove the run folder."""
    _STOP["signal"] = signum
    stop_children()
    raise KeyboardInterrupt


def run_cli(cmd: List[str], prompt: str, cwd: Path, env: Dict[str, str], raw: Path, timeout: float,
            turn_cap: Optional[int] = None) -> Tuple[List[str], str, Optional[str], int]:
    """Run one `claude -p` call. Returns (stdout lines, stderr text, why the
    runner stopped it or None, exit code)."""
    if _STOP["signal"] is not None:
        raise RunnerError("the run was stopped before this call started")
    raw.parent.mkdir(parents=True, exist_ok=True)
    prompt_file = raw.with_suffix(".prompt.txt")
    prompt_file.write_text(prompt, encoding="utf-8")
    err_file = raw.with_suffix(".stderr.txt")
    stopped: List[str] = []
    lines: List[str] = []
    with open(str(prompt_file), "rb") as stdin, open(str(err_file), "wb") as stderr, \
            open(str(raw), "w", encoding="utf-8") as out:
        try:
            proc = subprocess.Popen(cmd, cwd=str(cwd), env=env, stdin=stdin, stdout=subprocess.PIPE, stderr=stderr,
                                    start_new_session=True)
        except OSError as exc:
            raise RunnerError("cannot run %s: %s" % (cmd[0], exc.strerror or exc))
        with _LIVE_LOCK:
            _LIVE[proc.pid] = (proc, stopped)

        def kill(reason: str) -> None:
            stopped.append(reason)
            _kill_group(proc)

        if _STOP["signal"] is not None:      # the signal arrived while the child was starting
            kill("terminated")
        timer = threading.Timer(timeout, kill, args=("timeout",))
        timer.daemon = True
        timer.start()
        try:
            assert proc.stdout is not None
            turns = 0
            for chunk in proc.stdout:
                line = chunk.decode("utf-8", errors="replace")
                lines.append(line)
                out.write(line)
                if turn_cap is not None and '"tool_use"' in line and not stopped:
                    turns = count_turns(lines)
                    if turns > turn_cap:
                        kill("turn-cap")
            proc.wait()
        finally:
            timer.cancel()
            # The child itself (if an exception got here first) and anything
            # it started and left behind.
            _kill_group(proc)
            proc.wait()
            with _LIVE_LOCK:
                _LIVE.pop(proc.pid, None)
            if proc.stdout is not None:
                proc.stdout.close()
    stderr_text = err_file.read_text(encoding="utf-8", errors="replace")
    return lines, stderr_text, (stopped[0] if stopped else None), proc.returncode


USAGE_KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


def turn_metrics(result: Optional[dict], stopped: Optional[str], code: int) -> dict:
    result = result or {}
    usage = result.get("usage") or {}
    return {
        "cost_usd": float(result.get("total_cost_usd") or 0.0),
        "usage": {key: int(usage.get(key) or 0) for key in USAGE_KEYS},
        "num_turns": result.get("num_turns"),
        "duration_ms": result.get("duration_ms"),
        "subtype": result.get("subtype"),
        "terminal_reason": result.get("terminal_reason"),
        "is_error": bool(result.get("is_error")) if result else True,
        "result": result.get("result"),
        "permission_denials": result.get("permission_denials") or [],
        "stopped": stopped,
        "exit_code": code,
        "had_result": bool(result),
    }


# --------------------------------------------------------------------- evidence for the judge

RESULT_CAP = 3000
TEXT_CAP = 12000
INPUT_CAP = 2500
DIFF_CAP = 60000
LISTING_CAP = 12000


def _clip(text: str, cap: int) -> str:
    if len(text) <= cap:
        return text
    head = cap * 2 // 3
    tail = cap - head
    return "%s\n[... %d characters not shown ...]\n%s" % (text[:head], len(text) - cap, text[-tail:])


def _reads_plugin_text(call: dict, plugin: str) -> bool:
    """True when the result of this call is the plugin's own prose (skill
    text, references, changelog) rather than the output of a tool."""
    name = call.get("name")
    payload = call.get("input") or {}
    if name == "Skill":
        return True
    blob = json.dumps(payload, ensure_ascii=False)
    if plugin not in blob:
        return False
    if name in ("Read", "Grep"):
        return True
    if name == "Bash":
        command = str(payload.get("command", ""))
        runs_tool = re.search(r"python3?\s+\"?%s/bootstrap-assets/(tools/pka-tools|scripts/upgrade-roles\.py)\"?(\s|$)"
                              % re.escape(plugin), command)
        reads = re.search(r"(^|[\s;&|(])(cat|head|tail|grep|sed|awk|less|more|rg)\s", command)
        return bool(reads) or not runs_tool
    return False


def render_transcript(turns: List[dict], plugin: Path) -> str:
    """The transcript as the judge sees it. Skill text is withheld: the
    result of every Skill call, of every read of a plugin file, and every
    message the harness injected into the conversation."""
    plugin_text = str(plugin)
    out: List[str] = []
    step = 0
    for number, turn in enumerate(turns, 1):
        out.append("=== USER MESSAGE %d ===\n%s\n" % (number, turn["prompt"]))
        calls: Dict[str, dict] = {}
        for event in turn["events"]:
            step += 1
            kind = event["kind"]
            if kind == "assistant_text":
                out.append("[%d] ASSISTANT SAYS:\n%s\n" % (step, _clip(event["text"], TEXT_CAP)))
            elif kind == "tool_call":
                calls[event.get("id") or ""] = event
                shown = json.dumps(event["input"], ensure_ascii=False, sort_keys=True)
                out.append("[%d] TOOL CALL %s: %s\n" % (step, event["name"], _clip(shown, INPUT_CAP)))
            elif kind == "tool_result":
                call = calls.get(event.get("id") or "", {})
                label = "TOOL RESULT (error)" if event["is_error"] else "TOOL RESULT"
                if call and _reads_plugin_text(call, plugin_text) and not event["is_error"]:
                    out.append("[%d] %s: [withheld: %d characters of the plugin's own text]\n"
                               % (step, label, len(event["text"])))
                else:
                    out.append("[%d] %s:\n%s\n" % (step, label, _clip(event["text"], RESULT_CAP)))
            elif kind == "injected":
                out.append("[%d] HARNESS MESSAGE: [withheld: %d characters]\n" % (step, len(event["text"])))
        notes = []
        if turn["metrics"].get("stopped"):
            notes.append("the runner stopped this turn early (%s)" % turn["metrics"]["stopped"])
        if turn["metrics"].get("subtype") not in (None, "success"):
            notes.append("the run ended with %s" % turn["metrics"]["subtype"])
        for denial in turn["metrics"].get("permission_denials", []):
            notes.append("the harness denied: %s %s" % (
                denial.get("tool_name", "a tool"),
                _clip(json.dumps(denial.get("tool_input", {}), ensure_ascii=False, sort_keys=True), 400)))
        if notes:
            out.append("HARNESS NOTES for message %d:\n- %s\n" % (number, "\n- ".join(notes)))
    return "\n".join(out)


def describe_setup(plan: dict) -> str:
    lines = []
    fixture = plan["fixture"]
    lines.append({"vault": "A bootstrapped PKA workspace (fixture \"vault\"): CLAUDE.md with a Repo Map, knowledge/ "
                           "with AI, leadership, personnel, lab-notebook, reference and archived folders, projects/orion, "
                           "meeting-notes/ with one earshot capture directory, owner-inbox/ and team-inbox/.",
                  "lint": "The bootstrapped \"vault\" workspace plus seeded lint problems (duplicate files, broken links, "
                          "duplicate people, two topic wikis under knowledge/topics/, old files in team-inbox/unsorted/).",
                  "existing": "Folders of notes (knowledge/, projects/, meeting-notes/) that have never been bootstrapped: "
                              "no CLAUDE.md, no .pka/, no .pkaignore, no inboxes.",
                  "empty": "An empty folder."}[fixture])
    if fixture != "empty":
        lines.append("knowledge/.obsidian/ %s." % ("exists (an Obsidian vault)" if plan["obsidian"] else "does not exist"))
    if fixture in ("vault", "lint"):
        lines.append("Toolkit (.pka/bin/pka-tools): %s." % {"current": "installed, same version as the plugin",
                                                           "absent": "not installed, no .pka/manifest.json"}[plan["toolkit"]])
        lines.append("Role files (.pka/roles/): %s." % {"current": "current seeds", "absent": "none",
                                                       "v1.7.0": "as v1.7.0 seeded them, including the obsolete "
                                                                 "commit/push sections and _git-protocol.md; no _obsidian.md"}[plan["roles"]])
        lines.append("Index (.pka/knowledge.db): %s." % {True: "present and current", False: "none (markdown-only mode)",
                                                        "legacy": "present, schema version 0 (needs migrating)"}[plan["index"]])
        lines.append("Autonomy level in CLAUDE.md: %s." % plan["autonomy"])
    if plan["cwd"] != ".":
        lines.append("The session starts in the subfolder %s." % plan["cwd"])
    if plan["steps"]:
        lines.append("Then, in order:")
        for step in plan["steps"]:
            shown = {key: (_clip(as_text(value), 600) if key in ("text", "old", "new") else value)
                     for key, value in step.items()}
            lines.append("- " + json.dumps(shown, ensure_ascii=False))
    return "\n".join(lines)


def build_evidence(scenario: dict, plan: dict, turns: List[dict], diff: dict, home_changes: List[str],
                   plugin: Path) -> str:
    expectations = "\n".join("%d. %s" % (n, text) for n, text in enumerate(scenario["expectations"], 1))
    changed = []
    for label in ("added", "removed", "changed"):
        names = [rel for rel in diff[label] if not _is_vendored(rel)]
        changed.append("%s (%d): %s" % (label, len(names), ", ".join(names) if names else "none"))
    if diff.get("vendored"):
        changed.append("vendored toolkit files added or changed under .pka/bin/: %d" % diff["vendored"])
    parts = [
        "# EXPECTATIONS (grade each one)\n" + expectations,
        "# STARTING STATE\n" + describe_setup(plan),
        "# TRANSCRIPT\n" + render_transcript(turns, plugin),
        "# WORKSPACE CHANGES (start of run -> end of run)\n" + "\n".join(changed),
        "# FILES WRITTEN OUTSIDE THE WORKSPACE (in the scratch home directory)\n"
        + ("\n".join(home_changes) if home_changes else "none"),
        "# DIFF OF TEXT FILES\n" + (_clip(diff["text"], DIFF_CAP) if diff["text"].strip() else "(no text file changed)"),
        "# FINAL FILE LISTING (sha256 prefix, size, path)\n" + _clip(listing_text(diff["final"]), LISTING_CAP),
    ]
    return "\n\n".join(parts) + "\n"


# --------------------------------------------------------------------- judging

class JudgeError(Exception):
    pass


def _find_json_object(text: str) -> Optional[dict]:
    """The first JSON object in `text` that has an "expectations" list."""
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            value, _end = decoder.raw_decode(text[match.start():])
        except ValueError:
            continue
        if isinstance(value, dict) and isinstance(value.get("expectations"), list):
            return value
    return None


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_judge_response(stdout: str, expectations: List[str], evidence: str) -> dict:
    """Read the judge's answer out of the CLI's `--output-format json`
    envelope, check it against the expectations and the evidence, and work out
    the verdict. Raises JudgeError when there is no usable answer."""
    stdout = stdout.strip()
    if not stdout:
        raise JudgeError("the judge printed nothing")
    envelope: Any = None
    try:
        envelope = json.loads(stdout)
    except ValueError:
        pass
    if isinstance(envelope, list):          # some versions print every event as one array
        envelope = next((e for e in reversed(envelope) if isinstance(e, dict) and e.get("type") == "result"), None)
    answer: Optional[dict] = None
    cost = 0.0
    usage: dict = {}
    if isinstance(envelope, dict) and ("result" in envelope or "structured_output" in envelope
                                       or envelope.get("type") == "result"):
        cost = float(envelope.get("total_cost_usd") or 0.0)
        usage = envelope.get("usage") or {}
        if envelope.get("is_error"):
            message = str(envelope.get("result") or envelope.get("subtype") or "unknown error")
            if looks_like_auth_failure(message):
                raise AuthError(message)
            raise JudgeError("the judge call failed: %s" % message.split("\n")[0])
        structured = envelope.get("structured_output")
        if isinstance(structured, dict) and isinstance(structured.get("expectations"), list):
            answer = structured
        elif isinstance(envelope.get("result"), str):
            answer = _find_json_object(envelope["result"])
    elif isinstance(envelope, dict) and isinstance(envelope.get("expectations"), list):
        answer = envelope
    else:
        answer = _find_json_object(stdout)
    if answer is None:
        raise JudgeError("the judge's answer has no JSON object with an \"expectations\" list")

    haystack = _squash(evidence)
    by_index: Dict[int, dict] = {}
    for item in answer["expectations"]:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("index"))
        except (TypeError, ValueError):
            continue
        if 1 <= index <= len(expectations) and index not in by_index:
            by_index[index] = item
    graded: List[dict] = []
    for index, text in enumerate(expectations, 1):
        item = by_index.get(index)
        if item is None:
            graded.append({"index": index, "expectation": text, "met": "unverifiable", "basis": "quote", "quotes": [],
                           "quotes_found": [], "reason": "The judge gave no answer for this expectation.",
                           "downgraded": "no answer"})
            continue
        met = item.get("met") if item.get("met") in ("yes", "no", "unverifiable") else "unverifiable"
        basis = item.get("basis") if item.get("basis") in ("quote", "absence") else "quote"
        quotes = [str(q) for q in item.get("quotes") or [] if isinstance(q, (str, int, float)) and str(q).strip()]
        found = [len(_squash(q)) >= 6 and _squash(q) in haystack for q in quotes]
        downgraded = None
        if item.get("met") not in ("yes", "no", "unverifiable"):
            downgraded = "the judge's answer was not yes, no or unverifiable"
        elif met == "yes" and basis == "quote" and not any(found):
            met = "unverifiable"
            downgraded = ("the judge said yes but quoted nothing" if not quotes
                          else "the judge said yes but none of its quotes is in the evidence")
        graded.append({"index": index, "expectation": text, "met": met, "basis": basis, "quotes": quotes,
                       "quotes_found": found, "reason": str(item.get("reason", "")).strip(), "downgraded": downgraded})
    met_count = sum(1 for g in graded if g["met"] == "yes")
    return {"expectations": graded, "met": met_count, "total": len(graded),
            "verdict": verdict_for(met_count, len(graded)),
            "judge_verdict": answer.get("verdict") if answer.get("verdict") in ("pass", "partial", "fail") else None,
            "summary": str(answer.get("summary", "")).strip(),
            "cost_usd": cost, "usage": {key: int(usage.get(key) or 0) for key in USAGE_KEYS}}


def verdict_for(met: int, total: int) -> str:
    """pass: every expectation met. fail: fewer than half. partial: the rest."""
    if total and met == total:
        return "pass"
    if met * 2 < total or total == 0:
        return "fail"
    return "partial"


def run_judge(cfg: dict, scenario: dict, evidence: str, judge_dir: Path, raw: Path, home: Path, tmp: Path) -> dict:
    judge_dir.mkdir(parents=True, exist_ok=True)
    lines, stderr, stopped, code = run_cli(judge_command(cfg), evidence, judge_dir,
                                           child_env(cfg, home, tmp, judge_dir), raw, cfg["timeout"])
    stdout = "".join(lines)
    if stopped:
        raise JudgeError("the judge call was stopped (%s)" % stopped)
    if not stdout.strip():
        detail = stderr.strip().split("\n")[0] if stderr.strip() else "exit code %d" % code
        if looks_like_auth_failure(stderr):
            raise AuthError(detail)
        raise JudgeError("the judge printed nothing: %s" % detail)
    return parse_judge_response(stdout, scenario["expectations"], evidence)


# --------------------------------------------------------------------- one scenario

def plugin_path_allowed(rel: str) -> bool:
    """True for a checkout-relative path that may go into the plugin copy:
    one of PLUGIN_FILES, or a file under one of PLUGIN_DIRS."""
    if not isinstance(rel, str) or not rel or rel.startswith("/") or "\\" in rel or "\0" in rel:
        return False
    parts = rel.split("/")
    if any(part in ("", ".", "..") for part in parts) or parts[0] in NEVER_COPIED:
        return False
    if any(part in PLUGIN_SKIP_NAMES or part.endswith(".pyc") for part in parts):
        return False
    if len(parts) == 1:
        return rel in PLUGIN_FILES
    return parts[0] in PLUGIN_DIRS


def tracked_files(repo: Path) -> Optional[List[str]]:
    """The files git tracks under the plugin's parts, or None when `repo` is
    not a git checkout. This is the one git command the runner runs, and it
    only reads."""
    if not (repo / ".git").exists():
        return None
    git = shutil.which("git")
    if not git:
        raise RunnerError("%s is a git checkout and git is not installed: the plugin copy is made from the files "
                          "git tracks, so that an untracked file is never handed to the model" % repo)
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    names = [name for name in PLUGIN_DIRS + PLUGIN_FILES if (repo / name).exists()]
    try:
        proc = subprocess.run([git, "-C", str(repo), "ls-files", "-z", "--"] + names, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        raise RunnerError("cannot list the tracked files of %s: %s" % (repo, exc.strerror or exc))
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip().split("\n")[0]
        raise RunnerError("cannot list the tracked files of %s: %s" % (repo, detail or "git exited %d" % proc.returncode))
    return sorted(name for name in proc.stdout.decode("utf-8", errors="surrogateescape").split("\0") if name)


def plugin_files(repo: Path) -> List[str]:
    """Checkout-relative paths of the files the plugin copy holds.

    In a git checkout: the tracked files under PLUGIN_DIRS and PLUGIN_FILES,
    with the content they have in the working tree. An untracked file is
    never listed, wherever it is. Outside git (an unpacked archive) there is
    no such list, so every file under those parts is taken. In both cases a
    symbolic link is left out, and a path that is not under the parts is
    refused."""
    listed = tracked_files(repo)
    if listed is None:
        listed = []
        for name in PLUGIN_DIRS:
            for folder, dirs, files in os.walk(str(repo / name), followlinks=False):
                dirs[:] = sorted(d for d in dirs if d not in PLUGIN_SKIP_NAMES)
                listed.extend((Path(folder) / f).relative_to(repo).as_posix() for f in sorted(files))
        listed.extend(name for name in PLUGIN_FILES if (repo / name).exists())
    out = []
    for rel in listed:
        if any(part in PLUGIN_SKIP_NAMES or part.endswith(".pyc") for part in rel.split("/")):
            continue
        if not plugin_path_allowed(rel):
            raise RunnerError("refusing to copy %r into the plugin copy: it is not under %s" % (
                rel, ", ".join(PLUGIN_DIRS + PLUGIN_FILES)))
        source = repo / rel
        if source.is_symlink() or not source.is_file():
            continue            # a link, or tracked and deleted in the working tree
        out.append(rel)
    return out


def lock_tree(root: Path) -> None:
    """Take write permission off every file and every folder under `root`,
    and off `root` itself: nothing can be changed, added, renamed or removed
    inside it without a chmod first (which the subject's allow list does not
    have)."""
    no_write = ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
    for folder, dirs, files in os.walk(str(root), topdown=False):
        for name in files + dirs:
            path = os.path.join(folder, name)
            if not os.path.islink(path):
                os.chmod(path, os.stat(path).st_mode & no_write)
    os.chmod(str(root), os.stat(str(root)).st_mode & no_write)


def build_plugin_copy(target: Path, repo: Path = REPO) -> Path:
    """Copy the plugin's files from `repo` to `target` and lock the copy."""
    files = plugin_files(repo)
    remove_tree(target)
    target.mkdir(parents=True)
    for rel in files:
        destination = target / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(repo / rel), str(destination))
        shutil.copymode(str(repo / rel), str(destination))
    if not (target / ".claude-plugin" / "plugin.json").is_file():
        remove_tree(target)
        raise RunnerError("the plugin copy has no .claude-plugin/plugin.json: is %s the plugin's checkout, with its "
                          "files tracked by git?" % repo)
    lock_tree(target)
    return target


def prepare_plugin(run_dir: Path, repo: Path = REPO) -> Path:
    """The run's own copy of the plugin (see `plugin_files` for what is in
    it). No subject is given this copy: each scenario gets a copy of it."""
    plugin = run_dir / "plugin"
    if plugin.exists():
        return plugin
    return build_plugin_copy(plugin, repo)


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for rel, info in sorted(snapshot(root).items()):
        digest.update(("%s\0%s\0" % (rel, info.get("sha256") or info.get("link") or "")).encode("utf-8"))
    return digest.hexdigest()


class PluginCopies:
    """The plugin copies of one run.

    `master` is built once from the checkout and never handed to a subject.
    Every scenario gets its own locked copy of it, in its own scratch
    folder, so that one scenario cannot change what the next one loads, and
    a change is attributed to the scenario that made it even with --jobs.
    After every scenario its copy is hashed and compared with the master,
    and the master is compared with what it was when it was built; if the
    master was changed it is rebuilt before the next scenario."""

    def __init__(self, run_dir: Path, repo: Path = REPO):
        self.repo = repo
        self.master = prepare_plugin(run_dir, repo)
        self.digest = tree_digest(self.master)
        self.rebuilt = 0
        self._lock = threading.Lock()

    def copy_for(self, base: Path) -> Path:
        target = base / "plugin"
        with self._lock:
            self._check_master()
            remove_tree(target)
            shutil.copytree(str(self.master), str(target), symlinks=True)
        lock_tree(target)
        return target

    def _check_master(self) -> bool:
        """Rebuild the master if it is not what was built. True when it was intact."""
        if self.master.is_dir() and tree_digest(self.master) == self.digest:
            return True
        build_plugin_copy(self.master, self.repo)
        self.digest = tree_digest(self.master)
        self.rebuilt += 1
        return False

    def unchanged(self, copy: Path) -> bool:
        """True when the scenario's copy and the master are both as built."""
        with self._lock:
            before = self.digest
            intact = self._check_master()
            return intact and copy.is_dir() and tree_digest(copy) == before


def check_work_dir(work_dir: Path) -> None:
    """Scratch workspaces must not be made at the filesystem root or inside
    this checkout (a stopped run would leave untracked folders in it, and a
    workspace there would have the checkout above it)."""
    resolved = work_dir.resolve()
    if resolved == Path(resolved.anchor):
        raise RunnerError("the work folder cannot be the filesystem root (%s); choose another --work-dir" % resolved)
    if resolved == REPO or REPO in resolved.parents:
        raise RunnerError("the work folder %s is inside this checkout; choose a --work-dir (or a TMPDIR) outside %s"
                          % (resolved, REPO))


def ancestors_clean(path: Path) -> Optional[str]:
    """A workspace must not sit under a folder that Claude Code or the
    bootstrap skill would mistake for part of it."""
    for parent in path.resolve().parents:
        for name in ("CLAUDE.md", "CLAUDE.local.md", ".pka"):
            if (parent / name).exists():
                return str(parent / name)
    return None


def scenario_dirs(run_dir: Path, scenario: dict) -> Dict[str, Path]:
    base = run_dir / scenario["id"]
    return {"base": base, "ws": base / "ws", "start": base / "start", "home": base / "home",
            "tmp": base / "tmp", "judge": base / "judge", "settings": base / "settings.json",
            "plugin": base / "plugin"}


def prepare_scenario(cfg: dict, scenario: dict, run_dir: Path, plugins: PluginCopies) -> dict:
    dirs = scenario_dirs(run_dir, scenario)
    remove_tree(dirs["base"])
    for key in ("ws", "home", "tmp", "judge"):
        dirs[key].mkdir(parents=True)
    plugin = plugins.copy_for(dirs["base"])
    plan = build_workspace(scenario["setup"], dirs["ws"], dirs["home"])
    shutil.copytree(str(dirs["ws"]), str(dirs["start"]), symlinks=True)
    home_before = snapshot(dirs["home"])
    settings = subject_settings(dirs["ws"], plugin, cfg["sandbox"] == "require")
    dirs["settings"].write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    cwd = dirs["ws"] if plan["cwd"] == "." else dirs["ws"] / plan["cwd"]
    multi = bool(scenario["followups"])
    session = str(uuid.uuid4()) if multi else None
    commands = [subject_command(cfg, plugin, dirs["settings"], session, False)]
    commands += [subject_command(cfg, plugin, dirs["settings"], session, True) for _ in scenario["followups"]]
    return {"dirs": dirs, "plan": plan, "cwd": cwd, "session": session, "commands": commands, "plugin": plugin,
            "home_before": home_before, "prompts": [fill(scenario["prompt"])] + [fill(f) for f in scenario["followups"]]}


def forget_session(cfg: dict, session: Optional[str], ws: Path) -> List[str]:
    """Remove what the CLI kept about this run in its own configuration
    directory: the session transcript (found by the id the runner generated)
    and the project folder it made for the scratch workspace, if that is now
    empty. Returns what could not be removed."""
    left: List[str] = []
    projects = Path(cfg["config_dir"]) / "projects"
    if not projects.is_dir():
        return left
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(ws))
    candidates = [p for p in projects.iterdir() if p.name.startswith(slug)]
    for project in candidates:
        if session:
            for path in project.glob(session + "*"):
                try:
                    if path.is_dir():
                        shutil.rmtree(str(path))
                    else:
                        path.unlink()
                except OSError:
                    left.append(str(path))
        for folder in (project / "memory", project):
            try:
                folder.rmdir()
            except OSError:
                if folder.exists() and any(folder.iterdir()):
                    left.append(str(folder))
    return left


INVALID_NOTE = ("the plugin copy this scenario was given was changed during it, so what the subject loaded cannot be "
                "trusted: the result is not graded. The next scenario starts from a fresh copy; run this one again "
                "with --resume")


def run_scenario(cfg: dict, scenario: dict, run_dir: Path, plugins: PluginCopies, results_dir: Path) -> dict:
    started = time.time()
    record: dict = {
        "id": scenario["id"], "skill": scenario["skill"], "scenario": scenario["scenario"],
        "prompt": scenario["prompt"], "followups": scenario["followups"],
        "expectations": scenario["expectations"], "setup": scenario["setup"], "tags": scenario["tags"],
        "needs": scenario.get("needs"),
        "status": "error", "verdict": None, "met": 0, "total": len(scenario["expectations"]),
        "model": cfg["model"], "judge_model": cfg["judge_model"], "plugin_version": plugin_version(),
        "started": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "error": None, "turns": [], "judgement": None, "plugin_copy_changed": False,
        "subject_cost_usd": 0.0, "judge_cost_usd": 0.0, "cost_usd": 0.0,
        "tokens": {key: 0 for key in USAGE_KEYS}, "judge_tokens": {key: 0 for key in USAGE_KEYS},
    }
    raw_dir = results_dir / "raw"
    prepared = None
    forgotten = False
    checked = False
    try:
        prepared = prepare_scenario(cfg, scenario, run_dir, plugins)
        dirs, plan, plugin = prepared["dirs"], prepared["plan"], prepared["plugin"]
        record["effective_setup"] = plan
        record["commands"] = {"subject": [shell_line(c) for c in prepared["commands"]],
                              "judge": shell_line(judge_command(cfg))}
        env = child_env(cfg, dirs["home"], dirs["tmp"], prepared["cwd"])
        turns: List[dict] = []
        for number, (prompt, cmd) in enumerate(zip(prepared["prompts"], prepared["commands"]), 1):
            raw = raw_dir / ("%s.turn%d.jsonl" % (scenario["id"], number))
            lines, stderr, stopped, code = run_cli(cmd, prompt, prepared["cwd"], env, raw, cfg["timeout"],
                                                   turn_cap=cfg["max_turns"] + 2)
            events, result, init = parse_stream(lines)
            metrics = turn_metrics(result, stopped, code)
            turns.append({"prompt": prompt, "events": events, "metrics": metrics})
            record["subject_cost_usd"] += metrics["cost_usd"]
            for key in USAGE_KEYS:
                record["tokens"][key] += metrics["usage"][key]
            if init and number == 1:
                record["subject_model"] = init.get("model")
                record["subject_tools"] = init.get("tools")
                record["cli_version"] = init.get("claude_code_version")
            message = str(metrics.get("result") or "") + "\n" + stderr
            if metrics["is_error"] and looks_like_auth_failure(message):
                raise AuthError((str(metrics.get("result") or "").strip() or stderr.strip()).split("\n")[0])
            if stopped == "terminated":
                raise RunnerError("the run was stopped before this scenario finished")
            if not metrics["had_result"] and not stopped:
                detail = stderr.strip().split("\n")[0] if stderr.strip() else "exit code %d, no result event" % code
                raise RunnerError("the subject run produced no result: %s" % detail)
            if stopped or metrics["subtype"] not in (None, "success"):
                break       # capped or failed: the follow-ups would answer nothing
        record["turns"] = [{"prompt": t["prompt"], **t["metrics"]} for t in turns]
        record["transcript"] = [{"turn": n, **event} for n, t in enumerate(turns, 1) for event in t["events"]]
        diff = diff_workspace(dirs["start"], dirs["ws"])
        home_after = snapshot(dirs["home"])
        home_changes = sorted("~/" + rel for rel in home_after
                              if home_after[rel] != prepared["home_before"].get(rel))
        record["workspace"] = diff
        record["home_changes"] = home_changes
        left = forget_session(cfg, prepared["session"], dirs["ws"])
        forgotten = True
        unchanged = plugins.unchanged(plugin)
        checked = True
        record["isolation"] = {
            "sandbox": cfg["sandbox"], "home": cfg["home"],
            "plugin_copy_unchanged": unchanged,
            "left_in_cli_config": left,
        }
        evidence = build_evidence(scenario, plan, turns, diff, home_changes, plugin)
        record["evidence"] = evidence
        if not unchanged:
            raise InvalidRun(INVALID_NOTE)
        record["status"] = "judge-error"
        judgement = run_judge(cfg, scenario, evidence, dirs["judge"],
                              raw_dir / ("%s.judge.json" % scenario["id"]), dirs["home"], dirs["tmp"])
        apply_judgement(record, judgement)
    except AuthError:
        raise
    except JudgeError as exc:
        record["error"] = str(exc)
    except InvalidRun:
        pass                    # marked below, with every other way a changed copy is found
    except RunnerError as exc:
        record["error"] = str(exc)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        # A scenario must never take the run down with it: the others still
        # run, and the summary is still written.
        record["error"] = "%s: %s" % (type(exc).__name__, _plain_error(exc))
    finally:
        # The plugin copy is checked after EVERY scenario, also one that
        # stopped on an error before the check above.
        if prepared is not None and not checked:
            try:
                unchanged = plugins.unchanged(prepared["plugin"])
            except (OSError, RunnerError):
                unchanged = False
            record.setdefault("isolation", {"sandbox": cfg["sandbox"], "home": cfg["home"]})
            record["isolation"]["plugin_copy_unchanged"] = unchanged
        if prepared is not None and not record["isolation"]["plugin_copy_unchanged"]:
            record.update({"plugin_copy_changed": True, "status": "invalid", "verdict": None, "judgement": None,
                           "error": INVALID_NOTE})
        record["cost_usd"] = round(record["subject_cost_usd"] + record["judge_cost_usd"], 6)
        record["wall_seconds"] = round(time.time() - started, 1)
        if prepared is not None and not forgotten:
            forget_session(cfg, prepared["session"], prepared["dirs"]["ws"])
        if prepared is not None and not cfg["keep_workspaces"]:
            remove_tree(prepared["dirs"]["base"])
    return record


def apply_judgement(record: dict, judgement: dict) -> None:
    record["judge_cost_usd"] = judgement.pop("cost_usd", 0.0)
    record["judge_tokens"] = judgement.pop("usage", {key: 0 for key in USAGE_KEYS})
    record["judgement"] = judgement
    record["verdict"] = judgement["verdict"]
    record["met"] = judgement["met"]
    record["total"] = judgement["total"]
    record["status"] = "graded"
    record["error"] = None
    record["cost_usd"] = round(record.get("subject_cost_usd", 0.0) + record["judge_cost_usd"], 6)


# --------------------------------------------------------------------- results

def result_path(results_dir: Path, scenario: dict) -> Path:
    return results_dir / scenario["skill"] / (scenario["id"] + ".json")


def write_result(results_dir: Path, record: dict) -> Path:
    path = results_dir / record["skill"] / (record["id"] + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".json.part")
    temp.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(str(temp), str(path))
    return path


def read_results(results_dir: Path) -> List[dict]:
    out = []
    for path in sorted(results_dir.glob("*/*.json")):
        if path.parent.name == "raw":
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(record, dict) and all(isinstance(record.get(key), str) for key in ("id", "status", "skill")):
            out.append(record)
    return out


def summarise(records: List[dict]) -> dict:
    """Totals for a set of results."""
    verdicts = ("pass", "partial", "fail")
    by_skill: Dict[str, dict] = {}
    totals = {"scenarios": len(records), "graded": 0, "pass": 0, "partial": 0, "fail": 0, "error": 0,
              "invalid": [], "cost_usd": 0.0, "subject_cost_usd": 0.0, "judge_cost_usd": 0.0, "wall_seconds": 0.0,
              "tokens": {key: 0 for key in USAGE_KEYS}, "expectations_met": 0, "expectations": 0}
    for record in records:
        skill = by_skill.setdefault(record["skill"], {"scenarios": 0, "pass": 0, "partial": 0, "fail": 0,
                                                      "error": 0, "cost_usd": 0.0})
        skill["scenarios"] += 1
        if record.get("status") == "graded" and record.get("verdict") in verdicts:
            totals["graded"] += 1
            totals[record["verdict"]] += 1
            skill[record["verdict"]] += 1
            totals["expectations_met"] += int(record.get("met") or 0)
            totals["expectations"] += int(record.get("total") or 0)
        else:
            totals["error"] += 1
            skill["error"] += 1
            if record.get("plugin_copy_changed") or record.get("status") == "invalid":
                totals["invalid"].append(record["id"])
        for key in ("cost_usd", "subject_cost_usd", "judge_cost_usd", "wall_seconds"):
            totals[key] += float(record.get(key) or 0.0)
        skill["cost_usd"] += float(record.get("cost_usd") or 0.0)
        for source in ("tokens", "judge_tokens"):
            for key in USAGE_KEYS:
                totals["tokens"][key] += int((record.get(source) or {}).get(key) or 0)
    for key in ("cost_usd", "subject_cost_usd", "judge_cost_usd"):
        totals[key] = round(totals[key], 4)
    totals["wall_seconds"] = round(totals["wall_seconds"], 1)
    for skill in by_skill.values():
        skill["cost_usd"] = round(skill["cost_usd"], 4)
    totals["invalid"].sort()
    return {"totals": totals, "by_skill": dict(sorted(by_skill.items()))}


def _cell(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def first_unmet(record: dict) -> str:
    if record.get("status") != "graded":
        return "%s: %s" % (record.get("status"), record.get("error") or "")
    for item in (record.get("judgement") or {}).get("expectations", []):
        if item["met"] != "yes":
            return "%d. %s (%s)" % (item["index"], item["expectation"], item["met"])
    return ""


def render_summary(records: List[dict], meta: dict) -> str:
    """The readable summary: totals, one row per scenario, then every
    expectation that was not met with the judge's evidence."""
    summary = summarise(records)
    totals = summary["totals"]
    lines = ["# Eval run %s" % meta.get("name", ""), ""]
    lines.append("- Plugin version: %s; subject model: %s; judge model: %s" % (
        meta.get("plugin_version", "?"), meta.get("model", "?"), meta.get("judge_model", "?")))
    lines.append("- Isolation: OS sandbox %s; home directory: %s%s" % (
        meta.get("sandbox", "?"), meta.get("home", "?"),
        "; extra variables passed to the CLI: %s" % ", ".join(meta["pass_env"]) if meta.get("pass_env") else ""))
    lines.append("- Scenarios: %d (graded %d, not graded %d)" % (totals["scenarios"], totals["graded"], totals["error"]))
    if totals["invalid"]:
        lines.append("- INVALID: %d scenario(s) changed the plugin copy they were given and were not graded: %s. "
                     "Each scenario runs with its own copy, so the others are not affected. Run these again with "
                     "--resume, and read their transcripts to see what was changed."
                     % (len(totals["invalid"]), ", ".join(totals["invalid"])))
    lines.append("- Verdicts: %d pass, %d partial, %d fail; expectations met: %d of %d" % (
        totals["pass"], totals["partial"], totals["fail"], totals["expectations_met"], totals["expectations"]))
    lines.append("- Cost as reported by the CLI: $%.4f (subject $%.4f, judge $%.4f)" % (
        totals["cost_usd"], totals["subject_cost_usd"], totals["judge_cost_usd"]))
    tokens = totals["tokens"]
    lines.append("- Tokens: %d in, %d out, %d cache read, %d cache write" % (
        tokens["input_tokens"], tokens["output_tokens"], tokens["cache_read_input_tokens"],
        tokens["cache_creation_input_tokens"]))
    lines.append("- Time, summed over scenarios: %.0f s" % totals["wall_seconds"])
    lines += ["", "| Skill | Scenarios | Pass | Partial | Fail | Not graded | Cost |", "|---|---|---|---|---|---|---|"]
    for name, skill in summary["by_skill"].items():
        lines.append("| %s | %d | %d | %d | %d | %d | $%.4f |" % (
            name, skill["scenarios"], skill["pass"], skill["partial"], skill["fail"], skill["error"], skill["cost_usd"]))
    lines += ["", "| Scenario | Skill | Verdict | Met | Turns | Cost | Seconds | First expectation not met |",
              "|---|---|---|---|---|---|---|---|"]
    for record in sorted(records, key=lambda r: (r["skill"], r["id"])):
        turns = sum(int(t.get("num_turns") or 0) for t in record.get("turns", []))
        verdict = record.get("verdict") if record.get("status") == "graded" else record.get("status")
        lines.append("| %s | %s | %s | %d/%d | %d | $%.4f | %.0f | %s |" % (
            record["id"], record["skill"], verdict, int(record.get("met") or 0), int(record.get("total") or 0),
            turns, float(record.get("cost_usd") or 0.0), float(record.get("wall_seconds") or 0.0),
            _cell(_clip(first_unmet(record), 160))))
    details = []
    for record in sorted(records, key=lambda r: (r["skill"], r["id"])):
        if record.get("status") != "graded":
            details += ["", "## %s — %s" % (record["id"], record.get("status")), "", record.get("error") or ""]
            continue
        unmet = [i for i in record["judgement"]["expectations"] if i["met"] != "yes"]
        if not unmet:
            continue
        details += ["", "## %s — %s (%d/%d)" % (record["id"], record["verdict"], record["met"], record["total"]), ""]
        if record["judgement"].get("summary"):
            details += [record["judgement"]["summary"], ""]
        for item in unmet:
            details.append("- **%d. %s** — %s. %s" % (item["index"], item["expectation"], item["met"], item["reason"]))
            if item.get("downgraded"):
                details.append("  - Downgraded by the runner: %s." % item["downgraded"])
            for quote, found in zip(item["quotes"], item["quotes_found"]):
                details.append("  - %s `%s`" % ("Evidence:" if found else "Quote not found in the evidence:",
                                                 _clip(quote, 300).replace("`", "'").replace("\n", " ")))
    if details:
        lines += ["", "# Expectations not met"] + details
    return "\n".join(lines) + "\n"


def write_summary(results_dir: Path, meta: dict) -> Tuple[dict, str]:
    records = read_results(results_dir)
    summary = summarise(records)
    text = render_summary(records, meta)
    (results_dir / "summary.json").write_text(json.dumps({"meta": meta, **summary}, indent=2) + "\n", encoding="utf-8")
    (results_dir / "summary.md").write_text(text, encoding="utf-8")
    return summary, text


# --------------------------------------------------------------------- the run

def isolation_report(cfg: dict) -> str:
    sandbox = cfg["sandbox"] == "require"
    lines = [
        "How a run is confined:",
        "  workspace   a fresh folder per scenario under %s; it is the only folder the file tools may write" % cfg["work_dir"],
        "  plugin      a locked copy per scenario of the files git tracks under %s (nothing from docs/, evals/, tests/;"
        % ", ".join(name + "/" for name in PLUGIN_DIRS),
        "              no untracked file); it is hashed after every scenario, and a scenario that changed it is not graded",
        "  tools       %s; no web access, no subagents, no MCP servers" % SUBJECT_TOOLS,
        "  permissions --permission-mode dontAsk: anything not on the allow list is denied, nobody is asked",
        "  shell       allow list only: the two copies of pka-tools and upgrade-roles.py, ls cat head tail wc grep stat which",
        "              date pwd echo test cd mkdir mv cp%s; no git, no curl, no pip, no python -c beyond two import checks"
        % (" rm" if sandbox else ""),
        "  home        %s" % ("a scratch HOME and TMPDIR inside the run folder (the CLI's own config directory is passed "
                             "by name so it can log in)" if cfg["home"] == "scratch"
                             else "the real HOME (--home real); TMPDIR inside the run folder"),
        "  environment built from a list: PATH, LANG, LC_*, TERM, TZ, HOME, TMPDIR, PWD, CLAUDE_CONFIG_DIR and, when set,",
        "              %s%s. The subject's shell can read these." % (
            ", ".join(AUTH_ENV), "; also, because you asked (--pass-env): %s" % ", ".join(cfg["pass_env"])
            if cfg.get("pass_env") else ""),
        "  settings    user and local settings, user CLAUDE.md, user plugins and MCP servers are not loaded",
    ]
    if sandbox:
        lines.append("  OS sandbox  required: shell commands run inside Claude Code's sandbox (writes limited to the "
                     "workspace and temp, no network); the CLI refuses to start without it")
    else:
        lines.append("  OS sandbox  OFF (--sandbox off): shell commands are limited by the allow list only. `mv`, `cp` "
                     "and `mkdir` could reach a path outside the workspace if the model asked for one.")
    return "\n".join(lines)


def sandbox_available() -> Optional[str]:
    """None when Claude Code's OS sandbox can work here, else why not."""
    if sys.platform == "darwin":
        return None
    if sys.platform.startswith("linux"):
        missing = [name for name in ("bwrap", "socat") if not shutil.which(name)]
        if missing:
            return "%s not installed (on Linux the sandbox needs bubblewrap and socat)" % " and ".join(missing)
        return None
    return "Claude Code has no OS sandbox on %s" % sys.platform


def resolve_claude(explicit: Optional[str]) -> str:
    name = explicit or os.environ.get("PKA_EVAL_CLAUDE") or "claude"
    found = shutil.which(name)
    if not found:
        raise RunnerError("cannot find the Claude Code CLI (%r); pass --claude /path/to/claude" % name)
    return found


def make_config(args: argparse.Namespace, need_cli: bool) -> dict:
    work_dir = Path(args.work_dir).resolve() if args.work_dir else Path(tempfile.gettempdir()).resolve()
    cfg = {
        "claude": resolve_claude(args.claude) if need_cli else (args.claude or "claude"),
        "model": args.model, "judge_model": args.judge_model,
        "max_turns": args.max_turns, "max_usd": args.max_usd, "judge_max_usd": args.judge_max_usd,
        "max_total_usd": args.max_total_usd, "timeout": args.timeout,
        "sandbox": args.sandbox, "home": args.home, "keep_workspaces": args.keep_workspaces,
        "work_dir": str(work_dir),
        "config_dir": os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude"),
        "pass_env": sorted(set(getattr(args, "pass_env", None) or [])),
    }
    for name in cfg["pass_env"]:
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
            raise RunnerError("--pass-env takes the name of an environment variable, not %r" % name)
    return cfg


def make_run_dir(cfg: dict) -> Path:
    base = Path(cfg["work_dir"])
    if not base.is_dir():
        raise RunnerError("--work-dir %s is not a folder" % base)
    check_work_dir(base)
    try:
        run_dir = Path(tempfile.mkdtemp(prefix="pka-evals.", dir=str(base))).resolve()
    except OSError as exc:
        raise RunnerError("cannot create a run folder in %s: %s" % (base, exc.strerror or exc))
    dirty = ancestors_clean(run_dir / "x" / "ws")
    if dirty:
        remove_tree(run_dir)
        raise RunnerError("%s exists above the work folder; a scenario would inherit it. Choose another --work-dir" % dirty)
    return run_dir


def dry_run(cfg: dict, scenarios: List[dict], out) -> int:
    run_dir = make_run_dir(cfg)
    failures = 0
    try:
        plugins = PluginCopies(run_dir)
        out.write("Dry run: %d scenario(s). Workspaces are built and nothing is sent to a model.\n\n" % len(scenarios))
        out.write(isolation_report(cfg) + "\n\n")
        out.write("Caps: %d turns and $%.2f per subject call, $%.2f per judge call, $%.2f for the whole run, "
                  "%d s per call.\n\n" % (cfg["max_turns"], cfg["max_usd"], cfg["judge_max_usd"],
                                          cfg["max_total_usd"], cfg["timeout"]))
        for scenario in scenarios:
            try:
                prepared = prepare_scenario(cfg, scenario, run_dir, plugins)
            except (RunnerError, OSError, ValueError, TypeError, AttributeError) as exc:
                failures += 1
                out.write("%s  SETUP FAILED: %s\n\n" % (
                    scenario["id"], exc if isinstance(exc, RunnerError) else _plain_error(exc)))
                continue
            files = snapshot(prepared["dirs"]["ws"])
            out.write("%s  (%s; %d expectation(s); %d user message(s))%s\n" % (
                scenario["id"], scenario["skill"], len(scenario["expectations"]), len(prepared["prompts"]),
                "  needs " + scenario["needs"] if scenario.get("needs") else ""))
            out.write("  workspace: %s (%d files)\n" % (prepared["dirs"]["ws"], len(files)))
            out.write("  cwd:       %s\n" % prepared["cwd"])
            for number, (prompt, cmd) in enumerate(zip(prepared["prompts"], prepared["commands"]), 1):
                out.write("  message %d: %s\n" % (number, _clip(prompt.replace("\n", " "), 200)))
                out.write("  command %d: %s < prompt\n" % (number, shell_line(cmd)))
            out.write("  judge:     %s < evidence\n\n" % shell_line(judge_command(cfg)))
            if not cfg["keep_workspaces"]:
                remove_tree(prepared["dirs"]["base"])
        out.write("%d scenario(s) prepared, %d failed to set up.\n" % (len(scenarios) - failures, failures))
        if cfg["keep_workspaces"]:
            out.write("Workspaces kept in %s\n" % run_dir)
    finally:
        if not cfg["keep_workspaces"]:
            remove_tree(run_dir)
    return 2 if failures else 0


def real_run(cfg: dict, scenarios: List[dict], results_dir: Path, jobs: int, out) -> int:
    if cfg["sandbox"] == "require":
        why = sandbox_available()
        if why:
            raise RunnerError("the OS sandbox is required and is not available: %s. Install it, or pass --sandbox off "
                              "to run confined by permission rules only (see evals/README.md)" % why)
    results_dir.mkdir(parents=True, exist_ok=True)
    done = {r["id"]: r for r in read_results(results_dir) if r.get("status") == "graded"}
    todo = [s for s in scenarios if s["id"] not in done]
    meta = {"name": results_dir.name, "plugin_version": plugin_version(), "model": cfg["model"],
            "judge_model": cfg["judge_model"], "sandbox": cfg["sandbox"], "home": cfg["home"],
            "max_turns": cfg["max_turns"], "max_usd": cfg["max_usd"], "max_total_usd": cfg["max_total_usd"],
            "pass_env": cfg["pass_env"], "selected": [s["id"] for s in scenarios]}
    (results_dir / "run.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    out.write("%d scenario(s) selected, %d already graded in %s, %d to run.\n" % (
        len(scenarios), len(scenarios) - len(todo), results_dir, len(todo)))
    out.write(isolation_report(cfg) + "\n\n")
    run_dir = make_run_dir(cfg)
    lock = threading.Lock()
    state = {"spent": sum(float(r.get("cost_usd") or 0.0) for r in done.values()), "skipped": 0, "abort": None}

    def work(scenario: dict) -> None:
        with lock:
            if state["abort"] or _STOP["signal"] is not None:
                return
            if state["spent"] >= cfg["max_total_usd"]:
                state["skipped"] += 1
                return
        try:
            record = run_scenario(cfg, scenario, run_dir, plugins, results_dir)
        except AuthError as exc:
            with lock:
                state["abort"] = "Claude Code could not authenticate: %s" % exc
            return
        if _STOP["signal"] is not None and record["status"] != "graded":
            return              # cut short by the signal: nothing worth keeping, --resume runs it again
        write_result(results_dir, record)
        with lock:
            state["spent"] += record["cost_usd"]
            label = record["verdict"] if record["status"] == "graded" else record["status"]
            out.write("  %-8s %-44s %d/%d  $%.4f  %.0fs%s\n" % (
                label, record["id"], record["met"], record["total"], record["cost_usd"], record["wall_seconds"],
                "  " + record["error"] if record["error"] else ""))
            out.flush()

    try:
        plugins = PluginCopies(run_dir)
        with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
            list(pool.map(work, todo))
    except KeyboardInterrupt:
        stop_children()
        if read_results(results_dir):
            write_summary(results_dir, meta)        # what finished before the signal is still summarised
        raise
    finally:
        if not cfg["keep_workspaces"]:
            remove_tree(run_dir)
        else:
            out.write("Workspaces kept in %s\n" % run_dir)
    summary, text = write_summary(results_dir, meta)
    if state["abort"]:
        raise AuthError("%s. Nothing more was run; results so far are in %s" % (state["abort"], results_dir))
    out.write("\n" + text)
    if state["skipped"]:
        out.write("\n%d scenario(s) were not run: the run reached its cap of $%.2f. Continue with --resume %s\n" % (
            state["skipped"], cfg["max_total_usd"], results_dir))
    out.write("\nResults: %s\n" % results_dir)
    totals = summary["totals"]
    if totals["error"] or state["skipped"]:
        return 2
    return 0 if totals["pass"] == totals["graded"] else 1


def rejudge(cfg: dict, results_dir: Path, scenarios: List[dict], out) -> int:
    """Grade stored transcripts again (after changing an expectation or the
    judge), without running the subject."""
    by_id = {s["id"]: s for s in scenarios}
    records = [r for r in read_results(results_dir) if r["id"] in by_id and r.get("evidence")
               and not r.get("plugin_copy_changed")]
    if not records:
        raise RunnerError("no stored transcripts for the selected scenarios in %s" % results_dir)
    meta_path = results_dir / "run.json"
    meta: Any = {"name": results_dir.name}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RunnerError("%s is not readable JSON (%s); restore it, or delete it to grade without it"
                              % (meta_path, _plain_error(exc)))
        if not isinstance(meta, dict):
            raise RunnerError("%s does not hold a JSON object; restore it, or delete it to grade without it" % meta_path)
    run_dir = make_run_dir(cfg)
    try:
        for record in records:
            scenario = by_id[record["id"]]
            evidence = record["evidence"]
            head, sep, rest = evidence.partition("\n\n# STARTING STATE\n")
            if sep:
                numbered = "\n".join("%d. %s" % (n, t) for n, t in enumerate(scenario["expectations"], 1))
                evidence = "# EXPECTATIONS (grade each one)\n" + numbered + sep + rest
            dirs = scenario_dirs(run_dir, scenario)
            for key in ("home", "tmp", "judge"):
                dirs[key].mkdir(parents=True, exist_ok=True)
            record["expectations"] = scenario["expectations"]
            record["evidence"] = evidence
            try:
                judgement = run_judge(cfg, scenario, evidence, dirs["judge"],
                                      results_dir / "raw" / ("%s.judge.json" % scenario["id"]), dirs["home"], dirs["tmp"])
                apply_judgement(record, judgement)
            except JudgeError as exc:
                record["status"], record["error"] = "judge-error", str(exc)
            write_result(results_dir, record)
            out.write("  %-8s %s\n" % (record["verdict"] if record["status"] == "graded" else record["status"], record["id"]))
    finally:
        remove_tree(run_dir)
    meta["judge_model"] = cfg["judge_model"]
    _summary, text = write_summary(results_dir, meta)
    out.write("\n" + text)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evals/run.py", description="Run the pka-skills behavioural evals with Claude Code and grade them.")
    pick = parser.add_argument_group("which scenarios")
    pick.add_argument("--skill", action="append", default=[], metavar="NAME",
                      help="only this skill's scenarios (pka-wiki or wiki); repeatable")
    pick.add_argument("--scenario", action="append", default=[], metavar="ID",
                      help="only this scenario id (shell wildcards allowed); repeatable")
    pick.add_argument("--tag", action="append", default=[], metavar="TAG", help="only scenarios with this tag, e.g. smoke")
    pick.add_argument("--limit", type=int, metavar="N", help="at most N scenarios, in file order")
    pick.add_argument("--include-needs", action="store_true",
                      help="also run scenarios marked `needs` (behaviour that waits for another change to be merged)")
    mode = parser.add_argument_group("what to do")
    mode.add_argument("--dry-run", action="store_true", help="build the workspaces and print the commands; call no model")
    mode.add_argument("--list", action="store_true", help="list the selected scenarios and exit")
    mode.add_argument("--validate", action="store_true", help="check the eval files and exit")
    mode.add_argument("--resume", metavar="DIR", help="continue a run: skip the scenarios already graded in DIR")
    mode.add_argument("--rejudge", metavar="DIR", help="grade the transcripts stored in DIR again, without the subject")
    mode.add_argument("--results-dir", metavar="DIR", help="where to write results (default evals/results/<timestamp>)")
    caps = parser.add_argument_group("models and caps")
    caps.add_argument("--model", default=DEFAULTS["model"], help="subject model (default %(default)s)")
    caps.add_argument("--judge-model", default=DEFAULTS["judge_model"], help="judge model (default %(default)s)")
    caps.add_argument("--max-turns", type=int, default=DEFAULTS["max_turns"], metavar="N",
                      help="agentic turns per user message (default %(default)s)")
    caps.add_argument("--max-usd", type=float, default=DEFAULTS["max_usd"], metavar="USD",
                      help="spend cap per subject call (default %(default)s)")
    caps.add_argument("--judge-max-usd", type=float, default=DEFAULTS["judge_max_usd"], metavar="USD",
                      help="spend cap per judge call (default %(default)s)")
    caps.add_argument("--max-total-usd", type=float, default=DEFAULTS["max_total_usd"], metavar="USD",
                      help="stop starting scenarios once the run has cost this much (default %(default)s)")
    caps.add_argument("--timeout", type=int, default=DEFAULTS["timeout"], metavar="SECONDS",
                      help="wall-clock limit per model call (default %(default)s)")
    caps.add_argument("--jobs", type=int, default=1, metavar="N", help="scenarios to run at once (default 1)")
    env = parser.add_argument_group("environment")
    env.add_argument("--claude", metavar="PATH", help="the Claude Code CLI (default: `claude` on PATH, or $PKA_EVAL_CLAUDE)")
    env.add_argument("--sandbox", choices=("require", "off"), default="require",
                     help="require Claude Code's OS sandbox for shell commands (default), or run without it")
    env.add_argument("--home", choices=("scratch", "real"), default="scratch",
                     help="give the run a scratch HOME (default), or the real one if the CLI cannot log in otherwise")
    env.add_argument("--work-dir", metavar="DIR", help="where scratch workspaces are made (default: the system temp "
                                                       "folder); not inside this checkout")
    env.add_argument("--pass-env", action="append", default=[], metavar="NAME",
                     help="also pass this environment variable to the CLI, and so to the commands the model runs "
                          "(repeatable). By default only PATH, LANG, LC_*, TERM, TZ and the CLI's login variables "
                          "are passed")
    env.add_argument("--keep-workspaces", action="store_true", help="do not delete the scratch workspaces afterwards")
    return parser


def main(argv: Optional[List[str]] = None, out=None) -> int:
    """Run with handlers for SIGINT, SIGTERM and SIGHUP that stop every model
    call (each runs in a process group of its own) before the run folder is
    removed. The handlers are put back afterwards."""
    previous = {}
    _STOP["signal"] = None
    if threading.current_thread() is threading.main_thread():
        for name in ("SIGINT", "SIGTERM", "SIGHUP"):
            if hasattr(signal, name):
                previous[getattr(signal, name)] = signal.signal(getattr(signal, name), _on_signal)
    try:
        return _main(argv, out)
    except KeyboardInterrupt:           # a second signal, during the clean-up of the first
        stop_children()
        return 130
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def _main(argv: Optional[List[str]] = None, out=None) -> int:
    out = out or sys.stdout
    args = build_parser().parse_args(argv)
    try:
        for name in ("max_turns", "jobs", "timeout"):
            if getattr(args, name) < 1:
                raise RunnerError("--%s must be at least 1" % name.replace("_", "-"))
        for name in ("max_usd", "judge_max_usd", "max_total_usd"):
            if getattr(args, name) <= 0:
                raise RunnerError("--%s must be more than 0" % name.replace("_", "-"))
        scenarios = load_scenarios(EVALS_DIR)
        selected = select(scenarios, args.skill, args.scenario, args.tag, args.limit)
        runnable = select(scenarios, args.skill, args.scenario, args.tag, args.limit, include_needs=args.include_needs)
        waiting = [s for s in selected if s not in runnable]
        if args.validate:
            out.write("%d scenarios in %d files, %d expectations: no problems.\n" % (
                len(scenarios), len({s["file"] for s in scenarios}), sum(len(s["expectations"]) for s in scenarios)))
            return 0
        if args.list:
            for scenario in selected:
                out.write("%-46s %-14s %2d expectations, %d message(s)%s%s\n" % (
                    scenario["id"], scenario["skill"], len(scenario["expectations"]), 1 + len(scenario["followups"]),
                    "  [" + ", ".join(scenario["tags"]) + "]" if scenario["tags"] else "",
                    "  needs " + scenario["needs"] if scenario.get("needs") else ""))
            out.write("%d scenario(s), %d of them waiting for another change (`needs`)\n" % (
                len(selected), sum(1 for s in selected if s.get("needs"))))
            return 0
        if not selected:
            raise RunnerError("no scenario selected")
        if args.dry_run:
            return dry_run(make_config(args, need_cli=False), selected, out)
        if waiting:
            out.write("Left out, waiting for another change (run them with --include-needs): %s\n" % ", ".join(
                "%s (%s)" % (s["id"], s["needs"]) for s in waiting))
        selected = runnable
        if not selected:
            raise RunnerError("every selected scenario is marked `needs`; pass --include-needs to run them")
        cfg = make_config(args, need_cli=True)
        if args.rejudge:
            results_dir = Path(args.rejudge)
            if not results_dir.is_dir():
                raise RunnerError("no results folder at %s" % results_dir)
            return rejudge(cfg, results_dir, selected, out)
        if args.resume:
            results_dir = Path(args.resume)
            if not results_dir.is_dir():
                raise RunnerError("no results folder at %s" % results_dir)
        elif args.results_dir:
            results_dir = Path(args.results_dir)
        else:
            results_dir = RESULTS_DIR / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        return real_run(cfg, selected, results_dir.resolve(), args.jobs, out)
    except RunnerError as exc:
        sys.stderr.write("evals/run.py: %s\n" % exc)
        return 2
    except KeyboardInterrupt:
        stop_children()
        signum = _STOP["signal"]
        sys.stderr.write("evals/run.py: %s; the model calls were stopped and the scratch folder removed. "
                         "Continue with --resume\n" % ("interrupted" if signum in (None, signal.SIGINT)
                                                       else "stopped by signal %d" % signum))
        return 130 if signum in (None, signal.SIGINT) else 128 + int(signum)


if __name__ == "__main__":
    sys.exit(main())
