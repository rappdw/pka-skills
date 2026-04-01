# Rendering Paths

Implementation details for the two rendering modes: markdown-only and SQLite.

---

## Mode Detection

```javascript
// In dashboard.html initialization
async function detectMode() {
    try {
        const response = await fetch('.pka/knowledge.db');
        if (response.ok) return 'sqlite';
    } catch (e) {
        // file:// protocol or CORS — try File System Access API
    }
    return 'markdown';
}
```

Practical detection: check for `.pka/knowledge.db` presence. If found → SQLite path. Otherwise → markdown-only path.

---

## SQLite Rendering Path

### Setup

Load sql.js from CDN:
```html
<script src="https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.2/sql-wasm.js"></script>
```

Initialize:
```javascript
async function initSQLite() {
    const SQL = await initSqlJs({
        locateFile: file => `https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.2/${file}`
    });
    const response = await fetch('.pka/knowledge.db');
    const buffer = await response.arrayBuffer();
    return new SQL.Database(new Uint8Array(buffer));
}
```

### Data Queries

Each dashboard section runs queries against the loaded database:

```javascript
// Personnel section — card grid
const personnel = db.exec(`
    SELECT person_slug, last_modified, excerpt 
    FROM personnel_index 
    ORDER BY last_modified DESC
`);

// Leadership section — timeline (meeting-home tagged)
const meetings = db.exec(`
    SELECT note_date, topic, excerpt 
    FROM leadership_index 
    ORDER BY note_date DESC
`);

// Full-text search
const results = db.exec(`
    SELECT path, filename, folder, snippet(search_fts, 3, '<mark>', '</mark>', '...', 32) 
    FROM search_fts 
    WHERE search_fts MATCH ?
`, [query]);

// Activity log
const activity = db.exec(`
    SELECT * FROM file_index 
    ORDER BY indexed_at DESC 
    LIMIT 20
`);

// Projects
const projects = db.exec(`
    SELECT project_slug, has_claude_md, last_modified, status 
    FROM projects_index 
    ORDER BY last_modified DESC
`);
```

### Browser Compatibility

Works in any modern browser. The database is loaded entirely into memory via sql.js (WebAssembly). No server needed. File links use `file:///` absolute paths for local navigation.

---

## Markdown-Only Rendering Path

### Setup

Uses the File System Access API to read files directly from the filesystem. Only available in Chrome and Edge when the page is opened via `file://` protocol.

```javascript
async function initMarkdown() {
    // Request directory access
    const dirHandle = await window.showDirectoryPicker();
    return dirHandle;
}
```

### Data Access

```javascript
async function readSessionLog(dirHandle) {
    const pkaDir = await dirHandle.getDirectoryHandle('.pka');
    const logFile = await pkaDir.getFileHandle('session-log.md');
    const file = await logFile.getFile();
    return await file.text();
}

async function listFolder(dirHandle, folderPath) {
    let current = dirHandle;
    for (const part of folderPath.split('/')) {
        current = await current.getDirectoryHandle(part);
    }
    const entries = [];
    for await (const entry of current.values()) {
        entries.push({
            name: entry.name,
            kind: entry.kind
        });
    }
    return entries;
}
```

### Search

Markdown-only mode cannot do full-text search across file contents without reading every file. Instead:
- Search is limited to filenames and folder paths
- A "deep search" button triggers reading all `.md` files (slow for large repos)
- Dashboard shows a note: "Enable SQLite mode for fast full-text search"

### Browser Compatibility Warning

```html
<div id="browser-warning" style="display: none;">
    ⚠ This dashboard uses the File System Access API, which requires 
    Chrome or Edge. Safari is not fully supported. For full compatibility, 
    enable SQLite mode by running "index my knowledge base" in PKA.
</div>
<script>
    if (!('showDirectoryPicker' in window)) {
        document.getElementById('browser-warning').style.display = 'block';
    }
</script>
```

---

## File Links

Both modes generate clickable file links using `file:///` absolute paths:

```javascript
function fileLink(relativePath, pkaRoot) {
    const absolutePath = `${pkaRoot}/${relativePath}`;
    return `file:///${absolutePath}`;
}
```

The PKA root path is detected at initialization (SQLite mode reads it from the database path; markdown mode gets it from the directory picker).

---

## Update Mode

When `dashboard.html` already exists:
- Read the existing file
- Identify PKA-generated sections (marked with HTML comments: `<!-- pka:section:start:NAME -->` / `<!-- pka:section:end:NAME -->`)
- Update only PKA sections; preserve user customizations outside those markers
- Add new sections for folders added to the Repo Map since last generation
- Remove sections for folders no longer in the Repo Map (after confirmation)

This enables surgical updates without losing manual tweaks.
