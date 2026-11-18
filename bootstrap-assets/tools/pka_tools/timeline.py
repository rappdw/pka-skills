"""Person timelines: a managed block in `<people-home>/<slug>/index.md`.

    ## Timeline
    <!-- pka:timeline v1 — maintained by pka-tools; newest first; edit summaries freely, leave links alone -->
    - 2026-11-14 · meeting · [[leadership/2026-11-14-slt-sync|SLT sync]] — deferred the vendor decision
    - 2026-11-10 · 1on1 · [[personnel/priya/2026-11-10-1-1-priya|1-1]] — Q1 goals, hiring plan
    <!-- /pka:timeline -->

Line grammar: `- <date> · <kind> · <link>[ — <summary>]`, kind one of
`1on1`, `meeting`, `doc`. The link is a wikilink in an Obsidian vault and a
relative markdown link otherwise. A note is on a timeline when any link in
the block points at it; that is the key, so adding is idempotent.

What a timeline can link to (`Workspace.link_root`): in an Obsidian vault,
notes in the vault, since a wikilink cannot leave it; otherwise any note in
the workspace (`projects/`, `meeting-notes/`, …) except what is not filed
yet (`owner-inbox/`, `team-inbox/`) and hidden folders. Keys are relative
to that root. A wikilink written by hand in a workspace without Obsidian is
still read the way Obsidian reads it, relative to the vault.

The tool inserts a new line before the first line with an older date, and
rewrites a link target when a note moves. It never moves, re-sorts or
rewrites any other line, so a hand-edited summary, or text a user added
inside the block, stays as it is. A block it cannot read is reported and left
alone.

Who goes on a note's timeline (evidence tiers):
  T1  the note is inside the person's folder;
  T2  frontmatter `person` or `attendees` resolves with high confidence, a
      link in the note's `## Attendees` section points at the person's
      folder, or the person's slug appears as words of the filename.
Names that resolve ambiguously or not at all are reported, never added. A
meeting with more than LARGE_MEETING resolved attendees adds nobody from its
attendee lists unless asked (`include_large`), so an all-hands does not land
on forty timelines.
"""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote

from . import frontmatter
from .actions import note_date
from .errors import EXIT_USAGE, ToolError
from .markdown import WIKILINK_RE, block_mask, heading_of, link_target, unclosed_fence
from .actions import parse_date
from .people import INDEX, Person, Registry, registry, require_home, stub_text, words_of
from .textio import (
    NotText, detect_newline, has_bare_cr, line_body, line_end, read_text, split_lines, write_text_atomic,
)
from .workspace import MOC_NAME, Workspace

OPEN_MARK = "<!-- pka:timeline v1 — maintained by pka-tools; newest first; edit summaries freely, leave links alone -->"
CLOSE_MARK = "<!-- /pka:timeline -->"
HEADING = "## Timeline"
KINDS = ("1on1", "meeting", "doc")
LARGE_MEETING = 8
SUMMARY_MAX = 140

_OPEN_RE = re.compile(r"^\s*<!--\s*pka:timeline\b.*-->\s*$")
_CLOSE_RE = re.compile(r"^\s*<!--\s*/pka:timeline\s*-->\s*$")
_LINE_RE = re.compile(
    r"^- (?P<date>\d{4}-\d{2}-\d{2}) · (?P<kind>[\w-]+) · "
    r"(?P<link>\[\[[^\[\]\n]+\]\]|\[[^\]\n]*\]\((?:<[^>\n]*>|[^)\n]*)\))(?: — (?P<summary>.*))?$"
)
_MD_LINK = re.compile(r"\[[^\]\n]*\]\(\s*(<[^>\n]*>|[^)\s\n]*)[^)\n]*\)")
_ONE_ON_ONE = re.compile(r"^\d{4}-\d{2}-\d{2}-(?:1on1|1-1|1-on-1)(?:-.+)?$", re.IGNORECASE)
_DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}[-_ ]?")
_UNLINKABLE = set("[]|#^")


# ------------------------------------------------------------ the block

