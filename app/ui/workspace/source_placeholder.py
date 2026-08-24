"""Read-only source slot used when the optional native preview is unavailable."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.ui.theme.typography import TypographyRole, apply_typography
from app.ui.workspace.presentation import WorkspaceDocumentPresentation


class SourcePlaceholder(QWidget):
    """Small H1 seam; H2's native SourcePreview is selected when importable."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message = QLabel("תצוגת המקור אינה זמינה")
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        apply_typography(self.message, TypographyRole.SECTION_TITLE)
        root.addWidget(self.message)

    def load_presentation(self, _presentation: WorkspaceDocumentPresentation) -> None:
        self.message.setText("תצוגת המקור אינה זמינה")

    def release_source(self) -> None:
        pass
