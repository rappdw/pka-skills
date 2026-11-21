"""Health checks: `pka-tools lint`.

Lint reads the workspace and writes one file, the report
`owner-inbox/librarian-lint-<date>.md`. It never edits, moves or deletes a
note. It needs no model and no network, so it can run from cron.

Rules (numbers as in the librarian's `lint-rules.md`):

  1   things left in `team-inbox/unsorted/` and not changed for 14 days
  2   links to files that are not there (wikilinks and markdown links)
  3   paths in a wiki's `## Sources` that are not there
  4   Repo Map folders with nothing indexable in them
  5   notes that belong on a person's timeline and are not on it (one
      informational line, from the backfill planner's evidence rules)
  8a  byte-identical files
  8b  the same text after dropping frontmatter, case and spacing
  8c  near-duplicates, and one note contained in another
  8d  duplicate entities: person folders, wiki topics, pointer topics

`--quick` runs 1 to 4, 8a and 8b. Rules 6 and 7 need judgement and stay with
the librarian, who appends them to the report.

A set of copies is one finding, filed under the broadest rule that holds for
it: files that are identical, re-saved and nearly the same as each other are
one 8c finding that says how each file relates to the suggested keeper.

Every finding has an id made from its rule and its subject, so the same
problem has the same id on every run. `lint suppress <id>` records an id in
`.pka/lint-suppressions.json`; a suppressed finding is left out of the
report and counted.

Not reported: anything under `.pka/` or a dot-folder, `.pkaignore` matches,
the contents of earshot capture directories, an OCR sidecar against its
source (a sidecar stands in for its source's text and is never listed
itself), `_MOC.md` files as duplicates, and pointer rows repeated across
different MOCs. A copy of a file in a wiki's `sources/` folder is reported
as information, not as a finding.

Generated files (the report, the suppressions file) are never written
through a symbolic link.
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import difflib
import hashlib
import json
import math
import os
import re
import time
import unicodedata
import zlib
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set, Tuple

from . import frontmatter, pointers
from .errors import EXIT_FAIL, EXIT_USAGE, ToolError
from .indexer import TEXT_EXTENSIONS, _is_sidecar, _sidecar_of
from .markdown import (
    WIKILINK_RE, block_mask, find_heading, heading_of, link_target, prose_mask as _line_masks, protected_spans,
    section_end,
)
from .people import registry, words_of
from .textio import (
    GeneratedRefused, NotText, generated_problem, line_body, read_text, read_text_lossy, sha256_file, split_lines,
    write_generated,
)
from .workspace import CAPTURE_MARKER, MOC_NAME, UNFILED_ROOTS, Workspace

REPORT_DIR = "owner-inbox"
REPORT_RE = re.compile(r"^librarian-lint-(\d{4}-\d{2}-\d{2})\.md$")
# Reports the tools write into owner-inbox/: never lint input.
GENERATED_RE = re.compile(r"^(librarian-lint-|timeline-backfill-plan-).*\.md$")
HEADER_RE = re.compile(r"^<!-- pka-lint (\{.*\}) -->\s*$")
ID_TAG_RE = re.compile(r"\[id: ([0-9a-z]+-[0-9a-z]+)(, information)?\]")
MORE_IDS_RE = re.compile(r"^<!-- pka-lint-(info-)?ids: ([0-9a-z \-]*)-->\s*$")
SUPPRESS_FILE = "lint-suppressions.json"
SUPPRESS_VERSION = 1
HEADER_VERSION = 1
TODAY_ENV = "PKA_LINT_TODAY"        # YYYY-MM-DD; lets a test (or a rehearsal) pick the day

ORPHAN_DAYS = 14
RECENT_DAYS = 7
SUPPRESS_LOOKBACK_DAYS = 30
MARKDOWN = (".md", ".markdown")
INDEXABLE = MARKDOWN + (".txt", ".pdf", ".docx")
MIN_CONTENT_CHARS = 80          # 8a (text files) and 8b: less text than this, outside headings, is not compared
MIN_BINARY_BYTES = 16           # 8a for files that are not text
MIN_WORDS = 200                 # 8c
SHINGLE = 5
SIMILARITY = 0.8
CONTAINMENT = 0.9
SIG_BINS = 64                   # one-permutation MinHash: 64 bins ...
BAND_ROWS = 4                   # ... in 16 bands of 4
SAMPLE_MASK = 15                # containment candidates: shingles whose hash ends in four zero bits
SMALL_BUCKET = 6                # up to this many notes sharing a band or sample: every pair is looked at
POSTING_CAP = 50                # more than this: a family or boilerplate; compared against one representative
SET_CACHE = 512
REPORT_CAP = 200                # findings shown per rule in the report; `--json` has all of them
RULE5_EXAMPLES = 20
LIBRARIAN_MARK = "<!-- librarian:rules-6-7 -->"
LIBRARIAN_DEFAULTS = (
    "Not part of a quick lint.",
    "Not run by the tool: contradiction candidates (rule 6) and uncited wiki claims (rule 7) need "
    "the librarian. Ask for \"full lint\" in a session and the librarian adds them below this line.",
)

_LINK_OPEN_RE = re.compile(r"(?<![\w\\])!?\[(?:[^\]\[\n]|\[[^\]\n]*\])*\]\(")
_REF_DEF_RE = re.compile(r"^ {0,3}\[(?!\^)([^\]\n]+)\]:\s*(?:<([^>\n]+)>|(\S+))")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d{1,9}[.)])\s+")
_CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
_PATHISH_RE = re.compile(r"(/|\.[A-Za-z0-9]{1,8}$)")
_PERCENT_RE = re.compile(r"%([0-9A-Fa-f]{2})")
_WORD_RE = re.compile(r"\w+", re.UNICODE)
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d{1,9}[.)])(\s|$)")

TITLES = {
    "1": "Left in team-inbox/unsorted/",
    "2": "Broken links",
    "3": "Stale wiki sources",
    "4": "Empty Repo Map folders",
    "5": "Notes not on a person's timeline",
    "8a": "Byte-identical files",
    "8b": "Same text, different bytes",
    "8c": "Near-duplicates and contained notes",
    "8d": "Duplicate entities",
}
HINTS = {
    "1": "Route these or delete them. Say: \"process team-inbox/unsorted\".",
    "2": "Fix or remove these references. The librarian does not remove pointer-row links by itself.",
    "3": "Update the wiki's Sources list or restore the file.",
    "4": "Remove the row from the Repo Map, or archive the folder.",
    "5": "Ask the librarian to \"backfill timelines\". It plans first and writes nothing until you approve. "
         "To leave one note off every timeline, give it `no-backref: true`. This line cannot be suppressed.",
    "8a": "Keep one copy and delete or move the others yourself; links to a removed copy will then show as broken.",
    "8b": "Usually one is a re-save of the other. Keep one, or suppress the group if both are meant.",
    "8c": "Often raw notes beside a reconciled version, or a `-2` copy. Keep the fuller one, or suppress the group.",
    "8d": "Merge the two, or record that they are different (suppress the finding).",
}
QUICK_RULES = ("1", "2", "3", "4", "8a", "8b")
FULL_RULES = ("1", "2", "3", "4", "5", "8a", "8b", "8c", "8d")
RELATIONS = {"keeper": "suggested keeper", "bytes": "identical bytes", "text": "same text", "near": "near copy"}


def today() -> _dt.date:
    forced = os.environ.get(TODAY_ENV)
    if forced:
        try:
            return _dt.date.fromisoformat(forced)
        except ValueError:
            raise ToolError("%s must be a date like 2026-11-20, not %r" % (TODAY_ENV, forced), EXIT_USAGE)
    return _dt.date.today()


def fid(rule: str, *parts: str) -> str:
    """A finding's id: the rule, and a hash of what it is about."""
    digest = hashlib.sha256("\0".join(parts).encode("utf-8", "surrogateescape")).hexdigest()
    return "%s-%s" % (rule, digest[:8])


