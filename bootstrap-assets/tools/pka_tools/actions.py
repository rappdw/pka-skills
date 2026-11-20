"""Open action items: unchecked boxes in dated notes.

Full-text search cannot find `- [ ]` (the tokenizer discards the
punctuation), so this reads the notes. The note is the record: a box that
has been ticked is closed, whatever a log entry says.

Nothing here writes: an item is read in whichever form it was written.

    - [ ] Send the comparison — @Sam — by 2026-05-01      pka-meetings
    - [ ] Send the comparison — @Sam — 2026-05-01         pka-meetings, no "by"
    - [ ] **Sam**: Send the comparison (due: 2026-05-01)  thinkkit take-notes

Owners: every `@name`, and a bold name with a colon at the start of the
item. Due date: `by` / `due` followed by a date, `(due: …)`, or an ISO date
that ends the item after a dash. A due date that is not a calendar date
("Friday", "12/1") is returned as written in `due_text` and never guessed.
"""
from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path
from typing import List, Optional, Tuple

from . import frontmatter
from .errors import EXIT_USAGE, ToolError
from .markdown import fence_mask
from .textio import NotText, line_body, read_text, split_lines
from .workspace import MOC_NAME, Workspace

_OPEN_BOX = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\[ \]\s+(.*\S)\s*$")
_DONE_BOX = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\[[xX]\]\s+")
_NAME_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:\D|$)")
_OWNER = re.compile(r"(?<![\w/])@([A-Za-z][\w.\-]*)")
_ISO = r"\d{4}-\d{2}-\d{2}"
# `by 2026-05-01`, `due 2026-05-01`, `due: 2026-05-01`, with or without brackets.
_DUE = re.compile(r"\b(?:by|due)(?:\s*:\s*|\s+)(?:on\s+)?(%s)(?!\d)" % _ISO, re.IGNORECASE)
# `(due: Friday)`, `(due Dec 1)`, `(by: end of month)`: thinkkit writes what was said.
_DUE_PAREN = re.compile(r"[(\[]\s*(?:due|by)(?:\s*:\s*|\s+)([^()\[\]]*?)\s*[)\]]", re.IGNORECASE)
# `… — @Sam — 2026-05-01`: the form pka-meetings writes. The date must end the item.
_DUE_TRAILING = re.compile(r"(?:\s[-\u2013\u2014]|[\u2013\u2014])\s*(%s)\s*\.?\s*$" % _ISO)
# `**Robin**: …` or `**Robin:** …` at the start of the item (thinkkit take-notes).
_BOLD_LEAD = re.compile(r"^(?:\*\*|__)\s*([^*_:]{1,80}?)\s*(?::\s*(?:\*\*|__)|(?:\*\*|__)\s*:)(?=\s|$)")
_OWNER_SPLIT = re.compile(r"\s*(?:,|&|/|\+|\band\b)\s*", re.IGNORECASE)
_PAREN_TAIL = re.compile(r"\s*\([^()]*\)\s*$")
# A bold lead-in that labels the item rather than naming who owns it.
_NOT_OWNERS = frozenset((
    "action", "action item", "blocked", "blocker", "context", "decision", "done", "due", "follow up",
    "follow-up", "followup", "fyi", "important", "n/a", "next", "next step", "none", "note", "notes",
    "open", "optional", "owner", "priority", "question", "reminder", "status", "tbd", "todo", "to do",
    "unassigned", "update", "urgent", "warning",
))
_NAME_PARTICLES = frozenset(("al", "bin", "da", "de", "del", "della", "den", "der", "di", "du", "el", "la",
                             "le", "ten", "ter", "van", "von"))
_MONTHS = {name: number for number, names in enumerate((
    ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",), ("jun", "june"),
    ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"), ("oct", "october"),
    ("nov", "november"), ("dec", "december")), 1) for name in names}
_MONTH_DAY = re.compile(r"^([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?$")
_DAY_MONTH = re.compile(r"^(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?(?:,?\s+(\d{4}))?$")


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


