"""Health checks: `pka-tools lint`.

Lint reads the workspace and writes one file, the report
`owner-inbox/librarian-lint-<date>.md`. It never edits, moves or deletes a
note. It needs no model and no network, so it can run from cron.

Rules (numbers as in the librarian's `lint-rules.md`):

  1   files left in `team-inbox/unsorted/` for more than 14 days
  2   links to files that are not there (wikilinks and relative markdown links)
  3   paths in a wiki's `## Sources` that are not there
  4   Repo Map folders with nothing indexable in them
  5   notes that belong on a person's timeline and are not on it (one
      informational finding, from the backfill planner's evidence rules)
  8a  byte-identical files
  8b  the same text after dropping frontmatter, case and spacing
  8c  near-duplicates, and one note contained in another
  8d  duplicate entities: person folders, wiki topics, pointer topics

`--quick` runs 1 to 4, 8a and 8b. Rules 6 and 7 need judgement and stay with
the librarian, who appends them to the report.

Every finding has an id made from its rule and its subject, so the same
problem has the same id on every run. `lint suppress <id>` records an id in
`.pka/lint-suppressions.json`; a suppressed finding is left out of the
report and counted.

Not reported: anything under `.pka/` or a dot-folder, `.pkaignore` matches,
the contents of earshot capture directories, an OCR sidecar against its
source (a sidecar stands in for its source's text and is never listed
itself), and pointer rows repeated across different MOCs. A copy of a file
in a wiki's `sources/` folder is reported as information, not as a finding.
"""
from __future__ import annotations

import datetime as _dt
import difflib
import hashlib
import json
import math
import os
import re
import zlib
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from . import frontmatter, pointers
from .errors import EXIT_FAIL, EXIT_USAGE, ToolError
from .indexer import TEXT_EXTENSIONS, _is_sidecar, _sidecar_of
from .markdown import WIKILINK_RE, block_mask, find_heading, link_target, protected_spans, section_end
from .people import registry, words_of
from .textio import NotText, line_body, read_text, read_text_lossy, sha256_file, split_lines, write_text_atomic
from .workspace import MOC_NAME, UNFILED_ROOTS, Workspace

REPORT_DIR = "owner-inbox"
REPORT_RE = re.compile(r"^librarian-lint-(\d{4}-\d{2}-\d{2})\.md$")
# Reports the tools write into owner-inbox/: never lint input.
GENERATED_RE = re.compile(r"^(librarian-lint-|timeline-backfill-plan-).*\.md$")
HEADER_RE = re.compile(r"^<!-- pka-lint (\{.*\}) -->\s*$")
ID_TAG_RE = re.compile(r"\[id: ([0-9a-z]+-[0-9a-z]+)\]")
SUPPRESS_FILE = "lint-suppressions.json"
SUPPRESS_VERSION = 1
HEADER_VERSION = 1

ORPHAN_DAYS = 14
RECENT_DAYS = 7
INDEXABLE = (".md", ".pdf", ".docx", ".txt")
MARKDOWN = (".md", ".markdown")
MIN_NORMALISED_CHARS = 80       # 8b: shorter texts are too slight to call duplicates
MIN_WORDS = 200                 # 8c
SHINGLE = 5
SIMILARITY = 0.8
CONTAINMENT = 0.9
SIG_BINS = 64                   # one-permutation MinHash: 64 bins ...
BAND_ROWS = 4                   # ... in 16 bands of 4
SAMPLE_MASK = 7                 # containment candidates: shingles whose hash ends in three zero bits
POSTING_CAP = 50                # a bucket or sampled shingle shared by more documents is boilerplate
RULE5_EXAMPLES = 20
LIBRARIAN_MARK = "<!-- librarian:rules-6-7 -->"

_MD_LINK_RE = re.compile(
    r"(?<!\\)\[(?:[^\]\[\n]|\[[^\]\n]*\])*\]\(\s*(?:<([^>\n]+)>|([^)\s]+))(?:\s+(?:\"[^\"\n]*\"|'[^'\n]*'))?\s*\)"
)
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")
_SOURCE_BULLET_RE = re.compile(r"^\s*[-*+]\s+`([^`]+)`")
_PERCENT_RE = re.compile(r"%([0-9A-Fa-f]{2})")
_WORD_RE = re.compile(r"\w+", re.UNICODE)

