#!/usr/bin/env python3
"""Build the fixture workspace used by the pka-tools tests.

    python3 tests/fixtures/build_vault.py <destination>

The workspace is generated rather than stored as files so that the awkward
bytes survive: CRLF line endings, a byte-order mark, a file with no final
newline, a file that is not UTF-8, and names with spaces, commas and
non-ASCII letters. Git would normalise several of those.

Every name here is invented (see tests/README.md, "Examples use the fixture
cast only").
"""
from __future__ import annotations

import sys
from pathlib import Path

BOM = b"\xef\xbb\xbf"


def crlf(text: str) -> bytes:
    return text.replace("\n", "\r\n").encode("utf-8")


def lf(text: str) -> bytes:
    return text.encode("utf-8")


CLAUDE_MD = """\
<!-- PKA v1.6 | vendor-agnostic -->

# Sam's Personal Knowledge Assistance

## Storage Mode
Index mode

## Repo Map
<!-- Last updated: 2026-11-01 -->

| Folder | Contents | Organization | Priority | Status | Confidence | Tags |
|--------|----------|-------------|----------|--------|------------|------|
| `knowledge/AI/` | AI strategy and research | by topic | Active | active | High | |
| `knowledge/leadership/` | Leadership meeting notes | by date | Active | active | High | meeting-home |
| `knowledge/personnel/` | Notes per person | by person | Active | active | High | people-home |
| `knowledge/lab-notebook/` | Daily notes | by date | Reference | active | High | |
| `knowledge/reference/` | Scans and reference documents | flat | Reference | active | Medium | |
| `knowledge/archived/` | Old material | flat | Archive | archived | High | |
| `projects/` | Project workspaces | by project | Active | active | High | |
"""

PKAIGNORE = """\
# PKA noise filter
.pka/
.git/
*.pyc
.DS_Store
node_modules/
*.log

# @pka-section: projects
projects/*/*/*
"""

AI_MOC = """\
# AI

Hand-written introduction. The tools must never touch this line.

## Subdomains
- [[AI/northwind/_MOC|Northwind]]

## Files
- [[AI/ai-adoption-research]]
- [[AI/Vendor landscape, 2026]]

## Pointers

My own remark about this table, above it.

| Topic                      | Entities                    | Files                                                          | Notes   |
| :------------------------- | --------------------------- | -------------------------------------------------------------- | ------- |
| northwind-partnership-2026 | sasha-ortega, taylor-brooks | [[AI/northwind/northwind_partnership_proposal\\|the proposal]] | keep me |
| ai-adoption-research       | —                           | [[AI/ai-adoption-research]]                                    |         |

Trailing prose after the table stays where it is.

## Later section

```markdown
## Pointers

| Topic | Entities | Files |
|---|---|---|
| example-inside-a-fence | nobody | [[AI/not-a-real-file]] |
```
"""

LEADERSHIP_MOC = """\
# Leadership

## Files
- [[leadership/2026-04-22-slt-meeting]]

## Pointers

| Topic | Entities | Files |
|---|---|---|
| slt-meeting | priya | [[leadership/2026-04-22-slt-meeting]] |

A note the owner wrote under the table.
"""

RESEARCH = """\
---
# a comment the owner left here
type: brief
date: 2026-03-02
topic: ai-adoption-research
related:
  - "[[AI/Vendor landscape, 2026]]"
tags:
  - research
  - strategy
---

# AI adoption research

Body text. The word northwind appears once here among many others.
"""

VENDOR = """\
# Vendor landscape, 2026

No frontmatter on this one.
"""

JOINT_MEETING = """\
---
type: meeting
date: 2026-04-23
topic: northwind-partnership-2026
attendees: ["[[personnel/priya/index]]", "[[personnel/robin-smith/index|Robin]]", jamie-lin]
tags: [meeting, ai, leadership]   # inline comment
---

# Joint partnership meeting

## Action Items
- [ ] Send Priya the architecture comparison @Sam by 2026-05-01
- [x] Book the room
"""

PROPOSAL = """\
# Northwind partnership proposal

Draft.
"""

UMLAUT = """\
# Übersicht

Notes from Zürich.
"""

SLT_0422 = """\
# SLT meeting

- [ ] Review the Q2 budget proposal @Sam
* [ ] Circulate minutes
- [x] Approve the agenda
"""

SLT_0429 = """\
---
type: meeting
date: 2026-04-29
topic: slt-meeting
attendees: []
tags: [meeting]
---

# SLT meeting

Deferred the vendor decision.
"""

BUDGET_MALFORMED = """\
---
type: meeting
topic: budget review: second pass
tags: [meeting]
---

Body of a note whose frontmatter is not valid YAML.
"""

