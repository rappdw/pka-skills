# OCR Patterns

OCR tool detection, extraction strategies, and fallback behavior.

---

## Tool Detection Order

Check in order before any OCR attempt:

```bash
# 1. Best for text-layer PDFs
python3 -c "import pdfplumber" 2>/dev/null && echo "pdfplumber available"

# 2. Fallback for text-layer PDFs
python3 -c "import pypdf" 2>/dev/null && echo "pypdf available"

# 3. Required for image-only PDFs and scanned documents
which tesseract 2>/dev/null && echo "tesseract available"
```

---

## Capability Matrix

| Tool | Text-layer PDFs | Image PDFs | Scanned images | Install |
|------|----------------|------------|----------------|---------|
| pdfplumber | Best | No | No | `pip install pdfplumber` |
| pypdf | Good | No | No | `pip install pypdf` |
| tesseract | Via PDF-to-image | Yes | Yes | `brew install tesseract` (macOS) / `apt install tesseract-ocr` (Linux) |
| None available | — | — | — | Offer installation guidance |

---

## Extraction Strategy

### Text-Layer PDFs
1. Try pdfplumber first (best text extraction quality)
2. Fall back to pypdf if pdfplumber unavailable
3. Extract all pages; concatenate with page separators
4. Store in sidecar `.txt` file alongside original
5. Store in `file_index.ocr_text` and `search_fts.content`

### Image-Only PDFs
1. Requires tesseract
2. Convert PDF pages to images (via pdf2image/Pillow)
3. Run tesseract on each page image
4. Concatenate results with page separators
5. Store in sidecar `.txt` file alongside original

### Scanned Images (PNG, JPG)
1. Requires tesseract
2. Run tesseract directly on the image
3. Store result in sidecar `.txt` file alongside original

### Text Detection Heuristic
To determine if a PDF has a text layer:
```python
import pdfplumber
with pdfplumber.open(path) as pdf:
    first_page = pdf.pages[0]
    text = first_page.extract_text()
    has_text_layer = bool(text and len(text.strip()) > 50)
```

If text layer has < 50 characters on the first page, treat as image-only.

---

## Sidecar File Convention

OCR output is always stored as a sidecar `.txt` file:
- Source: `document.pdf` → Sidecar: `document.pdf.txt`
- Source: `scan.png` → Sidecar: `scan.png.txt`

The sidecar lives alongside the original in the destination folder. Originals are never modified.

The sidecar filename pattern (`.pdf.txt`, `.png.txt`) distinguishes OCR output from regular `.txt` files.

---

## Fallback Behavior

When OCR tools are unavailable:

### Text-layer PDFs, no Python PDF library
- Flag in report: "PDF text extraction unavailable"
- Offer: `pip install pdfplumber --break-system-packages`
- Index the file in `file_index` with metadata only (no content)
- **Never silently skip**

### Image PDFs / scans, no tesseract
- Flag in report: "OCR unavailable — install tesseract"
- Provide platform-specific install command:
  - macOS: `brew install tesseract`
  - Linux: `sudo apt install tesseract-ocr`
- Index the file in `file_index` with metadata only
- **Never silently skip**

### Partial availability
- Use whatever's available for the files it can handle
- Flag remaining files clearly in the report
- Separate "processed" and "needs OCR" sections in the report

---

## Language Detection

For multilingual knowledge bases:
- pdfplumber and tesseract both support language hints
- If a file appears to be non-English, note the detected language in `file_index`
- Tesseract language packs: `brew install tesseract-lang` (macOS) / `apt install tesseract-ocr-<lang>` (Linux)
- Default to English if no language signal detected

---

## Performance Notes

- Text-layer extraction: ~1 second per 100-page PDF
- Image OCR: ~2-5 seconds per page (varies with image quality)
- For large batches (50+ PDFs), process sequentially and report progress
- Never parallelize tesseract — it's CPU-intensive and parallelism causes contention
