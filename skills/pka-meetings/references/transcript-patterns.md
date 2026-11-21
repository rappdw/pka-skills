# Transcript File Patterns

Detection patterns for meeting transcript files in `team-inbox/` and earshot capture directories. Used by `pka-meetings` pre-flight and by the librarian's transcript awareness check.

---

## Earshot Capture Directories

[earshot](https://github.com/rappdw/earshot) records meetings locally and writes capture directories named `YYYY-MM-DD_HHMMSS[_<title>]/`. Detection is **marker-based, not path-based**: any directory containing a `meeting.json` file is an earshot capture, wherever it lives. In an earshot+PKA workspace they typically sit under `meeting-notes/` (earshot's output root is configurable).

### Capture Directory Contents

| File | Purpose |
|------|---------|
| `meeting.json` | Marker + metadata — presence of this file identifies the capture |
| `*.wav` | Recorded audio |
| `transcript.json` | Diarized transcript (machine format) |
| `transcript.md` | Diarized transcript (readable — use this for reconciliation) |
| `notes.md` | Machine notes |
| `narrative.md` | Meeting narrative from earshot's meeting-narrative skill — richest artifact when present |

### Detection Logic

```python
from pathlib import Path

def find_earshot_captures(root: Path) -> list[Path]:
    """Find earshot capture directories: any dir containing meeting.json."""
    return sorted(p.parent for p in root.rglob("meeting.json"))

def is_mode2_candidate(capture: Path) -> bool:
    """A capture with a transcript but no reconciliation yet."""
    return (capture / "transcript.md").exists()
```

A capture with `transcript.md` but no reconciled note is a Mode 2 candidate, same as a detected Zoom transcript. To check whether reconciliation happened, look for a routed/filed notes file whose `**Recording**:` header points at the capture directory (or a same-date session-log entry referencing it).

### Handling Rules

- **Never move, rename, or delete capture directories.** Routing files notes; captures stay where earshot wrote them.
- Reconcile in place: pass `<capture-dir>/transcript.md` to `resolve-against-transcript`.
- The transcript-disposition question (keep/archive/delete) does **not** apply to capture artifacts — they always stay in the capture directory.
- Notes created by thinkkit v0.8.0+ take-notes carry a `**Recording**: <capture-dir>` header. Preserve that line verbatim through routing and rewrites — it stays valid because the capture directory never moves.
- Matching notes to a capture: prefer the `**Recording**:` pointer; fall back to date match on the directory name (`YYYY-MM-DD_HHMMSS`), then title-keyword match on the optional `_<title>` suffix.
- Capture directories must not be covered by `.pkaignore` patterns that would hide `meeting.json` from the scan.

---

## Recognized Patterns

| Pattern | Source | Example |
|---------|--------|---------|
| `GMT*.transcript.vtt` | Zoom auto-save | `GMT20260331-162935_Recording.transcript.vtt` |
| `GMT*.cc.vtt` | Zoom closed captions | `GMT20260331-162935_Recording.cc.vtt` |
| `*_transcript.txt` | Teams download | `Meeting_transcript.txt` |
| `*_transcript.docx` | Teams download | `Meeting_transcript.docx` |
| `transcript*.txt` | Generic | `transcript-2026-03-31.txt` |
| `*.vtt` | Any WebVTT file | `captions.vtt` |
| `*.srt` | Any SRT subtitles | `meeting.srt` |
| `*recording*.txt` | Recording export | `recording-notes.txt` |
| `*recording*.docx` | Recording export | `recording-transcript.docx` |

---

## Detection Logic

### Filename-Based Detection

```python
import re
from pathlib import Path

TRANSCRIPT_PATTERNS = [
    r'GMT.*\.transcript\.vtt$',
    r'GMT.*\.cc\.vtt$',
    r'.*_transcript\.txt$',
    r'.*_transcript\.docx$',
    r'^transcript.*\.txt$',
    r'.*\.vtt$',
    r'.*\.srt$',
    r'.*recording.*\.txt$',
    r'.*recording.*\.docx$',
]

def is_transcript(filename: str) -> bool:
    """Check if a filename matches known transcript patterns."""
    for pattern in TRANSCRIPT_PATTERNS:
        if re.match(pattern, filename, re.IGNORECASE):
            return True
    return False

def find_transcripts(inbox_path: Path) -> list[Path]:
    """Find all transcript files in team-inbox/."""
    return [f for f in inbox_path.iterdir() if f.is_file() and is_transcript(f.name)]
```

### Content-Based Detection (Fallback)

If a `.txt` or `.docx` file doesn't match filename patterns but might be a transcript, check content:

1. Read first 20 lines
2. Look for timestamp patterns:
   - WebVTT: `00:01:23.456 --> 00:01:25.789`
   - SRT: `00:01:23,456 --> 00:01:25,789`
   - Generic: `[00:01:23]`, `(00:01:23)`, `0:01:23`
3. Look for speaker attribution patterns:
   - `Speaker Name:` at line start
   - `[Speaker Name]` at line start
   - `SPEAKER NAME:` (all caps)
4. If 3+ timestamp lines found in first 20 lines: treat as transcript

---

## Handling Rules

### In team-inbox/
- Transcript files are **held, not routed** by the librarian
- The orchestrator flags them at session start
- `pka-meetings` processes them via the reconcile workflow

### In .pkaignore
- `.vtt` and `.srt` files must **NOT** be in `.pkaignore`
- Transcript patterns must not appear in the ignore list
- They need to remain visible to the detection system

### Disposition Options
After reconciliation, the user chooses what to do with the transcript:
1. **Keep in team-inbox/** — leave as-is for future reference
2. **Archive** — move to a `transcripts/` subfolder at the meeting note's destination
3. **Delete** — remove after confirmation (never auto-delete)

Default: keep in team-inbox/. The user can always clean up later.

---

## Matching Transcripts to Notes

When reconciling, `pka-meetings` needs to find the matching notes for a transcript.

### When No Notes Match

`pka-meetings` offers to write notes from the transcript. This is PKA's own step and does not depend on thinkkit, which has no skill that turns a transcript into notes: with or without thinkkit the offer is the same, and the notes are written only on the user's yes. They carry a `**Source**: written from transcript <file>, not checked against notes taken in the meeting` header line, use speaker labels exactly as the transcript gives them, and skip reconciliation (there is nothing independent to reconcile against). The procedure is "Notes from a transcript" in the pka-meetings skill.

What does need thinkkit is checking existing notes against a transcript (`resolve-against-transcript`). Without it, existing notes are filed as they are and the user is told the check was skipped.

### Matching Strategy

1. **Date match:** Extract date from transcript filename (e.g., `GMT20260331` → 2026-03-31). Find notes files created on that date.
2. **Recent match:** If no date in filename, look for notes files created today or in the last 24 hours.
3. **Title match:** If transcript filename contains keywords (meeting name, project name), match against note titles.
4. **Ask the user:** If multiple candidates or no confident match, present options and ask.

### Date Extraction from Transcript Filenames

```python
import re
from datetime import date

def extract_date(filename: str) -> date | None:
    """Try to extract a date from a transcript filename."""
    # GMT format: GMT20260331-162935
    m = re.search(r'GMT(\d{4})(\d{2})(\d{2})', filename)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    
    # ISO format: 2026-03-31
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', filename)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    
    # Compact format: 20260331
    m = re.search(r'(\d{4})(\d{2})(\d{2})', filename)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    
    return None
```
