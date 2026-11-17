"""YAML frontmatter, handled line by line.

The standard library has no YAML parser, and re-rendering a user's
frontmatter would reorder keys, drop comments and change quoting. So this
module never renders a document. It recognises a conservative subset well
enough to answer "is this key present?" and "what are the tags?", and it
edits by inserting or changing single lines.

Anything outside the subset makes the block `error`: callers then leave the
file alone and report it. Being unable to edit is safe; guessing is not.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .textio import BOM, line_body, line_end

_KEY_RE = re.compile(r"^(\w[\w .\-]*?)[ \t]*:(?:[ \t]+(.*)|[ \t]*)$")
_PLAIN_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-/]*$")
_LOOKS_SPECIAL = re.compile(
    r"^(true|false|yes|no|on|off|null|~|[-+]?[0-9][0-9_,.]*([eE][-+]?[0-9]+)?|0x[0-9a-fA-F]+)$",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Key:
    __slots__ = ("name", "line", "end", "value")

    def __init__(self, name: str, line: int, end: int, value: str):
        self.name = name      # as written
        self.line = line      # index of the `key:` line
        self.end = end        # index one past the key's last continuation line
        self.value = value    # inline value, comment stripped, may be ""


class Frontmatter:
    """The frontmatter block of a file, as positions in its list of lines."""

    def __init__(self) -> None:
        self.present = False
        self.error: Optional[str] = None
        self.open = 0          # index of the opening --- line
        self.close = 0         # index of the closing --- line
        self.keys: Dict[str, Key] = {}
        self.order: List[Key] = []

    @property
    def usable(self) -> bool:
        return self.present and self.error is None

    def has(self, name: str) -> bool:
        return name in self.keys

    def has_ci(self, name: str) -> Optional[Key]:
        wanted = name.lower()
        for key in self.order:
            if key.name.lower() == wanted:
                return key
        return None


def _strip_comment(value: str) -> str:
    """Remove a trailing ` # comment` that is outside quotes."""
    quote = ""
    idx = 0
    while idx < len(value):
        char = value[idx]
        if quote:
            if char == "\\" and quote == '"':
                idx += 2
                continue
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char == "#" and (idx == 0 or value[idx - 1] in " \t"):
            return value[:idx].rstrip()
        idx += 1
    return value.rstrip()


def _flow_close(body: str, start: int) -> int:
    """Index of the bracket that closes the `[` at `start`, or -1."""
    depth = 0
    quote = ""
    idx = start
    while idx < len(body):
        char = body[idx]
        if quote:
            if char == "\\" and quote == '"':
                idx += 2
                continue
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return idx
        idx += 1
    return -1


def _value_problem(value: str, has_continuation: bool) -> Optional[str]:
    """Why an inline value is outside the supported subset, or None."""
    if not value:
        return None
    first = value[0]
    if first == '"':
        body = value[1:]
        closed = False
        idx = 0
        while idx < len(body):
            if body[idx] == "\\":
                idx += 2
                continue
            if body[idx] == '"':
                closed = True
                if body[idx + 1:].strip():
                    return "text after a closing quote"
                break
            idx += 1
        if not closed:
            return "unterminated double quote"
        return None
    if first == "'":
        body = value[1:].replace("''", "")
        pos = body.find("'")
        if pos == -1:
            return "unterminated single quote"
        if body[pos + 1:].strip():
            return "text after a closing quote"
        return None
    if first == "[":
        close = _flow_close(value, 0)
        if close == -1:
            if has_continuation:
                return None  # multi-line flow value: opaque, but not an error
            return "unclosed ["
        if close != len(value) - 1:
            return "text after the closing ]"
        return None
    if first == "{":
        if not value.endswith("}"):
            if has_continuation:
                return None
            return "unclosed {"
        return None
    if first in "|>":
        return None  # block scalar; the indented lines that follow are opaque
    if first in "&*!":
        return None  # anchors, aliases and tags: opaque
    if re.search(r":(\s|$)", value):
        return "unquoted colon in value"
    return None


def parse(lines: List[str]) -> Frontmatter:
    fm = Frontmatter()
    if not lines:
        return fm
    first = line_body(lines[0])
    if first.startswith(BOM):
        first = first[len(BOM):]
    if first.rstrip() != "---":
        return fm
    fm.present = True
    fm.open = 0
    close = None
    for idx in range(1, len(lines)):
        if line_body(lines[idx]).rstrip() in ("---", "..."):
            close = idx
            break
    if close is None:
        fm.error = "no closing --- line"
        return fm
    fm.close = close

    current: Optional[Key] = None
    for idx in range(1, close):
        body = line_body(lines[idx])
        if not body.strip() or body.lstrip().startswith("#"):
            continue
        if body[0] == "\t":
            fm.error = "line %d: tab used for indentation" % (idx + 1)
            return fm
        if body[0] == " ":
            if current is None:
                fm.error = "line %d: indented line before any key" % (idx + 1)
                return fm
            if "\t" in body[: len(body) - len(body.lstrip())]:
                fm.error = "line %d: tab used for indentation" % (idx + 1)
                return fm
            current.end = idx + 1
            continue
        if body == "-" or body.startswith("- "):
            # A block list written at column 0 under its key (valid YAML).
            if current is None or current.value:
                fm.error = "line %d: list item without a key" % (idx + 1)
                return fm
            current.end = idx + 1
            continue
        match = _KEY_RE.match(body)
        if not match:
            fm.error = "line %d: not a `key: value` line" % (idx + 1)
            return fm
        name = match.group(1)
        value = _strip_comment(match.group(2) or "")
        if name in fm.keys:
            fm.error = "line %d: key `%s` appears twice" % (idx + 1, name)
            return fm
        current = Key(name, idx, idx + 1, value)
        fm.keys[name] = current
        fm.order.append(current)

    for key in fm.order:
        problem = _value_problem(key.value, key.end > key.line + 1)
        if problem:
            fm.error = "line %d: %s (key `%s`)" % (key.line + 1, problem, key.name)
            return fm
    return fm


# ---------------------------------------------------------------- reading

def _unquote(item: str) -> str:
    item = item.strip()
    if len(item) >= 2 and item[0] == item[-1] and item[0] in "\"'":
        inner = item[1:-1]
        if item[0] == '"':
            inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        else:
            inner = inner.replace("''", "'")
        return inner
    return item


def split_flow(inner: str) -> List[str]:
    """Split the inside of a flow list on commas outside quotes and brackets."""
    items = []
    depth = 0
    quote = ""
    start = 0
    idx = 0
    while idx < len(inner):
        char = inner[idx]
        if quote:
            if char == "\\" and quote == '"':
                idx += 2
                continue
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif char == "," and depth == 0:
            items.append(inner[start:idx])
            start = idx + 1
        idx += 1
    items.append(inner[start:])
    return [item.strip() for item in items if item.strip()]


def _block_items(lines: List[str], key: Key) -> Optional[List[Tuple[int, str, str]]]:
    """Items of a block list as (line index, indent, text), or None if not a list."""
    items = []
    for idx in range(key.line + 1, key.end):
        body = line_body(lines[idx])
        if not body.strip() or body.lstrip().startswith("#"):
            continue
        stripped = body.lstrip()
        indent = body[: len(body) - len(stripped)]
        if stripped == "-" or stripped.startswith("- "):
            items.append((idx, indent, _strip_comment(stripped[1:].strip())))
        else:
            return None
    return items


def get_list(lines: List[str], fm: Frontmatter, name: str) -> List[str]:
    """The key's value as a list of strings ([] when absent or not readable)."""
    if not fm.usable or name not in fm.keys:
        return []
    key = fm.keys[name]
    value = key.value
    if value.startswith("[") and value.endswith("]"):
        return [_unquote(item) for item in split_flow(value[1:-1])]
    if not value:
        items = _block_items(lines, key)
        if items is None:
            return []
        return [_unquote(text) for _, _, text in items if text]
    if value[0] in "|>&*!{[":
        return []
    return [_unquote(value)]


