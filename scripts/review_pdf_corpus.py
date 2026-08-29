"""Local interactive ground-truth review for Panda's private PDF corpus."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import diagnose_pdf_batch as batch
from app.services.pdf_corpus_service import (
    REVIEW_FIELDS as FIELD_SPECS,
    ManifestWriteError,
    PdfCorpusService,
    panda_field_text as _panda_text,
    replace_manifest_row,
    review_priority,
    select_review_records,
)

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

    service = PdfCorpusService(root)
    service.reload()
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
        service.save_review(
            str(record.get("sha256") or ""),
            {expected: updated.get(expected, "") for expected, _label, _parser in FIELD_SPECS},
        )
        manifest_rows = batch.read_manifest(manifest_path)
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
    except ManifestWriteError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
