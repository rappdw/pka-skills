"""Timeline backfill: put the notes a workspace already has on people's timelines.

Plan, then apply. Planning reads the notes and writes two files: a review
report (`owner-inbox/timeline-backfill-plan-<id>.md`) and the exact lines to
be written (`.pka/backfill/plan-<id>.json`). It changes nothing else and can
be run as often as you like. A note whose name a link cannot carry is
reported, not planned.

Applying a plan:
  - checks the plan file itself (it is data and may have been edited):
    every target must be the page of a person folder, every line a timeline
    line linking to its note;
  - refuses when a person page or a planned note changed since the plan;
  - copies every page it will touch to `.pka/backups/<id>/`, and records
    each page's new hash before writing it;
  - adds timeline lines only, through the same code `timeline add` uses;
  - verifies that every planned line is present, every link resolves, and
    no other file a timeline can link to changed. A failed check, an exception or an
    interrupt puts every page back;
  - commits nothing: the changed pages are left for the user to review and
    commit.

`restore` puts a backup back. It refuses a page that changed after the
apply, or whose state after it was never recorded, unless forced; and a
backup that was rolled back.

Notes are never modified. Who goes on a timeline is decided as for a newly
filed note (`timeline.who`), plus one more source of evidence: a link in the
old back-link sections of a person's own page (`## Mentioned in`,
`## Related meetings`, `## Inbound References`, `## References`), which
earlier versions wrote by hand.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import random
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Set

from . import timeline as tl
from .actions import parse_date
from .errors import EXIT_FAIL, EXIT_NOT_READY, EXIT_USAGE, ToolError
from .markdown import block_mask, heading_of
from .people import INDEX, Person, Registry, registry, require_home
from .textio import (
    GeneratedRefused, NotText, detect_newline, generated_problem, line_body, read_text, sha256_file, split_lines,
    write_generated, write_text_atomic,
)
from .workspace import MOC_NAME, UNFILED_ROOTS, Workspace

PLAN_VERSION = 1
BACKLINK_SECTIONS = ("mentioned in", "related meetings", "inbound references", "references")
NOTE_SUFFIXES = (".md", ".markdown", ".pdf", ".docx", ".doc", ".pptx", ".xlsx")
SAMPLE_SIZE = 20
FREQUENT_UNMATCHED = 3
_SKIP_IN_MANIFEST = (".pka/backups/", ".pka/backfill/")


def _stamp() -> str:
    """A sortable id that two runs in the same second never share."""
    return "%s-%s" % (_dt.datetime.now().strftime("%Y%m%d-%H%M%S"), os.urandom(3).hex())


# ------------------------------------------------------------ evidence

def backlinks(ws: Workspace, reg: Registry) -> Dict[str, Dict[str, str]]:
    """note key -> {slug: section} for links in the old back-link sections
    of each person's own index.md."""
    out: Dict[str, Dict[str, str]] = {}
    cache: dict = {}
    for person in reg.people.values():
        if not person.index.is_file() or person.index.is_symlink():
            continue
        try:
            lines = split_lines(read_text(person.index))
        except (NotText, OSError):
            continue
        mask = block_mask(lines)
        section = None
        for idx, line in enumerate(lines):
            if mask[idx]:
                continue
            found = heading_of(line)
            if found:
                if found[0] <= 2:
                    section = found[1].strip() if found[1].strip().lower() in BACKLINK_SECTIONS else None
                continue
            if section is None:
                continue
            for key in tl.keys_in(ws, person.index, line_body(line), cache):
                key = tl.resolve_bare(ws, key, cache)
                out.setdefault(key, {}).setdefault(person.slug, section)
    return out


def _in_wiki(path: Path, vault: Path) -> bool:
    """Wiki material: a file in a wiki page's own folder (one holding
    `wiki.md`, below the vault root) or in its `sources/` folder."""
    folder = path.parent
    if folder.name == "sources":
        folder = folder.parent
    return folder != vault and vault in folder.parents and (folder / "wiki.md").is_file()


