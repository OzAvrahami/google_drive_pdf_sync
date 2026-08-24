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
QPushButton[pandaComponent="button"][variant="dark"] {{
    background: {c.text_primary}; color: {c.text_on_color}; border-color: {c.text_primary};
}}
QPushButton[pandaComponent="button"][variant="dark"]:hover {{
    background: {c.navigation_active}; border-color: {c.navigation_active};
}}
QPushButton[pandaComponent="button"][variant="dark"]:pressed {{
    background: {c.navigation_rail}; border-color: {c.navigation_rail};
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
QPushButton[pandaComponent="button"][variant="dark"]:focus,
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
QFrame[pandaComponent="workRail"] {{
    background: {c.navigation_rail}; border: none;
}}
QFrame[pandaComponent="railBrand"] {{
    background: {c.navigation_rail}; border: none;
    border-bottom: {b.hairline}px solid {c.navigation_active};
}}
QLabel[pandaComponent="brandMark"] {{
    background: {c.brand}; color: {c.text_on_color}; border-radius: {r.compact_control}px;
}}
QLabel[pandaComponent="brandName"] {{ color: #f1f4f7; background: transparent; }}
QLabel[pandaComponent="brandVersion"] {{ color: #6b7480; background: transparent; }}
QPushButton[pandaComponent="navigationButton"] {{
    background: transparent; border: {b.hairline}px solid transparent;
    border-radius: {r.control}px; padding: 0; text-align: right;
}}
QPushButton[pandaComponent="navigationButton"]:hover {{ background: {c.navigation_task}; }}
QPushButton[pandaComponent="navigationButton"]:focus {{
    border: {b.focus}px solid {c.navigation_accent}; background: {c.navigation_task};
}}
QPushButton[pandaComponent="navigationButton"][active="true"] {{
    background: {c.navigation_active}; border-color: {c.navigation_active};
}}
QLabel[pandaComponent="navigationLabel"] {{ color: {c.navigation_text}; background: transparent; }}
QLabel[pandaComponent="navigationLabel"][active="true"] {{ color: {c.text_on_color}; }}
QLabel[pandaComponent="navigationIcon"] {{ background: transparent; }}
QLabel[pandaComponent="navigationCount"] {{
    min-width: 12px; min-height: 20px; max-height: 20px; padding: 0 5px;
    color: #8a93a1; background: {c.navigation_active}; border-radius: 10px;
}}
QLabel[pandaComponent="navigationCount"][active="true"] {{
    color: #f0b64a; background: #3a2f14;
}}
QFrame[pandaComponent="navigationAccent"] {{
    background: {c.navigation_accent}; border: none; border-radius: 2px;
}}
QWidget[pandaComponent="taskDockContainer"] {{
    background: {c.navigation_rail}; border-top: {b.hairline}px solid {c.navigation_active};
}}
QPushButton[pandaComponent="taskDock"] {{
    background: {c.navigation_task}; border: {b.hairline}px solid {c.navigation_border};
    border-radius: {r.control}px; padding: 0; text-align: right;
}}
QPushButton[pandaComponent="taskDock"]:hover {{ background: {c.navigation_active}; }}
QPushButton[pandaComponent="taskDock"]:focus {{ border: {b.focus}px solid {c.navigation_accent}; }}
QLabel[pandaComponent="taskIndicator"] {{
    background: #6b7480; border-radius: 4px;
}}
QLabel[pandaComponent="taskIndicator"][taskState="running"] {{ background: {c.navigation_accent}; }}
QLabel[pandaComponent="taskIndicator"][taskState="succeeded"] {{ background: {c.approval}; }}
QLabel[pandaComponent="taskIndicator"][taskState="failed"] {{ background: {c.error}; }}
QLabel[pandaComponent="taskIndicator"][taskState="cancelled"],
QLabel[pandaComponent="taskIndicator"][taskState="queued"] {{ background: {c.irrelevant}; }}
QLabel[pandaComponent="taskTitle"] {{ color: #e6eaef; background: transparent; }}
QLabel[pandaComponent="taskCount"] {{ color: {c.navigation_accent}; background: transparent; }}
QLabel[pandaComponent="taskDetail"] {{ color: #7c8592; background: transparent; }}
QProgressBar[pandaComponent="taskProgress"] {{
    background: {c.navigation_border}; border: none; border-radius: 2px;
}}
QProgressBar[pandaComponent="taskProgress"]::chunk {{
    background: {c.navigation_accent}; border-radius: 2px;
}}
QFrame[pandaComponent="taskCenter"] {{
    background: {c.surface}; border: {b.hairline}px solid {c.border_control};
    border-radius: {r.card}px;
}}
QFrame[pandaComponent="taskCenterHeader"] {{
    background: {c.surface}; border: none;
    border-bottom: {b.hairline}px solid {c.border_secondary};
}}
QLabel[pandaComponent="taskCenterCount"] {{
    color: {c.text_secondary}; background: {c.irrelevant_tint};
    min-height: 20px; padding: 0 7px; border-radius: 10px;
}}
QScrollArea[pandaComponent="taskCenterScroll"], QWidget[pandaComponent="taskCenterBody"] {{
    background: {c.surface}; border: none;
}}
QLabel[pandaComponent="taskCenterSection"] {{ color: {c.text_heading}; }}
QFrame[pandaComponent="taskCenterRow"] {{
    background: {c.surface}; border: {b.hairline}px solid {c.border_secondary};
    border-radius: {r.control}px;
}}
QLabel[pandaComponent="taskCenterIndicator"], QLabel[pandaComponent="overviewTaskIndicator"] {{
    background: {c.irrelevant}; border-radius: 4px;
}}
QLabel[pandaComponent="taskCenterIndicator"][taskState="running"],
QLabel[pandaComponent="overviewTaskIndicator"][taskState="running"] {{ background: {c.brand}; }}
QLabel[pandaComponent="taskCenterIndicator"][taskState="succeeded"],
QLabel[pandaComponent="overviewTaskIndicator"][taskState="succeeded"] {{ background: {c.approval}; }}
QLabel[pandaComponent="taskCenterIndicator"][taskState="failed"],
QLabel[pandaComponent="overviewTaskIndicator"][taskState="failed"] {{ background: {c.error}; }}
QLabel[pandaComponent="taskCenterState"][taskState="running"] {{ color: {c.brand_hover}; }}
QLabel[pandaComponent="taskCenterState"][taskState="succeeded"] {{ color: {c.approval}; }}
QLabel[pandaComponent="taskCenterState"][taskState="failed"] {{ color: {c.error}; }}
QLabel[pandaComponent="taskCenterState"][taskState="queued"],
QLabel[pandaComponent="taskCenterState"][taskState="cancelled"] {{ color: {c.text_secondary}; }}
QLabel[pandaComponent="taskCenterDetail"] {{ color: {c.text_secondary}; }}
QProgressBar[pandaComponent="taskCenterProgress"], QProgressBar[pandaComponent="overviewTaskProgress"] {{
    background: {c.border_secondary}; border: none; border-radius: 3px;
}}
QProgressBar[pandaComponent="taskCenterProgress"]::chunk,
QProgressBar[pandaComponent="overviewTaskProgress"]::chunk {{
    background: {c.brand}; border-radius: 3px;
}}
QPushButton[pandaComponent="taskCancel"] {{
    color: {c.error}; background: transparent; border: none; padding: 2px 4px;
}}
QPushButton[pandaComponent="taskCancel"]:hover {{ color: {c.destructive}; text-decoration: underline; }}
QPushButton[pandaComponent="taskCancel"]:focus {{ border: {b.focus}px solid {c.focus}; border-radius: {r.compact_control}px; }}
QPushButton[pandaComponent="taskLink"] {{
    color: {c.brand_hover}; background: transparent; border: none; text-align: right;
    padding: 2px 0;
}}
QPushButton[pandaComponent="taskLink"]:hover {{ text-decoration: underline; }}
QPushButton[pandaComponent="taskLink"]:focus {{ border: {b.focus}px solid {c.focus}; border-radius: {r.compact_control}px; }}
QFrame[pandaComponent="overviewTaskSummary"] {{
    background: {c.surface_secondary}; border: {b.hairline}px solid {c.border_secondary};
    border-radius: {r.control}px;
}}
QFrame[pandaComponent="screenHeader"] {{
    background: {c.surface}; border: none;
    border-bottom: {b.hairline}px solid {c.border_primary};
}}
QScrollArea[pandaComponent="overviewScroll"] {{
    background: {c.application_background}; border: none;
}}
QWidget[pandaComponent="overviewCanvas"] {{ background: {c.application_background}; }}
QFrame[pandaComponent="overviewCard"], QFrame[pandaComponent="overviewPanel"] {{
    background: {c.surface}; border: {b.hairline}px solid {c.border_primary};
    border-radius: {r.card}px;
}}
QFrame[pandaComponent="cardAccent"][semantic="attention"] {{ background: {c.warning}; border: none; }}
QFrame[pandaComponent="cardAccent"][semantic="approval"] {{ background: {c.approval}; border: none; }}
QFrame[pandaComponent="cardAccent"][semantic="export"] {{ background: {c.brand_hover}; border: none; }}
QLabel[pandaComponent="metricValue"] {{ color: {c.text_primary}; background: transparent; }}
QLabel[pandaComponent="metricLabel"] {{ color: {c.text_secondary}; background: transparent; }}
QLabel[pandaComponent="metricUnavailable"] {{ color: {c.text_placeholder}; background: transparent; }}
QFrame[pandaComponent="breakdownChip"] {{
    background: {c.surface_secondary}; border: {b.hairline}px solid {c.border_secondary};
    border-radius: {r.chip}px;
}}
QLabel[pandaComponent="breakdownDot"][semantic="attention"] {{ background: {c.warning}; border-radius: 3px; }}
QLabel[pandaComponent="breakdownDot"][semantic="error"] {{ background: {c.error}; border-radius: 3px; }}
QLabel[pandaComponent="breakdownDot"][semantic="duplicate"] {{ background: {c.duplicate}; border-radius: 3px; }}
QFrame[pandaComponent="metricsStrip"] {{
    background: {c.surface}; border: {b.hairline}px solid {c.border_primary};
    border-radius: {r.panel}px;
}}
QFrame[pandaComponent="metricCell"] {{ background: transparent; border: none; }}
QFrame[pandaComponent="recentRow"] {{
    background: transparent; border: none; border-top: {b.hairline}px solid {c.border_secondary};
}}
QLabel[pandaComponent="recentDot"][semantic="ready"] {{ background: {c.approval}; border-radius: 3px; }}
QLabel[pandaComponent="recentDot"][semantic="warning"] {{ background: {c.warning}; border-radius: 3px; }}
QLabel[pandaComponent="recentDot"][semantic="error"] {{ background: {c.error}; border-radius: 3px; }}
QLabel[pandaComponent="recentDot"][semantic="new"] {{ background: {c.informational}; border-radius: 3px; }}
QLabel[pandaComponent="recentDot"][semantic="exported"] {{ background: {c.exported}; border-radius: 3px; }}
QLabel[pandaComponent="recentDot"][semantic="duplicate"] {{ background: {c.duplicate}; border-radius: 3px; }}
QLabel[pandaComponent="recentDot"][semantic="irrelevant"],
QLabel[pandaComponent="recentDot"][semantic="neutral"] {{ background: {c.irrelevant}; border-radius: 3px; }}
QFrame[pandaComponent="idleTaskCard"] {{
    background: {c.surface_secondary}; border: {b.hairline}px solid {c.border_secondary};
    border-radius: {r.control}px;
}}
QFrame[pandaComponent="routePlaceholder"] {{
    background: {c.application_background}; border: none;
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
