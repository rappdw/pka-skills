---
name: pka-interface
description: >
  ALWAYS use this skill when the user wants a dashboard, browser interface, or
  visual view of their knowledge base, notes, projects, or PKA system. Triggers
  on: building a dashboard, updating an existing dashboard, adding sections or
  views to a dashboard, visualizing data in a browser, creating a PKA interface,
  refreshing a stale dashboard, fixing dashboard search, changing dashboard theme
  or dark mode, adding kanban/timeline/card views, or any request to see knowledge
  or project data visually in HTML. Generates an HTML dashboard (no server, no
  build step, no network, double-click to open) with sections auto-generated from
  the Repo Map. Use this skill even if the user just says "build my dashboard",
  "update the dashboard", "show me my data in a browser", "add a view for X",
  or "the dashboard needs refreshing". Works in index and markdown-only modes.
user-invocable: true
argument-hint: "[command or section name]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# pka-interface

Build, update or refresh the dashboard of a Personal Knowledge Assistance workspace.

## The two files

| File | What it is | Who writes it |
|---|---|---|
| `dashboard.html` | The page: layout, styles, one section per folder, the script that draws them | You, from `references/dashboard-template.html` |
| `dashboard-data.js` | The data the page shows: a snapshot of the workspace | `.pka/bin/pka-tools dashboard data`, never by hand |

Both sit at the workspace root. The page loads the data with `<script src="dashboard-data.js">`, which works when the page is opened by double-click. It loads nothing else: no library, no CDN, no `fetch`, no folder picker, and it never reads `.pka/knowledge.db`. A page opened from `file://` cannot read a local file with `fetch`, which is why the data is a script.

## Pre-flight

1. `.pka/bin/pka-tools status` → storage mode (index or markdown-only) and the folders.
2. Read `CLAUDE.md` `## Repo Map` → which folders become sections, and their tags. No `CLAUDE.md`: use the top-level folders.
3. Is there a `dashboard.html`?
   - No → **generate**.
   - Yes, and it contains `pka:loader:start` → **update** or **refresh** (below).
   - Yes, without `pka:loader:start` → it was built by an earlier release (such a page typically contains `sql-wasm`, `fetch('.pka/knowledge.db')` or `showDirectoryPicker`, but the missing loader block is the test): see "An older dashboard" in `references/rendering-paths.md`. Say what the page is and offer the rebuild; do not refresh or edit it in place.

## Generate

1. In index mode, bring the index up to date: `.pka/bin/pka-tools index`.
2. Write the data: `.pka/bin/pka-tools dashboard data`. Report its one-line summary.
3. Copy `references/dashboard-template.html` to `dashboard.html`. Keep the loader block (`pka:loader:start` … `pka:loader:end`) and the views block (`pka:views:start` … `pka:views:end`) exactly as they are.
4. Replace the template's example sections with one section per Active or Reference folder of the Repo Map, choosing the view from the table below, and make the navigation list match. Keep the fixed sections.
5. Tell the user to open `dashboard.html` (double-click), what each section shows, and how to refresh it.

A section is a few lines of markup; the view script draws its contents from the data:

```html
<!-- pka:section:start:leadership -->
<section id="leadership" data-view="timeline" data-folder="knowledge/leadership">
  <h2>Leadership</h2>
  <div class="pka-body"></div>
</section>
<!-- pka:section:end:leadership -->
```

## Sections and views

Sections come from the Repo Map, never from a fixed list. Choose the view by what the folder holds:

| The folder holds | `data-view` | Shows |
|---|---|---|
| One subfolder per person (tag `people-home`) | `people` | A card per person: files, last change, newest timeline entries |
| Dated meeting or strategy notes (tag `meeting-home`) | `timeline` | Notes by date, newest first, grouped by month |
| A subfolder per topic (research, wikis) | `topics` | A card per subfolder with its files |
| A journal of dated notes (tag `daily-home`) | `calendar` | A square per day for recent months, then the entries |
| `projects/` | `projects` | A card per project folder under `projects/`: days since last change, top-level files, whether it has a `CLAUDE.md` |
| Anything else | `files` | A sortable, filterable table |

The tag decides. `calendar` is used **only** for a folder tagged `daily-home`: a folder of dated notes without that tag gets `timeline`, even when its files are named `YYYY-MM-DD.md`. If the user wants the calendar for it, the Repo Map row gets the tag first (the orchestrator's change, on the user's word).

Project status: every card is badged Active. The page can show "Winding down" and "Archived", but nothing in this release records those states where the data looks for them, and a project that has been transitioned out of `projects/` is no longer in the Projects section (its files are in the section of the folder it moved to). Do not promise the user a status the page cannot show. Details in `references/rendering-paths.md` (`projects[].status`).

Fixed sections, always present: **Search** (`search`), **Open actions** (`actions`: unticked checkboxes in dated meeting and person notes) and **Activity** (`activity`: the last 20 session-log entries and the files changed last).

`references/ui-patterns.md` has each view's data source and markup; `references/rendering-paths.md` has the data format, the loader, links and update mode.

## Refresh the data

The page shows the workspace as it was when the data was written, and says when that was. To refresh:

```
.pka/bin/pka-tools index            # index mode only
.pka/bin/pka-tools dashboard data
```

Then the user reloads the page. `dashboard.html` is not touched.

When to do it:

- The user asks ("refresh the dashboard", "the dashboard is stale", "the dashboard doesn't show X").
- At the end of a session, when `dashboard.html` and `dashboard-data.js` both exist at the workspace root: once, not once per note. The orchestrator does this from its own instructions (the Session End Protocol in `CLAUDE.md`, and "At session end" in its role file), so it happens in sessions where this skill was never loaded. A workspace set up before v1.11.0 has it once its orchestrator role section has been refreshed by `bootstrap upgrade`.
- After a bulk import, a backfill or a project transition.
- After any update to `dashboard.html` itself.

Do not run it after every filed note. It reads the whole workspace: about half a second at 3,000 notes and 3 to 6 seconds at 20,000, against a fifth of a second for `post-route`.

## Update

"Add a section", "change the theme", "the Repo Map changed": edit `dashboard.html` in place.

- Change only what is between a section's `pka:section:start:NAME` / `pka:section:end:NAME` markers, add new marked sections, and keep the navigation list in step. What the user wrote outside the markers stays.
- Removing a section for a folder that left the Repo Map: ask first.
- Never edit `dashboard-data.js`. If a view needs data that is not in it, say so; do not add a `fetch` or a library to get it.
- Finish with a data refresh.

## What the user should know

- Open the page by double-click. It works in any current browser, offline, in both storage modes.
- Search covers titles, paths, tags, headings and a one-line summary of each file. It does not search the text inside notes; for that they ask you (`pka-tools search` in index mode).
- Links are relative to the page, so the workspace folder can be moved or synced to another machine and the links still work. Keep `dashboard.html` and `dashboard-data.js` together.
- A note opens the way the browser opens a `.md` file: as plain text, or as a download.

## Design constraints

- Two files at the workspace root; all HTML, CSS and JavaScript inline in `dashboard.html`; the data in `dashboard-data.js`.
- Double-click to open: `file://`, no localhost, no server, no build step, no npm.
- No network request of any kind, and no script, style, font or image from another host.
- No `fetch`, `XMLHttpRequest`, File System Access API or WebAssembly.
- Every link is relative, built with `PKA.href(path)`.
- Everything from the data is escaped with `PKA.esc` before it goes into the page.
- Dark and light mode: system preference plus a toggle.
- Update mode: marked sections only; customizations preserved.