def candidates(ws: Workspace, reg: Registry) -> List[Path]:
    """The files a backfill considers: notes and documents a timeline can
    link to (the vault in an Obsidian workspace, else the whole workspace
    but the inboxes), not MOCs, person pages, wiki pages, capture
    directories or anything under `node_modules/`."""
    out = []
    person_pages = {p.index for p in reg.people.values()}
    for path in ws.walk(ws.link_root, captures=False):
        if path.suffix.lower() not in NOTE_SUFFIXES:
            continue
        if ws.link_scope_problem(path) or "node_modules" in path.relative_to(ws.root).parts:
            continue
        if path.name == MOC_NAME or path in person_pages or path.name == "wiki.md":
            continue
        if _in_wiki(path, ws.vault):
            continue
        out.append(path)
    return out


def _link_reads_back(ws: Workspace, index: Path, link: str, key: str, path: Path, cache: dict) -> bool:
    """The link, as it will be written, is read back as this note and
    resolves to this very file, by the name it has. A name that cannot
    survive the round trip (an upper-case `.MD`, angle brackets without
    Obsidian) is left out. Compared by name, not by what the filesystem
    opens: on a case-insensitive one (macOS) `Sync.md` opens `Sync.MD`, but
    `timeline apply` and `check` would not agree it is the same note."""
    found = tl.keys_in(ws, index, link, cache)
    if not found or tl.resolve_bare(ws, found[0], cache) != key:
        return False
    target = tl.note_file(ws, key)
    return target is not None and ws.rel(target) == ws.rel(path)


# ------------------------------------------------------------ plan

