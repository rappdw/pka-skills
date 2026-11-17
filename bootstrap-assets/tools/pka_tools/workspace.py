"""Where things are in a PKA workspace, and how to walk it."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from .errors import EXIT_NOT_READY, EXIT_USAGE, ToolError
from .markdown import cell_texts, fence_mask, find_heading, is_separator_row, section_end
from .pkaignore import Ignore
from .textio import line_body, split_lines

# Folder-name fallbacks, used only when the Repo Map carries no tag for the
# role. The Repo Map tags (`meeting-home`, `people-home`) take precedence.
DEFAULT_PEOPLE_HOME = "personnel"
DEFAULT_MEETING_HOMES = ("leadership", "ArchCouncil")
DEFAULT_DAILY_HOMES = ("lab-notebook",)

CAPTURE_MARKER = "meeting.json"     # an earshot capture directory
CAPTURE_INDEXED = ("narrative.md",)  # the only file indexed from a capture
MOC_NAME = "_MOC.md"

# Folders at the workspace root that never hold knowledge to index.
_NEVER_ROOTS = {"owner-inbox", "team-inbox", "projects", "meeting-notes", "node_modules"}


class RepoMapEntry:
    __slots__ = ("folder", "priority", "status", "tags")

    def __init__(self, folder: str, priority: str, status: str, tags: List[str]):
        self.folder = folder
        self.priority = priority
        self.status = status
        self.tags = tags


def find_root(explicit: Optional[str]) -> Path:
    """The workspace root: --workspace, else $WORKSPACE_ROOT, else the nearest
    ancestor of the current directory that contains `.pka/`."""
    candidate = explicit or os.environ.get("WORKSPACE_ROOT")
    if candidate:
        root = Path(candidate)
        if not root.is_dir():
            raise ToolError("workspace not found: %s" % candidate, EXIT_USAGE)
        return Path(os.path.realpath(str(root)))
    here = Path(os.path.realpath(os.getcwd()))
    for folder in [here] + list(here.parents):
        if (folder / ".pka").is_dir():
            return folder
    raise ToolError(
        "no PKA workspace here (no .pka/ in this directory or above it). "
        "Run from the workspace root or pass --workspace.",
        EXIT_NOT_READY,
    )


class Workspace:
    def __init__(self, root: Path):
        self.root = Path(os.path.realpath(str(root)))
        self.pka = self.root / ".pka"
        self.db_path = self.pka / "knowledge.db"
        self._ignore: Optional[Ignore] = None
        self._repo_map: Optional[List[RepoMapEntry]] = None

    # ---- predicates -------------------------------------------------
    @property
    def vault(self) -> Path:
        """The folder wikilinks are relative to: knowledge/ when it exists."""
        knowledge = self.root / "knowledge"
        return knowledge if knowledge.is_dir() else self.root

    @property
    def obsidian_present(self) -> bool:
        return (self.root / "knowledge" / ".obsidian").is_dir()

    @property
    def hybrid_monorepo_present(self) -> bool:
        return (self.root / ".meta").is_file() and (self.root / ".git").exists()

    @property
    def ignore(self) -> Ignore:
        if self._ignore is None:
            self._ignore = Ignore.load(self.root)
        return self._ignore

    # ---- paths ------------------------------------------------------
    def resolve(self, given: str) -> Path:
        """An absolute path inside the workspace for a user-supplied path.

        Relative paths are taken from the workspace root. The check is on the
        path as written (after collapsing `.` and `..`), so a `knowledge/`
        that is a symbolic link to a vault elsewhere still counts as inside.
        A path that leaves the workspace is a usage error.
        """
        root = str(self.root)

        def inside(candidate: str) -> bool:
            return candidate == root or candidate.startswith(root.rstrip(os.sep) + os.sep)

        if os.path.isabs(given):
            candidate = os.path.normpath(given)
            if not inside(candidate):
                # The same place reached through a symlinked prefix (/var -> /private/var).
                parent, name = os.path.split(candidate)
                candidate = os.path.join(os.path.realpath(parent), name) if name else os.path.realpath(candidate)
        else:
            candidate = os.path.normpath(os.path.join(root, given))
        if not given.strip() or not inside(candidate):
            raise ToolError("path is outside the workspace: %s" % given, EXIT_USAGE)
        return Path(candidate)

    def rel(self, path: Path) -> str:
        """Workspace-relative POSIX path."""
        return Path(path).relative_to(self.root).as_posix()

    def vault_rel(self, path: Path) -> str:
        try:
            return Path(path).relative_to(self.vault).as_posix()
        except ValueError:
            raise ToolError(
                "%s is not inside the vault (%s)" % (self.rel(path), self.rel(self.vault) or "."),
                EXIT_USAGE,
            )

    # ---- Repo Map ---------------------------------------------------
    def repo_map(self) -> List[RepoMapEntry]:
        """Rows of the `## Repo Map` table in CLAUDE.md ([] when unreadable)."""
        if self._repo_map is not None:
            return self._repo_map
        entries: List[RepoMapEntry] = []
        claude = self.root / "CLAUDE.md"
        if claude.is_file():
            try:
                text = claude.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            lines = split_lines(text)
            mask = fence_mask(lines)
            head = find_heading(lines, mask, "Repo Map", 2)
            if head is not None:
                end = section_end(lines, mask, head)
                columns: Dict[str, int] = {}
                for idx in range(head + 1, end):
                    if mask[idx]:
                        continue
                    body = line_body(lines[idx])
                    cells = cell_texts(body)
                    if cells is None:
                        continue
                    if not columns:
                        lowered = [cell.lower() for cell in cells]
                        if "folder" in lowered:
                            columns = {name: pos for pos, name in enumerate(lowered)}
                        continue
                    if is_separator_row(body):
                        continue
                    def cell(name: str) -> str:
                        pos = columns.get(name)
                        if pos is None or pos >= len(cells):
                            return ""
                        return cells[pos]
                    folder = cell("folder").strip("`").strip().strip("/")
                    if not folder:
                        continue
                    tags = [t.strip().strip("`") for t in re.split(r"[,\s]+", cell("tags")) if t.strip()]
                    entries.append(RepoMapEntry(folder, cell("priority"), cell("status"), tags))
        self._repo_map = entries
        return entries

    def tagged_folders(self, tag: str) -> List[Path]:
        out = []
        for entry in self.repo_map():
            if tag in entry.tags:
                folder = self.root / entry.folder
                if folder.is_dir():
                    out.append(folder)
        return out

    def index_roots(self) -> List[Path]:
        """Folders the index covers.

        Repo Map folders with priority Active or Reference when the map is
        readable; otherwise knowledge/, or the top-level content folders.
        Nested entries are folded into their parent.
        """
        roots: List[Path] = []
        for entry in self.repo_map():
            if entry.priority.strip().lower() not in ("active", "reference"):
                continue
            folder = self.root / entry.folder
            if folder.is_dir():
                roots.append(folder)
        if not roots:
            knowledge = self.root / "knowledge"
            if knowledge.is_dir():
                roots = [knowledge]
            else:
                for child in sorted(self.root.iterdir()):
                    if not child.is_dir() or child.name.startswith(".") or child.name in _NEVER_ROOTS:
                        continue
                    if self.ignore.match(child.name, True):
                        continue
                    roots.append(child)
        roots = sorted(set(roots), key=lambda p: p.as_posix())
        folded: List[Path] = []
        for root in roots:
            if any(parent == root or parent in root.parents for parent in folded):
                continue
            folded.append(root)
        return folded

    # ---- conventions ------------------------------------------------
    def people_home(self) -> Optional[Path]:
        tagged = self.tagged_folders("people-home")
        if tagged:
            return tagged[0]
        fallback = self.vault / DEFAULT_PEOPLE_HOME
        return fallback if fallback.is_dir() else None

    def meeting_homes(self) -> List[Path]:
        tagged = self.tagged_folders("meeting-home")
        if tagged:
            return tagged
        return [self.vault / name for name in DEFAULT_MEETING_HOMES if (self.vault / name).is_dir()]

    def daily_homes(self) -> List[Path]:
        tagged = self.tagged_folders("daily-home")
        if tagged:
            return tagged
        return [self.vault / name for name in DEFAULT_DAILY_HOMES if (self.vault / name).is_dir()]

    # ---- walking ----------------------------------------------------
    def walk(self, start: Path, use_ignore: bool = True) -> Iterator[Path]:
        """Every file under `start`, in a stable order.

        Skipped: dot-directories, `.pkaignore` matches, symbolic links, and
        the contents of earshot capture directories other than the narrative.
        """
        start = Path(start)
        if start.is_file():
            yield start
            return
        if not start.is_dir():
            return
        stack = [start]
        while stack:
            folder = stack.pop()
            try:
                children = sorted(os.scandir(str(folder)), key=lambda e: e.name)
            except OSError:
                continue
            names = {entry.name for entry in children}
            is_capture = CAPTURE_MARKER in names
            subdirs = []
            for entry in children:
                path = Path(entry.path)
                if entry.is_symlink():
                    continue
                rel = self.rel(path)
                if entry.is_dir(follow_symlinks=False):
                    if entry.name.startswith(".") or is_capture:
                        continue
                    if use_ignore and self.ignore.match(rel, True):
                        continue
                    subdirs.append(path)
                elif entry.is_file(follow_symlinks=False):
                    if is_capture and entry.name not in CAPTURE_INDEXED:
                        continue
                    if use_ignore and self.ignore.match(rel, False):
                        continue
                    yield path
            stack.extend(reversed(subdirs))

    def moc_files(self) -> List[Path]:
        return [path for path in self.walk(self.vault, use_ignore=True) if path.name == MOC_NAME]


def domain_tag(folder_name: str) -> str:
    """The tag for a top-level folder: lower case, separators to hyphens."""
    tag = re.sub(r"[\s_]+", "-", folder_name.strip().lower())
    tag = re.sub(r"[^\w\-]+", "", tag)
    return tag.strip("-")


def tag_key(text: str) -> str:
    """For comparing a tag with a folder name: letters and digits only."""
    return re.sub(r"[^\w]+", "", text.lower()).replace("_", "")
