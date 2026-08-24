"""Offline native visual harness for the read-only Panda 2.0 Workspace.

Only synthetic documents, a generated PDF, and generated extracted text are used.
No DocumentStore, Drive, credentials, environment file, or operational path is read.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if "--snapshot" in sys.argv:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QTimer, QRectF
from PySide6.QtGui import QPainter, QPdfWriter
from PySide6.QtWidgets import QApplication

from app.models.document import Document
from app.ui.routes import AppRoute
from app.ui.shell import PandaMainWindow
from app.ui.theme.typography import register_bundled_fonts


def _window_size(value: str) -> tuple[int, int]:
    try:
        width, height = value.lower().split("x", 1)
        return int(width), int(height)
    except (AttributeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("size must use WIDTHxHEIGHT") from exc


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=("normal", "missing", "duplicate", "failed", "corrected"),
        default="normal",
    )
    parser.add_argument("--size", type=_window_size, default=(1440, 900))
    parser.add_argument("--snapshot", type=Path)
    return parser.parse_args()


def _generate_pdf(path: Path) -> None:
    writer = QPdfWriter(str(path))
    painter = QPainter(writer)
    painter.drawText(QRectF(300, 300, 3000, 700), "Panda 2.0 synthetic invoice")
    painter.drawText(QRectF(300, 1100, 3000, 700), "Invoice INV-DEMO-2026")
    writer.newPage()
    painter.drawText(QRectF(300, 300, 3000, 700), "Synthetic second page")
    painter.end()


class _SyntheticSource:
    def __init__(self, root: Path) -> None:
        pdf = root / "panda2-workspace-synthetic.pdf"
        raw = root / "panda2-workspace-extracted.txt"
        _generate_pdf(pdf)
        raw.write_text(
            "Panda 2.0 synthetic extracted text\nInvoice: INV-DEMO-2026\nTotal: 1,170.00",
            encoding="utf-8",
        )
        self.documents = [
            Document(
                drive_file_id="normal",
                file_name="חשבונית_אוגוסט_2026.pdf",
                folder_path="Drive / 2026 / אוגוסט",
                status="needs_review",
                confidence=0.86,
                supplier_name="ספק הדגמה בע״מ",
                invoice_number="INV-DEMO-2026",
                invoice_date="24/08/2026",
                subtotal=1000,
                vat=170,
                total=1170,
                description="שירותים מקצועיים — נתונים סינתטיים בלבד",
                local_path=str(pdf),
                raw_text_path=str(raw),
                extracted_data={"document_type": "חשבונית מס"},
            ),
            Document(
                drive_file_id="corrected",
                file_name="corrected_english_supplier_long_filename_2026_08.pdf",
                folder_path="Drive / English supplier",
                status="needs_review",
                confidence=0.58,
                supplier_name="Extracted Ltd",
                corrected_data={"supplier_name": "Corrected Demo Ltd", "total": 999.5},
                invoice_number="TECH-7788",
                invoice_date="24/08/2026",
                subtotal=850,
                vat=149.5,
                total=999.5,
                local_path=str(pdf),
                raw_text_path=str(raw),
                was_manually_corrected=True,
            ),
            Document(
                drive_file_id="missing",
                file_name="missing-local-source.pdf",
                folder_path="Drive / unavailable",
                status="needs_review",
                confidence=0.41,
                supplier_name=None,
                invoice_number=None,
                invoice_date=None,
                total=None,
                local_path=str(root / "not-present.pdf"),
                raw_text_path=str(raw),
            ),
            Document(
                drive_file_id="duplicate",
                file_name="duplicate_suspected.pdf",
                folder_path="Drive / 2026",
                status="processed",
                confidence=0.92,
                supplier_name="ספק כפול לדוגמה",
                invoice_number="DUP-10",
                invoice_date="24/08/2026",
                total=1170,
                local_path=str(pdf),
                raw_text_path=str(raw),
                is_duplicate_suspected=True,
                suspected_duplicate_of=["normal"],
                duplicate_confidence="exact",
            ),
            Document(
                drive_file_id="failed",
                file_name="malformed_source.pdf",
                folder_path="Drive / failures",
                status="failed",
                confidence=0,
                error_message="שגיאת עיבוד סינתטית לצורך תצוגה",
                local_path=str(root / "not-present-failed.pdf"),
                raw_text_path=str(raw),
            ),
        ]

    def all(self) -> list[Document]:
        return list(self.documents)


def main() -> int:
    args = _args()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Panda 2.0 Read-only Workspace Gallery")
    register_bundled_fonts()
    temporary = tempfile.TemporaryDirectory(prefix="panda2-workspace-")
    source = _SyntheticSource(Path(temporary.name))
    window = PandaMainWindow(source, operational_enabled=False)
    window.resize(*args.size)
    ordered = tuple(document.drive_file_id for document in source.documents)
    window.open_workspace(args.scenario, ordered, AppRoute.ATTENTION.value)
    window.show()

    if args.snapshot:
        def save_and_exit() -> None:
            args.snapshot.parent.mkdir(parents=True, exist_ok=True)
            window.grab().save(str(args.snapshot))
            app.quit()

        QTimer.singleShot(650, save_and_exit)
    result = app.exec()
    window.workspace.source_preview.release_source()
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    temporary.cleanup()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
