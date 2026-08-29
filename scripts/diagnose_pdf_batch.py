"""Benchmark and optionally organize Panda's local digital-PDF fixture corpus.

Read-only benchmark:
    python -B scripts/diagnose_pdf_batch.py tests/fixtures/pdf

Organization preview/application:
    python -B scripts/diagnose_pdf_batch.py tests/fixtures/pdf --organize --dry-run
    python -B scripts/diagnose_pdf_batch.py tests/fixtures/pdf --organize

The production parser continues to receive only ``extract_text_from_pdf``
output.  Word coordinates and all heuristics in this module are diagnostic.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Mapping, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pdfplumber
from pdfminer.pdftypes import resolve1

from app.parsers.invoice_parser import classify_document_type, parse_invoice_text
from app.parsers.pdf_parser import _RE_PUA, extract_text_from_pdf
from app.parsers.pdf_layout import apply_positional_supplier_override
from app.services.correction_map_service import load_correction_map
from app.services.pdf_corpus_service import (
    MANIFEST_FIELDS,
    DuplicatePdf,
    ManifestWriteError,
    atomic_write_manifest,
    attach_manifest_state,
    correctness_for_record,
    discover_unique_pdfs,
    ground_truth_mismatches,
    manifest_indexes,
    read_manifest,
    scan_pdf_files,
    sha256_file,
    verified_accuracy,
)
from app.services.processing_service import _confidence
from app.utils.text_helpers import normalize_rtl_text
from scripts.diagnose_pdf import (
    _meaningful_native_text,
    _prime_supplier_rules_read_only,
    _processing_status,
)


CSV_FIELDS = (
    "filename",
    "relative_path",
    "sha256",
    "file_size",
    "source_system",
    "source_confidence",
    "creator",
    "producer",
    "pdf_engine",
    "pages",
    "raw_chars",
    "meaningful_chars",
    "native_text",
    "rtl_pattern",
    "document_type",
    "supplier",
    "supplier_score",
    "invoice_date",
    "invoice_number",
    "amount",
    "confidence",
    "status",
    "layout_flags",
    "warnings",
    "error",
    "reviewed",
    "expected_supplier",
    "expected_invoice_number",
    "expected_invoice_date",
    "expected_amount",
    "supplier_correct",
    "invoice_number_correct",
    "invoice_date_correct",
    "amount_correct",
    "fully_correct",
)

CONFIDENCE_ORDER = {"unknown": 0, "low": 1, "medium": 2, "high": 3}

# Deliberately small: these systems are evidenced in the current corpus.
# Text markers require branding context so a supplier name alone is not used.
SOURCE_RULES: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "Morning": {
        "metadata": ("morning",),
        "text": ("morning.co.il", "greeninvoice.co.il"),
    },
    "iCount": {
        "metadata": ("icount",),
        "text": ("icount.co.il", "icount תועצמאב", "באמצעות icount"),
    },
    "Ypay": {
        "metadata": ("ypay",),
        "text": ("ypay.co.il",),
    },
    "Rivhit": {
        "metadata": (),
        "text": (),
        "high_text": ("rivhit.co.il",),
    },
}

HEBREW_RE = re.compile(r"[\u05d0-\u05ea]")
ASCII_OR_DIGIT_RE = re.compile(r"[A-Za-z0-9]")
HEBREW_TOKEN_RE = re.compile(r"[\u05d0-\u05ea][\u05d0-\u05ea\u05f3\u05f4'\"]*")
NUMERIC_TOKEN_RE = re.compile(r"(?<!\w)[0-9][0-9.,:/-]{2,}[0-9](?!\w)")
RTL_ANCHORS = frozenset(
    {
        "חשבונית",
        "חשבון",
        "עסקה",
        "לתשלום",
        "תאריך",
        "מספר",
        "סהכ",
        "מע״מ",
        "מעמ",
        "לכבוד",
        "מקור",
        "קבלה",
        "דרישת",
        "תשלום",
        "עוסק",
        "עמוד",
        "הופק",
        "סה״כ",
    }
)
REVERSED_RTL_ANCHORS = frozenset(anchor[::-1] for anchor in RTL_ANCHORS)


@dataclass(frozen=True, slots=True)
class SourceDetection:
    source_system: str
    source_confidence: str
    source_evidence: tuple[str, ...]
    conflicting: bool = False
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OrganizationMove:
    source: Path
    destination: Path
    source_system: str
    confidence: str
    evidence: tuple[str, ...]
    category: str
    sha256: str = ""
    file_size: int = 0
    unchanged: bool = False
    conflict: str | None = None


def _metadata_value(metadata: Mapping[str, Any], key: str) -> str:
    for candidate, value in metadata.items():
        if str(candidate).lstrip("/").casefold() == key.casefold() and value is not None:
            return str(value)
    return ""


def _extract_xmp(pdf: Any) -> tuple[dict[str, str], str | None]:
    """Best-effort XMP extraction using PDFMiner already used by pdfplumber."""
    try:
        catalog = getattr(getattr(pdf, "doc", None), "catalog", {}) or {}
        metadata_object = catalog.get("Metadata")
        if metadata_object is None:
            return {}, None
        stream = resolve1(metadata_object)
        if not hasattr(stream, "get_data"):
            return {}, "XMP metadata object was not a readable stream"
        root = ET.fromstring(stream.get_data())
        values: dict[str, str] = {}
        for element in root.iter():
            text = (element.text or "").strip()
            if not text:
                continue
            local_name = element.tag.rsplit("}", 1)[-1]
            values.setdefault(local_name, text)
        return values, None
    except Exception as exc:
        return {}, f"XMP metadata could not be read: {type(exc).__name__}: {exc}"


def collect_metadata(pdf: Any) -> tuple[dict[str, Any], list[str]]:
    info = dict(getattr(pdf, "metadata", None) or {})
    xmp, xmp_warning = _extract_xmp(pdf)
    result: dict[str, Any] = {
        "Creator": _metadata_value(info, "Creator"),
        "Producer": _metadata_value(info, "Producer"),
        "Author": _metadata_value(info, "Author"),
        "Title": _metadata_value(info, "Title"),
        "Subject": _metadata_value(info, "Subject"),
        "Keywords": _metadata_value(info, "Keywords"),
        "CreationDate": _metadata_value(info, "CreationDate"),
        "ModDate": _metadata_value(info, "ModDate"),
        "xmp": xmp,
        "pdf_info": {str(key).lstrip("/"): str(value) for key, value in info.items()},
    }
    return result, [xmp_warning] if xmp_warning else []


def detect_pdf_engine(metadata: Mapping[str, Any]) -> str:
    creator = str(metadata.get("Creator") or "")
    producer = str(metadata.get("Producer") or "")
    combined = f"{creator} {producer}".casefold()
    engines: list[str] = []

    if "wkhtmltopdf" in combined:
        engines.append("wkhtmltopdf")
    if "skia/pdf" in combined:
        engines.append("Skia/PDF")
    if "mpdf" in combined:
        engines.append("mPDF")
    if "tcpdf" in combined:
        engines.append("TCPDF")
    if "itextsharp" in combined:
        engines.append("iTextSharp")
    elif "itext" in combined:
        engines.append("iText")
    if "microsoft print to pdf" in combined:
        engines.append("Microsoft Print to PDF")
    if not engines and ("chromium" in combined or "chrome/" in combined):
        engines.append("Chromium PDF")
    if not engines and "pdfsharp" in combined:
        engines.append("PDFsharp")
    return " + ".join(dict.fromkeys(engines)) or "Unknown"


def detect_source_system(metadata: Mapping[str, Any], raw_text: str) -> SourceDetection:
    """Detect source software from explicit product evidence, never supplier names."""
    metadata_fields: list[tuple[str, str]] = []
    for field in ("Creator", "Producer", "Title", "Subject", "Keywords"):
        value = str(metadata.get(field) or "")
        if value:
            metadata_fields.append((field, value))
    for key, value in (metadata.get("xmp") or {}).items():
        metadata_fields.append((f"XMP {key}", str(value)))

    evidence_by_system: dict[str, list[tuple[str, str]]] = defaultdict(list)
    raw_folded = raw_text.casefold()
    for system, rules in SOURCE_RULES.items():
        for marker in rules["metadata"]:
            folded_marker = marker.casefold()
            for field, value in metadata_fields:
                if folded_marker in value.casefold():
                    evidence_by_system[system].append(
                        ("high", f'{field} metadata contains "{marker}"')
                    )
        for marker in rules["text"]:
            if marker.casefold() in raw_folded:
                evidence_by_system[system].append(
                    ("medium", f'document text contains explicit "{marker}" branding')
                )
        for marker in rules.get("high_text", ()):
            if marker.casefold() in raw_folded:
                evidence_by_system[system].append(
                    ("high", f'document text contains explicit "{marker}" branding')
                )

    systems = sorted(evidence_by_system)
    if not systems:
        return SourceDetection(
            "Unknown",
            "unknown",
            ("no defensible source-system metadata or branding evidence",),
        )
    if len(systems) > 1:
        evidence = tuple(
            f"{system}: {description}"
            for system in systems
            for _confidence, description in evidence_by_system[system]
        )
        return SourceDetection(
            "Conflicting",
            "low",
            evidence,
            conflicting=True,
            candidates=tuple(systems),
        )

    system = systems[0]
    entries = evidence_by_system[system]
    confidence = max((item[0] for item in entries), key=CONFIDENCE_ORDER.get)
    return SourceDetection(
        system,
        confidence,
        tuple(dict.fromkeys(description for _level, description in entries)),
        candidates=(system,),
    )


def _rtl_tokens(text: str) -> list[str]:
    return [
        token.replace('"', "").replace("׳", "").replace("״", "")
        for token in HEBREW_TOKEN_RE.findall(text)
    ]


def characterize_rtl(raw_text: str) -> dict[str, Any]:
    if not HEBREW_RE.search(raw_text):
        return {
            "pattern": "no_hebrew",
            "logical_anchor_hits": 0,
            "visual_anchor_hits": 0,
            "normalized_anchor_hits": 0,
            "mixed_direction_lines": 0,
            "suspicious_numeric_reversals": 0,
            "normalization_potentially_harmful": False,
            "numeric_reversal_evidence": [],
            "evidence": [],
        }

    raw_tokens = _rtl_tokens(raw_text)
    normalized_text = normalize_rtl_text(_RE_PUA.sub("", raw_text))
    normalized_tokens = _rtl_tokens(normalized_text)
    logical_hits = sum(token in RTL_ANCHORS for token in raw_tokens)
    visual_hits = sum(token in REVERSED_RTL_ANCHORS for token in raw_tokens)
    normalized_hits = sum(token in RTL_ANCHORS for token in normalized_tokens)

    if logical_hits >= 2 and visual_hits >= 2:
        pattern = "mixed"
    elif logical_hits >= 2 and logical_hits > visual_hits:
        pattern = "logical_order"
    elif visual_hits >= 2 and visual_hits > logical_hits:
        pattern = "visual_order"
    elif normalized_hits >= logical_hits + 3:
        pattern = "visual_order"
    elif logical_hits >= normalized_hits + 3:
        pattern = "logical_order"
    else:
        pattern = "unknown"

    mixed_direction_lines = 0
    numeric_reversal_evidence: list[dict[str, str]] = []
    evidence: list[dict[str, str]] = []
    raw_lines = raw_text.splitlines()
    normalized_lines = normalized_text.splitlines()
    for raw_line, normalized_line in zip(raw_lines, normalized_lines):
        if HEBREW_RE.search(raw_line) and ASCII_OR_DIGIT_RE.search(raw_line):
            mixed_direction_lines += 1
        for token in NUMERIC_TOKEN_RE.findall(raw_line):
            reversed_token = token[::-1]
            if (
                token != reversed_token
                and token not in normalized_line
                and reversed_token in normalized_line
            ):
                numeric_reversal_evidence.append(
                    {
                        "token": token,
                        "normalized_token": reversed_token,
                        "raw": raw_line[:240],
                        "normalized": normalized_line[:240],
                    }
                )
        if raw_line == normalized_line or len(evidence) >= 5:
            continue
        raw_line_tokens = set(_rtl_tokens(raw_line))
        normalized_line_tokens = set(_rtl_tokens(normalized_line))
        if (
            raw_line_tokens & (RTL_ANCHORS | REVERSED_RTL_ANCHORS)
            or normalized_line_tokens & RTL_ANCHORS
        ):
            evidence.append({"raw": raw_line[:240], "normalized": normalized_line[:240]})

    harmful = bool(numeric_reversal_evidence) or (
        pattern in {"logical_order", "mixed"} and normalized_hits < logical_hits
    )
    return {
        "pattern": pattern,
        "logical_anchor_hits": logical_hits,
        "visual_anchor_hits": visual_hits,
        "normalized_anchor_hits": normalized_hits,
        "mixed_direction_lines": mixed_direction_lines,
        "suspicious_numeric_reversals": len(numeric_reversal_evidence),
        "normalization_potentially_harmful": harmful,
        "numeric_reversal_evidence": numeric_reversal_evidence[:5],
        "evidence": evidence,
    }


def analyze_layout(pages: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    wide_lines = 0
    multi_gap_lines = 0
    aligned_table_rows = 0
    recurring_column_bins: Counter[int] = Counter()

    for page in pages:
        width = float(page.get("width") or 0.0)
        words = list(page.get("words") or [])
        grouped: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
        for word in words:
            try:
                grouped[round(float(word["top"]) / 3)].append(word)
            except (KeyError, TypeError, ValueError):
                continue
        threshold = max(90.0, width * 0.22)
        for line_words in grouped.values():
            ordered = sorted(line_words, key=lambda word: float(word.get("x0") or 0.0))
            gaps = [
                float(right.get("x0") or 0.0) - float(left.get("x1") or 0.0)
                for left, right in zip(ordered, ordered[1:])
            ]
            large_gaps = sum(gap >= threshold for gap in gaps)
            if large_gaps:
                wide_lines += 1
            if large_gaps >= 2:
                multi_gap_lines += 1
            if len(ordered) >= 4:
                bins = {round(float(word.get("x0") or 0.0) / 24) for word in ordered}
                for value in bins:
                    recurring_column_bins[value] += 1

    recurring_columns = sum(count >= 4 for count in recurring_column_bins.values())
    if recurring_columns >= 3:
        aligned_table_rows = sum(count >= 4 for count in recurring_column_bins.values())

    flags: list[str] = []
    if wide_lines:
        flags.append("widely_separated_same_line_regions")
    if wide_lines >= 3 or multi_gap_lines >= 2:
        flags.append("possible_multi_column_layout")
    if recurring_columns >= 3:
        flags.append("possible_table_layout")
    return {
        "flags": flags,
        "widely_separated_line_count": wide_lines,
        "multiple_large_gap_line_count": multi_gap_lines,
        "recurring_column_count": recurring_columns,
        "aligned_table_indicator_count": aligned_table_rows,
    }


def _empty_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "filename": path.name,
        "relative_path": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path) if path.is_file() else "",
        "file_size": path.stat().st_size if path.is_file() else 0,
        "metadata": {},
        "pdf_engine": "Unknown",
        "source_detection": asdict(
            SourceDetection("Unknown", "unknown", ("analysis did not complete",))
        ),
        "extraction_metrics": {
            "pages": 0,
            "raw_chars": 0,
            "meaningful_chars": 0,
            "native_text": False,
        },
        "rtl_diagnostics": characterize_rtl(""),
        "layout_diagnostics": analyze_layout([]),
        "parser_result": None,
        "supplier_validation": None,
        "confidence": 0.0,
        "status": "failed",
        "warnings": [],
        "errors": {"extraction": None, "parser": None},
    }


def analyze_pdf(
    path: Path,
    root: Path,
    *,
    correction_map: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    record = _empty_record(path, root)
    raw_pages: list[str] = []
    page_layout: list[dict[str, Any]] = []
    try:
        with pdfplumber.open(path) as pdf:
            metadata, metadata_warnings = collect_metadata(pdf)
            record["metadata"] = metadata
            record["warnings"].extend(metadata_warnings)
            for page_number, page in enumerate(pdf.pages, start=1):
                raw_text = page.extract_text() or ""
                raw_pages.append(raw_text)
                try:
                    words = page.extract_words()
                except Exception as exc:
                    words = []
                    record["warnings"].append(
                        f"page {page_number} word extraction failed: {type(exc).__name__}: {exc}"
                    )
                page_layout.append(
                    {
                        "page": page_number,
                        "width": float(page.width),
                        "height": float(page.height),
                        "words": [
                            {
                                "text": word.get("text", ""),
                                "x0": word.get("x0"),
                                "x1": word.get("x1"),
                                "top": word.get("top"),
                                "bottom": word.get("bottom"),
                            }
                            for word in words
                        ],
                    }
                )
            record["extraction_metrics"]["pages"] = len(pdf.pages)
    except Exception as exc:
        record["errors"]["extraction"] = f"{type(exc).__name__}: {exc}"
        return record

    raw_text = "\n".join(raw_pages)
    native_text, meaningful_chars = _meaningful_native_text(raw_text)
    record["extraction_metrics"].update(
        {
            "raw_chars": len(raw_text),
            "meaningful_chars": meaningful_chars,
            "native_text": native_text,
        }
    )
    record["pdf_engine"] = detect_pdf_engine(record["metadata"])
    record["source_detection"] = asdict(
        detect_source_system(record["metadata"], raw_text)
    )
    record["rtl_diagnostics"] = characterize_rtl(raw_text)
    record["layout_diagnostics"] = analyze_layout(page_layout)
    if record["rtl_diagnostics"]["normalization_potentially_harmful"]:
        record["warnings"].append("current RTL normalization may reduce Hebrew text quality")
    if record["rtl_diagnostics"]["pattern"] == "mixed":
        record["warnings"].append("mixed raw Hebrew ordering requires inspection")

    try:
        production_text = extract_text_from_pdf(str(path))
        document_type = classify_document_type(production_text)
        parsed = parse_invoice_text(
            production_text,
            correction_map=dict(correction_map or {"version": 1, "fields": {}}),
        )
        if parsed:
            apply_positional_supplier_override(
                parsed,
                production_text,
                pages=page_layout,
            )
        confidence = _confidence(parsed)
        record["parser_result"] = deepcopy(parsed)
        if record["parser_result"] is None:
            record["parser_result"] = {"document_type": document_type}
        record["supplier_validation"] = deepcopy(
            (parsed or {}).get("supplier_validation")
        )
        record["confidence"] = confidence
        record["status"] = _processing_status(document_type, parsed)
    except Exception as exc:
        record["errors"]["parser"] = f"{type(exc).__name__}: {exc}"
        record["status"] = "failed"
    return record


def analyze_corpus(
    root: Path,
    paths: Sequence[Path] | None = None,
) -> list[dict[str, Any]]:
    root = root.resolve()
    _prime_supplier_rules_read_only()
    correction_map = load_correction_map()
    records: list[dict[str, Any]] = []
    for path in paths if paths is not None else scan_pdf_files(root):
        try:
            records.append(analyze_pdf(path, root, correction_map=correction_map))
        except Exception as exc:
            record = _empty_record(path, root)
            record["errors"]["extraction"] = (
                f"unexpected analyzer error: {type(exc).__name__}: {exc}"
            )
            records.append(record)
    return records


def select_new_records(
    records: Sequence[Mapping[str, Any]], new_digests: set[str],
) -> list[Mapping[str, Any]]:
    """Freeze new-at-start records; keep unreviewed incoming files visible."""
    return [
        record
        for record in records
        if str(record.get("sha256") or "") in new_digests
        or (
            str(record.get("relative_path") or "").startswith("_incoming/")
            and record.get("reviewed") is not True
        )
    ]


def _csv_record(record: Mapping[str, Any]) -> dict[str, Any]:
    parser = record.get("parser_result") or {}
    source = record.get("source_detection") or {}
    metrics = record.get("extraction_metrics") or {}
    supplier_validation = record.get("supplier_validation") or {}
    errors = record.get("errors") or {}
    return {
        "filename": record.get("filename", ""),
        "relative_path": record.get("relative_path", ""),
        "sha256": record.get("sha256", ""),
        "file_size": record.get("file_size", 0),
        "source_system": source.get("source_system", "Unknown"),
        "source_confidence": source.get("source_confidence", "unknown"),
        "creator": (record.get("metadata") or {}).get("Creator", ""),
        "producer": (record.get("metadata") or {}).get("Producer", ""),
        "pdf_engine": record.get("pdf_engine", "Unknown"),
        "pages": metrics.get("pages", 0),
        "raw_chars": metrics.get("raw_chars", 0),
        "meaningful_chars": metrics.get("meaningful_chars", 0),
        "native_text": str(bool(metrics.get("native_text"))).lower(),
        "rtl_pattern": (record.get("rtl_diagnostics") or {}).get("pattern", "unknown"),
        "document_type": parser.get("document_type") or "",
        "supplier": parser.get("business_name") or "",
        "supplier_score": supplier_validation.get("score", ""),
        "invoice_date": parser.get("invoice_date") or "",
        "invoice_number": parser.get("invoice_number") or "",
        "amount": parser.get("amount", ""),
        "confidence": record.get("confidence", 0.0),
        "status": record.get("status", "failed"),
        "layout_flags": " | ".join((record.get("layout_diagnostics") or {}).get("flags", [])),
        "warnings": " | ".join(record.get("warnings") or []),
        "error": " | ".join(str(value) for value in errors.values() if value),
        "reviewed": str(bool(record.get("reviewed"))).lower(),
        "expected_supplier": record.get("expected_supplier", ""),
        "expected_invoice_number": record.get("expected_invoice_number", ""),
        "expected_invoice_date": record.get("expected_invoice_date", ""),
        "expected_amount": record.get("expected_amount", ""),
        "supplier_correct": record.get("supplier_correct"),
        "invoice_number_correct": record.get("invoice_number_correct"),
        "invoice_date_correct": record.get("invoice_date_correct"),
        "amount_correct": record.get("amount_correct"),
        "fully_correct": record.get("fully_correct"),
    }


def write_benchmark_reports(
    records: Sequence[Mapping[str, Any]],
    csv_path: Path,
    json_path: Path,
) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(_csv_record(record) for record in records)

    payload = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "document_count": len(records),
        "documents": list(records),
        "aggregate": aggregate_statistics(records),
        "ground_truth_mismatches": ground_truth_mismatches(records),
        "investigation_ranking": rank_for_investigation(records),
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def write_manifest(
    records: Sequence[Mapping[str, Any]], manifest_path: Path,
) -> list[dict[str, str]]:
    existing_rows = read_manifest(manifest_path)
    by_sha, by_path = manifest_indexes(existing_rows)
    by_filename: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in existing_rows:
        by_filename[row["filename"]].append(row)
    rows: list[dict[str, str]] = []
    seen_sha: set[str] = set()
    for record in records:
        relative_path = str(record["relative_path"])
        filename = str(record["filename"])
        digest = str(record.get("sha256") or "")
        if digest and digest in seen_sha:
            continue
        if digest:
            seen_sha.add(digest)
        preserved = by_sha.get(digest) if digest else None
        preserved = preserved or by_path.get(relative_path)
        if preserved is None and len(by_filename.get(filename, [])) == 1:
            preserved = by_filename[filename][0]
        source = record.get("source_detection") or {}
        metadata = record.get("metadata") or {}
        row = {
            "filename": filename,
            "relative_path": relative_path,
            "sha256": digest,
            "file_size": str(record.get("file_size") or 0),
            "source_system": str(source.get("source_system", "Unknown")),
            "source_confidence": str(source.get("source_confidence", "unknown")),
            "source_evidence": " | ".join(source.get("source_evidence") or []),
            "creator": str(metadata.get("Creator") or ""),
            "producer": str(metadata.get("Producer") or ""),
            "pdf_engine": str(record.get("pdf_engine") or "Unknown"),
            "rtl_pattern": str((record.get("rtl_diagnostics") or {}).get("pattern", "unknown")),
            "reviewed": "false",
            "expected_supplier": "",
            "expected_invoice_number": "",
            "expected_invoice_date": "",
            "expected_amount": "",
            "notes": "",
        }
        if preserved:
            for field in (
                "reviewed",
                "expected_supplier",
                "expected_invoice_number",
                "expected_invoice_date",
                "expected_amount",
                "notes",
            ):
                row[field] = preserved.get(field, row[field]) or row[field]
        rows.append(row)
    rows.sort(key=lambda row: row["relative_path"].casefold())
    atomic_write_manifest(rows, manifest_path)
    return rows


def source_slug(source_system: str) -> str:
    known = {
        "Morning": "morning",
        "iCount": "icount",
        "Ypay": "ypay",
        "Rivhit": "rivhit",
    }
    if source_system in known:
        return known[source_system]
    normalized = unicodedata.normalize("NFKD", source_system)
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.casefold()).strip("-")
    return slug or "_review"


def plan_organization(root: Path, records: Sequence[Mapping[str, Any]]) -> list[OrganizationMove]:
    root = root.resolve()
    planned_destinations: dict[Path, Path] = {}
    moves: list[OrganizationMove] = []
    for record in records:
        source = (root / str(record["relative_path"])).resolve()
        detection = record.get("source_detection") or {}
        system = str(detection.get("source_system") or "Unknown")
        confidence = str(detection.get("source_confidence") or "unknown")
        conflicting = bool(detection.get("conflicting"))
        if system == "Unknown" or confidence == "unknown":
            folder, category = "_unknown", "unknown"
        elif conflicting or confidence in {"medium", "low"}:
            folder, category = "_review", "review"
        else:
            folder, category = source_slug(system), "high"
        destination = (root / folder / source.name).resolve()

        conflict: str | None = None
        try:
            source.relative_to(root)
            destination.relative_to(root)
        except ValueError:
            conflict = "source or destination escapes corpus root"
        previous = planned_destinations.get(destination)
        if previous is not None and previous != source:
            conflict = f"destination also planned for {previous.relative_to(root).as_posix()}"
        elif destination.exists() and destination != source:
            conflict = "destination already exists"
        planned_destinations[destination] = source
        moves.append(
            OrganizationMove(
                source=source,
                destination=destination,
                source_system=system,
                confidence=confidence,
                evidence=tuple(detection.get("source_evidence") or []),
                category=category,
                sha256=str(record.get("sha256") or ""),
                file_size=int(record.get("file_size") or 0),
                unchanged=source == destination,
                conflict=conflict,
            )
        )
    return moves


def validate_organization_plan(
    root: Path,
    records: Sequence[Mapping[str, Any]],
    moves: Sequence[OrganizationMove],
) -> list[str]:
    errors: list[str] = []
    if len(records) != len(moves):
        errors.append("not every analyzed PDF has exactly one organization plan entry")
    sources = [move.source for move in moves]
    if len(set(sources)) != len(sources):
        errors.append("a source PDF appears more than once in the move plan")
    destinations = [move.destination for move in moves]
    if len(set(destinations)) != len(destinations):
        errors.append("multiple PDFs share a planned destination")
    if any(move.conflict for move in moves):
        errors.append("one or more filename/path conflicts require review")
    root = root.resolve()
    for move in moves:
        if not move.source.is_file():
            errors.append(f"source missing: {move.source.relative_to(root).as_posix()}")
            continue
        if move.file_size and move.source.stat().st_size != move.file_size:
            errors.append(f"file size changed: {move.source.relative_to(root).as_posix()}")
        if move.sha256 and sha256_file(move.source) != move.sha256:
            errors.append(f"SHA-256 changed: {move.source.relative_to(root).as_posix()}")
    return errors


def print_organization_plan(root: Path, moves: Sequence[OrganizationMove]) -> None:
    root = root.resolve()
    print("\nORGANIZATION PLAN\n")
    for move in moves:
        print(move.source.relative_to(root).as_posix())
        print(f"  source: {move.source_system}")
        print(f"  confidence: {move.confidence}")
        print(f"  evidence: {'; '.join(move.evidence)}")
        print(f"  destination: {move.destination.relative_to(root).as_posix()}")
        if move.conflict:
            print(f"  CONFLICT: {move.conflict}")
        elif move.unchanged:
            print("  unchanged")
        print()
    counts = Counter(move.category for move in moves if not move.unchanged)
    print(f"High-confidence source moves: {counts['high']}")
    print(f"Review moves:                 {counts['review']}")
    print(f"Unknown moves:                {counts['unknown']}")
    print(f"Unchanged:                    {sum(move.unchanged for move in moves)}")
    print(f"Conflicts:                    {sum(bool(move.conflict) for move in moves)}")


def apply_organization(root: Path, moves: Sequence[OrganizationMove]) -> int:
    root = root.resolve()
    changed = 0
    for move in moves:
        if move.conflict:
            continue
        if move.unchanged:
            continue
        move.source.relative_to(root)
        move.destination.relative_to(root)
        move.destination.parent.mkdir(parents=True, exist_ok=True)
        move.source.rename(move.destination)
        if move.file_size and move.destination.stat().st_size != move.file_size:
            raise RuntimeError(f"organized PDF size changed: {move.destination}")
        if move.sha256 and sha256_file(move.destination) != move.sha256:
            raise RuntimeError(f"organized PDF SHA-256 changed: {move.destination}")
        changed += 1
    return changed


def update_record_paths_after_organization(
    root: Path,
    records: Sequence[dict[str, Any]],
    moves: Sequence[OrganizationMove],
) -> None:
    root = root.resolve()
    destinations = {
        move.source.relative_to(root).as_posix(): move.destination.relative_to(root).as_posix()
        for move in moves
        if not move.conflict
    }
    for record in records:
        destination = destinations.get(str(record.get("relative_path") or ""))
        if destination:
            record["relative_path"] = destination
            record["filename"] = Path(destination).name


def _distribution(records: Sequence[Mapping[str, Any]], accessor) -> dict[str, int]:
    return dict(sorted(Counter(accessor(record) for record in records).items()))


def aggregate_statistics(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    fields = ("business_name", "invoice_date", "invoice_number", "amount")
    native_records = [
        record
        for record in records
        if (record.get("extraction_metrics") or {}).get("native_text")
    ]
    non_native_records = [
        record
        for record in records
        if not (record.get("extraction_metrics") or {}).get("native_text")
    ]
    result: dict[str, Any] = {
        "status": _distribution(records, lambda r: str(r.get("status", "failed"))),
        "native_digital_count": len(native_records),
        "non_native_count": len(non_native_records),
        "native_digital_status": _distribution(
            native_records,
            lambda r: str(r.get("status", "failed")),
        ),
        "non_native_status": _distribution(
            non_native_records,
            lambda r: str(r.get("status", "failed")),
        ),
        "native_text": _distribution(
            records,
            lambda r: "strong" if (r.get("extraction_metrics") or {}).get("native_text") else "weak_or_none",
        ),
        "source_system": _distribution(
            records,
            lambda r: str((r.get("source_detection") or {}).get("source_system", "Unknown")),
        ),
        "source_confidence": _distribution(
            records,
            lambda r: str((r.get("source_detection") or {}).get("source_confidence", "unknown")),
        ),
        "pdf_engine": _distribution(records, lambda r: str(r.get("pdf_engine", "Unknown"))),
        "rtl_pattern": _distribution(
            records,
            lambda r: str((r.get("rtl_diagnostics") or {}).get("pattern", "unknown")),
        ),
        "field_coverage": {
            field: sum(bool((record.get("parser_result") or {}).get(field)) for record in records)
            for field in fields
        },
        "suspicious_rtl": sum(
            bool((record.get("rtl_diagnostics") or {}).get("normalization_potentially_harmful"))
            for record in records
        ),
        "layout_flags": Counter(
            flag
            for record in records
            for flag in (record.get("layout_diagnostics") or {}).get("flags", [])
        ),
        "verified_accuracy": verified_accuracy(records),
    }
    result["layout_flags"] = dict(sorted(result["layout_flags"].items()))

    by_source: dict[str, Any] = {}
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str((record.get("source_detection") or {}).get("source_system", "Unknown"))].append(record)
    for system, items in sorted(grouped.items()):
        confidences = [float(item.get("confidence") or 0.0) for item in items]
        by_source[system] = {
            "documents": len(items),
            "status": _distribution(items, lambda item: str(item.get("status", "failed"))),
            "field_coverage": {
                field: sum(bool((item.get("parser_result") or {}).get(field)) for item in items)
                for field in fields
            },
            "average_confidence": round(mean(confidences), 3) if confidences else 0.0,
            "minimum_confidence": min(confidences, default=0.0),
            "rtl_pattern": _distribution(
                items,
                lambda item: str((item.get("rtl_diagnostics") or {}).get("pattern", "unknown")),
            ),
            "creator": _distribution(items, lambda item: str((item.get("metadata") or {}).get("Creator") or "Unknown")),
            "producer": _distribution(items, lambda item: str((item.get("metadata") or {}).get("Producer") or "Unknown")),
            "pdf_engine": _distribution(items, lambda item: str(item.get("pdf_engine") or "Unknown")),
            "layout_warning_count": sum(bool((item.get("layout_diagnostics") or {}).get("flags")) for item in items),
            "suspicious_rtl_count": sum(
                bool((item.get("rtl_diagnostics") or {}).get("normalization_potentially_harmful"))
                for item in items
            ),
        }
    result["by_source_system"] = by_source
    return result


def _investigation_score(record: Mapping[str, Any]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    status = record.get("status")
    parser = record.get("parser_result") or {}
    rtl = record.get("rtl_diagnostics") or {}
    source = record.get("source_detection") or {}
    layout = record.get("layout_diagnostics") or {}
    if status == "failed":
        score += 100
        reasons.append("failed")
    elif status == "needs_review":
        score += 70
        reasons.append("needs_review")
    for field, label in (
        ("invoice_number", "missing invoice number"),
        ("amount", "missing amount"),
        ("business_name", "missing supplier"),
    ):
        if not parser.get(field):
            score += 18
            reasons.append(label)
    if rtl.get("normalization_potentially_harmful"):
        score += 35
        reasons.append("potentially harmful RTL normalization")
    if rtl.get("pattern") in {"logical_order", "mixed"}:
        score += 20
        reasons.append(f"RTL {rtl.get('pattern')}")
    if source.get("source_system") in {"Unknown", "Conflicting"}:
        score += 12
        reasons.append("unknown/conflicting source system")
    if layout.get("flags"):
        score += 10
        reasons.append("layout diagnostics")
    score += round((1.0 - float(record.get("confidence") or 0.0)) * 20)
    return score, reasons


def rank_for_investigation(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    ranked = []
    for record in records:
        score, reasons = _investigation_score(record)
        ranked.append(
            {
                "relative_path": record.get("relative_path"),
                "score": score,
                "confidence": record.get("confidence"),
                "status": record.get("status"),
                "reasons": reasons,
            }
        )
    return sorted(ranked, key=lambda item: (-item["score"], str(item["relative_path"]).casefold()))


def _print_distribution(title: str, values: Mapping[str, int]) -> None:
    print(f"\n{title}\n{'-' * len(title)}")
    for label, count in values.items():
        print(f"{label}: {count}")


def _print_verified_accuracy(records: Sequence[Mapping[str, Any]]) -> None:
    accuracy = verified_accuracy(records)
    print("\nVerified Ground-Truth Accuracy\n------------------------------")
    print(f"Reviewed: {accuracy['reviewed']} / {accuracy['total']}")
    labels = {
        "supplier_correct": "Supplier",
        "invoice_date_correct": "Date",
        "invoice_number_correct": "Number",
        "amount_correct": "Amount",
    }
    for field, label in labels.items():
        stats = accuracy["fields"][field]
        print(f"{label}: {stats['correct']} / {stats['total']} correct")
    print(
        f"Fully correct: {accuracy['fully_correct']} / {accuracy['reviewed']}"
    )
    if accuracy["by_source"]:
        print("\nVerified accuracy by source\n---------------------------")
        for source, stats in accuracy["by_source"].items():
            print(
                f"{source}: {stats['fully_correct']}/{stats['reviewed']} fully correct"
            )
    mismatches = ground_truth_mismatches(records)
    print("\nGround-truth mismatches\n-----------------------")
    if not mismatches:
        print("None")
    for item in mismatches:
        print(item["relative_path"])
        for field in item["fields"]:
            print(f"  {field['field']}: Panda={field['panda']!r}; Expected={field['expected']!r}")


def print_new_only_report(
    records: Sequence[Mapping[str, Any]], duplicates: Sequence[DuplicatePdf] = (),
) -> None:
    print("\nNEW DIGITAL PDF DOCUMENTS")
    print("=" * 25)
    print(f"\nNew PDFs discovered: {len(records)}")
    aggregate = aggregate_statistics(records)
    _print_distribution("Operational results", aggregate["status"])
    _print_distribution("Native text", aggregate["native_text"])
    _print_distribution("Detected sources", aggregate["source_system"])
    _print_distribution("Source confidence", aggregate["source_confidence"])
    coverage = aggregate["field_coverage"]
    print("\nParser field presence\n---------------------")
    print(f"Supplier: {coverage['business_name']}/{len(records)}")
    print(f"Date: {coverage['invoice_date']}/{len(records)}")
    print(f"Number: {coverage['invoice_number']}/{len(records)}")
    print(f"Amount: {coverage['amount']}/{len(records)}")
    print("\nDocuments\n---------")
    if not records:
        print("No newly discovered or unreviewed incoming PDFs.")
    for record in records:
        parser = record.get("parser_result") or {}
        source = record.get("source_detection") or {}
        print(record.get("relative_path"))
        print(f"  source: {source.get('source_system')} ({source.get('source_confidence')})")
        print(f"  supplier parsed: {parser.get('business_name') or '<missing>'}")
        print(f"  invoice number parsed: {parser.get('invoice_number') or '<missing>'}")
        print(f"  date parsed: {parser.get('invoice_date') or '<missing>'}")
        print(f"  amount parsed: {parser.get('amount') if parser.get('amount') is not None else '<missing>'}")
        print(f"  Panda confidence: {float(record.get('confidence') or 0):.2f}")
        print(f"  status: {record.get('status')}")
        if record.get("warnings"):
            print(f"  warnings: {'; '.join(record['warnings'])}")
    if duplicates:
        print("\nDuplicate PDFs detected\n-----------------------")
        for duplicate in duplicates:
            print(f"Incoming: {duplicate.duplicate}")
            print(f"Existing: {duplicate.canonical}")
            print(f"SHA-256: {duplicate.sha256}")


def print_aggregate_report(
    records: Sequence[Mapping[str, Any]],
    *,
    new_count: int = 0,
    duplicates: Sequence[DuplicatePdf] = (),
) -> None:
    aggregate = aggregate_statistics(records)
    print("\n" + "=" * 60)
    print("PANDA DIGITAL PDF BENCHMARK")
    print("=" * 60)
    reviewed_count = sum(record.get("reviewed") is True for record in records)
    print("\nCorpus\n------")
    print(f"PDFs analyzed: {len(records)}")
    print(f"New since manifest snapshot: {new_count}")
    print(f"Reviewed: {reviewed_count} / {len(records)}")
    print(f"Unreviewed: {len(records) - reviewed_count}")
    _print_distribution("Production result", aggregate["status"])
    _print_distribution("Native text", aggregate["native_text"])
    print("\nDigital/native split\n--------------------")
    print(f"Native digital PDFs: {aggregate['native_digital_count']}")
    print(f"Non-native / no meaningful text: {aggregate['non_native_count']}")
    _print_distribution(
        "Native digital operational result",
        aggregate["native_digital_status"],
    )
    if aggregate["non_native_count"]:
        _print_distribution("Non-native operational result", aggregate["non_native_status"])
    _print_distribution("Source systems", aggregate["source_system"])
    _print_distribution("Source confidence", aggregate["source_confidence"])
    _print_distribution("PDF engines", aggregate["pdf_engine"])
    _print_distribution("RTL diagnostic", aggregate["rtl_pattern"])

    coverage = aggregate["field_coverage"]
    print("\nParser field coverage\n---------------------")
    for field, label in (
        ("business_name", "Supplier found"),
        ("invoice_date", "Invoice date found"),
        ("invoice_number", "Invoice number found"),
        ("amount", "Amount found"),
    ):
        print(f"{label}: {coverage[field]} / {len(records)}")

    print("\nPotential extraction concerns\n-----------------------------")
    print(f"Suspicious RTL normalization: {aggregate['suspicious_rtl']}")
    for flag, count in aggregate["layout_flags"].items():
        print(f"{flag}: {count}")

    print("\nPer-source-system statistics\n----------------------------")
    for system, stats in aggregate["by_source_system"].items():
        print(f"\n{system}\n{'~' * len(system)}")
        print(f"Documents: {stats['documents']}")
        for status, count in stats["status"].items():
            print(f"{status}: {count}")
        print(
            "Coverage: "
            f"supplier {stats['field_coverage']['business_name']}/{stats['documents']}, "
            f"date {stats['field_coverage']['invoice_date']}/{stats['documents']}, "
            f"number {stats['field_coverage']['invoice_number']}/{stats['documents']}, "
            f"amount {stats['field_coverage']['amount']}/{stats['documents']}"
        )
        print(
            f"Panda confidence: avg {stats['average_confidence']:.2f}, "
            f"min {stats['minimum_confidence']:.2f}"
        )
        print(f"RTL: {stats['rtl_pattern']}")
        print(f"Creator: {stats['creator']}")
        print(f"Producer: {stats['producer']}")
        print(f"PDF engine: {stats['pdf_engine']}")
        print(f"Layout warnings: {stats['layout_warning_count']}")
        print(f"Suspicious RTL: {stats['suspicious_rtl_count']}")

    ranking = rank_for_investigation(records)
    print("\nLowest-confidence documents\n---------------------------")
    for item in sorted(ranking, key=lambda value: (float(value["confidence"] or 0), str(value["relative_path"])))[:10]:
        print(f"{float(item['confidence'] or 0):.2f}  {item['relative_path']}")
    print("\nNeeds-inspection documents\n--------------------------")
    for item in ranking[:15]:
        print(f"{item['score']:3d}  {item['relative_path']} - {', '.join(item['reasons'])}")
    unknown = [
        record["relative_path"]
        for record in records
        if (record.get("source_detection") or {}).get("source_system") in {"Unknown", "Conflicting"}
    ]
    if unknown:
        print("\nUnknown/ambiguous source systems\n--------------------------------")
        for path in unknown:
            print(path)
    _print_verified_accuracy(records)
    if duplicates:
        print("\nDuplicate PDFs detected\n-----------------------")
        for duplicate in duplicates:
            print(
                f"{duplicate.duplicate} duplicates {duplicate.canonical} "
                f"({duplicate.sha256})"
            )


def _default_artifacts() -> tuple[Path, Path]:
    root = Path(__file__).resolve().parents[1]
    return root / "artifacts" / "pdf_benchmark.csv", root / "artifacts" / "pdf_benchmark.json"


def run(
    corpus_root: Path,
    *,
    organize: bool = False,
    dry_run: bool = False,
    new_only: bool = False,
    csv_path: Path | None = None,
    json_path: Path | None = None,
) -> int:
    root = corpus_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    csv_default, json_default = _default_artifacts()
    csv_path = (csv_path or csv_default).resolve()
    json_path = (json_path or json_default).resolve()
    manifest_path = root / "pdf_manifest.csv"
    manifest_snapshot = read_manifest(manifest_path)
    by_sha, by_path = manifest_indexes(manifest_snapshot)
    paths, duplicates, identities = discover_unique_pdfs(root, manifest_snapshot)
    new_digests = {
        digest
        for path, (digest, _size) in identities.items()
        if path in paths
        and digest not in by_sha
        and path.relative_to(root).as_posix() not in by_path
    }
    records = analyze_corpus(root, paths)
    attach_manifest_state(records, manifest_snapshot)
    new_records = select_new_records(records, new_digests)
    if new_only:
        print_new_only_report(new_records, duplicates)
    else:
        print_aggregate_report(records, new_count=len(new_digests), duplicates=duplicates)

    if organize:
        moves = plan_organization(root, records)
        print_organization_plan(root, moves)
        errors = validate_organization_plan(root, records, moves)
        if errors:
            print("Organization validation failed:", file=sys.stderr)
            for error in errors:
                print(f"- {error}", file=sys.stderr)
            return 1
        if dry_run:
            print("Dry run complete: no filesystem changes made.")
            return 0
        # Fail before moving PDFs when the private manifest cannot be replaced
        # (most commonly because Excel has it open on Windows).
        write_manifest(records, manifest_path)
        pdf_count_before = len(scan_pdf_files(root))
        changed = apply_organization(root, moves)
        pdf_count_after = len(scan_pdf_files(root))
        if pdf_count_after != pdf_count_before:
            raise RuntimeError(
                f"organization changed PDF count: {pdf_count_before} -> {pdf_count_after}"
            )
        update_record_paths_after_organization(root, records, moves)
        write_benchmark_reports(records, csv_path, json_path)
        write_manifest(records, manifest_path)
        print(f"Organization applied: {changed} PDF(s) moved.")
        return 0

    write_benchmark_reports(records, csv_path, json_path)
    write_manifest(records, manifest_path)
    print(f"\nCSV report: {csv_path}")
    print(f"JSON report: {json_path}")
    print(f"Manifest: {manifest_path}")
    return 0


def _parse_args(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark Panda's current native digital-PDF pipeline."
    )
    parser.add_argument("corpus_root", type=Path)
    parser.add_argument("--organize", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--new-only", action="store_true")
    parser.add_argument("--csv", type=Path, default=None)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(arguments)
    if args.dry_run and not args.organize:
        parser.error("--dry-run requires --organize")
    if args.new_only and args.organize:
        parser.error("--new-only cannot be combined with --organize")
    return args


def main(arguments: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    # Some otherwise-readable corpus PDFs have incomplete optional font
    # descriptors.  pdfminer logs a warning for every affected glyph/page;
    # keep the aggregate CLI readable while real parse failures remain caught
    # and recorded per document by ``analyze_pdf``.
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    args = _parse_args(arguments)
    try:
        return run(
            args.corpus_root,
            organize=args.organize,
            dry_run=args.dry_run,
            new_only=args.new_only,
            csv_path=args.csv,
            json_path=args.json,
        )
    except ManifestWriteError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
