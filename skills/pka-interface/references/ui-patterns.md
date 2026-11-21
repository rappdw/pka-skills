# UI Patterns

The views a dashboard section can use, what each one draws, and where its data comes from. The working code for every view is in `dashboard-template.html` (the block between `pka:views:start` and `pka:views:end`); this file explains it.

---

## A section

Sections are generated from the Active and Reference folders of the Repo Map. No hardcoded sections. Each is a marked block; the `data-view` attribute names the view and `data-folder` the folder it shows:

```html
<!-- pka:section:start:personnel -->
<section id="personnel" data-view="people" data-folder="knowledge/personnel">
  <h2>People</h2>
  <div class="pka-body"></div>
</section>
<!-- pka:section:end:personnel -->
```

- `NAME` in the markers and the `id` are the folder's slug (`knowledge/lab-notebook` → `lab-notebook`); they must be unique in the page.
- The view script fills `.pka-body`. Leave it empty. Anything else inside the section (an introduction, a link) is yours to write.
- Add a link to the section in the navigation list.
- `data-folder` is the workspace-relative folder exactly as the Repo Map writes it, without a trailing slash.

## Choosing the view

| The folder holds | `data-view` | Needs `data-folder` |
|---|---|---|
| One subfolder per person (Repo Map tag `people-home`) | `people` | yes |
| Dated meeting or strategy notes (tag `meeting-home`) | `timeline` | yes |
| A subfolder per topic: research outputs, wikis (tag `wiki-home`) | `topics` | yes |
| A journal or lab notebook of dated notes (tag `daily-home`) | `calendar` | yes |
| Project workspaces (`projects/`) | `projects` | no |
| Anything else | `files` | yes |

Use the tags first; without a tag, look at the folder: date-prefixed filenames → `timeline`, subfolders with a few files each → `topics`, flat or mixed → `files`. `calendar` is never chosen by looking: it is used only for a folder tagged `daily-home`, so an untagged folder of `YYYY-MM-DD.md` notes gets `timeline`.

---

## `people`: card grid

**Source:** `PKA.people`, limited to people whose folder is under `data-folder`.

One card per person, the person with the most recent timeline entry (else the most recent change) first. A card has the name (linked to the person's `index.md`, or to the folder when there is none), the number of files, how long ago the folder last changed, the three newest timeline entries (date, kind, linked note title, summary), and a count of the rest with a link to the full timeline.

A person with no timeline block shows "No timeline entries yet": the timeline is maintained by `pka-tools timeline`, not by this page.

## `timeline`: dated notes

**Source:** `PKA.under(folder)`, files that have a `date`, newest first.

Grouped under month headings. Each row has the date, the title (linked) and the summary. Sixty rows are shown, with a "Show more" button. Notes without a date of their own (no `YYYY-MM-DD` filename prefix and no frontmatter `date`) are not on the timeline; the file's modification time is never used as its date.

## `topics`: topic list

**Source:** `PKA.under(folder)`, grouped by the first subfolder below `data-folder`.

One card per subfolder, in alphabetical order: the topic name (from the folder name, linked to the folder), the number of files, the six newest files (linked), and the summary of the newest file that has one. Files directly in the folder are grouped under "(not in a topic folder)".

## `calendar`: journal

**Source:** `PKA.under(folder)`, files that have a `date`.

A grid per month for the six most recent months that have entries: one square per day, filled when the day has an entry and darker the more was written (by file size), linked to that day's first entry. Below it, the entries newest first, thirty at a time.

## `projects`: project cards

**Source:** `PKA.projects`.

One card per project: a status badge, the name (linked to the folder), how long ago it last changed, the number of top-level files and whether it has a `CLAUDE.md`, and the last lifecycle event when there is one. Order: active, then winding down, then archived; within each, most recently changed first.

| Badge | When |
|---|---|
| Active (green) | `status` is `active` |
| Winding down (amber) | `status` is `archiving` |
| Archived (grey) | `status` is `archived` |
| quiet for N days (amber, beside Active) | an active project unchanged for 60 days or more: a prompt to the user, not a status |

The status comes from the data (see `rendering-paths.md`); the page does not decide that a project is winding down. Today the data gives `active` for every project: nothing writes the lifecycle events it is taken from, so the Winding down and Archived badges are not seen in practice, and a project transitioned out of `projects/` is not listed at all.

## `files`: file table

**Source:** `PKA.under(folder)`.

Columns: name (the title, linked), type, date, changed, size. Click a column heading to sort; the filter box above the table narrows it by title and path. One hundred rows are shown, with a "Show more" button.

---

## Fixed sections

Always present, whatever the Repo Map says. None of them takes a `data-folder`.

### `search`

**Source:** `PKA.search(query, 50)`.

A search box; results as you type. People whose name, slug or alias matches come first, then files: date, title, tags, path and summary, with the matched words marked. Under the box, one line says what is searched (titles, paths, tags, headings, summaries) and that the text inside notes is not. Keep that line.

### `actions`: open actions

**Source:** `PKA.actions`, `PKA.counts.open_actions`.

Unticked checkboxes from dated notes in the meeting and people folders, newest note first: the note's date, the item's text, a "due" badge when the item names a date, and a link to the note with the line number. When there are more than the 200 in the data, a line says how many there are in all.

The page cannot tick a box. The note is the record: the user ticks it there, and the item is gone after the next data refresh.

### `activity`

**Source:** `PKA.activity`, and `PKA.files` sorted by `modified`.

The last 20 session-log entries (time, role, summary, open threads, next action), then the ten files changed most recently.

---

## Adding a view

A view is a function in the views block: `VIEWS.name = function (body, folder) { … }`. It reads from `PKA` and writes markup into `body`.

- Escape everything that comes from the data with `PKA.esc`; build links with `PKA.link` or `PKA.href`.
- Read only from `PKA`. A view that needs something the data does not hold cannot be built in the page: tell the user what is missing instead of fetching it.
- Show long lists a page at a time (the template's `paged` helper): a folder can hold thousands of notes.
- Put a view you add for one user outside the `pka:views` markers, in its own `<script>`, so that a later update of the views block keeps it.

---

## Design system

### Theme
- Dark and light mode from `prefers-color-scheme`
- A toggle button; the choice is kept in `localStorage` when the browser allows it for a local page
- CSS custom properties for every colour

### Layout
- Responsive: a grid on a wide screen, stacked on a narrow one
- A navigation list of all sections
- A header with the workspace title, when the data was written and how to refresh it, and the counts

### Typography
- System font stack: `-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`
- Monospace for file paths: `"SF Mono", "Fira Code", ui-monospace, monospace`
- No web fonts, icons or images from anywhere else
