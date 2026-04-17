"""
Tests for app.ui.file_opener.open_local_file.

We mock os.startfile / subprocess.Popen and QMessageBox so no real files,
no PDF viewer, and no GUI are needed.

Run from the project root:
    pytest tests/test_file_opener.py -v
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _call_open(path: str, parent=None):
    """Import fresh and call open_local_file, returning the bool result."""
    from app.ui.file_opener import open_local_file
    return open_local_file(path, parent=parent)


# ── Empty / missing path ───────────────────────────────────────────────────────

class TestEmptyPath:

    def test_empty_string_returns_false(self, tmp_path):
        assert _call_open("") is False

    def test_whitespace_only_returns_false(self):
        assert _call_open("   ") is False

    def test_empty_path_shows_warning(self):
        mock_parent = MagicMock()
        with patch("app.ui.file_opener.QMessageBox") as mock_mb:
            _call_open("", parent=mock_parent)
        mock_mb.warning.assert_called_once()
        args = mock_mb.warning.call_args[0]
        assert args[1] == "קובץ לא זמין"

    def test_empty_path_does_not_call_startfile(self):
        with patch("os.startfile") as mock_sf:
            _call_open("")
        mock_sf.assert_not_called()


# ── File not found ─────────────────────────────────────────────────────────────

class TestFileNotFound:

    def test_nonexistent_path_returns_false(self, tmp_path):
        missing = str(tmp_path / "does_not_exist.pdf")
        assert _call_open(missing) is False

    def test_missing_file_shows_warning_with_path(self, tmp_path):
        missing = str(tmp_path / "ghost.pdf")
        mock_parent = MagicMock()
        with patch("app.ui.file_opener.QMessageBox") as mock_mb:
            _call_open(missing, parent=mock_parent)
        mock_mb.warning.assert_called_once()
        # Body should contain the path so the user knows what was expected.
        body = mock_mb.warning.call_args[0][2]
        assert missing in body

    def test_missing_file_does_not_call_startfile(self, tmp_path):
        missing = str(tmp_path / "ghost.pdf")
        with patch("os.startfile") as mock_sf:
            _call_open(missing)
        mock_sf.assert_not_called()


# ── Successful open (Windows) ─────────────────────────────────────────────────

class TestSuccessfulOpenWindows:

    def test_existing_pdf_calls_startfile(self, tmp_path):
        pdf = tmp_path / "invoice.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        with patch.object(sys, "platform", "win32"), \
             patch("os.startfile") as mock_sf:
            result = _call_open(str(pdf))
        assert result is True
        mock_sf.assert_called_once_with(str(pdf))

    def test_no_messagebox_on_success(self, tmp_path):
        pdf = tmp_path / "invoice.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        with patch.object(sys, "platform", "win32"), \
             patch("os.startfile"), \
             patch("app.ui.file_opener.QMessageBox") as mock_mb:
            _call_open(str(pdf))
        mock_mb.warning.assert_not_called()
        mock_mb.critical.assert_not_called()


# ── Successful open (macOS / Linux) ───────────────────────────────────────────

class TestSuccessfulOpenUnix:

    def test_existing_pdf_calls_popen_darwin(self, tmp_path):
        pdf = tmp_path / "invoice.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        with patch.object(sys, "platform", "darwin"), \
             patch("subprocess.Popen") as mock_popen:
            result = _call_open(str(pdf))
        assert result is True
        mock_popen.assert_called_once_with(["open", str(pdf)])

    def test_existing_pdf_calls_popen_linux(self, tmp_path):
        pdf = tmp_path / "invoice.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        with patch.object(sys, "platform", "linux"), \
             patch("subprocess.Popen") as mock_popen:
            result = _call_open(str(pdf))
        assert result is True
        mock_popen.assert_called_once_with(["xdg-open", str(pdf)])


# ── OS call raises exception ───────────────────────────────────────────────────

class TestOsCallException:

    def test_startfile_exception_returns_false(self, tmp_path):
        pdf = tmp_path / "invoice.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        with patch.object(sys, "platform", "win32"), \
             patch("os.startfile", side_effect=OSError("No app associated")):
            result = _call_open(str(pdf))
        assert result is False

    def test_startfile_exception_shows_critical(self, tmp_path):
        pdf = tmp_path / "invoice.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        mock_parent = MagicMock()
        with patch.object(sys, "platform", "win32"), \
             patch("os.startfile", side_effect=OSError("No app associated")), \
             patch("app.ui.file_opener.QMessageBox") as mock_mb:
            _call_open(str(pdf), parent=mock_parent)
        mock_mb.critical.assert_called_once()

    def test_startfile_exception_body_contains_path(self, tmp_path):
        pdf = tmp_path / "invoice.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        mock_parent = MagicMock()
        with patch.object(sys, "platform", "win32"), \
             patch("os.startfile", side_effect=OSError("boom")), \
             patch("app.ui.file_opener.QMessageBox") as mock_mb:
            _call_open(str(pdf), parent=mock_parent)
        body = mock_mb.critical.call_args[0][2]
        assert str(pdf) in body
        assert "boom" in body


# ── No-extension filename (real-world edge case) ───────────────────────────────

class TestNoExtensionFile:
    """
    Some Drive files are uploaded without a .pdf extension
    (e.g. "INV 13305595_BOX-JANUARYpdf").
    open_local_file should still attempt to open them and
    return True (Windows may or may not find a viewer, but that's
    the user's environment — the code has done its job).
    """

    def test_extensionless_file_still_attempted(self, tmp_path):
        oddfile = tmp_path / "INV 13305595_BOX-JANUARYpdf"
        oddfile.write_bytes(b"%PDF-1.4")
        with patch.object(sys, "platform", "win32"), \
             patch("os.startfile") as mock_sf:
            result = _call_open(str(oddfile))
        assert result is True
        mock_sf.assert_called_once()

    def test_no_extension_does_not_block_open(self, tmp_path):
        oddfile = tmp_path / "document_without_ext"
        oddfile.write_bytes(b"%PDF-1.4")
        with patch.object(sys, "platform", "win32"), \
             patch("os.startfile"):
            # Should succeed — existence check passes, open attempted
            result = _call_open(str(oddfile))
        assert result is True


# ── Parent=None does not crash ─────────────────────────────────────────────────

class TestNoParent:
    """Passing parent=None must not crash — just skip the message box."""

    def test_no_parent_missing_file_no_crash(self, tmp_path):
        missing = str(tmp_path / "gone.pdf")
        # Should return False without raising
        result = _call_open(missing, parent=None)
        assert result is False

    def test_no_parent_empty_path_no_crash(self):
        result = _call_open("", parent=None)
        assert result is False
