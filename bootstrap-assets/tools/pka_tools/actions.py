"""Open action items: unchecked boxes in dated notes.

Full-text search cannot find `- [ ]` (the tokenizer discards the
punctuation), so this reads the notes. The note is the record: a box that
has been ticked is closed, whatever a log entry says.

Nothing here writes: an item is read in whichever form it was written.

    - [ ] Send the comparison — @Sam — by 2026-05-01      pka-meetings
    - [ ] Send the comparison — @Sam — 2026-05-01         pka-meetings, no "by"
    - [ ] **Sam**: Send the comparison (due: 2026-05-01)  thinkkit take-notes

Owners: every `@name`, and a bold name with a colon at the start of the
item when it names someone the workspace knows (a person folder, the note's
attendees, the owner profile). Due date: `by` / `due` followed by a date,
`(due: …)`, or an ISO date that ends the item after a dash. `due` is set
only when the item gives exactly one date: two different dates, a range, or
words that are not a calendar date ("Friday", "12/1") leave it null, with
what was written in `due_text`. Nothing is guessed.
"""
from __future__ import annotations

import datetime as _dt
import os
import re
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from . import frontmatter
from .errors import EXIT_USAGE, ToolError
from .markdown import heading_of, prose_mask, protected_spans
from .people import registry, words_of
from .textio import NotText, line_body, read_text, split_lines
from .workspace import MOC_NAME, Workspace

# A checkbox item, also inside a quote or an Obsidian callout (`> - [ ] …`).
_OPEN_BOX = re.compile(r"^\s*(?:>\s*)*(?:[-*+]|\d+[.)])\s+\[ \]\s+(.*\S)\s*$")
_DONE_BOX = re.compile(r"^\s*(?:>\s*)*(?:[-*+]|\d+[.)])\s+\[[xX]\]\s+")
_NAME_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:\D|$)")
# `@Sam`, `@robin.smith`, `@zoë-åkesson`. A full stop or hyphen that ends the
# name is punctuation (`ask @Sam.`); `@types/node` is a package, not a person.
_OWNER = re.compile(r"(?<![\w/@])@([^\W\d_]\w*(?:[.\-]\w+)*)(?![\w/])")
_ISO = r"\d{4}-\d{2}-\d{2}"
_ISO_RE = re.compile(r"(?<![\d-])%s(?![\d-])" % _ISO)
# What joins two dates into a range or a choice: `to`, `or`, a dash, a slash.
_JOIN = r"(?:\s*(?:to|or|and|through|thru|until|till|[-\u2013\u2014/,&])\s*)"
# `by 2026-05-01`, `due 2026-05-01`, `due: 2026-05-01`; and what follows when it
# is a second date (`by 2026-12-01 or 2026-12-05`), which is then not one date.
_DUE = re.compile(r"\b(by|due)(?:\s*:\s*|\s+)(?:on\s+)?(%s(?:%s%s)*)(?!\d)" % (_ISO, _JOIN, _ISO), re.IGNORECASE)
# `(due: Friday)`, `(due Dec 1)`, `(by: end of month)`: thinkkit writes what was said.
_DUE_PAREN = re.compile(r"[(\[]\s*(?:due|by)(\s*:\s*|\s+)([^()\[\]]*?)\s*[)\]]", re.IGNORECASE)
# `… — @Sam — 2026-05-01`: the form pka-meetings writes. The date must end the item.
_DUE_TRAILING = re.compile(r"(?:\s[-\u2013\u2014]|[\u2013\u2014])\s*(%s)\s*\.?\s*$" % _ISO)
# Verbs that take `by` as part of themselves: "stand by 2026-12-01" names no deadline.
_BY_VERBS = frozenset((
    "abide", "abides", "came", "come", "comes", "drop", "dropped", "drops", "get", "gets", "go", "goes", "going",
    "gone", "got", "live", "lives", "pass", "passed", "passes", "passing", "ran", "run", "runs", "stand",
    "standing", "stands", "stood", "swear", "went",
))
# A bracket without a colon (`(due Friday)`, `(by end of month)`) is a due
# date only when it holds a digit or one of these words: `(due diligence)` and
# `[by Robin]` are not.
_WHEN_WORDS = frozenset((
    "today", "tonight", "tomorrow", "asap", "eod", "eow", "eom", "eoq", "eoy", "cob", "next", "this", "end",
    "mid", "early", "late", "start", "beginning", "week", "weekend", "month", "quarter", "year", "sprint",
    "morning", "noon", "afternoon", "evening", "midnight", "christmas", "easter", "now", "soon", "later",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "mon", "tue", "tues", "wed", "thu", "thur", "thurs", "fri", "sat", "sun",
))
# A date without a year is resolved only when the first such day on or after
# the note's date is at most this far ahead. Beyond it the day fell within
# the two months before the note was written, where "overdue since then" is
# as likely as "a year from then", and nothing is guessed.
YEARLESS_HORIZON_DAYS = 300
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


