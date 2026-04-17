"""
Local file opener — centralised helper for the UI.

Opens a local file using the OS default application.
All error paths produce both a log entry and a user-facing QMessageBox so
failures are never silent.

Public API
----------
open_local_file(path, parent=None) -> bool
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QMessageBox, QWidget

logger = logging.getLogger(__name__)


def open_local_file(path: str, parent: Optional[QWidget] = None) -> bool:
    """
    Open *path* with the OS default application.

    Returns True if the open was attempted, False on any failure (existence
    check failed, or the OS call raised an exception).  All failure cases show
    a QMessageBox when *parent* is provided.

    Guards
    ------
    - Empty path  → warn that the document has not been processed yet.
    - File missing → warn with the expected path so the user knows what failed.
    - OS exception → log at ERROR level + show critical dialog with details.
    """
    # ── Guard: no path stored ─────────────────────────────────────────────────
    if not path or not path.strip():
        logger.warning("open_local_file: path is empty — document not yet processed?")
        _warn(parent, "קובץ לא זמין",
              "הקובץ המקומי אינו זמין.\n"
              "עבד את המסמך תחילה כדי שהקובץ יורד מ-Google Drive.")
        return False

    resolved = Path(path)

    # ── Guard: file does not exist on disk ────────────────────────────────────
    if not resolved.exists():
        logger.warning("open_local_file: file not found: %s", path)
        _warn(parent, "קובץ לא נמצא",
              f"הקובץ אינו קיים בנתיב הבא:\n{path}\n\n"
              "ייתכן שהקובץ נמחק או שהנתיב שגוי.")
        return False

    # ── Warn about missing PDF extension (Windows may not find a viewer) ──────
    if resolved.suffix.lower() not in {".pdf", ".PDF"}:
        logger.warning(
            "open_local_file: file has no .pdf extension (%r) — "
            "Windows may not know which application to use: %s",
            resolved.suffix, path,
        )

    # ── Open ──────────────────────────────────────────────────────────────────
    logger.info("open_local_file: opening %s", path)
    try:
        if sys.platform == "win32":
            os.startfile(str(resolved))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(resolved)])
        else:
            subprocess.Popen(["xdg-open", str(resolved)])
        return True

    except Exception as exc:
        logger.error("open_local_file: failed to open %s: %s", path, exc)
        _critical(parent, "שגיאה בפתיחת קובץ",
                  f"לא ניתן לפתוח את הקובץ:\n{path}\n\n{exc}")
        return False


# ── Internal helpers ───────────────────────────────────────────────────────────

def _warn(parent: Optional[QWidget], title: str, body: str) -> None:
    if parent is not None:
        QMessageBox.warning(parent, title, body)


def _critical(parent: Optional[QWidget], title: str, body: str) -> None:
    if parent is not None:
        QMessageBox.critical(parent, title, body)
