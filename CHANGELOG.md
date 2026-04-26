# Changelog

## v1.6.1 — 2026-04-26

### Added — Pointer layer for MOC files (closet pattern)

A small set of curated, dense, machine-readable rows inside each `_MOC.md` — one row per concept cluster — that the librarian maintains as files are routed. Sits between FTS queries and file bodies, converting "1,500-file haystack" queries into "30-cluster summary, then 3–5 targeted file reads". No vector store, no embeddings — just markdown table rows that FTS5's BM25 ranks above sparse body matches.

- **New section in `.pka/roles/_obsidian.md`**: "Pointer Layer" — file location, three-column row schema (Topic, Entities, Files), librarian behavior, retrieval behavior, behavior-without-Obsidian, invariants. Layered onto the existing MOC convention; works in plain-markdown workspaces too (the retrieval value comes from FTS, not Obsidian rendering).
- **Librarian per-route step**: after every route into a domain, identify the cluster (slug-coverage similarity ≥ 0.5 against existing topic slugs), update the matching row append-only, OR coin a new slug from frontmatter and append a new row. Cross-MOC duplication when the file's tags imply multiple top-level domains. 8-file soft cap surfaced in the routing summary; the librarian never auto-splits.
- **Indexing tweak**: pointer-table rows tagged `is_pointer = 1` in `search_fts`; retrieval applies `rank * 3.0` to those rows (FTS5 BM25 returns negatives where more negative = better match, so `× 3` makes pointer matches more negative and ranks them above body-level matches).
- **Rename / graduate propagation**: when a file is moved or a project is graduated, every pointer-row wikilink referencing the old path is rewritten across all `_MOC.md` files in the vault. `graduate.sh` does the rewrite as part of the same graduation commit in `knowledge/`.
- **Lint coverage**: existing "broken links" rule (rule 2) now explicitly covers wikilinks inside `_MOC.md` Pointers tables; output annotates the row's topic slug for cleanup targeting.
- **Upgrade path**: `bootstrap upgrade` (introduced in 1.6.0) now also adds the v1.6.1 pointer-layer sections to existing `.pka/roles/_obsidian.md` and `.pka/roles/librarian.md` files. Idempotent and append-only at the section level — never modifies content the user has customized.

### Tests

- Shell suite `tests/test_pointer_layer.sh` covering scenarios PR1–PR6 + cross-MOC duplication: 7 mechanical tests, all passing.
- Python reference impl `tests/pointer_maintainer.py` for deterministic per-route maintenance, rename propagation, and lint scanning.

### Backward compatibility

A workspace bootstrapped on v1.6.0 continues to work identically. The Pointers section is invisible to existing MOC behavior; adding a `## Pointers` section to a v1.6.0 MOC produces a clean diff that the user can commit. No 1.6.0 test scenarios changed.

### Skills

- `pka-bootstrap` v1.6.1 (new sqlite-modes section for pointer indexing; updated obsidian-conventions seed; upgrade-roles helper extended for v1.6.1)
- `pka-librarian` v1.6.1 (pointer-layer routing step; new references `pointer-layer.md`)

Spec: [`docs/specification-addendum.md`](docs/specification-addendum.md) plus the 1.6.1 pointer-layer additions documented inline in `skills/pka-bootstrap/references/obsidian-conventions.md` and `skills/pka-librarian/references/pointer-layer.md`.

## v1.6.0 — 2026-04-26

### Added — Obsidian coexistence (additive; opt-in via bootstrap)

- **Detection**: `obsidian_present := directory_exists("./knowledge/.obsidian")` evaluated once per session. When true, the orchestrator surfaces a one-line greeting and roles enable additive Obsidian-aware behavior. When false, behavior is identical to v1.5.
- **Shared-reference seed**: new `.pka/roles/_obsidian.md` documenting frontmatter schemas (daily, meeting, 1on1, brief, person), wikilink rules, MOC policy, tag conventions, and error handling. Roles link here rather than duplicate.
- **`bootstrap obsidian` target**: one-time mechanical retrofit of an existing vault. Creates `_MOC.md` stubs per top-level domain, person index stubs at `personnel/<name>/index.md`, filename-pattern frontmatter (1on1, meeting, daily). No body reading; idempotent; merges, never overwrites.
- **Librarian per-route enhancements** when `obsidian_present`: frontmatter merge on routed files, MOC append, person backlinks (high-confidence only), wikilink hygiene.
- **Researcher brief frontmatter** (`type: brief`) when briefs land in vault.

