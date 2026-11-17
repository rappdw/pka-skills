"""Fill and refresh the index from the files on disk.

`file_index` gets one row per file under the index roots (any type), with a
SHA-256 of its bytes. `search_fts` gets the text: markdown and plain-text
files directly, other files through their OCR sidecar (`report.pdf.txt`
beside `report.pdf`). A `_MOC.md` contributes one extra row per pointer-table
row, flagged `is_pointer = 1`.

The tool never extracts text from PDFs or Office files itself. Text that a
role put into `search_fts` for such a file is kept until the file changes or
goes away.
"""
from __future__ import annotations

import datetime as _dt
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from . import frontmatter
from .db import now_iso, require_current
from .errors import EXIT_FAIL, EXIT_USAGE, ToolError
from .pointers import locate
from .textio import line_body, read_text_lossy, sha256_file, split_lines
from .workspace import CAPTURE_INDEXED, CAPTURE_MARKER, MOC_NAME, Workspace

TEXT_EXTENSIONS = {".md", ".markdown", ".txt"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".doc", ".pptx", ".xlsx", ".rtf"}
_OWN_STATUS = {None, "", "indexed", "metadata"}


def _mtime_iso(stamp: float) -> str:
    return _dt.datetime.fromtimestamp(stamp, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _sidecar_of(path: Path) -> Optional[Path]:
    """The OCR sidecar of a non-text file, if there is one."""
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return None
    sidecar = Path(str(path) + ".txt")
    return sidecar if sidecar.is_file() else None


def _is_sidecar(path: Path) -> bool:
    if path.suffix.lower() != ".txt":
        return False
    source = Path(str(path)[:-4])
    return bool(source.suffix) and source.suffix.lower() not in TEXT_EXTENSIONS and source.is_file()


def _in_scope(rel: str, scopes: List[Tuple[str, bool]]) -> bool:
    if not isinstance(rel, str):
        return False
    for prefix, is_dir in scopes:
        if is_dir:
            if prefix == "" or rel == prefix or rel.startswith(prefix + "/"):
                return True
        elif rel == prefix:
            return True
    return False


def _collect(
    ws: Workspace, targets: List[str]
) -> Tuple[List[Path], List[Tuple[str, bool]], List[str], List[str]]:
    """Files to look at, the scopes they came from, targets not found, and
    "loose" folders: only the narrative of a capture is taken from them, so a
    row there is dropped when its file is gone, not merely when it was not
    walked."""
    files: List[Path] = []
    scopes: List[Tuple[str, bool]] = []
    missing: List[str] = []
    loose: List[str] = []
    seen: Set[Path] = set()

    def take(path: Path) -> None:
        if path not in seen and not _is_sidecar(path):
            seen.add(path)
            files.append(path)

    if targets:
        for given in targets:
            path = ws.resolve(given)
            rel = ws.rel(path) if path != ws.root else ""
            first = rel.split("/", 1)[0]
            if first in (".pka", ".git"):
                raise ToolError("%s is not indexable" % given, EXIT_USAGE)
            if path.is_dir():
                scopes.append((rel, True))
                for found in ws.walk(path):
                    take(found)
            elif path.is_file():
                scopes.append((rel, False))
                source = Path(str(path)[:-4]) if _is_sidecar(path) else path
                if source != path:
                    scopes.append((ws.rel(source), False))
                take(source)
            else:
                scopes.append((rel, False))
                missing.append(rel)
        return files, scopes, missing, loose

    for root in ws.index_roots():
        scopes.append((ws.rel(root), True))
        for found in ws.walk(root):
            take(found)
    captures = ws.root / "meeting-notes"
    if captures.is_dir():
        loose.append(ws.rel(captures))
        for found in ws.walk(captures):
            if found.name in CAPTURE_INDEXED and (found.parent / CAPTURE_MARKER).is_file():
                take(found)
    return files, scopes, missing, loose


def _moc_parts(text: str) -> Tuple[str, List[str]]:
    """A MOC's body without its pointer rows, and one string per pointer row."""
    lines = split_lines(text)
    table = locate(lines)
    row_lines = {row.line for row in table.rows}
    body = "".join(line for idx, line in enumerate(lines) if idx not in row_lines)
    rows = []
    for row in table.rows:
        if row.ok:
            rows.append(" ".join(part for part in (row.topic, row.entities_raw, row.files_raw) if part))
    return body, rows


def _frontmatter_fields(text: str) -> Tuple[Optional[str], Optional[str]]:
    """(tags, topic) from a markdown file's frontmatter, None when unknown."""
    head = text[:20000]
    lines = split_lines(head)
    fm = frontmatter.parse(lines)
    if not fm.usable:
        return None, None
    tags = [tag.lstrip("#") for tag in frontmatter.get_list(lines, fm, "tags")]
    topic = frontmatter.get_scalar(lines, fm, "topic")
    return (", ".join(tags) if tags else None), (topic or None)


def run(
    ws: Workspace,
    conn: sqlite3.Connection,
    targets: Optional[List[str]] = None,
    rebuild: bool = False,
    prune: bool = False,
    dry_run: bool = False,
) -> dict:
    started = time.time()
    require_current(conn)
    files, scopes, missing, loose = _collect(ws, targets or [])

    known: Dict[str, sqlite3.Row] = {}
    for row in conn.execute(
        "SELECT rowid AS rid, path, size_bytes, modified_at, content_hash, status, inferred_topic, tags "
        "FROM file_index"
    ):
        if row["path"] is not None:
            known[row["path"]] = row
    fts_body: Dict[str, List[int]] = {}
    fts_pointer: Dict[str, List[int]] = {}
    for row in conn.execute("SELECT rowid AS rid, path, is_pointer FROM search_fts"):
        bucket = fts_pointer if row["is_pointer"] in (1, "1") else fts_body
        bucket.setdefault(row["path"], []).append(row["rid"])

    report = {
        "scope": [prefix or "." for prefix, _ in scopes] + loose,
        "added": 0, "updated": 0, "unchanged": 0, "removed": 0,
        "pointer_rows": 0,
        "needs_text": [], "stale_text": [], "not_found": missing,
        "stale_elsewhere": 0, "pruned": 0,
        "dry_run": dry_run,
    }
    seen: Set[str] = set()
    stamp = now_iso()

    def delete_fts(rowids: List[int]) -> None:
        for rid in rowids:
            conn.execute("DELETE FROM search_fts WHERE rowid = ?", (rid,))

    try:
        if not dry_run:
            conn.execute("BEGIN IMMEDIATE")

        for path in files:
            rel = ws.rel(path)
            seen.add(rel)
            try:
                stat = path.stat()
            except OSError:
                continue
            size = stat.st_size
            mtime = _mtime_iso(stat.st_mtime)
            ext = path.suffix.lower()
            is_text = ext in TEXT_EXTENSIONS
            is_moc = path.name == MOC_NAME
            sidecar = _sidecar_of(path)
            row = known.get(rel)
            has_body = rel in fts_body

            same_stat = (
                row is not None and not rebuild
                and row["size_bytes"] == size and row["modified_at"] == mtime and row["content_hash"]
            )
            sidecar_text: Optional[str] = None
            if sidecar is not None:
                sidecar_text = read_text_lossy(sidecar)
            if same_stat:
                if is_text and has_body and not is_moc:
                    report["unchanged"] += 1
                    continue
                if sidecar is not None and has_body:
                    stored = conn.execute("SELECT ocr_text FROM file_index WHERE rowid = ?", (row["rid"],)).fetchone()
                    if stored and stored["ocr_text"] == sidecar_text:
                        report["unchanged"] += 1
                        continue
                if not is_text and sidecar is None:
                    if not has_body and ext in DOCUMENT_EXTENSIONS:
                        report["needs_text"].append(rel)
                    report["unchanged"] += 1
                    continue

            try:
                digest = sha256_file(path)
            except OSError:
                continue
            content: Optional[str] = None
            pointer_rows: List[str] = []
            tags: Optional[str] = None
            topic: Optional[str] = None
            if is_text:
                content = read_text_lossy(path)
                if ext != ".txt":
                    tags, topic = _frontmatter_fields(content)
                if is_moc:
                    content, pointer_rows = _moc_parts(content)
            elif sidecar_text is not None:
                content = sidecar_text

            content_same = (
                row is not None and not rebuild and row["content_hash"] == digest
                and has_body and sidecar is None and is_text
                and (not is_moc or len(fts_pointer.get(rel, [])) == len(pointer_rows))
            )
            if content_same and same_stat:
                report["unchanged"] += 1
                continue
            folder = rel.rsplit("/", 1)[0] if "/" in rel else ""
            status = "indexed" if (content is not None or has_body) else "metadata"

            if row is None:
                report["added"] += 1
                if not dry_run:
                    conn.execute(
                        "INSERT INTO file_index(path, folder, filename, file_type, size_bytes, modified_at, "
                        "inferred_topic, tags, ocr_text, indexed_at, status, content_hash) "
                        "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (rel, folder, path.name, ext.lstrip("."), size, mtime, topic, tags,
                         sidecar_text, stamp, status, digest),
                    )
            else:
                if content_same:
                    report["unchanged"] += 1
                else:
                    report["updated"] += 1
                if not dry_run:
                    keep_status = row["status"] if row["status"] not in _OWN_STATUS else status
                    conn.execute(
                        "UPDATE file_index SET folder = ?, filename = ?, file_type = ?, size_bytes = ?, "
                        "modified_at = ?, inferred_topic = COALESCE(?, inferred_topic), "
                        "tags = COALESCE(?, tags), ocr_text = COALESCE(?, ocr_text), indexed_at = ?, "
                        "status = ?, content_hash = ? WHERE rowid = ?",
                        (folder, path.name, ext.lstrip("."), size, mtime, topic, tags, sidecar_text,
                         stamp, keep_status, digest, row["rid"]),
                    )

            if content is not None:
                if not content_same and not dry_run:
                    delete_fts(fts_body.get(rel, []))
                    conn.execute(
                        "INSERT INTO search_fts(path, filename, folder, content, is_pointer) VALUES(?, ?, ?, ?, 0)",
                        (rel, path.name, folder, content),
                    )
                if is_moc and not content_same:
                    if not dry_run:
                        delete_fts(fts_pointer.get(rel, []))
                        for text in pointer_rows:
                            conn.execute(
                                "INSERT INTO search_fts(path, filename, folder, content, is_pointer) "
                                "VALUES(?, ?, ?, ?, 1)",
                                (rel, path.name, folder, text),
                            )
                    report["pointer_rows"] += len(pointer_rows)
            elif ext in DOCUMENT_EXTENSIONS:
                if not has_body:
                    report["needs_text"].append(rel)
                elif row is not None and row["content_hash"] and row["content_hash"] != digest:
                    report["stale_text"].append(rel)

        # Rows for files that are gone (or no longer indexable) inside the scope.
        def vanished(rel: str) -> bool:
            return any(rel.startswith(prefix + "/") for prefix in loose) and not (ws.root / rel).is_file()

        gone = [rel for rel in known if rel not in seen and (_in_scope(rel, scopes) or vanished(rel))]
        orphans = [rel for rel in list(fts_body) + list(fts_pointer)
                   if rel not in seen and rel not in known and rel is not None and _in_scope(rel, scopes)]
        gone_set = set(gone)
        for rel in gone:
            report["removed"] += 1
            if not dry_run:
                conn.execute("DELETE FROM file_index WHERE rowid = ?", (known[rel]["rid"],))
                delete_fts(fts_body.get(rel, []) + fts_pointer.get(rel, []))
        for rel in set(orphans):
            if not dry_run:
                delete_fts(fts_body.get(rel, []) + fts_pointer.get(rel, []))

        # Rows outside the scope whose file does not exist (older path forms,
        # folders that left the Repo Map). Counted; removed only with --prune.
        stale = []
        for rel in set(list(known) + [p for p in list(fts_body) + list(fts_pointer) if p is not None]):
            if not isinstance(rel, str) or rel in seen or _in_scope(rel, scopes) or rel in gone_set:
                continue
            # A row is stale only when its file is gone. A row written in an
            # older path form (./x, an absolute path) for a file that still
            # exists is left alone: it may hold text a role extracted.
            candidate = Path(rel)
            target = candidate if candidate.is_absolute() else ws.root / rel
            try:
                exists = target.is_file()
            except OSError:
                exists = False
            if not exists:
                stale.append(rel)
        if prune:
            for rel in stale:
                report["pruned"] += 1
                if not dry_run:
                    if rel in known:
                        conn.execute("DELETE FROM file_index WHERE rowid = ?", (known[rel]["rid"],))
                    delete_fts(fts_body.get(rel, []) + fts_pointer.get(rel, []))
        else:
            report["stale_elsewhere"] = len(stale)

        if not dry_run:
            conn.execute("COMMIT")
    except sqlite3.Error as exc:
        if not dry_run:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
        raise ToolError("indexing failed and was rolled back: %s" % exc, EXIT_FAIL)

    report["unreadable_names"] = ws.unreadable_names
    report["needs_text"].sort()
    report["stale_text"].sort()
    report["seconds"] = round(time.time() - started, 2)
    return report