def plan(
    ws: Workspace,
    since: Optional[str] = None,
    person: Optional[str] = None,
    include_large: bool = False,
    write: bool = True,
    seed: Optional[int] = None,
) -> dict:
    reg = registry(ws)
    require_home(reg)
    if since is not None:
        parse_date(since, "--since")
    only = None
    if person is not None:
        found = reg.get(person)
        if found is None:
            raise ToolError("no person folder %r" % person, EXIT_USAGE)
        only = found.slug
    plan_id = _stamp()
    obsidian = ws.obsidian_present
    back = backlinks(ws, reg)
    cache: dict = {}

    # What each person's page can take, and what is on it already.
    pages: Dict[str, dict] = {}
    for p in reg.people.values():
        problem, text, created = tl.prepare_index(p)
        present: Set[str] = set()
        if text is not None and not created:
            lines = split_lines(text)
            present = set(tl.block_keys(ws, p.index, lines, tl.locate(lines), cache))
        pages[p.slug] = {"person": p, "problem": problem, "created": created, "present": present,
                         "sha256": None if created or not p.index.is_file() else sha256_file(p.index)}

    entries: List[dict] = []
    already = 0
    undated: List[dict] = []
    large: List[dict] = []
    opted_out: List[str] = []
    unlinkable: List[str] = []
    ambiguous: Dict[str, dict] = {}
    unmatched: Dict[str, Set[str]] = {}
    files = candidates(ws, reg)
    for path in files:
        note = tl.Note(ws, path)
        rel = ws.rel(path)
        verdict = tl.who(ws, reg, note, include_large=include_large)
        if verdict.get("opted_out"):
            opted_out.append(rel)
            continue
        key = tl.note_key(ws, path)
        people = {p["slug"]: {"tier": p["tier"], "evidence": list(p["evidence"])} for p in verdict["people"]}
        for slug, section in back.get(key, {}).items():
            people.setdefault(slug, {"tier": "T2", "evidence": []})
            people[slug]["evidence"].append("T2: listed under ## %s on their page" % section)
        for item in verdict["ambiguous"]:
            slot = ambiguous.setdefault(item["text"], {"candidates": item["candidates"], "notes": set()})
            slot["notes"].add(rel)
        for name in verdict["unresolved"]:
            unmatched.setdefault(name, set()).add(rel)
        if verdict["large_skipped"]:
            large.append({"note": rel, "attendees": verdict["attendees"]})
        if only is not None:
            people = {s: v for s, v in people.items() if s == only}
        if not people:
            continue
        date = note.date()
        if not date:
            undated.append({"note": rel, "people": sorted(people)})
            continue
        if since is not None and date < since:
            continue
        if obsidian and tl._UNLINKABLE & set(key):
            unlinkable.append(rel)
            continue
        kind = note.kind(reg)
        label = note.label(kind)
        note_hash = sha256_file(path)
        for slug in sorted(people):
            page = pages[slug]
            if key in page["present"]:
                already += 1
                continue
            p = page["person"]
            link = tl.format_link(ws, p.index, path, label, obsidian)
            if not _link_reads_back(ws, p.index, link, key, path, cache):
                if rel not in unlinkable:
                    unlinkable.append(rel)
                continue
            entries.append({
                "slug": slug, "index": ws.rel(p.index), "note": rel, "note_sha256": note_hash, "key": key,
                "date": date, "kind": kind, "tier": people[slug]["tier"], "evidence": people[slug]["evidence"],
                "line": tl.format_line(date, kind, link, ""),
            })

    blocked = sorted({e["slug"] for e in entries if pages[e["slug"]]["problem"]})
    skipped_people = [{"slug": s, "index": ws.rel(pages[s]["person"].index), "problem": pages[s]["problem"],
                       "entries": sum(1 for e in entries if e["slug"] == s)} for s in blocked]
    entries = [e for e in entries if not pages[e["slug"]]["problem"]]
    entries.sort(key=lambda e: (e["slug"], e["date"], e["note"]), reverse=False)
    touched = sorted({e["slug"] for e in entries})
    targets = {ws.rel(pages[s]["person"].index): {"slug": s, "sha256": pages[s]["sha256"],
                                                    "created": pages[s]["created"]} for s in touched}
    stubs = sorted(rel for rel, t in targets.items() if t["created"])

    per_person = []
    for slug in sorted(reg.people):
        mine = [e for e in entries if e["slug"] == slug]
        per_person.append({"slug": slug, "entries": len(mine), "present": len(pages[slug]["present"]),
                           "first": min((e["date"] for e in mine), default=None),
                           "last": max((e["date"] for e in mine), default=None)})
    rng = random.Random(seed if seed is not None else plan_id)
    sample = rng.sample(entries, min(SAMPLE_SIZE, len(entries))) if entries else []
    result = {
        "version": PLAN_VERSION, "id": plan_id, "created": _dt.datetime.now().isoformat(timespec="seconds"),
        "options": {"since": since, "person": only, "include_large": include_large},
        "obsidian": obsidian, "files_considered": len(files), "already_present": already,
        "entries": entries, "targets": targets, "stubs": stubs, "people": per_person,
        "people_skipped": skipped_people, "undated": undated, "large_meetings": large,
        "opted_out": opted_out, "unlinkable": unlinkable,
        "ambiguous": sorted(({"text": t, "candidates": v["candidates"], "notes": len(v["notes"])}
                             for t, v in ambiguous.items()), key=lambda a: (-a["notes"], a["text"])),
        "unmatched": sorted(({"text": t, "notes": len(v)} for t, v in unmatched.items()
                             if len(v) >= FREQUENT_UNMATCHED), key=lambda a: (-a["notes"], a["text"])),
        "sample": sample, "plan_file": None, "report_file": None,
    }
    if write:
        plan_file = ws.pka / "backfill" / ("plan-%s.json" % plan_id)
        report_file = ws.root / "owner-inbox" / ("timeline-backfill-plan-%s.md" % plan_id)
        # Generated files never go through a link (a linked owner-inbox/ or
        # .pka/backfill/ would send them somewhere else): check both first.
        for target in (plan_file, report_file):
            problem = generated_problem(ws.root, target)
            if problem:
                raise ToolError("%s; the plan was not written." % problem, EXIT_FAIL)
        result["plan_file"] = ws.rel(plan_file)
        result["report_file"] = ws.rel(report_file)
        try:
            write_generated(ws.root, plan_file, json.dumps(result, indent=1, ensure_ascii=False) + "\n")
            write_generated(ws.root, report_file, report(result))
        except GeneratedRefused as exc:
            raise ToolError("%s; the plan was not written." % exc, EXIT_FAIL)
    return result


