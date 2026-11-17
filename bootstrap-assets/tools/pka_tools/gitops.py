"""Path-scoped commits in child repositories.

Rules, from `.pka/roles/_git-protocol.md`:
  - Stage and commit by path. Never `git add -A`.
  - Only child repositories (knowledge/, projects/<name>/) are committed
    automatically. The workspace root is the user's review gate: changes
    there are staged at most.
  - Every commit carries the trailer, verbatim.
  - A commit that fails is reported as a failure. Nothing is retried, reset
    or forced.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from .errors import EXIT_ENV, EXIT_FAIL, EXIT_USAGE, ToolError
from .workspace import Workspace

TRAILER = "Co-Authored-By: Claude <noreply@anthropic.com>"


def _git(repo: Path, *args: str) -> Tuple[int, str, str]:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    proc = subprocess.run(
        ["git", "-C", str(repo)] + list(args),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
    )
    return proc.returncode, proc.stdout, proc.stderr


def require_git() -> None:
    if shutil.which("git") is None:
        raise ToolError("git is not on PATH", EXIT_ENV)


def toplevel(folder: Path) -> Optional[Path]:
    """The repository that contains `folder`, or None."""
    probe = folder
    while not probe.is_dir():
        if probe.parent == probe:
            return None
        probe = probe.parent
    code, out, _ = _git(probe, "rev-parse", "--show-toplevel")
    if code != 0 or not out.strip():
        return None
    return Path(os.path.realpath(out.strip()))


def commit(
    ws: Workspace,
    subject: str,
    paths: List[str],
    body: str = "",
    stage_only: bool = False,
) -> dict:
    """Stage `paths` and commit exactly those paths in their child repository.

    Returns a result with `committed` and, when nothing was committed, the
    `reason`:
      no-repo     the paths are not inside a git repository
      root-repo   the repository is the workspace root (or encloses it);
                  it is never committed automatically
      no-changes  the paths have nothing to commit
      staged      --stage-only was given
    """
    require_git()
    subject = subject.strip()
    if not stage_only and (not subject or "\n" in subject):
        raise ToolError("the commit subject must be one non-empty line", EXIT_USAGE)
    if not paths:
        raise ToolError("no paths given; name every file this commit should contain", EXIT_USAGE)

    absolute = [ws.resolve(path) for path in paths]
    # Git reports a repository by its physical path. Compare like with like,
    # so that a knowledge/ reached through a symbolic link still resolves.
    physical = []
    for path in absolute:
        parent, name = os.path.split(str(path))
        physical.append(Path(os.path.realpath(parent)) / name)
    repos = []
    for path in physical:
        repo = toplevel(path.parent)
        if repo not in repos:
            repos.append(repo)
    if len(repos) > 1:
        raise ToolError(
            "the paths are in more than one repository (%s); commit each repository separately"
            % ", ".join(str(repo) for repo in repos),
            EXIT_USAGE,
        )
    repo = repos[0]
    result = {"committed": False, "reason": None, "repo": None, "sha": None, "paths": []}
    if repo is None:
        result["reason"] = "no-repo"
        return result

    # A child repository is one whose top level is a folder strictly inside
    # the workspace (as written, or through a link such as knowledge/).
    child_label = None
    probe = absolute[0].parent
    while probe != ws.root and ws.root in probe.parents:
        if Path(os.path.realpath(str(probe))) == repo:
            child_label = ws.rel(probe)
            break
        probe = probe.parent
    is_child = child_label is not None
    result["repo"] = child_label if is_child else str(repo)
    relative = [os.path.relpath(str(path), str(repo)) for path in physical]
    result["paths"] = relative
    if not is_child and not stage_only:
        result["reason"] = "root-repo"
        return result

    code, _, err = _git(repo, "add", "--", *relative)
    if code != 0:
        raise ToolError("git add failed in %s:\n%s" % (result["repo"], err.strip()), EXIT_FAIL)
    if stage_only:
        result["reason"] = "staged"
        return result

    code, _, _ = _git(repo, "diff", "--cached", "--quiet", "--", *relative)
    if code == 0:
        result["reason"] = "no-changes"
        return result

    code, _, err = _git(repo, "var", "GIT_COMMITTER_IDENT")
    if code != 0:
        raise ToolError(
            "git has no user identity for %s, so the commit cannot be made. The files are staged.\n"
            "Set one with: git config --global user.name \"Your Name\" && "
            "git config --global user.email you@example.com" % result["repo"],
            EXIT_FAIL,
        )

    message = ["-m", subject]
    if body.strip():
        message += ["-m", body.strip()]
    message += ["-m", TRAILER]
    code, out, err = _git(repo, "commit", "-q", *message, "--", *relative)
    if code != 0:
        raise ToolError(
            "git commit failed in %s. The files are still staged; nothing was reset.\n%s"
            % (result["repo"], (err.strip() or out.strip())),
            EXIT_FAIL,
        )
    code, out, _ = _git(repo, "rev-parse", "HEAD")
    result["committed"] = True
    result["sha"] = out.strip() if code == 0 else None
    return result
