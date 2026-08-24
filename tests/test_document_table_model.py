"""Headless characterization tests for the Panda 2.0 document table model."""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from app.domain.status_presentation import presentation_for
from app.models.document import Document
from app.ui.models.document_record import AttentionReason, DocumentPresentationRecord
from app.ui.models.document_table_model import (
    COLUMN_SPECS,
    DocumentColumn,
    DocumentRoles,
    DocumentTableModel,
)
from app.ui.theme.direction import TextKind


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _document(document_id: str = "drive-1", **overrides) -> Document:
    values = {
        "drive_file_id": document_id,
        "id": f"record-{document_id}",
        "file_name": f"Invoice-{document_id}.PDF",
        "folder_path": "2026/אוגוסט",
        "local_path": f"C:/Panda/{document_id}.pdf",
        "status": "processed",
        "supplier_name": "ספק אלפא",
        "invoice_number": "INV-100",
        "invoice_date": "23/08/2026",
        "total": 4820.5,
        "confidence": 0.92,
    }
    values.update(overrides)
    return Document(**values)


def _index(model: DocumentTableModel, column: DocumentColumn, row: int = 0):
    return model.index(row, model.column_for(column))


def test_row_column_counts_and_centralized_headers(qapp) -> None:
    model = DocumentTableModel([_document("one"), _document("two")])

    assert model.rowCount() == 2
    assert model.columnCount() == len(COLUMN_SPECS) == 9
    assert [
        model.headerData(column, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
        for column in range(model.columnCount())
    ] == [spec.header_he for spec in COLUMN_SPECS]
    assert all(spec.width_hint > 0 for spec in COLUMN_SPECS)


def test_stable_drive_identity_and_local_record_identity_are_separate(qapp) -> None:
    model = DocumentTableModel([_document("drive-stable", id="local-uuid")])
    index = model.index(0, 0)

    assert model.data(index, DocumentRoles.DOCUMENT_ID) == "drive-stable"
    assert model.data(index, DocumentRoles.RECORD_ID) == "local-uuid"
    assert model.document_id_at(0) == "drive-stable"
    assert model.row_for_document_id("drive-stable") == 0


def test_display_formatting_is_separate_from_typed_values(qapp) -> None:
    model = DocumentTableModel([_document()])

    assert model.data(_index(model, DocumentColumn.TOTAL)) == "₪4,820.50"
    assert model.data(_index(model, DocumentColumn.TOTAL), DocumentRoles.SORT) == Decimal(
        "4820.5"
    )
    assert model.data(_index(model, DocumentColumn.DATE)) == "23/08/2026"
    assert model.data(_index(model, DocumentColumn.DATE), DocumentRoles.SORT) == date(
        2026, 8, 23
    )
    assert model.data(_index(model, DocumentColumn.CONFIDENCE)) == "92%"
    assert model.data(_index(model, DocumentColumn.CONFIDENCE), DocumentRoles.SORT) == 0.92


def test_missing_and_invalid_typed_values_are_deterministic(qapp) -> None:
    model = DocumentTableModel(
        [_document(total=None, invoice_date="not-a-date", confidence=None)]
    )

    assert model.data(_index(model, DocumentColumn.TOTAL)) == ""
    assert model.data(_index(model, DocumentColumn.TOTAL), DocumentRoles.SORT) is None
    assert model.data(_index(model, DocumentColumn.DATE)) == "not-a-date"
    assert model.data(_index(model, DocumentColumn.DATE), DocumentRoles.SORT) is None
    assert model.data(_index(model, DocumentColumn.CONFIDENCE)) == ""
    assert model.data(_index(model, DocumentColumn.CONFIDENCE), DocumentRoles.SORT) is None


def test_effective_corrections_are_snapshotted_without_mutable_document_state(qapp) -> None:
    document = _document(corrected_data={"supplier_name": "Corrected", "total": 10})
    model = DocumentTableModel([document])
    record = model.record_at(0)

    document.corrected_data["supplier_name"] = "Mutated later"

    assert record is not None
    assert record.supplier_name == "Corrected"
    assert record.total == Decimal("10")
    assert not hasattr(record, "corrected_data")


@pytest.mark.parametrize(
    "status",
    [
        "new",
        "processed",
        "needs_review",
        "failed",
        "skipped",
        "approved",
        "exported",
        "confirmed_irrelevant",
        "excluded",
    ],
)
def test_status_presentation_roles_use_domain_metadata(qapp, status: str) -> None:
    model = DocumentTableModel([_document(status=status)])
    index = _index(model, DocumentColumn.STATUS)
    expected = presentation_for(status)

    assert model.data(index) == expected.label_he
    assert model.data(index, DocumentRoles.STATUS_LABEL) == expected.label_he
    assert model.data(index, DocumentRoles.STATUS_CATEGORY) == expected.semantic_category.value
    assert model.data(index, DocumentRoles.RAW_STATUS) == status


def test_duplicate_and_manual_correction_flags_have_independent_roles(qapp) -> None:
    model = DocumentTableModel(
        [_document(is_duplicate_suspected=True, was_manually_corrected=True)]
    )
    index = model.index(0, 0)

    assert model.data(index, DocumentRoles.DUPLICATE_SUSPECTED) is True
    assert model.data(index, DocumentRoles.MANUALLY_CORRECTED) is True
    assert model.data(index, DocumentRoles.QUEUE_ROUTE) == "attention"
    assert model.data(index, DocumentRoles.ATTENTION_REASON) == "suspected_duplicate"


@pytest.mark.parametrize(
    "status, expected",
    [
        ("failed", AttentionReason.FAILED),
        ("skipped", AttentionReason.SKIPPED),
        ("needs_review", AttentionReason.NEEDS_REVIEW),
        ("processed", AttentionReason.NONE),
    ],
)
def test_attention_reason_state_is_exposed(qapp, status: str, expected: AttentionReason) -> None:
    record = DocumentPresentationRecord.from_document(_document(status=status))

    assert record.attention_reason is expected


@pytest.mark.parametrize(
    "column, kind",
    [
        (DocumentColumn.DOCUMENT, TextKind.FILENAME),
        (DocumentColumn.SOURCE, TextKind.PATH),
        (DocumentColumn.SUPPLIER, TextKind.HEBREW),
        (DocumentColumn.DOCUMENT_NUMBER, TextKind.DOCUMENT_NUMBER),
        (DocumentColumn.DATE, TextKind.DATE),
        (DocumentColumn.TOTAL, TextKind.AMOUNT),
        (DocumentColumn.CONFIDENCE, TextKind.PERCENTAGE),
    ],
)
def test_column_direction_metadata_is_available(qapp, column: DocumentColumn, kind: TextKind) -> None:
    model = DocumentTableModel([_document()])

    assert model.data(_index(model, column), DocumentRoles.TEXT_KIND) == kind.value
    assert model.data(_index(model, column), Qt.ItemDataRole.TextAlignmentRole) is not None


def test_model_items_are_selectable_but_not_editable(qapp) -> None:
    model = DocumentTableModel([_document()])
    flags = model.flags(model.index(0, 0))

    assert flags & Qt.ItemFlag.ItemIsSelectable
    assert flags & Qt.ItemFlag.ItemIsEnabled
    assert not flags & Qt.ItemFlag.ItemIsEditable


def test_incremental_update_emits_data_changed_without_reset(qapp) -> None:
    model = DocumentTableModel([_document("same")])
    changed = QSignalSpy(model.dataChanged)
    reset = QSignalSpy(model.modelReset)

    assert model.update_document(_document("same", total=99.5, supplier_name="Updated"))

    assert changed.count() == 1
    assert reset.count() == 0
    assert model.document_id_at(0) == "same"
    assert model.data(_index(model, DocumentColumn.TOTAL), DocumentRoles.SORT) == Decimal("99.5")


def test_insertion_and_removal_use_narrow_notifications(qapp) -> None:
    model = DocumentTableModel([_document("one")])
    inserted = QSignalSpy(model.rowsInserted)
    removed = QSignalSpy(model.rowsRemoved)
    reset = QSignalSpy(model.modelReset)

    assert model.insert_document(_document("two")) == 1
    assert inserted.count() == 1
    assert model.remove_document("one") is True
    assert removed.count() == 1
    assert reset.count() == 0
    assert model.document_id_at(0) == "two"


def test_refresh_updates_known_rows_and_inserts_new_rows(qapp) -> None:
    model = DocumentTableModel([_document("one", supplier_name="Before")])

    model.refresh_documents(
        [_document("one", supplier_name="After"), _document("two")]
    )

    assert model.rowCount() == 2
    assert model.record_at(model.row_for_document_id("one")).supplier_name == "After"
    assert model.row_for_document_id("two") == 1


def test_wholesale_replacement_resets_order_and_identity_map(qapp) -> None:
    model = DocumentTableModel([_document("one"), _document("two")])
    reset = QSignalSpy(model.modelReset)

    model.replace_documents([_document("three"), _document("one")])

    assert reset.count() == 1
    assert model.document_id_at(0) == "three"
    assert model.row_for_document_id("two") is None
    assert model.row_for_document_id("one") == 1


def test_duplicate_stable_identity_is_rejected(qapp) -> None:
    with pytest.raises(ValueError, match="duplicate drive_file_id"):
        DocumentTableModel([_document("same"), _document("same")])


def test_blank_drive_identity_is_rejected(qapp) -> None:
    with pytest.raises(ValueError, match="non-empty drive_file_id"):
        DocumentTableModel([_document("")])