def report(result: dict) -> str:
    out = ["# Timeline backfill plan %s" % result["id"], ""]
    out.append("Plan file: `%s`. Nothing has been written to any timeline yet. Review this report, add aliases "
               "(`pka-tools people alias`) or person folders where it helps, and plan again; planning is cheap. "
               "Then: `pka-tools timeline apply %s`." % (result["plan_file"], result["plan_file"]))
    out.append("")
    opts = result["options"]
    scope = []
    if opts["since"]:
        scope.append("notes dated %s or later" % opts["since"])
    if opts["person"]:
        scope.append("only %s" % opts["person"])
    if opts["include_large"]:
        scope.append("large meetings included")
    out.append("- Files considered: %d%s" % (result["files_considered"], (" (" + "; ".join(scope) + ")") if scope else ""))
    out.append("- Lines to add: %d, on %d people's timelines" % (len(result["entries"]), len(result["targets"])))
    out.append("- Already on a timeline: %d" % result["already_present"])
    out.append("- index.md stubs to create: %d" % len(result["stubs"]))
    out.append("")
    out.append("## Entries per person")
    out.append("")
    out.append("| Person | To add | Already there | First | Last |")
    out.append("|---|---|---|---|---|")
    for p in result["people"]:
        out.append("| %s | %d | %d | %s | %s |" % (p["slug"], p["entries"], p["present"], p["first"] or "", p["last"] or ""))
    people_without = [p["slug"] for p in result["people"] if not p["entries"] and not p["present"]]
    if people_without:
        out += ["", "People with no entries: %s." % ", ".join(people_without)]

    def section(title: str, rows: List[str], empty: str = "None.") -> None:
        out.extend(["", "## %s" % title, ""])
        out.extend(rows or [empty])

    section("Sample of %d entries" % len(result["sample"]),
            ["- `%s` → %s (%s)" % (e["note"], e["slug"], "; ".join(e["evidence"]))
             for e in result["sample"]])
    section("Ambiguous names (not added)",
            ["- %r: %s (%d note%s)" % (a["text"], ", ".join(a["candidates"]), a["notes"], "" if a["notes"] == 1 else "s")
             for a in result["ambiguous"]])
    section("Names with no person folder, in %d or more notes" % FREQUENT_UNMATCHED,
            ["- %r: %d notes (an alias for someone, or a new person folder?)" % (u["text"], u["notes"])
             for u in result["unmatched"]])
    section("Undated notes (not added; give them a YYYY-MM-DD filename prefix or a `date`)",
            ["- `%s` → %s" % (u["note"], ", ".join(u["people"])) for u in result["undated"]])
    section("Large meetings (attendees not added; plan with --include-large to add them)",
            ["- `%s` (%d attendees)" % (m["note"], m["attendees"]) for m in result["large_meetings"]])
    section("People whose page cannot be written (their entries are left out)",
            ["- %s (`%s`): %s, %d entries" % (s["slug"], s["index"], s["problem"], s["entries"])
             for s in result["people_skipped"]])
    section("index.md stubs to create", ["- `%s`" % s for s in result["stubs"]])
    if result["opted_out"]:
        section("Opted out (`no-backref: true`)", ["- `%s`" % n for n in result["opted_out"]])
    if result["unlinkable"]:
        section("Notes whose name a link cannot carry (not added; rename them to add them)", ["- `%s`" % n for n in result["unlinkable"]])
    return "\n".join(out) + "\n"


# ------------------------------------------------------------ apply

def manifest(ws: Workspace) -> Dict[str, str]:
    """sha256 of every regular file a timeline can link to (see
    `candidates`), not in dot-folders (`.obsidian`, `.git`, `.trash`:
    editors and sync rewrite those at will), not in the inboxes (the plan's
    report lives there) and not symbolic links. Apply writes only person
    pages, so this is the scope its "nothing else changed" check needs."""
    out = {}
    top = str(ws.link_root)
    for folder, dirs, names in os.walk(top):
        skip = UNFILED_ROOTS if folder == top and ws.link_root == ws.root else ()
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in skip
                         and not os.path.islink(os.path.join(folder, d)))
        for name in names:
            path = os.path.join(folder, name)
            if name.startswith(".") or os.path.islink(path) or not os.path.isfile(path):
                continue
            rel = os.path.relpath(path, str(ws.root)).replace(os.sep, "/")
            try:
                out[rel] = sha256_file(Path(path))
            except OSError:
                out[rel] = "unreadable"
    return out


