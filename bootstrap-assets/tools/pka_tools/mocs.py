"""MOC navigation links: the `- [[path]]` bullet a routed note gets in the
`_MOC.md` of the folder it landed in.

This is the Obsidian-side counterpart of the pointer row. Pointer rows are
for search; these bullets are for a person browsing the vault.

Editing rule, as everywhere: one inserted line. The bullet goes at the end of
the chosen section (`## Files` by default, or a section the caller names), or
under a `## Unsorted` section added at the end. Nothing is reordered. A link
to the note anywhere in the MOC's prose (outside fenced examples, inline
code and the Pointers table) counts as already present.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from .errors import EXIT_USAGE, ToolError
from .markdown import (
    WIKILINK_RE,
    fence_mask,
    find_heading,
    link_target,
    protected_spans,
    section_end,
    unclosed_fence,
)
from .pointers import pointer_row_lines
from .textio import (
    NotText, detect_newline, has_bare_cr, line_body, line_end, read_text, split_lines, write_text_atomic,
)
from .workspace import MOC_NAME, Workspace

DEFAULT_SECTION = "Files"
FALLBACK_SECTION = "Unsorted"
STUB_COMMENT = "<!-- MOC stub created by pka-tools. Reorganise freely. -->"
_UNLINKABLE = set("[]|#^")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")


def link_path(ws: Workspace, path: Path) -> str:
    rel = ws.vault_rel(path)
    return rel[:-3] if rel.lower().endswith(".md") else rel


def target_moc(ws: Workspace, path: Path) -> Path:
    """The nearest existing `_MOC.md` from the note's folder up to its
    top-level folder; when there is none, the top-level folder's MOC (the
    vault root's for a note at the root)."""
    rel_parts = ws.vault_rel(path).split("/")
    folder = path.parent
    top = ws.vault / rel_parts[0] if len(rel_parts) > 1 else ws.vault
    probe = folder
    while True:
        candidate = probe / MOC_NAME
        if candidate.exists() or candidate.is_symlink():
            return candidate
        if probe == top or probe == ws.vault:
            break
        probe = probe.parent
    return top / MOC_NAME


def has_link(lines: List[str], target: str) -> bool:
    mask = fence_mask(lines)
    pointer_lines = pointer_row_lines(lines)
    for idx, line in enumerate(lines):
        if mask[idx] or idx in pointer_lines or "[[" not in line:
            continue
        guarded = protected_spans(line)
        for match in WIKILINK_RE.finditer(line):
            start = match.start()
            if start > 0 and line[start - 1] == "\\":
                continue
            if any(a <= start < b for a, b in guarded):
                continue
            if link_target(match.group("target")) == target:
                return True
    return False


def insert_link(lines: List[str], bullet: str, section: Optional[str]) -> List[str]:
    """New lines with `bullet` (no line ending) placed in the right section."""
    text = "".join(lines)
    newline = detect_newline(text)
    mask = fence_mask(lines)
    wanted = section or DEFAULT_SECTION
    head = find_heading(lines, mask, wanted, 2)
    if head is None and section is None:
        head = find_heading(lines, mask, FALLBACK_SECTION, 2)
    out = list(lines)
    if head is not None:
        end = section_end(lines, mask, head)
        last = end - 1
        while last > head and not line_body(lines[last]).strip():
            last -= 1
        if not line_end(out[last]):
            out[last] = out[last] + newline
        new = [bullet + newline]
        # A bullet straight after a paragraph or heading is fine in markdown;
        # after the last line of the file keep the file's ending style.
        out[last + 1:last + 1] = new
        return out
    if out and not line_end(out[-1]):
        out[-1] = out[-1] + newline
    if out and line_body(out[-1]).strip():
        out.append(newline)
    out += ["## %s%s" % (FALLBACK_SECTION, newline), bullet + newline]
    return out


def add_link(
    ws: Workspace,
    file_arg: str,
    section: Optional[str] = None,
    create: Optional[bool] = None,
    dry_run: bool = False,
) -> dict:
    """Add a navigation bullet for a note to its folder's MOC.

    `create` (default: when the vault is an Obsidian vault) allows creating
    the MOC when there is none. A section named with `section` must exist.
    """
    path = ws.resolve(file_arg)
    if not path.is_file():
        raise ToolError("no such file: %s" % file_arg, EXIT_USAGE)
    if path.name == MOC_NAME:
        raise ToolError("a %s does not link to itself" % MOC_NAME, EXIT_USAGE)
    target = link_path(ws, path)
    moc = target_moc(ws, path)
    result = {"file": ws.rel(path), "moc": ws.rel(moc), "action": "noop", "problem": None,
              "changed": [], "dry_run": dry_run}
    if create is None:
        create = ws.obsidian_present
    if _UNLINKABLE & set(target):
        result.update(action="skipped",
                      problem="the path contains a character a wikilink cannot express ([ ] | # ^)")
        return result
    bullet = "- [[%s]]" % target

    if not moc.exists() and not moc.is_symlink():
        if not create:
            result.update(action="no-moc")
            return result
        if section is not None:
            raise ToolError("--section %r: %s does not exist yet" % (section, ws.rel(moc)), EXIT_USAGE)
        title = moc.parent.name if moc.parent != ws.vault else (ws.vault.name or "Knowledge")
        text = "\n".join(["# %s" % title, "", STUB_COMMENT, "", "## %s" % DEFAULT_SECTION, bullet]) + "\n"
        if not dry_run:
            try:
                write_text_atomic(moc, text)
            except OSError as exc:
                result.update(action="skipped", problem="could not write: %s" % exc)
                return result
        result.update(action="created-moc", changed=[ws.rel(moc)])
        return result

    try:
        text = read_text(moc)
    except NotText:
        result.update(action="skipped", problem="not valid UTF-8")
        return result
    except OSError as exc:
        result.update(action="skipped", problem=str(exc))
        return result
    lines = split_lines(text)
    if has_bare_cr(text):
        result.update(action="skipped", problem="the file uses bare carriage returns as line endings")
        return result
    if unclosed_fence(lines):
        result.update(action="skipped", problem="the file has a code fence that is never closed")
        return result
    if has_link(lines, target):
        return result
    if section is not None and find_heading(lines, fence_mask(lines), section, 2) is None:
        raise ToolError("--section %r: no `## %s` heading in %s" % (section, section, ws.rel(moc)), EXIT_USAGE)
    new_lines = insert_link(lines, bullet, section)
    if not dry_run:
        try:
            write_text_atomic(moc, "".join(new_lines))
        except OSError as exc:
            result.update(action="skipped", problem="could not write: %s" % exc)
            return result
    result.update(action="added", changed=[ws.rel(moc)])
    return result
