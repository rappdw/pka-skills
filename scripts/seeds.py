#!/usr/bin/env python3
"""Keep the seed text in one place.

The seeds that bootstrap writes into a workspace live in the pka-bootstrap
references, as markdown:

  skills/pka-bootstrap/references/role-definitions.md   the three role files
  skills/pka-bootstrap/references/obsidian-conventions.md   .pka/roles/_obsidian.md

`bootstrap-assets/scripts/upgrade-roles.py` runs inside a workspace, where
the plugin's references may not be readable, so it carries copies: whole
shared-reference seeds, and the H2 sections it adds to existing role files.
This script regenerates those copies from the references.

    python3 scripts/seeds.py --check    exit 1 if any copy differs (CI runs this)
    python3 scripts/seeds.py --write    rewrite the copies in upgrade-roles.py
    python3 scripts/seeds.py --write --from-history
                                        also record every version found in git history

Edit the references, then run --write. Never edit the copies by hand.

--write also maintains KNOWN_SECTION_HASHES in upgrade-roles.py: a hash of
every version of each seeded section that has ever been current. It is
append-only, so the record survives a shallow clone; `upgrade-roles.py
--refresh` replaces a workspace's section only when its text matches one of
them (the user never edited it). --check fails if a current section is not
recorded. Hashes are only ever taken from this repository's public history.

Hashes of sections that are no longer seeded stay in the table (the sections
of the removed `_git-protocol.md`, the commit/push sections of the role
files): `upgrade-roles.py` uses them to tell an untouched obsolete section,
which `--refresh` removes, from one the user edited, which it leaves.

A seed is found by its heading range, not by its fence: the seeds contain
fenced examples of their own, so the outer fence is the first ```` or
```markdown line after the heading and the last fence line before the next
seed. Within a role seed, a section runs from its `## ` heading to the next
`## ` heading outside an inner fence.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REPO = Path(__file__).resolve().parent.parent
REFS = REPO / "skills" / "pka-bootstrap" / "references"
UPGRADE = REPO / "bootstrap-assets" / "scripts" / "upgrade-roles.py"

ROLE_SEEDS = {"orchestrator": "## Seed Role: @orchestrator",
              "researcher": "## Seed Role: @researcher",
              "librarian": "## Seed Role: @librarian"}
SHARED_SEEDS = {"OBSIDIAN_SEED": REFS / "obsidian-conventions.md"}
# Which upgrade-roles.py list carries which role's (or shared file's) sections.
SECTION_LISTS = {
    "ORCHESTRATOR_SECTIONS": ("role", "orchestrator"),
    "LIBRARIAN_SECTIONS": ("role", "librarian"),
    "LIBRARIAN_SECTIONS_V161": ("role", "librarian"),
    "RESEARCHER_SECTIONS": ("role", "researcher"),
    "OBSIDIAN_SECTIONS_V161": ("shared", "OBSIDIAN_SEED"),
    "OBSIDIAN_SECTIONS_V170": ("shared", "OBSIDIAN_SEED"),
}
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def _seed_block(lines: List[str], start: int, stop: int) -> List[str]:
    """Lines inside the outer fence that opens after `start` and closes
    before `stop` (the last fence line in the range)."""
    opener = None
    for idx in range(start, stop):
        if _FENCE.match(lines[idx]):
            opener = idx
            break
    if opener is None:
        raise SystemExit("no fenced seed after line %d" % (start + 1))
    closer = None
    for idx in range(stop - 1, opener, -1):
        if _FENCE.match(lines[idx]) and lines[idx].strip().strip("`~") == "":
            closer = idx
            break
    if closer is None:
        raise SystemExit("seed opened at line %d is never closed" % (opener + 1))
    return lines[opener + 1:closer]


def role_seed(name: str, text: str = None) -> List[str]:
    if text is None:
        text = (REFS / "role-definitions.md").read_text(encoding="utf-8")
    lines = text.split("\n")
    start = lines.index(ROLE_SEEDS[name])
    stop = len(lines)
    for idx in range(start + 1, len(lines)):
        if lines[idx].startswith("## Seed Role:") or lines[idx] == "## Roster File":
            stop = idx
            break
    return _seed_block(lines, start + 1, stop)


def shared_seed(path: Path, text: str = None) -> List[str]:
    if text is None:
        text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    start = next(idx for idx, line in enumerate(lines) if line.startswith("## Seed content"))
    stop = next((idx for idx in range(start + 1, len(lines)) if lines[idx].startswith("## Notes for")), len(lines))
    return _seed_block(lines, start + 1, stop)


def sections(seed: List[str]) -> Dict[str, str]:
    """{`## heading`: body} for a seed. The body is the text after the
    heading line up to the next H2, with the blank lines that separate
    sections removed from its end and a single final newline."""
    out: Dict[str, str] = {}
    current = None
    body: List[str] = []
    fence = ""
    for line in seed:
        match = _FENCE.match(line)
        if fence:
            if match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence) \
                    and not line.strip().strip("`~"):
                fence = ""
            body.append(line)
            continue
        if match:
            fence = match.group(1)
            body.append(line)
            continue
        if line.startswith("## "):
            if current is not None:
                out[current] = "\n".join(body).strip("\n") + "\n"
            current = line.rstrip()
            body = []
            continue
        body.append(line)
    if current is not None:
        out[current] = "\n".join(body).strip("\n") + "\n"
    return out


def expected() -> Tuple[Dict[str, str], Dict[str, List[Tuple[str, str]]]]:
    """What upgrade-roles.py should carry: whole seeds, and section lists."""
    module = ast.parse(UPGRADE.read_text(encoding="utf-8"))
    current_lists: Dict[str, List[str]] = {}
    for node in module.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in SECTION_LISTS and isinstance(node.value, ast.List):
                current_lists[name] = [ast.literal_eval(item)[0] for item in node.value.elts]
    shared = {name: "\n".join(shared_seed(path)).strip("\n") + "\n" for name, path in SHARED_SEEDS.items()}
    lists: Dict[str, List[Tuple[str, str]]] = {}
    for name, (kind, source) in SECTION_LISTS.items():
        if kind == "role":
            available = sections(role_seed(source))
        else:
            available = sections(shared[source].split("\n"))
        entries = []
        for heading in current_lists.get(name, []):
            if heading not in available:
                raise SystemExit("%s lists %r, which the reference seed no longer has" % (name, heading))
            entries.append((heading, available[heading]))
        lists[name] = entries
    return shared, lists


def _render_list(entries: List[Tuple[str, str]]) -> str:
    out = ["["]
    for heading, body in entries:
        out.append("    (")
        out.append("        %s," % json.dumps(heading, ensure_ascii=False))
        out.append('        """\\\n' + _escape(body) + '""",')
        out.append("    ),")
    out.append("]")
    return "\n".join(out)


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')


def _upgrade_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("upgrade_roles", str(UPGRADE))
    module = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(module)
    return module


FILE_OF_LIST = {"ORCHESTRATOR_SECTIONS": "orchestrator.md", "LIBRARIAN_SECTIONS": "librarian.md",
                "LIBRARIAN_SECTIONS_V161": "librarian.md", "RESEARCHER_SECTIONS": "researcher.md",
                "OBSIDIAN_SECTIONS_V161": "_obsidian.md", "OBSIDIAN_SECTIONS_V170": "_obsidian.md"}
# GIT_PROTOCOL_SEED is no longer in upgrade-roles.py; the entry is for reading history.
FILE_OF_SEED = {"OBSIDIAN_SEED": "_obsidian.md", "GIT_PROTOCOL_SEED": "_git-protocol.md"}
ROLE_FILES = {"orchestrator": "orchestrator.md", "librarian": "librarian.md", "researcher": "researcher.md"}


def current_hashes(shared: Dict[str, str], lists: Dict[str, List[Tuple[str, str]]], up) -> Dict[str, set]:
    out: Dict[str, set] = {}
    for name, entries in lists.items():
        for heading, body in entries:
            out.setdefault("%s:%s" % (FILE_OF_LIST[name], heading), set()).add(up.section_hash(body))
    for name, seed in shared.items():
        for heading, _, body, end in up.h2_sections(seed):
            out.setdefault("%s:%s" % (FILE_OF_SEED[name], heading), set()).add(up.section_hash(seed[body:end]))
    return out


def _git(*args: str) -> str:
    import subprocess
    proc = subprocess.run(["git", "-C", str(REPO)] + list(args), stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, text=True)
    return proc.stdout if proc.returncode == 0 else ""


def history_hashes(up, wanted: set) -> Dict[str, set]:
    """Hashes of every version of the refreshable sections in git history."""
    out: Dict[str, set] = {}

    def add(key: str, body: str) -> None:
        if key in wanted:
            out.setdefault(key, set()).add(up.section_hash(body))

    paths = {
        "up": "bootstrap-assets/scripts/upgrade-roles.py",
        "roles": "skills/pka-bootstrap/references/role-definitions.md",
        "obs": "skills/pka-bootstrap/references/obsidian-conventions.md",
        "git": "skills/pka-bootstrap/references/git-protocol.md",
    }
    commits = _git("log", "--format=%H", "--", *paths.values()).split()
    for sha in commits:
        text = _git("show", "%s:%s" % (sha, paths["up"]))
        if text:
            try:
                tree = ast.parse(text)
            except SyntaxError:
                tree = None
            for node in (tree.body if tree else []):
                if not (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)):
                    continue
                name = node.targets[0].id
                try:
                    value = ast.literal_eval(node.value)
                except ValueError:
                    continue
                if name in FILE_OF_LIST:
                    for heading, body in value:
                        add("%s:%s" % (FILE_OF_LIST[name], heading), body)
                elif name in FILE_OF_SEED:
                    for heading, _, body, end in up.h2_sections(value):
                        add("%s:%s" % (FILE_OF_SEED[name], heading), value[body:end])
        text = _git("show", "%s:%s" % (sha, paths["roles"]))
        for role, filename in ROLE_FILES.items():
            if text and ROLE_SEEDS[role] in text.split("\n"):
                try:
                    for heading, body in sections(role_seed(role, text)).items():
                        add("%s:%s" % (filename, heading), body)
                except SystemExit:
                    pass
        for key, filename in (("obs", "_obsidian.md"), ("git", "_git-protocol.md")):
            text = _git("show", "%s:%s" % (sha, paths[key]))
            if text and "## Seed content" in text:
                try:
                    seed = "\n".join(shared_seed(Path("x"), text))
                except (SystemExit, StopIteration):
                    continue
                for heading, _, body, end in up.h2_sections(seed + "\n"):
                    add("%s:%s" % (filename, heading), seed[body:end])
    return out


def _render_known(known: Dict[str, set]) -> str:
    out = ["{"]
    for key in sorted(known):
        out.append("    %s: [" % json.dumps(key, ensure_ascii=False))
        for digest in sorted(known[key]):
            out.append('        "%s",' % digest)
        out.append("    ],")
    out.append("}")
    return "\n".join(out)


def render(source: str, from_history: bool = False) -> str:
    shared, lists = expected()
    up = _upgrade_module()
    known: Dict[str, set] = {key: set(values) for key, values in up.KNOWN_SECTION_HASHES.items()}
    for key, values in current_hashes(shared, lists, up).items():
        known.setdefault(key, set()).update(values)
    if from_history:
        for key, values in history_hashes(up, set(known)).items():
            known[key].update(values)
    module = ast.parse(source)
    lines = source.split("\n")
    edits = []
    for node in module.body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)):
            continue
        name = node.targets[0].id
        if name in lists:
            text = _render_list(lists[name])
        elif name == "KNOWN_SECTION_HASHES":
            text = _render_known(known)
        elif name in shared:
            text = '"""\\\n' + _escape(shared[name]) + '"""'
        else:
            continue
        edits.append((node.value.lineno, node.value.col_offset, node.value.end_lineno, node.value.end_col_offset, text))
    for start_line, start_col, end_line, end_col, text in sorted(edits, reverse=True):
        head = lines[start_line - 1][:start_col]
        tail = lines[end_line - 1][end_col:]
        lines[start_line - 1:end_line] = (head + text + tail).split("\n")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--from-history", action="store_true",
                        help="with --write: also record section versions found in git history")
    args = parser.parse_args()
    source = UPGRADE.read_text(encoding="utf-8")
    wanted = render(source, from_history=args.from_history and args.write)
    if args.write:
        if wanted != source:
            UPGRADE.write_text(wanted, encoding="utf-8")
            print("updated %s" % UPGRADE.relative_to(REPO))
        else:
            print("%s is current" % UPGRADE.relative_to(REPO))
        return 0
    if wanted != source:
        import difflib
        diff = difflib.unified_diff(source.split("\n"), wanted.split("\n"), "upgrade-roles.py (now)",
                                    "upgrade-roles.py (from the references)", lineterm="", n=1)
        sys.stdout.write("\n".join(list(diff)[:200]) + "\n")
        sys.stdout.write("\nThe seed copies in upgrade-roles.py differ from the references. "
                         "Run: python3 scripts/seeds.py --write\n")
        return 1
    print("seed copies in %s match the references" % UPGRADE.relative_to(REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
