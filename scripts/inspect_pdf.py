"""Manually inspect Panda's extracted text for a caller-supplied PDF.

This utility intentionally lives outside the pytest suite. It performs local
file I/O only when explicitly invoked with a path.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Permit direct execution from the repository root as well as module execution.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.parsers.pdf_parser import extract_text_from_pdf


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="PDF file to inspect")
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Maximum extracted characters to print (default: 1000)",
    )
    args = parser.parse_args()

    text = extract_text_from_pdf(str(args.pdf))
    print(text[: max(args.limit, 0)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
