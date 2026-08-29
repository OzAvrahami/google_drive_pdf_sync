"""CLI/reporting for Panda's shared positional supplier analyzer.

Examples::

    python -B scripts/diagnose_pdf_layout.py tests/fixtures/pdf
    python -B scripts/diagnose_pdf_layout.py tests/fixtures/pdf \
        --json artifacts/pdf_layout_supplier_prototype.json
    python -B scripts/diagnose_pdf_layout.py path/to/invoice.pdf --details
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.parsers.invoice_parser import parse_invoice_text
from app.parsers.pdf_layout import (
    analyze_page_header,
    analyze_pdf_layout,
    group_rows as _group_rows,
    normalize_mirrored_rtl_parentheses as _normalize_mirrored_rtl_parentheses,
    row_text as _row_text,
)
from app.parsers.pdf_parser import extract_text_from_pdf
from app.services.correction_map_service import load_correction_map
from app.services.pdf_corpus_service import (
    _normalized_supplier,
    discover_unique_pdfs,
    manifest_indexes,
    read_manifest,
    scan_pdf_files,
    sha256_file,
)
from scripts.diagnose_pdf import _prime_supplier_rules_read_only


def _parse_current_supplier(path: Path, correction_map: Mapping[str, Any]) -> str | None:
    """Return the text parser's supplier so the layout proposal stays visible."""

    parsed = parse_invoice_text(
        extract_text_from_pdf(str(path)), correction_map=dict(correction_map)
    )
    return (parsed or {}).get("business_name")


