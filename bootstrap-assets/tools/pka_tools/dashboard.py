"""`dashboard data`: the data the dashboard page shows, as one script file.

`dashboard.html` is opened by double-click, from `file://`. A page opened
that way cannot `fetch` a local file, so it cannot read `.pka/knowledge.db`
or a note. It can load a script that sits beside it. This command writes that
script, `dashboard-data.js`:

    /* pka-dashboard-data v1 … */
    window.PKA_DATA = {
    "version":1,
    …
    };

What is in it is what the views list: files (path, title, dates, tags, a
one-line summary, a few headings), the Repo Map folders, people and their
timeline entries, projects, open action items and the recent session log.
Note bodies are not in it.

The file is a snapshot. It is generated (never written through a symbolic
link), holds workspace-relative paths only (a timeline link that leaves the
workspace keeps its text and loses its path), and is the same bytes for the
same workspace at the same moment (`generated_at` is the one value that
changes from run to run; `PKA_DASHBOARD_NOW` pins it).

In index mode the list of files, their tags and their text come from the
index, so the snapshot is as fresh as the last `pka-tools index`. Without an
index the files are walked and read. People, timelines, projects, action
items and the log are read from the files in both modes.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import __version__
from . import actions as actions_mod
from . import db as db_mod
from . import frontmatter, indexer, sessionlog, timeline as timeline_mod
from .errors import EXIT_FAIL, EXIT_USAGE, ToolError
from .markdown import fence_mask, heading_of
from .people import display_name, registry
from .textio import GeneratedRefused, NotText, line_body, read_text, split_lines, write_generated
from .workspace import MOC_NAME, Workspace

DATA_VERSION = 1
DATA_NAME = "dashboard-data.js"
PAGE_NAME = "dashboard.html"
GLOBAL = "PKA_DATA"
MARKER = "/* pka-dashboard-data v"
# The whole first line of a file this command wrote, in any version of the format.
_OURS = re.compile(r"^/\* pka-dashboard-data v\d{1,6} \u2014 written by `pka-tools dashboard data`\. "
                   r"Do not edit: run it again instead\. \*/\r?\n?$")
NOW_ENV = "PKA_DASHBOARD_NOW"     # YYYY-MM-DDTHH:MM:SSZ; lets a test (or a rehearsal) pick the moment

HEAD_CHARS = 6000        # how much of a note is read for its title, headings and summary
SUMMARY_MAX = 160
HEADING_MAX = 60
HEADINGS_PER_FILE = 6
TIMELINE_PER_PERSON = 50
ACTIONS_MAX = 200
ACTIVITY_MAX = 20
PROJECTS_DIR = "projects"

FILE_COLUMNS = ["dir", "name", "title", "date", "modified", "size", "tags", "summary", "headings"]

_MARKDOWN = (".md", ".markdown")
_NAME_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:\D|$)")
_NOW_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_WIKI = re.compile(r"\[\[([^\[\]|]*?)(?:\\?\|([^\[\]]*))?\]\]")
_MD_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_LEAD = re.compile(r"^\s*(?:>\s*)*(?:(?:[-*+]|\d{1,9}[.)])\s+(?:\[[ xX]\]\s+)?)?")
# Emphasis is a run of `*`, `_` or `~~` that opens at the start of a word and
# closes at the end of one. A mark inside a word (`snake_case`, `2*3`) is text,
# and so is one that a file extension follows (`__init__.py`).
_EMPHASIS = re.compile(r"(?<![\w*_~\\])(\*{1,3}|_{1,3}|~~)(?=\S)(.+?)(?<=[^\s\\])\1(?![\w*_~]|\.\w)")
_CODE_SPAN = re.compile(r"(`+)(?!`)(.+?)(?<!`)\1(?!`)")
_TABLE_ROW = re.compile(r"^\s*\|")
_RULE = re.compile(r"^\s*(?:[-*_=]\s*){3,}$")

# What a `project_lifecycle` event says about the project now.
_EVENT_STATUS = {"created": "active", "restored": "active", "archiving": "archiving",
                 "transitioned": "archived", "archived": "archived"}

# Inside a <script>, `</script>` ends the element and U+2028/U+2029 used to
# end a line. The file is loaded with `src`, where neither matters, but a
# page that inlines it must not break either.
_JS_ESCAPES = {ord("<"): "\\u003c", ord(">"): "\\u003e", ord("&"): "\\u0026",
               0x2028: "\\u2028", 0x2029: "\\u2029"}


def now_stamp() -> str:
    forced = os.environ.get(NOW_ENV)
    if forced:
        try:
            if not _NOW_RE.match(forced):
                raise ValueError(forced)
            _dt.datetime.strptime(forced, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            raise ToolError("%s must be a moment like 2026-11-20T09:30:00Z, not %r" % (NOW_ENV, forced), EXIT_USAGE)
        return forced
    return db_mod.now_iso()


def _js(value: object) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return text.translate(_JS_ESCAPES)


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _unmark(text: str) -> str:
    """Take emphasis marks off the words they emphasise, and nothing else."""
    for _ in range(4):                      # `***x***`, `**_x_**`: marks nest a few deep
        stripped = _EMPHASIS.sub(lambda m: m.group(2), text)
        if stripped == text:
            break
        text = stripped
    return text


def _inline(text: str) -> str:
    """Inline markdown as plain words: a link is its label, `**bold**`,
    `_emphasis_` and `~~struck~~` lose their marks, a code span loses its
    backticks and keeps its content as written. Marks that are not markup
    stay: `snake_case_title`, `2*3`, a lone `*`."""
    text = _WIKI.sub(lambda m: (m.group(2) or m.group(1).rsplit("/", 1)[-1]), text)
    text = _MD_LINK.sub(lambda m: m.group(1), text)
    out = []
    last = 0
    for match in _CODE_SPAN.finditer(text):
        out.append(_unmark(text[last:match.start()]))
        out.append(match.group(2).strip())
        last = match.end()
    out.append(_unmark(text[last:]))
    return "".join(out).strip()


def _plain(text: str) -> str:
    """A line of markdown as plain words: `_inline`, less the list marker,
    quote mark or checkbox the line starts with."""
    return _inline(_LEAD.sub("", text, count=1))


def _clean_rel(rel: object) -> Optional[str]:
    """A workspace-relative POSIX path, or None for anything else (an
    absolute path, `./x`, `..`, a hidden folder, a backslash form)."""
    if not isinstance(rel, str) or not rel or rel.startswith("/") or "\\" in rel or "\0" in rel:
        return None
    parts = rel.split("/")
    if any(part in ("", ".", "..") for part in parts) or re.match(r"^[A-Za-z]:", rel):
        return None
    if any(part.startswith(".") for part in parts[:-1]):
        return None
    return rel


def _note_date(name: str, frontmatter_date: str = "") -> str:
    """A note's date, by the rule of `actions.note_date`: the filename's
    `YYYY-MM-DD` prefix, else frontmatter `date`; never the modification time."""
    match = _NAME_DATE.match(name)
    for candidate in ([match.group(1)] if match else []) + ([frontmatter_date[:10]] if frontmatter_date else []):
        try:
            return _dt.date.fromisoformat(candidate).isoformat()
        except ValueError:
            continue
    return ""


class _Text:
    """What the head of a note says about it."""
    __slots__ = ("title", "date", "tags", "summary", "headings")

    def __init__(self) -> None:
        self.title = ""
        self.date = ""
        self.tags: Optional[List[str]] = None     # None: no readable frontmatter
        self.summary = ""
        self.headings: List[str] = []


def describe_text(rel: str, head: str, markdown: bool) -> _Text:
    out = _Text()
    lines = split_lines(head)
    start = 0
    name = rel.rsplit("/", 1)[-1]
    if markdown:
        fm = frontmatter.parse(lines)
        out.date = _note_date(name, frontmatter.get_scalar(lines, fm, "date"))
        if fm.usable:
            start = fm.close + 1
            out.tags = [tag.lstrip("#") for tag in frontmatter.get_list(lines, fm, "tags") if tag.strip("# ")]
            out.title = _clip(frontmatter.get_scalar(lines, fm, "title"), 120)
            out.summary = _clip(frontmatter.get_scalar(lines, fm, "summary")
                                or frontmatter.get_scalar(lines, fm, "description"), SUMMARY_MAX)
        elif fm.present:
            # Frontmatter that cannot be read: skip it when it closes, and the whole head when it does not.
            start = fm.close + 1 if fm.close else len(lines)
    else:
        out.date = _note_date(name)
    body = lines[start:]
    mask = fence_mask(body) if markdown else [False] * len(body)
    words: List[str] = []
    in_comment = False
    for idx, line in enumerate(body):
        if mask[idx]:
            continue
        text = line_body(line).lstrip("﻿")
        stripped = text.strip()
        if in_comment:
            in_comment = "-->" not in stripped
            continue
        if not stripped:
            if words:
                words.append("")     # a paragraph break: the summary stops at the first one
            continue
        if stripped.startswith("<!--"):
            in_comment = "-->" not in stripped
            continue
        found = heading_of(text) if markdown else None
        if found:
            level, title = found[0], _plain(found[1])
            if not title:
                continue
            if level == 1 and not out.title:
                out.title = _clip(title, 120)
            elif level <= 3 and len(out.headings) < HEADINGS_PER_FILE and _clip(title, 120) != out.title:
                out.headings.append(_clip(title, HEADING_MAX))
            if words:
                words.append("")
            continue
        if out.summary or (words and words[-1] == ""):
            continue
        if markdown and (_TABLE_ROW.match(text) or _RULE.match(text)):
            continue
        plain = _plain(text) if markdown else stripped
        if plain:
            words.append(plain)
    if not out.summary:
        out.summary = _clip(" ".join(word for word in words if word), SUMMARY_MAX)
    return out


# ---------------------------------------------------------------- files

def _from_index(ws: Workspace, conn: sqlite3.Connection, report: dict) -> Tuple[List[dict], Optional[str]]:
    db_mod.require_current(conn)
    meta: Dict[str, dict] = {}
    newest = ""
    for row in conn.execute("SELECT path, size_bytes, modified_at, tags, indexed_at FROM file_index"):
        rel = _clean_rel(row["path"])
        if rel is None:
            report["skipped"] += 1
            continue
        if rel.rsplit("/", 1)[-1] == MOC_NAME:
            continue
        if not (ws.root / rel).is_file():
            report["missing"] += 1
            continue
        tags = [tag.strip() for tag in (row["tags"] or "").split(",") if tag.strip()]
        meta[rel] = {"path": rel, "size": int(row["size_bytes"] or 0), "modified": (row["modified_at"] or "")[:10],
                     "tags": tags, "text": None}
        if (row["indexed_at"] or "") > newest:
            newest = row["indexed_at"]
    for row in conn.execute("SELECT path, substr(content, 1, %d) AS head, is_pointer FROM search_fts" % HEAD_CHARS):
        if row["is_pointer"] in (1, "1"):
            continue
        entry = meta.get(row["path"])
        if entry is None or entry["text"] is not None:
            continue
        markdown = row["path"].lower().endswith(_MARKDOWN)
        entry["text"] = describe_text(row["path"], row["head"] or "", markdown)
    return list(meta.values()), newest or None


def _from_walk(ws: Workspace, report: dict) -> List[dict]:
    files, _scopes, _missing, _loose = indexer._collect(ws, [])
    out = []
    for path in files:
        if path.name == MOC_NAME:
            continue
        rel = _clean_rel(ws.rel(path))
        if rel is None:
            report["skipped"] += 1
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        entry = {"path": rel, "size": stat.st_size, "modified": indexer._mtime_iso(stat.st_mtime)[:10],
                 "tags": [], "text": None}
        ext = path.suffix.lower()
        source = path if ext in indexer.TEXT_EXTENSIONS else indexer._sidecar_of(path)   # `report.pdf.txt`
        if source is not None:
            try:
                with open(str(source), "rb") as handle:
                    head = handle.read(HEAD_CHARS * 2).decode("utf-8", errors="replace")[:HEAD_CHARS]
            except OSError:
                head = ""
            entry["text"] = describe_text(rel, head, ext in _MARKDOWN)
        out.append(entry)
    return out


def _file_rows(entries: List[dict]) -> Tuple[List[str], List[str], List[list]]:
    """(dirs, tags, rows): the files as rows of FILE_COLUMNS, with folders and
    tags replaced by positions in two sorted lists."""
    for entry in entries:
        text = entry["text"]
        if text is not None and text.tags is not None and not entry["tags"]:
            # The index stores a file's tags joined by commas, so a tag written
            # with a comma in it is two tags there; it is two tags here as well.
            entry["tags"] = [part.strip() for tag in text.tags for part in tag.split(",") if part.strip()]
    entries.sort(key=lambda item: item["path"])
    dirs = sorted({entry["path"].rsplit("/", 1)[0] if "/" in entry["path"] else "" for entry in entries})
    dir_pos = {name: pos for pos, name in enumerate(dirs)}
    tags = sorted({tag for entry in entries for tag in entry["tags"]})
    tag_pos = {name: pos for pos, name in enumerate(tags)}
    rows = []
    for entry in entries:
        folder, _, name = entry["path"].rpartition("/")
        text = entry["text"]
        rows.append([
            dir_pos[folder], name,
            text.title if text else "",
            text.date if text else _note_date(name),
            entry["modified"], entry["size"],
            sorted({tag_pos[tag] for tag in entry["tags"]}),
            text.summary if text else "",
            text.headings if text else [],
        ])
    return dirs, tags, rows


class _Folders:
    """Counts and the newest date under each folder, for cards and sections."""

    def __init__(self, entries: List[dict]):
        self.count: Dict[str, int] = {}
        self.latest: Dict[str, str] = {}
        for entry in entries:
            parts = entry["path"].split("/")[:-1]
            for depth in range(1, len(parts) + 1):
                folder = "/".join(parts[:depth])
                self.count[folder] = self.count.get(folder, 0) + 1
                if entry["modified"] > self.latest.get(folder, ""):
                    self.latest[folder] = entry["modified"]


# ---------------------------------------------------------------- the other views

def _sections(ws: Workspace, folders: _Folders) -> List[dict]:
    out = []
    for entry in ws.repo_map():
        folder = _clean_rel(entry.folder)
        if folder is None or any(part.startswith(".") for part in folder.split("/")):
            continue            # `.pka/`, `.obsidian/`: never a section of the dashboard
        out.append({"folder": folder, "priority": entry.priority.strip(), "status": entry.status.strip(),
                    "tags": sorted(entry.tags), "files": folders.count.get(folder, 0),
                    "latest": folders.latest.get(folder, "")})
    return out


def _link_path(ws: Workspace, key: str, report: dict) -> str:
    """The workspace-relative path of the note a timeline link names, or "".

    The link is resolved as written (`..` collapsed) before anything is
    looked up. A target that is not inside the workspace is never tested
    for existence and never recorded: the entry keeps its text, has no
    path, and is counted in `skipped_links`. A target inside the workspace
    that does not exist has no path either, and is not counted."""
    try:
        base = os.path.normpath(os.path.join(str(ws.link_root), key))
    except (TypeError, ValueError):
        report["skipped_links"] += 1
        return ""
    root = str(ws.root)
    if "\0" in key or not base.startswith(root.rstrip(os.sep) + os.sep):
        report["skipped_links"] += 1
        return ""
    for candidate in (base + ".md", base):
        try:
            found = os.path.isfile(candidate)
        except (OSError, ValueError):
            found = False
        if found:
            rel = _clean_rel(Path(candidate).relative_to(ws.root).as_posix())
            if rel is None:
                report["skipped_links"] += 1        # a hidden folder such as `.obsidian/`
                return ""
            return rel
    return ""


def _people(ws: Workspace, folders: _Folders, report: dict) -> List[dict]:
    reg = registry(ws)
    if reg.home is None:
        return []
    out = []
    for person in reg.people.values():
        folder = ws.rel(person.folder)
        item = {"slug": person.slug, "name": person.name, "aliases": list(person.aliases), "folder": folder,
                "index": ws.rel(person.index) if person.index.is_file() else "",
                "files": folders.count.get(folder, 0), "latest": folders.latest.get(folder, ""),
                "timeline": [], "timeline_total": 0}
        if person.index.is_file():
            try:
                lines = split_lines(read_text(person.index))
            except (NotText, OSError):
                lines = []
            block = timeline_mod.locate(lines)
            if block.problem:
                report["notes"].append("%s: %s" % (item["index"], block.problem))
            else:
                found = timeline_mod.entries(ws, person.index, lines, block)
                found.sort(key=lambda e: e["date"], reverse=True)       # stable: same-day lines keep their order
                item["timeline_total"] = len(found)
                for entry in found[:TIMELINE_PER_PERSON]:
                    path = _link_path(ws, entry["key"], report) if entry["key"] else ""
                    item["timeline"].append({
                        "date": entry["date"], "kind": entry["kind"], "summary": entry["summary"], "path": path})
        out.append(item)
    out.sort(key=lambda p: p["slug"])
    return out


def _projects(ws: Workspace, conn: Optional[sqlite3.Connection], folders: _Folders) -> List[dict]:
    events: Dict[str, List[dict]] = {}
    if conn is not None:
        try:
            rows = conn.execute(
                "SELECT project_slug, event, event_date, notes FROM project_lifecycle ORDER BY event_date, id"
            ).fetchall()
        except sqlite3.Error:
            rows = []
        for row in rows:
            if not row["project_slug"]:
                continue
            events.setdefault(row["project_slug"], []).append(
                {"event": row["event"] or "", "date": (row["event_date"] or "")[:10],
                 "notes": _clip(row["notes"] or "", SUMMARY_MAX)})
    found: Dict[str, dict] = {}
    home = ws.root / PROJECTS_DIR
    if home.is_dir() and not home.is_symlink():
        try:
            children = sorted(os.scandir(str(home)), key=lambda e: e.name)
        except OSError:
            children = []
        for child in children:
            if child.name.startswith(".") or child.is_symlink() or not child.is_dir(follow_symlinks=False):
                continue
            try:
                child.name.encode("utf-8")
            except UnicodeEncodeError:
                continue
            folder = "%s/%s" % (PROJECTS_DIR, child.name)
            if ws.ignore.match(folder, True):
                continue
            docs = 0
            latest = folders.latest.get(folder, "")
            try:
                inside = list(os.scandir(child.path))
            except OSError:
                inside = []
            for entry in inside:
                if entry.name.startswith(".") or entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                    continue
                docs += 1
                try:
                    stamp = indexer._mtime_iso(entry.stat(follow_symlinks=False).st_mtime)[:10]
                except OSError:
                    continue
                if stamp > latest:
                    latest = stamp
            found[child.name] = {"slug": child.name, "name": display_name(child.name), "folder": folder,
                                 "has_claude_md": os.path.isfile(os.path.join(child.path, "CLAUDE.md")),
                                 "docs": docs, "latest": latest}
    out = []
    for slug in sorted(set(found) | set(events)):
        item = found.get(slug) or {"slug": slug, "name": display_name(slug), "folder": "",
                                   "has_claude_md": False, "docs": 0, "latest": ""}
        history = events.get(slug, [])
        last = history[-1]["event"].strip().lower() if history else ""
        item["status"] = _EVENT_STATUS.get(last, "active" if item["folder"] else "archived")
        item["events"] = history
        out.append(item)
    return out


def _actions(ws: Workspace) -> Tuple[List[dict], int]:
    result = actions_mod.run(ws, None, None)
    items = [{"path": item["path"], "line": item["line"], "date": item["date"] or "",
              "text": _clip(_inline(item["text"]), 240), "owners": item["owners"], "due": item["due"] or "",
              "due_text": item["due_text"] or ""}
             for item in result["items"] if _clean_rel(item["path"])]
    items.sort(key=lambda item: (item["date"], item["path"], -item["line"]), reverse=True)
    return items[:ACTIONS_MAX], len(items)


def _activity(ws: Workspace, report: dict) -> List[dict]:
    try:
        entries = sessionlog.entries(ws)
    except (ToolError, OSError) as exc:
        report["notes"].append("session log not read: %s" % getattr(exc, "message", exc))
        return []
    good = [entry.as_dict() for entry in entries if not entry.problem]
    return [{"at": e["at"], "role": e["role"], "summary": e["summary"], "open": e["open"], "next": e["next"]}
            for e in reversed(good[-ACTIVITY_MAX:])]


def _title(ws: Workspace) -> str:
    claude = ws.root / "CLAUDE.md"
    try:
        with open(str(claude), "rb") as handle:
            head = handle.read(4000).decode("utf-8", errors="replace")
    except OSError:
        return ""
    lines = split_lines(head)
    mask = fence_mask(lines)
    for idx, line in enumerate(lines):
        found = None if mask[idx] else heading_of(line)
        if found and found[0] == 1:
            return _clip(_plain(found[1]), 120)
    return ""


# ---------------------------------------------------------------- the file

def _target(ws: Workspace, out: Optional[str]) -> Path:
    """Where the file goes. `--out` must name a `.js` file inside the
    workspace (`ws.resolve` refuses anything else) that is not hidden and
    not inside a hidden folder: `.pka/` holds the tools and the index, and
    `.obsidian/`, `.git/` and the like belong to other programs."""
    if not out:
        path = ws.root / DATA_NAME
        if path.is_dir() and not path.is_symlink():
            raise ToolError("%s is a folder; the data file cannot be written there. Rename the folder or choose "
                            "another place with --out." % DATA_NAME, EXIT_FAIL)
        return path
    path = ws.resolve(out)
    if path == ws.root or (path.is_dir() and not path.is_symlink()):
        path = path / DATA_NAME
    if path.suffix.lower() != ".js":
        raise ToolError("--out must name a .js file (the page loads it as a script): %s" % out, EXIT_USAGE)
    hidden = [part for part in path.relative_to(ws.root).parts if part.startswith(".")]
    if hidden:
        raise ToolError("--out must not be a hidden file or inside a hidden folder (%s): %s. .pka/ holds the tools "
                        "and the index; write the data beside the page." % (hidden[0], out), EXIT_USAGE)
    return path


def _root_prefix(ws: Workspace, path: Path) -> str:
    depth = len(path.relative_to(ws.root).parts) - 1
    return "../" * depth


def _not_ours(path: Path) -> bool:
    """True when a file is already there and this command did not write it:
    anything whose first line is not, in full, the line `render` writes. An
    empty file is not ours either."""
    if not path.is_file() or path.is_symlink():
        return False
    try:
        with open(str(path), "rb") as handle:
            first = handle.readline(400)
    except OSError:
        return True
    try:
        line = first.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return not _OURS.match(line.lstrip("\ufeff"))


def render(data: dict) -> str:
    """The script file. One key per line; one file, person, project, action
    and log entry per line, so two snapshots compare line by line."""
    def block(items: List[object]) -> str:
        return "[\n" + ",\n".join(_js(item) for item in items) + "\n]" if items else "[]"

    multiline = ("sections", "files", "people", "projects", "actions", "activity")
    lines = []
    for key, value in data.items():
        lines.append("%s:%s" % (_js(key), block(value) if key in multiline else _js(value)))
    return ("%s%d — written by `pka-tools dashboard data`. Do not edit: run it again instead. */\n"
            "window.%s = {\n%s\n};\n" % (MARKER, DATA_VERSION, GLOBAL, ",\n".join(lines)))


def build(ws: Workspace, stamp: str, root_prefix: str = "") -> Tuple[dict, dict]:
    """(data, report). `data` is what the page gets, in the order it is written."""
    report = {"missing": 0, "skipped": 0, "skipped_links": 0, "notes": []}
    indexed_at = None
    if ws.db_path.is_file():
        mode = "index"
        with closing(db_mod.connect(ws)) as conn:
            entries, indexed_at = _from_index(ws, conn, report)
            folders = _Folders(entries)
            projects = _projects(ws, conn, folders)
    else:
        mode = "markdown-only"
        entries = _from_walk(ws, report)
        folders = _Folders(entries)
        projects = _projects(ws, None, folders)
    dirs, tags, rows = _file_rows(entries)
    people = _people(ws, folders, report)
    actions, actions_total = _actions(ws)
    activity = _activity(ws, report)
    notes = sum(1 for row in rows if row[1].lower().endswith(_MARKDOWN))
    data = {
        "version": DATA_VERSION,
        "generated_at": stamp,
        "generated_by": "pka-tools %s" % __version__,
        "mode": mode,
        "indexed_at": indexed_at or "",
        "root": root_prefix,
        "title": _title(ws),
        "counts": {"files": len(rows), "notes": notes, "folders": len(dirs), "people": len(people),
                   "projects": len(projects), "open_actions": actions_total, "activity": len(activity)},
        "sections": _sections(ws, folders),
        "dirs": dirs,
        "tags": tags,
        "file_columns": FILE_COLUMNS,
        "files": rows,
        "people": people,
        "projects": projects,
        "actions": actions,
        "activity": activity,
    }
    return data, report


def run(ws: Workspace, out: Optional[str] = None) -> dict:
    started = time.time()
    if not ws.pka.is_dir():
        raise ToolError("no .pka/ directory in %s; bootstrap the workspace first." % ws.root, EXIT_USAGE)
    stamp = now_stamp()
    path = _target(ws, out)
    rel = ws.rel(path)
    if _not_ours(path):
        raise ToolError("%s exists and was not written by `dashboard data`; not overwriting it. "
                        "Move it away or choose another --out." % rel, EXIT_FAIL)
    data, report = build(ws, stamp, _root_prefix(ws, path))
    text = render(data)
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        text = text.encode("utf-8", errors="replace").decode("utf-8")
    try:
        write_generated(ws.root, path, text)
    except GeneratedRefused as exc:
        raise ToolError("dashboard data not written: %s." % exc, EXIT_FAIL)
    except OSError as exc:
        # The system's message names the temporary file by its absolute path; say where, relative to the workspace.
        raise ToolError("dashboard data not written: %s could not be written (%s)." % (
            rel, exc.strerror or type(exc).__name__), EXIT_FAIL)
    return {
        "path": rel, "bytes": len(text.encode("utf-8")), "version": DATA_VERSION, "mode": data["mode"],
        "generated_at": stamp, "indexed_at": data["indexed_at"], "counts": data["counts"],
        "missing": report["missing"], "skipped": report["skipped"], "skipped_links": report["skipped_links"],
        "notes": report["notes"],
        "page": (path.parent / PAGE_NAME).is_file(), "seconds": round(time.time() - started, 2),
    }
