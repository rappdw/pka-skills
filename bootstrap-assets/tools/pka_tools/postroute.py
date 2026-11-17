"""`post-route`: everything that happens to a note after a skill has put it
in place, in one command.

Every skill that files a note (the librarian, pka-meetings, pka-wiki, the
researcher) runs this, so a meeting note gets the same treatment as a routed
document. The steps, in order:

  1. frontmatter   schema keys and the domain tag      (Obsidian vaults only)
  2. moc-link      a `- [[note]]` bullet in its MOC      (Obsidian vaults only)
  3. pointers      a pointer row in its domain MOC(s)   (without Obsidian: only
                                                         into MOCs that exist)
  4. timeline      reserved for the person timeline (v1.7.0)
  5. index         the note and every MOC changed above  (index mode only)
  6. commit        the note and every file changed above, in its child repo
                                                        (hybrid monorepo only)

A step that cannot do its work reports why and the later steps still run:
filing must never be blocked by bookkeeping. Only a refused commit makes the
command fail (exit 1), as `commit` does.
"""
from __future__ import annotations

import os
from contextlib import closing
from pathlib import Path
from typing import Dict, List, Optional

from . import db as db_mod
from . import gitops, indexer, mocs, obsidian, pointers
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


def default_message(ws: Workspace, path: Path, role: str) -> str:
    if _in_vault(ws, path):
        folder = ws.vault_rel(path.parent) if path.parent != ws.vault else ""
        where = (folder + "/") if folder else ws.vault.name + "/"
    else:
        where = ws.rel(path.parent) + "/"
    return "%s: Route %s to %s" % (role, path.name, where)


def run(
    ws: Workspace,
    file_arg: str,
    role: str = "Librarian",
    message: Optional[str] = None,
    body: str = "",
    topic: str = "",
    entities: Optional[List[str]] = None,
    context: str = "",
    section: Optional[str] = None,
    also: Optional[List[str]] = None,
    do_commit: bool = True,
    create_mocs: Optional[bool] = None,
    dry_run: bool = False,
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
    if message is not None and (not message.strip() or "\n" in message):
        raise ToolError("the commit subject must be one non-empty line", EXIT_USAGE)
    if topic and not pointers.slugify(topic):
        raise ToolError("--topic %r has no letters or digits to make a slug from" % topic, EXIT_USAGE)
    in_vault = _in_vault(ws, path)
    rel = ws.rel(path)
    if section is not None and in_vault:
        _check_section(ws, path, section)

    # Validate every --also path now: once step 1 has run, a usage error
    # would leave the note edited and uncommitted.
    committing = do_commit and ws.hybrid_monorepo_present
    note_repo = gitops.toplevel(path.parent) if committing else None
    extra: List[str] = []
    notes: List[str] = []
    for given in also or []:
        other = ws.resolve(given)
        if other.is_dir() and not other.is_symlink():
            raise ToolError("--also %s is a folder; name the files" % given, EXIT_USAGE)
        other_rel = ws.rel(other)
        if committing and note_repo is not None:
            repo = gitops.toplevel(other.parent)
            if repo != note_repo:
                raise ToolError("--also %s is not in the same repository as the note" % given, EXIT_USAGE)
            if not os.path.lexists(str(other)) and not gitops.is_tracked(repo, other):
                if gitops.in_history(repo, other):
                    notes.append("%s: already committed as removed" % other_rel)
                    extra.append(other_rel)       # still re-indexed, not committed
                    continue
                raise ToolError("--also %s: no such file, and git has never tracked it" % given, EXIT_USAGE)
        extra.append(other_rel)
    skip_commit = {item.split(":", 1)[0] for item in notes}

    steps: List[Dict[str, object]] = []
    touched: List[str] = []

    def record(step: str, action: str, detail: str = "", changed: Optional[List[str]] = None) -> None:
        changed = changed or []
        steps.append({"step": step, "action": action, "detail": detail, "changed": changed})
        for rel in changed:
            if rel not in touched:
                touched.append(rel)

    related: List[str] = []       # MOCs that point at the note (for leftovers of earlier runs)

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
            related.append(str(result["moc"]))
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
                summary = "written" if acted else (
                    "no MOC, pointer row not written"
                    if result["mocs"] and all(entry["action"] == "no-moc" for entry in result["mocs"])
                    else "noop")
                record("pointers", summary, actions, list(result["changed"]))
                related.extend(str(entry["moc"]) for entry in result["mocs"])
                if result["over_cap"]:
                    steps[-1]["over_cap"] = result["over_cap"]
        except ToolError as exc:
            if exc.code == EXIT_USAGE and topic:
                raise
            record("pointers", "skipped", exc.message)

    # 4. timeline: reserved (v1.7.0).

    # MOCs this note is recorded in, changed or not this time: a change left
    # uncommitted by an earlier run (a refused commit, --no-commit) belongs
    # to this note's unit too.
    link = "[[" + (pointers.link_path_for(ws, path) if in_vault else rel)
    leftovers = []
    for moc_rel in related:
        if moc_rel in touched or moc_rel in leftovers:
            continue
        try:
            if link in read_text(ws.root / moc_rel):
                leftovers.append(moc_rel)
        except (NotText, OSError):
            continue

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

    # 6. commit
    commit_result = None
    failed = False
    paths = [rel] + [p for p in touched if p != rel]
    paths += [p for p in leftovers if p not in paths]
    paths += [p for p in extra if p not in paths and p not in skip_commit]
    if not do_commit:
        record("commit", "not-requested")
    elif not ws.hybrid_monorepo_present:
        record("commit", "not-applicable", "not a hybrid monorepo")
    elif dry_run:
        record("commit", "dry-run", ", ".join(paths))
    else:
        subject = message.strip() if message else default_message(ws, path, role)
        try:
            commit_result = gitops.commit(ws, subject, paths, body=body)
        except ToolError as exc:
            failed = True
            record("commit", "failed", exc.message)
        else:
            if commit_result["committed"]:
                record("commit", "committed", "%s in %s: %s" % ((commit_result["sha"] or "")[:10],
                                                                 commit_result["repo"], subject))
            else:
                record("commit", str(commit_result["reason"]), str(commit_result["repo"] or ""))

    return {
        "file": rel,
        "notes": notes,
        "steps": steps,
        "touched": touched,
        "commit": commit_result,
        "failed": failed,
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
