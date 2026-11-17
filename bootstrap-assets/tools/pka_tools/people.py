"""The people registry: who the person folders are, and which of them a name
means.

A person is a subfolder of the people home (the Repo Map folder tagged
`people-home`; fallback `knowledge/personnel/`). The slug is the folder name.
`index.md` in the folder may give a display `name` and `aliases`.

Resolution never guesses. A name resolves with **high** confidence only when
it is exactly a person's slug, name or alias (ignoring case, punctuation and
honorifics), the slug's words in either order, a link to the person's folder,
or a first name that only one person has. A last name on its own, or a name
that fits more than one person, is **ambiguous** and is never linked
automatically. Nicknames are not inferred: they become aliases when the user
says so (`people alias`).
"""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import unquote

from . import frontmatter
from .errors import EXIT_NOT_READY, EXIT_USAGE, ToolError
from .markdown import WIKILINK_RE, link_target
from .textio import NotText, detect_newline, has_bare_cr, read_text, split_lines, write_text_atomic
from .workspace import CAPTURE_MARKER, Workspace

INDEX = "index.md"
_HONORIFICS = {"dr", "mr", "mrs", "ms", "mx", "prof", "sir", "dame"}
_MD_LINK = re.compile(r"^\[[^\]]*\]\(\s*<?([^)>]+?)>?\s*\)$")


def display_name(slug: str) -> str:
    """`robin-smith` -> `Robin Smith`. Words that already have capitals are kept."""
    words = []
    for token in re.split(r"[-_]+", slug):
        if not token:
            continue
        words.append(token if any(c.isupper() for c in token) else token[:1].upper() + token[1:])
    return " ".join(words) or slug


def words_of(text: str) -> List[str]:
    """Lower-case words, accents folded for comparison, honorifics and
    `@` removed."""
    folded = unicodedata.normalize("NFKD", text.casefold())
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    words = [w for w in re.split(r"[^\w]+|_+", folded) if w]
    while words and words[0] in _HONORIFICS:
        words = words[1:]
    return words


class Person:
    __slots__ = ("slug", "folder", "index", "name", "aliases", "problem")

    def __init__(self, slug: str, folder: Path):
        self.slug = slug
        self.folder = folder
        self.index = folder / INDEX
        self.name = display_name(slug)
        self.aliases: List[str] = []
        self.problem: Optional[str] = None

    def load(self) -> "Person":
        if not self.index.is_file():
            return self
        try:
            lines = split_lines(read_text(self.index))
        except (NotText, OSError) as exc:
            self.problem = "index.md could not be read: %s" % exc
            return self
        fm = frontmatter.parse(lines)
        if fm.error:
            self.problem = "index.md frontmatter: %s" % fm.error
            return self
        name = frontmatter.get_scalar(lines, fm, "name")
        if name:
            self.name = name
        self.aliases = [alias for alias in frontmatter.get_list(lines, fm, "aliases") if alias.strip()]
        return self

    def as_dict(self, ws: Workspace) -> dict:
        return {"slug": self.slug, "name": self.name, "aliases": self.aliases,
                "folder": ws.rel(self.folder), "index": self.index.is_file(), "problem": self.problem}


