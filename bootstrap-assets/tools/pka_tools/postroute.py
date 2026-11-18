"""`post-route`: everything that happens to a note after a skill has put it
in place, in one command.

Every skill that files a note (the librarian, pka-meetings, pka-wiki, the
researcher) runs this, so a meeting note gets the same treatment as a routed
document. The steps, in order:

  1. frontmatter   schema keys and the domain tag      (Obsidian vaults only)
  2. moc-link      a `- [[note]]` bullet in its MOC      (Obsidian vaults only)
  3. pointers      a pointer row in its domain MOC(s)   (without Obsidian: only
                                                         into MOCs that exist)
  4. timeline      a line on the timeline of each person the note belongs
                   to (see timeline.py for the evidence rules)
  5. index         the note and every MOC changed above  (index mode only)

A step that cannot do its work reports why and the later steps still run:
filing must never be blocked by bookkeeping.

Nothing is committed. `pka-tools` does not run git: what a route changed is
left in the working tree for the user to commit. In a workspace that still
has the `.meta` file of the removed nested-repository layout, the result says
so in `notes`, because routes there used to end in a commit.
"""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import Dict, List, Optional

from . import db as db_mod
from . import indexer, mocs, obsidian, people, pointers, timeline
from .errors import EXIT_USAGE, ToolError
from .markdown import block_mask, find_heading
from .textio import NotText, read_text, split_lines
from .workspace import CAPTURE_MARKER, MOC_NAME, Workspace

MARKDOWN = (".md", ".markdown")


def _in_capture(ws: Workspace, path: Path) -> bool:
    probe = path.parent
    while probe != ws.root and ws.root in probe.parents:
        if (probe / CAPTURE_MARKER).is_file():
            return True
        probe = probe.parent
    return False


def _in_vault(ws: Workspace, path: Path) -> bool:
    try:
        path.relative_to(ws.vault)
    except ValueError:
        return False
    return ws.vault != ws.root


