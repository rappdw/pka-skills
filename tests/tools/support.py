"""Shared helpers for the pka-tools tests.

The tests run the tool the way a workspace does: the plugin's copy is
installed into a temporary workspace with `pka-tools install`, and every
command after that goes through the vendored `.pka/bin/pka-tools`. So the
code under test is the code that ships, by the path it ships through.
"""
from __future__ import annotations

import difflib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parent.parent.parent
ASSETS = REPO / "bootstrap-assets"
PLUGIN_TOOL = ASSETS / "tools" / "pka-tools"
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
sys.path.insert(0, str(ASSETS / "tools"))
sys.dont_write_bytecode = True

import build_vault  # noqa: E402


def split_lines(text: str) -> List[str]:
    parts = text.split("\n")
    lines = [part + "\n" for part in parts[:-1]]
    if parts[-1] != "":
        lines.append(parts[-1])
    return lines


class ToolsCase(unittest.TestCase):
    """A temporary workspace with the tool installed and git isolated."""

    fixture = True      # build the fixture vault into the workspace
    install = True      # run `pka-tools install`

    def setUp(self) -> None:
        base = tempfile.mkdtemp(prefix="pka-tools-test.", dir=os.environ.get("TMPDIR") or None)
        self.base = Path(os.path.realpath(base))
        self.addCleanup(self._cleanup)
        self.ws = self.base / "ws"
        self.ws.mkdir()
        home = self.base / "home"
        home.mkdir()
        self.env = dict(os.environ)
        for name in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME",
                     "GIT_COMMITTER_EMAIL", "EMAIL", "XDG_CONFIG_HOME", "WORKSPACE_ROOT"):
            self.env.pop(name, None)
        self.env.update({
            "HOME": str(home),
            "GIT_CONFIG_GLOBAL": str(home / ".gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        self.git_config("user.email", "test@pka-skills.test")
        self.git_config("user.name", "PKA Test Runner")
        self.git_config("init.defaultBranch", "main")
        self.git_config("commit.gpgsign", "false")
        if self.fixture:
            build_vault.build(self.ws)
        else:
            (self.ws / ".pka").mkdir()
        if self.install:
            code, out, err = self.plugin("install", "--workspace", str(self.ws))
            self.assertEqual(code, 0, err)

    def _cleanup(self) -> None:
        for root, dirs, _files in os.walk(str(self.base)):
            for name in dirs:
                try:
                    os.chmod(os.path.join(root, name), 0o755)
                except OSError:
                    pass
        shutil.rmtree(str(self.base), ignore_errors=True)

    # ---- running things --------------------------------------------
    def git_config(self, key: str, value: str) -> None:
        subprocess.run(["git", "config", "--global", key, value], env=self.env, check=True)

    def git(self, repo: Path, *args: str) -> str:
        proc = subprocess.run(["git", "-C", str(repo)] + list(args), env=self.env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc.returncode, 0, "git %s failed: %s" % (" ".join(args), proc.stderr))
        return proc.stdout

    def _run(self, tool: Path, args: Tuple[str, ...], cwd: Optional[Path]) -> Tuple[int, str, str]:
        proc = subprocess.run([sys.executable, str(tool)] + list(args), cwd=str(cwd or self.ws),
                              env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def plugin(self, *args: str, cwd: Optional[Path] = None) -> Tuple[int, str, str]:
        """Run the plugin's copy (only `install` should need this)."""
        return self._run(PLUGIN_TOOL, args, cwd)

    def tool(self, *args: str, cwd: Optional[Path] = None) -> Tuple[int, str, str]:
        """Run the copy vendored into the workspace."""
        return self._run(self.ws / ".pka" / "bin" / "pka-tools", args, cwd)

    def ok(self, *args: str, cwd: Optional[Path] = None) -> str:
        code, out, err = self.tool(*args, cwd=cwd)
        self.assertEqual(code, 0, "pka-tools %s exited %d\n%s\n%s" % (" ".join(args), code, out, err))
        return out

    def json(self, *args: str, cwd: Optional[Path] = None) -> dict:
        if "--" in args:
            cut = args.index("--")
            args = args[:cut] + ("--json",) + args[cut:]
        else:
            args = args + ("--json",)
        return json.loads(self.ok(*args, cwd=cwd))

    # ---- files ------------------------------------------------------
    def path(self, rel: str) -> Path:
        return self.ws / rel

    def read(self, rel: str) -> bytes:
        return self.path(rel).read_bytes()

    def text(self, rel: str) -> str:
        return self.read(rel).decode("utf-8")

    def write(self, rel: str, data) -> Path:
        path = self.path(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
        return path

    def snapshot(self, rel: str = "knowledge") -> Dict[str, bytes]:
        out = {}
        root = self.path(rel)
        for path in sorted(root.rglob("*")):
            if path.is_file() and ".git" not in path.relative_to(root).parts:
                out[path.relative_to(self.ws).as_posix()] = path.read_bytes()
        return out

    def changed(self, before: Dict[str, bytes], after: Dict[str, bytes]) -> List[str]:
        names = sorted(set(before) | set(after))
        return [name for name in names if before.get(name) != after.get(name)]

    def init_child_repo(self, rel: str = "knowledge") -> Path:
        repo = self.path(rel)
        self.git(repo, "init", "-q", "-b", "main")
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-q", "-m", "baseline")
        return repo


def removed_and_added(before: bytes, after: bytes) -> List[Tuple[List[str], List[str]]]:
    """Line-level changes as (removed lines, added lines) pairs."""
    old = split_lines(before.decode("utf-8", errors="surrogateescape"))
    new = split_lines(after.decode("utf-8", errors="surrogateescape"))
    out = []
    matcher = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    for tag, a1, a2, b1, b2 in matcher.get_opcodes():
        if tag != "equal":
            out.append((old[a1:a2], new[b1:b2]))
    return out
