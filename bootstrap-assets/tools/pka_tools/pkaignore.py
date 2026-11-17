"""`.pkaignore`: gitignore syntax plus `# @pka-section: <folder>` scoping.

Supported: comments, blank lines, `!` negation, a trailing `/` (directories
only), a leading `/` or an inner `/` (anchored to the workspace root),
`*`, `?`, `[...]` and `**`. A pattern with no slash matches a name at any
depth. The last matching rule wins, and everything under an ignored
directory is ignored.

Lines after `# @pka-section: <folder>` apply only inside `<folder>/`. They
are matched against the workspace-relative path first and, failing that,
against the path relative to the section folder.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

DEFAULT_PATTERNS = """\
.pka/
.git/
~$*
*.pyc
*.tsbuildinfo
.DS_Store
Thumbs.db
node_modules/
dist/
build/
target/
__pycache__/
_output/
*.map
*.dll
*.cache
*.class
# @pka-section: projects
projects/*/*/*
"""

_SECTION_RE = re.compile(r"^#\s*@pka-section:\s*(.+?)\s*$")


class Rule:
    __slots__ = ("regex", "negated", "dir_only", "section")

    def __init__(self, regex: "re.Pattern[str]", negated: bool, dir_only: bool, section: str):
        self.regex = regex
        self.negated = negated
        self.dir_only = dir_only
        self.section = section


def _glob_to_regex(pattern: str) -> str:
    out = []
    idx = 0
    length = len(pattern)
    while idx < length:
        char = pattern[idx]
        if char == "*":
            if pattern.startswith("**", idx):
                if pattern.startswith("**/", idx):
                    out.append("(?:.*/)?")
                    idx += 3
                    continue
                out.append(".*")
                idx += 2
                continue
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        elif char == "[":
            close = pattern.find("]", idx + 2)
            if close == -1:
                out.append(re.escape(char))
            else:
                body = pattern[idx + 1: close]
                if body.startswith("!"):
                    body = "^" + body[1:]
                out.append("[" + body.replace("\\", "\\\\") + "]")
                idx = close
        elif char == "\\" and idx + 1 < length:
            idx += 1
            out.append(re.escape(pattern[idx]))
        else:
            out.append(re.escape(char))
        idx += 1
    return "".join(out)


def _compile(line: str, section: str) -> Optional[Rule]:
    pattern = line.rstrip()
    if not pattern:
        return None
    negated = False
    if pattern.startswith("!"):
        negated = True
        pattern = pattern[1:]
    elif pattern.startswith("\\!") or pattern.startswith("\\#"):
        pattern = pattern[1:]
    dir_only = pattern.endswith("/")
    pattern = pattern.rstrip("/")
    if not pattern:
        return None
    anchored = pattern.startswith("/") or "/" in pattern
    pattern = pattern.lstrip("/")
    body = _glob_to_regex(pattern)
    if anchored:
        regex = re.compile("^" + body + "$")
    else:
        regex = re.compile("^(?:.*/)?" + body + "$")
    return Rule(regex, negated, dir_only, section)


class Ignore:
    def __init__(self, rules: List[Rule]):
        self.rules = rules

    @classmethod
    def from_text(cls, text: str) -> "Ignore":
        rules = []
        section = ""
        for raw in text.splitlines():
            line = raw.strip()
            match = _SECTION_RE.match(line)
            if match:
                section = match.group(1).strip().strip("/")
                continue
            if not line or line.startswith("#"):
                continue
            rule = _compile(line, section)
            if rule is not None:
                rules.append(rule)
        return cls(rules)

    @classmethod
    def load(cls, root: Path) -> "Ignore":
        path = root / ".pkaignore"
        if path.is_file():
            try:
                return cls.from_text(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
        return cls.from_text(DEFAULT_PATTERNS)

    def _match_one(self, rel: str, is_dir: bool) -> bool:
        ignored = False
        for rule in self.rules:
            if rule.dir_only and not is_dir:
                continue
            if rule.section:
                prefix = rule.section + "/"
                if not rel.startswith(prefix):
                    continue
                hit = rule.regex.match(rel) or rule.regex.match(rel[len(prefix):])
            else:
                hit = rule.regex.match(rel)
            if hit:
                ignored = not rule.negated
        return ignored

    def is_ignored(self, rel: str, is_dir: bool) -> bool:
        """True when `rel` (workspace-relative, POSIX) or an ancestor is ignored."""
        parts = rel.strip("/").split("/")
        for depth in range(1, len(parts)):
            if self._match_one("/".join(parts[:depth]), True):
                return True
        return self._match_one("/".join(parts), is_dir)

    def match(self, rel: str, is_dir: bool) -> bool:
        """For a walker that prunes ignored directories: test this path only."""
        return self._match_one(rel.strip("/"), is_dir)
