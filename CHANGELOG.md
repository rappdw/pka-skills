# Changelog

## v1.2.0 — 2026-04-01

### Added
- **pka-meetings** skill — full meeting documentation pipeline
  - Four modes: capture, reconcile, route-only, full pipeline
  - Orchestrates thinkkit's `take-notes` and `resolve-against-transcript` when available
  - Smart routing into knowledge base using Repo Map meeting-home tags
  - Attendee linking against personnel records
  - Action item extraction and session log integration
  - Graceful degradation when thinkkit is not installed
- Bootstrap inference now detects `meeting-home` folders from date-slug filenames
- Librarian transcript awareness — holds `.vtt`/`.srt` files for pka-meetings instead of auto-routing
- CLAUDE.md template includes transcript handling conventions in inbox section
- Repo Map `meeting-home` tag for meeting note destination folders
- Tutorial documentation at `docs/TUTORIAL.md`

### Changed
- Repo Map table now includes Tags column for meeting-home and future tags
- Session start protocol scans for transcript files in team-inbox
- Librarian pre-flight includes transcript detection before any routing

### Skills
- `pka-bootstrap` v1.2.0
- `pka-librarian` v1.2.0
- `pka-interface` v1.2.0
- `pka-meetings` v1.0.0 (new)
