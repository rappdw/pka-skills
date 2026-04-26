#!/usr/bin/env python3
"""pointer_maintainer.py — reference implementation of the pointer-layer
maintenance algorithm.

Mirrors the algorithm in
`pka-skills/skills/pka-librarian/references/pointer-layer.md`. Used by the
shell test harness in `pka-skills/tests/test_pointer_layer.sh`.

Hard rules (from the spec):
  - Append-only at the row level (existing rows are extended, never deleted,
    reordered, or merged)
  - Idempotent (re-routing the same file produces no diff)
  - Cluster discovery via Jaccard similarity ≥ 0.5
  - Cross-MOC duplication when file has multiple top-level domain tags
  - 8-file soft cap (flag, do not auto-split)
  - No file-body reading (frontmatter + filename + routing-context only)

This is a test companion, not a runtime artifact. Claude (the librarian)
follows the algorithm by reading the reference document at runtime; this
helper exists so the shell tests can drive the algorithm deterministically.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

JACCARD_THRESHOLD = 0.5  # named historically; metric is now slug-coverage
SIZE_CAP = 8

# --- token extraction ---

STOP_WORDS = {
    "the", "and", "for", "with", "to", "of", "in", "on", "at", "by", "an",
    "a", "is", "are", "was", "were", "be", "been", "this", "that", "those",
    "these", "from", "as", "or", "but", "not", "no", "yes", "do", "does", "did",
}


def tokenize(text: str) -> set[str]:
    """Lowercase, split on -_/whitespace, drop stop-words and very-short tokens."""
    if not text:
        return set()
    parts = re.split(r"[-_/\s]+", text.lower())
    return {p for p in parts if len(p) >= 3 and p not in STOP_WORDS}


def candidate_tokens(file_path: str, frontmatter: dict, routing_context: str = "") -> set[str]:
    tokens = set()
    # topic field
    if "topic" in frontmatter and frontmatter["topic"]:
        tokens |= tokenize(str(frontmatter["topic"]))
    # tags
    for tag in frontmatter.get("tags") or []:
        tokens |= tokenize(str(tag))
    # type
    if "type" in frontmatter and frontmatter["type"]:
        tokens |= tokenize(str(frontmatter["type"]))
    # entities
    for field in ("attendees", "person", "related"):
        vals = frontmatter.get(field) or []
        if isinstance(vals, str):
            vals = [vals]
        for v in vals:
            # strip [[wikilink]] brackets if present
            v = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", str(v))
            tokens |= tokenize(v)
    # filename stem (strip date prefix and extension)
    stem = Path(file_path).stem
    stem_no_date = re.sub(r"^\d{4}-\d{2}-\d{2}-?", "", stem)
    tokens |= tokenize(stem_no_date)
    # routing context
    if routing_context:
        tokens |= tokenize(routing_context)
    return tokens


def slug_coverage(slug_tokens: set[str], candidate_tokens: set[str]) -> float:
    """What fraction of the slug's tokens appear in the candidate set?

    This is the cluster-discovery metric for v1.6.1. The spec's "Jaccard"
    framing penalized exact-slug matches when the candidate token set was
    much larger (filename + attendees + tags together swamp a 2-3 token
    slug). Slug-coverage is more forgiving: a candidate that contains all
    of the slug's tokens scores 1.0 regardless of what else it carries.
    Threshold: 0.5. With a 2-token slug, this requires at least 1 token to
    match; with 3 tokens, 2 of 3.
    """
    if not slug_tokens:
        return 0.0
    return len(slug_tokens & candidate_tokens) / len(slug_tokens)


def coin_slug(file_path: str, frontmatter: dict, event_bound: bool = False) -> str:
    """Build a topic slug from frontmatter or filename. Lowercase hyphenated."""
    primary = (
        (frontmatter.get("topic") or "")
        or (next(iter(frontmatter.get("tags") or []), ""))
        or (frontmatter.get("type") or "")
    )
    if not primary:
        primary = re.sub(r"^\d{4}-\d{2}-\d{2}-?", "", Path(file_path).stem)
    slug = re.sub(r"[^a-z0-9]+", "-", str(primary).lower()).strip("-")
    if event_bound:
        # date-suffix from frontmatter `date` if present
        date = frontmatter.get("date") or ""
        m = re.match(r"(\d{4})", str(date))
        if m and m.group(1) not in slug:
            slug = f"{slug}-{m.group(1)}"
    return slug or "uncategorized"


# --- entity extraction ---

def entities_of(frontmatter: dict) -> list[str]:
    """Lowercased, hyphenated entity slugs from frontmatter only.
    Filename heuristics intentionally excluded (too noisy)."""
    raw = []
    for field in ("attendees", "person", "related"):
        vals = frontmatter.get(field) or []
        if isinstance(vals, str):
            vals = [vals]
        for v in vals:
            v = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", str(v))
            v = Path(v).name  # strip path components
            v = re.sub(r"\.md$", "", v)
            raw.append(v)
    # tags that look like entity refs (orgs/products) — heuristic: the tag
    # contains no domain-tag noise like "ai", "leadership", "meeting", etc.
    # In practice we just take all non-domain tags.
    domain_like = {"ai", "leadership", "personnel", "techcouncil", "lab-notebook",
                   "meeting", "1on1", "daily", "brief", "person", "research"}
    for tag in frontmatter.get("tags") or []:
        if tag and tag not in domain_like:
            raw.append(str(tag))
    out = []
    for r in raw:
        slug = re.sub(r"[^a-z0-9-]+", "-", r.lower()).strip("-")
        if slug and slug not in out:
            out.append(slug)
    return sorted(out)


# --- table parsing/serialization ---

POINTERS_HEADER = "## Pointers"
TABLE_HEADER = "| Topic | Entities | Files |"
TABLE_SEPARATOR = "|---|---|---|"
SECTION_PREAMBLE = (
    "Compact retrieval rows maintained by the librarian. Format: one row per "
    "concept cluster. FTS-indexed for fast lookup before expanding to file "
    "bodies."
)


def parse_pointers_section(text: str) -> tuple[Optional[int], Optional[int], list[dict]]:
    """Return (section_start_line, table_start_line, rows). Section_start
    points to the `## Pointers` heading line; table_start points to the
    first data row line. None if the section doesn't exist."""
    lines = text.splitlines()
    sec_idx = None
    for i, ln in enumerate(lines):
        if ln.strip() == POINTERS_HEADER:
            sec_idx = i
            break
    if sec_idx is None:
        return None, None, []
    # Find the separator line after the section heading
    rows: list[dict] = []
    table_start = None
    i = sec_idx + 1
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("## ") and i > sec_idx:
            break
        if ln.strip() == TABLE_SEPARATOR:
            table_start = i + 1
            break
        i += 1
    if table_start is None:
        return sec_idx, None, []
    j = table_start
    while j < len(lines):
        ln = lines[j]
        if not ln.startswith("|") or ln.startswith("## "):
            break
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) >= 3:
            entities = [e.strip() for e in cells[1].split(",") if e.strip()]
            files = [f.strip() for f in cells[2].split(",") if f.strip()]
            rows.append({
                "topic": cells[0],
                "entities": entities,
                "files": files,
                "line": j,
            })
        j += 1
    return sec_idx, table_start, rows