TODAY_ENV = "PKA_ACTIONS_TODAY"     # YYYY-MM-DD; lets a test (or a rehearsal) pick the day


def today() -> _dt.date:
    """Today, for the default window of the last seven days."""
    forced = os.environ.get(TODAY_ENV)
    if forced:
        try:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", forced):
                raise ValueError(forced)
            return _dt.date.fromisoformat(forced)
        except ValueError:
            raise ToolError("%s must be a date like 2026-11-20, not %r" % (TODAY_ENV, forced), EXIT_USAGE)
    return _dt.date.today()


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


class Known:
    """The people a bold lead-in may name: sets of folded words, one per
    name. `Robin`, `Smith` and `Dr. Smith` all match `Robin Smith`."""

    def __init__(self, names: Iterable[str] = ()):
        self._sets = {frozenset(words_of(name)) for name in names} - {frozenset()}

    def has(self, name: str) -> bool:
        words = frozenset(words_of(name))
        return bool(words) and any(words <= known for known in self._sets)

    def plus(self, names: Iterable[str]) -> "Known":
        out = Known()
        out._sets = self._sets | (Known(names)._sets)
        return out


_WIKI_NAME = re.compile(r"!?\[\[([^\[\]|]*?)(?:\\?\|([^\[\]]*))?\]\]")
_LINK_NAME = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_ATTENDEE_LINE = re.compile(
    r"^\s*(?:>\s*)*(?:[-*+]\s+)?(?:\*\*|__)?\s*(?:attendees|participants|present|attending)\s*"
    r"(?::\s*(?:\*\*|__)|(?:\*\*|__)\s*:|:)\s*(.+)$", re.IGNORECASE)
_PROFILE_NAME = re.compile(r"^\s*(?:[-*+]\s+)?(?:\*\*|__)?\s*name\s*(?::\s*(?:\*\*|__)|(?:\*\*|__)\s*:|:)\s*(.+)$",
                           re.IGNORECASE)


def _person_text(raw: str) -> str:
    """A name out of an attendee entry: `[Priya](../personnel/priya/)`,
    `[[priya|Priya Nair]]`, `Robin (PM)`, `@Sam — notes` give `Priya`,
    `Priya Nair`, `Robin`, `Sam`."""
    def wiki(match: "re.Match[str]") -> str:
        if match.group(2):
            return match.group(2)
        parts = [part for part in match.group(1).split("#")[0].split("/") if part]
        if parts and parts[-1].lower() in ("index", "index.md") and len(parts) > 1:
            parts = parts[:-1]
        return parts[-1] if parts else ""
    text = _LINK_NAME.sub(lambda m: m.group(1), _WIKI_NAME.sub(wiki, raw))
    text = re.sub(r"\([^()]*\)|\[[^\[\]]*\]", " ", text)
    text = re.split(r"\s[-\u2013\u2014]\s|[\u2013\u2014:]", text, maxsplit=1)[0]
    return text.replace("*", " ").replace("`", " ").replace("@", " ").strip(" \t_.,;")


