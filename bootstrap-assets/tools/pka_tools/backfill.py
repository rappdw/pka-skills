"""Timeline backfill: put the notes a vault already has on people's timelines.

Plan, then apply. Planning reads the vault and writes two files: a review
report (`owner-inbox/timeline-backfill-plan-<date>.md`) and the exact lines
to be written (`.pka/backfill/plan-<id>.json`). It changes nothing else and
can be run as often as you like.

Applying a plan:
  - refuses when any person's index.md changed since the plan was made;
  - copies every file it will touch to `.pka/backups/<id>/`;
  - adds timeline lines only, through the same code `timeline add` uses, so
    existing lines and anything else in index.md are never rewritten;
  - verifies that every planned line is present, that every link resolves,
    and that no file outside the planned index.md files changed (a hash of
    every file in the workspace, before and after). A failed verification
    puts the backup back;
  - in a hybrid monorepo, makes one commit with exactly those files.

`restore` puts a backup back. It refuses a file that changed after the
apply unless told to overwrite it.

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
    NotText, detect_newline, line_body, read_text, sha256_file, split_lines, write_text_atomic,
)
from .workspace import MOC_NAME, Workspace

PLAN_VERSION = 1
BACKLINK_SECTIONS = ("mentioned in", "related meetings", "inbound references", "references")
NOTE_SUFFIXES = (".md", ".markdown", ".pdf", ".docx", ".doc", ".pptx", ".xlsx")
SAMPLE_SIZE = 20
FREQUENT_UNMATCHED = 3
_SKIP_IN_MANIFEST = (".pka/backups/", ".pka/backfill/")


def _stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


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
            for key in tl.keys_in(ws, person.index, line_body(line)):
                key = tl.resolve_bare(ws, key, cache)
                out.setdefault(key, {}).setdefault(person.slug, section)
    return out


def _in_wiki(path: Path, vault: Path) -> bool:
    """Inside a wiki page's folder (a folder holding `wiki.md`)."""
    probe = path.parent
    while probe == vault or vault in probe.parents:
        if (probe / "wiki.md").is_file():
            return True
        if probe == vault:
            break
        probe = probe.parent
    return False


