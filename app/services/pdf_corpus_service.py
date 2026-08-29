"""Local-only PDF benchmark corpus inventory and human review service.

This module is deliberately Qt-independent.  It owns manifest identity,
ground-truth comparison, review persistence, filtering, and selected-document
analysis so the terminal and Panda 2.0 review experiences share one contract.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


MANIFEST_FIELDS = (
    "filename",
    "relative_path",
    "sha256",
    "file_size",
    "source_system",
    "source_confidence",
    "source_evidence",
    "creator",
    "producer",
    "pdf_engine",
    "rtl_pattern",
    "reviewed",
    "expected_supplier",
    "expected_invoice_number",
    "expected_invoice_date",
    "expected_amount",
    "notes",
)

REVIEW_FIELDS = (
    ("expected_supplier", "Supplier", "business_name"),
    ("expected_invoice_number", "Invoice number", "invoice_number"),
    ("expected_invoice_date", "Date", "invoice_date"),
    ("expected_amount", "Amount", "amount"),
)


class ManifestWriteError(RuntimeError):
    """Raised when the private manifest cannot be replaced safely."""


@dataclass(frozen=True, slots=True)
class DuplicatePdf:
    duplicate: Path
    canonical: Path
    sha256: str


Analyzer = Callable[[Path, Path], dict[str, Any]]


def scan_pdf_files(root: Path) -> list[Path]:
    root = root.resolve()
    if not root.is_dir():
        return []
    return sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.casefold() == ".pdf"
        ),
        key=lambda path: path.relative_to(root).as_posix().casefold(),
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_manifest(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {field: row.get(field, "") for field in MANIFEST_FIELDS}
            for row in csv.DictReader(handle)
        ]


def manifest_indexes(
    rows: Sequence[Mapping[str, str]],
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    by_sha: dict[str, dict[str, str]] = {}
    by_path: dict[str, dict[str, str]] = {}
    for source_row in rows:
        row = {field: str(source_row.get(field, "")) for field in MANIFEST_FIELDS}
        if row["sha256"]:
            by_sha.setdefault(row["sha256"], row)
        if row["relative_path"]:
            by_path[row["relative_path"]] = row
    return by_sha, by_path


def discover_unique_pdfs(
    root: Path,
    manifest_rows: Sequence[Mapping[str, str]] = (),
) -> tuple[list[Path], list[DuplicatePdf], dict[Path, tuple[str, int]]]:
    """Return one canonical path per SHA and report duplicates non-destructively."""

    root = root.resolve()
    _by_sha, by_path = manifest_indexes(manifest_rows)
    identities: dict[Path, tuple[str, int]] = {}
    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in scan_pdf_files(root):
        identity = (sha256_file(path), path.stat().st_size)
        identities[path] = identity
        grouped[identity[0]].append(path)

    canonical: list[Path] = []
    duplicates: list[DuplicatePdf] = []
    for digest, paths in grouped.items():
        ordered = sorted(paths, key=lambda item: item.relative_to(root).as_posix().casefold())
        existing = [
            path for path in ordered if path.relative_to(root).as_posix() in by_path
        ]
        non_incoming = [
            path
            for path in ordered
            if not path.relative_to(root).as_posix().startswith("_incoming/")
        ]
        chosen = (existing or non_incoming or ordered)[0]
        canonical.append(chosen)
        duplicates.extend(
            DuplicatePdf(path, chosen, digest) for path in ordered if path != chosen
        )
    canonical.sort(key=lambda item: item.relative_to(root).as_posix().casefold())
    duplicates.sort(key=lambda item: item.duplicate.relative_to(root).as_posix().casefold())
    return canonical, duplicates, identities


def atomic_write_manifest(rows: Sequence[Mapping[str, str]], manifest_path: Path) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8-sig",
            newline="",
            delete=False,
            dir=manifest_path.parent,
            prefix=f".{manifest_path.name}.",
            suffix=".tmp",
        ) as handle:
            temporary = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
            writer.writeheader()
            writer.writerows(
                {field: str(row.get(field, "")) for field in MANIFEST_FIELDS}
                for row in rows
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, manifest_path)
    except (PermissionError, OSError) as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise ManifestWriteError(
            "Cannot update pdf_manifest.csv because it may be open in another "
            "application. Close Excel and retry. No partial manifest was written."
        ) from exc


def _normalized_supplier(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return (
        text.replace("''", '"')
        .replace("``", '"')
        .replace("׳", "'")
        .replace("’", "'")
        .replace("״", '"')
        .replace("“", '"')
        .replace("”", '"')
    )


def _normalized_date(value: Any) -> str | None:
    text = str(value or "").strip().replace(".", "/")
    for pattern in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(text, pattern).strftime("%d/%m/%Y")
        except ValueError:
            pass
    return text or None


def _normalized_amount(value: Any) -> Decimal | None:
    text = str(value if value is not None else "").strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def panda_field_text(parser_key: str, value: Any) -> str:
    if value is None:
        return ""
    if parser_key == "amount":
        amount = _normalized_amount(value)
        if amount is not None:
            return f"{amount:.2f}"
    return str(value)


def correctness_for_record(
    record: Mapping[str, Any], manifest_row: Mapping[str, str] | None,
) -> dict[str, bool | None]:
    if (
        not manifest_row
        or str(manifest_row.get("reviewed", "false")).casefold() != "true"
        or not isinstance(record.get("parser_result"), Mapping)
    ):
        return {
            "supplier_correct": None,
            "invoice_number_correct": None,
            "invoice_date_correct": None,
            "amount_correct": None,
            "fully_correct": None,
        }
    parser = record.get("parser_result") or {}
    comparisons = {
        "supplier_correct": _normalized_supplier(parser.get("business_name"))
        == _normalized_supplier(manifest_row.get("expected_supplier")),
        "invoice_number_correct": str(parser.get("invoice_number") or "").strip()
        == str(manifest_row.get("expected_invoice_number") or "").strip(),
        "invoice_date_correct": _normalized_date(parser.get("invoice_date"))
        == _normalized_date(manifest_row.get("expected_invoice_date")),
        "amount_correct": _normalized_amount(parser.get("amount"))
        == _normalized_amount(manifest_row.get("expected_amount")),
    }
    comparisons["fully_correct"] = all(comparisons.values())
    return comparisons


def attach_manifest_state(
    records: Sequence[dict[str, Any]], manifest_rows: Sequence[Mapping[str, str]],
) -> None:
    by_sha, by_path = manifest_indexes(manifest_rows)
    for record in records:
        row = by_sha.get(str(record.get("sha256") or "")) or by_path.get(
            str(record.get("relative_path") or "")
        )
        reviewed = bool(row and str(row.get("reviewed", "false")).casefold() == "true")
        record["reviewed"] = reviewed
        for field in (
            "expected_supplier",
            "expected_invoice_number",
            "expected_invoice_date",
            "expected_amount",
        ):
            record[field] = str((row or {}).get(field, ""))
        record.update(correctness_for_record(record, row))


def verified_accuracy(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    reviewed = [record for record in records if record.get("reviewed") is True]
    fields = (
        "supplier_correct",
        "invoice_date_correct",
        "invoice_number_correct",
        "amount_correct",
    )
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in reviewed:
        grouped[str((record.get("source_detection") or {}).get("source_system", "Unknown"))].append(record)
    return {
        "reviewed": len(reviewed),
        "total": len(records),
        "fields": {
            field: {
                "correct": sum(record.get(field) is True for record in reviewed),
                "total": len(reviewed),
            }
            for field in fields
        },
        "fully_correct": sum(record.get("fully_correct") is True for record in reviewed),
        "by_source": {
            source: {
                "reviewed": len(items),
                "fully_correct": sum(item.get("fully_correct") is True for item in items),
            }
            for source, items in sorted(grouped.items())
        },
    }


def ground_truth_mismatches(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    field_map = (
        ("supplier_correct", "Supplier", "business_name", "expected_supplier"),
        ("invoice_number_correct", "Invoice number", "invoice_number", "expected_invoice_number"),
        ("invoice_date_correct", "Date", "invoice_date", "expected_invoice_date"),
        ("amount_correct", "Amount", "amount", "expected_amount"),
    )
    mismatches: list[dict[str, Any]] = []
    for record in records:
        if record.get("reviewed") is not True:
            continue
        fields = []
        parser = record.get("parser_result") or {}
        for correctness, label, parser_key, expected_key in field_map:
            if record.get(correctness) is False:
                fields.append(
                    {
                        "field": label,
                        "panda": parser.get(parser_key),
                        "expected": record.get(expected_key, ""),
                    }
                )
        if fields:
            mismatches.append({"relative_path": record.get("relative_path"), "fields": fields})
    return mismatches


def review_priority(record: Mapping[str, Any]) -> tuple[Any, ...]:
    relative = str(record.get("relative_path") or "")
    status_order = {"failed": 0, "needs_review": 1, "processed": 2, "skipped": 3}
    source = str((record.get("source_detection") or {}).get("source_system", "Unknown"))
    native = bool((record.get("extraction_metrics") or {}).get("native_text"))
    return (
        0 if relative.startswith("_incoming/") else 1,
        0 if native else 1,
        status_order.get(str(record.get("status")), 4),
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


def replace_manifest_row(
    rows: Sequence[Mapping[str, str]], updated: Mapping[str, str],
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    replaced = False
    for row in rows:
        same = bool(updated.get("sha256")) and row.get("sha256") == updated.get("sha256")
        same = same or row.get("relative_path") == updated.get("relative_path")
        if same:
            result.append({field: str(updated.get(field, "")) for field in MANIFEST_FIELDS})
            replaced = True
        else:
            result.append({field: str(row.get(field, "")) for field in MANIFEST_FIELDS})
    if not replaced:
        result.append({field: str(updated.get(field, "")) for field in MANIFEST_FIELDS})
    return sorted(result, key=lambda item: item["relative_path"].casefold())


def _processing_status(document_type: str | None, parsed: Mapping[str, Any] | None) -> str:
    from app.parsers.invoice_parser import EXCLUDED_DOCUMENT_TYPES
    from app.services.processing_service import _confidence

    if document_type in EXCLUDED_DOCUMENT_TYPES:
        return "skipped"
    supplier_validation = (parsed or {}).get("supplier_validation", {})
    rejected = (
        not supplier_validation.get("is_valid", True)
        and not supplier_validation.get("fallback_used", False)
    )
    if rejected:
        return "needs_review"
    return "processed" if _confidence(parsed) >= 0.75 else "needs_review"


def analyze_current_pdf(path: Path, root: Path) -> dict[str, Any]:
    """Run only Panda's current production extraction/parser for one local PDF."""

    import app.parsers.supplier_validator as supplier_validator
    from app.parsers.invoice_parser import classify_document_type, parse_invoice_text
    from app.parsers.pdf_layout import apply_positional_supplier_override
    from app.parsers.pdf_parser import extract_text_from_pdf
    from app.services.correction_map_service import load_correction_map
    from app.services.processing_service import _confidence

    relative = path.resolve().relative_to(root.resolve()).as_posix()
    record: dict[str, Any] = {
        "filename": path.name,
        "relative_path": relative,
        "sha256": sha256_file(path),
        "file_size": path.stat().st_size,
        "source_detection": {
            "source_system": "Unknown",
            "source_confidence": "unknown",
            "source_evidence": [],
        },
        "extraction_metrics": {
            "pages": 0,
            "raw_chars": 0,
            "meaningful_chars": 0,
            "native_text": False,
        },
        "parser_result": None,
        "supplier_validation": None,
        "confidence": 0.0,
        "status": "failed",
        "warnings": [],
        "errors": {"extraction": None, "parser": None},
    }
    try:
        text = extract_text_from_pdf(str(path))
    except Exception as exc:
        record["errors"]["extraction"] = f"{type(exc).__name__}: {exc}"
        return record
    meaningful = sum(character.isalnum() for character in text)
    record["extraction_metrics"].update(
        {
            "raw_chars": len(text),
            "meaningful_chars": meaningful,
            "native_text": meaningful >= 20,
        }
    )
    try:
        # Match the diagnostic pipeline without supplier-validator create-on-missing
        # writes. This updates only the process-local cache.
        rules = supplier_validator._read_json(
            supplier_validator.SUPPLIER_RULES_JSON,
            supplier_validator._DEFAULT_BASE_RULES,
        )
        learned = supplier_validator._read_json(
            supplier_validator.LEARNED_RULES_JSON,
            {"version": 1, "rules": []},
        )
        rules["learned"] = learned.get("rules", [])
        supplier_validator._rules_cache = rules
        document_type = classify_document_type(text)
        parsed = parse_invoice_text(text, correction_map=load_correction_map())
        if parsed:
            apply_positional_supplier_override(parsed, text, pdf_path=path)
        record["parser_result"] = deepcopy(parsed) or {"document_type": document_type}
        record["supplier_validation"] = deepcopy((parsed or {}).get("supplier_validation"))
        record["confidence"] = _confidence(parsed)
        record["status"] = _processing_status(document_type, parsed)
    except Exception as exc:
        record["errors"]["parser"] = f"{type(exc).__name__}: {exc}"
    return record