def render_row(row: dict) -> str:
    return f"| {row['topic']} | {', '.join(row['entities'])} | {', '.join(row['files'])} |"


def render_pointers_section(rows: list[dict]) -> str:
    body = [POINTERS_HEADER, "", SECTION_PREAMBLE, "", TABLE_HEADER, TABLE_SEPARATOR]
    for r in rows:
        body.append(render_row(r))
    return "\n".join(body) + "\n"


# --- core operation ---

def update_moc(
    moc_path: Path,
    file_wikilink: str,
    candidate: set[str],
    file_entities: list[str],
    coined_slug: str,
) -> tuple[bool, str]:
    """Apply the pointer-row update to a single MOC file. Idempotent.
    Returns (changed, action) where action is one of:
      'extended' — row updated with new file/entities
      'appended' — new row appended
      'noop'     — file already present in matched row, no change
      'created'  — Pointers section created from scratch
    """
    text = moc_path.read_text(encoding="utf-8") if moc_path.exists() else ""
    sec_idx, table_start, rows = parse_pointers_section(text)

    # Find best-matching existing row by slug-coverage. Tie-break on
    # post-coin slug equality (defense against the edge case where the
    # coined slug is identical to an existing row's slug but slug-coverage
    # somehow falls short — e.g., a 1-token slug where the candidate only
    # contributed via filename heuristics).
    best = None
    best_score = 0.0
    for row in rows:
        score = slug_coverage(tokenize(row["topic"]), candidate)
        if score >= JACCARD_THRESHOLD and score > best_score:
            best, best_score = row, score
    if best is None:
        # Defensive: if the coined slug exactly matches an existing row,
        # extend that row instead of creating a duplicate.
        for row in rows:
            if row["topic"] == coined_slug:
                best = row
                break

    action: str
    if best is not None:
        # Case A: extend
        files_set = set(best["files"])
        new_files = [f for f in [file_wikilink] if f not in files_set]
        new_entities = [e for e in file_entities if e not in best["entities"]]
        if not new_files and not new_entities:
            return False, "noop"
        best["files"] = sorted(set(best["files"] + new_files), key=str.lower)
        best["entities"] = sorted(set(best["entities"] + new_entities), key=str.lower)
        action = "extended"
    else:
        # Case B: append a new row (or create section)
        new_row = {
            "topic": coined_slug,
            "entities": sorted(set(file_entities), key=str.lower),
            "files": [file_wikilink],
        }
        rows.append(new_row)
        action = "appended" if sec_idx is not None else "created"

    # Rebuild the MOC text
    if sec_idx is None:
        # Section didn't exist — append to end of file
        new_section = render_pointers_section(rows)
        if not text.endswith("\n"):
            text += "\n"
        if text.strip():
            text += "\n"
        text += new_section
    else:
        # Replace existing section in place
        lines = text.splitlines()
        # Find end of section: next H2 or EOF
        end = sec_idx + 1
        while end < len(lines) and not lines[end].startswith("## "):
            end += 1
        new_section = render_pointers_section(rows)
        text = "\n".join(lines[:sec_idx]) + ("\n" if sec_idx > 0 else "") + new_section + (
            "\n" + "\n".join(lines[end:]) if end < len(lines) else ""
        )
        # Normalize trailing newline
        if not text.endswith("\n"):
            text += "\n"

    moc_path.parent.mkdir(parents=True, exist_ok=True)
    moc_path.write_text(text, encoding="utf-8")
    return True, action


