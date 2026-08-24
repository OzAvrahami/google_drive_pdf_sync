"""Offline development harness for Panda 2.0 document queue models.

Run from the repository root:
    python -B scripts/show_panda2_table_model.py

This harness uses synthetic records only. It does not open DocumentStore, Drive,
credentials, or any operational file.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if "--snapshot" in sys.argv:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.models.document import Document
from app.ui.components import SearchField
from app.ui.models.document_filter_model import DocumentFilterProxyModel
from app.ui.models.document_table_model import COLUMN_SPECS, DocumentTableModel
from app.ui.models.queue_policy import AttentionSegment, QueueRoute, ReadySegment
from app.ui.models.selection import selected_document_ids
from app.ui.theme import apply_panda_theme
from app.ui.theme.tokens import LAYOUT, SPACING
from app.ui.theme.typography import TypographyRole, apply_typography


def _synthetic_documents() -> list[Document]:
    rows = (
        ("d-001", "חשבונית ארנונה.pdf", "עיריית ירושלים", "100238", "03/08/2026", 4820.5, "new", 0.0),
        ("d-002", "cloud-hosting.pdf", "Globex Cloud", "INV-204", "11/07/2026", 89.9, "processed", 0.96),
        ("d-003", "invoice_003.pdf", "ספק אלפא", "A-003", "23/08/2026", 1250, "needs_review", 0.58),
        ("d-004", "failed-scan.pdf", None, None, None, None, "failed", None),
        ("d-005", "receipt.pdf", "חנות לדוגמה", "R-41", "07/08/2026", 42.5, "skipped", 0.88),
        ("d-006", "consulting.pdf", "Acme Advisory", "AC-77", "15/06/2026", 9400, "approved", 0.99),
        ("d-007", "corrected.pdf", "חברת החשמל", "530-44", "18/08/2026", 733.2, "processed", 0.81),
        ("d-008", "exported.pdf", "עברית מערכות", "EX-8", "01/05/2026", 314, "exported", 0.91),
        ("d-009", "irrelevant.pdf", None, None, None, None, "confirmed_irrelevant", None),
        ("d-010", "duplicate.pdf", "Globex Cloud", "INV-204", "11/07/2026", 89.9, "processed", 0.97),
    )
    documents: list[Document] = []
    for document_id, name, supplier, number, invoice_date, total, status, confidence in rows:
        documents.append(
            Document(
                drive_file_id=document_id,
                id=f"record-{document_id}",
                file_name=name,
                folder_path="Drive / 2026 / אוגוסט",
                status=status,
                supplier_name=supplier,
                invoice_number=number,
                invoice_date=invoice_date,
                total=total,
                confidence=confidence,
                was_manually_corrected=document_id == "d-007",
                is_duplicate_suspected=document_id == "d-010",
                suspected_duplicate_of=["d-002"] if document_id == "d-010" else None,
                duplicate_confidence="exact" if document_id == "d-010" else None,
                error_message="קובץ PDF פגום" if status == "failed" else None,
            )
        )
    return documents


class PandaTableModelHarness(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Panda 2.0 — Document Model Harness")
        self.setMinimumSize(LAYOUT.minimum_width, LAYOUT.minimum_height)
        self.resize(1260, 760)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        root = QWidget()
        apply_panda_theme(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(SPACING.page, SPACING.panel, SPACING.page, SPACING.page)
        layout.setSpacing(SPACING.standard)
        self.setCentralWidget(root)

        title = QLabel("מודל תורי מסמכים — נתונים סינתטיים")
        apply_typography(title, TypographyRole.PAGE_TITLE)
        layout.addWidget(title)

        controls = QHBoxLayout()
        self.search = SearchField()
        self.route = QComboBox()
        self.route.addItem("כל המסמכים", None)
        for value, label in (
            (QueueRoute.INBOX, "נכנסו"),
            (QueueRoute.ATTENTION, "דורש טיפול"),
            (QueueRoute.READY, "מוכן"),
            (QueueRoute.IRRELEVANT, "לא רלוונטי"),
            (QueueRoute.HISTORY, "היסטוריה"),
        ):
            self.route.addItem(label, value)
        self.ready = QComboBox()
        for value, label in (
            (ReadySegment.ALL, "מוכן — הכל"),
            (ReadySegment.READY_TO_APPROVE, "מוכן לאישור"),
            (ReadySegment.READY_TO_EXPORT, "מוכן לייצוא"),
        ):
            self.ready.addItem(label, value)
        self.attention = QComboBox()
        for value, label in (
            (AttentionSegment.ALL, "טיפול — הכל"),
            (AttentionSegment.NEEDS_REVIEW, "לבדיקה"),
            (AttentionSegment.FAILED, "נכשל"),
            (AttentionSegment.SKIPPED, "דולג"),
            (AttentionSegment.SUSPECTED_DUPLICATE, "חשד לכפילות"),
        ):
            self.attention.addItem(label, value)
        controls.addWidget(self.search, 1)
        controls.addWidget(self.route)
        controls.addWidget(self.ready)
        controls.addWidget(self.attention)
        layout.addLayout(controls)

        self.source_model = DocumentTableModel(_synthetic_documents(), self)
        self.proxy_model = DocumentFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.source_model)
        self.table = QTableView()
        self.table.setModel(self.proxy_model)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(False)
        self.table.verticalHeader().setDefaultSectionSize(48)
        for column, spec in enumerate(COLUMN_SPECS):
            self.table.setColumnWidth(column, spec.width_hint)
            self.table.setColumnHidden(column, not spec.default_visible)
        layout.addWidget(self.table, 1)

        self.selection_summary = QLabel("0 מסמכים נבחרו")
        self.selection_summary.setProperty("pandaRole", "muted")
        apply_typography(self.selection_summary, TypographyRole.HELPER)
        layout.addWidget(self.selection_summary)

        self.search.textChanged.connect(self.proxy_model.set_search_query)
        self.route.currentIndexChanged.connect(
            lambda: self.proxy_model.set_route(self.route.currentData())
        )
        self.ready.currentIndexChanged.connect(
            lambda: self.proxy_model.set_ready_segment(self.ready.currentData())
        )
        self.attention.currentIndexChanged.connect(
            lambda: self.proxy_model.set_attention_segment(self.attention.currentData())
        )
        self.table.selectionModel().selectionChanged.connect(self._update_selection_summary)
        self.table.sortByColumn(
            self.source_model.column_for(COLUMN_SPECS[0].key), Qt.SortOrder.AscendingOrder
        )

    def _update_selection_summary(self) -> None:
        selection = self.table.selectionModel()
        ids = selected_document_ids(selection) if isinstance(selection, QItemSelectionModel) else []
        self.selection_summary.setText(f"{len(ids)} מסמכים נבחרו · {', '.join(ids)}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, help="Render one offline PNG and exit")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Panda 2.0 Table Model Harness")
    window = PandaTableModelHarness()
    if args.snapshot:
        window.resize(LAYOUT.minimum_width, LAYOUT.minimum_height)
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