def attendees_of(lines: List[str]) -> List[str]:
    """The names a note gives as its attendees: frontmatter `attendees`, a
    header line (`**Attendees**: Priya (PM), Robin`), and the items of an
    `## Attendees` section."""
    out: List[str] = []
    fm = frontmatter.parse(lines)
    if fm.usable:
        out.extend(frontmatter.get_list(lines, fm, "attendees"))
    mask = prose_mask(lines)
    inside = False
    first = fm.close + 1 if fm.present and fm.close else 0
    for idx, line in enumerate(lines):
        if mask[idx] or idx < first:
            continue
        body = line_body(line)
        found = heading_of(body)
        if found:
            inside = found[0] in (2, 3) and found[1].strip().strip(":").lower() in ("attendees", "participants")
            continue
        header = _ATTENDEE_LINE.match(body)
        if header:
            # Commas inside brackets belong to a role: `Priya (PM, EMEA), Robin`.
            flat = re.sub(r"\([^()]*\)", lambda m: m.group(0).replace(",", " ").replace(";", " "), header.group(1))
            out.extend(re.split(r"[,;]|\band\b|&", flat))
        elif inside:
            item = re.match(r"^\s*(?:>\s*)*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?(.+)$", body)
            if item:
                out.append(item.group(1))
    return [name for name in (_person_text(raw) for raw in out) if name]


def known_people(ws: Workspace) -> Known:
    """Who the workspace knows: every person folder (name, aliases, slug)
    and the owner named in `.pka/owner-profile.md`."""
    names: List[str] = []
    try:
        people = registry(ws).people.values()
    except (ToolError, OSError):
        people = []
    for person in people:
        names.extend([person.name, person.slug] + list(person.aliases))
    profile = ws.pka / "owner-profile.md"
    try:
        lines = split_lines(read_text(profile)) if profile.is_file() else []
    except (NotText, OSError):
        lines = []
    fm = frontmatter.parse(lines)
    if fm.usable and frontmatter.get_scalar(lines, fm, "name"):
        names.append(frontmatter.get_scalar(lines, fm, "name"))
    for line in lines[:40]:
        match = _PROFILE_NAME.match(line_body(line))
        if match:
            names.append(_person_text(match.group(1)))
    return Known(names)


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


def _prose(text: str) -> str:
    """The item with inline code and comments blanked out (same length, so
    positions still line up): `@dataclass` in backticks is not an owner."""
    out = list(text)
    for start, end in protected_spans(text):
        out[start:end] = " " * (end - start)
    return "".join(out)


def owners_of(text: str, known: Optional[Known] = None) -> List[str]:
    """Owners of an item, in the order written, each once.

    Every `@name` is an owner. A bold lead-in with a colon is read as
    owners only when every name in it (1) looks like a name and (2) names
    someone in `known`: `**Robin and Sam**:` gives two, `**Note**:` and
    `**Draft the plan**:` give none, and neither does `**Budget**:` or
    `**Orion**:`, which look like names and are nobody the workspace knows.
    When unsure, no owner. With `known` left out only the first test is
    made; the command always passes it.
    """
    owners: List[str] = []
    lead = _BOLD_LEAD.match(text)
    if lead:
        names = []
        for part in _OWNER_SPLIT.split(lead.group(1).strip()):
            name = _PAREN_TAIL.sub("", part).strip().lstrip("@").strip()
            if name:
                names.append(name)
        if names and all(_is_name(name) and (known is None or known.has(name)) for name in names):
            owners.extend(names)
    for name in _OWNER.findall(_prose(text)):
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
            ahead = (_dt.date.fromisoformat(found) - note_date).days
            return found if ahead <= YEARLESS_HORIZON_DAYS else None
    return None