TITLES = {
    "1": "Files left in team-inbox/unsorted/",
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
    "5": "Ask the librarian to \"backfill timelines\". It plans first and writes nothing until you approve.",
    "8a": "Keep one copy and delete or move the others yourself; links to a removed copy will then show as broken.",
    "8b": "Usually one is a re-save of the other. Keep one, or suppress the group if both are meant.",
    "8c": "Often raw notes beside a reconciled version, or a `-2` copy. Keep the fuller one, or suppress the group.",
    "8d": "Merge the two, or record that they are different (suppress the finding).",
}
QUICK_RULES = ("1", "2", "3", "4", "8a", "8b")
FULL_RULES = ("1", "2", "3", "4", "5", "8a", "8b", "8c", "8d")


def fid(rule: str, *parts: str) -> str:
    """A finding's id: the rule, and a hash of what it is about."""
    digest = hashlib.sha256("\0".join(parts).encode("utf-8", "surrogateescape")).hexdigest()
    return "%s-%s" % (rule, digest[:8])


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


def strip_frontmatter(text: str) -> str:
    lines = text.split("\n")
    if not lines or lines[0].lstrip("﻿").rstrip("\r") != "---":
        return text
    for idx in range(1, len(lines)):
        if lines[idx].rstrip("\r") in ("---", "..."):
            return "\n".join(lines[idx + 1:])
    return text


def normalise(text: str) -> str:
    """Body text for comparison: no frontmatter, one case, single spaces."""
    return " ".join(strip_frontmatter(text).casefold().split())


class Scan:
    """One walk of the workspace, and what the rules share."""

    def __init__(self, ws: Workspace, today: _dt.date):
        self.ws = ws
        self.today = today
        self.files: List[Path] = []
        self.unreadable: List[str] = []
        self.notes: List[str] = []
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

    def member(self, path: Path) -> dict:
        rel = self.ws.rel(path)
        try:
            stat = path.stat()
            size, modified = stat.st_size, _dt.date.fromtimestamp(stat.st_mtime).isoformat()
            mtime = stat.st_mtime
        except OSError:
            size, modified, mtime = 0, "", 0.0
        return {"path": rel, "size": size, "modified": modified, "inbound": len(self.inbound.get(rel, ())),
                "inbox": self.in_inbox(rel), "_mtime": mtime}

    def group_members(self, paths: List[Path]) -> Tuple[List[dict], str]:
        members = [self.member(p) for p in sorted(paths, key=lambda p: self.ws.rel(p))]
        keeper = sorted(members, key=lambda m: (-m["inbound"], m["inbox"], m["_mtime"], m["path"]))[0]["path"]
        for item in members:
            item.pop("_mtime")
        return members, keeper


def _in_wiki_sources(path: Path) -> bool:
    return path.parent.name == "sources" and (path.parent.parent / "wiki.md").is_file()


# ------------------------------------------------------------ rule 1

def rule_orphans(scan: Scan) -> List[dict]:
    out = []
    prefix = "team-inbox/unsorted/"
    for path in scan.files:
        rel = scan.ws.rel(path)
        if not rel.startswith(prefix):
            continue
        try:
            age = (scan.today - _dt.date.fromtimestamp(path.stat().st_mtime)).days
        except OSError:
            continue
        if age > ORPHAN_DAYS:
            out.append({"id": fid("1", rel), "rule": "1", "severity": "finding", "path": rel, "age_days": age,
                        "text": "`%s` (there for %d days)" % (rel, age)})
    return out


# ------------------------------------------------------------ rule 2

def _resolve_wikilink(ws: Workspace, target: str) -> Optional[Path]:
    found = pointers.resolve_link(ws, target)
    if found is not None:
        return found
    for base in (ws.vault, ws.root):
        candidate = base / target
        if candidate.is_dir():
            return candidate
        if base != ws.vault:
            for option in (Path(str(candidate) + ".md"), candidate):
                if option.is_file():
                    return option
    return None


