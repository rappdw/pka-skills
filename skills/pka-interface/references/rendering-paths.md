# Rendering Paths

How the dashboard gets its data, in both storage modes.

There is one rendering path. The page (`dashboard.html`) never reads the workspace itself: it shows a snapshot, `dashboard-data.js`, that `pka-tools` writes beside it. The storage mode changes where the tool gets the snapshot from, not what the page does.

---

## Why a snapshot

`dashboard.html` is opened by double-click, so its address is `file://…`. From such a page:

- `fetch('.pka/knowledge.db')` is refused (Chromium: "URL scheme "file" is not supported"; Firefox: "CORS request not http"), so a page cannot load the index;
- a `<script src="…">` beside the page loads normally.

So the data is a script. This also means no SQLite library in the browser, and so no CDN.

---

## Writing the data

```
.pka/bin/pka-tools dashboard data [--out PATH] [--json]
```

| | |
|---|---|
| Default output | `dashboard-data.js` at the workspace root, beside `dashboard.html` |
| `--out PATH` | Another place inside the workspace (a `.js` file). The data records the way back to the root, so links still work |
| Index mode | The file list, tags and text come from `.pka/knowledge.db`: run `pka-tools index` first. Files that have gone since the last index are left out and counted |
| Markdown-only mode | The same folders are walked and read. Same output, a little slower |
| Both modes | People and timelines, projects, open action items and the session log are read from the files |
| Not included | Note bodies, `_MOC.md` files, anything `.pkaignore` hides, the contents of capture directories other than the narrative, folders with Archive priority |

The command changes no other file. It refuses to write through a symbolic link, or over a file it did not write.

---

## The data

`dashboard-data.js` assigns one object to `window.PKA_DATA`. Paths are relative to the workspace root; there are no absolute paths in it.

```javascript
window.PKA_DATA = {
"version": 1,
"generated_at": "2026-11-20T09:30:00Z",        // UTC
"generated_by": "pka-tools 1.11.0",
"mode": "index",                                // or "markdown-only"
"indexed_at": "2026-11-20T09:29:58Z",          // newest index entry; "" without an index
"root": "",                                     // from the data file's folder to the workspace root: "" or "../"…
"title": "Sam's Personal Knowledge Assistance", // the first heading of CLAUDE.md
"counts": {"files": 21, "notes": 19, "folders": 10, "people": 3, "projects": 1, "open_actions": 3, "activity": 1},
"sections": [                                   // the Repo Map rows, in its order
  {"folder": "knowledge/leadership", "priority": "Active", "status": "active", "tags": ["meeting-home"],
   "files": 3, "latest": "2026-11-20"}
],
"dirs": ["knowledge/AI", "knowledge/leadership"],   // every folder that holds a listed file
"tags": ["ai", "leadership", "meeting"],            // every tag in use
"file_columns": ["dir", "name", "title", "date", "modified", "size", "tags", "summary", "headings"],
"files": [                                          // one row per file, sorted by path
  [1, "2026-04-29-slt-meeting.md", "SLT meeting", "2026-04-29", "2026-11-20", 137, [1, 2],
   "Deferred the vendor decision.", ["Decisions"]]
],
"people": [
  {"slug": "priya", "name": "Priya Nair", "aliases": [], "folder": "knowledge/personnel/priya",
   "index": "knowledge/personnel/priya/index.md", "files": 2, "latest": "2026-11-20",
   "timeline_total": 1,
   "timeline": [{"date": "2026-04-29", "kind": "meeting", "summary": "Deferred the vendor decision",
                 "path": "knowledge/leadership/2026-04-29-slt-meeting.md"}]}
],
"projects": [
  {"slug": "orion", "name": "Orion", "folder": "projects/orion", "status": "active",
   "has_claude_md": true, "docs": 1, "latest": "2026-11-20", "events": []}
],
"actions": [
  {"path": "knowledge/leadership/2026-04-22-slt-meeting.md", "line": 3, "date": "2026-04-22",
   "text": "Review the Q2 budget proposal @Sam", "owners": ["Sam"], "due": ""}
],
"activity": [
  {"at": "2026-11-01", "role": "bootstrap", "summary": "PKA initialized", "open": "", "next": ""}
]
};
```

Field notes:

| Field | Meaning |
|---|---|
| `files` rows | In `file_columns` order. `dir` is a position in `dirs`, `tags` are positions in `tags`. `title` is the note's frontmatter `title`, else its first `#` heading, else `""` (the loader then makes one from the filename). `date` is the note's own date (filename prefix, else frontmatter `date`), `""` when it has none. `modified` is the day the file last changed. `summary` is frontmatter `summary` or `description`, else the first paragraph, at most 160 characters. `headings` are up to six `#`–`###` headings |
| `people[].index` | The person's `index.md`, `""` when there is none. `timeline` holds the newest 50 entries of the managed timeline block, newest first; `timeline_total` counts all of them. An entry's `path` is `""` when its note cannot be found |
| `projects[]` | One entry per folder directly under `projects/`, plus any project that is only in the index's `project_lifecycle` table (`folder` is then `""`). A project that was transitioned to the archive destination has no folder under `projects/` any more, so it is not in this list |
| `projects[].status` | `active`, `archiving` or `archived`, from the last event in the index's `project_lifecycle` table (`created`, `restored` → active; `archiving`; `transitioned` → archived); without an index, or without events, `active`. **Nothing in this release writes that table**: no `pka-tools` command and no skill step. So in practice every project in the data is `active` with `events` empty. The Repo Map's Status column is not read. `events` are the table's rows for the project (`event`, `date`, `notes`) |
| `actions` | Unticked checkboxes in dated notes under the meeting and people folders (what `pka-tools actions --all-dates` lists), newest note first, at most 200. `counts.open_actions` is the full number |
| `activity` | The last 20 well-formed entries of `.pka/session-log.md`, newest first |
| `sections[].files`, `latest` | How many listed files are under the folder, and the newest `modified` among them |

