"""Token-driven, opt-in stylesheet boundary for Panda 2.0 widgets."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from app.ui.theme.tokens import BORDERS, COLORS, CONTROLS, RADII
from app.ui.theme.typography import TypographyRole, apply_typography


def panda_stylesheet() -> str:
    c = COLORS
    r = RADII
    h = CONTROLS
    b = BORDERS
    return f"""
QWidget[pandaThemeRoot="true"] {{
    background: {c.application_background};
    color: {c.text_primary};
}}
QLabel[pandaRole="muted"] {{ color: {c.text_secondary}; }}
QLabel[pandaRole="helper"] {{ color: {c.text_muted}; }}
QFrame[pandaRole="surface"] {{
    background: {c.surface};
    border: {b.hairline}px solid {c.border_primary};
    border-radius: {r.panel}px;
}}
QPushButton[pandaComponent="button"] {{
    min-height: {h.button_height}px;
    padding: 0 14px;
    border: {b.hairline}px solid {c.border_control};
    border-radius: {r.control}px;
    background: {c.surface};
    color: {c.text_heading};
}}
QPushButton[pandaComponent="button"]:hover {{
    background: {c.surface_secondary};
    border-color: {c.brand};
}}
QPushButton[pandaComponent="button"]:pressed {{ background: {c.border_secondary}; }}
QPushButton[pandaComponent="button"]:focus {{
    border: {b.focus}px solid {c.focus};
    background: {c.focus_ring};
}}
QPushButton[pandaComponent="button"][variant="primary"] {{
    background: {c.brand}; color: {c.text_on_color}; border-color: {c.brand};
}}
QPushButton[pandaComponent="button"][variant="primary"]:hover {{
    background: {c.brand_hover}; border-color: {c.brand_hover};
}}
QPushButton[pandaComponent="button"][variant="primary"]:pressed {{
    background: {c.brand_pressed}; border-color: {c.brand_pressed};
}}
QPushButton[pandaComponent="button"][variant="approval"] {{
    min-height: {h.approval_button_height}px;
    background: {c.approval}; color: {c.text_on_color}; border-color: {c.approval};
    border-radius: {r.approval}px;
}}
QPushButton[pandaComponent="button"][variant="approval"]:hover {{
    background: {c.approval_hover}; border-color: {c.approval_hover};
}}
QPushButton[pandaComponent="button"][variant="approval"]:pressed {{
    background: {c.approval_pressed}; border-color: {c.approval_pressed};
}}
QPushButton[pandaComponent="button"][variant="ghost"] {{
    background: transparent; border-color: transparent; color: {c.text_body};
}}
QPushButton[pandaComponent="button"][variant="ghost"]:hover {{
    background: {c.surface_secondary}; border-color: {c.border_secondary};
}}
QPushButton[pandaComponent="button"][variant="destructive"] {{
    background: {c.destructive}; color: {c.text_on_color}; border-color: {c.destructive};
}}
QPushButton[pandaComponent="button"][variant="destructive"]:hover {{
    background: {c.error}; border-color: {c.error};
}}
QPushButton[pandaComponent="button"][variant="destructive"]:pressed {{
    background: {c.destructive_pressed}; border-color: {c.destructive_pressed};
}}
QPushButton[pandaComponent="button"][variant="primary"]:focus,
QPushButton[pandaComponent="button"][variant="approval"]:focus,
QPushButton[pandaComponent="button"][variant="destructive"]:focus {{
    border: {b.focus}px solid {c.text_on_color};
}}
QPushButton[pandaComponent="button"]:disabled {{
    background: {c.disabled_fill}; color: {c.text_muted}; border-color: {c.disabled_border};
}}
QPushButton[pandaComponent="iconButton"] {{
    min-width: {h.icon_button}px; max-width: {h.icon_button}px;
    min-height: {h.icon_button}px; max-height: {h.icon_button}px;
    padding: 0; background: {c.surface}; color: {c.text_body};
    border: {b.hairline}px solid {c.border_control}; border-radius: {r.compact_control}px;
}}
QPushButton[pandaComponent="iconButton"]:hover {{
    background: {c.surface_secondary}; border-color: {c.brand};
}}
QPushButton[pandaComponent="iconButton"]:focus {{
    border: {b.focus}px solid {c.focus}; background: {c.focus_ring};
}}
QPushButton[pandaComponent="iconButton"][destructive="true"] {{
    color: {c.error}; border-color: {c.error_tint};
}}
QPushButton[pandaComponent="iconButton"]:disabled {{
    background: {c.surface_secondary}; border-color: {c.disabled_border};
}}
QLabel[pandaComponent="statusBadge"], QLabel[pandaComponent="auxiliaryBadge"] {{
    min-height: {h.badge_height}px; padding: 0 7px;
    border-radius: {r.chip}px; border: {b.hairline}px solid transparent;
}}
QLabel[pandaComponent="statusBadge"][status="new"] {{ color: {c.informational}; background: {c.surface_secondary}; }}
QLabel[pandaComponent="statusBadge"][status="processed"] {{ color: {c.processed}; background: {c.irrelevant_tint}; }}
QLabel[pandaComponent="statusBadge"][status="needs_review"] {{ color: {c.warning}; background: {c.warning_tint}; }}
QLabel[pandaComponent="statusBadge"][status="failed"] {{ color: {c.error}; background: {c.error_tint}; }}
QLabel[pandaComponent="statusBadge"][status="skipped"] {{ color: {c.irrelevant}; background: {c.irrelevant_tint}; }}
QLabel[pandaComponent="statusBadge"][status="approved"] {{ color: {c.approval}; background: {c.approval_tint}; }}
QLabel[pandaComponent="statusBadge"][status="exported"] {{ color: {c.exported}; background: {c.brand_tint}; }}
QLabel[pandaComponent="statusBadge"][status="confirmed_irrelevant"],
QLabel[pandaComponent="statusBadge"][status="excluded"] {{ color: {c.irrelevant}; background: {c.irrelevant_tint}; }}
QLabel[pandaComponent="auxiliaryBadge"][status="manual"] {{ color: {c.brand_hover}; background: {c.brand_tint}; }}
QLabel[pandaComponent="auxiliaryBadge"][status="duplicate"] {{ color: {c.duplicate}; background: {c.duplicate_tint}; }}
QLineEdit[pandaComponent="textField"] {{
    min-height: {h.input_height}px; padding: 0 10px;
    color: {c.text_primary}; background: {c.surface};
    border: {b.hairline}px solid {c.border_control}; border-radius: {r.control}px;
    selection-background-color: {c.brand}; selection-color: {c.text_on_color};
}}
QLineEdit[pandaComponent="textField"]:focus {{
    border: {b.focus}px solid {c.focus}; background: {c.surface};
}}
QLineEdit[pandaComponent="textField"][validationState="error"],
QLineEdit[pandaComponent="textField"][validationState="invalid"] {{
    border-color: {c.error}; background: {c.error_tint};
}}
QLineEdit[pandaComponent="textField"][validationState="missing"] {{
    border-color: {c.warning}; background: {c.warning_tint};
}}
QLineEdit[pandaComponent="textField"][validationState="low_confidence"] {{
    border-color: {c.warning_marker}; background: {c.warning_tint};
}}
QLineEdit[pandaComponent="textField"][validationState="corrected"] {{
    border-color: {c.brand}; background: {c.brand_tint};
}}
QLineEdit[pandaComponent="textField"]:read-only,
QLineEdit[pandaComponent="textField"][validationState="disabled"] {{
    color: {c.text_muted}; background: {c.surface_secondary}; border-color: {c.border_secondary};
}}
QFrame[pandaComponent="fieldEditor"] {{ background: transparent; border: none; }}
QLabel[pandaComponent="fieldStateLabel"][validationState="corrected"] {{ color: {c.brand_hover}; }}
QLabel[pandaComponent="fieldStateLabel"][validationState="low_confidence"],
QLabel[pandaComponent="fieldStateLabel"][validationState="missing"] {{ color: {c.warning}; }}
QLabel[pandaComponent="fieldStateLabel"][validationState="invalid"] {{ color: {c.error}; }}
QFrame[pandaComponent="feedback"] {{
    border: {b.hairline}px solid {c.border_secondary}; border-radius: {r.control}px;
    background: {c.surface_secondary};
}}
QFrame[pandaComponent="feedback"][variant="info"] {{ color: {c.informational}; background: {c.brand_tint}; border-color: {c.brand_border_tint}; }}
QFrame[pandaComponent="feedback"][variant="warning"] {{ color: {c.warning}; background: {c.warning_tint}; }}
QFrame[pandaComponent="feedback"][variant="error"] {{ color: {c.error}; background: {c.error_tint}; }}
QFrame[pandaComponent="feedback"][variant="success"] {{ color: {c.approval}; background: {c.approval_tint}; }}
QFrame[pandaComponent="emptyState"] {{ background: {c.surface}; border: none; }}
QLabel[pandaComponent="emptyIcon"] {{
    min-width: 52px; max-width: 52px; min-height: 52px; max-height: 52px;
    border-radius: 14px; background: {c.irrelevant_tint};
}}
QFrame[pandaComponent="confirmationPanel"] {{
    background: {c.surface}; border: {b.hairline}px solid {c.border_primary};
    border-radius: {r.card}px;
}}
QFrame[pandaComponent="consequence"][destructive="true"] {{
    background: {c.destructive_note}; border: {b.hairline}px solid {c.error_tint};
    border-radius: {r.control}px; color: {c.destructive_note_text};
}}
"""


def repolish(widget: QWidget) -> None:
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()


def set_dynamic_property(widget: QWidget, name: str, value: object) -> None:
    widget.setProperty(name, value)
    repolish(widget)


def apply_panda_theme(root: QWidget) -> None:
    """Theme one widget subtree without changing QApplication or legacy UI."""
    root.setProperty("pandaThemeRoot", True)
    apply_typography(root, TypographyRole.BODY)
    root.setStyleSheet(panda_stylesheet())
    repolish(root)
