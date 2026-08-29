"""Deterministic local performance benchmark for unique private-PDF identities.

This is diagnostic-only instrumentation.  It runs the same extraction, text
parser, and optional positional supplier path used by production while counting
PDF opens and positional work.  Private document data is never written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import statistics
import sys
import time
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Sequence

import pdfplumber.page


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app.parsers.invoice_parser as invoice_parser
import app.parsers.pdf_layout as pdf_layout
import app.parsers.pdf_parser as pdf_parser
import app.parsers.supplier_validator as supplier_validator
from app.services.correction_map_service import load_correction_map


def _unique_pdfs(root: Path) -> list[Path]:
    by_sha: dict[str, Path] = {}
    for path in sorted(root.rglob("*.pdf")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        by_sha.setdefault(digest, path)
    return list(by_sha.values())


def _timed_call(counters: dict[str, float], key: str, call: Callable[..., Any]):
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return call(*args, **kwargs)
        finally:
            counters[key] += time.perf_counter() - started

    return wrapper


def _run_once(paths: Sequence[Path], correction_map: dict[str, Any]) -> dict[str, Any]:
    counts: dict[str, int] = defaultdict(int)
    timings: dict[str, float] = defaultdict(float)

    original_open = pdf_parser.pdfplumber.open
    original_extract_words = pdfplumber.page.Page.extract_words
    original_extract_word_pages = pdf_layout.extract_word_pages
    original_analyze_page = pdf_layout.analyze_page_header
    original_best_proposal = pdf_layout.best_supplier_proposal
    original_validate = pdf_layout.validate_supplier

    open_phase = {"value": "other"}

    def measured_open(*args: Any, **kwargs: Any) -> Any:
        phase = open_phase["value"]
        counts[f"{phase}_pdf_opens"] += 1
        return _timed_call(timings, f"{phase}_open_seconds", original_open)(
            *args, **kwargs
        )

    def extract_words(*args: Any, **kwargs: Any) -> Any:
        counts["extract_words_calls"] += 1
        return _timed_call(timings, "extract_words_seconds", original_extract_words)(
            *args, **kwargs
        )

    def extract_word_pages(*args: Any, **kwargs: Any) -> Any:
        previous = open_phase["value"]
        open_phase["value"] = "geometry"
        try:
            return _timed_call(
                timings, "geometry_pass_seconds", original_extract_word_pages
            )(*args, **kwargs)
        finally:
            open_phase["value"] = previous

    def analyze_page(*args: Any, **kwargs: Any) -> Any:
        return _timed_call(timings, "layout_analysis_seconds", original_analyze_page)(
            *args, **kwargs
        )

    def best_proposal(*args: Any, **kwargs: Any) -> Any:
        result = original_best_proposal(*args, **kwargs)
        if result is not None:
            counts["proposals"] += 1
        return result

    def validate(*args: Any, **kwargs: Any) -> Any:
        counts["positional_validator_calls"] += 1
        return _timed_call(timings, "positional_validator_seconds", original_validate)(
            *args, **kwargs
        )

    pdf_parser.pdfplumber.open = measured_open
    pdfplumber.page.Page.extract_words = extract_words
    pdf_layout.extract_word_pages = extract_word_pages
    pdf_layout.analyze_page_header = analyze_page
    pdf_layout.best_supplier_proposal = best_proposal
    pdf_layout.validate_supplier = validate

    started_total = time.perf_counter()
    try:
        for path in paths:
            started = time.perf_counter()
            open_phase["value"] = "native"
            try:
                text = pdf_parser.extract_text_from_pdf(path)
            finally:
                open_phase["value"] = "other"
            timings["native_extraction_seconds"] += time.perf_counter() - started

            started = time.perf_counter()
            parsed = invoice_parser.parse_invoice_text(
                text,
                correction_map=correction_map,
            )
            timings["text_parser_seconds"] += time.perf_counter() - started
            if not parsed:
                counts["not_parsed_or_policy_skipped"] += 1
                continue
            counts["parsed_documents"] += 1
            if pdf_layout.has_required_layout_signals(text):
                counts["semantic_preflight_passes"] += 1
            if pdf_layout.has_positional_supplier_ambiguity(
                text,
                parsed.get("business_name"),
            ):
                counts["ambiguity_preflight_passes"] += 1

            started = time.perf_counter()
            resolution = pdf_layout.apply_positional_supplier_override(
                parsed,
                text,
                pdf_path=path,
            )
            timings["positional_apply_seconds"] += time.perf_counter() - started
            if resolution is not None:
                counts["overrides"] += 1
    finally:
        pdf_parser.pdfplumber.open = original_open
        pdfplumber.page.Page.extract_words = original_extract_words
        pdf_layout.extract_word_pages = original_extract_word_pages
        pdf_layout.analyze_page_header = original_analyze_page
        pdf_layout.best_supplier_proposal = original_best_proposal
        pdf_layout.validate_supplier = original_validate

    timings["total_seconds"] = time.perf_counter() - started_total
    timings["geometry_residual_seconds"] = max(
        0.0,
        timings["geometry_pass_seconds"]
        - timings["extract_words_seconds"]
        - timings["layout_analysis_seconds"],
    )
    return {
        "counts": dict(sorted(counts.items())),
        "timings": {
            key: round(value, 6) for key, value in sorted(timings.items())
        },
    }


def benchmark(
    root: Path,
    *,
    repeat: int,
    force_broad_preflight: bool = False,
) -> dict[str, Any]:
    paths = _unique_pdfs(root)
    rules = deepcopy(supplier_validator._DEFAULT_BASE_RULES)
    rules["learned"] = []
    supplier_validator._rules_cache = rules
    correction_map = load_correction_map()
    original_ambiguity = pdf_layout.has_positional_supplier_ambiguity
    if force_broad_preflight:
        pdf_layout.has_positional_supplier_ambiguity = (
            lambda text, _supplier: pdf_layout.has_required_layout_signals(text)
        )
    try:
        runs = [_run_once(paths, correction_map) for _ in range(repeat)]
    finally:
        pdf_layout.has_positional_supplier_ambiguity = original_ambiguity
    totals = [run["timings"]["total_seconds"] for run in runs]
    return {
        "unique_identities": len(paths),
        "preflight_mode": "broad-baseline" if force_broad_preflight else "optimized",
        "repeat": repeat,
        "first_run_seconds": totals[0],
        "subsequent_run_seconds": totals[1:],
        "median_seconds": round(statistics.median(totals), 6),
        "runs": runs,
    }


def _parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument(
        "--force-broad-preflight",
        action="store_true",
        help="Reproduce the pre-optimization semantic-only geometry gate.",
    )
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = _parse_args(arguments)
    if args.repeat < 1:
        raise SystemExit("--repeat must be at least 1")
    logging.disable(logging.CRITICAL)
    print(
        json.dumps(
            benchmark(
                args.root.resolve(),
                repeat=args.repeat,
                force_broad_preflight=args.force_broad_preflight,
            ),
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