def code(text: str) -> str:
    """`text` as a markdown code span that cannot break its line or its span."""
    text = text.replace("\r", "\\r").replace("\n", "\\n")
    if "`" in text:
        return "`` %s ``" % text
    return "`%s`" % text


def human_size(size: int) -> str:
    if size < 1024:
        return "%d B" % size
    if size < 1024 * 1024:
        return "%.1f KB" % (size / 1024.0)
    if size < 1024 ** 3:
        return "%.1f MB" % (size / 1024.0 ** 2)
    return "%.1f GB" % (size / 1024.0 ** 3)


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _percent_decode(text: str) -> str:
    """`%20` and friends, as a link destination writes them."""
    if "%" not in text:
        return text
    pieces = bytearray()
    idx = 0
    while idx < len(text):
        match = _PERCENT_RE.match(text, idx)
        if match:
            pieces.append(int(match.group(1), 16))
            idx = match.end()
        else:
            pieces += text[idx].encode("utf-8", "surrogateescape")
            idx += 1
    return pieces.decode("utf-8", "replace")


def body_of(text: str) -> str:
    """The text without its frontmatter. Only a block the frontmatter parser
    accepts is dropped: a paragraph between two `---` rules is body text."""
    lines = split_lines(text)
    fm = frontmatter.parse(lines)
    if fm.usable:
        return "".join(lines[fm.close + 1:])
    return text


def normalise(text: str) -> str:
    """Body text for comparison: no frontmatter, one case, single spaces."""
    return " ".join(body_of(text).casefold().split())


def content_chars(text: str) -> int:
    """How much there is to compare: characters of body text outside headings."""
    total = 0
    for line in split_lines(body_of(text)):
        if heading_of(line) is None:
            total += len(" ".join(line.split()))
    return total


class Names:
    """Does a path exist, by the exact name it was written with?

    Asked of directory listings, never of the filesystem directly, so a
    case-insensitive disk (macOS) and a case-sensitive one give the same
    answer. Names are compared after Unicode normalisation.
    """

    def __init__(self) -> None:
        self._listing: Dict[str, Tuple[Dict[str, str], Dict[str, str]]] = {}

    def _entries(self, folder: Path) -> Tuple[Dict[str, str], Dict[str, str]]:
        key = str(folder)
        if key not in self._listing:
            exact: Dict[str, str] = {}
            folded: Dict[str, str] = {}
            try:
                names = os.listdir(key)
            except OSError:
                names = []
            for name in sorted(names):
                exact.setdefault(_nfc(name), name)
                folded.setdefault(_nfc(name).casefold(), name)
            self._listing[key] = (exact, folded)
        return self._listing[key]

    def find(self, base: Path, parts: Tuple[str, ...]) -> Tuple[str, Optional[Path]]:
        """("ok" | "case" | "missing", the path found)."""
        current = base
        state = "ok"
        for part in parts:
            if part in ("", "."):
                continue
            exact, folded = self._entries(current)
            wanted = _nfc(part)
            if wanted in exact:
                current = current / exact[wanted]
            elif wanted.casefold() in folded:
                current = current / folded[wanted.casefold()]
                state = "case"
            else:
                return "missing", None
        return state, current


class Scan:
    """One walk of the workspace, and what the rules share."""

    def __init__(self, ws: Workspace, day: _dt.date):
        self.ws = ws
        self.today = day
        self.files: List[Path] = []
        self.unreadable: List[str] = []
        self.notes: List[str] = []
        self.names = Names()
        self._text: Dict[Path, Optional[str]] = {}
        self.inbound: Dict[str, Set[str]] = {}
        starts = [ws.root]
        if ws.vault != ws.root and ws.vault.is_symlink():
            starts.append(ws.vault)     # the walk does not follow links; a linked vault is still the vault
        for start in starts:
            for path in ws.walk(start, captures=False):
                if path.name.startswith("."):
                    continue
                rel = ws.rel(path)
                if rel.split("/", 1)[0] == REPORT_DIR and GENERATED_RE.match(path.name):
                    continue
                self.files.append(path)
        self.files.sort(key=lambda p: ws.rel(p))

    def text(self, path: Path) -> Optional[str]:
        if path not in self._text:
            try:
                self._text[path] = read_text(path)
            except NotText:
                self._text[path] = None
                self.unreadable.append(self.ws.rel(path))
            except OSError:
                self._text[path] = None
        return self._text[path]

    def body_text(self, path: Path) -> Optional[str]:
        """The text a file stands for: its own, or its OCR sidecar's."""
        if path.suffix.lower() in TEXT_EXTENSIONS:
            return self.text(path)
        sidecar = _sidecar_of(path)
        if sidecar is None:
            return None
        try:
            return read_text_lossy(sidecar)
        except OSError:
            return None

    def in_inbox(self, rel: str) -> bool:
        return rel.split("/", 1)[0] in UNFILED_ROOTS


def _in_wiki_sources(path: Path) -> bool:
    return path.parent.name == "sources" and (path.parent.parent / "wiki.md").is_file()


def _last_change(path: Path) -> Optional[float]:
    """When a file last changed here: the later of its modification time and
    its status-change time. A file copied in with an old date still has a
    status change from the day it arrived."""
    try:
        stat = os.lstat(str(path))
    except OSError:
        return None
    return max(stat.st_mtime, stat.st_ctime)


# ------------------------------------------------------------ rule 1

def rule_orphans(scan: Scan) -> List[dict]:
    ws = scan.ws
    folder = ws.root / "team-inbox" / "unsorted"
    items: Dict[str, float] = {}
    prefix = "team-inbox/unsorted/"
    for path in scan.files:
        rel = ws.rel(path)
        if rel.startswith(prefix):
            stamp = _last_change(path)
            if stamp is not None:
                items[rel] = stamp
    if folder.is_dir() and not folder.is_symlink():
        # An earshot capture directory is one thing to route, not its files.
        for current, dirs, names in os.walk(str(folder)):
            dirs[:] = sorted(d for d in dirs if not d.startswith(".")
                             and not os.path.islink(os.path.join(current, d)))
            if CAPTURE_MARKER in names and Path(current) != folder:
                dirs[:] = []
                stamps = [s for s in (_last_change(Path(current) / n) for n in names) if s is not None]
                own = _last_change(Path(current))
                if own is not None:
                    stamps.append(own)
                if stamps:
                    rel = ws.rel(Path(current)) + "/"
                    if not ws.ignore.match(rel.rstrip("/"), True):
                        items[rel] = max(stamps)
    out = []
    for rel, stamp in sorted(items.items()):
        age = (scan.today - _dt.date.fromtimestamp(stamp)).days
        if age > ORPHAN_DAYS:
            what = "capture directory, " if rel.endswith("/") else ""
            out.append({"id": fid("1", rel), "rule": "1", "severity": "finding", "path": rel, "age_days": age,
                        "text": "%s (%slast changed %d days ago)" % (code(rel), what, age)})
    return out


# ------------------------------------------------------------ rule 2

def _guarded_spans(body: str) -> List[Tuple[int, int]]:
    """Inline code and comments, plus `%%…%%` and `$$…$$` on one line."""
    spans = protected_spans(body)
    for fence in ("%%", "$$"):
        start = body.find(fence)
        while start != -1:
            close = body.find(fence, start + 2)
            if close == -1:
                break
            spans.append((start, close + 2))
            start = body.find(fence, close + 2)
    return spans


