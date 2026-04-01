---
name: pka-interface
description: >
  ALWAYS use this skill when the user wants a dashboard, browser interface, or
  visual view of their knowledge base, notes, projects, or PKA system. Triggers
  on: building a dashboard, updating an existing dashboard, adding sections or
  views to a dashboard, visualizing data in a browser, creating a PKA interface,
  refreshing a stale dashboard, fixing dashboard search, changing dashboard theme
  or dark mode, adding kanban/timeline/card views, or any request to see knowledge
  or project data visually in HTML. Generates a single-file HTML dashboard (no
  server, no build step, double-click to open) with sections auto-generated from
  the Repo Map. Use this skill even if the user just says "build my dashboard",
  "update the dashboard", "show me my data in a browser", "add a view for X",
  or "the dashboard needs refreshing". Supports SQLite and markdown-only modes.
user-invocable: true
argument-hint: "[command or section name]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# pka-interface

Build or update a single-file HTML dashboard for a Personal Knowledge Assistance system.

## Pre-Flight

1. Check for `.pka/knowledge.db` → SQLite rendering path
2. Read `CLAUDE.md` `## Repo Map` → section structure and view types
3. Check for existing `dashboard.html` → generate vs. update mode
4. Fallback if no `CLAUDE.md`: read top-level folder structure directly

## Mode Detection

| Signal | Rendering path |
|--------|---------------|
| `.pka/knowledge.db` present | SQLite path (sql.js) |
| No database | Markdown-only path (File System Access API) |

See `references/rendering-paths.md` for implementation details per mode.

## Section Generation

Sections generated from Active and Reference priority folders in the Repo Map. No hardcoded sections. View type inferred from content:

| Inferred content type | Default view |
|-----------------------|-------------|
| Per-person notes | Card grid — one card per person, sorted by last modified |
| Meeting / strategy notes + `meeting-home` tag | Timeline — sorted by date from filename |
| Research outputs | Topic list with linked files |
| Journal / lab notes | Calendar heatmap + entry list |
| Project workspaces | Card per project — name, status badge, days since last activity |
| Generic / flat | File table with search |

See `references/ui-patterns.md` for view implementation details.

Fixed sections always present:
- **Activity** — last 20 entries from `.pka/session-log.md`
- **Search** — full-text search; source filter if multiple areas present

## Rendering Paths

**Markdown-only:** File System Access API (Chrome/Edge, `file://` only). Safari not fully supported — dashboard displays a warning and suggests switching to Chrome or enabling SQLite mode.

**SQLite:** sql.js loaded from CDN:
`https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.2/sql-wasm.js`

Works in any browser, any repo size.

## Design Constraints

- Single file: all HTML, CSS, JS inline in `dashboard.html`
- Double-click to open — `file://` protocol, no localhost
- Dark/light mode — system preference + manual toggle
- File links use `file:///` absolute paths
- Update mode: surgical edits only, customizations preserved
- Incrementally extensible
- No npm, no build step, no server
