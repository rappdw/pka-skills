"""The SQLite index at .pka/knowledge.db: schema, migration and backup.

The schema version lives in `PRAGMA user_version`. Version 0 is a database
that was created before this tool existed (by a model following the
reference prose), so its layout cannot be assumed: migration inspects what is
there and changes only what it recognises.

A migration always takes a backup first, runs in one transaction, and checks
the result before it commits.
"""
from __future__ import annotations

import datetime as _dt
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Dict, List, Optional

from . import __version__
from .errors import EXIT_ENV, EXIT_FAIL, EXIT_NOT_READY, ToolError
from .workspace import Workspace

SCHEMA_VERSION = 1

FILE_INDEX_COLUMNS = [
    ("id", "INTEGER PRIMARY KEY"),
    ("path", "TEXT NOT NULL"),
    ("folder", "TEXT NOT NULL"),
    ("filename", "TEXT NOT NULL"),
    ("file_type", "TEXT"),
    ("size_bytes", "INTEGER"),
    ("modified_at", "TEXT"),
    ("inferred_topic", "TEXT"),
    ("tags", "TEXT"),
    ("ocr_text", "TEXT"),
    ("indexed_at", "TEXT"),
    ("status", "TEXT"),
    ("content_hash", "TEXT"),
]

FTS_COLUMNS = ["path", "filename", "folder", "content", "is_pointer"]
FTS_TOKENIZE = "porter unicode61"

_CREATE_FILE_INDEX = "CREATE TABLE file_index (\n    %s\n)" % ",\n    ".join(
    "%s %s" % (name, decl) for name, decl in FILE_INDEX_COLUMNS
)
_CREATE_FTS = (
    "CREATE VIRTUAL TABLE %s USING fts5(\n"
    "    path, filename, folder, content,\n"
    "    is_pointer UNINDEXED,\n"
    "    tokenize = '" + FTS_TOKENIZE + "'\n)"
)
_CREATE_LIFECYCLE = (
    "CREATE TABLE project_lifecycle (\n"
    "    id INTEGER PRIMARY KEY,\n"
    "    project_slug TEXT NOT NULL,\n"
    "    event TEXT NOT NULL,\n"
    "    event_date TEXT NOT NULL,\n"
    "    notes TEXT\n)"
)
_CREATE_META = "CREATE TABLE pka_meta (key TEXT PRIMARY KEY, value TEXT)"
_INDEXES = [
    "CREATE UNIQUE INDEX IF NOT EXISTS file_index_path_uq ON file_index(path)",
    "CREATE INDEX IF NOT EXISTS file_index_content_hash ON file_index(content_hash)",
]


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def check_fts5() -> None:
    try:
        with closing(sqlite3.connect(":memory:")) as conn:
            conn.execute("CREATE VIRTUAL TABLE t USING fts5(a)")
    except sqlite3.Error:
        raise ToolError(
            "this Python's SQLite was built without FTS5, which the index needs. "
            "Use a Python whose sqlite3 module includes FTS5 (python.org and Homebrew builds do).",
            EXIT_ENV,
        )


def connect(ws: Workspace, must_exist: bool = True) -> sqlite3.Connection:
    if must_exist and not ws.db_path.is_file():
        raise ToolError(
            "no index at %s. This workspace is in markdown-only mode; "
            "run `pka-tools db init` to create an index." % ws.rel(ws.db_path),
            EXIT_NOT_READY,
        )
    try:
        conn = sqlite3.connect(str(ws.db_path), timeout=10, isolation_level=None)
    except sqlite3.Error as exc:
        raise ToolError("cannot open %s: %s" % (ws.rel(ws.db_path), exc), EXIT_FAIL)
    conn.row_factory = sqlite3.Row
    return conn


def user_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def require_current(conn: sqlite3.Connection) -> None:
    version = user_version(conn)
    if version < SCHEMA_VERSION:
        raise ToolError(
            "the index is at schema version %d and this tool needs %d. "
            "Run `pka-tools db migrate` to see the changes, then `pka-tools db migrate --apply`."
            % (version, SCHEMA_VERSION),
            EXIT_NOT_READY,
        )
    if version > SCHEMA_VERSION:
        raise ToolError(
            "the index is at schema version %d, newer than this tool (%d). Update pka-tools."
            % (version, SCHEMA_VERSION),
            EXIT_NOT_READY,
        )


def _objects(conn: sqlite3.Connection) -> Dict[str, sqlite3.Row]:
    rows = conn.execute("SELECT name, type, sql FROM sqlite_master").fetchall()
    return {row["name"]: row for row in rows}


def _columns(conn: sqlite3.Connection, table: str) -> List[str]:
    return [row["name"] for row in conn.execute('PRAGMA table_info("%s")' % table.replace('"', '""'))]