def run(
    ws: Workspace,
    file_arg: str,
    topic: str = "",
    entities: Optional[List[str]] = None,
    context: str = "",
    section: Optional[str] = None,
    also: Optional[List[str]] = None,
    create_mocs: Optional[bool] = None,
    dry_run: bool = False,
    do_timeline: bool = True,
    timeline_people: Optional[List[str]] = None,
    summary: str = "",
    summary_for: Optional[Dict[str, str]] = None,
    include_large: bool = False,
) -> dict:
    path = ws.resolve(file_arg)
    if not path.is_file():
        raise ToolError("no such file: %s" % file_arg, EXIT_USAGE)
    if path.name == MOC_NAME:
        raise ToolError("a %s is not a filed note" % MOC_NAME, EXIT_USAGE)
    first = ws.rel(path).split("/", 1)[0]
    if first in (".pka", ".git"):
        raise ToolError("%s is not a filed note" % file_arg, EXIT_USAGE)
    if _in_capture(ws, path):
        raise ToolError(
            "%s is inside an earshot capture directory, which is never routed. "
            "Index its narrative with `pka-tools index` instead." % file_arg,
            EXIT_USAGE,
        )
    if topic and not pointers.slugify(topic):
        raise ToolError("--topic %r has no letters or digits to make a slug from" % topic, EXIT_USAGE)
    in_vault = _in_vault(ws, path)
    rel = ws.rel(path)
    if section is not None and in_vault:
        _check_section(ws, path, section)
    reg = people.registry(ws) if (in_vault and do_timeline) else None
    if do_timeline and in_vault:
        for slug in list(timeline_people or []) + list((summary_for or {}).keys()):
            if reg is None or reg.get(slug) is None:
                raise ToolError("no person folder %r for the timeline" % slug, EXIT_USAGE)

    # Validate every --also path now: once step 1 has run, a usage error
    # would leave the note half-processed.
    extra: List[str] = []
    for given in also or []:
        other = ws.resolve(given)
        if other.is_dir() and not other.is_symlink():
            raise ToolError("--also %s is a folder; name the files" % given, EXIT_USAGE)
        extra.append(ws.rel(other))
    notes: List[str] = []
    if (ws.root / ".meta").is_file():
        notes.append("not committed: pka-tools no longer commits (nested-repository support was removed); "
                     "the changed files are left for the user to commit. Do not run git")

    steps: List[Dict[str, object]] = []
    touched: List[str] = []

    def record(step: str, action: str, detail: str = "", changed: Optional[List[str]] = None) -> None:
        changed = changed or []
        steps.append({"step": step, "action": action, "detail": detail, "changed": changed})
        for rel in changed:
            if rel not in touched:
                touched.append(rel)

    # 1. frontmatter
    if not in_vault:
        record("frontmatter", "not-applicable", "outside the vault")
    elif path.suffix.lower() not in MARKDOWN:
        record("frontmatter", "not-applicable", "not a markdown note")
    elif not ws.obsidian_present:
        record("frontmatter", "not-applicable", "not an Obsidian vault")
    else:
        try:
            outcome, detail = obsidian.ensure_note(ws, obsidian.Plan(ws), path, dry_run)
        except (OSError, ToolError) as exc:
            outcome, detail = "skipped", str(exc)
        record("frontmatter", outcome, detail, [rel] if outcome in ("created", "merged") else [])

    # 2. moc-link
    if not in_vault:
        record("moc-link", "not-applicable", "outside the vault")
    elif not ws.obsidian_present and not create_mocs:
        record("moc-link", "not-applicable", "not an Obsidian vault")
    else:
        try:
            result = mocs.add_link(ws, rel, section=section, create=create_mocs, dry_run=dry_run)
            record("moc-link", str(result["action"]), result["problem"] or str(result["moc"]),
                   list(result["changed"]))
        except ToolError as exc:
            if exc.code == EXIT_USAGE and section is not None:
                raise
            record("moc-link", "skipped", exc.message)

    # 3. pointers
    if not in_vault:
        record("pointers", "not-applicable", "outside the vault")
    else:
        try:
            result = pointers.add(ws, rel, topic=topic, entities=entities, context=context,
                                  dry_run=dry_run, create_mocs=create_mocs)
            if result.get("problem"):
                record("pointers", "skipped", str(result["problem"]))
            else:
                actions = ", ".join("%s: %s" % (entry["moc"], entry["problem"] or entry["action"])
                                    for entry in result["mocs"])
                acted = [entry for entry in result["mocs"] if entry["action"] not in ("noop", "no-moc", "skipped")]
                outcome = "written" if acted else (
                    "no MOC, pointer row not written"
                    if result["mocs"] and all(entry["action"] == "no-moc" for entry in result["mocs"])
                    else "noop")
                record("pointers", outcome, actions, list(result["changed"]))
                if result["over_cap"]:
                    steps[-1]["over_cap"] = result["over_cap"]
        except ToolError as exc:
            if exc.code == EXIT_USAGE and topic:
                raise
            record("pointers", "skipped", exc.message)

    # 4. timeline
    if not in_vault:
        record("timeline", "not-applicable", "outside the vault")
    elif not do_timeline:
        record("timeline", "not-requested")
    elif reg is None or reg.home is None:
        record("timeline", "not-applicable", (reg.problem if reg is not None and reg.problem else "no people folder"))
    elif reg.person_of_path(path) is not None and path.name == people.INDEX:
        record("timeline", "not-applicable", "a person's own index")
    else:
        try:
            result = timeline.add(ws, rel, people=timeline_people, summary=summary, summary_for=summary_for,
                                  include_large=include_large, dry_run=dry_run)
        except ToolError as exc:
            record("timeline", "skipped", exc.message)
        else:
            written = [e["slug"] for e in result["people"] if e["action"] in ("added", "created-index")]
            bits = []
            for entry in result["people"]:
                bits.append("%s: %s" % (entry["slug"], entry["problem"] or entry["action"]))
            if result["ambiguous"]:
                bits.append("ambiguous: " + "; ".join("%s (%s)" % (a["text"], ", ".join(a["candidates"]))
                                                       for a in result["ambiguous"]))
            if result["large_skipped"]:
                bits.append("large meeting (%d attendees): attendees not added" % result["attendees"])
            if result.get("opted_out"):
                bits.append("the note has `no-backref: true`")
            failed = [e for e in result["people"] if e["action"] == "skipped"]
            if written:
                action = "written"
            elif failed:
                action = "skipped"
            else:
                action = "noop" if result["people"] else "nobody"
            record("timeline", action, "; ".join(bits), list(result["changed"]))
            steps[-1]["people"] = result["people"]
            steps[-1]["ambiguous"] = result["ambiguous"]
            steps[-1]["unresolved"] = result["unresolved"]

    # 5. index
    if not ws.db_path.is_file():
        record("index", "not-applicable", "markdown-only mode (no index)")
    elif dry_run:
        record("index", "dry-run")
    else:
        try:
            with closing(db_mod.connect(ws)) as conn:
                # `--also` paths are indexed too: naming a removed old location drops its rows.
                report = indexer.run(ws, conn, targets=[rel] + [p for p in touched if p != rel] + extra)
            record("index", "indexed", "%d added, %d updated" % (report["added"], report["updated"]))
        except ToolError as exc:
            record("index", "skipped", exc.message)

    return {
        "file": rel,
        "notes": notes,
        "steps": steps,
        "touched": touched,
        "dry_run": dry_run,
    }


def _check_section(ws: Workspace, path: Path, section: str) -> None:
    """--section must name a `## ` heading of the MOC the link goes to."""
    moc = mocs.target_moc(ws, path)
    if not moc.is_file():
        raise ToolError("--section %r: %s does not exist yet" % (section, ws.rel(moc)), EXIT_USAGE)
    try:
        lines = split_lines(read_text(moc))
    except (NotText, OSError):
        return          # the moc-link step will report it
    if find_heading(lines, block_mask(lines), section, 2) is None:
        raise ToolError("--section %r: no `## %s` heading in %s" % (section, section, ws.rel(moc)), EXIT_USAGE)
