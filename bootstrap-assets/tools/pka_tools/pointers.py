"""The pointer layer: `## Pointers` tables inside `_MOC.md` files.

Editing rule: this module changes only the lines it owns. Extending a
cluster changes one table row (new entries are added at the end of a cell;
nothing is re-sorted). A new cluster inserts one line after the last row. A
missing table or section is added without touching the lines already there.
A table it cannot read is left alone and reported.

Cluster rule (the one the reference document states):
  1. A row whose Topic equals the file's topic slug is the file's cluster.
  2. Otherwise a row matches when its Topic has at least two distinctive
     tokens and every one of them appears among the file's tokens. The row
     with the most distinctive tokens wins; ties go to the earlier row.
  3. Otherwise a new row is coined, unless a row already carries the coined
     slug, in which case that row is used.
A topic passed explicitly (`--topic`) is a decision: it skips step 2.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from . import frontmatter
from .errors import EXIT_USAGE, ToolError
from .markdown import (
    WIKILINK_RE,
    cell_spans,
    fence_mask,
    find_heading,
    heading_of,
    is_separator_row,
    link_target,
    replace_cell,
    section_end,
)
from .textio import NotText, detect_newline, line_body, line_end, read_text, split_lines, write_text_atomic
from .workspace import MOC_NAME, Workspace, tag_key

SIZE_CAP = 8
SECTION_TITLE = "Pointers"
PREAMBLE = (
    "Compact retrieval rows maintained by the librarian. Format: one row per "
    "concept cluster. FTS-indexed for fast lookup before expanding to file bodies."
)
COLUMNS = ("topic", "entities", "files")
HEADER_ROW = "| Topic | Entities | Files |"
SEPARATOR_ROW = "|---|---|---|"
STUB_COMMENT = "<!-- MOC stub created by pka-tools. Reorganise freely. -->"

STOP_WORDS = {
    "the", "and", "for", "with", "from", "that", "this", "those", "these",
    "are", "was", "were", "been", "but", "not", "yes", "does", "did", "has",
    "have", "had", "its", "our", "your", "their", "into", "onto", "about",
    "over", "under", "per", "via", "new", "old", "notes", "note", "doc", "docs",
    "file", "files", "draft", "final", "copy", "index",
}
_EMPTY_CELL = {"", "-", "–", "—", "none", "n/a", "na", "tbd"}
_DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}[-_ ]?")
_TOKEN_SPLIT = re.compile(r"[^\w]+|_+", re.UNICODE)


# ------------------------------------------------------------ tokens

def slugify(text: str) -> str:
    slug = re.sub(r"[^\w]+", "-", text.strip().lower(), flags=re.UNICODE)
    slug = slug.replace("_", "-")
    return re.sub(r"-{2,}", "-", slug).strip("-")


def tokenize(text: str) -> Set[str]:
    """Lower-case tokens of three or more characters, stop-words removed."""
    out = set()
    for token in _TOKEN_SPLIT.split(text.lower()):
        if len(token) >= 3 and token not in STOP_WORDS:
            out.add(token)
    return out


def distinctive(tokens: Set[str]) -> Set[str]:
    """Tokens that identify a cluster: numbers (years, dates) do not."""
    return {token for token in tokens if not token.isdigit()}


def _strip_link(value: str) -> str:
    match = WIKILINK_RE.search(value)
    if match:
        return link_target(match.group("target"))
    return value.strip()


def entity_slug(value: str) -> str:
    """`[[personnel/priya/index]]` -> `priya`; `Priya Nair` -> `priya-nair`."""
    target = _strip_link(value)
    parts = [part for part in target.replace("\\", "/").split("/") if part]
    if not parts:
        return ""
    name = parts[-1]
    if name.lower().endswith(".md"):
        name = name[:-3]
    if name.lower() == "index" and len(parts) > 1:
        name = parts[-2]
    return slugify(name)


class FileFacts:
    """What the pointer step may know about a routed file: its path and its
    frontmatter. The body is never read."""

    def __init__(self) -> None:
        self.topic = ""
        self.type = ""
        self.tags: List[str] = []
        self.entities: List[str] = []
        self.tokens: Set[str] = set()


def facts_for(ws: Workspace, path: Path, context: str = "") -> FileFacts:
    facts = FileFacts()
    people_values: List[str] = []
    if path.suffix.lower() in (".md", ".markdown") and path.is_file():
        try:
            lines = split_lines(read_text(path))
        except (NotText, OSError):
            lines = []
        fm = frontmatter.parse(lines)
        if fm.usable:
            facts.topic = frontmatter.get_scalar(lines, fm, "topic")
            facts.type = frontmatter.get_scalar(lines, fm, "type")
            facts.tags = [tag.lstrip("#") for tag in frontmatter.get_list(lines, fm, "tags")]
            for name in ("attendees", "person", "related"):
                people_values.extend(frontmatter.get_list(lines, fm, name))
    for value in people_values:
        slug = entity_slug(value)
        if slug and slug not in facts.entities:
            facts.entities.append(slug)

    tokens: Set[str] = set()
    tokens |= tokenize(facts.topic)
    tokens |= tokenize(facts.type)
    for tag in facts.tags:
        tokens |= tokenize(tag)
    for slug in facts.entities:
        tokens |= tokenize(slug)
    stem = path.name[: -len(path.suffix)] if path.suffix else path.name
    tokens |= tokenize(_DATE_PREFIX.sub("", stem))
    rel_parts = ws.vault_rel(path).split("/")[:-1]
    for part in rel_parts:
        tokens |= tokenize(part)
    tokens |= tokenize(context)
    facts.tokens = tokens
    return facts


def coin_slug(path: Path, facts: FileFacts) -> str:
    """Topic, else `<first non-type tag>-<type>`, else the filename stem."""
    if facts.topic:
        slug = slugify(facts.topic)
        if slug:
            return slug
    if facts.type:
        type_slug = slugify(facts.type)
        for tag in facts.tags:
            tag_slug = slugify(tag)
            if tag_slug and tag_slug != type_slug:
                return "%s-%s" % (tag_slug, type_slug)
    stem = path.name[: -len(path.suffix)] if path.suffix else path.name
    slug = slugify(_DATE_PREFIX.sub("", stem)) or slugify(stem)
    return slug or "uncategorized"


# ------------------------------------------------------------ tables

class Row:
    __slots__ = ("line", "spans", "topic", "entities_raw", "files_raw", "ok")

    def __init__(self, line: int, spans: List[Tuple[int, int]], topic: str,
                 entities_raw: str, files_raw: str, ok: bool):
        self.line = line
        self.spans = spans
        self.topic = topic
        self.entities_raw = entities_raw
        self.files_raw = files_raw
        self.ok = ok

    @property
    def entities(self) -> List[str]:
        if self.entities_raw.strip().lower() in _EMPTY_CELL:
            return []
        return [item.strip() for item in self.entities_raw.split(",") if item.strip()]

    @property
    def targets(self) -> List[str]:
        return [link_target(m.group("target")) for m in WIKILINK_RE.finditer(self.files_raw)]


class Table:
    """Where the Pointers section and its table are in a list of lines."""

    def __init__(self) -> None:
        self.heading: Optional[int] = None   # index of the `## Pointers` line
        self.end: int = 0                    # one past the section's last line
        self.header: Optional[int] = None    # index of the header row
        self.columns: Dict[str, int] = {}    # column name -> cell position
        self.width: int = 0                  # number of cells in the header
        self.rows: List[Row] = []
        self.last: Optional[int] = None      # index of the last table line
        self.problem: Optional[str] = None   # set when the table is unreadable


def locate(lines: List[str]) -> Table:
    table = Table()
    mask = fence_mask(lines)
    heading = find_heading(lines, mask, SECTION_TITLE, 2)
    if heading is None:
        return table
    table.heading = heading
    table.end = section_end(lines, mask, heading)

    idx = heading + 1
    first_row = None
    while idx < table.end:
        if not mask[idx] and cell_spans(line_body(lines[idx])) is not None:
            first_row = idx
            break
        idx += 1
    if first_row is None:
        return table

    body = line_body(lines[first_row])
    spans = cell_spans(body) or []
    names = [body[a:b].strip().lower() for a, b in spans]
    if not all(name in names for name in COLUMNS):
        table.problem = "the first table row is not a `Topic | Entities | Files` header"
        return table
    if first_row + 1 >= table.end or not is_separator_row(line_body(lines[first_row + 1])):
        table.problem = "the header row is not followed by a `|---|` separator row"
        return table
    table.header = first_row
    table.columns = {name: names.index(name) for name in COLUMNS}
    table.width = len(names)
    table.last = first_row + 1

    idx = first_row + 2
    while idx < table.end:
        body = line_body(lines[idx])
        spans = cell_spans(body)
        if spans is None or mask[idx]:
            break
        needed = max(table.columns.values()) + 1
        if len(spans) >= needed:
            table.rows.append(Row(
                idx, spans,
                body[slice(*spans[table.columns["topic"]])].strip(),
                body[slice(*spans[table.columns["entities"]])].strip(),
                body[slice(*spans[table.columns["files"]])].strip(),
                True,
            ))
        else:
            table.rows.append(Row(idx, spans, "", "", "", False))
        table.last = idx
        idx += 1
    return table


def read_rows(text: str) -> List[Row]:
    """Readable pointer rows of a MOC (for indexing and checks)."""
    table = locate(split_lines(text))
    return [row for row in table.rows if row.ok]


def pointer_row_lines(lines: List[str]) -> Set[int]:
    table = locate(lines)
    return {row.line for row in table.rows}


def _new_row_text(table: Table, topic: str, entities: List[str], link: str) -> str:
    width = max(table.width, 3)
    columns = table.columns or {name: pos for pos, name in enumerate(COLUMNS)}
    cells = [""] * width
    cells[columns["topic"]] = topic
    cells[columns["entities"]] = ", ".join(entities)
    cells[columns["files"]] = link
    return "| " + " | ".join(cells) + " |"


def _section_block(topic: str, entities: List[str], link: str, newline: str) -> List[str]:
    table = Table()
    return [
        "## %s%s" % (SECTION_TITLE, newline),
        newline,
        PREAMBLE + newline,
        newline,
        HEADER_ROW + newline,
        SEPARATOR_ROW + newline,
        _new_row_text(table, topic, entities, link) + newline,
    ]


def choose_row(table: Table, facts: FileFacts, explicit_topic: str, coined: str) -> Optional[Row]:
    rows = [row for row in table.rows if row.ok]
    wanted = [slugify(explicit_topic)] if explicit_topic else []
    if not explicit_topic and facts.topic:
        wanted.append(slugify(facts.topic))
    for slug in wanted:
        for row in rows:
            if slugify(row.topic) == slug:
                return row
    if not explicit_topic:
        best: Optional[Row] = None
        best_size = 0
        for row in rows:
            tokens = distinctive(tokenize(row.topic))
            if len(tokens) >= 2 and tokens <= facts.tokens and len(tokens) > best_size:
                best, best_size = row, len(tokens)
        if best is not None:
            return best
    for row in rows:
        if slugify(row.topic) == coined:
            return row
    return None


def apply_to_lines(
    lines: List[str],
    link_path: str,
    facts: FileFacts,
    explicit_topic: str,
    coined: str,
    title: str,
) -> Tuple[List[str], dict]:
    """Return (new lines, result) for adding one file to one MOC's pointers."""
    text = "".join(lines)
    newline = detect_newline(text)
    link = "[[%s]]" % link_path
    result = {"action": "noop", "topic": "", "files_in_row": 0, "problem": None}

    if not lines:
        block = ["# %s%s" % (title, newline), newline, STUB_COMMENT + newline, newline]
        block += _section_block(coined, facts.entities, link, newline)
        result.update(action="created-moc", topic=coined, files_in_row=1)
        return block, result

    table = locate(lines)
    if table.problem:
        result.update(action="skipped", problem=table.problem)
        return lines, result

    out = list(lines)
    if table.heading is None:
        if line_end(out[-1]) == "":
            out[-1] = out[-1] + newline
        if line_body(out[-1]).strip():
            out.append(newline)
        out += _section_block(coined, facts.entities, link, newline)
        result.update(action="created-section", topic=coined, files_in_row=1)
        return out, result

    if table.header is None:
        insert_at = table.end
        while insert_at > table.heading + 1 and not line_body(out[insert_at - 1]).strip():
            insert_at -= 1
        if line_end(out[insert_at - 1]) == "":
            out[insert_at - 1] = out[insert_at - 1] + newline
        block = [
            newline,
            HEADER_ROW + newline,
            SEPARATOR_ROW + newline,
            _new_row_text(Table(), coined, facts.entities, link) + newline,
        ]
        if insert_at < len(out) and line_body(out[insert_at]).strip():
            block.append(newline)
        out[insert_at:insert_at] = block
        result.update(action="created-table", topic=coined, files_in_row=1)
        return out, result

    row = choose_row(table, facts, explicit_topic, coined)
    if row is None:
        topic = slugify(explicit_topic) if explicit_topic else coined
        at = table.last if table.last is not None else table.header + 1
        end = line_end(out[at])
        if end == "":
            out[at] = out[at] + newline
            end = newline
        out.insert(at + 1, _new_row_text(table, topic, facts.entities, link) + end)
        result.update(action="appended", topic=topic, files_in_row=1)
        return out, result

    targets = row.targets
    have_file = link_path in targets
    existing = {entity.lower() for entity in row.entities}
    new_entities = [entity for entity in facts.entities if entity.lower() not in existing]
    result.update(topic=row.topic, files_in_row=len(targets) + (0 if have_file else 1))
    if have_file and not new_entities:
        return lines, result

    body = line_body(out[row.line])
    end = line_end(out[row.line])
    edits = []
    if not have_file:
        current = row.files_raw
        content = link if current.strip().lower() in _EMPTY_CELL else current + ", " + link
        edits.append((row.spans[table.columns["files"]], content))
    if new_entities:
        current = row.entities_raw
        addition = ", ".join(new_entities)
        content = addition if current.strip().lower() in _EMPTY_CELL else current + ", " + addition
        edits.append((row.spans[table.columns["entities"]], content))
    for span, content in sorted(edits, key=lambda item: item[0][0], reverse=True):
        body = replace_cell(body, span, content)
    out[row.line] = body + end
    result.update(action="extended")
    return out, result