def _bad_plan(what: str) -> ToolError:
    return ToolError("the plan is not usable: %s; make a new one with `timeline plan`" % what, EXIT_USAGE)


def load_plan(ws: Workspace, plan_arg: str) -> dict:
    path = ws.resolve(plan_arg)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ToolError("no such plan: %s" % plan_arg, EXIT_USAGE)
    except (ValueError, OSError, UnicodeDecodeError) as exc:
        raise ToolError("the plan cannot be read: %s" % exc, EXIT_USAGE)
    if not isinstance(data, dict) or data.get("version") != PLAN_VERSION:
        raise ToolError("%s is not a version-%d backfill plan" % (plan_arg, PLAN_VERSION), EXIT_USAGE)
    targets, entries = data.get("targets"), data.get("entries")
    if not isinstance(targets, dict) or not isinstance(entries, list):
        raise _bad_plan("it has no targets or entries")
    for rel, target in targets.items():
        if not (isinstance(rel, str) and isinstance(target, dict) and isinstance(target.get("slug"), str)
                and (target.get("sha256") is None or isinstance(target.get("sha256"), str))):
            raise _bad_plan("target %r is malformed" % (rel,))
    for entry in entries:
        fields = ("slug", "index", "note", "note_sha256", "key", "date", "kind", "line")
        if not isinstance(entry, dict) or not all(isinstance(entry.get(f), str) for f in fields):
            raise _bad_plan("an entry is missing one of %s" % ", ".join(fields))
    return data


def _current_hash(path: Path) -> Optional[str]:
    if path.is_symlink() or not path.exists():
        return None
    return sha256_file(path)


def _check_plan(ws: Workspace, reg: Registry, data: dict) -> Dict[str, Person]:
    """Every target is a person page of this registry and every entry a
    well-formed line for an existing note a timeline can link to, before
    any file is read or written. A plan file is data; it may have been edited."""
    pages: Dict[str, Person] = {}
    for rel, target in data["targets"].items():
        person = reg.get(target["slug"])
        if person is None or ws.rel(person.index) != rel:
            raise _bad_plan("%s is not the page of a person folder %r" % (rel, target["slug"]))
        pages[rel] = person
    cache: dict = {}
    for entry in data["entries"]:
        person = pages.get(entry["index"])
        if person is None or person.slug != entry["slug"]:
            raise _bad_plan("the entry for %s names a page that is not among its targets" % entry["note"])
        match = tl._LINE_RE.match(entry["line"])
        if not match or match.group("date") != entry["date"] or match.group("kind") not in tl.KINDS:
            raise _bad_plan("the line for %s is not a timeline line" % entry["note"])
        if "\n" in entry["line"] or "\r" in entry["line"]:
            raise _bad_plan("the line for %s spans more than one line" % entry["note"])
        found = tl.keys_in(ws, person.index, match.group("link"), cache)
        if not found or tl.resolve_bare(ws, found[0], cache) != entry["key"]:
            raise _bad_plan("the line for %s does not link to it" % entry["note"])
        note = tl.note_file(ws, entry["key"])
        if note is None or ws.rel(note) != entry["note"] or ws.link_scope_problem(note):
            raise _bad_plan("%s is not a note a timeline can link to" % entry["note"])
    return pages


def _save(backup: Path, record: dict) -> None:
    write_text_atomic(backup / "backup.json", json.dumps(record, indent=1, ensure_ascii=False) + "\n")


def _new_backup(ws: Workspace) -> Path:
    root = ws.pka / "backups"
    problem = generated_problem(ws.root, root / "x")
    if problem:
        raise ToolError("%s; no backup can be kept there, so nothing was applied." % problem, EXIT_FAIL)
    root.mkdir(parents=True, exist_ok=True)
    while True:
        backup = root / _stamp()
        try:
            backup.mkdir()
            return backup
        except FileExistsError:
            continue