class Block:
    __slots__ = ("open", "close", "heading", "problem")

    def __init__(self) -> None:
        self.open: Optional[int] = None
        self.close: Optional[int] = None
        self.heading: Optional[int] = None    # a `## Timeline` heading without markers
        self.problem: Optional[str] = None


def locate(lines: List[str]) -> Block:
    block = Block()
    mask = block_mask(lines)          # fenced examples and HTML comments are not structure
    opens = [i for i, line in enumerate(lines) if not mask[i] and _OPEN_RE.match(line_body(line))]
    closes = [i for i, line in enumerate(lines) if not mask[i] and _CLOSE_RE.match(line_body(line))]
    if not opens and not closes:
        for idx, line in enumerate(lines):
            found = None if mask[idx] else heading_of(line)
            if found and found[0] == 2 and found[1].lower() == "timeline":
                block.heading = idx
                break
        return block
    if len(opens) != 1 or len(closes) != 1 or closes[0] < opens[0]:
        block.problem = "the timeline markers are missing, repeated or out of order"
        return block
    block.open, block.close = opens[0], closes[0]
    return block


def _href_key(ws: Workspace, index: Path, href: str) -> Optional[str]:
    href = href.strip()
    if href.startswith("<") and href.endswith(">"):
        href = href[1:-1]
    href = unquote(href.split("#", 1)[0])
    if not href or "://" in href:
        return None
    target = os.path.normpath(os.path.join(str(index.parent), href))
    try:
        rel = Path(target).relative_to(ws.link_root).as_posix()
    except ValueError:
        return None
    return rel[:-3] if rel.lower().endswith(".md") else rel


def _find_bare(ws: Workspace, name: str, cache: dict) -> Optional[str]:
    """The key of the one file in the vault called `name` (or `name.md`)."""
    if name not in cache:
        wanted = {name.casefold() + ".md", name.casefold()}
        hits = [p for p in ws.walk(ws.vault, captures=False) if p.name.casefold() in wanted]
        cache[name] = note_key(ws, hits[0]) if len(hits) == 1 and not ws.link_scope_problem(hits[0]) else None
    return cache[name]


def wiki_key(ws: Workspace, target: str, cache: Optional[dict] = None) -> str:
    """A wikilink target as a key. Obsidian reads it relative to the vault,
    and so do we; in a workspace whose keys are relative to the root, the
    vault's folder is put in front (and a bare name is looked up now)."""
    if ws.link_root == ws.vault:
        return target           # bare names are resolved by the caller (resolve_bare)
    cache = {} if cache is None else cache
    if "/" not in target:
        found = _find_bare(ws, target, cache)
        if found:
            return found
    joined = os.path.normpath(os.path.join(ws.rel(ws.vault), target)).replace(os.sep, "/")
    return joined


def _encode_href(rel: str) -> str:
    """A path as a markdown link target: `%` and `#` percent-encoded (so the
    path survives being read back), angle brackets around spaces."""
    rel = rel.replace("%", "%25").replace("#", "%23")
    if any(char in rel for char in " ()<>"):
        rel = "<%s>" % rel
    return rel


def resolve_bare(ws: Workspace, key: str, cache: Optional[dict] = None) -> str:
    """Obsidian's shortest form: `[[2026-11-12-sync]]` means the one file in
    the vault with that name. Return its full key, or the key unchanged."""
    if "/" in key or ws.link_root != ws.vault:
        return key              # without Obsidian, keys_in has resolved bare wikilinks already
    cache = {} if cache is None else cache
    return _find_bare(ws, key, cache) or key


def block_keys(ws: Workspace, index: Path, lines: List[str], block: Block, cache: Optional[dict] = None) -> List[str]:
    """The note each line of the block is about: a grammar line's own link,
    or the first link of any other line. Links in summaries do not count."""
    keys = []
    cache = {} if cache is None else cache
    if block.open is None:
        return keys
    for idx in range(block.open + 1, block.close):
        body = line_body(lines[idx])
        match = _LINE_RE.match(body)
        found = keys_in(ws, index, match.group("link") if match else body, cache)
        if found:
            keys.append(resolve_bare(ws, found[0], cache))
    return keys