def _destination(body: str, start: int) -> Optional[str]:
    """The destination of an inline link whose `(` ends at `start`, or None
    when what follows is not a link destination. Parentheses may nest."""
    idx = start
    while idx < len(body) and body[idx] in " \t":
        idx += 1
    if idx < len(body) and body[idx] == "<":
        close = body.find(">", idx + 1)
        return body[idx + 1:close] if close != -1 else None
    depth = 0
    begin = idx
    while idx < len(body):
        char = body[idx]
        if char == "\\" and idx + 1 < len(body):
            idx += 2
            continue
        if char in " \t":
            break
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                break
            depth -= 1
        idx += 1
    if idx >= len(body) or depth:
        return None
    return body[begin:idx] or None


class Links:
    """Resolves links the way they are written, and remembers who links where."""

    def __init__(self, scan: Scan):
        self.scan = scan
        self.ws = scan.ws
        self.root = str(self.ws.root)
        self._bare: Optional[Dict[str, List[Path]]] = None

    def bare(self, name: str) -> List[Path]:
        """Vault files a bare `[[name]]` could mean (by file name or note name)."""
        if self._bare is None:
            self._bare = {}
            vault = self.ws.vault
            for candidate in self.scan.files:
                if vault != candidate.parent and vault not in candidate.parents:
                    continue
                keys = {_nfc(candidate.name).casefold()}
                if candidate.suffix.lower() in MARKDOWN:
                    keys.add(_nfc(candidate.stem).casefold())
                for key in keys:
                    self._bare.setdefault(key, []).append(candidate)
        return self._bare.get(_nfc(name).casefold(), [])

    def wikilink(self, target: str) -> Tuple[str, Optional[Path], Optional[str]]:
        """(state, file, suggestion) for a wikilink target."""
        ws = self.ws
        target = target.lstrip("/")
        parts = tuple(target.split("/"))
        if not target or ".." in parts:
            return "skip", None, None
        best = "missing"
        for base in ((ws.vault, ws.root) if ws.vault != ws.root else (ws.root,)):
            for option in (parts[:-1] + (parts[-1] + ".md",), parts):
                state, found = self.scan.names.find(base, option)
                if state == "ok":
                    return "ok", found, None
                if state == "case":
                    best = "case"
        if "/" not in target:
            same = self.bare(target)
            if len(same) == 1:
                if ws.obsidian_present:
                    return "ok", same[0], None      # Obsidian's shortest-path link
                rel = ws.vault_rel(same[0])
                return best, None, "[[%s]]" % (rel[:-3] if rel.lower().endswith(".md") else rel)
            if len(same) > 1 and ws.obsidian_present:
                return "ambiguous", None, "%d notes have that name" % len(same)
        return best, None, None

    def path_link(self, source: Path, dest: str) -> Tuple[str, Optional[Path]]:
        """(state, file) for a relative markdown destination."""
        if not dest or dest.startswith(("#", "/", "\\")) or _SCHEME_RE.match(dest):
            return "skip", None
        dest = _percent_decode(dest.split("#", 1)[0].split("?", 1)[0])
        if not dest:
            return "skip", None
        candidate = os.path.normpath(os.path.join(str(source.parent), dest))
        if candidate != self.root and not candidate.startswith(self.root.rstrip(os.sep) + os.sep):
            return "skip", None                 # outside the workspace: not ours to judge
        parts = tuple(os.path.relpath(candidate, self.root).split(os.sep))
        return self.scan.names.find(self.ws.root, parts)


def rule_links(scan: Scan) -> List[dict]:
    """Broken links. Also fills `scan.inbound` (who links to each file)."""
    ws = scan.ws
    links = Links(scan)
    broken: Dict[Tuple[str, str], dict] = {}

    def note_inbound(target: Optional[Path], source_rel: str) -> None:
        if target is not None and target.is_file():
            try:
                scan.inbound.setdefault(ws.rel(target), set()).add(source_rel)
            except ValueError:
                pass

    def add(source_rel: str, shown: str, line_no: int, topic: Optional[str], state: str,
            suggestion: Optional[str]) -> None:
        slot = broken.setdefault((source_rel, shown), {"lines": [], "topic": topic, "state": state,
                                                       "suggestion": suggestion})
        slot["lines"].append(line_no)
        if topic and not slot["topic"]:
            slot["topic"] = topic

    for path in scan.files:
        if path.suffix.lower() not in MARKDOWN:
            continue
        text = scan.text(path)
        if text is None or ("[" not in text):
            continue
        source_rel = ws.rel(path)
        lines = split_lines(text)
        mask = _line_masks(lines)
        topics: Dict[int, str] = {}
        if path.name == MOC_NAME:
            table = pointers.locate(lines)
            if not table.problem:
                topics = {row.line: row.topic for row in table.rows if row.ok}
        for idx, line in enumerate(lines):
            if mask[idx] or "[" not in line:
                continue
            body = line_body(line)
            guarded = _guarded_spans(body)

            def hidden(start: int) -> bool:
                return any(a <= start < b for a, b in guarded)

            for match in WIKILINK_RE.finditer(body):
                start = match.start()
                if (start > 0 and body[start - 1] == "\\") or hidden(start):
                    continue
                target = link_target(match.group("target"))
                if not target:
                    continue
                state, found, suggestion = links.wikilink(target)
                if state == "ok":
                    note_inbound(found, source_rel)
                elif state != "skip":
                    add(source_rel, "[[%s]]" % target, idx + 1, topics.get(idx), state, suggestion)
            destinations: List[Tuple[int, str]] = []
            for match in _LINK_OPEN_RE.finditer(body):
                if hidden(match.start()):
                    continue
                dest = _destination(body, match.end())
                if dest is not None:
                    destinations.append((match.start(), dest.strip()))
            definition = _REF_DEF_RE.match(body)
            if definition and not hidden(0):
                destinations.append((0, (definition.group(2) or definition.group(3) or "").strip()))
            for _start, dest in destinations:
                state, found = links.path_link(path, dest)
                if state == "ok":
                    note_inbound(found, source_rel)
                elif state != "skip":
                    add(source_rel, dest, idx + 1, topics.get(idx), state, None)

    out = []
    for (source_rel, shown), slot in sorted(broken.items()):
        lines = sorted(set(slot["lines"]))
        where = "%s:%s" % (source_rel, ",".join(str(n) for n in lines[:5]) + ("…" if len(lines) > 5 else ""))
        if slot["state"] == "case":
            reason = "differs only in upper and lower case from a file that is there"
        elif slot["state"] == "ambiguous":
            reason = "ambiguous: %s" % slot["suggestion"]
        else:
            reason = "missing"
        text = "%s → %s (%s" % (code(where), code(shown), reason)
        if slot["topic"]:
            text += "; in the Pointers row for topic '%s'" % slot["topic"]
        text += ")"
        suggestion = slot["suggestion"] if slot["state"] != "ambiguous" else None
        if suggestion:
            text += "; the only note of that name is %s" % code(suggestion)
        out.append({"id": fid("2", source_rel, shown), "rule": "2", "severity": "finding", "source": source_rel,
                    "target": shown, "lines": lines, "topic": slot["topic"], "suggestion": suggestion,
                    "reason": slot["state"], "text": text})
    return out


# ------------------------------------------------------------ rule 3

def _wiki_pages(scan: Scan) -> List[Path]:
    vault = scan.ws.vault
    return [p for p in scan.files if p.name == "wiki.md" and p.parent != vault and vault in p.parents]


