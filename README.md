# Google Drive PDF → Excel Sync

A Python-based automation tool that scans a Google Drive folder containing subfolders with PDF files, extracts structured data (supplier and amount), and maintains an up-to-date Excel file.

Each subfolder in Google Drive is mapped to a separate worksheet in the Excel file.

---

## 🚀 Features

- 🔄 Incremental sync (only processes new or updated PDFs)
- 📁 Supports nested folder structure (1 level under parent)
- 📄 Extracts text from PDF files
- 🧾 Extracts:
  - Supplier name
  - Amount
- 📊 Generates a single Excel file with:
  - One sheet per folder
  - One row per PDF
- 🧠 Persistent state tracking (prevents duplicate processing)
- ❌ Detects deleted files and marks them accordingly
- ⚡ Fast and scalable for large datasets

---

## 🧱 Project Structure


google_drive_pdf_sync/
│
├── app/
│ ├── main.py
│ ├── config.py
│ │
│ ├── clients/
│ │ └── drive_client.py
│ │
│ ├── parsers/
│ │ └── pdf_parser.py
│ │
│ ├── extractors/
│ │ └── invoice_extractor.py
│ │
│ ├── writers/
│ │ └── excel_writer.py
│ │
│ ├── state/
│ │ └── state_manager.py
│ │
│ ├── models/
│ │ └── record.py
│ │
│ └── utils/
│ └── ...
│
├── data/
│ ├── output/
│ │ └── invoices.xlsx
│ ├── state/
│ │ └── sync_state.json
│ └── temp/
│
├── credentials/
│ └── service_account.json
│
├── .env
├── .gitignore
├── requirements.txt
└── README.md


---

## ⚙️ Requirements

- Python 3.10+
- Google Cloud Project with Drive API enabled
- Service Account credentials

---

## 📦 Installation

```bash
git clone <your-repo>
cd google_drive_pdf_sync

python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

pip install -r requirements.txt
🔐 Google Drive Setup
Go to Google Cloud Console
Create a new project
Enable Google Drive API
Create a Service Account
Download the JSON credentials file
Place it in:
credentials/service_account.json
Share your target Google Drive folder with the service account email
🔧 Configuration

Create a .env file:

GOOGLE_DRIVE_PARENT_FOLDER_ID=your_folder_id
EXCEL_OUTPUT_PATH=data/output/invoices.xlsx
STATE_FILE_PATH=data/state/sync_state.json
GOOGLE_SERVICE_ACCOUNT_FILE=credentials/service_account.json
▶️ Running the Project
python app/main.py
🧠 How It Works
1. Folder Mapping
Google Drive:
Parent Folder
├── January
│   ├── file1.pdf
│   └── file2.pdf
├── February
│   └── file3.pdf

↓

Excel:
- Sheet: January
- Sheet: February
2. Incremental Sync Logic

Each file is tracked using:

file_id
modified_time
(optional) checksum
Behavior:
מצב	פעולה
קובץ חדש	מתווסף לאקסל
קובץ עודכן	שורה מתעדכנת
קובץ לא השתנה	מדולג
קובץ נמחק	מסומן כ־deleted
3. State Management

The system maintains a JSON file:

data/state/sync_state.json

Example:

{
  "files": {
    "file_id_1": {
      "file_name": "invoice1.pdf",
      "modified_time": "2026-04-01T08:00:00Z",
      "sheet_name": "January"
    }
  }
}
📊 Excel Output Structure

Each sheet contains:

file_id	file_name	supplier	amount	modified_time	status

You can hide technical columns (file_id, modified_time) if needed.

🧾 PDF Processing

Handled by:

pdfplumber for text extraction
🔍 Data Extraction

The system extracts:

Supplier
Based on known patterns or top text lines
Amount
Regex-based detection of currency values

This logic is customizable in:

app/extractors/invoice_extractor.py
⚠️ Limitations
Works best with text-based PDFs
Scanned PDFs require OCR (not included in v1)
Extraction accuracy depends on PDF format consistency
🔄 Future Improvements
OCR support (Tesseract)
Smart supplier detection (ML / rules engine)
Web dashboard
Google Sheets integration
Scheduled execution (cron / cloud)
🧪 Testing
pytest
🔒 Security Notes
Never commit:
.env
credentials/
data/state/
Use .gitignore properly
🧠 Design Principles
Separation of concerns
Idempotent sync
Safe updates (no destructive deletes)
Extensible architecture
🤝 Contributing

Feel free to fork and extend the project.

```
---

## 📄 License

MIT License

---

## 💡 Author Notes

This project is designed for real-world automation workflows involving financial documents and structured data extraction.