# Local digital-PDF corpus workflow

The real invoice corpus is private, local development data. PDF files, the real
`pdf_manifest.csv`, and generated benchmark reports are ignored by Git. Never
upload them or add them with a forced Git command.

## Intake and analysis

1. Copy new digital PDFs into `tests/fixtures/pdf/_incoming/`.
2. Inspect the intake snapshot:

   ```powershell
   python -B scripts/diagnose_pdf_batch.py "tests/fixtures/pdf" --new-only
   ```

   `--new-only` includes PDFs absent from the manifest at command start plus
   unreviewed PDFs still in `_incoming`. Exact duplicate bytes are reported by
   SHA-256 and are not registered as a second corpus identity.

3. Preview source-system organization without changing files:

   ```powershell
   python -B scripts/diagnose_pdf_batch.py "tests/fixtures/pdf" --organize --dry-run
   ```

4. Apply a validated organization plan:

   ```powershell
   python -B scripts/diagnose_pdf_batch.py "tests/fixtures/pdf" --organize
   ```

   High-confidence sources move to their source slug. Medium, low, or
   conflicting evidence moves to `_review`; unknown sources move to `_unknown`.

## Human ground-truth review

Run the unreviewed queue:

```powershell
python -B scripts/review_pdf_corpus.py "tests/fixtures/pdf"
```

Options:

```powershell
python -B scripts/review_pdf_corpus.py "tests/fixtures/pdf" --new-only
python -B scripts/review_pdf_corpus.py "tests/fixtures/pdf" --all
python -B scripts/review_pdf_corpus.py "tests/fixtures/pdf" --file "relative/path.pdf"
```

Pressing Enter for a field is an explicit human confirmation of Panda's current
value. Type a corrected value when Panda is wrong, or `-` for an intentional
blank. The manifest is marked `reviewed=true` only after the final confirmation.

## Full benchmark

```powershell
python -B scripts/diagnose_pdf_batch.py "tests/fixtures/pdf"
```

The operational section measures parser status and field presence for every
PDF. `processed` means the current workflow accepted the parser output; it does
not prove accuracy. The verified section includes only human-reviewed rows and
compares Panda output with explicit `expected_*` ground truth. A document is
`fully correct` only when supplier, invoice number, date, and amount all match.

Use `scripts/diagnose_pdf.py --words "path/to/file.pdf"` for deep local analysis
of one suspicious PDF. None of these tools make network or OCR calls.