def _is_name(text: str) -> bool:
    """Could this bold lead-in be a person? Up to four words, each starting
    with a letter that is not lower case (particles such as `van` aside),
    no digits, and not a label such as `Note` or `TODO`."""
    if not text or text.lower() in _NOT_OWNERS or any(ch.isdigit() for ch in text):
        return False
    words = text.split()
    if not 1 <= len(words) <= 4:
        return False
    for word in words:
        if word.lower() in _NAME_PARTICLES:
            continue
        if not word[0].isalpha() or word[0].islower():
            return False
        if not all(ch.isalpha() or ch in ".'\u2019-" for ch in word):
            return False
    return words[0].lower() not in _NAME_PARTICLES or len(words) > 1


def owners_of(text: str) -> List[str]:
    """Owners of an item, in the order written, each once.

    A bold lead-in with a colon is read as owners only when every name in
    it looks like a name: `**Robin and Sam**:` gives two, `**Note**:` and
    `**Draft the plan**:` give none.
    """
    owners: List[str] = []
    lead = _BOLD_LEAD.match(text)
    if lead:
        names = []
        for part in _OWNER_SPLIT.split(lead.group(1).strip()):
            name = _PAREN_TAIL.sub("", part).strip().lstrip("@").strip()
            if name:
                names.append(name)
        if names and all(_is_name(name) for name in names):
            owners.extend(names)
    for name in _OWNER.findall(text):
        owners.append(name)
    seen = set()
    out = []
    for name in owners:
        key = name.casefold()
        if key not in seen:
            seen.add(key)
            out.append(name)
    return out


def _iso(year: int, month: int, day: int) -> Optional[str]:
    try:
        return _dt.date(year, month, day).isoformat()
    except ValueError:
        return None


def _calendar_date(text: str, note_date: Optional[_dt.date]) -> Optional[str]:
    """`2026-12-01`, `Dec 1`, `December 1st, 2026`, `1 Dec 2026` as an ISO
    date; None for anything else. A date written without a year is the
    first such date on or after the note's date, and is left unresolved
    when the note has no date. Numeric forms other than ISO (`12/1`) are
    not read: day and month cannot be told apart."""
    text = text.strip().rstrip(".").strip()
    if re.match(r"^%s$" % _ISO, text):
        return _iso(int(text[:4]), int(text[5:7]), int(text[8:10]))
    month = day = year = None
    match = _MONTH_DAY.match(text)
    if match:
        month, day, year = _MONTHS.get(match.group(1).lower()), int(match.group(2)), match.group(3)
    else:
        match = _DAY_MONTH.match(text)
        if match:
            day, month, year = int(match.group(1)), _MONTHS.get(match.group(2).lower()), match.group(3)
    if not month:
        return None
    if year:
        return _iso(int(year), month, day)
    if note_date is None:
        return None
    for candidate_year in (note_date.year, note_date.year + 1):
        found = _iso(candidate_year, month, day)
        if found and found >= note_date.isoformat():
            return found
    return None


def due_of(text: str, note_date: Optional[_dt.date] = None) -> Tuple[Optional[str], Optional[str]]:
    """(due as YYYY-MM-DD or None, the due date as written or None).

    Read in this order: `by` / `due` followed by an ISO date; a bracketed
    `(due: …)` or `(by: …)` holding any text; an ISO date that ends the
    item after a dash. An ISO date anywhere else in the item is part of
    the sentence, not a due date.
    """
    match = _DUE.search(text)
    if match:
        iso = _calendar_date(match.group(1), note_date)
        return iso, match.group(1)
    match = _DUE_PAREN.search(text)
    if match and match.group(1):
        written = match.group(1)
        return _calendar_date(written, note_date), written
    match = _DUE_TRAILING.search(text)
    # `2026-11-01 — 2026-11-21` is a period, not a due date.
    if match and not re.search(r"%s\s*$" % _ISO, text[:match.start()]):
        iso = _calendar_date(match.group(1), note_date)
        return iso, match.group(1)
    return None, None


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
                due, due_text = due_of(text, date)
                items.append({
                    "path": ws.rel(path),
                    "line": idx + 1,
                    "date": date.isoformat() if date else None,
                    "text": text,
                    "owners": owners_of(text),
                    "due": due,
                    "due_text": due_text,
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