def _valid_isos(text: str) -> List[str]:
    return [found for found in (_iso(int(m.group(0)[:4]), int(m.group(0)[5:7]), int(m.group(0)[8:10]))
                                for m in _ISO_RE.finditer(text)) if found]


def _is_when(content: str) -> bool:
    """Does a bracket without a colon speak of time? A digit, a month or a
    weekday name, or a word such as `tomorrow`, `next`, `end`."""
    if any(ch.isdigit() for ch in content):
        return True
    return any(word in _WHEN_WORDS or word in _MONTHS for word in re.findall(r"[a-z]+", content.lower()))


def due_of(text: str, note_date: Optional[_dt.date] = None) -> Tuple[Optional[str], Optional[str]]:
    """(due as YYYY-MM-DD or None, the due date as written or None).

    A due date is read in three places:

      1. a bracket: `(due: …)`, `(by: …)`, `[due …]`, holding any text;
      2. `by` / `due`, an optional colon, and an ISO date, anywhere else;
      3. an ISO date that ends the item after a dash.

    `due` is set only when those places give exactly one date between them.
    Two different dates (a bracket with two, a range, a bracket that
    disagrees with the date after the dash) give no `due`, and `due_text`
    holds everything that was written, in the order written, joined with
    `; `. A bracket that is not a date (`(due: tomorrow)`) beside one ISO
    date gives that date, and `due_text` keeps the bracket's words. An ISO
    date anywhere else in the item is part of the sentence.
    """
    prose = _prose(text)
    # (where it starts, as written, the one date it resolves to or None, every valid ISO date in it)
    found: List[Tuple[int, str, Optional[str], List[str]]] = []
    taken: List[Tuple[int, int]] = []
    for match in _DUE_PAREN.finditer(prose):
        written = match.group(2).strip()
        if not written or (":" not in match.group(1) and not _is_when(written)):
            continue
        found.append((match.start(), written, _calendar_date(written, note_date), _valid_isos(written)))
        taken.append(match.span())

    def free(start: int, end: int) -> bool:
        return not any(start < t_end and end > t_start for t_start, t_end in taken)

    for match in _DUE.finditer(prose):
        if not free(*match.span()):
            continue
        if match.group(1).lower() == "by":
            before = re.findall(r"[A-Za-z]+", prose[:match.start()])
            if before and before[-1].lower() in _BY_VERBS:
                continue
        written = match.group(2)
        dates = _valid_isos(written)
        # One date, or the same date said twice, is one date.
        single = dates[0] if dates and len(set(dates)) == 1 and len(dates) == len(_ISO_RE.findall(written)) else None
        found.append((match.start(), written, single, dates))
        taken.append(match.span())
    match = _DUE_TRAILING.search(prose)
    # `2026-11-01 — 2026-11-21` is a period, not a due date.
    if match and free(*match.span(1)) and not re.search(r"%s\s*$" % _ISO, prose[:match.start()]):
        found.append((match.start(1), match.group(1), _calendar_date(match.group(1), note_date),
                      _valid_isos(match.group(1))))
    if not found:
        return None, None
    found.sort(key=lambda item: item[0])
    dates = {date for _pos, _written, single, inside in found for date in ([single] if single else []) + inside}
    resolved = [written for _pos, written, single, _inside in found if single]
    others = [written for _pos, written, single, _inside in found if not single]

    def joined(parts: List[str]) -> str:
        return "; ".join(dict.fromkeys(parts))

    if len(dates) == 1 and resolved:
        return next(iter(dates)), joined(others) if others else resolved[0]
    return None, joined([written for _pos, written, _single, _inside in found])


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
    people = known_people(ws)
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
            mask = prose_mask(lines)
            known = people.plus(attendees_of(lines))
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
                    "owners": owners_of(text, known),
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