def rule_links(scan: Scan) -> List[dict]:
    """Broken links. Also fills `scan.inbound` (who links to each file)."""
    ws = scan.ws
    root = str(ws.root)
    broken: Dict[Tuple[str, str], dict] = {}
    names: Optional[Dict[str, List[str]]] = None

    def note_inbound(target: Path, source_rel: str) -> None:
        if target.is_file():
            try:
                scan.inbound.setdefault(ws.rel(target), set()).add(source_rel)
            except ValueError:
                pass

    def add(source_rel: str, shown: str, line_no: int, topic: Optional[str], kind: str) -> None:
        slot = broken.setdefault((source_rel, shown), {"lines": [], "topic": topic, "kind": kind})
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
        mask = block_mask(lines)
        topics: Dict[int, str] = {}
        if path.name == MOC_NAME:
            table = pointers.locate(lines)
            if not table.problem:
                topics = {row.line: row.topic for row in table.rows if row.ok}
        for idx, line in enumerate(lines):
            if mask[idx] or "[" not in line:
                continue
            body = line_body(line)
            guarded = protected_spans(body)

            def hidden(start: int) -> bool:
                return any(a <= start < b for a, b in guarded)

            for match in WIKILINK_RE.finditer(body):
                start = match.start()
                if (start > 0 and body[start - 1] == "\\") or hidden(start):
                    continue
                target = link_target(match.group("target"))
                if not target:
                    continue
                found = _resolve_wikilink(ws, target)
                if found is not None:
                    note_inbound(found, source_rel)
                else:
                    add(source_rel, "[[%s]]" % target, idx + 1, topics.get(idx), "wikilink")
            for match in _MD_LINK_RE.finditer(body):
                if hidden(match.start()):
                    continue
                dest = (match.group(1) or match.group(2) or "").strip()
                if not dest or dest.startswith(("#", "/", "\\")) or _SCHEME_RE.match(dest):
                    continue
                shown = dest
                dest = _percent_decode(dest.split("#", 1)[0].split("?", 1)[0])
                if not dest:
                    continue
                candidate = os.path.normpath(os.path.join(str(path.parent), dest))
                if candidate != root and not candidate.startswith(root.rstrip(os.sep) + os.sep):
                    continue                    # outside the workspace: not ours to judge
                if os.path.exists(candidate):
                    note_inbound(Path(candidate), source_rel)
                else:
                    add(source_rel, shown, idx + 1, topics.get(idx), "markdown")

    out = []
    for (source_rel, shown), slot in sorted(broken.items()):
        suggestion = None
        if slot["kind"] == "wikilink" and "/" not in shown:
            if names is None:
                names = {}
                for candidate in scan.files:
                    if candidate.suffix.lower() in MARKDOWN and ws.vault in candidate.parents:
                        names.setdefault(candidate.stem.casefold(), []).append(ws.vault_rel(candidate))
            same = names.get(shown[2:-2].casefold(), [])
            if len(same) == 1:
                suggestion = "[[%s]]" % same[0][:-3] if same[0].lower().endswith(".md") else "[[%s]]" % same[0]
        lines = sorted(set(slot["lines"]))
        where = "%s:%s" % (source_rel, ",".join(str(n) for n in lines[:5]) + ("…" if len(lines) > 5 else ""))
        text = "`%s` → `%s` (missing" % (where, shown)
        if slot["topic"]:
            text += "; in the Pointers row for topic '%s'" % slot["topic"]
        text += ")"
        if suggestion:
            text += "; the only note of that name is `%s`" % suggestion
        out.append({"id": fid("2", source_rel, shown), "rule": "2", "severity": "finding", "source": source_rel,
                    "target": shown, "lines": lines, "topic": slot["topic"], "suggestion": suggestion, "text": text})
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
            match = _SOURCE_BULLET_RE.match(line_body(lines[idx]))
            if not match:
                continue
            cited = match.group(1).strip()
            if not cited or cited in seen or any(char in cited for char in "<>{}") or _SCHEME_RE.match(cited):
                continue
            seen.add(cited)
            plain = cited.lstrip("/")
            if any((base / plain).exists() for base in (ws.root, ws.vault, wiki.parent)):
                continue
            out.append({"id": fid("3", wiki_rel, cited), "rule": "3", "severity": "finding", "wiki": wiki_rel,
                        "cited": cited, "text": "`%s` cites `%s` (missing)" % (wiki_rel, cited)})
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
                    "text": "`%s/` — %s" % (entry.folder, state)})
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
    examples = ["`%s` → %s" % pair for pair in pairs[:RULE5_EXAMPLES]]
    text = "%d note%s (%d timeline line%s) across %d %s" % (
        len(notes), "" if len(notes) == 1 else "s", len(pairs), "" if len(pairs) == 1 else "s",
        len({slug for _, slug in pairs}), "person" if len({slug for _, slug in pairs}) == 1 else "people")
    return [{"id": "5-timelines", "rule": "5", "severity": "info", "notes": len(notes), "lines": len(pairs),
             "examples": examples, "more": max(0, len(pairs) - RULE5_EXAMPLES), "text": text}]


