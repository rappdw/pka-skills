# Changelog

## v1.5.0 — 2026-04-05

### Added
- **pka-wiki** skill — topic wiki lifecycle (create, ingest, query, list, retire). LLM-maintained synthesis pages that cite authored notes. Inspired by Karpathy's LLM wiki pattern, adapted to PKA's files-are-source-of-truth model. Ingest always requires confirmation regardless of autonomy level.
- **Librarian lint** — 7-rule non-destructive health check (orphan files, broken links, stale wiki sources, empty Repo Map folders, missing back-references, contradiction candidates, uncited wiki claims). Reports to `owner-inbox/librarian-lint-<date>.md`; never auto-fixes.
- **`wiki-home` Repo Map tag** — structural detection of topic wiki folders (subfolders containing `wiki.md`); default location `knowledge/topics/`.
- **@researcher wiki mode** — role now maintains topic wikis with section-level diffs, not one-shot rewrites. Every wiki claim cites a source.
- **Tutorial modules 8 and 9** — Topic Wikis and Health Checks added to onboarding curriculum.

### Changed
- Bootstrap inference guide detects wiki-home folders during scan
- CLAUDE.md template documents `wiki-home` tag alongside `meeting-home`
- Librarian description and capabilities expanded to include lint
- @researcher role definition adds topic wiki maintenance as competency

### Skills
- `pka-wiki` v1.0.0 (new)
- `pka-librarian` v1.5.0 (lint capability added)
- `pka-bootstrap` v1.5.0 (wiki-home inference, researcher wiki-mode)
- `pka-tutorial` v1.1.0 (modules 8 and 9)

## v1.4.0 — 2026-04-05

### Added
- **pka-tutorial** skill — conversational onboarding and capability walkthrough for new users. 7 teaching modules (orientation, finding things, inbox pattern, meeting capture, dashboard, project lifecycle, role system) grounded in the user's actual Repo Map. Complements `docs/TUTORIAL.md` (reference doc) as the interactive counterpart.

### Skills
- `pka-tutorial` v1.0.0 (new)

## v1.3.0 — 2026-04-03

### Added
- **Owner profile** — bootstrap now captures role, domain expertise, communication style, and goals during Q1 interview; generates `.pka/owner-profile.md` referenced by all roles
- **Communication style** in CLAUDE.md template — roles adapt output format and depth to owner preferences
- **Decision log** — `.pka/decision-log.md` captures reasoning behind structural decisions (archive, mode switch, role additions); complements the action-oriented session log
- **Personal context portfolio** concept — documented in README; the owner profile, decision log, session history, and Repo Map form a portable, agent-maintained representation of the owner
- **Future scope: pka-mcp** — README notes MCP server as natural evolution for exposing PKA as a tool surface

### Changed
- Bootstrap Phase 2 Q1 expanded from name-only to lightweight profile interview (max 5 questions total)
- Bootstrap Phase 3 output steps renumbered to include owner profile (3e) and decision log (3h)
- `.pka/` directory structure now includes `owner-profile.md` and `decision-log.md`

### Skills
- `pka-bootstrap` v1.3.0

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