class PdfCorpusService:
    """Session-oriented local corpus index with on-demand current parsing."""

    def __init__(
        self,
        corpus_root: Path,
        *,
        benchmark_path: Path | None = None,
        analyzer: Analyzer = analyze_current_pdf,
    ) -> None:
        self.root = corpus_root.resolve()
        self.manifest_path = self.root / "pdf_manifest.csv"
        if benchmark_path is None:
            try:
                repository_root = self.root.parents[2]
            except IndexError:
                repository_root = self.root
            benchmark_path = repository_root / "artifacts" / "pdf_benchmark.json"
        self.benchmark_path = benchmark_path.resolve()
        self._analyzer = analyzer
        self._manifest_rows: list[dict[str, str]] = []
        self._records: list[dict[str, Any]] = []
        self._paths_by_sha: dict[str, Path] = {}
        self._cache: dict[tuple[str, int, int], dict[str, Any]] = {}
        self.duplicates: tuple[DuplicatePdf, ...] = ()

    @property
    def records(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._records)

    def reload(self) -> tuple[dict[str, Any], ...]:
        self._manifest_rows = read_manifest(self.manifest_path)
        paths, duplicates, identities = discover_unique_pdfs(self.root, self._manifest_rows)
        self.duplicates = tuple(duplicates)
        snapshot_by_sha = self._load_benchmark_snapshot()
        manifest_by_sha, manifest_by_path = manifest_indexes(self._manifest_rows)
        records: list[dict[str, Any]] = []
        paths_by_sha: dict[str, Path] = {}
        for path in paths:
            digest, file_size = identities[path]
            relative = path.relative_to(self.root).as_posix()
            record = deepcopy(snapshot_by_sha.get(digest) or {})
            row = manifest_by_sha.get(digest) or manifest_by_path.get(relative)
            record.update(
                {
                    "filename": path.name,
                    "relative_path": relative,
                    "sha256": digest,
                    "file_size": file_size,
                    "_absolute_path": str(path),
                }
            )
            record.setdefault("parser_result", None)
            record.setdefault("confidence", 0.0)
            record.setdefault("status", "unanalyzed")
            record.setdefault("extraction_metrics", {"native_text": None})
            record.setdefault(
                "source_detection",
                {
                    "source_system": str((row or {}).get("source_system") or "Unknown"),
                    "source_confidence": str((row or {}).get("source_confidence") or "unknown"),
                    "source_evidence": [str((row or {}).get("source_evidence") or "")],
                },
            )
            if row:
                source = record["source_detection"]
                source["source_system"] = row.get("source_system") or source.get("source_system", "Unknown")
                source["source_confidence"] = row.get("source_confidence") or source.get("source_confidence", "unknown")
            records.append(record)
            paths_by_sha[digest] = path
        attach_manifest_state(records, self._manifest_rows)
        self._records = sorted(records, key=review_priority)
        self._paths_by_sha = paths_by_sha
        return self.records

    def record_by_sha(self, sha256: str) -> dict[str, Any] | None:
        return next((record for record in self._records if record.get("sha256") == sha256), None)

    def analyze(self, sha256: str, *, force: bool = False) -> dict[str, Any]:
        path = self._paths_by_sha.get(sha256)
        if path is None or not path.is_file():
            raise FileNotFoundError(f"PDF corpus file is unavailable for SHA-256 {sha256}")
        stat = path.stat()
        key = (sha256, stat.st_size, stat.st_mtime_ns)
        if force:
            self._cache.pop(key, None)
        analyzed = deepcopy(self._cache.get(key) or self._analyzer(path, self.root))
        self._cache[key] = deepcopy(analyzed)
        current = self.record_by_sha(sha256) or {}
        for field in ("source_detection", "metadata", "pdf_engine", "rtl_diagnostics"):
            if field not in analyzed and field in current:
                analyzed[field] = deepcopy(current[field])
        analyzed.update(
            {
                "filename": path.name,
                "relative_path": path.relative_to(self.root).as_posix(),
                "sha256": sha256,
                "file_size": stat.st_size,
                "_absolute_path": str(path),
            }
        )
        attach_manifest_state([analyzed], self._manifest_rows)
        self._replace_record(analyzed)
        return analyzed

    def everything_correct(self, sha256: str) -> dict[str, Any]:
        record = self.analyze(sha256)
        parser = record.get("parser_result") or {}
        values = {
            expected: panda_field_text(parser_key, parser.get(parser_key))
            for expected, _label, parser_key in REVIEW_FIELDS
        }
        return self.save_review(sha256, values)

    def save_review(
        self, sha256: str, expected_values: Mapping[str, Any]
    ) -> dict[str, Any]:
        record = self.record_by_sha(sha256)
        if record is None:
            raise KeyError(f"Unknown corpus SHA-256: {sha256}")
        latest = read_manifest(self.manifest_path)
        by_sha, by_path = manifest_indexes(latest)
        row = dict(
            by_sha.get(sha256)
            or by_path.get(str(record.get("relative_path") or ""))
            or self._manifest_row(record)
        )
        row.update(
            {
                "filename": str(record.get("filename") or ""),
                "relative_path": str(record.get("relative_path") or ""),
                "sha256": sha256,
                "file_size": str(record.get("file_size") or 0),
                "reviewed": "true",
            }
        )
        for expected, _label, _parser_key in REVIEW_FIELDS:
            row[expected] = str(expected_values.get(expected, "")).strip()
        rows = replace_manifest_row(latest, row)
        atomic_write_manifest(rows, self.manifest_path)
        self._manifest_rows = rows
        attach_manifest_state([record], rows)
        self._replace_record(record)
        return record

    def filtered_records(
        self,
        *,
        review_state: str = "all",
        status: str = "all",
        source: str = "all",
        native: str = "all",
        low_confidence: bool = False,
        include_skipped: bool = True,
        sort_by: str = "priority",
    ) -> list[dict[str, Any]]:
        records = list(self._records)
        if review_state == "unreviewed":
            records = [record for record in records if record.get("reviewed") is not True]
        elif review_state == "reviewed":
            records = [record for record in records if record.get("reviewed") is True]
        elif review_state == "mismatches":
            records = [record for record in records if record.get("fully_correct") is False]
        if status != "all":
            records = [record for record in records if record.get("status") == status]
        if source != "all":
            records = [
                record
                for record in records
                if (record.get("source_detection") or {}).get("source_system") == source
            ]
        if native in {"native", "non_native"}:
            if native == "native":
                # Unanalyzed incoming files remain discoverable until their first
                # on-demand parse establishes whether native text exists.
                records = [
                    record
                    for record in records
                    if (record.get("extraction_metrics") or {}).get("native_text") is not False
                ]
            else:
                records = [
                    record
                    for record in records
                    if (record.get("extraction_metrics") or {}).get("native_text") is False
                ]
        if low_confidence:
            records = [record for record in records if float(record.get("confidence") or 0) < 0.75]
        if not include_skipped:
            records = [record for record in records if record.get("status") != "skipped"]
        sorters = {
            "priority": review_priority,
            "confidence": lambda record: (float(record.get("confidence") or 0), review_priority(record)),
            "filename": lambda record: str(record.get("filename") or "").casefold(),
            "source": lambda record: (
                str((record.get("source_detection") or {}).get("source_system") or "Unknown").casefold(),
                str(record.get("filename") or "").casefold(),
            ),
            "status": lambda record: (
                str(record.get("status") or ""),
                str(record.get("filename") or "").casefold(),
            ),
        }
        return sorted(records, key=sorters.get(sort_by, review_priority))

    def accuracy(self) -> dict[str, Any]:
        return verified_accuracy(self._records)

    def _load_benchmark_snapshot(self) -> dict[str, dict[str, Any]]:
        if not self.benchmark_path.is_file():
            return {}
        try:
            payload = json.loads(self.benchmark_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}
        documents = payload.get("documents", []) if isinstance(payload, dict) else []
        return {
            str(record.get("sha256")): record
            for record in documents
            if isinstance(record, dict) and record.get("sha256")
        }

    def _manifest_row(self, record: Mapping[str, Any]) -> dict[str, str]:
        source = record.get("source_detection") or {}
        metadata = record.get("metadata") or {}
        evidence = source.get("source_evidence") or []
        if isinstance(evidence, str):
            evidence = [evidence] if evidence else []
        return {
            "filename": str(record.get("filename") or ""),
            "relative_path": str(record.get("relative_path") or ""),
            "sha256": str(record.get("sha256") or ""),
            "file_size": str(record.get("file_size") or 0),
            "source_system": str(source.get("source_system") or "Unknown"),
            "source_confidence": str(source.get("source_confidence") or "unknown"),
            "source_evidence": " | ".join(evidence),
            "creator": str(metadata.get("Creator") or ""),
            "producer": str(metadata.get("Producer") or ""),
            "pdf_engine": str(record.get("pdf_engine") or "Unknown"),
            "rtl_pattern": str((record.get("rtl_diagnostics") or {}).get("pattern") or "unknown"),
            "reviewed": "false",
            "expected_supplier": "",
            "expected_invoice_number": "",
            "expected_invoice_date": "",
            "expected_amount": "",
            "notes": "",
        }

    def _replace_record(self, updated: dict[str, Any]) -> None:
        self._records = [
            updated if record.get("sha256") == updated.get("sha256") else record
            for record in self._records
        ]