# ------------------------------------------------------------ rule 8a, 8b

def _duplicate_finding(scan: Scan, rule: str, paths: List[Path], detail: str) -> dict:
    members, keeper = scan.group_members(paths)
    outside = [p for p in paths if not _in_wiki_sources(p)]
    copy = len(outside) <= 1 and len(outside) < len(paths)
    return {"id": fid(rule, *[m["path"] for m in members]), "rule": rule,
            "severity": "info" if copy else "finding", "members": members, "keeper": keeper,
            "wiki_source_copy": copy, "detail": detail,
            "text": "%d files%s" % (len(members), (", " + detail) if detail else "")}


def rule_identical(scan: Scan) -> Tuple[List[dict], Dict[Path, str]]:
    by_size: Dict[int, List[Path]] = {}
    for path in scan.files:
        if _is_sidecar(path):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size:
            by_size.setdefault(size, []).append(path)
    by_hash: Dict[str, List[Path]] = {}
    for size, paths in by_size.items():
        if len(paths) < 2:
            continue
        for path in paths:
            try:
                by_hash.setdefault(sha256_file(path), []).append(path)
            except OSError:
                continue
    out = []
    group_of: Dict[Path, str] = {}
    for digest, paths in sorted(by_hash.items(), key=lambda kv: scan.ws.rel(sorted(kv[1], key=str)[0])):
        if len(paths) < 2:
            continue
        finding = _duplicate_finding(scan, "8a", paths, "byte for byte the same")
        for path in paths:
            group_of[path] = finding["id"]
        out.append(finding)
    return out, group_of


class Doc:
    __slots__ = ("path", "rel", "norm_hash", "words")

    def __init__(self, path: Path, rel: str, norm_hash: str, words: int):
        self.path = path
        self.rel = rel
        self.norm_hash = norm_hash
        self.words = words


def text_documents(scan: Scan) -> List[Doc]:
    """Every file with comparable text (its own or its sidecar's)."""
    docs = []
    for path in scan.files:
        if _is_sidecar(path) or path.name == MOC_NAME:
            continue
        text = scan.body_text(path)
        if text is None:
            continue
        norm = normalise(text)
        if len(norm) < MIN_NORMALISED_CHARS:
            continue
        docs.append(Doc(path, scan.ws.rel(path), hashlib.sha256(norm.encode("utf-8", "replace")).hexdigest(),
                        len(_WORD_RE.findall(norm))))
    return docs


def rule_same_text(scan: Scan, docs: List[Doc], identical: Dict[Path, str]) -> List[dict]:
    groups: Dict[str, List[Doc]] = {}
    for doc in docs:
        groups.setdefault(doc.norm_hash, []).append(doc)
    out = []
    for _digest, members in sorted(groups.items(), key=lambda kv: kv[1][0].rel):
        if len(members) < 2:
            continue
        ids = {identical.get(doc.path) for doc in members}
        if len(ids) == 1 and None not in ids:
            continue                            # all byte-identical: reported under 8a
        out.append(_duplicate_finding(scan, "8b", [doc.path for doc in members],
                                      "the same text once frontmatter, case and spacing are set aside"))
    return out


