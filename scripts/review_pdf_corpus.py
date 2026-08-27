"""Local interactive ground-truth review for Panda's private PDF corpus."""

from __future__ import annotations

import argparse
import logging
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import diagnose_pdf_batch as batch


FIELD_SPECS = (
    ("expected_supplier", "Supplier", "business_name"),
    ("expected_invoice_number", "Invoice number", "invoice_number"),
    ("expected_invoice_date", "Date", "invoice_date"),
    ("expected_amount", "Amount", "amount"),
)


def _panda_text(parser_key: str, value: Any) -> str:
    if value is None:
        return ""
    if parser_key == "amount":
        try:
            return f"{Decimal(str(value)):.2f}"
        except InvalidOperation:
            pass
    return str(value)


def review_priority(record: Mapping[str, Any]) -> tuple[Any, ...]:
    relative = str(record.get("relative_path") or "")
    status_order = {"failed": 0, "needs_review": 1, "processed": 2}
    source = str((record.get("source_detection") or {}).get("source_system", "Unknown"))
    return (
        0 if relative.startswith("_incoming/") else 1,
        status_order.get(str(record.get("status")), 3),
        float(record.get("confidence") or 0.0),
        0 if source == "Unknown" else 1,
        relative.casefold(),
    )


def select_review_records(
    records: Sequence[Mapping[str, Any]],
    *,
    include_all: bool = False,
    new_only: bool = False,
    relative_path: str | None = None,
) -> list[Mapping[str, Any]]:
    selected = list(records)
    if relative_path is not None:
        normalized = Path(relative_path).as_posix()
        return [record for record in selected if record.get("relative_path") == normalized]
    if not include_all:
        selected = [record for record in selected if record.get("reviewed") is not True]
    if new_only:
        selected = [
            record
            for record in selected
            if str(record.get("relative_path") or "").startswith("_incoming/")
        ]
    return sorted(selected, key=review_priority)


def review_record(
    row: Mapping[str, str],
    record: Mapping[str, Any],
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> dict[str, str] | None:
    parser = record.get("parser_result") or {}
    output_fn("=" * 60)
    output_fn(f"File: {record.get('relative_path')}")
    source = record.get("source_detection") or {}
    output_fn(f"Source: {source.get('source_system')} ({source.get('source_confidence')})")
    output_fn(f"Local PDF: {record.get('_absolute_path', '')}")
    output_fn("\nPanda result:")
    for _expected, label, parser_key in FIELD_SPECS:
        output_fn(f"  {label}: {_panda_text(parser_key, parser.get(parser_key)) or '<blank>'}")
    output_fn(f"  Confidence: {float(record.get('confidence') or 0.0):.2f}")
    output_fn(f"  Status: {record.get('status')}")
    output_fn("\nEnter accepts Panda's value; '-' records intentional blank; 'q' aborts.")

    updated = dict(row)
    for expected_key, label, parser_key in FIELD_SPECS:
        panda_value = _panda_text(parser_key, parser.get(parser_key))
        answer = input_fn(f"{label} [Panda: {panda_value or '<blank>'}]: ")
        if answer.casefold() == "q":
            return None
        updated[expected_key] = "" if answer == "-" else panda_value if answer == "" else answer.strip()
    confirm = input_fn("Mark this document reviewed? [y/N]: ").strip().casefold()
    if confirm not in {"y", "yes"}:
        return None
    updated["reviewed"] = "true"
    return updated


def replace_manifest_row(
    rows: Sequence[Mapping[str, str]], updated: Mapping[str, str],
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    replaced = False
    for row in rows:
        same = bool(updated.get("sha256")) and row.get("sha256") == updated.get("sha256")
        same = same or row.get("relative_path") == updated.get("relative_path")
        if same:
            result.append({field: str(updated.get(field, "")) for field in batch.MANIFEST_FIELDS})
            replaced = True
        else:
            result.append({field: str(row.get(field, "")) for field in batch.MANIFEST_FIELDS})
    if not replaced:
        result.append({field: str(updated.get(field, "")) for field in batch.MANIFEST_FIELDS})
    return sorted(result, key=lambda item: item["relative_path"].casefold())


def run(
    corpus_root: Path,
    *,
    include_all: bool = False,
    new_only: bool = False,
    relative_path: str | None = None,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> int:
    root = corpus_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "pdf_manifest.csv"
    snapshot = batch.read_manifest(manifest_path)
    paths, duplicates, _identities = batch.discover_unique_pdfs(root, snapshot)
    records = batch.analyze_corpus(root, paths)
    batch.attach_manifest_state(records, snapshot)
    manifest_rows = batch.write_manifest(records, manifest_path)
    batch.attach_manifest_state(records, manifest_rows)
    for record in records:
        record["_absolute_path"] = str(root / str(record["relative_path"]))

    selected = select_review_records(
        records,
        include_all=include_all,
        new_only=new_only,
        relative_path=relative_path,
    )
    if relative_path is not None and not selected:
        output_fn(f"PDF not found in corpus: {Path(relative_path).as_posix()}")
        return 1
    if duplicates:
        output_fn(f"Duplicate PDFs require manual attention: {len(duplicates)}")
    if not selected:
        output_fn("No documents match the requested review queue.")
        return 0

    by_sha, by_path = batch.manifest_indexes(manifest_rows)
    for index, record in enumerate(selected, start=1):
        output_fn(f"\nDOCUMENT {index} / {len(selected)}")
        row = by_sha.get(str(record.get("sha256") or "")) or by_path.get(
            str(record.get("relative_path") or "")
        )
        if row is None:
            output_fn("Manifest entry is unavailable; review stopped safely.")
            return 1
        updated = review_record(row, record, input_fn=input_fn, output_fn=output_fn)
        if updated is None:
            output_fn("Review stopped; this document was not marked reviewed.")
            return 0
        manifest_rows = replace_manifest_row(manifest_rows, updated)
        batch.atomic_write_manifest(manifest_rows, manifest_path)
        by_sha, by_path = batch.manifest_indexes(manifest_rows)
        output_fn("Ground truth saved.")
    return 0


def _parse_args(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review Panda PDF corpus ground truth locally.")
    parser.add_argument("corpus_root", type=Path)
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--new-only", action="store_true")
    scope.add_argument("--all", action="store_true", dest="include_all")
    scope.add_argument("--file", dest="relative_path")
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    args = _parse_args(arguments)
    try:
        return run(
            args.corpus_root,
            include_all=args.include_all,
            new_only=args.new_only,
            relative_path=args.relative_path,
        )
    except batch.ManifestWriteError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
