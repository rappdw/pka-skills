"""Vendor the plugin's helpers into a workspace's `.pka/`, by manifest.

`.pka/manifest.json` records, for each vendored file, the SHA-256 of the
plugin's copy at the time it was last offered. Comparing three hashes (the
plugin's copy now, the file on disk, the manifest) tells an untouched file
from one the user has edited:

  on disk == plugin            current, nothing to do
  on disk == manifest          untouched since install: replaced
  on disk differs from both    edited locally: kept, and the plugin's copy is
                               written beside it as `<name>.new` when the
                               plugin's copy has changed
  no manifest entry (a workspace installed before the manifest existed):
      code      replaced; the previous copy is saved under
                .pka/upgrade-backups/<timestamp>/vendored/
      template  kept; `<name>.new` written

Nothing is ever deleted. A file the plugin no longer ships is moved to the
same backup folder if untouched, and left alone otherwise.

The scripts and templates of the nested-repository layout (RETIRED below) are
no longer shipped. Where the manifest records them they follow that rule. In
a workspace installed before the manifest existed there is nothing to compare
them with, so they are left in place and listed in the report.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import __version__
from .errors import EXIT_FAIL, EXIT_NOT_READY, EXIT_USAGE, ToolError
from .textio import sha256_file

MANIFEST_NAME = "manifest.json"
MANIFEST_VERSION = 1
# Helpers of the removed nested-repository layout, as they were vendored under .pka/.
RETIRED = (
    "graduate.sh",
    "init_project_repos.sh",
    "reinit-project-with-lfs.sh",
    "push-all.sh",
    "build-repo-list.sh",
    "gitattributes-template",
    "gitignore-template",
)


class Item:
    __slots__ = ("source", "dest", "component", "kind", "executable")

    def __init__(self, source: Path, dest: str, component: str, kind: str, executable: bool):
        self.source = source
        self.dest = dest            # POSIX path relative to .pka/
        self.component = component  # "core"
        self.kind = kind            # "code" or "template"
        self.executable = executable


def default_assets() -> Path:
    """bootstrap-assets/, located from this file (…/tools/pka_tools/install.py)."""
    return Path(os.path.realpath(__file__)).parent.parent.parent


def catalogue(assets: Path) -> List[Item]:
    tools = assets / "tools"
    scripts = assets / "scripts"
    package = tools / "pka_tools"
    if not (tools / "pka-tools").is_file() or not package.is_dir() or not scripts.is_dir():
        raise ToolError(
            "%s does not look like the plugin's bootstrap-assets/ folder. Run install from the "
            "plugin's copy: python3 <plugin>/bootstrap-assets/tools/pka-tools install" % assets,
            EXIT_USAGE,
        )
    items = [Item(tools / "pka-tools", "bin/pka-tools", "core", "code", True)]
    for module in sorted(package.glob("*.py")):
        items.append(Item(module, "bin/pka_tools/" + module.name, "core", "code", False))
    items.append(Item(scripts / "upgrade-roles.py", "upgrade-roles.py", "core", "code", True))
    for item in items:
        if not item.source.is_file():
            raise ToolError("missing plugin asset: %s" % item.source, EXIT_FAIL)
    return items


def _load_manifest(path: Path) -> Dict[str, dict]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ToolError(
            "%s is not valid JSON. Nothing was changed; fix or remove it and re-run." % path, EXIT_FAIL
        )
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, dict):
        return {}
    # A manifest key names a file under .pka/. Anything that could point
    # elsewhere (an absolute path, a `..` component) is not ours: drop it.
    safe = {}
    for name, entry in files.items():
        parts = str(name).replace("\\", "/").split("/")
        if not name or os.path.isabs(str(name)) or ".." in parts or "" in parts:
            continue
        safe[str(name)] = entry
    return safe


def _copy(source: Path, dest: Path, executable: bool) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name("." + dest.name + ".pka-tmp")
    shutil.copyfile(str(source), str(tmp))
    os.chmod(str(tmp), 0o755 if executable else 0o644)
    os.replace(str(tmp), str(dest))


class _Backups:
    """Creates .pka/upgrade-backups/<timestamp>/vendored/ on first use."""

    def __init__(self, pka: Path):
        self.pka = pka
        self.root: Optional[Path] = None

    def save(self, dest_rel: str) -> Path:
        if self.root is None:
            parent = self.pka / "upgrade-backups"
            parent.mkdir(parents=True, exist_ok=True)
            marker = parent / ".gitignore"
            if not marker.exists():
                marker.write_text("*\n", encoding="utf-8")
            stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            root = parent / stamp
            counter = 2
            while root.exists():
                root = parent / ("%s-%d" % (stamp, counter))
                counter += 1
            self.root = root / "vendored"
        target = self.root / dest_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(self.pka / dest_rel), str(target))
        return target


def install(
    root: Path,
    assets: Optional[Path] = None,
    dry_run: bool = False,
) -> dict:
    root = Path(os.path.realpath(str(root)))
    if not root.is_dir():
        raise ToolError("workspace not found: %s" % root, EXIT_USAGE)
    pka = root / ".pka"
    assets = Path(os.path.realpath(str(assets))) if assets else default_assets()
    if pka in [assets] + list(assets.parents):
        raise ToolError(
            "this is the workspace's vendored copy. Run install from the plugin's copy: "
            "python3 <plugin>/bootstrap-assets/tools/pka-tools install",
            EXIT_USAGE,
        )
    items = catalogue(assets)

    manifest_path = pka / MANIFEST_NAME
    recorded = _load_manifest(manifest_path)
    selected = items

    report = {
        "workspace": str(root),
        "plugin_version": __version__,
        "components": ["core"],
        "installed": [], "updated": [], "current": [], "kept": [], "conflicts": [],
        "obsolete_moved": [], "obsolete_kept": [], "retired_unmanaged": [],
        "backups": None, "dry_run": dry_run,
    }
    backups = _Backups(pka)
    new_files: Dict[str, dict] = {}
    if not dry_run:
        pka.mkdir(parents=True, exist_ok=True)

    for item in selected:
        dest = pka / item.dest
        plugin_hash = sha256_file(item.source)
        entry = recorded.get(item.dest)
        base = entry.get("sha256") if isinstance(entry, dict) else None
        new_files[item.dest] = {"sha256": plugin_hash, "component": item.component}

        if dest.is_symlink() or (dest.exists() and not dest.is_file()):
            report["kept"].append(item.dest + " (not a regular file)")
            continue
        if not dest.exists():
            if not dry_run:
                _copy(item.source, dest, item.executable)
            report["installed"].append(item.dest)
            continue
        disk_hash = sha256_file(dest)
        if disk_hash == plugin_hash:
            if item.executable and not os.access(str(dest), os.X_OK) and not dry_run:
                os.chmod(str(dest), 0o755)
            report["current"].append(item.dest)
            continue
        if base is not None and disk_hash == base:
            if not dry_run:
                _copy(item.source, dest, item.executable)
            report["updated"].append(item.dest)
            continue
        if base is None and item.kind == "code":
            if not dry_run:
                backups.save(item.dest)
                _copy(item.source, dest, item.executable)
            report["updated"].append(item.dest + " (previous copy saved)")
            continue
        # Edited locally (or a template of unknown origin): keep it.
        if base is None or base != plugin_hash:
            if not dry_run:
                _copy(item.source, dest.with_name(dest.name + ".new"), False)
            report["conflicts"].append(item.dest)
        else:
            report["kept"].append(item.dest)

    # Files recorded earlier that the plugin no longer ships.
    shipped = {item.dest for item in items}
    for dest_rel, entry in sorted(recorded.items()):
        if dest_rel in shipped or not isinstance(entry, dict):
            if dest_rel in shipped and dest_rel not in new_files:
                new_files[dest_rel] = entry  # a component not selected this run
            continue
        dest = pka / dest_rel
        if not dest.is_file():
            continue
        if sha256_file(dest) == entry.get("sha256"):
            if not dry_run:
                backups.save(dest_rel)
            report["obsolete_moved"].append(dest_rel)
        else:
            report["obsolete_kept"].append(dest_rel)
            new_files[dest_rel] = entry

    # Retired helpers the manifest never recorded (a workspace from before the
    # manifest): nothing says whether they were edited, so they stay.
    for name in RETIRED:
        if name not in recorded and (pka / name).is_file():
            report["retired_unmanaged"].append(name)

    if backups.root is not None:
        report["backups"] = backups.root.relative_to(root).as_posix()

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "plugin_version": __version__,
        "files": {name: new_files[name] for name in sorted(new_files)},
    }
    rendered = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    current = manifest_path.read_text(encoding="utf-8") if manifest_path.is_file() else None
    report["manifest_changed"] = rendered != current
    if not dry_run and rendered != current:
        tmp = manifest_path.with_name("." + MANIFEST_NAME + ".pka-tmp")
        tmp.write_text(rendered, encoding="utf-8")
        os.replace(str(tmp), str(manifest_path))
    return report


def status(root: Path) -> Tuple[Optional[str], int]:
    """(plugin version recorded in the manifest, number of files), for `status`."""
    path = Path(root) / ".pka" / MANIFEST_NAME
    if not path.is_file():
        return None, 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, 0
    if not isinstance(data, dict):
        return None, 0
    files = data.get("files")
    version = data.get("plugin_version")
    return (version if isinstance(version, str) else None), (len(files) if isinstance(files, dict) else 0)