# ------------------------------------------------------------ rule 8c

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


def rule_near(scan: Scan, docs: List[Doc], identical: Dict[Path, str]) -> List[dict]:
    longer = [doc for doc in docs if doc.words >= MIN_WORDS]
    sets: Dict[int, Set[int]] = {}

    def hashes_of(index: int) -> Set[int]:
        if index not in sets:
            if len(sets) >= 512:
                sets.pop(next(iter(sets)))
            sets[index] = shingle_hashes(normalise(scan.body_text(longer[index].path) or ""))
        return sets[index]

    bands: Dict[Tuple[int, Tuple[int, ...]], List[int]] = {}
    postings: Dict[int, List[int]] = {}
    sample_count: List[int] = []
    for index, doc in enumerate(longer):
        hashes = shingle_hashes(normalise(scan.body_text(doc.path) or ""))
        sig = signature(hashes)
        for band in range(SIG_BINS // BAND_ROWS):
            rows = tuple(sig[band * BAND_ROWS:(band + 1) * BAND_ROWS])
            if any(value != -1 for value in rows):
                bands.setdefault((band, rows), []).append(index)
        sampled = [value for value in hashes if not value & SAMPLE_MASK]
        sample_count.append(len(sampled))
        for value in sampled:
            postings.setdefault(value, []).append(index)

    candidates: Set[Tuple[int, int]] = set()
    boilerplate = 0
    for members in bands.values():
        if len(members) < 2:
            continue
        if len(members) > POSTING_CAP:
            boilerplate += 1
            continue
        for i, first in enumerate(members):
            for second in members[i + 1:]:
                candidates.add((first, second))
    shared: Dict[Tuple[int, int], int] = {}
    for members in postings.values():
        if len(members) < 2:
            continue
        if len(members) > POSTING_CAP:
            boilerplate += 1
            continue
        for i, first in enumerate(members):
            for second in members[i + 1:]:
                shared[(first, second)] = shared.get((first, second), 0) + 1
    for pair, count in shared.items():
        if count >= max(2, int(math.ceil(0.5 * min(sample_count[pair[0]], sample_count[pair[1]])))):
            candidates.add(pair)
    if boilerplate:
        scan.notes.append("Rule 8c: %d passage(s) shared by more than %d notes were treated as boilerplate "
                          "and not used to pair notes." % (boilerplate, POSTING_CAP))

    parent = list(range(len(longer)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    evidence: Dict[Tuple[int, int], Tuple[float, float]] = {}
    for first, second in sorted(candidates):
        a, b = longer[first], longer[second]
        if a.norm_hash == b.norm_hash:
            continue                            # 8a or 8b has it
        group = identical.get(a.path)
        if group is not None and group == identical.get(b.path):
            continue
        similarity, containment = compare(hashes_of(first), hashes_of(second))
        if similarity >= SIMILARITY or containment >= CONTAINMENT:
            evidence[(first, second)] = (similarity, containment)
            parent[find(second)] = find(first)

    groups: Dict[int, List[int]] = {}
    for first, second in evidence:
        root = find(first)
        for index in (first, second):
            if index not in groups.setdefault(root, []):
                groups[root].append(index)
    out = []
    for root, members in sorted(groups.items(), key=lambda kv: min(longer[i].rel for i in kv[1])):
        pairs = [(pair, value) for pair, value in evidence.items() if find(pair[0]) == root]
        best_similarity = max(value[0] for _, value in pairs)
        best_containment = max(value[1] for _, value in pairs)
        if best_similarity >= SIMILARITY:
            detail = "up to %d%% alike" % int(best_similarity * 100)
        else:
            detail = "one holds %d%% of another" % int(best_containment * 100)
        finding = _duplicate_finding(scan, "8c", [longer[i].path for i in members], detail)
        finding["similarity"] = round(best_similarity, 3)
        finding["containment"] = round(best_containment, 3)
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
                        "text": "person folders `%s/` and `%s/`: %s" % (a, b, why)})

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
                        "text": "wikis sharing the topic '%s': %s" % (topic, ", ".join("`%s`" % p for p in sorted(pages)))})

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
                            "text": "`%s` has %d Pointers rows for the topic '%s' (lines %s)" % (
                                moc_rel, len(row_lines), shown[slug], ", ".join(str(n) for n in row_lines))})
    return out


