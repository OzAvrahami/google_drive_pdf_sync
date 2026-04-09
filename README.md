# Local Accountant Tool — Google Drive PDF Processor

A simple local desktop tool for accountants.  
Connects to Google Drive, downloads PDF invoices, parses them automatically,  
and lets the accountant review, correct, approve, and export to Excel.

**No servers. No database. No cloud subscriptions.**  
Everything runs on one computer and is stored in local JSON files.

---

## Features

- Scans Google Drive folders recursively for PDF files
- Downloads new PDFs only (incremental)
- Extracts and parses invoice fields automatically (supplier, date, invoice #, total)
- Supports Hebrew and English invoices
- Stores all state in `data/documents.json` — a plain JSON file you can inspect
- Review & correction screen for every document
- Status tracking: `new → processed / needs_review / failed → approved → exported`
- Export approved documents to Excel with duplicate detection
- Simple, clean PySide6 desktop UI

---

## Requirements

- Python 3.11+
- A Google Cloud service account with Drive read access
- Windows / macOS / Linux

---

## Setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd google_drive_pdf_sync
pip install -r requirements.txt
```

### 2. Google Drive credentials

1. Create a **Google Cloud project** and enable the **Google Drive API**.
2. Create a **Service Account** and download its JSON key file.
3. Share your Google Drive folder with the service account's email address (read-only is enough).
4. Place the JSON key file at `credentials/service_account.json`  
   (or point to it via `.env`).

### 3. Configure `.env`

Copy the example and fill in your values:

```bash
cp .env.example .env
```

Edit `.env`:

```
GOOGLE_DRIVE_PARENT_FOLDER_ID=your_folder_id_here
GOOGLE_SERVICE_ACCOUNT_FILE=credentials/service_account.json
```

The folder ID is the last part of the Google Drive folder URL:  
`https://drive.google.com/drive/folders/`**`1AbCdEfGhIjK`**

---

## Running the tool

```bash
python run.py
```

The desktop window will open.

---

## Workflow

| Step | Action | Button |
|------|--------|--------|
| 1 | Discover PDFs in Drive | **סרוק Drive** (Scan Drive) |
| 2 | Download and parse all new files | **עבד מסמכים חדשים** (Process New) |
| 3 | Review documents needing attention | Double-click any row → Review dialog |
| 4 | Correct extracted fields if needed | Edit fields → **שמור תיקונים** (Save) |
| 5 | Approve documents | **אשר מסמך** (Approve) in the review dialog |
| 6 | Export to Excel | **ייצא לאקסל** (Export Approved) |

---

## Local file structure

```
data/
├── documents.json        ← all document state (single source of truth)
├── settings.json         ← app settings (auto-created)
├── downloads/            ← downloaded PDF files
│   └── <folder>/<file>.pdf
├── text/                 ← extracted plain text per document
│   └── <drive_file_id>.txt
├── output/               ← Excel exports
│   └── invoices.xlsx
├── processed/            ← (reserved)
├── failed/               ← (reserved)
└── state/                ← legacy CLI state (for old main.py)
```

---

## Document statuses

| Status | Hebrew | Meaning |
|--------|--------|---------|
| `new` | חדש | Discovered in Drive, not yet processed |
| `processed` | עובד | Parsed successfully (confidence ≥ 75 %) |
| `needs_review` | לבדיקה | Parsed but low confidence or missing fields |
| `failed` | שגיאה | Exception during download or parsing |
| `approved` | מאושר | Accountant reviewed and approved |
| `exported` | יוצא | Included in the Excel export |

---

## Running tests

```bash
pytest tests/ -v
```

All existing parser, state, and text-helper tests are preserved.

---

## Legacy CLI pipeline

The original command-line pipeline still works:

```bash
python -m app.main
```

This is independent of the desktop UI and uses the old `data/state/` tracking.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `GOOGLE_DRIVE_PARENT_FOLDER_ID is missing` | Check your `.env` file |
| `Service account file not found` | Check `GOOGLE_SERVICE_ACCOUNT_FILE` path |
| PDFs not found in Drive | Make sure the service account email has access to the folder |
| `No module named 'PySide6'` | Run `pip install -r requirements.txt` |
| Hebrew text garbled | Normal for some PDFs — use the review dialog to correct manually |
