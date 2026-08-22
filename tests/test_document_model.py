"""Characterization tests for the active Document model."""

from app.models.document import Document


def _document(**overrides) -> Document:
    values = {
        "drive_file_id": "drive-1",
        "file_name": "invoice.pdf",
        "folder_path": "invoices",
        "supplier_name": "Extracted Supplier",
        "total": 125.5,
    }
    values.update(overrides)
    return Document(**values)


def test_effective_returns_extracted_model_value_without_correction() -> None:
    doc = _document()

    assert doc.effective("supplier_name") == "Extracted Supplier"


def test_effective_returns_corrected_override() -> None:
    doc = _document(corrected_data={"supplier_name": "Corrected Supplier"})

    assert doc.effective("supplier_name") == "Corrected Supplier"


def test_effective_falls_back_when_corrected_key_is_absent() -> None:
    doc = _document(corrected_data={"invoice_number": "INV-7"})

    assert doc.effective("supplier_name") == "Extracted Supplier"


def test_effective_falls_back_for_none_correction() -> None:
    doc = _document(corrected_data={"total": None})

    assert doc.effective("total") == 125.5


def test_effective_falls_back_for_empty_string_correction() -> None:
    """Explicit clearing is not supported by the current model."""
    doc = _document(corrected_data={"supplier_name": ""})

    assert doc.effective("supplier_name") == "Extracted Supplier"


def test_effective_preserves_zero_as_a_correction() -> None:
    doc = _document(corrected_data={"total": 0})

    assert doc.effective("total") == 0
