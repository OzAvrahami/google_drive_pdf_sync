import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, ".env")

load_dotenv(ENV_PATH)

# ── Google Drive ───────────────────────────────────────────────────────────────
GOOGLE_DRIVE_PARENT_FOLDER_ID = os.getenv("GOOGLE_DRIVE_PARENT_FOLDER_ID", "").strip()
GOOGLE_SERVICE_ACCOUNT_FILE   = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()

if GOOGLE_SERVICE_ACCOUNT_FILE and not os.path.isabs(GOOGLE_SERVICE_ACCOUNT_FILE):
    GOOGLE_SERVICE_ACCOUNT_FILE = os.path.join(BASE_DIR, GOOGLE_SERVICE_ACCOUNT_FILE)

# ── Local paths (override via .env if needed) ──────────────────────────────────
DOWNLOAD_DIR     = os.getenv("DOWNLOAD_DIR",     os.path.join(BASE_DIR, "downloads"))
EXCEL_OUTPUT_PATH = os.getenv("EXCEL_OUTPUT_PATH", os.path.join(BASE_DIR, "data", "output", "invoices.xlsx"))
STATE_FILE_PATH  = os.getenv("STATE_FILE_PATH",  os.path.join(BASE_DIR, "data", "state", "sync_state.json"))