def keys_in(ws: Workspace, index: Path, text: str, cache: Optional[dict] = None) -> List[str]:
    """Note keys (relative to the link root, no `.md`) of every link in some text."""
    keys = [wiki_key(ws, link_target(m.group("target")), cache) for m in WIKILINK_RE.finditer(text)]
    for match in _MD_LINK.finditer(text):
        key = _href_key(ws, index, match.group(1))
        if key:
            keys.append(key)
    return keys


def entries(ws: Workspace, index: Path, lines: List[str], block: Block) -> List[dict]:
    out = []
    if block.open is None:
        return out
    for idx in range(block.open + 1, block.close):
        match = _LINE_RE.match(line_body(lines[idx]))
        if not match:
            continue
        keys = keys_in(ws, index, match.group("link"))
        out.append({"line": idx, "date": match.group("date"), "kind": match.group("kind"),
                    "key": keys[0] if keys else None, "summary": (match.group("summary") or "").strip()})
    return out


# ------------------------------------------------------------ one line

def note_key(ws: Workspace, path: Path) -> str:
    rel = ws.link_rel(path)
    return rel[:-3] if rel.lower().endswith(".md") else rel


def note_file(ws: Workspace, key: str) -> Optional[Path]:
    """The file a key names, or None."""
    base = ws.link_root / key
    for candidate in (Path(str(base) + ".md"), base):
        if candidate.is_file():
            return candidate
    return None


def ref_key(ws: Workspace, given: str) -> str:
    """A key from a path the user (or a caller) gives: workspace-relative,
    or vault-relative the way wikilinks and MOCs write it."""
    ref = given.strip().replace("\\", "/").strip("/")
    while ref.startswith("./"):
        ref = ref[2:]
    if ref.lower().endswith(".md"):
        ref = ref[:-3]
    vault_prefix = ws.rel(ws.vault)
    if ws.link_root == ws.vault:
        if vault_prefix and (ref == vault_prefix or ref.startswith(vault_prefix + "/")):
            ref = ref[len(vault_prefix):].strip("/")
    elif vault_prefix and ref != vault_prefix and not ref.startswith(vault_prefix + "/"):
        first = ref.split("/", 1)[0]
        in_root = (ws.root / first).exists() or (ws.root / (first + ".md")).exists()
        in_vault = (ws.vault / first).exists() or (ws.vault / (first + ".md")).exists()
        if in_vault and not in_root:
            ref = vault_prefix + "/" + ref      # vault-relative, as a wikilink writes it
    if not ref:
        raise ToolError("empty path: %r" % given, EXIT_USAGE)
    return ref


def _joins_previous(char: str) -> bool:
    """Characters that belong to the one before them (accents, emoji
    modifiers, variation selectors, zero-width joiners)."""
    code = ord(char)
    return (unicodedata.combining(char) != 0 or char in "\u200d\ufe0e\ufe0f"
            or 0x1F3FB <= code <= 0x1F3FF or 0xE0020 <= code <= 0xE007F)


def clean_summary(text: str) -> str:
    flat = " ".join((text or "").split())
    if len(flat) > SUMMARY_MAX:
        cut = SUMMARY_MAX - 1
        # Never split a character from its accent, or an emoji sequence.
        while cut > 0 and (_joins_previous(flat[cut]) or flat[cut - 1] == "\u200d"):
            cut -= 1
        flat = flat[:cut].rstrip() + "…"
    return flat


def _clean_label(text: str) -> str:
    flat = " ".join(text.split())
    for char in "[]|":
        flat = flat.replace(char, " ")
    return " ".join(flat.split()) or "note"


def format_link(ws: Workspace, index: Path, note: Path, label: str, obsidian: bool) -> str:
    label = _clean_label(label)
    if obsidian:
        return "[[%s|%s]]" % (note_key(ws, note), label)
    rel = os.path.relpath(str(note), str(index.parent)).replace(os.sep, "/")
    return "[%s](%s)" % (label, _encode_href(rel))


