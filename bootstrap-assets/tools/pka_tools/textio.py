"""Byte-faithful text reading and writing.

Every tool that edits a user's file goes through here, so that a file keeps
its line endings, its byte-order mark and its missing-or-present final
newline. Lines are split on "\\n" only: `str.splitlines()` also splits on form
feeds and Unicode separators, which would make a paragraph look like several
lines.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import List

BOM = "﻿"


class NotText(Exception):
    """The file is not valid UTF-8."""


def read_text(path: Path) -> str:
    """Read a file exactly: no newline translation, BOM kept as a character."""
    data = Path(path).read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise NotText(str(exc)) from exc


def read_text_lossy(path: Path) -> str:
    """Read for indexing only (never for writing back)."""
    return Path(path).read_bytes().decode("utf-8", errors="replace")


def write_text_atomic(path: Path, text: str) -> None:
    """Write `text` exactly, by way of a temporary file and a rename."""
    path = Path(path)
    if path.is_symlink():
        # Write through the link, as an editor would; never replace the link.
        path = Path(os.path.realpath(str(path)))
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = None
    if path.exists():
        if not os.access(str(path), os.W_OK):
            # A rename would get past the file's own permissions. Honour them.
            raise PermissionError("read-only: %s" % path)
        mode = path.stat().st_mode & 0o7777
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".pka-tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(text.encode("utf-8"))
        if mode is not None:
            os.chmod(tmp, mode)
        else:
            os.chmod(tmp, 0o644)
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def split_lines(text: str) -> List[str]:
    """Split into lines, each keeping its own terminator. "".join() restores the text."""
    if not text:
        return []
    parts = text.split("\n")
    lines = [part + "\n" for part in parts[:-1]]
    if parts[-1] != "":
        lines.append(parts[-1])
    return lines


def line_body(line: str) -> str:
    """The line without its terminator (and nothing else removed)."""
    if line.endswith("\r\n"):
        return line[:-2]
    if line.endswith("\n"):
        return line[:-1]
    return line


def line_end(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    return ""


def detect_newline(text: str) -> str:
    """The file's line ending: that of its first terminated line, LF if none."""
    idx = text.find("\n")
    if idx > 0 and text[idx - 1] == "\r":
        return "\r\n"
    return "\n"


def has_bare_cr(text: str) -> bool:
    """True when the text uses a lone carriage return as a line ending.

    Such a file reads as one long line here, so no line-level edit is safe.
    """
    idx = text.find("\r")
    while idx != -1:
        if idx + 1 >= len(text) or text[idx + 1] != "\n":
            return True
        idx = text.find("\r", idx + 1)
    return False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- generated files

def generated_problem(root: Path, path: Path) -> str:
    """Why a file the tools generate (a report, a plan, their own state) must
    not be written at `path`, or "" when it may be.

    A user's note is written through a symbolic link, as an editor would. A
    generated file never is: a link at its path, or at a folder on the way to
    it, would send the tool's output over some other file. So every folder
    from the workspace root down must be a real folder (or not exist yet), and
    the path itself must be a regular file (or not exist yet).
    """
    root = Path(root)
    path = Path(path)
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return "%s is outside the workspace" % path
    folder = root
    for part in parts[:-1]:
        folder = folder / part
        shown = folder.relative_to(root).as_posix()
        if folder.is_symlink():
            return "%s is a symbolic link, not a folder in this workspace" % shown
        if os.path.lexists(str(folder)) and not folder.is_dir():
            return "%s is not a folder" % shown
    shown = path.relative_to(root).as_posix()
    if path.is_symlink():
        return "%s is a symbolic link" % shown
    if os.path.lexists(str(path)) and not path.is_file():
        return "%s is not a regular file" % shown
    return ""


def write_generated(root: Path, path: Path, text: str) -> None:
    """Write a generated file atomically, never through a link. Raises
    `OSError` with a one-line, workspace-relative message when it may not."""
    problem = generated_problem(root, path)
    if problem:
        raise GeneratedRefused(problem)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".pka-tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(text.encode("utf-8"))
        os.chmod(tmp, 0o644)
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class GeneratedRefused(Exception):
    """A generated file could not be written where it belongs (see `generated_problem`)."""