def apply(ws: Workspace, plan_arg: str, dry_run: bool = False) -> dict:
    data = load_plan(ws, plan_arg)
    reg = registry(ws)
    require_home(reg)
    if bool(data.get("obsidian")) != ws.obsidian_present:
        # First: with and without Obsidian, keys and links mean different things.
        raise ToolError("the plan was made %s Obsidian and the workspace is now %s; plan again"
                        % ("with" if data.get("obsidian") else "without",
                           "an Obsidian vault" if ws.obsidian_present else "not one"), EXIT_NOT_READY)
    pages = _check_plan(ws, reg, data)
    targets: Dict[str, dict] = data["targets"]
    stale = [rel for rel, t in targets.items() if _current_hash(ws.root / rel) != t["sha256"]]
    stale += sorted({e["note"] for e in data["entries"] if _current_hash(ws.root / e["note"]) != e["note_sha256"]})
    if stale:
        raise ToolError("these files changed since the plan was made; plan again: %s" % ", ".join(sorted(set(stale))),
                        EXIT_NOT_READY)
    by_index: Dict[str, List[dict]] = {}
    for entry in data["entries"]:
        by_index.setdefault(entry["index"], []).append(entry)
    result = {"plan": ws.rel(ws.resolve(plan_arg)), "entries": len(data["entries"]), "files": sorted(by_index),
              "backup": None, "verified": False, "problems": [],
              "restored": False, "dry_run": dry_run}
    if dry_run or not data["entries"]:
        return result

    backup = _new_backup(ws)
    before = manifest(ws)
    record = {"version": PLAN_VERSION, "plan": result["plan"], "state": "applying",
              "created": _dt.datetime.now().isoformat(timespec="seconds"), "files": {}}
    for rel in sorted(by_index):
        src = ws.root / rel
        existed = src.exists()
        if existed:
            dest = backup / "files" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dest))
        record["files"][rel] = {"slug": targets[rel]["slug"], "existed": existed,
                                "before": targets[rel]["sha256"], "after": None}
    _save(backup, record)
    result["backup"] = ws.rel(backup)

    problems: List[str] = []
    try:
        for rel, items in sorted(by_index.items()):
            person = pages[rel]
            problem, text, _created = tl.prepare_index(person)
            if problem:
                problems.append("%s: %s" % (rel, problem))
                break
            newline = detect_newline(text)
            lines = split_lines(text)
            present = set(tl.block_keys(ws, person.index, lines, tl.locate(lines)))
            for entry in sorted(items, key=lambda e: e["date"], reverse=True):
                if entry["key"] in present:
                    continue
                lines = tl.place(ws, person.index, lines, entry["line"], entry["date"], newline)
                present.add(entry["key"])
            content = "".join(lines)
            record["files"][rel]["after"] = tl_hash(content)    # recorded before the write: restore can tell ours from theirs
            _save(backup, record)
            write_text_atomic(person.index, content)

        if not problems:
            problems = _verify(ws, by_index, before)
    except BaseException as exc:      # an interrupt or crash: put everything back, then let it propagate
        _roll_back(ws, backup, record)
        if isinstance(exc, Exception) and not isinstance(exc, ToolError):
            raise ToolError("the backfill failed and the pages were put back: %s" % exc, EXIT_FAIL)
        raise

    if problems:
        failed = _roll_back(ws, backup, record)
        result["problems"] = problems + ["could not put back %s: %s" % (rel, why) for rel, why in failed]
        result["restored"] = not failed
        return result

    record["state"] = "applied"
    _save(backup, record)
    result["verified"] = True

    return result


def tl_hash(content: str) -> str:
    from .textio import sha256_bytes
    return sha256_bytes(content.encode("utf-8"))


def _verify(ws: Workspace, by_index: Dict[str, List[dict]], before: Dict[str, str]) -> List[str]:
    """Every planned line is there, every link resolves, nothing else in
    the workspace changed."""
    problems = []
    for rel, items in sorted(by_index.items()):
        index = ws.root / rel
        lines = split_lines(read_text(index))
        keys = set(tl.block_keys(ws, index, lines, tl.locate(lines)))
        for entry in items:
            if entry["key"] not in keys:
                problems.append("%s: the line for %s is missing" % (rel, entry["note"]))
            elif tl.note_file(ws, entry["key"]) is None:
                problems.append("%s: the link to %s does not resolve" % (rel, entry["note"]))
    after = manifest(ws)
    unexpected = sorted(rel for rel in set(before) | set(after)
                        if before.get(rel) != after.get(rel) and rel not in by_index)
    problems += ["changed although it is not in the plan: %s" % rel for rel in unexpected]
    return problems