### Added — Hybrid monorepo bootstrap (additive; opt-in)

- **`bootstrap git` target**: one-time setup of a `meta`-coordinated hybrid monorepo. Initializes root `.git` (no commit — human-review gate), `knowledge/.git` and each `projects/*/.git` with LFS, generates `.meta` JSON manifest, installs `.pka/` templates and helper scripts.
- **Vendored `bootstrap-assets/`**: `gitattributes-template`, `gitignore-template`, plus scripts `graduate.sh`, `init_project_repos.sh`, `reinit-project-with-lfs.sh`, `push-all.sh`, `build-repo-list.sh`. All are idempotent, network-free, root-no-commit, with typed-confirmation gates on destructive operations.
- **Optional opt-in origin**: `init_project_repos.sh` accepts `ORIGIN_BASE` env var when the user wants to set origin URLs at init time. Default: no origin set.

### Added — Commit/push protocol

- **Shared-reference seed**: new `.pka/roles/_git-protocol.md` documenting commit triggers, message format (`<Role>:` prefix + `Co-Authored-By: Claude` trailer), push triggers, graduation sequence, failure behavior. Activates only when `hybrid_monorepo_present`.
- **Per-role auto-commits** in child repos when `hybrid_monorepo_present`: librarian commits one routing unit per route, researcher commits one brief per save. Each side-effect (MOC update, frontmatter, backlink) rides along in the same commit.
- **Root never auto-commits**. Hard rule across all paths: root-tracked changes are staged for human review and surfaced in the session summary.
- **Session-end consolidated push** via `meta git push` (or fallback `.pka/push-all.sh` iterating `.meta`). Failures surface; session close still proceeds. Empty origins reported as skipped.
- **Mid-session "push now"** uses the same primitive.

### Added — Bootstrap upgrade (`bootstrap upgrade`)

- **`upgrade` target** for users on v1.5 who want the v1.6 additions without losing customizations. Implementation: `bootstrap-assets/scripts/upgrade-roles.py` performs deterministic structured merge (no LLM in the loop) — backs up `.pka/roles/`, seeds missing shared references, appends new H2 sections to existing role files anchored before `## Output Conventions`. Idempotent. Never modifies the body of existing sections; never modifies frontmatter.

### Added — Tests

- **JSON evals** for the 22 spec scenarios (1–11 Obsidian, 12–16 git bootstrap, 17–22 commit/push protocol).
- **Shell test harness** under `tests/`: 4 suites (git-bootstrap, obsidian-bootstrap, commit-protocol, upgrade) totalling 22 mechanical tests. Includes a Python reference implementation of the Obsidian retrofit algorithm for testability.

### Added — Documentation

- `docs/specification-addendum.md` — full spec for the addendum.
- `bootstrap-assets/README.md` — vendored asset contract and provenance.
- New algorithm references in `skills/pka-bootstrap/references/`: `obsidian-conventions.md`, `git-protocol.md`, `obsidian-bootstrap.md`, `git-bootstrap.md`, `upgrade.md`.
- New librarian references: `obsidian-routing.md`, `commit-protocol.md`.

### Backward compatibility

A user with no Obsidian vault (`knowledge/.obsidian/` absent) and no hybrid monorepo (`.meta` + `.git` at root absent) sees output identical to v1.5. Every new behavior is gated on the relevant detection predicate or explicit user invocation. Bootstraps never auto-run on detection.

### Skills

- `pka-bootstrap` v1.6.0 (Obsidian, git, upgrade targets; vendored assets)
- `pka-librarian` v1.6.0 (per-route Obsidian behavior; commit-per-unit)

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
