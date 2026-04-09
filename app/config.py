"""
Application configuration.

Loads from .env with sensible defaults.
All path constants are pathlib.Path objects (absolute).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH)

# ── Google Drive ───────────────────────────────────────────────────────────────
GOOGLE_DRIVE_PARENT_FOLDER_ID = os.getenv("GOOGLE_DRIVE_PARENT_FOLDER_ID", "").strip()
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()

if GOOGLE_SERVICE_ACCOUNT_FILE and not Path(GOOGLE_SERVICE_ACCOUNT_FILE).is_absolute():
    GOOGLE_SERVICE_ACCOUNT_FILE = str(BASE_DIR / GOOGLE_SERVICE_ACCOUNT_FILE)

# ── Data directories ───────────────────────────────────────────────────────────
DATA_DIR = BASE_DIR / "data"

DOWNLOADS_DIR = DATA_DIR / "downloads"
PROCESSED_DIR = DATA_DIR / "processed"
FAILED_DIR    = DATA_DIR / "failed"
TEXT_DIR      = DATA_DIR / "text"
OUTPUT_DIR    = DATA_DIR / "output"

# ── Persistence files ──────────────────────────────────────────────────────────
DOCUMENTS_JSON       = DATA_DIR / "documents.json"
SETTINGS_JSON        = DATA_DIR / "settings.json"
SUPPLIER_RULES_JSON  = DATA_DIR / "supplier_rules.json"
LEARNED_RULES_JSON   = DATA_DIR / "learned_rules.json"
CORRECTIONS_LOG_JSON = DATA_DIR / "corrections_log.json"

# ── Excel export ───────────────────────────────────────────────────────────────
EXCEL_OUTPUT_PATH = OUTPUT_DIR / "invoices.xlsx"

# ── Legacy aliases (backward-compat for pdf_downloader.py and old main.py) ────
DOWNLOAD_DIR    = DOWNLOADS_DIR
STATE_FILE_PATH = DATA_DIR / "state" / "sync_state.json"


def ensure_dirs() -> None:
    """Create all required data directories."""
    for d in (DOWNLOADS_DIR, PROCESSED_DIR, FAILED_DIR, TEXT_DIR, OUTPUT_DIR,
              DATA_DIR / "state"):
        d.mkdir(parents=True, exist_ok=True)
