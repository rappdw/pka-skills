"""Open action items: unchecked boxes in dated notes.

Full-text search cannot find `- [ ]` (the tokenizer discards the
punctuation), so this reads the notes. The note is the record: a box that
has been ticked is closed, whatever a log entry says.
"""
from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path
from typing import List, Optional

from . import frontmatter
from .errors import EXIT_USAGE, ToolError
from .markdown import fence_mask
from .textio import NotText, line_body, read_text, split_lines
from .workspace import MOC_NAME, Workspace

_OPEN_BOX = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\[ \]\s+(.*\S)\s*$")
_DONE_BOX = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\[[xX]\]\s+")
_NAME_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:\D|$)")
_OWNER = re.compile(r"(?<![\w/])@([A-Za-z][\w.\-]*)")
_DUE = re.compile(r"\b(?:by|due)\s+(\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)


def parse_date(text: str, option: str) -> _dt.date:
    try:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", text):
            raise ValueError(text)
        return _dt.date.fromisoformat(text)
    except ValueError:
        raise ToolError("%s needs a date as YYYY-MM-DD, got %r" % (option, text), EXIT_USAGE)


def note_date(path: Path, lines: List[str]) -> Optional[_dt.date]:
    """The note's date: the filename prefix, else frontmatter `date`.

    File modification time is never used: routing, indexing and sync all
    change it.
    """
    match = _NAME_DATE.match(path.name)
    candidates = [match.group(1)] if match else []
    fm = frontmatter.parse(lines)
    if fm.usable:
        value = frontmatter.get_scalar(lines, fm, "date")
        if value:
            candidates.append(value[:10])
    for candidate in candidates:
        try:
            return _dt.date.fromisoformat(candidate)
        except ValueError:
            continue
    return None


def _scope(ws: Workspace, scope: str, under: List[str]) -> List[Path]:
    if under:
        folders = []
        for given in under:
            folder = ws.resolve(given)
            if not folder.is_dir():
                raise ToolError("--under: not a folder: %s" % given, EXIT_USAGE)
            folders.append(folder)
        return folders
    if scope == "meetings":
        folders = list(ws.meeting_homes())
        people = ws.people_home()
        if people is not None:
            folders.append(people)
        if folders:
            return folders
    return ws.index_roots()


def run(
    ws: Workspace,
    since: Optional[_dt.date],
    until: Optional[_dt.date],
    scope: str = "meetings",
    under: Optional[List[str]] = None,
    include_undated: bool = False,
) -> dict:
    folders = _scope(ws, scope, under or [])
    items = []
    files_scanned = 0
    closed = 0
    seen = set()
    for folder in folders:
        for path in ws.walk(folder, captures=False):
            if path in seen or path.suffix.lower() not in (".md", ".markdown") or path.name == MOC_NAME:
                continue
            seen.add(path)
            try:
                lines = split_lines(read_text(path))
            except (NotText, OSError):
                continue
            date = note_date(path, lines)
            if date is None:
                if not include_undated:
                    continue
            else:
                if since is not None and date < since:
                    continue
                if until is not None and date > until:
                    continue
            files_scanned += 1
            mask = fence_mask(lines)
            for idx, line in enumerate(lines):
                if mask[idx]:
                    continue
                body = line_body(line)
                match = _OPEN_BOX.match(body)
                if not match:
                    if _DONE_BOX.match(body):
                        closed += 1
                    continue
                text = match.group(1)
                owners = _OWNER.findall(text)
                due = _DUE.search(text)
                items.append({
                    "path": ws.rel(path),
                    "line": idx + 1,
                    "date": date.isoformat() if date else None,
                    "text": text,
                    "owners": owners,
                    "due": due.group(1) if due else None,
                })
    items.sort(key=lambda item: (item["date"] or "", item["path"], item["line"]))
    return {
        "since": since.isoformat() if since else None,
        "until": until.isoformat() if until else None,
        "scope": [ws.rel(folder) or "." for folder in folders],
        "files_scanned": files_scanned,
        "open": len(items),
        "closed": closed,
        "items": items,
    }
