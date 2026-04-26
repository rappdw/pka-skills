#!/usr/bin/env python3
"""Reference implementation of the Obsidian mechanical retrofit.

Mirrors the algorithm in
`pka-skills/skills/pka-bootstrap/references/obsidian-bootstrap.md`. Used by the
shell test harness in `pka-skills/tests/`.

Hard rules (from the spec):
  - No body reading. Frontmatter parsing only.
  - Merge, never overwrite existing fields.
  - Skip files with malformed YAML frontmatter; flag them in the summary.
  - Idempotent: re-running on the same state produces no further changes.
  - Use only filename and folder structure as inputs (plus existing frontmatter).

This script is a thin, deterministic encoding of the algorithm. Claude (the
skill's actual executor) follows the same algorithm by reading the reference
document.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional


# ---------- frontmatter helpers ----------

FENCE = "---"


def parse_frontmatter(text: str) -> tuple[Optional[dict], str, Optional[str]]:
    """Return (parsed_dict, body, error). dict is None if no frontmatter.
    error is a string when frontmatter exists but is malformed.
    """
    if not text.startswith(FENCE + "\n") and not text.startswith(FENCE + "\r\n"):
        return None, text, None
    end = text.find("\n" + FENCE, 4)
    if end < 0:
        return None, text, "no closing --- fence"
    yaml_text = text[4:end]
    body_start = end + len("\n" + FENCE)
    if body_start < len(text) and text[body_start] == "\n":
        body_start += 1
    body = text[body_start:]
    parsed: dict = {}
    for raw_line in yaml_text.splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9_\-]+):\s*(.*)$", line)
        if not m:
            return None, text, f"unparseable line: {raw_line!r}"
        key = m.group(1)
        value = m.group(2).strip()
        # Detect "unquoted colon in scalar value" — a common malformed pattern.
        # If value is unquoted and contains a colon followed by a space and
        # more text, the YAML parser would interpret it as a nested mapping.
        if value and not (value.startswith(("'", '"', "[", "{"))):
            stripped = value
            if re.search(r":\s+\S", stripped):
                return None, text, f"unquoted colon in value for key {key!r}"
        parsed[key] = value
    return parsed, body, None


def render_frontmatter(d: dict) -> str:
    out = [FENCE]
    for k, v in d.items():
        out.append(f"{k}: {v}")
    out.append(FENCE)
    return "\n".join(out) + "\n"


# ---------- pattern detection ----------

DATE_RE = r"(\d{4}-\d{2}-\d{2})"

PATTERN_RULES = [
    {
        "name": "1on1",
        "match": re.compile(
            r"personnel/(?P<person>[^/]+)/(?P<date>\d{4}-\d{2}-\d{2})-(?:1on1|1-1)\.md$"
        ),
        "field_set": lambda m: {
            "type": "1on1",
            "date": m.group("date"),
            "person": f'"[[personnel/{m.group("person")}/index]]"',
            "tags": "[1on1]",
        },
    },
    {
        "name": "meeting-leadership",
        "match": re.compile(r"leadership/(?P<date>\d{4}-\d{2}-\d{2})-(?P<topic>[^/]+)\.md$"),
        "field_set": lambda m: {
            "type": "meeting",
            "date": m.group("date"),
            "topic": m.group("topic"),
            "attendees": "[]",
            "tags": "[meeting, leadership]",
        },
    },
    {
        "name": "meeting-techcouncil",
        "match": re.compile(r"TechCouncil/(?P<date>\d{4}-\d{2}-\d{2})-(?P<topic>[^/]+)\.md$"),
        "field_set": lambda m: {
            "type": "meeting",
            "date": m.group("date"),
            "topic": m.group("topic"),
            "attendees": "[]",
            "tags": "[meeting, techcouncil]",
        },
    },
    {
        "name": "daily",
        "match": re.compile(r"lab-notebook/(?P<date>\d{4}-\d{2}-\d{2})\.md$"),
        "field_set": lambda m: {
            "date": m.group("date"),
            "tags": "[daily]",
        },
    },
]


def match_pattern(rel_path: str):
    for rule in PATTERN_RULES:
        m = rule["match"].search(rel_path)
        if m:
            return rule, m
    return None, None


# ---------- domain tag derivation ----------

def domain_for(rel_path: str) -> Optional[str]:
    """Top-level folder name -> kebab-case domain tag."""
    parts = rel_path.split("/")
    # rel_path is relative to vault root, so first segment is the domain
    if not parts:
        return None
    folder = parts[0]
    # Strip _MOC.md and similar — those aren't files we tag.
    if folder.startswith("_") or folder.endswith(".md"):
        return None
    return re.sub(r"([a-z])([A-Z])", r"\1-\2", folder).lower()


def merge_tags(existing: Optional[str], new_tag: str) -> str:
    """Tags are stored as `[tag1, tag2, ...]` strings here for our minimal renderer."""
    if not existing:
        return f"[{new_tag}]"
    s = existing.strip()
    if s.startswith("[") and s.endswith("]"):
        body = s[1:-1].strip()
        items = [x.strip() for x in body.split(",")] if body else []
        if new_tag in items:
            return existing
        items.append(new_tag)
        return "[" + ", ".join(items) + "]"
    return existing  # don't try to mangle other formats


# ---------- de-slugification ----------

def de_slugify(folder: str) -> str:
    parts = folder.split("-")
    return " ".join(p.capitalize() for p in parts if p)


# ---------- the bootstrap ----------

def bootstrap(workspace: Path) -> dict:
    knowledge = workspace / "knowledge"
    if not (knowledge / ".obsidian").exists():
        raise SystemExit(
            "No Obsidian vault detected at knowledge/.obsidian/. "
            "The Obsidian bootstrap is a no-op outside an Obsidian vault."
        )
    summary = {
        "moc_created": [],
        "moc_already_present": [],
        "person_indexes_created": [],
        "person_indexes_already_present": [],
        "frontmatter_added": [],
        "domain_tags_merged": [],
        "malformed_frontmatter": [],
        "files_total": 0,
    }

    # 1. Walk the vault.
    files = []
    domains = set()
    sub_domains = []  # (parent_rel, child_rel)
    personnel_subfolders = []
    for p in sorted(knowledge.rglob("*")):
        if any(seg.startswith(".") for seg in p.relative_to(knowledge).parts):
            continue
        if p.is_dir():
            rel = p.relative_to(knowledge).as_posix()
            depth = rel.count("/")
            if depth == 0:
                domains.add(rel)
            if rel.startswith("personnel/") and depth == 1:
                personnel_subfolders.append(rel)
            # track sub-domains for any depth==1 that isn't personnel/<name>
            if depth == 1 and not rel.startswith("personnel/"):
                parent = rel.split("/", 1)[0]
                sub_domains.append((parent, rel))
        elif p.is_file() and p.suffix == ".md" and p.name != "_MOC.md":
            files.append(p)

    summary["files_total"] = len(files)

    # 2. MOC stubs for every top-level domain (plus sub-domains discovered).
    moc_targets = set()
    moc_targets.add(("", knowledge))  # vault root MOC
    for d in domains:
        moc_targets.add((d, knowledge / d))
    for parent, sub in sub_domains:
        moc_targets.add((sub, knowledge / sub))

    for rel, dirpath in sorted(moc_targets):
        moc_path = dirpath / "_MOC.md"
        rel_label = rel or "(vault root)"
        if moc_path.exists():
            summary["moc_already_present"].append(rel_label)
            continue
        # Build content
        title = rel.split("/")[-1] if rel else dirpath.name
        immediate_files = sorted(
            f for f in dirpath.iterdir()
            if f.is_file() and f.suffix == ".md" and f.name != "_MOC.md"
        )
        immediate_subdirs = sorted(
            f for f in dirpath.iterdir()
            if f.is_dir() and not f.name.startswith(".")
        )
        lines = [f"# {title or knowledge.name}", ""]
        lines.append("<!-- MOC stub created by pka-bootstrap (obsidian). User can reorganize freely. -->")
        lines.append("")
        if immediate_files:
            lines.append("## Files")
            for f in immediate_files:
                stem = f.stem
                lines.append(f"- [[{(f.relative_to(knowledge).as_posix()).rsplit('.md', 1)[0]}|{stem}]]")
            lines.append("")
        if immediate_subdirs:
            lines.append("## Subdomains")
            for sub in immediate_subdirs:
                if sub.name.startswith("personnel"):
                    continue
                lines.append(f"- [[{sub.relative_to(knowledge).as_posix()}/_MOC|{sub.name}]]")
            lines.append("")
        moc_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        summary["moc_created"].append(rel_label)

    # 3. Person index stubs.
    for personnel_rel in personnel_subfolders:
        folder_name = personnel_rel.split("/")[-1]
        idx = knowledge / personnel_rel / "index.md"
        if idx.exists():
            summary["person_indexes_already_present"].append(personnel_rel)
            continue
        display = de_slugify(folder_name)
        notes = sorted(
            f for f in (knowledge / personnel_rel).iterdir()
            if f.is_file() and f.suffix == ".md" and f.name != "index.md"
        )
        body_lines = [f"# {display}", "", "## Notes"]
        for n in notes:
            body_lines.append(f"- [[{n.relative_to(knowledge).as_posix().rsplit('.md', 1)[0]}|{n.stem}]]")
        text = (
            f'---\ntype: person\nname: {display}\nrole: ""\norg: ""\ntags: [person]\n---\n\n'
            + "\n".join(body_lines).rstrip() + "\n"
        )
        idx.write_text(text, encoding="utf-8")
        summary["person_indexes_created"].append(personnel_rel)

    # 4. + 5. Filename-pattern frontmatter and domain tag merging.
    for fpath in files:
        rel = fpath.relative_to(knowledge).as_posix()
        # Skip person index files — handled in step 3.
        if rel.endswith("/index.md"):
            continue
        original = fpath.read_text(encoding="utf-8")
        front, body, err = parse_frontmatter(original)
        if err:
            summary["malformed_frontmatter"].append(f"{rel}: {err}")
            continue

        rule, m = match_pattern(rel)

        if front is None:
            new_front: dict = {}
            if rule:
                new_front.update(rule["field_set"](m))
            domain = domain_for(rel)
            if domain:
                if "tags" in new_front:
                    new_front["tags"] = merge_tags(new_front["tags"], domain)
                else:
                    new_front["tags"] = f"[{domain}]"
            if not new_front:
                continue
            fpath.write_text(render_frontmatter(new_front) + "\n" + body if body else render_frontmatter(new_front),
                             encoding="utf-8")
            if rule:
                summary["frontmatter_added"].append(rel)
            else:
                summary["domain_tags_merged"].append(rel)
        else:
            # Merge missing schema fields and ensure domain tag is in tags.
            changed = False
            if rule:
                for k, v in rule["field_set"](m).items():
                    if k not in front:
                        front[k] = v
                        changed = True
            domain = domain_for(rel)
            if domain:
                merged = merge_tags(front.get("tags"), domain)
                if merged != front.get("tags"):
                    front["tags"] = merged
                    changed = True
            if changed:
                fpath.write_text(render_frontmatter(front) + body, encoding="utf-8")
                if rule and rel not in summary["frontmatter_added"]:
                    summary["frontmatter_added"].append(rel)
                else:
                    summary["domain_tags_merged"].append(rel)

    return summary


def print_summary(s: dict) -> None:
    print("Obsidian bootstrap summary")
    print("------------------------------")
    print(f"MOC stubs created:       {len(s['moc_created'])} ({len(s['moc_already_present'])} already present)")
    print(f"Person indexes created:  {len(s['person_indexes_created'])} ({len(s['person_indexes_already_present'])} already present)")
    print(f"Frontmatter added:       {len(s['frontmatter_added'])} files")
    print(f"Domain tags merged:      {len(s['domain_tags_merged'])} files")
    print(f"Total files in vault:    {s['files_total']}")
    if s["malformed_frontmatter"]:
        print(f"Files SKIPPED (malformed frontmatter): {len(s['malformed_frontmatter'])}")
        for e in s["malformed_frontmatter"]:
            print(f"  - {e}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Obsidian mechanical retrofit (test harness companion to pka-bootstrap).")
    ap.add_argument("--workspace", required=True, help="Workspace root (containing knowledge/).")
    args = ap.parse_args()
    s = bootstrap(Path(args.workspace).resolve())
    print_summary(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