def candidates(ws: Workspace, reg: Registry) -> List[Path]:
    """The files a backfill considers: notes and documents in the vault,
    not MOCs, person pages, wiki pages or capture directories."""
    out = []
    person_pages = {p.index for p in reg.people.values()}
    for path in ws.walk(ws.vault, captures=False):
        if path.suffix.lower() not in NOTE_SUFFIXES:
            continue
        if path.name == MOC_NAME or path in person_pages or path.name == "wiki.md":
            continue
        if _in_wiki(path, ws.vault):
            continue
        out.append(path)
    return out


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

    # What each person's page can take, and what is on it already.
    pages: Dict[str, dict] = {}
    for p in reg.people.values():
        problem, text, created = tl.prepare_index(p)
        present: Set[str] = set()
        if text is not None and not created:
            lines = split_lines(text)
            present = set(tl.block_keys(ws, p.index, lines, tl.locate(lines)))
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
        for slug in sorted(people):
            page = pages[slug]
            if key in page["present"]:
                already += 1
                continue
            p = page["person"]
            link = tl.format_link(ws, p.index, path, label, obsidian)
            entries.append({
                "slug": slug, "index": ws.rel(p.index), "note": rel, "key": key, "date": date, "kind": kind,
                "tier": people[slug]["tier"], "evidence": people[slug]["evidence"],
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
        folder = ws.pka / "backfill"
        folder.mkdir(parents=True, exist_ok=True)
        plan_file = folder / ("plan-%s.json" % plan_id)
        report_dir = ws.root / "owner-inbox"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / ("timeline-backfill-plan-%s.md" % plan_id[:8])
        result["plan_file"] = ws.rel(plan_file)
        result["report_file"] = ws.rel(report_file)
        write_text_atomic(plan_file, json.dumps(result, indent=1, ensure_ascii=False) + "\n")
        write_text_atomic(report_file, report(result))
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
        section("Paths a wikilink cannot express (not added)", ["- `%s`" % n for n in result["unlinkable"]])
    return "\n".join(out) + "\n"


# ------------------------------------------------------------ apply

def manifest(ws: Workspace) -> Dict[str, str]:
    """sha256 of every regular file in the workspace (not `.git`, not the
    backfill's own folders, not symbolic links)."""
    out = {}
    for folder, dirs, names in os.walk(str(ws.root)):
        dirs[:] = sorted(d for d in dirs if d != ".git" and not os.path.islink(os.path.join(folder, d)))
        for name in names:
            path = os.path.join(folder, name)
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            rel = os.path.relpath(path, str(ws.root)).replace(os.sep, "/")
            if rel.startswith(_SKIP_IN_MANIFEST):
                continue
            try:
                out[rel] = sha256_file(Path(path))
            except OSError:
                out[rel] = "unreadable"
    return out


def load_plan(ws: Workspace, plan_arg: str) -> dict:
    path = ws.resolve(plan_arg)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ToolError("no such plan: %s" % plan_arg, EXIT_USAGE)
    except (ValueError, OSError) as exc:
        raise ToolError("the plan cannot be read: %s" % exc, EXIT_USAGE)
    if not isinstance(data, dict) or data.get("version") != PLAN_VERSION or not isinstance(data.get("entries"), list):
        raise ToolError("%s is not a version-%d backfill plan" % (plan_arg, PLAN_VERSION), EXIT_USAGE)
    return data


def _current_hash(path: Path) -> Optional[str]:
    if path.is_symlink() or not path.exists():
        return None
    return sha256_file(path)


def apply(ws: Workspace, plan_arg: str, dry_run: bool = False, commit: bool = True) -> dict:
    data = load_plan(ws, plan_arg)
    reg = registry(ws)
    require_home(reg)
    if bool(data.get("obsidian")) != ws.obsidian_present:
        raise ToolError("the plan was made %s Obsidian and the workspace is now %s; plan again"
                        % ("with" if data.get("obsidian") else "without",
                           "an Obsidian vault" if ws.obsidian_present else "not one"), EXIT_NOT_READY)
    targets: Dict[str, dict] = data["targets"]
    changed_since = [rel for rel, t in targets.items() if _current_hash(ws.root / rel) != t["sha256"]]
    if changed_since:
        raise ToolError("these files changed since the plan was made; plan again: %s" % ", ".join(sorted(changed_since)),
                        EXIT_NOT_READY)
    by_index: Dict[str, List[dict]] = {}
    for entry in data["entries"]:
        if entry["index"] not in targets:
            raise ToolError("the plan is inconsistent: %s is not among its targets" % entry["index"], EXIT_USAGE)
        by_index.setdefault(entry["index"], []).append(entry)
    result = {"plan": ws.rel(ws.resolve(plan_arg)), "entries": len(data["entries"]), "files": sorted(by_index),
              "backup": None, "verified": False, "problems": [], "commit": None, "dry_run": dry_run}
    if dry_run or not data["entries"]:
        return result

    backup_id = _stamp()
    backup = ws.pka / "backups" / backup_id
    before = manifest(ws)
    files_dir = backup / "files"
    record = {"version": PLAN_VERSION, "plan": result["plan"], "created": _dt.datetime.now().isoformat(timespec="seconds"),
              "files": {}}
    for rel in sorted(by_index):
        src = ws.root / rel
        existed = src.exists()
        if existed:
            dest = files_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dest))
        record["files"][rel] = {"existed": existed, "before": targets[rel]["sha256"], "after": None}
    write_text_atomic(backup / "backup.json", json.dumps(record, indent=1) + "\n")
    result["backup"] = ws.rel(backup)

    problems: List[str] = []
    for rel, items in sorted(by_index.items()):
        person = reg.get(targets[rel]["slug"])
        if person is None or ws.rel(person.index) != rel:
            problems.append("%s: the person folder is gone" % rel)
            continue
        problem, text, _created = tl.prepare_index(person)
        if problem:
            problems.append("%s: %s" % (rel, problem))
            continue
        newline = detect_newline(text)
        lines = split_lines(text)
        present = set(tl.block_keys(ws, person.index, lines, tl.locate(lines)))
        for entry in sorted(items, key=lambda e: e["date"], reverse=True):
            if entry["key"] in present:
                continue
            lines = tl.place(ws, person.index, lines, entry["line"], entry["date"], newline)
            present.add(entry["key"])
        try:
            write_text_atomic(person.index, "".join(lines))
        except OSError as exc:
            problems.append("%s: could not write: %s" % (rel, exc))

    # Verify: every planned line is there, every link resolves, nothing else changed.
    if not problems:
        from .pointers import resolve_link
        for rel, items in sorted(by_index.items()):
            index = ws.root / rel
            lines = split_lines(read_text(index))
            keys = set(tl.block_keys(ws, index, lines, tl.locate(lines)))
            for entry in items:
                if entry["key"] not in keys:
                    problems.append("%s: the line for %s is missing" % (rel, entry["note"]))
                elif resolve_link(ws, entry["key"]) is None:
                    problems.append("%s: the link to %s does not resolve" % (rel, entry["note"]))
        after = manifest(ws)
        unexpected = sorted(rel for rel in set(before) | set(after)
                            if before.get(rel) != after.get(rel) and rel not in by_index)
        problems += ["changed although it is not in the plan: %s" % rel for rel in unexpected]

    if problems:
        put_back(ws, backup, record)
        result["problems"] = problems
        result["restored"] = True
        return result

    for rel in record["files"]:
        record["files"][rel]["after"] = sha256_file(ws.root / rel)
    write_text_atomic(backup / "backup.json", json.dumps(record, indent=1) + "\n")
    result["verified"] = True

    if commit and ws.hybrid_monorepo_present:
        from . import gitops
        people = len(by_index)
        subject = "Timelines: backfill %d entr%s for %d %s" % (
            len(data["entries"]), "y" if len(data["entries"]) == 1 else "ies", people, "person" if people == 1 else "people")
        try:
            result["commit"] = gitops.commit(ws, subject, sorted(by_index),
                                             body="Plan %s. Backup in %s." % (result["plan"], result["backup"]))
        except ToolError as exc:
            result["commit"] = {"committed": False, "reason": exc.message}
    return result


