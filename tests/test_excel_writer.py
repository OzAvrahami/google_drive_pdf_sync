"""Characterization tests for the current Excel export contract."""

from pathlib import Path

from openpyxl import load_workbook

from app.models.document import Document
from app.writers.excel_writer import _ALL_COLS, _DUP_COLOR, export_documents


def _document(drive_id: str, **overrides) -> Document:
    values = {
        "drive_file_id": drive_id,
        "file_name": f"{drive_id}.pdf",
        "folder_path": "invoices/2026",
        "status": "approved",
        "supplier_name": "Example Supplier",
        "invoice_number": "INV-100",
        "invoice_date": "01/02/2026",
        "total": 250.0,
        "extracted_data": {"document_type": "tax_invoice"},
    }
    values.update(overrides)
    return Document(**values)


def _worksheet(path: Path):
    return load_workbook(path).active


def test_export_writes_current_column_structure_and_corrected_values(tmp_path: Path) -> None:
    output = tmp_path / "output.xlsx"
    doc = _document(
        "drive-1",
        corrected_data={"supplier_name": "Corrected Supplier", "total": 275.0},
    )

    assert export_documents([doc], str(output)) == 1

    ws = _worksheet(output)
    headers = [cell.value for cell in ws[1]]
    assert headers == _ALL_COLS
    row = [cell.value for cell in ws[2]]
    assert row[3] == "Corrected Supplier"
    assert row[6] == 275
    assert row[7] == "drive-1"


def test_export_skips_an_existing_drive_id(tmp_path: Path) -> None:
    output = tmp_path / "output.xlsx"
    doc = _document("drive-1")

    assert export_documents([doc], str(output)) == 1
    assert export_documents([doc], str(output)) == 0

    ws = _worksheet(output)
    assert ws.max_row == 2


def test_export_appends_new_drive_ids_to_existing_workbook(tmp_path: Path) -> None:
    output = tmp_path / "output.xlsx"

    export_documents([_document("drive-1")], str(output))
    assert export_documents([_document("drive-2", invoice_number="INV-200")], str(output)) == 1

    ws = _worksheet(output)
    assert ws.max_row == 3
    assert [ws.cell(row=row, column=8).value for row in (2, 3)] == ["drive-1", "drive-2"]


def test_export_highlights_rows_with_duplicate_business_keys(tmp_path: Path) -> None:
    output = tmp_path / "output.xlsx"
    first = _document("drive-1")
    second = _document("drive-2")

    assert export_documents([first, second], str(output)) == 2

    ws = _worksheet(output)
    for row in (2, 3):
        assert all(
            (cell.fill.fgColor.rgb or "").endswith(_DUP_COLOR)
            for cell in ws[row]
        )