def format_line(date: str, kind: str, link: str, summary: str) -> str:
    line = "- %s · %s · %s" % (date, kind, link)
    summary = clean_summary(summary)
    return line + (" — " + summary if summary else "")


# ------------------------------------------------------------ facts about a note

class Note:
    """What the timeline needs to know about a note."""

    def __init__(self, ws: Workspace, path: Path):
        self.ws = ws
        self.path = path
        self.lines: List[str] = []
        self.fm = frontmatter.Frontmatter()
        if path.suffix.lower() in (".md", ".markdown"):
            try:
                self.lines = split_lines(read_text(path))
            except (NotText, OSError):
                self.lines = []
            self.fm = frontmatter.parse(self.lines)

    def scalar(self, key: str) -> str:
        return frontmatter.get_scalar(self.lines, self.fm, key) if self.fm.usable else ""

    def values(self, key: str) -> List[str]:
        return frontmatter.get_list(self.lines, self.fm, key) if self.fm.usable else []

    def date(self) -> Optional[str]:
        found = note_date(self.path, self.lines)
        return found.isoformat() if found else None

    def kind(self, reg: Registry) -> str:
        declared = self.scalar("type").strip().lower()
        if declared in ("1on1", "1-1", "one-on-one"):
            return "1on1"
        if declared == "meeting":
            return "meeting"
        stem = self.path.name[: -len(self.path.suffix)] if self.path.suffix else self.path.name
        if reg.person_of_path(self.path) is not None and _ONE_ON_ONE.match(stem):
            return "1on1"
        if self.path.parent in self.ws.meeting_homes():
            return "meeting"
        return "doc"

    def label(self, kind: str) -> str:
        if kind == "1on1":
            return "1-1"
        title = self.scalar("title")
        if title:
            return title
        mask = block_mask(self.lines)
        start = self.fm.close + 1 if self.fm.present and not self.fm.error else 0
        for idx in range(start, len(self.lines)):
            if mask[idx]:
                continue
            found = heading_of(self.lines[idx])
            if found and found[0] == 1:
                return found[1]
            if line_body(self.lines[idx]).strip():
                break
        topic = self.scalar("topic")
        if topic:
            return topic.replace("-", " ")
        stem = self.path.name[: -len(self.path.suffix)] if self.path.suffix else self.path.name
        return _DATE_PREFIX.sub("", stem).replace("-", " ").replace("_", " ").strip() or stem

    def attendee_links(self) -> List[str]:
        """Links and names in the note's `## Attendees` section (H2 or H3)."""
        mask = block_mask(self.lines)
        out = []
        inside = False
        for idx, line in enumerate(self.lines):
            if mask[idx]:
                continue
            found = heading_of(line)
            if found:
                inside = found[0] in (2, 3) and found[1].strip().lower() == "attendees"
                continue
            if not inside:
                continue
            body = line_body(line).strip()
            if not re.match(r"^[-*+]\s", body):
                continue
            item = body[2:].strip()
            wiki = WIKILINK_RE.search(item)
            if wiki:
                out.append(wiki.group(0))
                continue
            md = re.search(r"\[[^\]\n]*\]\([^)\n]*\)", item)
            if md:
                out.append(md.group(0))
        return out


def _filename_people(reg: Registry, path: Path) -> List[str]:
    stem = path.name[: -len(path.suffix)] if path.suffix else path.name
    tokens = words_of(stem)
    found = []
    for person in reg.people.values():
        slug_words = words_of(person.slug)
        size = len(slug_words)
        if size and any(tokens[i:i + size] == slug_words for i in range(len(tokens) - size + 1)):
            found.append(person.slug)
    return found