def put_back(ws: Workspace, backup: Path, record: dict, only: Optional[List[str]] = None) -> List[str]:
    done = []
    for rel, info in sorted(record["files"].items()):
        if only is not None and rel not in only:
            continue
        target = ws.root / rel
        saved = backup / "files" / rel
        if info["existed"]:
            data = saved.read_bytes()
            tmp = target.with_name(target.name + ".pka-restore")
            tmp.write_bytes(data)
            shutil.copystat(str(saved), str(tmp))
            os.replace(str(tmp), str(target))
        elif target.exists() and not target.is_symlink():
            os.remove(str(target))
        done.append(rel)
    return done


def restore(ws: Workspace, backup_arg: str, force: bool = False, dry_run: bool = False) -> dict:
    """Put a backfill backup back: the person pages as they were before the
    apply. Refuses files changed since the apply, unless `force`."""
    backup = ws.pka / "backups" / backup_arg if "/" not in backup_arg else ws.resolve(backup_arg)
    try:
        record = json.loads((backup / "backup.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ToolError("no backfill backup %s (they are in .pka/backups/)" % backup_arg, EXIT_USAGE)
    except (ValueError, OSError) as exc:
        raise ToolError("the backup record cannot be read: %s" % exc, EXIT_USAGE)
    conflicts = []
    for rel, info in sorted(record["files"].items()):
        now = _current_hash(ws.root / rel)
        if info.get("after") is not None and now != info["after"] and now != info["before"]:
            conflicts.append(rel)
    if conflicts and not force:
        raise ToolError("changed since the backfill (edits would be lost; --force to restore anyway): %s"
                        % ", ".join(conflicts), EXIT_NOT_READY)
    pending = [rel for rel, info in sorted(record["files"].items())
               if _current_hash(ws.root / rel) != info["before"]]
    result = {"backup": ws.rel(backup), "restored": [], "unchanged": sorted(set(record["files"]) - set(pending)),
              "conflicts": conflicts, "dry_run": dry_run}
    if dry_run:
        result["restored"] = pending
        return result
    result["restored"] = put_back(ws, backup, record, only=pending)
    return result