def maintain(
    workspace: Path,
    file_path_rel: str,           # e.g., "anthropic/2026-04-23-meeting"  (no .md)
    frontmatter: dict,
    routing_context: str = "",
    domain_tags: Optional[list[str]] = None,
) -> dict:
    """Top-level: run pointer maintenance for a routed file across the
    primary destination MOC plus any cross-MOC duplications implied by tags.
    """
    knowledge = workspace / "knowledge"
    candidate = candidate_tokens(file_path_rel, frontmatter, routing_context)
    file_entities = entities_of(frontmatter)
    event_bound = bool(re.search(r"\d{4}-\d{2}-\d{2}", Path(file_path_rel).stem))
    coined = coin_slug(file_path_rel, frontmatter, event_bound=event_bound)

    file_wikilink = f"[[{file_path_rel}]]"

    # Primary MOC = first segment of the file path under knowledge/
    parts = file_path_rel.split("/")
    primary_domain = parts[0] if parts else ""
    primary_moc = knowledge / primary_domain / "_MOC.md"

    # Cross-MOC targets from tags (only top-level folders that exist or that we'd create)
    moc_paths = [primary_moc]
    if domain_tags is None:
        domain_tags = list(frontmatter.get("tags") or [])
    for t in domain_tags:
        if not t:
            continue
        if t == primary_domain:
            continue
        # Only treat as a domain tag if a corresponding folder exists at vault root
        candidate_path = knowledge / t / "_MOC.md"
        if (knowledge / t).is_dir() or candidate_path.exists():
            moc_paths.append(candidate_path)

    actions: dict[str, str] = {}
    overflow_rows: list[str] = []
    for moc in moc_paths:
        _, action = update_moc(moc, file_wikilink, candidate, file_entities, coined)
        actions[str(moc.relative_to(workspace))] = action
        # Re-parse to check size cap
        _, _, rows = parse_pointers_section(moc.read_text(encoding="utf-8"))
        for row in rows:
            if len(row["files"]) >= SIZE_CAP:
                overflow_rows.append(f"{moc.relative_to(workspace)}: {row['topic']} ({len(row['files'])} files)")

    return {
        "actions": actions,
        "overflow_rows": overflow_rows,
        "candidate_tokens": sorted(candidate),
        "coined_slug": coined,
    }