PRIYA_INDEX = """\
---
type: person
name: Priya Nair
role: Staff Engineer
org: Example Corp
tags: [person]
---

# Priya Nair

Something the owner wrote about Priya.

## Notes
- hand-written bullet
"""

PRIYA_1ON1 = """\
# 1-1 with Priya

- [ ] Follow up on the adapter spike
"""

ROBIN_1ON1 = """\
Talked about the hiring plan.
"""

ZOE_1ON1 = """\
First 1-1.
"""

DAILY_0422 = """\
Worked on the index.
"""

DAILY_0423 = """\
---
date: 2026-04-23
tags: daily
---

A daily note whose tags are a plain string, not a list.
"""

CODE_FENCE = """\
# How the pointer table looks

```markdown
---
type: example
---
- [ ] not a real action item
## Pointers
```

Text after the fence.
"""

NARRATIVE = """\
# SLT sync narrative

The group agreed to revisit the lighthouse rollout in December.
"""

FILES = {
    "CLAUDE.md": lf(CLAUDE_MD),
    ".pkaignore": lf(PKAIGNORE),
    ".pka/session-log.md": lf("## 2026-11-01 | bootstrap | PKA initialized | — | —\n"),
    "owner-inbox/.keep": b"",
    "team-inbox/.keep": b"",
    "knowledge/.obsidian/app.json": lf("{}\n"),
    "knowledge/AI/_MOC.md": lf(AI_MOC),
    "knowledge/AI/ai-adoption-research.md": lf(RESEARCH),
    "knowledge/AI/Vendor landscape, 2026.md": lf(VENDOR),
    "knowledge/AI/build.log": lf("ignored by .pkaignore\n"),
    "knowledge/AI/northwind/2026-04-23-joint-partnership-meeting.md": lf(JOINT_MEETING),
    "knowledge/AI/northwind/northwind_partnership_proposal.md": lf(PROPOSAL),
    "knowledge/AI/northwind/Übersicht – Zürich.md": lf(UMLAUT),
    "knowledge/leadership/_MOC.md": crlf(LEADERSHIP_MOC),
    "knowledge/leadership/2026-04-22-slt-meeting.md": crlf(SLT_0422),
    "knowledge/leadership/2026-04-29-slt-meeting.md": BOM + lf(SLT_0429),
    "knowledge/leadership/2026-05-06-budget review.md": lf(BUDGET_MALFORMED),
    "knowledge/personnel/priya/index.md": lf(PRIYA_INDEX),
    "knowledge/personnel/priya/2026-03-31-1-1-priya.md": lf(PRIYA_1ON1),
    "knowledge/personnel/robin-smith/2026-04-22-1on1.md": lf(ROBIN_1ON1),
    "knowledge/personnel/zoë-åkesson/2026-05-01-1on1.md": lf(ZOE_1ON1),
    "knowledge/lab-notebook/2026-04-22.md": lf(DAILY_0422).rstrip(b"\n"),  # no final newline
    "knowledge/lab-notebook/2026-04-23.md": lf(DAILY_0423),
    "knowledge/reference/report.pdf": b"%PDF-1.4 fake bytes for the fixture\n",
    "knowledge/reference/report.pdf.txt": lf("Extracted text: quarterly lighthouse report.\n"),
    "knowledge/reference/scan.pdf": b"%PDF-1.4 a scan with no text layer\n",
    "knowledge/reference/empty.md": b"",
    "knowledge/reference/latin1.md": b"caf\xe9 au lait\n",
    "knowledge/reference/code-fence.md": lf(CODE_FENCE),
    "knowledge/archived/old-plan.md": lf("# Old plan\n\nArchive priority: not indexed.\n"),
    "projects/orion/CLAUDE.md": lf("# Orion\n\nProject workspace.\n"),
    "projects/orion/src/main.rs": lf("fn main() {}\n"),
    "meeting-notes/2026-11-10_140000_slt-sync/meeting.json": lf('{"title": "SLT sync"}\n'),
    "meeting-notes/2026-11-10_140000_slt-sync/transcript.md": lf("Speaker 1: hello\n"),
    "meeting-notes/2026-11-10_140000_slt-sync/narrative.md": lf(NARRATIVE),
    "meeting-notes/2026-11-10_140000_slt-sync/audio.wav": b"RIFF....WAVE",
    "meeting-notes/2026-11-11-loose-notes.md": lf("Unrouted notes: not indexed.\n"),
}


def build(destination: Path) -> Path:
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for rel, data in FILES.items():
        path = destination / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return destination


