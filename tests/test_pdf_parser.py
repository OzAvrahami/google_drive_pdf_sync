"""Deterministic tests for PDF text-extraction orchestration."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.parsers.pdf_parser import extract_text_from_pdf


def test_missing_pdf_raises_file_not_found(tmp_path: Path) -> None:
    missing = tmp_path / "missing.pdf"

    with pytest.raises(FileNotFoundError, match="PDF file not found"):
        extract_text_from_pdf(str(missing))


def test_extracts_each_page_and_removes_private_use_glyphs(tmp_path: Path) -> None:
    pdf_path = tmp_path / "synthetic.pdf"
    pdf_path.write_bytes(b"synthetic test placeholder")

    first_page = MagicMock()
    first_page.extract_text.return_value = "Invoice \uf8ffnumber 123"
    second_page = MagicMock()
    second_page.extract_text.return_value = None

    opened_pdf = MagicMock()
    opened_pdf.pages = [first_page, second_page]

    with patch("app.parsers.pdf_parser.pdfplumber.open") as mock_open:
        mock_open.return_value.__enter__.return_value = opened_pdf
        text = extract_text_from_pdf(str(pdf_path))

    mock_open.assert_called_once_with(pdf_path)
    assert "--- PAGE 1 ---" in text
    assert "Invoice number 123" in text
    assert "\uf8ff" not in text
    assert "--- PAGE 2 ---" in text
    first_page.extract_text.assert_called_once_with()
    second_page.extract_text.assert_called_once_with()
