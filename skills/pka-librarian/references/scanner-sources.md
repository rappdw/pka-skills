# Scanner Sources

Setup guides for feeding scanned documents into the PKA `team-inbox/`.

---

## ScanSnap (Fujitsu/Ricoh)

### ScanSnap Home Configuration

The ScanSnap Home application supports configurable scan-to-folder profiles.

**Setup steps:**
1. Open ScanSnap Home → Profiles
2. Create a new profile or edit an existing one
3. Set **Save destination** to: `~/pka/team-inbox/`
4. Set **File name format** to: `scan-{date}-{time}` (produces `scan-20260401-143022.pdf`)
5. Set **File format** to: PDF (Searchable) if available, otherwise standard PDF
6. Set **Image quality** to: Auto or Fine (300 DPI recommended for OCR)
7. Set **Color mode** to: Auto Detect
8. Enable **Blank page removal** if scanning double-sided documents

**Recommended profile settings for PKA:**
- Name: "PKA Inbox"
- File format: PDF (Searchable) — this adds a text layer, improving extraction quality
- Scan size: Auto Detect
- Duplex: Enabled
- Quality: Fine (300 DPI)

### ScanSnap Cloud Alternative

If using ScanSnap Cloud instead of ScanSnap Home:
1. Configure cloud destination to sync to a local folder
2. Point that local folder to `~/pka/team-inbox/`
3. Cloud adds its own OCR — the librarian will still create sidecars for indexing

---

## iPhone / iPad (Apple Notes + Files)

### Direct Scan to PKA

1. Open the **Files** app on iPhone/iPad
2. Navigate to the folder synced with `~/pka/team-inbox/` (via iCloud Drive)
3. Tap the `...` menu → **Scan Documents**
4. Scan pages, tap **Save**
5. The scanned PDF lands directly in `team-inbox/`

### Via Apple Notes

1. Open Notes → tap camera icon → **Scan Documents**
2. After scanning, share the note as PDF
3. Save to Files → navigate to `team-inbox/` folder (iCloud Drive)

### Via AirDrop

1. Scan on iPhone using any scanning app
2. AirDrop to your Mac
3. Save to `~/pka/team-inbox/`
4. (This is manual but works for quick one-offs)

---

## AirDrop Direct to Folder (macOS Automation)

For a more seamless AirDrop → PKA pipeline:

1. AirDrop files default to `~/Downloads/`
2. Create a Folder Action (via Automator or Shortcuts) on `~/Downloads/`:
   - Watch for: PDF files matching `scan*` or files from AirDrop
   - Action: Move to `~/pka/team-inbox/`
3. Alternative: use a Hazel rule on `~/Downloads/` to auto-move scan-patterned PDFs

---

## iCloud Drive Sync

If `~/pka/` is in your iCloud Desktop path (`~/Desktop/` or `~/Documents/`), `team-inbox/` syncs automatically. This enables:
- Scanning on iPhone → appears in `team-inbox/` within seconds
- No additional setup required beyond iCloud Drive being enabled
- Works from any Apple device signed into the same iCloud account

**Caveat:** `knowledge.db` also syncs. This is fine for single-machine use. After switching machines, run "Re-index" to pick up any changes that occurred on the other machine.

---

## Google Drive / Dropbox

If using Google Drive or Dropbox instead of iCloud:
1. Install the desktop sync client
2. Place `~/pka/` inside the synced folder (or symlink `team-inbox/` there)
3. Scan to the synced folder from any device
4. Files appear in `team-inbox/` when sync completes

---

## General Recommendations

- **Scan quality:** 300 DPI minimum for reliable OCR. 600 DPI for small text or low-contrast documents.
- **File format:** PDF preferred. PNG/JPG acceptable for single-page scans.
- **Naming:** Include `scan-` prefix in filenames so the librarian can identify scanner-sourced documents vs. manually-dropped files.
- **Batch scanning:** ScanSnap can scan multi-page documents as single PDFs. The librarian processes each PDF as one document. If you want individual pages routed separately, scan as separate files.
- **Business cards:** Scan as individual images (PNG/JPG). The librarian can OCR these and route to `personnel/` if a name is detected.