# ---------------------------------------------------------------- lint cases
#
# Seeded problems for `pka-tools lint`, added on top of the base vault by the
# lint tests only (other suites count the base vault's files). Each constant
# below names what the test expects lint to say about it.

_WORDS = (
    "lantern harbor copper meadow signal ledger orchard granite ribbon velvet compass timber "
    "pebble feather anchor marble thistle cinder willow saffron quartz ember juniper basalt "
    "hollow canvas drift maple ferry tundra clover walnut prism gravel meadowlark tidewater "
    "sundial birch cobalt heron lichen mortar nettle onyx pewter quill russet sorrel tallow "
    "umber vellum wicker yarrow zephyr alder bramble cedar dune estuary flint gorse"
).split()


def prose(seed: int, count: int) -> str:
    """`count` words of deterministic filler (a small linear generator, so the
    same text on every machine)."""
    state = seed * 2654435761 % 4294967296
    out = []
    for _ in range(count):
        state = (state * 1103515245 + 12345) % 2147483648
        out.append(_WORDS[state % len(_WORDS)])
    return " ".join(out)


def _vary(text: str, every: int) -> str:
    """Replace every `every`-th word, to make a near (or not so near) copy."""
    words = text.split()
    for idx in range(every - 1, len(words), every):
        words[idx] = "changed%d" % idx
    return " ".join(words)


LINT_CLAUDE_MD = CLAUDE_MD + (
    "| `knowledge/topics/` | Topic wikis | by topic | Active | active | High | wiki-home |\n"
    "| `knowledge/empty-area/` | Nothing yet | flat | Reference | active | Low | |\n"
    "| `knowledge/never-made/` | Planned | flat | Reference | active | Low | |\n"
)

CHARTER = ("# Orion charter\n\nThe charter text: what Orion is for, who decides, and how a change to it is agreed. "
           "Long enough to be worth comparing between copies.\n")
ORION_SPEC = ("# Orion spec\n\nA specification that is filed in reference and also kept beside the wiki, so the "
              "wiki has its source next to it. The two copies are the same file.\n")
SUMMARY_BODY = ("Quarterly summary\n\nThe lighthouse programme met its three goals, Northwind renewed for a year, "
                "and the adoption research was accepted by the leadership group.\n")
LONG_NOTE = "# Planning notes\n\n" + prose(1, 400) + "\n"
RAW_NOTES = prose(2, 260)
RECONCILED = "# Reconciled notes\n\n" + prose(3, 500) + "\n\n" + RAW_NOTES + "\n\n" + prose(4, 500) + "\n"
SYNC_NOTE = ("# Sync\n\nA short narrative that the capture directory also holds, word for word, as its narrative: "
             "who was there, what was decided and what happens next.\n")

LINKS_NOTE = """\
# Link forms

Resolving: [[AI/ai-adoption-research|with an alias]], [[AI/ai-adoption-research#Findings]],
[[AI/ai-adoption-research.md]], [[reference/report.pdf]], [[topics/orion/wiki|Orion]],
[relative](../reference/code-fence.md), [encoded](Vendor%20landscape,%202026.md),
[angle](<Vendor landscape, 2026.md>), [with anchor](ai-adoption-research.md#findings),
[[reference/charter]], [[/AI/ai-adoption-research]], [parens](paren%20(1).md),
[by reference][adoption].

[adoption]: ai-adoption-research.md "a title"

Not links to check: [site](https://example.com/missing.md), [mail](mailto:sam@example.com),
[anchor](#top), `[[missing/in-code]]`, \\[[missing/escaped]], <!-- [[missing/in-comment]] -->,
%% [[missing/in-percent]] %%, $$ x[[missing/in-math]] $$, and the call f[i](missing-call.md).

```
[[missing/in-fence]] and [gone](missing-in-fence.md)
```

%%
[[missing/in-percent-block]]
%%

An indented code block follows.

    [[missing/in-indent]] and [gone](missing-in-indent.md)

Broken: [[missing/wikilink|x]], [[missing/heading#Part]], [gone](../reference/gone.md),
[paren](missing(20).md), [[AI/AI-Adoption-Research]], [Case](VENDOR%20landscape,%202026.md),
[dangling][nowhere].

[nowhere]: ../reference/gone-by-reference.md
"""

REFERENCE_MOC = """\
# Reference

## Pointers

| Topic | Entities | Files |
|---|---|---|
| lighthouse-report | — | [[reference/report.pdf]] |
| Lighthouse Report | — | [[reference/vanished]] |
| ai-adoption-research | — | [[AI/ai-adoption-research]] |
"""