def who(ws: Workspace, reg: Registry, note: Note, include_large: bool = False) -> dict:
    """The people a note belongs to, with the evidence for each."""
    if note.scalar("no-backref").strip().lower() in ("true", "yes", "on", "1"):
        return {"note": ws.rel(note.path), "people": [], "ambiguous": [], "unresolved": [], "attendees": 0,
                "large_meeting": False, "large_skipped": False, "opted_out": True}
    evidence: Dict[str, List[str]] = {}
    ambiguous: List[dict] = []
    unresolved: List[str] = []

    def add(slug: str, why: str) -> None:
        evidence.setdefault(slug, [])
        if why not in evidence[slug]:
            evidence[slug].append(why)

    owner = reg.person_of_path(note.path)
    if owner is not None:
        add(owner.slug, "T1: in the person's folder")

    def consider(values: List[str], source: str, attendees: List[str]) -> None:
        for value in values:
            result = reg.resolve(value)
            if result["status"] == "high":
                attendees.append(result["slug"])
                add(result["slug"], "T2: %s %r" % (source, value))
            elif result["status"] == "ambiguous":
                ambiguous.append({"text": value, "candidates": result["candidates"], "reason": result["reason"],
                                  "source": source})
            else:
                unresolved.append(value)

    person_field: List[str] = []
    consider(note.values("person"), "frontmatter person", person_field)
    attendees: List[str] = []
    consider(note.values("attendees"), "frontmatter attendees", attendees)
    consider(note.attendee_links(), "## Attendees link", attendees)
    for slug in _filename_people(reg, note.path):
        add(slug, "T2: filename contains %r" % slug)

    distinct = sorted(set(attendees))
    large = len(distinct) > LARGE_MEETING
    if large and not include_large:
        keep = {s for s, why in evidence.items() if any(not w.startswith("T2: frontmatter attendees")
                                                         and not w.startswith("T2: ## Attendees") for w in why)}
        evidence = {s: why for s, why in evidence.items() if s in keep}
    people = []
    for slug in sorted(evidence):
        tier = "T1" if any(w.startswith("T1") for w in evidence[slug]) else "T2"
        people.append({"slug": slug, "tier": tier, "evidence": evidence[slug]})
    return {"note": ws.rel(note.path), "people": people, "ambiguous": ambiguous,
            "unresolved": sorted(set(unresolved)), "attendees": len(distinct),
            "large_meeting": large, "large_skipped": large and not include_large, "opted_out": False}


# ------------------------------------------------------------ writing

def _insert(lines: List[str], block: Block, entry_list: List[dict], new_line: str, date: str,
            newline: str) -> List[str]:
    out = list(lines)
    position = None
    for entry in entry_list:
        if entry["date"] < date:
            position = entry["line"]
            break
    if position is None:
        position = (entry_list[-1]["line"] + 1) if entry_list else block.open + 1
    end = line_end(out[position - 1]) or newline
    out.insert(position, new_line + end)
    return out


def place(ws: Workspace, index: Path, lines: List[str], new_line: str, date: str, newline: str) -> List[str]:
    """`lines` with `new_line` in the timeline block: before the first line
    with an older date, or in a new block (under an existing `## Timeline`
    heading, else a new section at the end). The caller has checked that the
    block is readable and that the note is not on it yet."""
    block = locate(lines)
    if block.open is not None:
        return _insert(lines, block, entries(ws, index, lines, block), new_line, date, newline)
    section = [OPEN_MARK + newline, new_line + newline, CLOSE_MARK + newline]
    out = list(lines)
    if block.heading is not None:
        at = block.heading + 1
        if not line_end(out[block.heading]):
            out[block.heading] += newline
        out[at:at] = section
    else:
        if out and not line_end(out[-1]):
            out[-1] += newline
        if out and line_body(out[-1]).strip():
            out.append(newline)
        out += [HEADING + newline] + section
    return out


def prepare_index(person: Person) -> Tuple[Optional[str], Optional[str], bool]:
    """(problem, text, created) for writing to a person's index.md. `text`
    is the stub when the file does not exist yet; `problem` says why the
    file must be left alone."""
    if person.index.is_symlink():
        return "index.md is a symbolic link; its timeline lives elsewhere", None, False
    created = not person.index.exists()
    if created:
        text = stub_text(person.name)
    else:
        try:
            text = read_text(person.index)
        except NotText:
            return "index.md is not valid UTF-8", None, False
        except OSError as exc:
            return str(exc), None, False
    if has_bare_cr(text):
        return "index.md uses bare carriage returns as line endings", None, created
    lines = split_lines(text)
    if unclosed_fence(lines):
        return "index.md has a code fence that is never closed", None, created
    if not created and not os.access(str(person.index), os.W_OK):
        return "index.md is read-only", None, created
    block = locate(lines)
    if block.problem:
        return block.problem, None, created
    return None, text, created


