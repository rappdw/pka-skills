"""Just enough markdown structure to edit a file line by line.

Nothing here renders or re-flows markdown. The functions locate things
(fenced blocks, headings, table cells, wikilinks) so that callers can change
one line and leave every other byte alone.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from .textio import line_body

_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$")

# [[target]], [[target#heading]], [[target|alias]], and the table-safe form
# [[target\|alias]]. Group 1 is the target.
WIKILINK_RE = re.compile(
    r"\[\[(?P<target>[^\[\]|#\\\n]+?)(?P<anchor>#[^\[\]|\\\n]*)?(?P<alias>\\?\|[^\[\]\n]*)?\]\]"
)


def fence_mask(lines: List[str]) -> List[bool]:
    """True for every line that is a fence delimiter or inside a fenced block."""
    mask = []
    open_char = ""
    open_len = 0
    for line in lines:
        body = line_body(line)
        match = _FENCE_RE.match(body)
        if open_char:
            mask.append(True)
            if match:
                run = match.group(1)
                rest = body[match.end():].strip()
                if run[0] == open_char and len(run) >= open_len and not rest:
                    open_char = ""
                    open_len = 0
            continue
        if match:
            run = match.group(1)
            open_char = run[0]
            open_len = len(run)
            mask.append(True)
        else:
            mask.append(False)
    return mask


def heading_of(line: str) -> Optional[Tuple[int, str]]:
    """(level, text) when the line is an ATX heading, else None."""
    match = _HEADING_RE.match(line_body(line))
    if not match:
        return None
    return len(match.group(1)), match.group(2).strip()


def find_heading(
    lines: List[str],
    mask: List[bool],
    text: str,
    level: int,
    start: int = 0,
    end: Optional[int] = None,
) -> Optional[int]:
    """Index of the first heading with this level and text (case-insensitive)."""
    stop = len(lines) if end is None else end
    wanted = text.strip().lower()
    for idx in range(start, stop):
        if mask[idx]:
            continue
        found = heading_of(lines[idx])
        if found and found[0] == level and found[1].lower() == wanted:
            return idx
    return None


def section_end(lines: List[str], mask: List[bool], heading_idx: int) -> int:
    """Index one past the last line of the section that starts at `heading_idx`.

    The section runs to the next heading of the same or a higher level.
    """
    found = heading_of(lines[heading_idx])
    level = found[0] if found else 6
    for idx in range(heading_idx + 1, len(lines)):
        if mask[idx]:
            continue
        other = heading_of(lines[idx])
        if other and other[0] <= level:
            return idx
    return len(lines)


def cell_spans(body: str) -> Optional[List[Tuple[int, int]]]:
    """Character spans of the cells in a table row, or None if it is not a row.

    A pipe does not separate cells when it is escaped (`\\|`), inside a
    `[[wikilink|alias]]`, or inside `inline code`.
    """
    if not body.strip().startswith("|"):
        return None
    seps = []
    idx = 0
    depth = 0
    length = len(body)
    while idx < length:
        char = body[idx]
        if char == "\\":
            idx += 2
            continue
        if body.startswith("[[", idx):
            depth += 1
            idx += 2
            continue
        if depth and body.startswith("]]", idx):
            depth -= 1
            idx += 2
            continue
        if char == "`":
            close = body.find("`", idx + 1)
            if close != -1:
                idx = close + 1
                continue
        if char == "|" and depth == 0:
            seps.append(idx)
        idx += 1
    if len(seps) < 2:
        if len(seps) == 1 and body[seps[0] + 1:].strip():
            return [(seps[0] + 1, length)]
        return None
    spans = [(seps[k] + 1, seps[k + 1]) for k in range(len(seps) - 1)]
    if body[seps[-1] + 1:].strip():
        spans.append((seps[-1] + 1, length))
    return spans


def cell_texts(body: str) -> Optional[List[str]]:
    spans = cell_spans(body)
    if spans is None:
        return None
    return [body[a:b].strip() for a, b in spans]


_SEPARATOR_CELL = re.compile(r"^:?-+:?$")


def is_separator_row(body: str) -> bool:
    cells = cell_texts(body)
    if not cells:
        return False
    return all(_SEPARATOR_CELL.match(cell) for cell in cells)


def replace_cell(body: str, span: Tuple[int, int], new_content: str) -> str:
    """Put `new_content` in a cell, keeping the cell's own padding."""
    start, end = span
    raw = body[start:end]
    if not raw.strip():
        lead, trail = " ", " "
    else:
        lead = raw[: len(raw) - len(raw.lstrip())]
        trail = raw[len(raw.rstrip()):]
    return body[:start] + lead + new_content + trail + body[end:]


def link_target(raw: str) -> str:
    """Normalise a wikilink target for comparison: no `.md`, no `./`, no anchor."""
    target = raw.strip()
    if "#" in target:
        target = target.split("#", 1)[0]
    while target.startswith("./"):
        target = target[2:]
    if target.lower().endswith(".md"):
        target = target[:-3]
    return target.strip()


def wikilink_targets(text: str) -> List[str]:
    return [link_target(m.group("target")) for m in WIKILINK_RE.finditer(text)]
