"""Read-only Panda 2.0 Document Workspace components."""

from app.ui.workspace.field_display import FieldDisplay
from app.ui.workspace.presentation import (
    WorkspaceDocumentPresentation,
    WorkspaceField,
    WorkspaceFieldState,
    build_workspace_presentation,
)
from app.ui.workspace.queue_rail import QueueRail
from app.ui.workspace.review_panel import ReviewPanel
from app.ui.workspace.workspace_header import WorkspaceHeader
from app.ui.workspace.workspace_view import WorkspaceView

__all__ = [
    "FieldDisplay",
    "QueueRail",
    "ReviewPanel",
    "WorkspaceDocumentPresentation",
    "WorkspaceField",
    "WorkspaceFieldState",
    "WorkspaceHeader",
    "WorkspaceView",
    "build_workspace_presentation",
]