def rule_wiki_sources(scan: Scan) -> List[dict]:
    ws = scan.ws
    out = []
    for wiki in _wiki_pages(scan):
        text = scan.text(wiki)
        if text is None:
            continue
        lines = split_lines(text)
        mask = block_mask(lines)
        head = find_heading(lines, mask, "Sources", 2)
        if head is None:
            continue
        wiki_rel = ws.rel(wiki)
        seen: Set[str] = set()
        for idx in range(head + 1, section_end(lines, mask, head)):
            if mask[idx]:
                continue
            body = line_body(lines[idx])
            if not _BULLET_RE.match(body):
                continue
            for match in _CODE_SPAN_RE.finditer(body):
                cited = match.group(1).strip()
                if (not cited or cited in seen or any(char in cited for char in "<>{}")
                        or _SCHEME_RE.match(cited) or not _PATHISH_RE.search(cited.split("#", 1)[0])):
                    continue
                seen.add(cited)
                plain = cited.split("#", 1)[0].lstrip("/")
                if not plain:
                    continue
                parts = tuple(plain.split("/"))
                if ".." in parts:
                    continue
                if any(scan.names.find(base, parts)[0] == "ok" for base in (ws.root, ws.vault, wiki.parent)):
                    continue
                out.append({"id": fid("3", wiki_rel, cited), "rule": "3", "severity": "finding", "wiki": wiki_rel,
                            "cited": cited, "text": "%s cites %s (missing)" % (code(wiki_rel), code(cited))})
    return out


# ------------------------------------------------------------ rule 4

def rule_repo_map(scan: Scan) -> List[dict]:
    ws = scan.ws
    out = []
    entries = ws.repo_map()
    if not entries:
        scan.notes.append("Rule 4 skipped: CLAUDE.md has no readable Repo Map.")
        return out
    for entry in entries:
        folder = ws.root / entry.folder
        if not folder.is_dir():
            state = "the folder does not exist"
        elif any(p.suffix.lower() in INDEXABLE for p in ws.walk(folder)):
            continue
        else:
            state = "nothing indexable in it"
        out.append({"id": fid("4", entry.folder), "rule": "4", "severity": "finding", "folder": entry.folder,
                    "text": "%s — %s" % (code(entry.folder + "/"), state)})
    return out


# ------------------------------------------------------------ rule 5

def rule_timelines(scan: Scan) -> List[dict]:
    ws = scan.ws
    reg = registry(ws)
    if reg.home is None:
        scan.notes.append("Rule 5 skipped: the workspace has no people folder.")
        return []
    from . import backfill
    try:
        plan = backfill.plan(ws, write=False, seed=0)
    except ToolError as exc:
        scan.notes.append("Rule 5 skipped: %s" % exc.message)
        return []
    pairs = sorted((entry["note"], entry["slug"]) for entry in plan["entries"])
    if not pairs:
        return []
    notes = sorted({note for note, _ in pairs})
    people = len({slug for _, slug in pairs})
    examples = ["%s → %s" % (code(note), slug) for note, slug in pairs[:RULE5_EXAMPLES]]
    text = "%d note%s (%d timeline line%s) across %d %s" % (
        len(notes), "" if len(notes) == 1 else "s", len(pairs), "" if len(pairs) == 1 else "s",
        people, "person" if people == 1 else "people")
    return [{"id": "5-timelines", "rule": "5", "severity": "info", "notes": len(notes), "lines": len(pairs),
             "examples": examples, "more": max(0, len(pairs) - RULE5_EXAMPLES), "text": text}]


# ------------------------------------------------------------ rule 8a, 8b, 8c

class Doc:
    """A file the duplicate rules consider."""
    __slots__ = ("path", "rel", "size", "sha", "norm_hash", "words")

    def __init__(self, path: Path, rel: str, size: int):
        self.path = path
        self.rel = rel
        self.size = size
        self.sha: Optional[str] = None
        self.norm_hash: Optional[str] = None
        self.words = 0


def shingle_hashes(norm: str) -> Set[int]:
    """Hashes of the 5-word shingles of normalised text. CRC-32, so the
    result is the same on every machine and run (`hash()` is salted)."""
    words = _WORD_RE.findall(norm)
    if len(words) < SHINGLE:
        return set()
    crc = zlib.crc32
    return {crc(" ".join(group).encode("utf-8", "replace"))
            for group in zip(*(words[offset:] for offset in range(SHINGLE)))}


def signature(hashes: Set[int]) -> List[int]:
    """One-permutation MinHash: the smallest hash in each of 64 bins."""
    sig = [-1] * SIG_BINS
    shift = 32 - (SIG_BINS.bit_length() - 1)
    for value in hashes:
        slot = value >> shift
        if sig[slot] == -1 or value < sig[slot]:
            sig[slot] = value
    return sig


def compare(a: Set[int], b: Set[int]) -> Tuple[float, float]:
    """(similarity, containment of the smaller in the larger)."""
    if not a or not b:
        return 0.0, 0.0
    shared = len(a & b)
    return shared / float(len(a) + len(b) - shared), shared / float(min(len(a), len(b)))