def _write_meta(conn: sqlite3.Connection, **values: str) -> None:
    for key, value in values.items():
        conn.execute(
            "INSERT INTO pka_meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def _self_ignore(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / ".gitignore"
    if not marker.exists():
        marker.write_text("*\n", encoding="utf-8")


# ---------------------------------------------------------------- init

def init(ws: Workspace) -> dict:
    """Create the index. Never touches an existing database."""
    check_fts5()
    if ws.db_path.exists():
        with closing(connect(ws)) as conn:
            version = user_version(conn)
        if version == SCHEMA_VERSION:
            return {"action": "already-initialized", "schema_version": version, "path": ws.rel(ws.db_path)}
        raise ToolError(
            "%s already exists at schema version %d. Use `pka-tools db migrate`."
            % (ws.rel(ws.db_path), version),
            EXIT_NOT_READY,
        )
    if not ws.pka.is_dir():
        raise ToolError("no .pka/ directory in %s; bootstrap the workspace first." % ws.root, EXIT_NOT_READY)
    with closing(connect(ws, must_exist=False)) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(_CREATE_FILE_INDEX)
            for statement in _INDEXES:
                conn.execute(statement)
            conn.execute(_CREATE_FTS % "search_fts")
            conn.execute(_CREATE_LIFECYCLE)
            conn.execute(_CREATE_META)
            _write_meta(conn, created_by="pka-tools " + __version__, created_at=now_iso())
            conn.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            conn.execute("ROLLBACK")
            raise ToolError("could not create the index: %s" % exc, EXIT_FAIL)
    return {"action": "created", "schema_version": SCHEMA_VERSION, "path": ws.rel(ws.db_path)}


# ---------------------------------------------------------------- backup

def backup(ws: Workspace) -> Path:
    """A consistent copy of the database under .pka/db-backups/."""
    if not ws.db_path.is_file():
        raise ToolError("no index at %s; nothing to back up." % ws.rel(ws.db_path), EXIT_NOT_READY)
    folder = ws.pka / "db-backups"
    _self_ignore(folder)
    stamp = _stamp()
    target = folder / ("knowledge-%s.db" % stamp)
    counter = 2
    while target.exists():
        target = folder / ("knowledge-%s-%d.db" % (stamp, counter))
        counter += 1
    try:
        with closing(sqlite3.connect(str(ws.db_path), timeout=10)) as source:
            with closing(sqlite3.connect(str(target))) as dest:
                source.backup(dest)
        with closing(sqlite3.connect(str(target))) as check:
            result = check.execute("PRAGMA integrity_check").fetchone()[0]
    except sqlite3.Error as exc:
        if target.exists():
            target.unlink()
        raise ToolError("backup failed: %s" % exc, EXIT_FAIL)
    if result != "ok":
        raise ToolError("backup written to %s but it fails its integrity check: %s" % (target, result), EXIT_FAIL)
    return target


# ---------------------------------------------------------------- migrate

class Step:
    def __init__(self, description: str, statements: List[str]):
        self.description = description
        self.statements = statements


def plan_migration(conn: sqlite3.Connection) -> List[Step]:
    """The steps from the database's current layout to SCHEMA_VERSION."""
    steps: List[Step] = []
    objects = _objects(conn)

    # file_index
    if "file_index" not in objects:
        steps.append(Step("create table file_index", [_CREATE_FILE_INDEX]))
    else:
        columns = _columns(conn, "file_index")
        if "path" not in columns:
            raise ToolError(
                "file_index has no `path` column; this layout is not one pka-tools recognises. "
                "Nothing was changed. Move .pka/knowledge.db aside and run `pka-tools db init`, "
                "then `pka-tools index`, to rebuild the index from the files.",
                EXIT_NOT_READY,
            )
        for name, decl in FILE_INDEX_COLUMNS:
            if name not in columns:
                plain = decl.replace(" NOT NULL", "").replace(" PRIMARY KEY", "")
                steps.append(Step(
                    "add column file_index.%s" % name,
                    ['ALTER TABLE file_index ADD COLUMN %s %s' % (name, plain)],
                ))
        canonical = {name for name, _ in FILE_INDEX_COLUMNS}
        required = [
            row["name"] for row in conn.execute('PRAGMA table_info("file_index")')
            if row["name"] not in canonical and row["notnull"] and row["dflt_value"] is None
        ]
        if required:
            steps.append(Step(
                "NOTE: file_index has extra required column(s) %s that pka-tools does not fill; "
                "`index` cannot add rows until they are made optional or given a default "
                "(no change is made to them here)" % ", ".join(required),
                [],
            ))
        duplicates = conn.execute(
            "SELECT COUNT(*) FROM file_index WHERE rowid NOT IN "
            "(SELECT MAX(rowid) FROM file_index GROUP BY path) AND path IS NOT NULL"
        ).fetchone()[0]
        if duplicates:
            steps.append(Step(
                "remove %d duplicate file_index row(s) (same path; the newest row of each path is kept)" % duplicates,
                ["DELETE FROM file_index WHERE path IS NOT NULL AND rowid NOT IN "
                 "(SELECT MAX(rowid) FROM file_index GROUP BY path)"],
            ))
    existing_indexes = {name for name, row in objects.items() if row["type"] == "index"}
    if "file_index_path_uq" not in existing_indexes:
        steps.append(Step("add unique index on file_index.path", [_INDEXES[0]]))
    if "file_index_content_hash" not in existing_indexes:
        steps.append(Step("add index on file_index.content_hash", [_INDEXES[1]]))

    # search_fts
    if "search_fts" not in objects:
        steps.append(Step("create full-text table search_fts", [_CREATE_FTS % "search_fts"]))
    else:
        sql = (objects["search_fts"]["sql"] or "").lower()
        columns = _columns(conn, "search_fts")
        canonical = (
            columns == FTS_COLUMNS
            and "fts5" in sql
            and "porter" in sql
            and "is_pointer unindexed" in " ".join(sql.split())
        )
        if not canonical:
            if "path" in columns and "content" in columns:
                def pick(name: str, default: str) -> str:
                    return name if name in columns else default
                rows = conn.execute("SELECT COUNT(*) FROM search_fts").fetchone()[0]
                steps.append(Step(
                    "rebuild search_fts with the current columns (%d row(s) copied across)" % rows,
                    [
                        "DROP TABLE IF EXISTS search_fts_pka_new",
                        _CREATE_FTS % "search_fts_pka_new",
                        "INSERT INTO search_fts_pka_new(path, filename, folder, content, is_pointer) "
                        "SELECT path, %s, %s, content, %s FROM search_fts"
                        % (pick("filename", "''"), pick("folder", "''"), pick("is_pointer", "0")),
                        "DROP TABLE search_fts",
                        "ALTER TABLE search_fts_pka_new RENAME TO search_fts",
                    ],
                ))
            else:
                legacy = "search_fts_legacy_v0"
                suffix = 2
                while legacy in objects:
                    legacy = "search_fts_legacy_v0_%d" % suffix
                    suffix += 1
                steps.append(Step(
                    "search_fts has an unrecognised layout: keep it as %s and create a new, empty "
                    "search_fts (run `pka-tools index` afterwards to fill it)" % legacy,
                    ["ALTER TABLE search_fts RENAME TO %s" % legacy, _CREATE_FTS % "search_fts"],
                ))

    if "project_lifecycle" not in objects:
        steps.append(Step("create table project_lifecycle", [_CREATE_LIFECYCLE]))
    if "pka_meta" not in objects:
        steps.append(Step("create table pka_meta", [_CREATE_META]))
    return steps


def migrate(ws: Workspace, apply: bool) -> dict:
    """Plan, and with `apply` carry out, the migration to SCHEMA_VERSION."""
    check_fts5()
    with closing(connect(ws)) as conn:
        version = user_version(conn)
        if version > SCHEMA_VERSION:
            require_current(conn)
        if version == SCHEMA_VERSION:
            return {"action": "none", "from": version, "to": SCHEMA_VERSION, "steps": [], "backup": None}
        try:
            steps = plan_migration(conn)
        except sqlite3.Error as exc:
            raise ToolError("could not read the index: %s" % exc, EXIT_FAIL)
        descriptions = [step.description for step in steps]
        descriptions.append("set schema version to %d" % SCHEMA_VERSION)
        if not apply:
            return {"action": "planned", "from": version, "to": SCHEMA_VERSION,
                    "steps": descriptions, "backup": None}

    saved = backup(ws)
    with closing(connect(ws)) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            for step in steps:
                for statement in step.statements:
                    conn.execute(statement)
            _write_meta(conn, migrated_by="pka-tools " + __version__, migrated_at=now_iso(),
                        migrated_from=str(version))
            conn.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)
            check = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if check != "ok":
                raise sqlite3.DatabaseError("integrity check failed: %s" % check)
            conn.execute("INSERT INTO search_fts(search_fts) VALUES('integrity-check')")
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise ToolError(
                "migration failed and was rolled back; the index is unchanged. (%s)\n"
                "A backup taken beforehand is at %s" % (exc, ws.rel(saved)),
                EXIT_FAIL,
            )
    return {"action": "migrated", "from": version, "to": SCHEMA_VERSION,
            "steps": descriptions, "backup": ws.rel(saved)}


# ---------------------------------------------------------------- schema

def describe(ws: Workspace) -> dict:
    with closing(connect(ws)) as conn:
        version = user_version(conn)
        tables = []
        for name, row in sorted(_objects(conn).items()):
            if row["type"] != "table" or name.startswith("sqlite_"):
                continue
            if name.startswith("search_fts_") and name.rsplit("_", 1)[-1] in ("data", "idx", "content", "docsize", "config"):
                continue
            count: Optional[int]
            try:
                count = conn.execute('SELECT COUNT(*) FROM "%s"' % name.replace('"', '""')).fetchone()[0]
            except sqlite3.Error:
                count = None
            tables.append({"name": name, "columns": _columns(conn, name), "rows": count})
    return {"path": ws.rel(ws.db_path), "schema_version": version,
            "current": version == SCHEMA_VERSION, "tables": tables}