The page never queries a database, so no table or column name appears in it. `file_index`, `search_fts` and `project_lifecycle` are read by the tool.

`version` goes up only when a page written for the old shape would misread the new one. The loader refuses a version it does not know and tells the user to ask for a dashboard update.

---

## The loader

The template's loader block (between `<!-- pka:loader:start -->` and `<!-- pka:loader:end -->`) turns the data into the `PKA` object the views use. Copy it unchanged.

| | |
|---|---|
| `PKA.ok`, `PKA.problem` | Whether there is data the page can read; if not, the message to show |
| `PKA.files` | One object per file: `path`, `dir`, `name`, `title`, `date`, `modified`, `size`, `tags` (names), `summary`, `headings`, `type` (extension) |
| `PKA.byPath[path]` | The same objects by path |
| `PKA.people`, `PKA.projects`, `PKA.actions`, `PKA.activity`, `PKA.sections`, `PKA.counts` | As in the data |
| `PKA.mode`, `PKA.title`, `PKA.generatedAt` | Storage mode, workspace title, a `Date` |
| `PKA.under(folder)` | Files in a folder, at any depth |
| `PKA.newest(files)` | Sorted newest first, by note date and else last change |
| `PKA.search(query, limit)` | `{terms, people, hits: [{file, score}], total}` |
| `PKA.href(path)` | The link to a workspace-relative path |
| `PKA.link(path, label)` | An escaped `<a>` |
| `PKA.esc(text)` | Text made safe for HTML |
| `PKA.mark(text, terms)` | Escaped text with matched words in `<mark>` |
| `PKA.daysSince(day)`, `PKA.ago(day)`, `PKA.size(bytes)`, `PKA.titleOf(filename)` | Formatting helpers |

When `dashboard-data.js` is missing, `window.PKA_DATA` is undefined: the page says so and shows how to create it. It does not fall back to another way of reading files.

---

## Search

`PKA.search` looks in each file's title, filename, tags, headings, summary and folder path. Every word of the query must appear in at least one of them; case and accents are ignored. Matches in the title rank first, then the filename, tags, headings and summary; ties go to the newest note. People are matched by name, slug and alias and shown above the files.

It does not search the text inside notes, because that text is not in the data. The search section says so on the page. For a full-text search the user asks the assistant, which runs `pka-tools search` in index mode.

---

## Links

Every link is relative to the page and percent-encoded one path segment at a time:

```javascript
PKA.href('knowledge/leadership/2026-05-06-budget review.md')
// → "knowledge/leadership/2026-05-06-budget%20review.md"
```

Never write a `file:///` link or an absolute path into the page. With relative links the workspace folder can be renamed, moved or synced to another machine and every link still resolves, as long as `dashboard.html` and `dashboard-data.js` stay where they are in it.

---

## Staleness

The page header shows when the data was written, the storage mode, and how to refresh ("ask your assistant to refresh the dashboard data, or run `.pka/bin/pka-tools dashboard data`, then reload"). After seven days the line is shown in the warning colour.

The data is never refreshed by the page and never by `post-route`. `SKILL.md` ("Refresh the data") says when a role runs the command; the one automatic occasion is the orchestrator's session end, once, when both dashboard files exist.

---

## Update mode

When `dashboard.html` already exists and has the loader block:

- Read the existing file.
- PKA's sections are marked with HTML comments: `<!-- pka:section:start:NAME -->` / `<!-- pka:section:end:NAME -->`.
- Change only marked sections; keep everything the user wrote outside the markers.
- Add a marked section for each folder added to the Repo Map since the page was written, and a navigation link for it.
- Remove the section of a folder that left the Repo Map only after the user agrees.
- Replace the loader block (`pka:loader:start` … `pka:loader:end`) or the views block (`pka:views:start` … `pka:views:end`) whole when the template's copy has a higher number in its first comment (`pka-loader 2`, `pka-views 2` in this release), never line by line.
- Finish by refreshing the data.

---

## An older dashboard

A `dashboard.html` written by a release before this one has no loader block. It loads `sql.js` from a CDN and reads `.pka/knowledge.db` with `fetch`, or asks for the folder with `showDirectoryPicker`. It keeps behaving exactly as it did; nothing here changes it.

When the user asks for an update or a refresh of such a page, say what it is and offer to rebuild it:

1. Save the old page as `dashboard.html.bak-<date>`.
2. Generate the new page from the template.
3. Carry over the user's customizations: their own sections outside the markers, their colours and wording. For each old marked section, write the new section for the same folder.
4. Write the data and tell the user what changed: it opens by double-click in any current browser, makes no network request, and its search covers titles, tags, headings and summaries.

Do not repair the old page in place by adding a snapshot to its SQL queries: its sections query tables that `pka-tools` does not create.

---

## Browsers

Opened from `file://`, with the data beside it, the reference page was checked in headless Chromium and headless Firefox: it draws every section, search works, and the only files read are the page and its data. It uses nothing newer than what every current browser has had for years, but it has not been checked in Safari.