def _roll_back(ws: Workspace, backup: Path, record: dict) -> List[tuple]:
    failed = put_back(ws, backup, record)[1]
    record["state"] = "rolled-back" if not failed else "rollback-incomplete"
    try:
        _save(backup, record)
    except OSError:
        pass
    return failed


def put_back(ws: Workspace, backup: Path, record: dict, only: Optional[List[str]] = None):
    """Restore the saved pages (and remove stubs the apply created). Every
    file is attempted; returns (restored, [(file, reason)])."""
    done, failed = [], []
    for rel, info in sorted(record["files"].items()):
        if only is not None and rel not in only:
            continue
        target = ws.root / rel
        try:
            if info["existed"]:
                saved = backup / "files" / rel
                data = saved.read_bytes()
                if not target.parent.is_dir():
                    raise OSError("the folder %s no longer exists" % ws.rel(target.parent))
                tmp = target.with_name(target.name + ".pka-restore")
                tmp.write_bytes(data)
                shutil.copystat(str(saved), str(tmp))
                os.replace(str(tmp), str(target))
            elif target.exists() and not target.is_symlink():
                os.remove(str(target))
            done.append(rel)
        except OSError as exc:
            failed.append((rel, str(exc)))
    return done, failed


def restore(ws: Workspace, backup_arg: str, force: bool = False, dry_run: bool = False) -> dict:
    """Put a backfill backup back: the person pages as they were before the
    apply. Refuses a page edited since the apply (or one whose state after
    the apply was never recorded) unless `force`."""
    name = backup_arg.rstrip("/").rsplit("/", 1)[-1]
    if not name or name in (".", ".."):
        raise ToolError("no backfill backup %s" % backup_arg, EXIT_USAGE)
    backup = ws.pka / "backups" / name
    try:
        record = json.loads((backup / "backup.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ToolError("no backfill backup %s (they are in .pka/backups/)" % backup_arg, EXIT_USAGE)
    except (ValueError, OSError, UnicodeDecodeError) as exc:
        raise ToolError("the backup record cannot be read: %s" % exc, EXIT_USAGE)
    if not isinstance(record, dict) or not isinstance(record.get("files"), dict):
        raise ToolError("the backup record is malformed", EXIT_USAGE)
    if record.get("state") == "rolled-back":
        raise ToolError("that backfill was rolled back when it failed; there is nothing to restore", EXIT_NOT_READY)
    reg = registry(ws)
    files = {}
    for rel, info in record["files"].items():
        person = reg.get(info.get("slug", "")) if isinstance(info, dict) else None
        if person is None or ws.rel(person.index) != rel or not isinstance(info.get("existed"), bool):
            raise ToolError("the backup names %s, which is not the page of a person folder; nothing restored" % rel,
                            EXIT_NOT_READY)
        files[rel] = info
    conflicts = []
    for rel, info in sorted(files.items()):
        now = _current_hash(ws.root / rel)
        if now == info["before"]:
            continue
        if info.get("after") is None or now != info["after"]:
            conflicts.append(rel)
    if conflicts and not force:
        raise ToolError("changed since the backfill, or its state after the backfill is unknown (edits would be "
                        "lost; --force to restore anyway): %s" % ", ".join(conflicts), EXIT_NOT_READY)
    pending = [rel for rel, info in sorted(files.items()) if _current_hash(ws.root / rel) != info["before"]]
    result = {"backup": ws.rel(backup), "restored": [], "failed": [], "unchanged": sorted(set(files) - set(pending)),
              "conflicts": conflicts, "dry_run": dry_run}
    if dry_run:
        result["restored"] = pending
        return result
    done, failed = put_back(ws, backup, {"files": files}, only=pending)
    result["restored"] = done
    result["failed"] = [{"file": rel, "reason": why} for rel, why in failed]
    return result
