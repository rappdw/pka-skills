# UI Patterns

View types for each inferred content type. Used to generate dashboard sections from the Repo Map.

---

## View Type Selection

Sections are generated from Active and Reference priority folders in the Repo Map. No hardcoded sections. The view type is inferred from the folder's content type.

| Inferred content type | Default view | Key features |
|-----------------------|-------------|-------------|
| Per-person notes | Card grid | One card per person, sorted by last modified |
| Meeting / strategy notes (`meeting-home`) | Timeline | Sorted by date from filename, chronological |
| Research outputs | Topic list | Grouped by topic, linked files per topic |
| Journal / lab notes | Calendar heatmap + entry list | Monthly grid, click for entries |
| Project workspaces | Project cards | Status badge, days since activity, doc count |
| Generic / flat | File table | Sortable columns, inline search |

---

## Card Grid (Per-Person Notes)

Used for `personnel/` style folders where subfolders represent individuals.

```html
<div class="card-grid">
    <!-- One card per person subfolder -->
    <div class="card" data-last-modified="2026-03-31">
        <h3><a href="file:///path/to/personnel/aarav/">Aarav</a></h3>
        <div class="meta">Last modified: 3 days ago</div>
        <div class="excerpt">Latest: 1-1 notes — MCP adapter decision...</div>
        <div class="count">12 files</div>
    </div>
</div>
```

**Sort:** By last modified date (most recent first).
**Card content:** Person name (from subfolder name), last modified date, excerpt from most recent file, file count.
**Click behavior:** Links to the person's folder.

---

## Timeline (Meeting/Strategy Notes)

Used for folders tagged `meeting-home` in the Repo Map. Optimized for chronologically-ordered meeting notes.

```html
<div class="timeline">
    <!-- Entries extracted from date-slug filenames -->
    <div class="timeline-entry" data-date="2026-03-31">
        <div class="timeline-date">Mar 31</div>
        <div class="timeline-content">
            <h4><a href="file:///path/to/leadership/2026-03-31-slt-q2-planning.md">
                SLT Q2 Planning
            </a></h4>
            <div class="excerpt">Discussed roadmap priorities...</div>
        </div>
    </div>
</div>
```

**Sort:** By date extracted from filename (most recent first).
**Date extraction:** Parse `YYYY-MM-DD` prefix from filenames matching the date-slug pattern.
**Grouping:** Group by month with month headers.
**Excerpt:** First 150 characters of file content (SQLite mode) or filename-derived title (markdown mode).

---

## Topic List (Research Outputs)

Used for folders with a consistent topic-subfolder structure.

```html
<div class="topic-list">
    <div class="topic">
        <h4><a href="file:///path/to/research/mcp-evaluation/">MCP Evaluation</a></h4>
        <div class="files">
            <span class="file-badge md">research.md</span>
            <span class="file-badge pdf">research.pdf</span>
            <span class="file-badge md">source-email.md</span>
        </div>
        <div class="excerpt">Evaluation of MCP protocol for...</div>
    </div>
</div>
```

**Sort:** Alphabetical by topic name, or by last modified.
**Display:** Topic name, file type badges for each file in the topic folder, excerpt from the primary `.md` file.

---

## Calendar Heatmap (Journal/Lab Notes)

Used for chronologically-organized notes (lab notebook, journal).

```html
<div class="calendar-view">
    <!-- Month grid showing activity density -->
    <div class="month" data-month="2026-03">
        <h4>March 2026</h4>
        <div class="heatmap-grid">
            <!-- 1 cell per day, color intensity = content length -->
            <div class="day active" data-date="2026-03-31" title="March notes">
            </div>
        </div>
    </div>
    <!-- Entry list below heatmap -->
    <div class="entry-list">
        <a href="file:///path/to/lab-notebook/2026-03.md">March 2026</a>
    </div>
</div>
```

**Heatmap:** Monthly grids showing which days/months have entries. Color intensity proportional to content length.
**Entry list:** Chronological list of all entries, most recent first.

---

## Project Cards

Used for the `projects/` section. One card per project workspace.

```html
<div class="project-grid">
    <div class="project-card" data-status="active" data-days-since="2">
        <div class="status-badge active">Active</div>
        <h3><a href="file:///path/to/projects/satori/">Satori</a></h3>
        <div class="meta">Last activity: 2 days ago</div>
        <div class="meta">4 top-level docs</div>
    </div>
    <div class="project-card" data-status="archiving" data-days-since="67">
        <div class="status-badge archiving">Winding Down</div>
        <h3><a href="file:///path/to/projects/operating_model/">Operating Model</a></h3>
        <div class="meta">Last activity: 67 days ago</div>
    </div>
</div>
```

**Status badges:**
- `active` (green) — recent activity
- `archiving` (yellow) — flagged as winding down (60+ days inactive)
- `archived` (gray) — transitioned to knowledge

**Sort:** Active first (by last modified), then archiving, then archived.
**Card content:** Project name, status badge, days since last activity, top-level document count, presence of `CLAUDE.md`.

---

## File Table (Generic/Flat)

Fallback view for folders that don't match a specific pattern.

```html
<table class="file-table">
    <thead>
        <tr>
            <th data-sort="name">Name</th>
            <th data-sort="type">Type</th>
            <th data-sort="modified">Modified</th>
            <th data-sort="size">Size</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td><a href="file:///path/to/file.md">file.md</a></td>
            <td>.md</td>
            <td>2026-03-31</td>
            <td>4.2 KB</td>
        </tr>
    </tbody>
</table>
```

**Features:** Sortable columns (click header), inline search/filter, file type icons.

---

## Fixed Sections

Always present regardless of Repo Map content:

### Activity
Last 20 entries from `.pka/session-log.md`. Displayed as a compact log with timestamps, role names, and summaries.

### Search
Full-text search input. SQLite mode: queries `search_fts`. Markdown mode: filename search only (with deep search option). Source filter dropdown if multiple areas present.

---

## Design System

### Theme
- Dark/light mode via `prefers-color-scheme` media query
- Manual toggle button (saves preference to localStorage)
- CSS custom properties for all colors

### Layout
- Responsive: grid on desktop, stack on mobile
- Sidebar navigation listing all sections
- Each section collapsible

### Typography
- System font stack: `-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`
- Monospace for file paths: `"SF Mono", "Fira Code", monospace`