ORION_WIKI = """\
---
topic: orion
last-updated: 2026-05-01
source-count: 2
status: active
---

# Orion

## What it is
A platform. See `knowledge/reference/orion-spec.md`.

## Sources
- `knowledge/reference/orion-spec.md` — the specification
- `knowledge/reference/withdrawn.md` — a note that was later removed
- `<path-to-authored-note>` — a placeholder line

## Changelog
- 2026-05-01: Wiki created
"""

ORION_PLATFORM_WIKI = "---\ntopic: Orion\nstatus: active\n---\n\n# Orion platform\n\n## Sources\n"

LINT_FILES = {
    "CLAUDE.md": lf(LINT_CLAUDE_MD),
    # 8a: byte-identical, one filed and linked to, one left in the inbox
    "knowledge/reference/charter.md": lf(CHARTER),
    "team-inbox/charter copy.md": lf(CHARTER),
    # 8a: two identical scans, each with its sidecar (sidecars are never listed)
    "knowledge/reference/report-copy.pdf": b"%PDF-1.4 fake bytes for the fixture\n",
    "knowledge/reference/report-copy.pdf.txt": lf("Extracted text: quarterly lighthouse report.\n"),
    # information only: a wiki's own copy of a file filed elsewhere
    "knowledge/reference/orion-spec.md": lf(ORION_SPEC),
    "knowledge/topics/orion/sources/orion-spec.md": lf(ORION_SPEC),
    "knowledge/topics/orion/wiki.md": lf(ORION_WIKI),
    "knowledge/topics/orion-platform/wiki.md": lf(ORION_PLATFORM_WIKI),
    # 8b: the same text, re-saved with frontmatter, other case and spacing
    "knowledge/AI/summary.md": lf("---\ntags: [ai]\n---\n" + SUMMARY_BODY),
    "knowledge/AI/summary resaved.md": lf(SUMMARY_BODY.upper().replace(" ", "   ")),
    # 8c: a near copy (1 word in 100 changed), a far one (1 in 12), and raw notes inside a longer note
    "knowledge/lab-notebook/2026-06-01-planning.md": lf(LONG_NOTE),
    "knowledge/lab-notebook/2026-06-01-planning-2.md": lf("# Planning notes\n\n" + _vary(prose(1, 400), 100) + "\n"),
    "knowledge/lab-notebook/2026-06-02-different.md": lf("# Planning notes\n\n" + _vary(prose(1, 400), 12) + "\n"),
    "knowledge/leadership/2026-06-03-raw-notes.md": lf(RAW_NOTES + "\n"),
    "knowledge/leadership/2026-06-03-reconciled.md": lf(RECONCILED),
    # not reported: a capture directory holding the same text as a note
    "knowledge/leadership/2026-06-04-sync.md": lf(SYNC_NOTE),
    "knowledge/leadership/2026-06-04_100000_sync/meeting.json": lf("{}\n"),
    "knowledge/leadership/2026-06-04_100000_sync/narrative.md": lf(SYNC_NOTE),
    # 8d: two folders answering to "Rob", and one slug inside another
    "knowledge/personnel/robin-smith/index.md": lf("---\nname: Robin Smith\naliases: [Rob]\n---\n\n# Robin Smith\n"),
    "knowledge/personnel/robin-chen/index.md": lf("---\nname: Robin Chen\naliases: [Rob]\n---\n\n# Robin Chen\n"),
    "knowledge/personnel/priya-nair/index.md": lf("---\nname: Priya Nair\n---\n\n# Priya Nair\n"),
    # 8d: one folder name contained in another, and nothing else in common
    "knowledge/personnel/taylor/2026-06-05-intro.md": lf("Met Taylor.\n"),
    "knowledge/personnel/taylor-brooks/2026-06-06-intro.md": lf("Met Taylor Brooks.\n"),
    # 8d: one topic twice in a MOC; rule 2: a pointer row whose file is gone
    "knowledge/reference/_MOC.md": lf(REFERENCE_MOC),
    # rule 2: every link form
    "knowledge/AI/links.md": lf(LINKS_NOTE),
    "knowledge/AI/paren (1).md": lf("A note whose name has parentheses in it.\n"),
    # rule 1 (the test ages one of them); rule 4
    "team-inbox/unsorted/old-scan.md": lf("left here a month ago\n"),
    "team-inbox/unsorted/new-scan.md": lf("dropped in today\n"),
    "knowledge/empty-area/.keep": b"",
}


def lint_cases(destination: Path) -> Path:
    """Add the seeded lint problems to a workspace built by `build`."""
    destination = Path(destination)
    for rel, data in LINT_FILES.items():
        path = destination / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return destination


def main() -> int:
    if len(sys.argv) != 2:
        sys.stderr.write("usage: build_vault.py <destination>\n")
        return 64
    build(Path(sys.argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
