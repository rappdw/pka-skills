"""`.pka/session-log.md`: one entry grammar for every role.

    ## YYYY-MM-DD HH:MM | <role> | <summary> | <open threads> | <next action>

Five fields separated by ` | `. The time is optional when reading (older
entries carry a date only). An empty field is written as `—`. A `|` inside a
field is written as `\\|`. The session-start greeting reads the fourth field
for open threads, so it must hold only what is still open.

`add` appends one well-formed entry and does nothing else (no staging).
`open` lists the open threads of recent entries. `check` reports entries
that do not follow the grammar; it never rewrites them.
"""
from __future__ import annotations

import datetime as _dt
import re
from typing import List, Optional

from .errors import EXIT_USAGE, ToolError
from .textio import NotText, detect_newline, has_bare_cr, line_body, read_text, write_text_atomic
from .workspace import Workspace

LOG_NAME = "session-log.md"
EMPTY = "—"
_EMPTY_VALUES = {"", "—", "–", "-", "none", "n/a"}
_STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?$")


def _clean(text: str) -> str:
    """One line, pipes escaped."""
    flat = " ".join((text or "").split())
    return flat.replace("\\|", "|").replace("|", "\\|")


def _split(body: str) -> List[str]:
    """Fields of an entry heading (without the leading `## `), on unescaped pipes."""
    fields = []
    current = []
    idx = 0
    while idx < len(body):
        char = body[idx]
        if char == "\\" and idx + 1 < len(body) and body[idx + 1] == "|":
            current.append("|")
            idx += 2
            continue
        if char == "|":
            fields.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        idx += 1
    fields.append("".join(current).strip())
    return fields


def _empty(value: str) -> bool:
    return value.strip().lower() in _EMPTY_VALUES


class Entry:
    __slots__ = ("line", "stamp", "role", "summary", "open", "next", "fields", "problem")

    def __init__(self, line: int, fields: List[str]):
        self.line = line
        self.fields = fields
        padded = fields + [""] * (5 - len(fields))
        self.stamp, self.role, self.summary, self.open, self.next = padded[:5]
        self.problem = None
        if len(fields) != 5:
            self.problem = "has %d field(s), expected 5: date | role | summary | open threads | next action" % len(fields)
        elif not _STAMP.match(self.stamp):
            self.problem = "first field %r is not `YYYY-MM-DD HH:MM`" % self.stamp
        elif not self.role or not self.summary:
            self.problem = "role and summary must not be empty"

    def as_dict(self) -> dict:
        return {
            "line": self.line, "at": self.stamp, "role": self.role, "summary": self.summary,
            "open": "" if _empty(self.open) else self.open,
            "next": "" if _empty(self.next) else self.next,
            "problem": self.problem,
        }


def _path(ws: Workspace):
    return ws.pka / LOG_NAME


def entries(ws: Workspace) -> List[Entry]:
    path = _path(ws)
    if not path.is_file():
        return []
    try:
        text = read_text(path)
    except NotText:
        raise ToolError("%s is not valid UTF-8" % ws.rel(path))
    out = []
    for number, line in enumerate(text.split("\n"), 1):
        body = line_body(line + "\n")
        if number == 1:
            body = body.lstrip("\ufeff")
        if not body.startswith("## "):
            continue
        out.append(Entry(number, _split(body[3:])))
    return out


def format_entry(role: str, summary: str, open_threads: str = "", next_action: str = "",
                 at: Optional[str] = None) -> str:
    stamp = at or _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        if not re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$", stamp):
            raise ValueError(stamp)
        _dt.datetime.strptime(stamp, "%Y-%m-%d %H:%M")
    except ValueError:
        raise ToolError("--at needs a real date and time as `YYYY-MM-DD HH:MM`, got %r" % stamp, EXIT_USAGE)
    role = _clean(role)
    summary = _clean(summary)
    if not role or not summary:
        raise ToolError("--role and --summary must not be empty", EXIT_USAGE)
    fields = [stamp, role, summary, _clean(open_threads) or EMPTY, _clean(next_action) or EMPTY]
    return "## " + " | ".join(fields)


def add(ws: Workspace, role: str, summary: str, open_threads: str = "", next_action: str = "",
        at: Optional[str] = None, dry_run: bool = False) -> dict:
    if not ws.pka.is_dir():
        raise ToolError("no .pka/ directory; bootstrap the workspace first", EXIT_USAGE)
    entry = format_entry(role, summary, open_threads, next_action, at)
    path = _path(ws)
    text = ""
    if path.is_file():
        try:
            text = read_text(path)
        except NotText:
            raise ToolError("%s is not valid UTF-8; not appending" % ws.rel(path))
        if has_bare_cr(text):
            raise ToolError("%s uses bare carriage returns as line endings; not appending" % ws.rel(path))
    newline = detect_newline(text)
    if text and not text.endswith("\n"):
        text += newline
    if not dry_run:
        write_text_atomic(path, text + entry + newline)
    return {"entry": entry, "path": ws.rel(path), "dry_run": dry_run}


def open_threads(ws: Workspace, last: int = 20) -> dict:
    if last < 1:
        raise ToolError("--last must be at least 1", EXIT_USAGE)
    recent = entries(ws)[-last:]
    items = [entry.as_dict() for entry in reversed(recent) if not entry.problem and not _empty(entry.open)]
    return {"looked_at": len(recent), "open": items}


def check(ws: Workspace) -> dict:
    found = entries(ws)
    problems = [entry.as_dict() for entry in found if entry.problem]
    return {"entries": len(found), "malformed": problems}