class _Union:
    def __init__(self, size: int):
        self.parent = list(range(size))

    def find(self, index: int) -> int:
        parent = self.parent
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def join(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            if ra < rb:
                self.parent[rb] = ra            # the lowest index stays the root: a stable representative
            else:
                self.parent[ra] = rb


def near_edges(scan: Scan, docs: List[Doc]) -> List[Tuple[int, int, float, float]]:
    """Pairs of `docs` (indices) that are near-duplicates or one inside the
    other, as (first, second, similarity, containment).

    Candidates come from MinHash bands (similar pairs) and from an index of
    sampled shingles (one note inside a longer one, which bands cannot see).
    A cheap estimate from the signatures or the samples decides whether a
    pair is worth reading both files for; the files then settle it exactly.
    Notes sharing a band or a sample with many others are compared against
    one representative, so a large family costs one comparison per member.
    """
    count = len(docs)
    sigs: List[List[int]] = []
    sample_count: List[int] = []
    bands: Dict[Tuple[int, Tuple[int, ...]], List[int]] = {}
    postings: Dict[int, object] = {}
    cache: "OrderedDict[int, Set[int]]" = OrderedDict()

    def hashes_of(index: int) -> Set[int]:
        if index in cache:
            cache.move_to_end(index)
            return cache[index]
        value = shingle_hashes(normalise(scan.body_text(docs[index].path) or ""))
        cache[index] = value
        if len(cache) > SET_CACHE:
            cache.popitem(last=False)
        return value

    for index in range(count):
        hashes = shingle_hashes(normalise(scan.body_text(docs[index].path) or ""))
        sig = signature(hashes)
        sigs.append(sig)
        for band in range(SIG_BINS // BAND_ROWS):
            rows = tuple(sig[band * BAND_ROWS:(band + 1) * BAND_ROWS])
            if any(value != -1 for value in rows):
                bands.setdefault((band, rows), []).append(index)
        sampled = 0
        for value in hashes:
            if not value & SAMPLE_MASK:
                sampled += 1
                held = postings.get(value)
                if held is None:
                    postings[value] = index
                elif isinstance(held, list):
                    held.append(index)
                else:
                    postings[value] = [held, index]
        sample_count.append(sampled)

    union = _Union(count)
    edges: List[Tuple[int, int, float, float]] = []
    settled: Dict[Tuple[int, int], bool] = {}

    def exact(first: int, second: int) -> bool:
        key = (first, second) if first < second else (second, first)
        if key not in settled:
            similarity, containment = compare(hashes_of(key[0]), hashes_of(key[1]))
            settled[key] = similarity >= SIMILARITY or containment >= CONTAINMENT
            if settled[key]:
                edges.append((key[0], key[1], similarity, containment))
                union.join(key[0], key[1])
        return settled[key]

    def alike(first: int, second: int) -> bool:
        """From the signatures alone: could these two be 80% similar?"""
        a, b = sigs[first], sigs[second]
        both = same = 0
        for x, y in zip(a, b):
            if x != -1 or y != -1:
                both += 1
                if x == y:
                    same += 1
        return both > 0 and same >= 0.55 * both

    boilerplate = 0
    for members in bands.values():
        if len(members) < 2:
            continue
        if len(members) <= SMALL_BUCKET:
            for i, first in enumerate(members):
                for second in members[i + 1:]:
                    if union.find(first) != union.find(second) and alike(first, second):
                        exact(first, second)
            continue
        # A family, or boilerplate: compare everyone with a representative,
        # then (for what is left) with the next one, a few times over.
        remaining = members
        rounds = 1 if len(members) > POSTING_CAP else 4
        for _ in range(rounds):
            if len(remaining) < 2:
                break
            head, rest = remaining[0], []
            for other in remaining[1:]:
                if union.find(other) == union.find(head):
                    continue
                if not (alike(head, other) and exact(head, other)):
                    rest.append(other)
            remaining = rest
        if len(members) > POSTING_CAP and len(remaining) > POSTING_CAP:
            boilerplate += 1

    # Containment: count sampled shingles shared between the representatives
    # of what is not already joined.
    shared: Dict[Tuple[int, int], int] = {}
    for held in postings.values():
        if not isinstance(held, list):
            continue
        reps = sorted({union.find(index) for index in held})
        if len(reps) < 2:
            continue
        if len(reps) <= SMALL_BUCKET * 2:
            for i, first in enumerate(reps):
                for second in reps[i + 1:]:
                    shared[(first, second)] = shared.get((first, second), 0) + 1
        else:
            if len(reps) > POSTING_CAP:
                boilerplate += 1
            head = reps[0]
            for other in reps[1:]:
                shared[(head, other)] = shared.get((head, other), 0) + 1
    for (first, second), number in sorted(shared.items()):
        smaller = min(sample_count[first], sample_count[second])
        larger = max(sample_count[first], sample_count[second])
        if number < 2 or union.find(first) == union.find(second):
            continue
        if smaller >= 16:
            estimate_containment = number / float(smaller)
            estimate_similarity = number / float(smaller + larger - number)
            if estimate_containment < 0.75 and estimate_similarity < 0.65:
                continue
        elif number < int(math.ceil(0.5 * smaller)):
            continue
        exact(first, second)
    if boilerplate:
        scan.notes.append("Rule 8c: %d passage(s) shared by more than %d otherwise different notes were treated "
                          "as boilerplate; notes that share only that are not paired." % (boilerplate, POSTING_CAP))
    return edges


def rule_duplicates(scan: Scan, near: bool) -> List[dict]:
    """8a, 8b and (when `near`) 8c: one finding per set of copies, filed
    under the broadest rule that holds for the set."""
    ws = scan.ws
    docs: List[Doc] = []
    for path in scan.files:
        if _is_sidecar(path) or path.name == MOC_NAME:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if not size:
            continue
        doc = Doc(path, ws.rel(path), size)
        is_text = path.suffix.lower() in TEXT_EXTENSIONS
        text = scan.body_text(path)
        if text is not None and content_chars(text) >= MIN_CONTENT_CHARS:
            norm = normalise(text)
            doc.norm_hash = hashlib.sha256(norm.encode("utf-8", "replace")).hexdigest()
            doc.words = len(_WORD_RE.findall(norm))
        elif is_text or size < MIN_BINARY_BYTES:
            continue                            # too slight to call a duplicate of anything
        docs.append(doc)

    union = _Union(len(docs))
    by_size: Dict[int, List[int]] = {}
    for index, doc in enumerate(docs):
        by_size.setdefault(doc.size, []).append(index)
    by_sha: Dict[str, int] = {}
    for indices in by_size.values():
        if len(indices) < 2:
            continue
        for index in indices:
            try:
                docs[index].sha = sha256_file(docs[index].path)
            except OSError:
                continue
            first = by_sha.setdefault(docs[index].sha, index)
            union.join(first, index)
    by_norm: Dict[str, int] = {}
    for index, doc in enumerate(docs):
        if doc.norm_hash is not None:
            first = by_norm.setdefault(doc.norm_hash, index)
            union.join(first, index)
    evidence: Dict[int, Tuple[float, float]] = {}
    if near:
        # One representative per distinct text: copies of it are already joined.
        reps = [index for index in sorted(by_norm.values()) if docs[index].words >= MIN_WORDS]
        edges = near_edges(scan, [docs[index] for index in reps])
        for first, second, _similarity, _containment in edges:
            union.join(reps[first], reps[second])
        for first, _second, similarity, containment in edges:
            root = union.find(reps[first])
            best = evidence.get(root, (0.0, 0.0))
            evidence[root] = (max(best[0], similarity), max(best[1], containment))

    groups: Dict[int, List[int]] = {}
    for index in range(len(docs)):
        groups.setdefault(union.find(index), []).append(index)
    out = []
    for root, indices in sorted(groups.items(), key=lambda kv: docs[kv[1][0]].rel):
        if len(indices) < 2:
            continue
        members = []
        for index in indices:
            doc = docs[index]
            if doc.sha is None:
                try:
                    doc.sha = sha256_file(doc.path)
                except OSError:
                    doc.sha = "unreadable:" + doc.rel
            stamp = _last_change(doc.path) or 0.0
            try:
                mtime = doc.path.stat().st_mtime
            except OSError:
                mtime = 0.0
            members.append({"path": doc.rel, "size": doc.size,
                            "modified": _dt.date.fromtimestamp(mtime).isoformat() if mtime else "",
                            "inbound": len(scan.inbound.get(doc.rel, ())), "inbox": scan.in_inbox(doc.rel),
                            "_mtime": mtime, "_sha": doc.sha, "_norm": doc.norm_hash, "_stamp": stamp})
        members.sort(key=lambda m: m["path"])
        keeper = sorted(members, key=lambda m: (-m["inbound"], m["inbox"], m["_mtime"], m["path"]))[0]
        texts = {m["_norm"] for m in members}
        shas = {m["_sha"] for m in members}
        if len(texts) > 1:
            rule = "8c"
            similarity, containment = evidence.get(root, (0.0, 0.0))
            detail = ("up to %d%% alike" % int(similarity * 100)) if similarity >= SIMILARITY \
                else ("one holds %d%% of another" % int(containment * 100))
        elif len(shas) > 1:
            rule, detail = "8b", "the same text once frontmatter, case and spacing are set aside"
        else:
            rule, detail = "8a", "byte for byte the same"
        for member in members:
            if member is keeper:
                member["relation"] = "keeper"
            elif member["_sha"] == keeper["_sha"]:
                member["relation"] = "bytes"
            elif member["_norm"] is not None and member["_norm"] == keeper["_norm"]:
                member["relation"] = "text"
            else:
                member["relation"] = "near"
        outside = [m for m in members if not _in_wiki_sources(ws.root / m["path"])]
        copy = len(outside) <= 1 and len(outside) < len(members)
        for member in members:
            for key in ("_mtime", "_sha", "_norm", "_stamp"):
                member.pop(key)
        finding = {"id": fid(rule, *[m["path"] for m in members]), "rule": rule,
                   "severity": "info" if copy else "finding", "members": members, "keeper": keeper["path"],
                   "wiki_source_copy": copy, "detail": detail,
                   "text": "%d files, %s" % (len(members), detail)}
        if rule == "8c":
            finding["similarity"] = round(evidence.get(root, (0.0, 0.0))[0], 3)
            finding["containment"] = round(evidence.get(root, (0.0, 0.0))[1], 3)
        out.append(finding)
    return out


# ------------------------------------------------------------ rule 8d

def rule_entities(scan: Scan) -> List[dict]:
    ws = scan.ws
    out = []
    reg = registry(ws)
    people = sorted(reg.people.values(), key=lambda p: p.slug)
    keys = {}
    for person in people:
        names = {" ".join(words_of(person.name)), " ".join(words_of(person.slug))}
        names |= {" ".join(words_of(alias)) for alias in person.aliases}
        keys[person.slug] = ({name for name in names if name}, set(words_of(person.slug)))
    for i, first in enumerate(people):
        for second in people[i + 1:]:
            names_a, tokens_a = keys[first.slug]
            names_b, tokens_b = keys[second.slug]
            common = sorted(names_a & names_b)
            if common:
                why = "both answer to \"%s\"" % common[0]
            elif tokens_a and tokens_b and (tokens_a < tokens_b or tokens_b < tokens_a):
                why = "one folder name is contained in the other"
            else:
                continue
            a, b = ws.rel(first.folder), ws.rel(second.folder)
            out.append({"id": fid("8d", "person", first.slug, second.slug), "rule": "8d", "severity": "finding",
                        "kind": "person", "subjects": [a, b],
                        "text": "person folders %s and %s: %s" % (code(a + "/"), code(b + "/"), why)})

    topics: Dict[str, List[str]] = {}
    for wiki in _wiki_pages(scan):
        text = scan.text(wiki)
        if text is None:
            continue
        lines = split_lines(text)
        fm = frontmatter.parse(lines)
        topic = frontmatter.get_scalar(lines, fm, "topic").strip().casefold()
        if topic:
            topics.setdefault(topic, []).append(ws.rel(wiki))
    for topic, pages in sorted(topics.items()):
        if len(pages) > 1:
            out.append({"id": fid("8d", "wiki", topic), "rule": "8d", "severity": "finding", "kind": "wiki",
                        "subjects": sorted(pages),
                        "text": "wikis sharing the topic '%s': %s" % (topic, ", ".join(code(p) for p in sorted(pages)))})

    for moc in scan.files:
        if moc.name != MOC_NAME:
            continue
        text = scan.text(moc)
        if text is None:
            continue
        table = pointers.locate(split_lines(text))
        if table.problem:
            continue
        seen: Dict[str, List[int]] = {}
        shown: Dict[str, str] = {}
        for row in table.rows:
            if not row.ok:
                continue
            slug = pointers.slugify(row.topic)
            if slug:
                seen.setdefault(slug, []).append(row.line + 1)
                shown.setdefault(slug, row.topic)
        moc_rel = ws.rel(moc)
        for slug, row_lines in sorted(seen.items()):
            if len(row_lines) > 1:
                out.append({"id": fid("8d", "topic", moc_rel, slug), "rule": "8d", "severity": "finding",
                            "kind": "topic", "subjects": [moc_rel],
                            "text": "%s has %d Pointers rows for the topic '%s' (lines %s)" % (
                                code(moc_rel), len(row_lines), shown[slug], ", ".join(str(n) for n in row_lines))})
    return out


# ------------------------------------------------------------ suppressions

def _suppress_path(ws: Workspace) -> Path:
    return ws.pka / SUPPRESS_FILE


def _refuse_generated(ws: Workspace, path: Path) -> None:
    problem = generated_problem(ws.root, path)
    if problem:
        raise ToolError("%s. Lint does not write through links or over things that are not its own files; "
                        "nothing was written." % problem, EXIT_FAIL)


def load_suppressions(ws: Workspace) -> dict:
    """The whole file as data, with `suppressed` guaranteed to be a mapping.
    Keys and entries this version does not know are kept as they are."""
    path = _suppress_path(ws)
    _refuse_generated(ws, path)
    if not path.is_file():
        return {"version": SUPPRESS_VERSION, "suppressed": {}}
    rel = ws.rel(path)
    try:
        data = json.loads(path.read_bytes().decode("utf-8-sig"))
    except (OSError, ValueError, RecursionError) as exc:
        reason = "it is nested too deeply" if isinstance(exc, RecursionError) else str(exc)
        raise ToolError("%s could not be read as JSON (%s). Nothing was changed; fix or remove the file and "
                        "run again." % (rel, reason), EXIT_FAIL)
    if not isinstance(data, dict) or not isinstance(data.get("suppressed", {}), dict):
        raise ToolError("%s is not a lint suppressions file (expected an object with a \"suppressed\" object). "
                        "Nothing was changed; fix or remove the file and run again." % rel, EXIT_FAIL)
    data.setdefault("suppressed", {})
    return data


def _newer_version(data: dict) -> bool:
    version = data.get("version", SUPPRESS_VERSION)
    return isinstance(version, int) and not isinstance(version, bool) and version > SUPPRESS_VERSION


def _save_suppressions(ws: Workspace, data: dict) -> None:
    if _newer_version(data):
        raise ToolError("%s was written by a later release (version %s). This release reads it but will not "
                        "rewrite it; update pka-tools (bootstrap upgrade) and try again."
                        % (ws.rel(_suppress_path(ws)), data.get("version")), EXIT_FAIL)
    data.setdefault("version", SUPPRESS_VERSION)
    try:
        write_generated(ws.root, _suppress_path(ws),
                        json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
    except GeneratedRefused as exc:
        raise ToolError("%s; nothing was written." % exc, EXIT_FAIL)


@contextlib.contextmanager
def _locked(ws: Workspace) -> Iterator[None]:
    """One writer at a time for the suppressions file (read, change, write)."""
    _refuse_generated(ws, _suppress_path(ws))
    ws.pka.mkdir(parents=True, exist_ok=True)
    try:
        import fcntl
    except ImportError:                         # no fcntl (Windows): a lock file instead
        fcntl = None                            # type: ignore[assignment]
    if fcntl is not None:
        handle = os.open(str(ws.pka), os.O_RDONLY)
        try:
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(handle, fcntl.LOCK_UN)
            finally:
                os.close(handle)
        return
    lock = ws.pka / ".lint-suppressions.lock"
    for _ in range(200):
        try:
            os.close(os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except FileExistsError:
            time.sleep(0.05)
    else:
        raise ToolError("another lint command is changing the suppressions (or left %s behind); try again, or "
                        "remove that file" % ws.rel(lock), EXIT_FAIL)
    try:
        yield
    finally:
        try:
            os.unlink(str(lock))
        except OSError:
            pass


def _reports(ws: Workspace) -> List[Tuple[_dt.date, Path]]:
    """Lint reports with a real date that is not in the future, oldest first.
    Links and anything that is not a regular file do not count."""
    folder = ws.root / REPORT_DIR
    out = []
    if folder.is_dir() and not folder.is_symlink():
        day = today()
        for entry in os.scandir(str(folder)):
            match = REPORT_RE.match(entry.name)
            if not match or entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                continue
            try:
                date = _dt.date.fromisoformat(match.group(1))
            except ValueError:
                continue
            if date <= day:
                out.append((date, Path(entry.path)))
    return sorted(out)


def _report_ids(path: Path) -> Tuple[Dict[str, str], Set[str], dict]:
    """(id -> the line that shows it, ids that are informational, header)."""
    ids: Dict[str, str] = {}
    info: Set[str] = set()
    header: dict = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ids, info, header
    for number, line in enumerate(text.splitlines()):
        if number == 0:
            match = HEADER_RE.match(line)
            if match:
                try:
                    parsed = json.loads(match.group(1))
                    header = parsed if isinstance(parsed, dict) else {}
                except ValueError:
                    header = {}
            continue
        if LIBRARIAN_MARK in line:
            break
        more = MORE_IDS_RE.match(line)
        if more:
            for ident in more.group(2).split():
                ids.setdefault(ident, "(not shown in the report; `pka-tools lint --json` has it)")
                if more.group(1):
                    info.add(ident)
            continue
        for match in ID_TAG_RE.finditer(line):
            subject = ID_TAG_RE.sub("", line).strip().lstrip("-#* ").strip()
            ids.setdefault(match.group(1), subject[:240])
            if match.group(2):
                info.add(match.group(1))
    return ids, info, header


def _find_id(ws: Workspace, ident: str) -> Tuple[Optional[str], List[str], bool]:
    """(subject or None, ids to offer as near matches, whether any report exists)."""
    day = today()
    recent = [(date, path) for date, path in _reports(ws) if (day - date).days <= SUPPRESS_LOOKBACK_DAYS]
    known: List[str] = []
    for _date, path in reversed(recent):
        ids, _info, _header = _report_ids(path)
        if ident in ids:
            return ids[ident], [], True
        known += [other for other in sorted(ids) if other not in known]
    return None, known, bool(recent)


def suppress(ws: Workspace, ident: str, reason: Optional[str] = None) -> dict:
    if ident.split("-", 1)[0] == "5":
        raise ToolError("rule 5 is information, not a finding, and cannot be suppressed (that would hide every "
                        "note that is later left off a timeline). To clear it, ask the librarian to \"backfill "
                        "timelines\"; to leave one note off every timeline, give it `no-backref: true`.", EXIT_USAGE)
    with _locked(ws):
        data = load_suppressions(ws)
        entries = data["suppressed"]
        if ident in entries:
            entry = entries[ident] if isinstance(entries[ident], dict) else {}
            updated = reason is not None and entry.get("reason", "") != reason
            if updated:
                entry["reason"] = reason
                entries[ident] = entry
                _save_suppressions(ws, data)
            return {"id": ident, "suppressed": True, "already": True, "updated": updated, "entry": entry}
        subject, known, any_report = _find_id(ws, ident)
        if not any_report:
            raise ToolError("there is no lint report from the last %d days to take the id from; run "
                            "`pka-tools lint` first" % SUPPRESS_LOOKBACK_DAYS, EXIT_USAGE)
        if subject is None:
            near = difflib.get_close_matches(ident, known, n=5, cutoff=0.5)
            rule = ident.split("-", 1)[0]
            near += [other for other in known if other.split("-", 1)[0] == rule and other not in near][:5]
            hint = ("; near matches: %s" % ", ".join(near[:8])) if near else ""
            raise ToolError("no finding with the id %r in the lint reports of the last %d days%s"
                            % (ident, SUPPRESS_LOOKBACK_DAYS, hint), EXIT_USAGE)
        entry = {"at": _dt.datetime.now().isoformat(timespec="seconds"), "reason": reason or "",
                 "rule": ident.split("-", 1)[0], "subject": subject}
        entries[ident] = entry
        _save_suppressions(ws, data)
        return {"id": ident, "suppressed": True, "already": False, "updated": False, "entry": entry}


def unsuppress(ws: Workspace, ident: str) -> dict:
    with _locked(ws):
        data = load_suppressions(ws)
        if ident not in data["suppressed"]:
            raise ToolError("%r is not suppressed" % ident, EXIT_USAGE)
        if _newer_version(data):
            _save_suppressions(ws, data)        # raises: a later version's file is not rewritten
        entry = data["suppressed"].pop(ident)
        _save_suppressions(ws, data)
        return {"id": ident, "suppressed": False, "entry": entry}


def suppressions(ws: Workspace) -> dict:
    data = load_suppressions(ws)
    items = []
    for ident in sorted(data["suppressed"]):
        entry = data["suppressed"][ident]
        entry = entry if isinstance(entry, dict) else {}
        items.append({"id": ident, "rule": entry.get("rule", ident.split("-", 1)[0]),
                      "subject": entry.get("subject", ""), "reason": entry.get("reason", ""),
                      "at": entry.get("at", "")})
    return {"file": ws.rel(_suppress_path(ws)), "suppressed": items, "read_only": _newer_version(data)}


# ------------------------------------------------------------ run and report

def run(ws: Workspace, quick: bool = False, write_report: bool = True) -> dict:
    day = today()
    target = ws.root / REPORT_DIR / ("librarian-lint-%s.md" % day.isoformat())
    if write_report:
        _refuse_generated(ws, target)           # before any work: a refusal should be immediate
    stored = load_suppressions(ws)
    # Rule 5 is never hidden, whatever a file says.
    suppressed_ids = {ident for ident in stored["suppressed"] if ident.split("-", 1)[0] != "5"}
    scan = Scan(ws, day)
    if _newer_version(stored):
        scan.notes.append("%s was written by a later release; it was used as it is and not changed."
                          % ws.rel(_suppress_path(ws)))
    rules = QUICK_RULES if quick else FULL_RULES
    found: List[dict] = []
    links = rule_links(scan)            # first: the duplicate rules use its inbound counts
    found += rule_orphans(scan)
    found += links
    found += rule_wiki_sources(scan)
    found += rule_repo_map(scan)
    if "5" in rules:
        found += rule_timelines(scan)
    found += rule_duplicates(scan, near="8c" in rules)
    if "8d" in rules:
        found += rule_entities(scan)

    order = {rule: pos for pos, rule in enumerate(FULL_RULES)}
    found.sort(key=lambda f: (order[f["rule"]], f["text"], f["id"]))
    shown = [f for f in found if f["id"] not in suppressed_ids]
    hidden = [f for f in found if f["id"] in suppressed_ids]
    counts = {rule: sum(1 for f in shown if f["rule"] == rule and f["severity"] == "finding") for rule in rules}
    info_counts = {rule: sum(1 for f in shown if f["rule"] == rule and f["severity"] == "info") for rule in rules}
    result = {
        "date": day.isoformat(), "mode": "quick" if quick else "full", "rules": list(rules),
        "scanned": len(scan.files), "markdown": sum(1 for p in scan.files if p.suffix.lower() in MARKDOWN),
        "findings": sum(counts.values()), "info": sum(info_counts.values()),
        "suppressed": len(hidden), "suppressed_ids": sorted(f["id"] for f in hidden),
        "stale_suppressions": sorted(suppressed_ids - {f["id"] for f in found}) if not quick else [],
        "counts": counts, "info_counts": info_counts, "items": shown, "notes": scan.notes,
        "unreadable": sorted(set(scan.unreadable)), "unreadable_names": ws.unreadable_names,
        "report": None, "report_kept": None,
    }
    if write_report:
        carried = None
        if target.is_file():
            try:
                existing = target.read_text(encoding="utf-8", errors="replace")
            except OSError:
                existing = ""
            _ids, _info, header = _report_ids(target)
            if quick and header.get("mode") == "full":
                result["report_kept"] = ws.rel(target)
                scan.notes.append("Today's full report (%s) was kept: a quick lint does not replace it."
                                  % ws.rel(target))
                return result
            if LIBRARIAN_MARK in existing:
                tail = existing.split(LIBRARIAN_MARK, 1)[1]
                if tail.strip() and tail.strip() not in LIBRARIAN_DEFAULTS:
                    carried = tail
        result["report"] = ws.rel(target)
        try:
            write_generated(ws.root, target, render(result, carried))
        except GeneratedRefused as exc:
            raise ToolError("%s; the report was not written." % exc, EXIT_FAIL)
    return result


def _plural(count: int, one: str, many: str) -> str:
    return "%d %s" % (count, one if count == 1 else many)


def _counted(real: int, info: int) -> str:
    parts = []
    if real or not info:
        parts.append(_plural(real, "finding", "findings"))
    if info:
        parts.append("%d informational" % info)
    return ", ".join(parts)


def render(result: dict, carried: Optional[str] = None) -> str:
    header = {"version": HEADER_VERSION, "date": result["date"], "mode": result["mode"],
              "findings": result["findings"], "info": result["info"], "suppressed": result["suppressed"],
              "scanned": result["scanned"]}
    out = ["<!-- pka-lint %s -->" % json.dumps(header, sort_keys=True),
           "# Knowledge Base Health — %s" % result["date"], ""]
    out.append("Written by `pka-tools lint`%s. Nothing was changed: lint reports, you decide."
               % (" --quick" if result["mode"] == "quick" else ""))
    out.append("")
    out.append("- Scanned: %s (%d markdown)" % (_plural(result["scanned"], "file", "files"), result["markdown"]))
    out.append("- Checks run: %s" % ", ".join("rule %s" % rule for rule in result["rules"]))
    out.append("- Findings: %d" % result["findings"])
    out.append("- Informational: %d" % result["info"])
    out.append("- Suppressed: %d" % result["suppressed"])
    skipped = len(result["unreadable"]) + result["unreadable_names"]
    if skipped:
        out.append("- Not read: %s (see \"Not read\" below)" % _plural(skipped, "file", "files"))
    out.append("")
    out.append("## Summary")
    out.append("")
    by_rule: Dict[str, List[dict]] = {}
    for item in result["items"]:
        by_rule.setdefault(item["rule"], []).append(item)
    if not result["items"]:
        out.append("Nothing to report.")
    for rule in result["rules"]:
        if by_rule.get(rule):
            out.append("- Rule %s, %s: %s" % (rule, TITLES[rule][0].lower() + TITLES[rule][1:],
                                             _counted(result["counts"][rule], result["info_counts"][rule])))
    for rule in result["rules"]:
        items = by_rule.get(rule)
        if not items:
            continue
        out += ["", "## %s. %s (%s)" % (rule, TITLES[rule], _counted(result["counts"][rule],
                                                                    result["info_counts"][rule])),
                "", HINTS[rule], ""]
        for item in items[:REPORT_CAP]:
            info = item["severity"] == "info"
            tag = "[id: %s%s]" % (item["id"], ", information" if info else "")
            if rule in ("8a", "8b", "8c"):
                label = "Wiki source copy (information)" if item["wiki_source_copy"] else item["text"].capitalize()
                names = [code(member["path"]) for member in item["members"][:3]]
                if len(item["members"]) > 3:
                    names.append("and %d more" % (len(item["members"]) - 3))
                out.append("### %s: %s %s" % (label, ", ".join(names), tag))
                out.append("")
                out.append("| File | Size | Modified | Links to it | Compared with the keeper |")
                out.append("|---|---|---|---|---|")
                for member in item["members"]:
                    out.append("| %s | %s | %s | %d | %s |" % (
                        code(member["path"]).replace("|", "\\|"), human_size(member["size"]), member["modified"],
                        member["inbound"], RELATIONS[member["relation"]]))
                out.append("")
            elif rule == "5":
                out.append("- Information: %s are not on the timeline of someone they involve %s" % (item["text"], tag))
                out += ["  - %s" % example for example in item["examples"]]
                if item["more"]:
                    out.append("  - … and %d more" % item["more"])
            else:
                out.append("- %s%s %s" % ("Information: " if info else "", item["text"], tag))
        if len(items) > REPORT_CAP:
            rest = items[REPORT_CAP:]
            out.append("")
            out.append("… and %d more; `pka-tools lint --json` has all of them." % len(rest))
            real = [item["id"] for item in rest if item["severity"] != "info"]
            extra = [item["id"] for item in rest if item["severity"] == "info"]
            if real:
                out.append("<!-- pka-lint-ids: %s -->" % " ".join(real))
            if extra:
                out.append("<!-- pka-lint-info-ids: %s -->" % " ".join(extra))
    if skipped:
        out += ["", "## Not read", ""]
        if result["unreadable"]:
            out.append("%s not valid UTF-8, so the links and text in %s were not checked. Re-save as UTF-8 "
                       "to have %s checked:" % (("These are", "them", "them") if len(result["unreadable"]) != 1
                                                 else ("This is", "it", "it")))
            out.append("")
            out += ["- %s" % code(rel) for rel in result["unreadable"]]
        if result["unreadable_names"]:
            out.append("")
            out.append("%s a name that is not valid UTF-8 and %s skipped entirely. Rename %s to have %s checked."
                       % (("%d files have" % result["unreadable_names"], "were", "them", "them")
                          if result["unreadable_names"] != 1 else ("1 file has", "was", "it", "it")))
    if result["notes"] or result["stale_suppressions"]:
        out += ["", "## Notes", ""]
        out += ["- %s" % note for note in result["notes"]]
        if result["stale_suppressions"]:
            number = len(result["stale_suppressions"])
            out.append("- %s no longer %s anything and can be removed with `pka-tools lint unsuppress <id>`: %s"
                       % (_plural(number, "suppression", "suppressions"), "matches" if number == 1 else "match",
                          ", ".join(result["stale_suppressions"])))
    out += ["", "## Hiding a finding you have dealt with", "",
            "`.pka/bin/pka-tools lint suppress <id> --reason \"why\"` hides one finding from later reports "
            "(`lint suppressions` lists them, `lint unsuppress <id>` brings one back). An id belongs to the "
            "exact files or link it names: if a group of duplicates gains or loses a file, it is a new finding.",
            "", "## Librarian checks (rules 6 and 7)", ""]
    if carried is not None:
        return "\n".join(out) + "\n" + LIBRARIAN_MARK + carried
    out.append(LIBRARIAN_MARK)
    out.append(LIBRARIAN_DEFAULTS[0] if result["mode"] == "quick" else LIBRARIAN_DEFAULTS[1])
    return "\n".join(out) + "\n"


# ------------------------------------------------------------ latest, schedule

def latest(ws: Workspace) -> dict:
    reports = _reports(ws)
    if not reports:
        return {"report": None, "date": None, "age_days": None, "findings": None, "info": None,
                "suppressed": None, "mode": None, "recent": False, "mention": False}
    date, path = reports[-1]
    ids, info, header = _report_ids(path)
    age = (today() - date).days
    findings: Optional[int] = header.get("findings") if isinstance(header.get("findings"), int) else None
    if header and findings is not None:
        # What is still open: the report's findings less what has been suppressed since.
        try:
            hidden = set(load_suppressions(ws)["suppressed"])
        except ToolError:
            hidden = set()
        listed = [ident for ident in ids if ident not in info]
        if listed or findings == 0:
            findings = sum(1 for ident in listed if ident not in hidden)
    recent = 0 <= age <= RECENT_DAYS
    return {"report": ws.rel(path), "date": date.isoformat(), "age_days": age, "findings": findings,
            "info": header.get("info") if isinstance(header.get("info"), int) else None,
            "suppressed": header.get("suppressed") if isinstance(header.get("suppressed"), int) else None,
            "mode": header.get("mode"), "recent": recent, "mention": bool(recent and findings)}


def _xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def schedule(ws: Workspace) -> dict:
    root = str(ws.root)
    tool = str(ws.pka / "bin" / "pka-tools")
    log = str(ws.pka / "lint-cron-log.txt")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ws.root.name).strip("-").lower()
    digest = hashlib.sha256(root.encode("utf-8", "surrogateescape")).hexdigest()[:8]
    label = "org.pka-skills.lint.%s" % ("%s-%s" % (slug, digest) if slug else digest)

    def quoted(text: str) -> str:
        return "'" + text.replace("'", "'\\''") + "'"

    command = "/usr/bin/env python3 %s lint --quick --workspace %s >> %s 2>&1" % (
        quoted(tool), quoted(root), quoted(log))
    cron = "0 9 * * 1 " + command.replace("%", "\\%")      # cron reads a bare % as a newline
    plist = "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
        '<plist version="1.0">',
        "<dict>",
        "  <key>Label</key><string>%s</string>" % _xml(label),
        "  <key>ProgramArguments</key>",
        "  <array>",
        "    <string>/usr/bin/env</string>",
        "    <string>python3</string>",
        "    <string>%s</string>" % _xml(tool),
        "    <string>lint</string>",
        "    <string>--quick</string>",
        "    <string>--workspace</string>",
        "    <string>%s</string>" % _xml(root),
        "  </array>",
        "  <key>StandardOutPath</key><string>%s</string>" % _xml(log),
        "  <key>StandardErrorPath</key><string>%s</string>" % _xml(log),
        "  <key>StartCalendarInterval</key>",
        "  <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>9</integer>"
        "<key>Minute</key><integer>0</integer></dict>",
        "</dict>",
        "</plist>",
    ])
    return {"workspace": root, "label": label, "cron": cron, "launchd_plist": plist,
            "launchd_path": "~/Library/LaunchAgents/%s.plist" % label, "log": ws.rel(ws.pka / "lint-cron-log.txt"),
            "installed": False}