class Registry:
    def __init__(self, ws: Workspace):
        self.ws = ws
        self.home = ws.people_home()
        self.people: Dict[str, Person] = {}
        if self.home is None or not self.home.is_dir():
            return
        try:
            children = sorted(os.scandir(str(self.home)), key=lambda e: e.name)
        except OSError:
            children = []
        for entry in children:
            if entry.name.startswith(".") or not entry.is_dir():
                continue
            folder = Path(entry.path)
            if (folder / CAPTURE_MARKER).exists() or ws.ignore.match(ws.rel(folder), True):
                continue
            try:
                entry.name.encode("utf-8")
            except UnicodeEncodeError:
                continue
            self.people[entry.name] = Person(entry.name, folder).load()

    # ---------------------------------------------------------------- lookup
    def person_of_path(self, path: Path) -> Optional[Person]:
        """The person whose folder contains `path` (at any depth)."""
        if self.home is None:
            return None
        try:
            rel = path.relative_to(self.home)
        except ValueError:
            return None
        first = rel.parts[0] if rel.parts else ""
        return self.people.get(first) if len(rel.parts) > 1 or path.is_dir() else None

    def _from_link(self, text: str) -> Optional[Person]:
        """A person named by a link to their folder or index.md: a wikilink
        (vault-relative) or a markdown link (relative, as attendee lists
        write them: `../personnel/priya/`)."""
        if self.home is None:
            return None
        match = WIKILINK_RE.fullmatch(text.strip())
        if match:
            target = link_target(match.group("target"))
        else:
            md = _MD_LINK.match(text.strip())
            if not md:
                return None
            target = unquote(md.group(1).split("#", 1)[0]).rstrip("/")
        if "/" not in target:
            return None      # a bare [[name]]: resolved by name
        home_rel = self.ws.rel(self.home)
        vault_rel = self.ws.rel(self.ws.vault)
        prefixes = {home_rel}
        if vault_rel and home_rel.startswith(vault_rel + "/"):
            prefixes.add(home_rel[len(vault_rel) + 1:])
        cleaned = target
        while cleaned.startswith("./") or cleaned.startswith("../"):
            cleaned = cleaned[2:] if cleaned.startswith("./") else cleaned[3:]
        for prefix in sorted(prefixes, key=len, reverse=True):
            if cleaned == prefix or cleaned.startswith(prefix + "/"):
                rest = cleaned[len(prefix):].strip("/").split("/")
                if rest and rest[0] in self.people:
                    return self.people[rest[0]]
        return None

    def resolve(self, text: str) -> dict:
        """{text, status: high|ambiguous|none, slug, candidates, reason}."""
        raw = text.strip()
        result = {"text": raw, "status": "none", "slug": None, "candidates": [], "reason": ""}
        if not raw:
            result["reason"] = "empty"
            return result
        linked = self._from_link(raw)
        if linked is not None:
            result.update(status="high", slug=linked.slug, reason="link to the person's folder")
            return result
        match = WIKILINK_RE.fullmatch(raw)
        if match:
            alias = match.group("alias")
            raw = link_target(match.group("target")) if not alias else alias.lstrip("\\|")
            if not alias and "/" in raw:
                result["reason"] = "a link that is not to a person folder"
                return result
        words = words_of(raw.lstrip("@"))
        if not words:
            result["reason"] = "no letters"
            return result
        joined = "-".join(words)
        exact: List[str] = []
        for person in self.people.values():
            slug_words = words_of(person.slug)
            forms = {"-".join(slug_words), "-".join(reversed(slug_words)), "-".join(words_of(person.name))}
            forms |= {"-".join(words_of(alias)) for alias in person.aliases}
            if joined in forms:
                exact.append(person.slug)
        if len(exact) == 1:
            result.update(status="high", slug=exact[0], reason="slug, name or alias")
            return result
        if len(exact) > 1:
            result.update(status="ambiguous", candidates=sorted(exact), reason="matches more than one person")
            return result
        if len(words) == 1:
            word = words[0]
            first = [p.slug for p in self.people.values()
                     if words_of(p.name)[:1] == [word] or words_of(p.slug)[:1] == [word]]
            last = [p.slug for p in self.people.values()
                    if (len(words_of(p.name)) > 1 and words_of(p.name)[-1] == word)
                    or (len(words_of(p.slug)) > 1 and words_of(p.slug)[-1] == word)]
            if len(first) == 1 and not [s for s in last if s != first[0]]:
                result.update(status="high", slug=first[0], reason="a first name only one person has")
                return result
            candidates = sorted(set(first) | set(last))
            if candidates:
                why = "first name shared by several people" if len(first) > 1 else "last name only"
                result.update(status="ambiguous", candidates=candidates, reason=why)
                return result
            result["reason"] = "no person folder matches"
            return result
        # Several words that are not exactly anyone: report people sharing the
        # first word, but never pick one.
        near = sorted(p.slug for p in self.people.values() if words_of(p.name)[:1] == words[:1])
        result.update(candidates=near, reason="no exact match" + (" (same first name: see candidates)" if near else ""))
        return result

    # ---------------------------------------------------------------- writing
    def ensure_index(self, person: Person, dry_run: bool) -> bool:
        """Create a stub index.md in an existing person folder. True if created."""
        if person.index.exists() or person.index.is_symlink():
            return False
        if not dry_run:
            write_text_atomic(person.index, stub_text(person.name))
        return True


def stub_text(name: str) -> str:
    return "\n".join([
        "---",
        "type: person",
        "name: %s" % frontmatter.scalar(name),
        'role: ""',
        'org: ""',
        "aliases: []",
        "tags: [person]",
        "---",
        "",
        "# %s" % name,
        "",
    ])


def registry(ws: Workspace) -> Registry:
    return Registry(ws)


def require_home(reg: Registry) -> None:
    if reg.home is None:
        raise ToolError(
            "no people folder: tag one Repo Map folder `people-home` (or create knowledge/personnel/)",
            EXIT_NOT_READY,
        )


def add_alias(ws: Workspace, slug: str, alias: str, dry_run: bool = False) -> dict:
    """Record a name the user has said means this person (a nickname, a
    maiden name, an initialism)."""
    reg = registry(ws)
    require_home(reg)
    person = reg.people.get(slug)
    if person is None:
        raise ToolError("no person folder %r under %s" % (slug, ws.rel(reg.home)), EXIT_USAGE)
    alias = " ".join(alias.split())
    if not words_of(alias):
        raise ToolError("the alias needs letters or digits", EXIT_USAGE)
    clash = reg.resolve(alias)
    if clash["status"] == "high" and clash["slug"] != slug:
        raise ToolError("%r already means %s (%s); not adding it to %s" % (alias, clash["slug"], clash["reason"], slug),
                        EXIT_USAGE)
    result = {"slug": slug, "alias": alias, "action": "noop", "index": ws.rel(person.index), "problem": None,
              "dry_run": dry_run}
    created = reg.ensure_index(person, dry_run)
    if dry_run and created:
        result["action"] = "added"
        return result
    try:
        text = read_text(person.index)
    except (NotText, OSError) as exc:
        result.update(action="skipped", problem=str(exc))
        return result
    if has_bare_cr(text):
        result.update(action="skipped", problem="index.md uses bare carriage returns as line endings")
        return result
    lines = split_lines(text)
    fm = frontmatter.parse(lines)
    newline = detect_newline(text)
    if not fm.present:
        new_lines = frontmatter.prepend_block(lines, [("aliases", frontmatter.flow_list([alias]))], newline)
        status = "added"
    elif fm.error:
        result.update(action="skipped", problem="index.md frontmatter: %s" % fm.error)
        return result
    else:
        new_lines, status = frontmatter.merge_list_item(lines, fm, "aliases", alias, newline)
    if status == "uneditable":
        result.update(action="skipped", problem="`aliases` in index.md is not a simple list")
        return result
    if status == "present":
        return result
    if frontmatter.parse(new_lines).error:
        result.update(action="skipped", problem="the edit would not leave readable frontmatter")
        return result
    if not dry_run:
        try:
            write_text_atomic(person.index, "".join(new_lines))
        except OSError as exc:
            result.update(action="skipped", problem="could not write: %s" % exc)
            return result
    result["action"] = "created-index" if created else "added"
    return result
