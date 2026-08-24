"""Read-only Document Workspace identity and navigation header."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.ui.components import ButtonVariant, PandaButton, StatusBadge
from app.ui.theme.direction import TextKind, apply_text_direction, isolate_ltr
from app.ui.theme.tokens import SPACING
from app.ui.theme.typography import TypographyRole, apply_typography
from app.ui.workspace.presentation import WorkspaceDocumentPresentation


class WorkspaceHeader(QFrame):
    backRequested = Signal()
    previousRequested = Signal()
    nextRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("pandaComponent", "workspaceHeader")
        self.setFixedHeight(58)
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 0, 16, 0)
        root.setSpacing(SPACING.standard)
        self.back_button = PandaButton("חזרה לתור", variant=ButtonVariant.SECONDARY)
        self.back_button.clicked.connect(self.backRequested)
        root.addWidget(self.back_button)
        identity = QWidget()
        identity_layout = QVBoxLayout(identity)
        identity_layout.setContentsMargins(0, 5, 0, 5)
        identity_layout.setSpacing(1)
        self.file_name = QLabel("—")
        apply_typography(self.file_name, TypographyRole.LABEL)
        apply_text_direction(self.file_name, TextKind.FILENAME)
        self.context = QLabel()
        self.context.setProperty("pandaRole", "muted")
        apply_typography(self.context, TypographyRole.HELPER)
        identity_layout.addWidget(self.file_name)
        identity_layout.addWidget(self.context)
        root.addWidget(identity, 1)
        self.status_badge = StatusBadge("new")
        root.addWidget(self.status_badge)
        self.confidence = QLabel("—")
        self.confidence.setProperty("pandaComponent", "workspaceConfidence")
        apply_typography(self.confidence, TypographyRole.TECHNICAL)
        apply_text_direction(self.confidence, TextKind.PERCENTAGE)
        root.addWidget(self.confidence)
        self.previous_button = PandaButton("הקודם", variant=ButtonVariant.GHOST)
        self.previous_button.clicked.connect(self.previousRequested)
        self.position_label = QLabel("0 / 0")
        apply_typography(self.position_label, TypographyRole.TECHNICAL)
        apply_text_direction(self.position_label, TextKind.TECHNICAL)
        self.next_button = PandaButton("הבא", variant=ButtonVariant.GHOST)
        self.next_button.clicked.connect(self.nextRequested)
        root.addWidget(self.previous_button)
        root.addWidget(self.position_label)
        root.addWidget(self.next_button)

    def set_presentation(
        self,
        presentation: WorkspaceDocumentPresentation,
        *,
        origin_label: str,
        position: int,
        total: int,
        can_previous: bool,
        can_next: bool,
    ) -> None:
        self.file_name.setText(presentation.file_name or "מסמך ללא שם")
        self.file_name.setToolTip(presentation.file_name)
        folder = presentation.folder_path or "ללא תיקיית מקור"
        self.context.setText(f"{origin_label} · {folder}")
        self.status_badge.set_status(presentation.status)
        self.confidence.setText(
            f"{int(presentation.confidence * 100)}%"
            if presentation.confidence is not None
            else "—"
        )
        self.confidence.setAccessibleName(
            f"ביטחון {self.confidence.text()}"
        )
        self.position_label.setText(isolate_ltr(f"{position} / {total}"))
        self.previous_button.setEnabled(can_previous)
        self.next_button.setEnabled(can_next)

