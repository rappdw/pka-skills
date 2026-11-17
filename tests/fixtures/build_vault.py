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


def main() -> int:
    if len(sys.argv) != 2:
        sys.stderr.write("usage: build_vault.py <destination>\n")
        return 64
    build(Path(sys.argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
