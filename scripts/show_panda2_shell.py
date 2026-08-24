"""Offline visual harness for the Panda 2.0 Phase E shell.

Examples:
    python -B scripts/show_panda2_shell.py
    python -B scripts/show_panda2_shell.py --snapshot overview.png --size 1440x900
    python -B scripts/show_panda2_shell.py --snapshot attention.png --route attention

Only synthetic documents are used; no operational store or Drive service is opened.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if "--snapshot" in sys.argv:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.models.document import Document
from app.ui.routes import AppRoute
from app.ui.shell import PandaMainWindow
from app.ui.theme.typography import register_bundled_fonts


class _SyntheticSource:
    def __init__(self) -> None:
        now = datetime.now(timezone.utc)
        definitions = (
            ("new-1", "חשבונית חדשה.pdf", "new", False, False, 0),
            ("new-2", "mobile_service.pdf", "new", False, False, 1),
            ("review-1", "חשמל יולי.pdf", "needs_review", False, False, 2),
            ("review-2", "office_rent.pdf", "needs_review", True, True, 3),
            ("failed-1", "damaged_scan.pdf", "failed", False, False, 4),
            ("skipped-1", "receipt.pdf", "skipped", False, False, 5),
            ("duplicate-1", "duplicate_cloud.pdf", "processed", True, False, 6),
            ("ready-1", "consulting.pdf", "processed", False, False, 7),
            ("ready-2", "שירותי ניקיון.pdf", "processed", False, True, 8),
            ("approved-1", "cellcom.pdf", "approved", False, False, 9),
            ("irrelevant-1", "supplier_form.pdf", "confirmed_irrelevant", False, False, 10),
            ("history-1", "exported_invoice.pdf", "exported", False, False, 11),
        )
        self.documents = [
            Document(
                drive_file_id=document_id,
                id=f"record-{document_id}",
                file_name=file_name,
                folder_path="Drive / 2026 / אוגוסט",
                status=status,
                confidence=0.82,
                supplier_name="ספק לדוגמה",
                invoice_number=f"INV-{index + 100}",
                invoice_date="17/08/2026",
                total=100 + index * 47.5,
                is_duplicate_suspected=duplicate,
                suspected_duplicate_of=["ready-1"] if duplicate else None,
                duplicate_confidence="exact" if duplicate else None,
                was_manually_corrected=corrected,
                updated_at=(now - timedelta(hours=index * 5)).isoformat(),
            )
            for document_id, file_name, status, duplicate, corrected, index in definitions
        ]

    def all(self) -> list[Document]:
        return list(self.documents)


def _window_size(value: str) -> tuple[int, int]:
    try:
        width, height = value.lower().split("x", 1)
        return int(width), int(height)
    except (ValueError, AttributeError) as exc:
        raise argparse.ArgumentTypeError("size must use WIDTHxHEIGHT") from exc


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, help="Render one offline PNG and exit")
    parser.add_argument("--size", type=_window_size, default=(1440, 900))
    parser.add_argument(
        "--route",
        choices=[route.value for route in AppRoute],
        default=AppRoute.OVERVIEW.value,
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Panda 2.0 Shell Gallery")
    register_bundled_fonts()
    window = PandaMainWindow(_SyntheticSource())
    window.resize(*args.size)
    window.navigate(args.route)
    window.show()
    if args.snapshot:
        app.processEvents()
        args.snapshot.parent.mkdir(parents=True, exist_ok=True)
        if not window.grab().save(str(args.snapshot), "PNG"):
            return 1
        window.close()
        return 0
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
