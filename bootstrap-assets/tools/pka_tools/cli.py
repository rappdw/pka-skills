"""Command line for pka-tools.

Every command takes `--workspace DIR` (default: $WORKSPACE_ROOT, else the
nearest folder above the current one that has `.pka/`) and `--json`.

Exit codes: 0 done (including "nothing to do"); 1 the operation failed;
2 a prerequisite is missing; 3 the workspace is not ready for this command;
64 bad arguments, nothing touched.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from typing import List, Optional

from . import __version__
from . import actions as actions_mod
from . import db as db_mod
from . import indexer, install as install_mod, mocs, obsidian, people as people_mod, pointers, postroute
from . import search as search_mod, sessionlog, timeline as timeline_mod
from .errors import EXIT_FAIL, EXIT_OK, EXIT_USAGE, ToolError
from .workspace import Workspace, find_root


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> "NoReturn":  # type: ignore[name-defined]
        self.print_usage(sys.stderr)
        sys.stderr.write("%s: error: %s\n" % (self.prog, message))
        raise SystemExit(EXIT_USAGE)


def _emit(args: argparse.Namespace, data: dict, text: List[str]) -> None:
    if getattr(args, "json", False):
        json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        sys.stdout.write("\n".join(text) + "\n")


def _workspace(args: argparse.Namespace) -> Workspace:
    return Workspace(find_root(args.workspace))


def _listed(title: str, items: List[str], limit: int = 20) -> List[str]:
    if not items:
        return []
    out = ["%s (%d):" % (title, len(items))]
    out += ["  - %s" % item for item in items[:limit]]
    if len(items) > limit:
        out.append("  … and %d more" % (len(items) - limit))
    return out


# ------------------------------------------------------------ commands

def cmd_version(args: argparse.Namespace) -> int:
    _emit(args, {"version": __version__}, ["pka-tools %s" % __version__])
    return EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    ws = _workspace(args)
    manifest_version, vendored = install_mod.status(ws.root)
    schema: Optional[int] = None
    if ws.db_path.is_file():
        with closing(db_mod.connect(ws)) as conn:
            schema = db_mod.user_version(conn)
    people = ws.people_home()
    data = {
        "workspace": str(ws.root),
        "tool_version": __version__,
        "vendored_version": manifest_version,
        "vendored_files": vendored,
        "vault": ws.rel(ws.vault) or ".",
        "obsidian_present": ws.obsidian_present,
        "storage_mode": "index" if schema is not None else "markdown-only",
        "schema_version": schema,
        "schema_current": schema == db_mod.SCHEMA_VERSION if schema is not None else None,
        "index_roots": [ws.rel(root) or "." for root in ws.index_roots()],
        "meeting_homes": [ws.rel(folder) for folder in ws.meeting_homes()],
        "people_home": ws.rel(people) if people else None,
        "repo_map_entries": len(ws.repo_map()),
    }
    text = [
        "Workspace:        %s" % data["workspace"],
        "pka-tools:        %s (vendored: %s)" % (__version__, manifest_version or "no manifest"),
        "Vault:            %s" % data["vault"],
        "Obsidian:         %s" % ("present" if data["obsidian_present"] else "not present"),
        "Storage:          %s" % (
            "markdown-only (no index)" if schema is None
            else "index, schema version %d%s" % (schema, "" if data["schema_current"] else " (needs `db migrate`)")
        ),
        "Index roots:      %s" % (", ".join(data["index_roots"]) or "none"),
        "Meeting homes:    %s" % (", ".join(data["meeting_homes"]) or "none"),
        "People home:      %s" % (data["people_home"] or "none"),
    ]
    _emit(args, data, text)
    return EXIT_OK


def cmd_install(args: argparse.Namespace) -> int:
    root = find_root_for_install(args.workspace)
    report = install_mod.install(root, assets=args.assets, dry_run=args.dry_run)
    text = ["pka-tools install%s — plugin version %s" % (
        " (dry run)" if args.dry_run else "", report["plugin_version"])]
    if args.git:
        text.append("  --git is deprecated and ignored: the nested-repository scripts are no longer shipped.")
    text += [
        "  installed: %d   updated: %d   current: %d   kept: %d   conflicts: %d" % (
            len(report["installed"]), len(report["updated"]), len(report["current"]),
            len(report["kept"]), len(report["conflicts"]))
    ]
    text += _listed("Installed", report["installed"], 60)
    text += _listed("Updated", report["updated"], 60)
    text += _listed("Kept (edited locally; the plugin's copy has not changed)", report["kept"])
    if report["conflicts"]:
        text += _listed(
            "Edited locally AND changed in the plugin — yours was kept, the plugin's copy is beside it as <name>.new",
            report["conflicts"])
    text += _listed("No longer shipped, moved to the backup folder", report["obsolete_moved"])
    text += _listed("No longer shipped, edited locally, left in place", report["obsolete_kept"])
    text += _listed(
        "From the removed nested-repository support, not recorded in the manifest, left in place (yours to keep or delete)",
        report["retired_unmanaged"])
    if report["backups"]:
        text.append("Previous copies saved under: %s" % report["backups"])
    _emit(args, report, text)
    return EXIT_OK


def find_root_for_install(explicit: Optional[str]) -> Path:
    """Install may run before `.pka/` exists, so the root defaults to cwd."""
    candidate = explicit or os.environ.get("WORKSPACE_ROOT") or os.getcwd()
    path = Path(candidate)
    if not path.is_dir():
        raise ToolError("workspace not found: %s" % candidate, EXIT_USAGE)
    return path


def cmd_db(args: argparse.Namespace) -> int:
    ws = _workspace(args)
    if args.db_command == "init":
        result = db_mod.init(ws)
        if result["action"] == "created":
            text = ["Created %s (schema version %d). Run `pka-tools index` to fill it." % (
                result["path"], result["schema_version"])]
        else:
            text = ["%s already exists at schema version %d; nothing to do." % (
                result["path"], result["schema_version"])]
        _emit(args, result, text)
        return EXIT_OK
    if args.db_command == "migrate":
        result = db_mod.migrate(ws, apply=args.apply)
        if result["action"] == "none":
            text = ["The index is already at schema version %d; nothing to do." % result["to"]]
        elif result["action"] == "planned":
            text = ["Migration plan: schema version %d -> %d" % (result["from"], result["to"])]
            text += ["  %d. %s" % (pos, step) for pos, step in enumerate(result["steps"], 1)]
            text += ["", "Nothing has been changed. A backup is taken before anything is.",
                     "To carry this out: pka-tools db migrate --apply"]
        else:
            text = ["Migrated the index from schema version %d to %d." % (result["from"], result["to"])]
            text += ["  %d. %s" % (pos, step) for pos, step in enumerate(result["steps"], 1)]
            text += ["Backup taken first: %s" % result["backup"],
                     "To undo: replace .pka/knowledge.db with that file."]
        _emit(args, result, text)
        return EXIT_OK
    if args.db_command == "backup":
        saved = db_mod.backup(ws)
        _emit(args, {"backup": ws.rel(saved)}, ["Backup written: %s" % ws.rel(saved)])
        return EXIT_OK
    result = db_mod.describe(ws)
    text = ["%s — schema version %d%s" % (
        result["path"], result["schema_version"], "" if result["current"] else " (needs `db migrate`)")]
    for table in result["tables"]:
        text.append("  %s (%s rows): %s" % (
            table["name"], "?" if table["rows"] is None else table["rows"], ", ".join(table["columns"])))
    _emit(args, result, text)
    return EXIT_OK


def cmd_index(args: argparse.Namespace) -> int:
    ws = _workspace(args)
    with closing(db_mod.connect(ws)) as conn:
        report = indexer.run(ws, conn, targets=args.paths, rebuild=args.rebuild,
                             prune=args.prune, dry_run=args.dry_run)
    text = ["Index%s: %d added, %d updated, %d removed, %d unchanged (%.2fs)" % (
        " (dry run)" if args.dry_run else "", report["added"], report["updated"],
        report["removed"], report["unchanged"], report["seconds"])]
    text.append("Scope: %s" % (", ".join(report["scope"]) or "nothing"))
    if report["pointer_rows"]:
        text.append("Pointer rows indexed: %d" % report["pointer_rows"])
    text += _listed("Not found", report["not_found"])
    if report.get("unreadable_names"):
        text.append("%d file or folder name(s) are not valid UTF-8 and were skipped." % report["unreadable_names"])
    text += _listed("Documents with no searchable text (write an OCR sidecar `<file>.txt`, then re-index)",
                    report["needs_text"])
    text += _listed("Documents that changed since their text was extracted", report["stale_text"])
    if report["pruned"]:
        text.append("Pruned %d row(s) whose file no longer exists." % report["pruned"])
    if report["stale_elsewhere"]:
        text.append("%d row(s) outside this scope point at files that no longer exist "
                    "(remove them with `pka-tools index --prune`)." % report["stale_elsewhere"])
    _emit(args, report, text)
    return EXIT_OK


def cmd_search(args: argparse.Namespace) -> int:
    ws = _workspace(args)
    with closing(db_mod.connect(ws)) as conn:
        result = search_mod.run(ws, conn, " ".join(args.query), limit=args.limit, any_term=args.any)
    text = []
    if not result["results"]:
        text.append("No results for: %s" % result["query"])
    else:
        note = "" if result["mode"] == "all" or args.any else " (no file has every term; showing files with any)"
        text.append("%d result(s) for: %s%s" % (result["count"], result["query"], note))
        for pos, entry in enumerate(result["results"], 1):
            if entry["is_pointer"]:
                text.append("%2d. [pointer] %s — %s" % (pos, entry.get("topic", ""), entry["path"]))
                for item in entry.get("files", []):
                    text.append("      -> %s" % (item["path"] or item["link"] + " (missing)"))
            else:
                text.append("%2d. %s" % (pos, entry["path"]))
                if entry["excerpt"]:
                    text.append("      %s" % entry["excerpt"])
    _emit(args, result, text)
    return EXIT_OK


def cmd_actions(args: argparse.Namespace) -> int:
    ws = _workspace(args)
    today = _dt.date.today()
    since = until = None
    if not args.all_dates:
        since = actions_mod.parse_date(args.since, "--since") if args.since else today - _dt.timedelta(days=7)
        until = actions_mod.parse_date(args.until, "--until") if args.until else None
    result = actions_mod.run(ws, since, until, scope=args.scope, under=args.under,
                             include_undated=args.include_undated)
    window = "all dates" if args.all_dates else "since %s%s" % (
        result["since"], " until %s" % result["until"] if result["until"] else "")
    text = ["%d open action item(s), %s, in %d note(s) under: %s" % (
        result["open"], window, result["files_scanned"], ", ".join(result["scope"]) or "nothing")]
    for item in result["items"]:
        text.append("- [ ] %s" % item["text"])
        text.append("      %s:%d" % (item["path"], item["line"]))
    _emit(args, result, text)
    return EXIT_OK


def cmd_commit(args: argparse.Namespace) -> int:
    """Deprecated stub. Role files written for earlier releases still call
    `pka-tools commit`; it must not fail them, and it must not touch git."""
    result = {
        "committed": False, "reason": "removed", "deprecated": True,
        "paths": list(args.paths),
        "message": "pka-tools no longer commits. Nothing was staged or committed; commit the changes yourself.",
    }
    _emit(args, result, [
        "Not committed: pka-tools no longer commits (`commit` is deprecated and does nothing).",
        "Nothing was staged or committed; commit the changes yourself.",
    ])
    return EXIT_OK


def cmd_pointers(args: argparse.Namespace) -> int:
    ws = _workspace(args)
    if args.pointers_command == "add":
        entities = [item.strip() for item in (args.entities or "").split(",") if item.strip()]
        result = pointers.add(ws, args.file, topic=args.topic or "", entities=entities,
                              context=args.context or "", extra_mocs=args.moc, dry_run=args.dry_run,
                              create_mocs=args.create_moc)
        text = ["Pointer rows for %s%s:" % (result["file"], " (dry run)" if args.dry_run else "")]
        if result.get("problem"):
            text.append("  SKIPPED — %s" % result["problem"])
        for entry in result["mocs"]:
            if entry["problem"]:
                text.append("  %s: SKIPPED — %s" % (entry["moc"], entry["problem"]))
            elif entry["action"] == "no-moc":
                text.append("  %s: no MOC, pointer row not written (not an Obsidian vault; "
                            "`pka-tools pointers init` opts in)" % entry["moc"])
            else:
                text.append("  %s: %s%s" % (entry["moc"], entry["action"],
                                             " (%s)" % entry["topic"] if entry["topic"] else ""))
        text += _listed("Rows at or over the %d-file soft cap (consider splitting)" % pointers.SIZE_CAP,
                        result["over_cap"])
        _emit(args, result, text)
        return EXIT_OK
    if args.pointers_command == "init":
        result = pointers.init(ws, args.folders, dry_run=args.dry_run)
        text = ["Pointer layer%s: %d MOC(s) created, %d already present" % (
            " (dry run)" if args.dry_run else "", len(result["created"]), len(result["already_present"]))]
        text += ["  + %s" % rel for rel in result["created"]]
        text += _listed("Could not create", result["skipped"])
        _emit(args, result, text)
        return EXIT_OK
    if args.pointers_command == "rename":
        result = pointers.rename(ws, args.old, args.new, prefix=args.prefix, dry_run=args.dry_run,
                                 notes=args.notes)
        text = ["%d link(s) rewritten in %d %s: [[%s]] -> [[%s]]%s" % (
            result["rewrites"], len(result["changed"]), "file(s)" if args.notes else "MOC file(s)",
            result["from"], result["to"],
            " (dry run)" if args.dry_run else "")]
        text += ["  %s" % rel for rel in result["changed"]]
        if result.get("timeline_rewrites"):
            text.append("%d timeline link(s) rewritten in: %s" % (result["timeline_rewrites"],
                                                                 ", ".join(result["timeline_changed"])))
        text += _listed("Skipped (left unchanged)",
                        ["%s: %s" % (rel, result["skip_reasons"].get(rel, "")) for rel in result["skipped"]])
        _emit(args, result, text)
        return EXIT_OK
    if args.pointers_command == "check":
        result = pointers.check(ws)
        text = ["%d pointer row(s) checked: %d broken link(s), %d unreadable table(s), %d long row(s)" % (
            result["rows"], len(result["broken"]), len(result["malformed"]), len(result["over_cap"]))]
        for item in result["broken"]:
            text.append("  broken: %s line %d, %s -> %s" % (item["moc"], item["line"], item["topic"], item["broken_link"]))
        for item in result["malformed"]:
            text.append("  unreadable: %s — %s" % (item["moc"], item["problem"]))
        for item in result["over_cap"]:
            text.append("  long: %s — %s (%d files)" % (item["moc"], item["topic"], item["files"]))
        _emit(args, result, text)
        return EXIT_FAIL if args.strict and (result["broken"] or result["malformed"]) else EXIT_OK
    result = pointers.listing(ws, args.moc_file)
    text = []
    for moc in result["mocs"]:
        text.append("%s (%d rows)" % (moc["moc"], len(moc["rows"])))
        for row in moc["rows"]:
            text.append("  %s — %d file(s)" % (row["topic"], len(row["files"])))
    _emit(args, result, text or ["No pointer rows."])
    return EXIT_OK


def cmd_moc(args: argparse.Namespace) -> int:
    ws = _workspace(args)
    result = mocs.add_link(ws, args.file, section=args.section, create=args.create_moc, dry_run=args.dry_run)
    if result["problem"]:
        text = ["%s: SKIPPED — %s" % (result["moc"], result["problem"])]
    elif result["action"] == "no-moc":
        text = ["%s: no MOC, link not written (not an Obsidian vault; pass --create-moc to create one)" % result["moc"]]
    else:
        text = ["%s: %s%s" % (result["moc"], result["action"], " (dry run)" if args.dry_run else "")]
    _emit(args, result, text)
    return EXIT_OK


def _summary_for(items: Optional[List[str]]) -> dict:
    out = {}
    for item in items or []:
        slug, sep, text = item.partition("=")
        if not sep or not slug.strip():
            raise ToolError("--summary-for takes SLUG=TEXT, got %r" % item, EXIT_USAGE)
        out[slug.strip()] = text
    return out


def cmd_post_route(args: argparse.Namespace) -> int:
    ws = _workspace(args)
    entities = [item.strip() for item in (args.entities or "").split(",") if item.strip()]
    result = postroute.run(
        ws, args.file,
        topic=args.topic or "", entities=entities, context=args.context or "", section=args.section,
        also=args.also, create_mocs=args.create_moc, dry_run=args.dry_run,
        do_timeline=not args.no_timeline, timeline_people=args.person, summary=args.summary or "",
        summary_for=_summary_for(args.summary_for), include_large=args.include_large,
    )
    text = ["post-route %s%s" % (result["file"], " (dry run)" if args.dry_run else "")]
    for step in result["steps"]:
        detail = (" — %s" % step["detail"]) if step["detail"] else ""
        text.append("  %-12s %s%s" % (step["step"], step["action"], detail))
        for item in step.get("over_cap", []):
            text.append("               over the 8-file soft cap: %s" % item)
    if result["touched"]:
        text.append("Files changed besides the note: %s" % (", ".join(p for p in result["touched"] if p != result["file"]) or "none"))
    text += ["Note: %s" % note for note in result["notes"]]
    _emit(args, result, text)
    return EXIT_OK


def cmd_people(args: argparse.Namespace) -> int:
    ws = _workspace(args)
    reg = people_mod.registry(ws)
    if args.people_command == "list":
        people_mod.require_home(reg)
        data = {"home": ws.rel(reg.home), "people": [p.as_dict(ws) for p in reg.people.values()]}
        text = ["%d people in %s" % (len(data["people"]), data["home"])]
        for p in data["people"]:
            extra = (" (also: %s)" % ", ".join(p["aliases"])) if p["aliases"] else ""
            text.append("  %-24s %s%s%s" % (p["slug"], p["name"], extra, "" if p["index"] else "  [no index.md]"))
        _emit(args, data, text)
        return EXIT_OK
    if args.people_command == "resolve":
        people_mod.require_home(reg)
        results = [reg.resolve(name) for name in args.names]
        text = []
        for r in results:
            if r["status"] == "high":
                text.append("%s -> %s (%s)" % (r["text"], r["slug"], r["reason"]))
            elif r["status"] == "ambiguous":
                text.append("%s -> AMBIGUOUS: %s (%s)" % (r["text"], ", ".join(r["candidates"]), r["reason"]))
            else:
                hint = (" — similar: %s" % ", ".join(r["candidates"])) if r["candidates"] else ""
                text.append("%s -> no match (%s)%s" % (r["text"], r["reason"], hint))
        _emit(args, {"results": results}, text)
        return EXIT_OK
    result = people_mod.add_alias(ws, args.slug, args.alias, dry_run=args.dry_run)
    text = ["%s: %s %r%s" % (result["slug"], result["problem"] and "SKIPPED — " + result["problem"] or result["action"],
                              result["alias"], " (dry run)" if args.dry_run else "")]
    _emit(args, result, text)
    return EXIT_OK


def cmd_timeline(args: argparse.Namespace) -> int:
    ws = _workspace(args)
    command = args.timeline_command
    if command == "add":
        result = timeline_mod.add(ws, args.file, people=args.person, summary=args.summary or "",
                                  summary_for=_summary_for(args.summary_for), kind=args.kind, label=args.label,
                                  date=args.date, include_large=args.include_large, dry_run=args.dry_run)
        text = ["Timeline for %s (%s, %s)%s:" % (result["note"], result["date"], result["kind"],
                                                  " (dry run)" if args.dry_run else "")]
        for entry in result["people"]:
            text.append("  %s [%s]: %s" % (entry["slug"], entry["tier"], entry["problem"] or entry["action"]))
            if entry["line"] and entry["action"] in ("added", "created-index"):
                text.append("      %s" % entry["line"])
        if not result["people"]:
            text.append("  nobody (no person folder matches the note)")
        for item in result["ambiguous"]:
            text.append("  ambiguous %r (%s): %s — not added" % (item["text"], item["source"], ", ".join(item["candidates"])))
        if result["unresolved"]:
            text.append("  no person folder: %s" % ", ".join(result["unresolved"]))
        if result["large_skipped"]:
            text.append("  large meeting (%d attendees): attendees not added; --include-large to add them"
                        % result["attendees"])
        _emit(args, result, text)
        return EXIT_OK
    if command == "who":
        reg = people_mod.registry(ws)
        people_mod.require_home(reg)
        path = ws.resolve(args.file)
        if not path.is_file():
            raise ToolError("no such file: %s" % args.file, EXIT_USAGE)
        result = timeline_mod.who(ws, reg, timeline_mod.Note(ws, path), include_large=args.include_large)
        text = ["%s belongs to: %s" % (result["note"], ", ".join(p["slug"] for p in result["people"]) or "nobody")]
        for p in result["people"]:
            text += ["  %s: %s" % (p["slug"], why) for why in p["evidence"]]
        for item in result["ambiguous"]:
            text.append("  ambiguous %r: %s" % (item["text"], ", ".join(item["candidates"])))
        if result["unresolved"]:
            text.append("  no person folder: %s" % ", ".join(result["unresolved"]))
        _emit(args, result, text)
        return EXIT_OK
    if command == "list":
        result = timeline_mod.listing(ws, args.slug)
        text = ["%s: %d entr%s" % (args.slug, len(result["entries"]), "y" if len(result["entries"]) == 1 else "ies")]
        text += ["  %s · %s · %s%s" % (e["date"], e["kind"], e["key"], (" — " + e["summary"]) if e["summary"] else "")
                 for e in result["entries"]]
        if result["problem"]:
            text.append("  PROBLEM: %s" % result["problem"])
        _emit(args, result, text)
        return EXIT_OK
    if command == "rename":
        old = pointers._normalise_ref(ws, args.old)
        new = pointers._normalise_ref(ws, args.new)
        result = timeline_mod.rename(ws, old, new, prefix=args.prefix, dry_run=args.dry_run)
        text = ["%d timeline link(s) rewritten in %d file(s)%s" % (result["rewrites"], len(result["changed"]),
                                                                  " (dry run)" if args.dry_run else "")]
        text += ["  %s" % rel for rel in result["changed"]]
        text += _listed("Skipped", result["skipped"])
        _emit(args, result, text)
        return EXIT_OK
    if command == "check":
        result = timeline_mod.check(ws)
        text = ["%d timeline problem(s)" % len(result["problems"])]
        text += ["  %s%s: %s" % (p["index"], ":%d" % p["line"] if p["line"] else "", p["problem"])
                 for p in result["problems"]]
        _emit(args, result, text)
        return EXIT_FAIL if args.strict and result["problems"] else EXIT_OK
    result = timeline_mod.strip(ws, args.person, dry_run=args.dry_run)
    text = ["Timeline blocks removed from %d file(s)%s" % (len(result["changed"]), " (dry run)" if args.dry_run else "")]
    text += ["  %s" % rel for rel in result["changed"]]
    text += _listed("Skipped (block unreadable)", result["skipped"])
    _emit(args, result, text)
    return EXIT_OK


def cmd_log(args: argparse.Namespace) -> int:
    ws = _workspace(args)
    if args.log_command == "add":
        result = sessionlog.add(ws, args.role, args.summary, args.open or "", args.next or "",
                                at=args.at, dry_run=args.dry_run)
        _emit(args, result, ["%s%s" % (result["entry"], "  (dry run)" if args.dry_run else "")])
        return EXIT_OK
    if args.log_command == "open":
        result = sessionlog.open_threads(ws, last=args.last)
        text = ["%d open thread(s) in the last %d entries" % (len(result["open"]), result["looked_at"])]
        for item in result["open"]:
            text.append("- %s (%s, %s)" % (item["open"], item["role"], item["at"]))
        _emit(args, result, text)
        return EXIT_OK
    result = sessionlog.check(ws)
    text = ["%d entries, %d malformed" % (result["entries"], len(result["malformed"]))]
    for item in result["malformed"]:
        text.append("  line %d: %s" % (item["line"], item["problem"]))
    _emit(args, result, text)
    return EXIT_FAIL if args.strict and result["malformed"] else EXIT_OK


def cmd_obsidian(args: argparse.Namespace) -> int:
    ws = _workspace(args)
    summary = obsidian.bootstrap(ws, dry_run=args.dry_run)
    text = [
        "Obsidian bootstrap summary%s" % (" (dry run)" if args.dry_run else ""),
        "------------------------------",
        "MOC stubs created:        %d (%d already present)" % (
            len(summary["moc_created"]), len(summary["moc_already_present"])),
        "Person indexes created:   %d (%d already present)" % (
            len(summary["person_indexes_created"]), len(summary["person_indexes_already_present"])),
        "Files given frontmatter:  %d" % len(summary["frontmatter_added"]),
        "Frontmatter merged:       %d files" % len(summary["frontmatter_merged"]),
        "Total notes in vault:     %d" % summary["files_total"],
        "Total files touched:      %d" % len(summary["touched"]),
    ]
    if summary["skipped"]:
        text.append("Files SKIPPED (malformed or unsupported frontmatter, left untouched): %d" % len(summary["skipped"]))
        text += ["  - %s" % item for item in summary["skipped"]]
    text += _listed("Notes", summary["warnings"])
    if summary["touched"] and not args.dry_run:
        text.append("Nothing was committed: review the changes and commit them yourself."
                    + (" (--commit is deprecated and ignored.)" if args.commit else ""))
    _emit(args, summary, text)
    return EXIT_OK


# ------------------------------------------------------------ parser

def _create_flags(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--create-moc", dest="create_moc", action="store_true", default=None,
                       help="create a missing _MOC.md (default: only in an Obsidian vault)")
    group.add_argument("--no-create-moc", dest="create_moc", action="store_false",
                       help="never create a missing _MOC.md")


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--workspace", metavar="DIR", help="workspace root (default: found from the current directory)")
    common.add_argument("--json", action="store_true", help="print the result as JSON")

    parser = _Parser(prog="pka-tools", description="Deterministic helpers for a PKA workspace.")
    parser.add_argument("--version", action="version", version="pka-tools %s" % __version__)
    parser.add_argument("--workspace", dest="workspace_global", metavar="DIR", help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", metavar="<command>", parser_class=_Parser)
    sub.required = True

    p = sub.add_parser("version", parents=[common], help="print the version")
    p.set_defaults(func=cmd_version)

    p = sub.add_parser("status", parents=[common], help="what this workspace is: vault, index, roots, versions")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("install", parents=[common],
                       help="vendor the plugin's helpers into .pka/ (run from the plugin's copy)")
    p.add_argument("--git", action="store_true", help="deprecated, ignored (the nested-repository scripts are no longer shipped)")
    p.add_argument("--assets", metavar="DIR", help="the plugin's bootstrap-assets/ folder (default: located automatically)")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_install)

    p = sub.add_parser("db", help="create, migrate, back up or describe the index")
    dbsub = p.add_subparsers(dest="db_command", metavar="<db command>", parser_class=_Parser)
    dbsub.required = True
    q = dbsub.add_parser("init", parents=[common], help="create .pka/knowledge.db")
    q.set_defaults(func=cmd_db)
    q = dbsub.add_parser("migrate", parents=[common], help="show the migration plan; --apply carries it out")
    q.add_argument("--apply", action="store_true", help="back up the index, then migrate it")
    q.set_defaults(func=cmd_db)
    q = dbsub.add_parser("backup", parents=[common], help="copy the index to .pka/db-backups/")
    q.set_defaults(func=cmd_db)
    q = dbsub.add_parser("schema", parents=[common], help="list tables, columns and row counts")
    q.set_defaults(func=cmd_db)

    p = sub.add_parser("index", parents=[common], help="index new and changed files; drop rows for removed ones")
    p.add_argument("paths", nargs="*", metavar="PATH", help="files or folders (default: the index roots)")
    p.add_argument("--rebuild", action="store_true", help="re-read every file in scope")
    p.add_argument("--prune", action="store_true", help="also remove rows anywhere whose file no longer exists")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("search", parents=[common], help="full-text search (terms are quoted for you)")
    p.add_argument("query", nargs="+", metavar="TERM")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--any", action="store_true", help="match files with any term rather than all")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("actions", parents=[common], help="open checkboxes in dated notes")
    p.add_argument("--since", metavar="YYYY-MM-DD", help="earliest note date (default: 7 days ago)")
    p.add_argument("--until", metavar="YYYY-MM-DD", help="latest note date")
    p.add_argument("--all-dates", action="store_true", help="no date window")
    p.add_argument("--include-undated", action="store_true", help="also scan notes with no date")
    p.add_argument("--scope", choices=("meetings", "all"), default="meetings",
                   help="meetings: meeting-home and people folders (default); all: every index root")
    p.add_argument("--under", action="append", metavar="FOLDER", help="scan this folder instead (repeatable)")
    p.set_defaults(func=cmd_actions)

    p = sub.add_parser("commit", parents=[common],
                       help="deprecated: does nothing (pka-tools no longer commits)")
    p.add_argument("-m", "--message", metavar="SUBJECT", help="ignored")
    p.add_argument("--body", metavar="TEXT", help="ignored")
    p.add_argument("--stage-only", action="store_true", help="ignored")
    p.add_argument("paths", nargs="*", metavar="PATH")
    p.set_defaults(func=cmd_commit)

    p = sub.add_parser("pointers", help="maintain the pointer tables in _MOC.md files")
    psub = p.add_subparsers(dest="pointers_command", metavar="<pointers command>", parser_class=_Parser)
    psub.required = True
    q = psub.add_parser("add", parents=[common], help="record a routed file in its domain MOC(s)")
    q.add_argument("file", metavar="FILE")
    q.add_argument("--topic", help="the cluster this file belongs to (skips matching)")
    q.add_argument("--entities", metavar="A,B", help="extra entities (people, organisations, products)")
    q.add_argument("--context", help="the routing directive, if any (adds matching tokens)")
    q.add_argument("--moc", action="append", metavar="PATH", help="an additional _MOC.md to update (repeatable)")
    _create_flags(q)
    q.add_argument("--dry-run", action="store_true")
    q.set_defaults(func=cmd_pointers)
    q = psub.add_parser("init", parents=[common],
                        help="opt in: give folders a _MOC.md with an empty Pointers table")
    q.add_argument("folders", nargs="*", metavar="FOLDER", help="default: every top-level folder of the vault")
    q.add_argument("--dry-run", action="store_true")
    q.set_defaults(func=cmd_pointers)
    q = psub.add_parser("rename", parents=[common], help="rewrite MOC links after a file or folder moved")
    q.add_argument("old", metavar="OLD")
    q.add_argument("new", metavar="NEW")
    q.add_argument("--prefix", action="store_true", help="OLD and NEW are folders: rewrite every link beneath OLD")
    q.add_argument("--notes", action="store_true",
                   help="also rewrite links in every markdown note of the vault, not only in _MOC.md files")
    q.add_argument("--dry-run", action="store_true")
    q.set_defaults(func=cmd_pointers)
    q = psub.add_parser("check", parents=[common], help="report broken pointer links and unreadable tables")
    q.add_argument("--strict", action="store_true", help="exit 1 when anything is broken")
    q.set_defaults(func=cmd_pointers)
    q = psub.add_parser("list", parents=[common], help="list pointer rows")
    q.add_argument("moc_file", nargs="?", metavar="MOC")
    q.set_defaults(func=cmd_pointers)

    p = sub.add_parser("moc", help="navigation links in _MOC.md files")
    msub = p.add_subparsers(dest="moc_command", metavar="<moc command>", parser_class=_Parser)
    msub.required = True
    q = msub.add_parser("add-link", parents=[common], help="add a - [[note]] bullet to the note's folder MOC")
    q.add_argument("file", metavar="FILE")
    q.add_argument("--section", metavar="HEADING", help="an existing ## section to add to (default: Files, else Unsorted)")
    _create_flags(q)
    q.add_argument("--dry-run", action="store_true")
    q.set_defaults(func=cmd_moc)

    p = sub.add_parser("post-route", parents=[common],
                       help="after filing a note: frontmatter, MOC link, pointer row, timeline, index")
    p.add_argument("file", metavar="FILE")
    p.add_argument("--role", default="Librarian", help="deprecated, ignored (was the commit message prefix)")
    p.add_argument("-m", "--message", metavar="SUBJECT", help="deprecated, ignored (was the commit subject)")
    p.add_argument("--body", metavar="TEXT", help="deprecated, ignored (was the commit body)")
    p.add_argument("--topic", help="pointer cluster (as for `pointers add`)")
    p.add_argument("--entities", metavar="A,B")
    p.add_argument("--context", help="the routing directive, if any")
    p.add_argument("--section", metavar="HEADING", help="MOC section for the link (as for `moc add-link`)")
    p.add_argument("--also", action="append", metavar="PATH",
                   help="another path to re-index with the note, e.g. the note's old location, "
                        "so its rows are dropped (repeatable)")
    p.add_argument("--no-commit", action="store_true", help="deprecated, ignored (nothing is committed)")
    p.add_argument("--no-timeline", action="store_true", help="do not add the note to anyone's timeline")
    p.add_argument("--person", action="append", metavar="SLUG",
                   help="put the note on this person's timeline instead of working it out (repeatable)")
    p.add_argument("--summary", metavar="TEXT", help="timeline summary (max 140 characters)")
    p.add_argument("--summary-for", action="append", metavar="SLUG=TEXT", help="summary for one person (repeatable)")
    p.add_argument("--include-large", action="store_true",
                   help="add attendees of a meeting with more than 8 of them")
    _create_flags(p)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_post_route)

    p = sub.add_parser("people", help="the people registry (person folders)")
    psub2 = p.add_subparsers(dest="people_command", metavar="<people command>", parser_class=_Parser)
    psub2.required = True
    q = psub2.add_parser("list", parents=[common], help="every person folder, with name and aliases")
    q.set_defaults(func=cmd_people)
    q = psub2.add_parser("resolve", parents=[common], help="which person a name, link or slug means")
    q.add_argument("names", nargs="+", metavar="NAME")
    q.set_defaults(func=cmd_people)
    q = psub2.add_parser("alias", parents=[common], help="record that a name means this person")
    q.add_argument("slug", metavar="SLUG")
    q.add_argument("alias", metavar="ALIAS")
    q.add_argument("--dry-run", action="store_true")
    q.set_defaults(func=cmd_people)

    p = sub.add_parser("timeline", help="person timelines (a managed block in each person's index.md)")
    tsub = p.add_subparsers(dest="timeline_command", metavar="<timeline command>", parser_class=_Parser)
    tsub.required = True
    q = tsub.add_parser("add", parents=[common], help="put a note on the timelines of the people it belongs to")
    q.add_argument("file", metavar="FILE")
    q.add_argument("--person", action="append", metavar="SLUG", help="name the people instead (repeatable)")
    q.add_argument("--summary", metavar="TEXT")
    q.add_argument("--summary-for", action="append", metavar="SLUG=TEXT")
    q.add_argument("--kind", choices=timeline_mod.KINDS)
    q.add_argument("--label", metavar="TEXT", help="link text (default: from the note)")
    q.add_argument("--date", metavar="YYYY-MM-DD", help="when the note has no date of its own")
    q.add_argument("--include-large", action="store_true")
    q.add_argument("--dry-run", action="store_true")
    q.set_defaults(func=cmd_timeline)
    q = tsub.add_parser("who", parents=[common], help="whose timeline a note belongs on, and why")
    q.add_argument("file", metavar="FILE")
    q.add_argument("--include-large", action="store_true")
    q.set_defaults(func=cmd_timeline)
    q = tsub.add_parser("list", parents=[common], help="a person's timeline entries")
    q.add_argument("slug", metavar="SLUG")
    q.set_defaults(func=cmd_timeline)
    q = tsub.add_parser("rename", parents=[common], help="rewrite timeline links after a note or folder moved")
    q.add_argument("old", metavar="OLD")
    q.add_argument("new", metavar="NEW")
    q.add_argument("--prefix", action="store_true")
    q.add_argument("--dry-run", action="store_true")
    q.set_defaults(func=cmd_timeline)
    q = tsub.add_parser("check", parents=[common], help="unreadable blocks, broken links, lines out of order")
    q.add_argument("--strict", action="store_true")
    q.set_defaults(func=cmd_timeline)
    q = tsub.add_parser("strip", parents=[common], help="remove timeline blocks (rollback)")
    q.add_argument("--person", metavar="SLUG", help="only this person")
    q.add_argument("--dry-run", action="store_true")
    q.set_defaults(func=cmd_timeline)

    p = sub.add_parser("log", help="the session log (.pka/session-log.md)")
    lsub = p.add_subparsers(dest="log_command", metavar="<log command>", parser_class=_Parser)
    lsub.required = True
    q = lsub.add_parser("add", parents=[common], help="append one well-formed entry")
    q.add_argument("--role", required=True)
    q.add_argument("--summary", required=True)
    q.add_argument("--open", metavar="TEXT", help="what is still open (the greeting reads this)")
    q.add_argument("--next", metavar="TEXT", help="the next action")
    q.add_argument("--at", metavar="'YYYY-MM-DD HH:MM'", help="timestamp (default: now)")
    q.add_argument("--dry-run", action="store_true")
    q.set_defaults(func=cmd_log)
    q = lsub.add_parser("open", parents=[common], help="open threads in recent entries, newest first")
    q.add_argument("--last", type=int, default=20, help="how many recent entries to read (default 20)")
    q.set_defaults(func=cmd_log)
    q = lsub.add_parser("check", parents=[common], help="report entries that do not follow the grammar")
    q.add_argument("--strict", action="store_true", help="exit 1 when any entry is malformed")
    q.set_defaults(func=cmd_log)

    p = sub.add_parser("obsidian", help="Obsidian vault helpers")
    osub = p.add_subparsers(dest="obsidian_command", metavar="<obsidian command>", parser_class=_Parser)
    osub.required = True
    q = osub.add_parser("bootstrap", parents=[common], help="the one-time mechanical retrofit of knowledge/")
    q.add_argument("--dry-run", action="store_true")
    q.add_argument("--commit", action="store_true", help="deprecated, ignored (nothing is committed)")
    q.set_defaults(func=cmd_obsidian)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "workspace", None) is None:
        args.workspace = getattr(args, "workspace_global", None)
    try:
        return args.func(args)
    except ToolError as exc:
        if getattr(args, "json", False):
            json.dump({"error": exc.message, "exit_code": exc.code}, sys.stdout, indent=2, ensure_ascii=False)
            sys.stdout.write("\n")
        sys.stderr.write("pka-tools: %s\n" % exc.message)
        return exc.code
    except BrokenPipeError:
        return EXIT_OK
    except sqlite3.Error as exc:
        sys.stderr.write(
            "pka-tools: the index (.pka/knowledge.db) could not be read or written: %s\n" % exc)
        return EXIT_FAIL
    except (OSError, UnicodeError) as exc:
        sys.stderr.write("pka-tools: %s\n" % exc)
        return EXIT_FAIL
    except KeyboardInterrupt:
        sys.stderr.write("pka-tools: interrupted\n")
        return 130