# ------------------------------------------------------------ commands

def _moc_for_domain(ws: Workspace, domain: str) -> Path:
    return (ws.vault / domain / MOC_NAME) if domain else (ws.vault / MOC_NAME)


def target_mocs(ws: Workspace, path: Path, facts: FileFacts, extra: List[str]) -> List[Path]:
    """The destination domain's MOC, then one per tag that names another domain."""
    rel_parts = ws.vault_rel(path).split("/")
    primary_domain = rel_parts[0] if len(rel_parts) > 1 else ""
    mocs = [_moc_for_domain(ws, primary_domain)]
    domains: Dict[str, str] = {}
    try:
        for child in sorted(ws.vault.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                domains.setdefault(tag_key(child.name), child.name)
    except OSError:
        pass
    for tag in facts.tags:
        name = domains.get(tag_key(tag))
        if name and name != primary_domain:
            moc = _moc_for_domain(ws, name)
            if moc not in mocs:
                mocs.append(moc)
    for given in extra:
        moc = ws.resolve(given)
        if moc.name != MOC_NAME:
            raise ToolError("--moc must name a %s file: %s" % (MOC_NAME, given), EXIT_USAGE)
        ws.vault_rel(moc)
        if moc not in mocs:
            mocs.append(moc)
    return mocs


def link_path_for(ws: Workspace, path: Path) -> str:
    rel = ws.vault_rel(path)
    if rel.lower().endswith(".md"):
        rel = rel[:-3]
    return rel


def add(
    ws: Workspace,
    file_arg: str,
    topic: str = "",
    entities: Optional[List[str]] = None,
    context: str = "",
    extra_mocs: Optional[List[str]] = None,
    dry_run: bool = False,
) -> dict:
    """Record a routed file in the pointer table of its domain MOC(s)."""
    path = ws.resolve(file_arg)
    if not path.is_file():
        raise ToolError("no such file: %s" % file_arg, EXIT_USAGE)
    if path.name == MOC_NAME:
        raise ToolError("a %s is not a routed file" % MOC_NAME, EXIT_USAGE)
    facts = facts_for(ws, path, context)
    for value in entities or []:
        slug = entity_slug(value)
        if slug and slug not in facts.entities:
            facts.entities.append(slug)
            facts.tokens |= tokenize(slug)
    if topic:
        facts.tokens |= tokenize(topic)
    coined = slugify(topic) if topic else coin_slug(path, facts)
    link_path = link_path_for(ws, path)

    results = []
    changed: List[str] = []
    over_cap: List[str] = []
    for moc in target_mocs(ws, path, facts, extra_mocs or []):
        rel = ws.rel(moc)
        entry = {"moc": rel, "action": "noop", "topic": "", "problem": None}
        try:
            lines = split_lines(read_text(moc)) if moc.is_file() else []
        except NotText:
            entry.update(action="skipped", problem="not valid UTF-8")
            results.append(entry)
            continue
        except OSError as exc:
            entry.update(action="skipped", problem=str(exc))
            results.append(entry)
            continue
        title = moc.parent.name if moc.parent != ws.vault else (ws.vault.name or "Knowledge")
        new_lines, outcome = apply_to_lines(lines, link_path, facts, topic, coined, title)
        entry.update(action=outcome["action"], topic=outcome["topic"], problem=outcome["problem"])
        if new_lines != lines:
            if not dry_run:
                try:
                    write_text_atomic(moc, "".join(new_lines))
                except OSError as exc:
                    entry.update(action="skipped", problem="could not write: %s" % exc)
                    results.append(entry)
                    continue
            changed.append(rel)
        if outcome["files_in_row"] >= SIZE_CAP:
            over_cap.append("%s: %s (%d files)" % (rel, outcome["topic"], outcome["files_in_row"]))
        results.append(entry)
    return {
        "file": ws.rel(path),
        "link": "[[%s]]" % link_path,
        "coined_slug": coined,
        "entities": facts.entities,
        "mocs": results,
        "changed": changed,
        "over_cap": over_cap,
        "dry_run": dry_run,
    }


def _normalise_ref(ws: Workspace, given: str) -> str:
    """A link target from either a workspace path or a vault-relative one."""
    ref = given.strip().replace("\\", "/").strip("/")
    while ref.startswith("./"):
        ref = ref[2:]
    vault_prefix = ws.rel(ws.vault)
    if vault_prefix and (ref == vault_prefix or ref.startswith(vault_prefix + "/")):
        ref = ref[len(vault_prefix):].strip("/")
    if ref.lower().endswith(".md"):
        ref = ref[:-3]
    if not ref:
        raise ToolError("empty path: %r" % given, EXIT_USAGE)
    return ref


def rename(ws: Workspace, old: str, new: str, prefix: bool = False, dry_run: bool = False) -> dict:
    """Rewrite wikilinks in every `_MOC.md` after a file or folder moved.

    Only the link target changes: an alias or a `#heading` is kept.
    """
    old_ref = _normalise_ref(ws, old)
    new_ref = _normalise_ref(ws, new)
    total = 0
    changed: List[str] = []
    skipped: List[str] = []

    def swap(match: "re.Match[str]") -> str:
        nonlocal count
        raw = match.group("target")
        target = link_target(raw)
        replacement = None
        if target == old_ref:
            replacement = new_ref
        elif prefix and target.startswith(old_ref + "/"):
            replacement = new_ref + target[len(old_ref):]
        if replacement is None:
            return match.group(0)
        if raw.strip().lower().endswith(".md"):
            replacement += raw.strip()[-3:]
        count += 1
        return "[[%s%s%s]]" % (replacement, match.group("anchor") or "", match.group("alias") or "")

    for moc in ws.moc_files():
        try:
            text = read_text(moc)
        except (NotText, OSError):
            skipped.append(ws.rel(moc))
            continue
        lines = split_lines(text)
        mask = fence_mask(lines)
        count = 0
        out = []
        for idx, line in enumerate(lines):
            if mask[idx] or "[[" not in line:
                out.append(line)
                continue
            out.append(WIKILINK_RE.sub(swap, line))
        if count:
            total += count
            changed.append(ws.rel(moc))
            if not dry_run:
                write_text_atomic(moc, "".join(out))
    return {"from": old_ref, "to": new_ref, "prefix": prefix, "rewrites": total,
            "changed": changed, "skipped": skipped, "dry_run": dry_run}


def resolve_link(ws: Workspace, target: str) -> Optional[Path]:
    """The file a vault-relative link target names, or None."""
    base = ws.vault / target
    for candidate in (Path(str(base) + ".md"), base):
        if candidate.is_file():
            return candidate
    return None


def check(ws: Workspace) -> dict:
    """Report pointer links to missing files, unreadable tables and long rows."""
    broken = []
    malformed = []
    over_cap = []
    rows_total = 0
    for moc in ws.moc_files():
        rel = ws.rel(moc)
        try:
            lines = split_lines(read_text(moc))
        except (NotText, OSError) as exc:
            malformed.append({"moc": rel, "problem": str(exc)})
            continue
        table = locate(lines)
        if table.problem:
            malformed.append({"moc": rel, "problem": table.problem})
            continue
        for row in table.rows:
            if not row.ok:
                malformed.append({"moc": rel, "problem": "line %d has too few cells" % (row.line + 1)})
                continue
            rows_total += 1
            targets = row.targets
            if len(targets) >= SIZE_CAP:
                over_cap.append({"moc": rel, "topic": row.topic, "files": len(targets)})
            for target in targets:
                if resolve_link(ws, target) is None:
                    broken.append({"moc": rel, "topic": row.topic, "broken_link": "[[%s]]" % target,
                                   "line": row.line + 1})
    return {"rows": rows_total, "broken": broken, "malformed": malformed, "over_cap": over_cap}


def listing(ws: Workspace, moc_arg: Optional[str] = None) -> dict:
    mocs = [ws.resolve(moc_arg)] if moc_arg else ws.moc_files()
    out = []
    for moc in mocs:
        if not moc.is_file():
            raise ToolError("no such file: %s" % moc_arg, EXIT_USAGE)
        try:
            rows = read_rows(read_text(moc))
        except (NotText, OSError):
            continue
        out.append({
            "moc": ws.rel(moc),
            "rows": [{"topic": row.topic, "entities": row.entities, "files": row.targets} for row in rows],
        })
    return {"mocs": out}
