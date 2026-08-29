"""Read-only diagnostic for Panda's current PDF extraction pipeline.

Usage from the repository root:
    python scripts/diagnose_pdf.py "<pdf-path>"
    python scripts/diagnose_pdf.py --words "<pdf-path>"

Word geometry is kept separate from text parsing and is used only by Panda's
strict positional supplier resolver after the normal text parser succeeds.
Production-equivalent text is produced by ``extract_text_from_pdf``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pdfplumber

import app.parsers.supplier_validator as supplier_validator
from app.parsers.invoice_parser import (
    EXCLUDED_DOCUMENT_TYPES,
    classify_document_type,
    parse_invoice_text,
)
from app.parsers.pdf_parser import _RE_PUA, extract_text_from_pdf
from app.parsers.pdf_layout import apply_positional_supplier_override
from app.services.correction_map_service import load_correction_map
from app.services.processing_service import _confidence
from app.utils.text_helpers import normalize_rtl_text


DEFAULT_WORD_LIMIT = 200


def _section(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _meaningful_native_text(text: str) -> tuple[bool, int]:
    """Return a diagnostic heuristic, not a production OCR decision."""
    meaningful_characters = sum(character.isalnum() for character in text)
    return meaningful_characters >= 20, meaningful_characters


def _processing_status(document_type: str | None, parsed: dict | None) -> str:
    """Mirror ProcessingService's current post-parse status decision."""
    if document_type in EXCLUDED_DOCUMENT_TYPES:
        return "skipped"

    supplier_validation = (parsed or {}).get("supplier_validation", {})
    rejected_without_fallback = (
        not supplier_validation.get("is_valid", True)
        and not supplier_validation.get("fallback_used", False)
    )
    if rejected_without_fallback:
        return "needs_review"
    return "processed" if _confidence(parsed) >= 0.75 else "needs_review"


def _prime_supplier_rules_read_only() -> None:
    """Match the validator's current rule merge without its create-on-missing write."""
    base = supplier_validator._read_json(
        supplier_validator.SUPPLIER_RULES_JSON,
        supplier_validator._DEFAULT_BASE_RULES,
    )
    learned = supplier_validator._read_json(
        supplier_validator.LEARNED_RULES_JSON,
        {"version": 1, "rules": []},
    )
    base["learned"] = learned.get("rules", [])
    supplier_validator._rules_cache = base


def diagnose(pdf_path: Path, *, all_words: bool = False) -> int:
    if not pdf_path.exists():
        print(f"PDF file not found: {pdf_path}", file=sys.stderr)
        return 2
    if not pdf_path.is_file():
        print(f"PDF path is not a file: {pdf_path}", file=sys.stderr)
        return 2

    raw_pages: list[str] = []
    normalized_pages: list[str] = []
    word_rows: list[dict[str, object]] = []
    layout_pages: list[dict[str, object]] = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            metadata = dict(pdf.metadata or {})
            page_count = len(pdf.pages)
            for page_number, page in enumerate(pdf.pages, start=1):
                # This is the exact pdfplumber call made by production.
                raw_text = page.extract_text() or ""
                raw_pages.append(raw_text)

                cleaned_text = _RE_PUA.sub("", raw_text)
                normalized_pages.append(normalize_rtl_text(cleaned_text))

                page_words = page.extract_words()
                layout_pages.append(
                    {
                        "page": page_number,
                        "width": float(page.width),
                        "height": float(page.height),
                        "words": page_words,
                    }
                )
                for word in page_words:
                    word_rows.append(
                        {
                            "page": page_number,
                            "text": word.get("text", ""),
                            "x0": word.get("x0"),
                            "x1": word.get("x1"),
                            "top": word.get("top"),
                            "bottom": word.get("bottom"),
                        }
                    )
    except Exception as exc:
        print(f"Could not inspect PDF: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    raw_text = "\n".join(raw_pages)
    normalized_text = "\n".join(
        f"\n--- PAGE {page_number} ---\n{text}"
        for page_number, text in enumerate(normalized_pages, start=1)
    )
    production_text = extract_text_from_pdf(str(pdf_path))
    has_native_text, meaningful_count = _meaningful_native_text(raw_text)

    _section("1. PDF metadata / basic information")
    print(f"Path: {pdf_path.resolve()}")
    print(f"Page count: {page_count}")
    print(f"Raw extracted character count: {len(raw_text)}")
    print(f"Production text character count: {len(production_text)}")
    print(f"Meaningful alphanumeric character count: {meaningful_count}")
    print(
        "Meaningful native PDF text appears to exist: "
        f"{'yes' if has_native_text else 'no'} "
        "(diagnostic heuristic: at least 20 alphanumeric characters)"
    )
    print("Metadata:")
    print(_json(metadata))

    _section("2. Raw pdfplumber output BEFORE Panda RTL normalization")
    for page_number, text in enumerate(raw_pages, start=1):
        print(f"\n--- RAW PAGE {page_number} ---")
        print(text)

    _section("3. Word-level pdfplumber extraction (diagnostic only)")
    rows = word_rows if all_words else word_rows[:DEFAULT_WORD_LIMIT]
    print("page | x0 | x1 | top | bottom | text")
    for row in rows:
        print(
            f"{row['page']} | {row['x0']} | {row['x1']} | "
            f"{row['top']} | {row['bottom']} | {row['text']}"
        )
    if not all_words and len(word_rows) > len(rows):
        print(
            f"... {len(word_rows) - len(rows)} more words omitted; "
            "rerun with --words to print every word."
        )
    print(f"Total extracted words: {len(word_rows)}")

    _section("4. Text AFTER Panda's current RTL normalization")
    print(normalized_text)

    _section("5. Exact text passed to the invoice parser")
    print(production_text)
    print(
        "\nDiagnostic reconstruction matches production extractor: "
        f"{'yes' if normalized_text == production_text else 'no'}"
    )

    _prime_supplier_rules_read_only()
    correction_map = load_correction_map()
    parsed = parse_invoice_text(production_text, correction_map=correction_map)
    if parsed:
        apply_positional_supplier_override(
            parsed,
            production_text,
            pages=layout_pages,
        )
    document_type = classify_document_type(production_text)
    confidence = _confidence(parsed)
    status = _processing_status(document_type, parsed)

    _section("6. Current structured parser result")
    print(f"Classified document type: {document_type!r}")
    print(_json(parsed))

    _section("7. Current confidence / validation information")
    print(f"Confidence: {confidence:.2f} ({confidence * 100:.0f}%)")
    print(f"Derived ProcessingService status: {status}")
    print("Supplier validation:")
    print(_json((parsed or {}).get("supplier_validation")))
    correction_fields = correction_map.get("fields", {})
    correction_count = sum(len(values) for values in correction_fields.values())
    print(f"Loaded correction-map entries: {correction_count}")
    print("OCR invoked: no")
    return 0


def _parse_args(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect Panda's existing PDF extraction and invoice parser stages."
    )
    parser.add_argument("pdf_path", type=Path, help="Local PDF to inspect")
    parser.add_argument(
        "--words",
        action="store_true",
        help="print every positional word (default: first 200)",
    )
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = _parse_args(arguments)
    return diagnose(args.pdf_path, all_words=args.words)


if __name__ == "__main__":
    raise SystemExit(main())