def add_to(
    ws: Workspace,
    reg: Registry,
    person: Person,
    note: Note,
    date: str,
    kind: str,
    label: str,
    summary: str,
    obsidian: bool,
    dry_run: bool,
) -> dict:
    """Add one line for `note` to `person`'s timeline."""
    result = {"slug": person.slug, "index": ws.rel(person.index), "action": "present", "problem": None, "line": None}
    key = note_key(ws, note.path)
    if obsidian and _UNLINKABLE & set(key):
        result.update(action="skipped", problem="the note's path contains a character a wikilink cannot express")
        return result
    problem, text, created = prepare_index(person)     # a stub is written together with the first line
    if problem:
        result.update(action="skipped", problem=problem)
        return result
    lines = split_lines(text)
    block = locate(lines)
    newline = detect_newline(text)
    link = format_link(ws, person.index, note.path, label, obsidian)
    new_line = format_line(date, kind, link, summary)
    result["line"] = new_line
    if block.open is not None and key in block_keys(ws, person.index, lines, block):
        return result
    out = place(ws, person.index, lines, new_line, date, newline)
    action = "added"
    if not dry_run:
        try:
            write_text_atomic(person.index, "".join(out))
        except OSError as exc:
            result.update(action="skipped", problem="could not write: %s" % exc)
            return result
    result["action"] = "created-index" if created else action
    return result


def add(
    ws: Workspace,
    file_arg: str,
    people: Optional[List[str]] = None,
    summary: str = "",
    summary_for: Optional[Dict[str, str]] = None,
    kind: Optional[str] = None,
    label: Optional[str] = None,
    date: Optional[str] = None,
    include_large: bool = False,
    dry_run: bool = False,
) -> dict:
    """Put a note on the timelines of the people it belongs to."""
    path = ws.resolve(file_arg)
    if not path.is_file():
        raise ToolError("no such file: %s" % file_arg, EXIT_USAGE)
    ws.link_rel(path)
    if path.name in (MOC_NAME,) or (path.name == INDEX):
        raise ToolError("%s is not a note that goes on a timeline" % file_arg, EXIT_USAGE)
    if kind is not None and kind not in KINDS:
        raise ToolError("--kind must be one of %s" % ", ".join(KINDS), EXIT_USAGE)
    reg = registry(ws)
    require_home(reg)
    note = Note(ws, path)
    when = date or note.date()
    if date is not None:
        parse_date(date, "--date")
    if not when:
        raise ToolError("%s has no date (no YYYY-MM-DD filename prefix, no frontmatter `date`); pass --date"
                        % file_arg, EXIT_USAGE)
    summary_for = {reg.get(slug).slug if reg.get(slug) else slug: text for slug, text in (summary_for or {}).items()}
    for slug in list(summary_for) + list(people or []):
        if reg.get(slug) is None:
            raise ToolError("no person folder %r" % slug, EXIT_USAGE)
    people = [reg.get(slug).slug for slug in people] if people else people
    the_kind = kind or note.kind(reg)
    the_label = label or note.label(the_kind)
    if people:
        evidence = {"note": ws.rel(path), "people": [{"slug": s, "tier": "named", "evidence": ["named by the caller"]}
                                                     for s in people],
                    "ambiguous": [], "unresolved": [], "attendees": 0, "large_meeting": False, "large_skipped": False}
    else:
        evidence = who(ws, reg, note, include_large=include_large)
    results = []
    changed = []
    for entry in evidence["people"]:
        person = reg.people[entry["slug"]]
        text = summary_for.get(person.slug, summary)
        outcome = add_to(ws, reg, person, note, when, the_kind, the_label, text, ws.obsidian_present, dry_run)
        outcome["tier"] = entry["tier"]
        results.append(outcome)
        if outcome["action"] in ("added", "created-index"):
            changed.append(outcome["index"])
    return {"note": ws.rel(path), "date": when, "kind": the_kind, "label": the_label, "people": results,
            "ambiguous": evidence["ambiguous"], "unresolved": evidence["unresolved"],
            "attendees": evidence["attendees"], "large_skipped": evidence["large_skipped"],
            "opted_out": evidence.get("opted_out", False), "changed": changed, "dry_run": dry_run}


