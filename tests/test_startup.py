"""Tests for safe startup failure when document storage cannot load."""

from pathlib import Path
from unittest.mock import patch

import run
from app.services.document_store import DocumentStoreLoadError


def test_startup_shows_critical_error_and_stops_before_main_window() -> None:
    load_error = DocumentStoreLoadError(
        Path("data/documents.json"),
        "malformed_json",
        "malformed JSON",
    )

    with (
        patch("run.ensure_dirs"),
        patch("run.QApplication") as application_class,
        patch("run.DocumentStore", side_effect=load_error),
        patch("run.MainWindow") as main_window,
        patch("run.QMessageBox.critical") as critical,
    ):
        result = run.main()

    assert result == 1
    main_window.assert_not_called()
    application_class.return_value.exec.assert_not_called()
    critical.assert_called_once()
    message = critical.call_args.args[2]
    assert "לא ניתן לטעון בבטחה" in message
    assert "לאובדן נתונים" in message
    assert "המאגר לא שונה" in message
