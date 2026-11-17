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

from contextlib import closing
from pathlib import Path
from typing import Dict, List, Optional

from . import db as db_mod
from . import gitops, indexer, mocs, obsidian, pointers
from .errors import EXIT_USAGE, ToolError
from .workspace import CAPTURE_MARKER, MOC_NAME, Workspace


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
    extra = [ws.rel(ws.resolve(item)) for item in (also or [])]

    steps: List[Dict[str, object]] = []
    touched: List[str] = []

    def record(step: str, action: str, detail: str = "", changed: Optional[List[str]] = None) -> None:
        changed = changed or []
        steps.append({"step": step, "action": action, "detail": detail, "changed": changed})
        for rel in changed:
            if rel not in touched:
                touched.append(rel)

    in_vault = _in_vault(ws, path)
    rel = ws.rel(path)

    # 1. frontmatter
    if not in_vault:
        record("frontmatter", "not-applicable", "outside the vault")
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
                summary = "written" if acted else (
                    "no MOC, pointer row not written"
                    if result["mocs"] and all(entry["action"] == "no-moc" for entry in result["mocs"])
                    else "noop")
                record("pointers", summary, actions, list(result["changed"]))
                if result["over_cap"]:
                    steps[-1]["over_cap"] = result["over_cap"]
        except ToolError as exc:
            if exc.code == EXIT_USAGE and topic:
                raise
            record("pointers", "skipped", exc.message)

    # 4. timeline: reserved (v1.7.0).

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
    paths = [rel] + [p for p in touched if p != rel] + [p for p in extra if p not in touched and p != rel]
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
        "steps": steps,
        "touched": touched,
        "commit": commit_result,
        "failed": failed,
        "dry_run": dry_run,
    }

