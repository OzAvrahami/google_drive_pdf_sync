"""Ground-truth regressions for supplier accuracy Phase 2."""

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

SERVICE_DESCRIPTION_SHAS = (
    "1542bf71649531f5c1b68ebfb0f449d754a0ec61a2339aa83df69aeca44e4e27",
    "b97315c99077d8079888547b5d8174b80ff223d69426fd35344262518d903666",
    "b4b19e90a0394166f66289a4663c93858badd86cd90027950055402166fdd88f",
    "cc78e6a869ec1bdc9b10667be0f7821ab717adc187c46031d447be0f752aa818",
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


@pytest.mark.parametrize("sha256", SERVICE_DESCRIPTION_SHAS)
def test_verified_supplier_wins_over_service_description(
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
