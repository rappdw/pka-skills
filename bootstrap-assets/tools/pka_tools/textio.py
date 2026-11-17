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
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = None
    if path.exists():
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