def person_indexes(ws: Workspace, reg: Optional[Registry] = None) -> List[Person]:
    reg = reg or registry(ws)
    return [p for p in reg.people.values() if p.index.is_file()]


def rename(ws: Workspace, old_ref: str, new_ref: str, prefix: bool = False, dry_run: bool = False) -> dict:
    """Rewrite timeline links after a note (or, with `prefix`, a folder)
    moved. `old_ref` / `new_ref` are paths, workspace- or vault-relative
    (see `ref_key`), with or without `.md`. A hand-written wikilink whose
    note moved out of the vault is left alone (`timeline check` reports it)."""
    old_ref, new_ref = ref_key(ws, old_ref), ref_key(ws, new_ref)
    vault_prefix = ws.rel(ws.vault)
    changed: List[str] = []
    skipped: List[str] = []
    total = 0

    def moved(key: str) -> Optional[str]:
        if key == old_ref:
            return new_ref
        if prefix and key.startswith(old_ref + "/"):
            return new_ref + key[len(old_ref):]
        return None

    for person in person_indexes(ws):
        try:
            text = read_text(person.index)
        except (NotText, OSError):
            skipped.append(ws.rel(person.index))
            continue
        if has_bare_cr(text):
            skipped.append(ws.rel(person.index))
            continue
        lines = split_lines(text)
        block = locate(lines)
        if block.open is None:
            continue
        count = 0
        out = list(lines)
        for idx in range(block.open + 1, block.close):
            line = out[idx]

            def wiki(match: "re.Match[str]") -> str:
                nonlocal count
                raw = match.group("target")
                target = moved(wiki_key(ws, link_target(raw)))
                if target is None:
                    return match.group(0)
                if ws.link_root != ws.vault:
                    # Back to the vault-relative form a wikilink uses.
                    if not (vault_prefix and target.startswith(vault_prefix + "/")):
                        return match.group(0)
                    target = target[len(vault_prefix) + 1:]
                count += 1
                suffix = raw.strip()[-3:] if raw.strip().lower().endswith(".md") else ""
                return "[[%s%s%s%s]]" % (target, suffix, match.group("anchor") or "", match.group("alias") or "")

            def md(match: "re.Match[str]") -> str:
                nonlocal count
                href = match.group(1)
                key = _href_key(ws, person.index, href)
                target = moved(key) if key else None
                if target is None:
                    return match.group(0)
                bare = href[1:-1] if href.startswith("<") else href
                ext = ".md" if unquote(bare.split("#", 1)[0]).lower().endswith(".md") else ""
                rel = _encode_href(os.path.relpath(str(ws.link_root / (target + ext)),
                                                   str(person.index.parent)).replace(os.sep, "/"))
                count += 1
                whole = match.group(0)
                return whole.replace("(" + href, "(" + rel, 1)

            line = WIKILINK_RE.sub(wiki, line)
            line = _MD_LINK.sub(md, line)
            out[idx] = line
        if count:
            if not os.access(str(person.index), os.W_OK):
                skipped.append(ws.rel(person.index))
                continue
            if not dry_run:
                try:
                    write_text_atomic(person.index, "".join(out))
                except OSError:
                    skipped.append(ws.rel(person.index))
                    continue
            total += count
            changed.append(ws.rel(person.index))
    return {"rewrites": total, "changed": changed, "skipped": skipped, "dry_run": dry_run}