def rewrite_renames(workspace: Path, mapping: dict[str, str]) -> int:
    """Walk all `_MOC.md` files; rewrite [[old_path]] → [[new_path]] for each
    mapping entry. Returns total number of rewrites. Idempotent."""
    knowledge = workspace / "knowledge"
    if not knowledge.is_dir():
        return 0
    total = 0
    for moc in knowledge.rglob("_MOC.md"):
        text = moc.read_text(encoding="utf-8")
        new_text = text
        for old, new in mapping.items():
            old_link = f"[[{old}]]"
            new_link = f"[[{new}]]"
            count = new_text.count(old_link)
            if count:
                new_text = new_text.replace(old_link, new_link)
                total += count
        if new_text != text:
            moc.write_text(new_text, encoding="utf-8")
    return total


def lint_broken_pointers(workspace: Path) -> list[dict]:
    """Find pointer-row wikilinks that resolve to nonexistent files.
    Returns a list of dicts with {moc, topic, broken_link}."""
    knowledge = workspace / "knowledge"
    if not knowledge.is_dir():
        return []
    broken: list[dict] = []
    for moc in knowledge.rglob("_MOC.md"):
        text = moc.read_text(encoding="utf-8")
        _, _, rows = parse_pointers_section(text)
        for row in rows:
            for fileref in row["files"]:
                m = re.match(r"\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]", fileref)
                if not m:
                    continue
                target = m.group(1)
                # Resolve relative to knowledge/
                target_path = knowledge / (target + ".md")
                if not target_path.exists():
                    broken.append({
                        "moc": str(moc.relative_to(workspace)),
                        "topic": row["topic"],
                        "broken_link": fileref,
                    })
    return broken


def main() -> int:
    ap = argparse.ArgumentParser(description="Pointer-layer maintenance test companion.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("route", help="Apply pointer maintenance for a routed file")
    p1.add_argument("--workspace", required=True)
    p1.add_argument("--file", required=True, help="Vault-relative path without .md, e.g. AI/foo")
    p1.add_argument("--frontmatter", required=True, help="JSON dict")
    p1.add_argument("--routing-context", default="")
    p1.add_argument("--domain-tags", default="", help="Comma-separated additional domain tags")

    p2 = sub.add_parser("rename", help="Rewrite pointer-row wikilinks for renamed files")
    p2.add_argument("--workspace", required=True)
    p2.add_argument("--mapping", required=True, help="JSON dict {old_path: new_path}")

    p3 = sub.add_parser("lint", help="Report broken pointer-row wikilinks")
    p3.add_argument("--workspace", required=True)

    args = ap.parse_args()

    if args.cmd == "route":
        ws = Path(args.workspace).resolve()
        fm = json.loads(args.frontmatter)
        domain_tags = [t.strip() for t in args.domain_tags.split(",") if t.strip()] or None
        result = maintain(ws, args.file, fm, args.routing_context, domain_tags)
        print(json.dumps(result, indent=2))
        return 0
    if args.cmd == "rename":
        ws = Path(args.workspace).resolve()
        mapping = json.loads(args.mapping)
        n = rewrite_renames(ws, mapping)
        print(json.dumps({"rewrites": n}))
        return 0
    if args.cmd == "lint":
        ws = Path(args.workspace).resolve()
        broken = lint_broken_pointers(ws)
        print(json.dumps({"broken": broken}, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