def get_scalar(lines: List[str], fm: Frontmatter, name: str) -> str:
    if not fm.usable or name not in fm.keys:
        return ""
    value = fm.keys[name].value
    if not value or value[0] in "[{|>&*!":
        return ""
    return _unquote(value)


# ---------------------------------------------------------------- writing

def scalar(text: str) -> str:
    """Render a string as a YAML scalar that every parser reads back the same."""
    if text == "":
        return '""'
    if _DATE_RE.match(text):
        return text
    if _PLAIN_OK.match(text) and not _LOOKS_SPECIAL.match(text) and not text.endswith(" "):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def quoted(text: str) -> str:
    """Always double-quoted (for values such as "[[a/b]]" that must be strings)."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def flow_list(items: List[str]) -> str:
    return "[" + ", ".join(scalar(item) for item in items) + "]"


def create_block(pairs: List[Tuple[str, str]], newline: str) -> List[str]:
    """Lines for a new frontmatter block. Values are already rendered."""
    out = ["---" + newline]
    for name, rendered in pairs:
        out.append("%s: %s%s" % (name, rendered, newline))
    out.append("---" + newline)
    return out


def prepend_block(lines: List[str], pairs: List[Tuple[str, str]], newline: str) -> List[str]:
    """A new list of lines with a frontmatter block in front of the content.

    The existing content is kept byte for byte; a byte-order mark stays first.
    """
    block = create_block(pairs, newline)
    if not lines:
        return block
    rest = list(lines)
    bom = ""
    if rest[0].startswith(BOM):
        bom = BOM
        rest[0] = rest[0][len(BOM):]
    block[0] = bom + block[0]
    if line_body(rest[0]).strip():
        block.append(newline)
    return block + rest


def add_keys(lines: List[str], fm: Frontmatter, pairs: List[Tuple[str, str]], newline: str) -> List[str]:
    """Insert `key: value` lines just above the closing ---. Nothing else moves."""
    if not pairs:
        return lines
    end = line_end(lines[fm.close]) or newline
    new = ["%s: %s%s" % (name, rendered, end) for name, rendered in pairs]
    return lines[: fm.close] + new + lines[fm.close:]


def _tag_equal(a: str, b: str) -> bool:
    return a.strip().lstrip("#").lower() == b.strip().lstrip("#").lower()


def merge_tag(lines: List[str], fm: Frontmatter, tag: str, newline: str) -> Tuple[List[str], str]:
    """Make sure `tag` is in the `tags` list.

    Returns (lines, status) with status one of:
      "added"       a line was inserted or one line was changed
      "present"     nothing to do
      "uneditable"  `tags` exists in a form this tool will not edit
    """
    key = fm.keys.get("tags")
    if key is None:
        other = fm.has_ci("tags") or fm.has_ci("tag")
        if other is not None:
            return lines, "uneditable"
        return add_keys(lines, fm, [("tags", flow_list([tag]))], newline), "added"

    existing = get_list(lines, fm, "tags")
    if any(_tag_equal(item, tag) for item in existing):
        return lines, "present"

    value = key.value
    body = line_body(lines[key.line])
    end = line_end(lines[key.line])

    if value.startswith("[") and value.endswith("]") and key.end == key.line + 1:
        opener = body.find("[", body.find(":"))
        close = _flow_close(body, opener)
        if opener == -1 or close == -1:
            return lines, "uneditable"
        inner = body[opener + 1: close].strip()
        if not inner:
            addition = scalar(tag)
        elif inner.endswith(","):
            addition = " " + scalar(tag)        # `[a, b,]`: reuse the trailing comma
        else:
            addition = ", " + scalar(tag)
        new_body = body[:close].rstrip() + addition + body[close:]
        out = list(lines)
        out[key.line] = new_body + end
        return out, "added"

    if not value:
        items = _block_items(lines, key)
        if items is None:
            return lines, "uneditable"
        if not items:
            if key.end != key.line + 1:
                return lines, "uneditable"
            colon = body.find(":")
            rest = body[colon + 1:].strip()          # a trailing comment, if any
            out = list(lines)
            out[key.line] = body[: colon + 1] + " " + flow_list([tag]) + ("  " + rest if rest else "") + end
            return out, "added"
        last_idx, indent, _ = items[-1]
        item_end = line_end(lines[last_idx]) or newline
        out = list(lines)
        if not line_end(out[last_idx]):
            out[last_idx] = out[last_idx] + item_end
        out.insert(last_idx + 1, "%s- %s%s" % (indent, scalar(tag), item_end))
        return out, "added"

    return lines, "uneditable"