def listing(ws: Workspace, slug: str) -> dict:
    reg = registry(ws)
    require_home(reg)
    person = reg.get(slug)
    if person is None:
        raise ToolError("no person folder %r" % slug, EXIT_USAGE)
    if not person.index.is_file():
        return {"slug": slug, "entries": [], "problem": None}
    try:
        lines = split_lines(read_text(person.index))
    except NotText:
        return {"slug": slug, "entries": [], "problem": "index.md is not valid UTF-8"}
    except OSError as exc:
        return {"slug": slug, "entries": [], "problem": str(exc)}
    block = locate(lines)
    items = [{k: v for k, v in e.items() if k != "line"} for e in entries(ws, person.index, lines, block)]
    return {"slug": slug, "entries": items, "problem": block.problem}


def check(ws: Workspace) -> dict:
    """Unreadable blocks, links to missing notes, lines out of order or not
    in the grammar. Reports only."""
    problems = []
    for person in person_indexes(ws):
        rel = ws.rel(person.index)
        try:
            lines = split_lines(read_text(person.index))
        except (NotText, OSError) as exc:
            problems.append({"index": rel, "line": None, "problem": str(exc)})
            continue
        block = locate(lines)
        if block.problem:
            problems.append({"index": rel, "line": None, "problem": block.problem})
            continue
        if block.open is None:
            continue
        found = entries(ws, person.index, lines, block)
        managed = {e["line"] for e in found}
        for idx in range(block.open + 1, block.close):
            if idx not in managed and line_body(lines[idx]).strip():
                problems.append({"index": rel, "line": idx + 1, "problem": "line is not in the timeline grammar"})
        cache: dict = {}
        for entry in found:
            key = resolve_bare(ws, entry["key"], cache) if entry["key"] else None
            if key is None or note_file(ws, key) is None:
                problems.append({"index": rel, "line": entry["line"] + 1,
                                 "problem": "links to a note that does not exist: %s" % entry["key"]})
        for first, second in zip(found, found[1:]):
            if first["date"] < second["date"]:
                problems.append({"index": rel, "line": second["line"] + 1, "problem": "out of date order"})
    return {"problems": problems}


def strip(ws: Workspace, slug: Optional[str] = None, dry_run: bool = False) -> dict:
    """Remove timeline blocks (the rollback for this feature). The
    `## Timeline` heading goes too when nothing else is under it."""
    reg = registry(ws)
    require_home(reg)
    if slug is not None and reg.get(slug) is None:
        raise ToolError("no person folder %r" % slug, EXIT_USAGE)
    targets = [reg.get(slug)] if slug else person_indexes(ws, reg)
    changed, skipped, removed = [], [], []
    for person in targets:
        if not person.index.is_file():
            continue
        rel = ws.rel(person.index)
        try:
            lines = split_lines(read_text(person.index))
        except (NotText, OSError):
            skipped.append(rel)
            continue
        block = locate(lines)
        if block.problem:
            skipped.append(rel)
            continue
        if block.open is None:
            continue
        start, stop = block.open, block.close + 1
        heading_above = start > 0 and line_body(lines[start - 1]).strip() == HEADING
        follow = stop
        while follow < len(lines) and not line_body(lines[follow]).strip():
            follow += 1
        section_empty = follow >= len(lines) or heading_of(lines[follow]) is not None
        if heading_above and section_empty:
            start -= 1          # the heading has nothing else under it
            if stop >= len(lines) and start > 0 and not line_body(lines[start - 1]).strip():
                start -= 1      # the blank line added before it
        out = lines[:start] + lines[stop:]
        remove_file = "".join(out) == stub_text(person.name)     # a stub the tool created for the timeline
        if not dry_run:
            try:
                if remove_file:
                    os.remove(str(person.index))
                else:
                    write_text_atomic(person.index, "".join(out))
            except OSError:
                skipped.append(rel)
                continue
        changed.append(rel)
        if remove_file:
            removed.append(rel)
    return {"changed": changed, "removed": removed, "skipped": skipped, "dry_run": dry_run}
