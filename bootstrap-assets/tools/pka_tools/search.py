"""Full-text search with safe query construction and the pointer-row boost."""
from __future__ import annotations

import re
import sqlite3
from typing import List

from .db import require_current
from .errors import EXIT_FAIL, EXIT_USAGE, ToolError
from .markdown import wikilink_targets
from .pointers import resolve_link
from .workspace import Workspace

POINTER_BOOST = 3.0
_HAS_WORD = re.compile(r"\w", re.UNICODE)

_QUERY = """
SELECT path, filename, is_pointer, content,
       snippet(search_fts, 3, '[', ']', ' … ', 24) AS excerpt,
       rank * (CASE is_pointer WHEN 1 THEN {boost} ELSE 1.0 END) AS score
FROM search_fts
WHERE search_fts MATCH ?
ORDER BY score
LIMIT ?
""".format(boost=POINTER_BOOST)


def terms_of(text: str) -> List[str]:
    """The words of a search, each one quoted for FTS5.

    FTS5 reads `-`, `:`, `?`, `/`, `AND`, `OR`, `NOT` and `NEAR` as syntax, so
    a term is never passed bare. A term with no letter or digit in it would
    quote to an empty phrase and is dropped.
    """
    out = []
    for term in text.split():
        if _HAS_WORD.search(term):
            out.append('"' + term.replace('"', '""') + '"')
    return out


def match_string(text: str, any_term: bool = False) -> str:
    terms = terms_of(text)
    if not terms:
        raise ToolError("nothing to search for in %r" % text, EXIT_USAGE)
    return (" OR " if any_term else " ").join(terms)


def run(ws: Workspace, conn: sqlite3.Connection, text: str, limit: int = 20, any_term: bool = False) -> dict:
    require_current(conn)
    if limit < 1:
        raise ToolError("--limit must be at least 1", EXIT_USAGE)
    mode = "any" if any_term else "all"
    match = match_string(text, any_term)
    try:
        rows = conn.execute(_QUERY, (match, limit)).fetchall()
        if not rows and not any_term and len(terms_of(text)) > 1:
            mode = "any"
            match = match_string(text, True)
            rows = conn.execute(_QUERY, (match, limit)).fetchall()
    except sqlite3.Error as exc:
        raise ToolError("search failed: %s" % exc, EXIT_FAIL)

    results = []
    for row in rows:
        is_pointer = row["is_pointer"] in (1, "1")
        entry = {
            "path": row["path"],
            "is_pointer": is_pointer,
            "score": round(row["score"], 4) if row["score"] is not None else None,
            "excerpt": " ".join((row["excerpt"] or "").split()),
        }
        if is_pointer:
            content = row["content"] or ""
            entry["topic"] = content.split(" ", 1)[0] if content else ""
            files = []
            for target in wikilink_targets(content):
                found = resolve_link(ws, target)
                files.append({
                    "path": ws.rel(found) if found else None,
                    "link": "[[%s]]" % target,
                    "exists": found is not None,
                })
            entry["files"] = files
        results.append(entry)
    return {"query": text, "match": match, "mode": mode, "count": len(results), "results": results}
