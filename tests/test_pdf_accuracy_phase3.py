"""Ground-truth regressions for supplier accuracy Phase 3."""

from __future__ import annotations

import csv
from copy import deepcopy
from pathlib import Path

import pytest

import app.parsers.supplier_validator as supplier_validator
from app.parsers.invoice_parser import parse_invoice_text
from app.parsers.pdf_parser import extract_text_from_pdf
from app.services.pdf_corpus_service import correctness_for_record


CORPUS = Path(__file__).parent / "fixtures" / "pdf"
MANIFEST = CORPUS / "pdf_manifest.csv"

PHASE3_TARGET_SHAS = (
    "df63fea9a07ae5208e55ca7b90a30b7f57f6c9405fa2832c9d594502ce87025f",
    "213eba333d41e258a88573153efcd46f43794e5334f27f948fc010a5eef1d53e",
)


def _manifest_row(sha256: str) -> dict[str, str]:
    if not MANIFEST.is_file():
        pytest.skip("private real-PDF manifest not available locally")
    with MANIFEST.open(encoding="utf-8-sig", newline="") as stream:
        row = next(
            (item for item in csv.DictReader(stream) if item.get("sha256") == sha256),
            None,
        )
    if row is None:
        pytest.skip("private real-PDF fixture is not registered locally")
    return row


@pytest.mark.parametrize("sha256", PHASE3_TARGET_SHAS)
def test_phase3_target_matches_verified_supplier(
    sha256: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = _manifest_row(sha256)
    path = CORPUS / Path(row["relative_path"])
    if not path.is_file():
        pytest.skip("private real-PDF fixture not available locally")

    rules = deepcopy(supplier_validator._DEFAULT_BASE_RULES)
    rules["learned"] = []
    monkeypatch.setattr(supplier_validator, "_rules_cache", rules)
    parsed = parse_invoice_text(
        extract_text_from_pdf(str(path)),
        correction_map={"version": 1, "fields": {}},
    )

    assert parsed is not None
    assert row["reviewed"] == "true"
    assert correctness_for_record({"parser_result": parsed}, row)["supplier_correct"] is True
    assert parsed["invoice_date"] == row["expected_invoice_date"]
    assert str(parsed["invoice_number"]) == row["expected_invoice_number"]
    assert float(parsed["amount"]) == pytest.approx(float(row["expected_amount"]))