# ------------------------------------------------------------ suppressions

def _suppress_path(ws: Workspace) -> Path:
    return ws.pka / SUPPRESS_FILE


def load_suppressions(ws: Workspace) -> dict:
    """The whole file as data, with `suppressed` guaranteed to be a mapping.
    Keys and entries this version does not know are kept as they are."""
    path = _suppress_path(ws)
    if not path.is_file():
        return {"version": SUPPRESS_VERSION, "suppressed": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ToolError("%s could not be read as JSON (%s). Nothing was changed; fix or remove the file and "
                        "run again." % (ws.rel(path), exc), EXIT_FAIL)
    if not isinstance(data, dict) or not isinstance(data.get("suppressed", {}), dict):
        raise ToolError("%s is not a lint suppressions file (expected an object with a \"suppressed\" object). "
                        "Nothing was changed; fix or remove the file and run again." % ws.rel(path), EXIT_FAIL)
    data.setdefault("suppressed", {})
    return data


def _save_suppressions(ws: Workspace, data: dict) -> None:
    data.setdefault("version", SUPPRESS_VERSION)
    ws.pka.mkdir(parents=True, exist_ok=True)
    write_text_atomic(_suppress_path(ws), json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n")


def _reports(ws: Workspace) -> List[Tuple[str, Path]]:
    folder = ws.root / REPORT_DIR
    out = []
    if folder.is_dir():
        for entry in os.scandir(str(folder)):
            match = REPORT_RE.match(entry.name)
            if match and entry.is_file(follow_symlinks=False):
                out.append((match.group(1), Path(entry.path)))
    return sorted(out)


def _last_ids(ws: Workspace) -> Optional[Dict[str, str]]:
    """id -> the line that shows it, from the newest report; None when there is no report."""
    reports = _reports(ws)
    if not reports:
        return None
    try:
        text = reports[-1][1].read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    out: Dict[str, str] = {}
    for line in text.splitlines():
        for match in ID_TAG_RE.finditer(line):
            subject = ID_TAG_RE.sub("", line).strip().lstrip("-#* ").strip()
            out.setdefault(match.group(1), subject[:240])
    return out


def suppress(ws: Workspace, ident: str, reason: str = "") -> dict:
    data = load_suppressions(ws)
    entries = data["suppressed"]
    if ident in entries:
        return {"id": ident, "suppressed": True, "already": True, "entry": entries[ident]}
    known = _last_ids(ws)
    if known is None:
        raise ToolError("there is no lint report to take the id from; run `pka-tools lint` first", EXIT_USAGE)
    if ident not in known:
        near = difflib.get_close_matches(ident, sorted(known), n=5, cutoff=0.5)
        rule = ident.split("-", 1)[0]
        near += [other for other in sorted(known) if other.split("-", 1)[0] == rule and other not in near][:5]
        hint = ("; near matches: %s" % ", ".join(near[:8])) if near else ""
        raise ToolError("no finding with the id %r in the last lint report%s" % (ident, hint), EXIT_USAGE)
    entry = {"at": _dt.datetime.now().isoformat(timespec="seconds"), "reason": reason or "",
             "rule": ident.split("-", 1)[0], "subject": known[ident]}
    entries[ident] = entry
    _save_suppressions(ws, data)
    return {"id": ident, "suppressed": True, "already": False, "entry": entry}


def unsuppress(ws: Workspace, ident: str) -> dict:
    data = load_suppressions(ws)
    if ident not in data["suppressed"]:
        raise ToolError("%r is not suppressed" % ident, EXIT_USAGE)
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
    return {"file": ws.rel(_suppress_path(ws)), "suppressed": items}


# ------------------------------------------------------------ run and report

def run(ws: Workspace, quick: bool = False, write_report: bool = True) -> dict:
    suppressed_ids = set(load_suppressions(ws)["suppressed"])
    today = _dt.date.today()
    scan = Scan(ws, today)
    rules = QUICK_RULES if quick else FULL_RULES
    found: List[dict] = []
    links = rule_links(scan)            # first: the duplicate rules use its inbound counts
    found += rule_orphans(scan)
    found += links
    found += rule_wiki_sources(scan)
    found += rule_repo_map(scan)
    if "5" in rules:
        found += rule_timelines(scan)
    identical, group_of = rule_identical(scan)
    found += identical
    docs = text_documents(scan)
    found += rule_same_text(scan, docs, group_of)
    if "8c" in rules:
        found += rule_near(scan, docs, group_of)
    if "8d" in rules:
        found += rule_entities(scan)

    order = {rule: pos for pos, rule in enumerate(FULL_RULES)}
    found.sort(key=lambda f: (order[f["rule"]], f["text"], f["id"]))
    shown = [f for f in found if f["id"] not in suppressed_ids]
    hidden = [f for f in found if f["id"] in suppressed_ids]
    counts = {rule: sum(1 for f in shown if f["rule"] == rule and f["severity"] == "finding") for rule in rules}
    result = {
        "date": today.isoformat(), "mode": "quick" if quick else "full", "rules": list(rules),
        "scanned": len(scan.files), "markdown": sum(1 for p in scan.files if p.suffix.lower() in MARKDOWN),
        "findings": sum(1 for f in shown if f["severity"] == "finding"),
        "info": sum(1 for f in shown if f["severity"] == "info"),
        "suppressed": len(hidden), "suppressed_ids": sorted(f["id"] for f in hidden),
        "stale_suppressions": sorted(suppressed_ids - {f["id"] for f in found}) if not quick else [],
        "counts": counts, "items": shown, "notes": scan.notes,
        "unreadable": sorted(set(scan.unreadable)), "unreadable_names": ws.unreadable_names, "report": None,
    }
    if write_report:
        folder = ws.root / REPORT_DIR
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / ("librarian-lint-%s.md" % result["date"])
        result["report"] = ws.rel(target)
        write_text_atomic(target, render(result))
    return result


def _plural(count: int, one: str, many: str) -> str:
    return "%d %s" % (count, one if count == 1 else many)


def render(result: dict) -> str:
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
    out.append("")
    out.append("## Summary")
    out.append("")
    by_rule: Dict[str, List[dict]] = {}
    for item in result["items"]:
        by_rule.setdefault(item["rule"], []).append(item)
    if not result["items"]:
        out.append("Nothing to report.")
    for rule in result["rules"]:
        items = by_rule.get(rule)
        if items:
            real = sum(1 for item in items if item["severity"] == "finding")
            info = len(items) - real
            parts = []
            if real:
                parts.append(_plural(real, "finding", "findings"))
            if info:
                parts.append("%d informational" % info)
            out.append("- Rule %s, %s: %s" % (rule, TITLES[rule].lower(), ", ".join(parts)))
    for rule in result["rules"]:
        items = by_rule.get(rule)
        if not items:
            continue
        out += ["", "## %s. %s (%d)" % (rule, TITLES[rule], len(items)), "", HINTS[rule], ""]
        for item in items:
            tag = "[id: %s]" % item["id"]
            if rule in ("8a", "8b", "8c"):
                label = "Wiki source copy (information)" if item["wiki_source_copy"] else item["text"].capitalize()
                names = ["`%s`" % member["path"] for member in item["members"][:3]]
                if len(item["members"]) > 3:
                    names.append("and %d more" % (len(item["members"]) - 3))
                out.append("### %s: %s %s" % (label, ", ".join(names), tag))
                out.append("")
                out.append("| File | Size | Modified | Links to it | |")
                out.append("|---|---|---|---|---|")
                for member in item["members"]:
                    out.append("| `%s` | %d | %s | %d | %s |" % (
                        member["path"].replace("|", "\\|"), member["size"], member["modified"], member["inbound"],
                        "suggested keeper" if member["path"] == item["keeper"] else ""))
                out.append("")
            elif rule == "5":
                out.append("- %s are not on the timeline of someone they involve %s" % (item["text"], tag))
                out += ["  - %s" % example for example in item["examples"]]
                if item["more"]:
                    out.append("  - … and %d more" % item["more"])
            else:
                out.append("- %s %s" % (item["text"], tag))
    if result["unreadable"]:
        out += ["", "## Not read", "",
                "Not valid UTF-8, so their links and text were not checked:", ""]
        out += ["- `%s`" % rel for rel in result["unreadable"]]
    if result["notes"] or result["stale_suppressions"]:
        out += ["", "## Notes", ""]
        out += ["- %s" % note for note in result["notes"]]
        if result["stale_suppressions"]:
            out.append("- %s no longer match anything and can be removed with `pka-tools lint unsuppress <id>`: %s"
                       % (_plural(len(result["stale_suppressions"]), "suppression", "suppressions"),
                          ", ".join(result["stale_suppressions"])))
    out += ["", "## Hiding a finding you have dealt with", "",
            "`.pka/bin/pka-tools lint suppress <id> --reason \"why\"` hides one finding from later reports "
            "(`lint suppressions` lists them, `lint unsuppress <id>` brings one back). An id belongs to the "
            "exact files or link it names: if a group of duplicates gains or loses a file, it is a new finding.",
            "", "## Librarian checks (rules 6 and 7)", "", LIBRARIAN_MARK]
    if result["mode"] == "quick":
        out.append("Not part of a quick lint.")
    else:
        out.append("Not run by the tool: contradiction candidates (rule 6) and uncited wiki claims (rule 7) need "
                   "the librarian. Ask for \"full lint\" in a session and the librarian adds them below this line.")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------ latest, schedule

def latest(ws: Workspace) -> dict:
    reports = _reports(ws)
    if not reports:
        return {"report": None, "date": None, "age_days": None, "findings": None, "info": None,
                "suppressed": None, "mode": None, "recent": False, "mention": False}
    date_text, path = reports[-1]
    header: dict = {}
    try:
        with open(str(path), "r", encoding="utf-8", errors="replace") as handle:
            match = HEADER_RE.match(handle.readline())
        if match:
            parsed = json.loads(match.group(1))
            if isinstance(parsed, dict):
                header = parsed
    except (OSError, ValueError):
        header = {}
    try:
        age = (_dt.date.today() - _dt.date.fromisoformat(date_text)).days
    except ValueError:
        age = None
    findings = header.get("findings") if isinstance(header.get("findings"), int) else None
    recent = age is not None and 0 <= age <= RECENT_DAYS
    return {"report": ws.rel(path), "date": date_text, "age_days": age, "findings": findings,
            "info": header.get("info") if isinstance(header.get("info"), int) else None,
            "suppressed": header.get("suppressed") if isinstance(header.get("suppressed"), int) else None,
            "mode": header.get("mode"), "recent": recent, "mention": bool(recent and findings)}


def _xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def schedule(ws: Workspace) -> dict:
    root = str(ws.root)
    tool = str(ws.pka / "bin" / "pka-tools")
    label = "org.pka-skills.lint.%s" % (re.sub(r"[^A-Za-z0-9]+", "-", ws.root.name).strip("-").lower() or "workspace")

    def quoted(text: str) -> str:
        return "'" + text.replace("'", "'\\''") + "'"

    cron = "0 9 * * 1 /usr/bin/env python3 %s lint --quick --workspace %s >/dev/null 2>&1" % (quoted(tool), quoted(root))
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
        "  <key>StartCalendarInterval</key>",
        "  <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>9</integer>"
        "<key>Minute</key><integer>0</integer></dict>",
        "</dict>",
        "</plist>",
    ])
    return {"workspace": root, "label": label, "cron": cron, "launchd_plist": plist,
            "launchd_path": "~/Library/LaunchAgents/%s.plist" % label, "installed": False}