def analyze_corpus(root: Path) -> dict[str, Any]:
    root = root.resolve()
    manifest_rows = read_manifest(root / "pdf_manifest.csv")
    by_sha, _by_path = manifest_indexes(manifest_rows)
    unique_paths, duplicates, _identities = discover_unique_pdfs(root, manifest_rows)
    paths = scan_pdf_files(root)
    _prime_supplier_rules_read_only()
    correction_map = load_correction_map()
    records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for path in paths:
        digest = sha256_file(path)
        manifest = by_sha.get(digest, {})
        try:
            current_supplier = _parse_current_supplier(path, correction_map)
            observations = analyze_pdf_layout(path, current_supplier=current_supplier)
        except Exception as exc:
            errors.append(
                {
                    "relative_path": path.relative_to(root).as_posix(),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        if not observations:
            continue
        observation = max(
            observations,
            key=lambda item: (
                item["proposal"]["would_change"],
                item["issuer_candidate_score"],
                item["anchor"]["row_span"],
            ),
        )
        reviewed = str(manifest.get("reviewed", "false")).casefold() == "true"
        expected = str(manifest.get("expected_supplier") or "")
        proposed = str(observation["proposal"].get("supplier") or "")
        records.append(
            {
                "sha256": digest,
                "relative_path": path.relative_to(root).as_posix(),
                "source_system": str(manifest.get("source_system") or "Unknown"),
                "pdf_engine": str(manifest.get("pdf_engine") or "Unknown"),
                "reviewed": reviewed,
                "current_panda_supplier": current_supplier,
                "expected_supplier": expected if reviewed else None,
                "current_supplier_correct": (
                    _normalized_supplier(current_supplier)
                    == _normalized_supplier(expected)
                    if reviewed
                    else None
                ),
                "proposal_matches_ground_truth": (
                    _normalized_supplier(proposed) == _normalized_supplier(expected)
                    if reviewed and proposed
                    else None
                ),
                "layout": observation,
            }
        )

    summary = summarize(records)
    summary.update(
        {
            "unique_pdf_identities": len(unique_paths),
            "physical_pdf_files": len(paths),
            "duplicate_files": len(duplicates),
            "analysis_errors": len(errors),
        }
    )
    return {
        "schema_version": 1,
        "diagnostic_only": True,
        "corpus_root": str(root),
        "summary": summary,
        "records": records,
        "errors": errors,
    }


def summarize(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    reviewed = [record for record in records if record.get("reviewed") is True]
    reviewed_correct = [
        record for record in reviewed if record.get("current_supplier_correct") is True
    ]
    reviewed_changes = [
        record
        for record in reviewed
        if (record.get("layout") or {}).get("proposal", {}).get("would_change")
    ]
    unreviewed_changes = [
        record
        for record in records
        if record.get("reviewed") is not True
        and (record.get("layout") or {}).get("proposal", {}).get("would_change")
    ]
    return {
        "positional_family_documents": len(records),
        "positional_family_unique_identities": len(
            {str(record.get("sha256") or "") for record in records}
        ),
        "reviewed_documents": len(reviewed),
        "reviewed_currently_correct": len(reviewed_correct),
        "reviewed_currently_incorrect": len(reviewed) - len(reviewed_correct),
        "reviewed_proposed_changes": len(reviewed_changes),
        "reviewed_proposals_matching_ground_truth": sum(
            record.get("proposal_matches_ground_truth") is True
            for record in reviewed_changes
        ),
        "reviewed_proposals_mismatching_ground_truth": sum(
            record.get("proposal_matches_ground_truth") is False
            for record in reviewed_changes
        ),
        "unreviewed_proposed_changes": len(unreviewed_changes),
        "unreviewed_proposed_unique_identities": len(
            {str(record.get("sha256") or "") for record in unreviewed_changes}
        ),
        "source_distribution": dict(
            Counter(str(record.get("source_system") or "Unknown") for record in records)
        ),
        "engine_distribution": dict(
            Counter(str(record.get("pdf_engine") or "Unknown") for record in records)
        ),
    }


def print_report(report: Mapping[str, Any], *, details: bool = False) -> None:
    summary = report.get("summary") or {}
    print("=" * 60)
    print("PANDA POSITIONAL SUPPLIER PROTOTYPE (DIAGNOSTIC ONLY)")
    print("=" * 60)
    print(f"Unique PDF identities:       {summary.get('unique_pdf_identities', 0)}")
    print(f"Physical PDF files:          {summary.get('physical_pdf_files', 0)}")
    print(f"Positional family:           {summary.get('positional_family_documents', 0)}")
    print(
        "Positional unique identities: "
        f"{summary.get('positional_family_unique_identities', 0)}"
    )
    print(f"Reviewed in family:          {summary.get('reviewed_documents', 0)}")
    print(f"Reviewed currently correct:  {summary.get('reviewed_currently_correct', 0)}")
    print(f"Reviewed currently wrong:    {summary.get('reviewed_currently_incorrect', 0)}")
    print(f"Reviewed proposed changes:   {summary.get('reviewed_proposed_changes', 0)}")
    print(
        "Reviewed proposals correct: "
        f"{summary.get('reviewed_proposals_matching_ground_truth', 0)}"
    )
    print(
        "Reviewed proposals wrong:   "
        f"{summary.get('reviewed_proposals_mismatching_ground_truth', 0)}"
    )
    print(f"Unreviewed proposed changes: {summary.get('unreviewed_proposed_changes', 0)}")
    print(f"Analysis errors:             {summary.get('analysis_errors', 0)}")

    proposed = [
        record
        for record in report.get("records") or []
        if (record.get("layout") or {}).get("proposal", {}).get("would_change")
    ]
    if proposed:
        print("\nPROPOSED CHANGES")
        print("----------------")
        for record in proposed:
            proposal = record["layout"]["proposal"]
            print(record["relative_path"])
            print(f"  Panda:      {record.get('current_panda_supplier')}")
            print(f"  Prototype:  {proposal.get('supplier')}")
            if record.get("reviewed"):
                print(f"  Expected:   {record.get('expected_supplier')}")
                print(f"  GT match:   {record.get('proposal_matches_ground_truth')}")

    if details:
        print("\nALL POSITIONAL-FAMILY RECORDS")
        print("-----------------------------")
        for record in report.get("records") or []:
            print(json.dumps(record, ensure_ascii=False, indent=2))


def _parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnostic-only positional supplier/header prototype."
    )
    parser.add_argument("path", type=Path, help="PDF file or corpus root")
    parser.add_argument("--json", type=Path, default=None, help="optional JSON report")
    parser.add_argument("--details", action="store_true", help="print every record")
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    args = _parse_args(arguments)
    path = args.path.resolve()
    if not path.exists():
        print(f"Path not found: {path}", file=sys.stderr)
        return 2
    if path.is_file():
        _prime_supplier_rules_read_only()
        current = _parse_current_supplier(path, load_correction_map())
        report: dict[str, Any] = {
            "schema_version": 1,
            "diagnostic_only": True,
            "path": str(path),
            "current_panda_supplier": current,
            "observations": analyze_pdf_layout(path, current_supplier=current),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        report = analyze_corpus(path)
        print_report(report, details=args.details)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nJSON report: {args.json.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
