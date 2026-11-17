"""The Obsidian mechanical retrofit (`bootstrap obsidian`).

Inputs are filenames, folder structure and existing frontmatter. File bodies
are carried through byte for byte and never interpreted.

What it writes:
  - `_MOC.md` stubs where a folder has none (never edits an existing MOC);
  - `index.md` stubs in person folders that have none;
  - a frontmatter block on notes that have none;
  - missing schema keys, and the folder's domain tag, on notes whose
    frontmatter it can read.
Notes whose frontmatter it cannot read are left untouched and listed.
Running it twice changes nothing the second time.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import frontmatter
from .errors import EXIT_NOT_READY, ToolError
from .gitops import commit as git_commit
from .textio import NotText, detect_newline, read_text, split_lines, write_text_atomic
from .workspace import CAPTURE_MARKER, MOC_NAME, Workspace, domain_tag

_DATE = r"(?P<date>\d{4}-\d{2}-\d{2})"
_ONE_ON_ONE = re.compile(r"^" + _DATE + r"-(?:1on1|1-1|1-on-1)(?:-.+)?$", re.IGNORECASE)
_DATED_TOPIC = re.compile(r"^" + _DATE + r"-(?P<topic>.+)$")
_DAILY = re.compile(r"^" + _DATE + r"$")
STUB_COMMENT = "<!-- MOC stub created by pka-bootstrap (obsidian). User can reorganize freely. -->"


def display_name(folder: str) -> str:
    """`robin-smith` -> `Robin Smith`. A name that already has capitals is kept."""
    words = []
    for token in re.split(r"[-_]+", folder):
        if not token:
            continue
        if any(char.isupper() for char in token):
            words.append(token)
        else:
            words.append(" ".join(part[:1].upper() + part[1:] for part in token.split(" ")))
    return " ".join(words) or folder


def _link(ws: Workspace, path: Path, label: Optional[str] = None) -> str:
    rel = ws.vault_rel(path)
    if rel.lower().endswith(".md"):
        rel = rel[:-3]
    return "[[%s|%s]]" % (rel, label) if label else "[[%s]]" % rel


class Plan:
    """Folder roles for one run, resolved once."""

    def __init__(self, ws: Workspace):
        self.ws = ws
        self.people_home = ws.people_home()
        self.meeting_homes = set(ws.meeting_homes())
        self.daily_homes = set(ws.daily_homes())

    def person_folder(self, path: Path) -> Optional[Path]:
        """The person folder a path sits directly in, if any."""
        if self.people_home is not None and path.parent.parent == self.people_home:
            return path.parent
        return None

    def domain(self, path: Path) -> str:
        parts = self.ws.vault_rel(path).split("/")
        return domain_tag(parts[0]) if len(parts) > 1 else ""

    def schema_for(self, path: Path) -> Tuple[str, List[Tuple[str, str]]]:
        """(kind, [(key, rendered value)]) for a note, from its name and folder."""
        stem = path.name[: -len(path.suffix)] if path.suffix else path.name
        domain = self.domain(path)

        def tags(first: str) -> str:
            items = [first]
            if domain and domain != first:
                items.append(domain)
            return frontmatter.flow_list(items)

        person = self.person_folder(path)
        match = _ONE_ON_ONE.match(stem)
        if person is not None and match:
            target = self.ws.vault_rel(person / "index.md")[:-3]
            return "1on1", [
                ("type", "1on1"),
                ("date", match.group("date")),
                ("person", '"[[%s]]"' % target),
                ("tags", tags("1on1")),
            ]
        match = _DATED_TOPIC.match(stem)
        if match and path.parent in self.meeting_homes:
            return "meeting", [
                ("type", "meeting"),
                ("date", match.group("date")),
                ("topic", frontmatter.scalar(match.group("topic"))),
                ("attendees", "[]"),
                ("tags", tags("meeting")),
            ]
        match = _DAILY.match(stem)
        if match and path.parent in self.daily_homes:
            return "daily", [("date", match.group("date")), ("tags", tags("daily"))]
        if domain:
            return "", [("tags", frontmatter.flow_list([domain]))]
        return "", []


def _moc_stub(ws: Workspace, folder: Path, plan: Plan, files: List[Path], subdirs: List[Path]) -> str:
    title = folder.name if folder != ws.vault else (ws.vault.name or "Knowledge")
    lines = ["# %s" % title, "", STUB_COMMENT, ""]
    notes = [f for f in files if f.suffix.lower() == ".md" and f.name != MOC_NAME]
    if notes:
        lines.append("## Files")
        for note in notes:
            lines.append("- " + _link(ws, note, note.name[:-3]))
        lines.append("")
    listed = [sub for sub in subdirs if plan.people_home is None or sub.parent != plan.people_home]
    if listed:
        lines.append("## Subdomains")
        for sub in listed:
            lines.append("- [[%s/_MOC|%s]]" % (ws.vault_rel(sub), sub.name))
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _person_stub(ws: Workspace, folder: Path, notes: List[Path]) -> str:
    name = display_name(folder.name)
    lines = [
        "---",
        "type: person",
        "name: %s" % frontmatter.scalar(name),
        'role: ""',
        'org: ""',
        "tags: [person]",
        "---",
        "",
        "# %s" % name,
        "",
        "## Notes",
    ]
    for note in notes:
        lines.append("- " + _link(ws, note, note.name[:-3]))
    return "\n".join(lines) + "\n"


def ensure_note(ws: Workspace, plan: Plan, path: Path, dry_run: bool) -> Tuple[str, str]:
    """Bring one note's frontmatter up to the conventions.

    Returns (outcome, detail) with outcome one of:
      created    a frontmatter block was added to a note that had none
      merged     missing keys and/or the domain tag were added
      unchanged  nothing to do
      skipped    the note was left alone; `detail` says why
    """
    kind, pairs = plan.schema_for(path)
    if not pairs:
        return "unchanged", ""
    try:
        text = read_text(path)
    except NotText:
        return "skipped", "not valid UTF-8"
    except OSError as exc:
        return "skipped", str(exc)
    if not os.access(str(path), os.W_OK):
        return "skipped", "read-only"
    lines = split_lines(text)
    newline = detect_newline(text)
    fm = frontmatter.parse(lines)

    if not fm.present:
        new_lines = frontmatter.prepend_block(lines, pairs, newline)
        if not dry_run:
            write_text_atomic(path, "".join(new_lines))
        return "created", kind
    if fm.error:
        return "skipped", fm.error

    missing = [(name, value) for name, value in pairs if name != "tags" and fm.has_ci(name) is None]
    new_lines = frontmatter.add_keys(lines, fm, missing, newline) if missing else lines
    domain = plan.domain(path)
    detail = ""
    if fm.has_ci("tags") is None and fm.has_ci("tag") is None:
        tags_value = dict(pairs).get("tags")
        if tags_value:
            refreshed = frontmatter.parse(new_lines)
            new_lines = frontmatter.add_keys(new_lines, refreshed, [("tags", tags_value)], newline)
    elif domain:
        refreshed = frontmatter.parse(new_lines)
        new_lines, status = frontmatter.merge_tag(new_lines, refreshed, domain, newline)
        if status == "uneditable":
            detail = "tags are not a simple list; domain tag not added"
    if new_lines == lines:
        return ("unchanged", detail)
    if not dry_run:
        write_text_atomic(path, "".join(new_lines))
    return "merged", detail


def bootstrap(ws: Workspace, dry_run: bool = False, do_commit: bool = False) -> dict:
    if not ws.obsidian_present:
        raise ToolError(
            "No Obsidian vault detected at knowledge/.obsidian/. "
            "The Obsidian bootstrap is a no-op outside an Obsidian vault.",
            EXIT_NOT_READY,
        )
    vault = ws.vault
    plan = Plan(ws)
    summary: Dict[str, object] = {
        "moc_created": [], "moc_already_present": [],
        "person_indexes_created": [], "person_indexes_already_present": [],
        "frontmatter_added": [], "frontmatter_merged": [],
        "skipped": [], "warnings": [],
        "files_total": 0, "touched": [], "dry_run": dry_run, "commit": None,
    }
    touched: List[str] = []

    # One walk: every folder with its immediate files and sub-folders.
    folders: Dict[Path, Tuple[List[Path], List[Path]]] = {}

    def ensure(folder: Path) -> None:
        if folder in folders:
            return
        folders[folder] = ([], [])
        if folder != vault:
            ensure(folder.parent)
            folders[folder.parent][1].append(folder)

    ensure(vault)
    for path in ws.walk(vault):
        ensure(path.parent)
        folders[path.parent][0].append(path)
    # Empty folders are not seen by the walk; include top-level ones.
    for child in sorted(vault.iterdir()):
        if child.is_dir() and not child.name.startswith(".") and not child.is_symlink():
            if ws.ignore.match(ws.rel(child), True) or (child / CAPTURE_MARKER).exists():
                continue
            ensure(child)
    for files, subdirs in folders.values():
        files.sort(key=lambda p: p.name)
        subdirs.sort(key=lambda p: p.name)

    notes = [
        path for files, _ in folders.values() for path in files
        if path.suffix.lower() == ".md" and path.name != MOC_NAME
    ]
    notes.sort(key=lambda p: ws.rel(p))
    summary["files_total"] = len(notes)

    # MOC stubs: the vault root, each top-level folder and each folder one
    # level below (person folders excepted: they get an index instead).
    for folder in sorted(folders, key=lambda p: ws.rel(p)):
        depth = 0 if folder == vault else len(ws.vault_rel(folder).split("/"))
        if depth > 2:
            continue
        if plan.people_home is not None and folder.parent == plan.people_home:
            continue
        label = ws.vault_rel(folder) if folder != vault else "(vault root)"
        moc = folder / MOC_NAME
        if moc.exists():
            summary["moc_already_present"].append(label)
            continue
        files, subdirs = folders[folder]
        if not dry_run:
            write_text_atomic(moc, _moc_stub(ws, folder, plan, files, subdirs))
        summary["moc_created"].append(label)
        touched.append(ws.rel(moc))

    # Person index stubs.
    if plan.people_home is not None and plan.people_home in folders:
        for folder in folders[plan.people_home][1]:
            label = ws.vault_rel(folder)
            index = folder / "index.md"
            if index.exists():
                summary["person_indexes_already_present"].append(label)
                continue
            person_notes = [f for f in folders[folder][0] if f.suffix.lower() == ".md" and f.name != "index.md"]
            if not dry_run:
                write_text_atomic(index, _person_stub(ws, folder, person_notes))
            summary["person_indexes_created"].append(label)
            touched.append(ws.rel(index))

    # Frontmatter and domain tags.
    for path in notes:
        if path.name == "index.md" and plan.person_folder(path) is not None:
            continue
        rel = ws.vault_rel(path)
        outcome, detail = ensure_note(ws, plan, path, dry_run)
        if outcome == "created":
            summary["frontmatter_added"].append(rel)
            touched.append(ws.rel(path))
        elif outcome == "merged":
            summary["frontmatter_merged"].append(rel)
            touched.append(ws.rel(path))
        elif outcome == "skipped":
            summary["skipped"].append("%s: %s" % (rel, detail))
        if detail and outcome in ("merged", "unchanged"):
            summary["warnings"].append("%s: %s" % (rel, detail))

    summary["touched"] = touched
    if do_commit and touched and not dry_run:
        subject = "Bootstrap (obsidian): %d MOCs, %d person indexes, %d frontmatter additions" % (
            len(summary["moc_created"]),
            len(summary["person_indexes_created"]),
            len(summary["frontmatter_added"]) + len(summary["frontmatter_merged"]),
        )
        summary["commit"] = git_commit(ws, subject, touched)
    return summary
