"""Approved Panda 2.0 design tokens expressed as immutable Python values."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ColorTokens:
    canvas_background: str = "#e6e4df"
    application_background: str = "#f7f6f2"
    surface: str = "#ffffff"
    surface_secondary: str = "#faf9f7"
    document_surface: str = "#efece7"
    subtle_divider_surface: str = "#fbfaf8"

    navigation_rail: str = "#1f2733"
    navigation_active: str = "#2b3543"
    navigation_task: str = "#26303d"
    navigation_border: str = "#313c4b"
    navigation_text: str = "#aab2bd"
    navigation_accent: str = "#1fb6ad"
    navigation_heading: str = "#f1f4f7"
    navigation_muted: str = "#6b7480"
    navigation_count: str = "#8a93a1"
    navigation_count_active: str = "#f0b64a"
    navigation_count_active_fill: str = "#3a2f14"
    navigation_task_title: str = "#e6eaef"
    navigation_task_detail: str = "#7c8592"

    text_primary: str = "#26241f"
    text_heading: str = "#3a362f"
    text_body: str = "#57534b"
    text_muted: str = "#6b675f"
    text_secondary: str = "#93908a"
    text_placeholder: str = "#a7a29a"
    text_on_color: str = "#ffffff"

    border_primary: str = "#e7e5e0"
    border_secondary: str = "#eeece7"
    border_row: str = "#f1efea"
    border_control: str = "#dcd9d3"
    border_frame: str = "#cdd3dc"
    border_strong: str = "#cbc6be"

    brand: str = "#0f8f8a"
    brand_hover: str = "#0c6f6a"
    brand_pressed: str = "#095b57"
    brand_tint: str = "#e6f4f2"
    brand_border_tint: str = "#cfe8e5"

    approval: str = "#2f7a44"
    approval_hover: str = "#28693b"
    approval_pressed: str = "#205731"
    approval_tint: str = "#eaf3ec"

    warning: str = "#9a6a12"
    warning_marker: str = "#e0a92b"
    warning_tint: str = "#fbf1dd"
    error: str = "#c0362c"
    destructive: str = "#b23b30"
    destructive_pressed: str = "#8f3027"
    error_tint: str = "#fbe6e3"
    destructive_note: str = "#fbf7f6"
    destructive_note_text: str = "#8a4a44"
    informational: str = "#2f5bd0"
    duplicate: str = "#7a3fb0"
    duplicate_tint: str = "#f2e9fb"
    processed: str = "#4a5568"
    irrelevant: str = "#6b7280"
    irrelevant_tint: str = "#eef0f2"
    exported: str = "#2b6a63"

    selection: str = "#eff6f4"
    selection_border: str = "#d3ebe9"
    focus: str = "#0f8f8a"
    focus_ring: str = "#e6f4f2"
    disabled_fill: str = "#c9cdc9"
    disabled_border: str = "#d9d5cf"


@dataclass(frozen=True, slots=True)
class SpacingTokens:
    tight: int = 4
    adjacent: int = 8
    standard: int = 12
    field_gap: int = 14
    section: int = 16
    panel: int = 20
    page: int = 24


@dataclass(frozen=True, slots=True)
class RadiusTokens:
    checkbox: int = 4
    chip: int = 7
    compact_control: int = 8
    control: int = 9
    approval: int = 10
    panel: int = 11
    card: int = 14
    modal: int = 16
    pill: int = 20


@dataclass(frozen=True, slots=True)
class BorderTokens:
    hairline: int = 1
    focus: int = 2
    selected_marker: int = 3


@dataclass(frozen=True, slots=True)
class ShadowToken:
    offset_y: int
    blur_radius: int
    color: str


@dataclass(frozen=True, slots=True)
class ElevationTokens:
    card: ShadowToken = ShadowToken(1, 2, "#0a000000")
    window: ShadowToken = ShadowToken(22, 54, "#1f000000")
    confirmation: ShadowToken = ShadowToken(14, 40, "#29000000")
    task_flyout: ShadowToken = ShadowToken(18, 48, "#38000000")
    duplicate_modal: ShadowToken = ShadowToken(24, 70, "#4d000000")


@dataclass(frozen=True, slots=True)
class ControlTokens:
    button_height: int = 35
    approval_button_height: int = 42
    compact_button_height: int = 30
    input_height: int = 37
    compact_input_height: int = 35
    search_height: int = 36
    icon_button: int = 36
    icon_button_small: int = 30
    icon_button_large: int = 42
    badge_height: int = 22
    table_header_height: int = 38
    table_row_height: int = 56


@dataclass(frozen=True, slots=True)
class LayoutTokens:
    target_width: int = 1440
    target_height: int = 900
    minimum_width: int = 1100
    minimum_height: int = 680
    navigation_width: int = 230
    screen_header_height: int = 58
    workspace_queue_width: int = 212
    workspace_queue_minimum_width: int = 172
    workspace_fields_width: int = 420
    workspace_fields_minimum_width: int = 360
    confirmation_width: int = 430
    duplicate_dialog_width: int = 800


COLORS = ColorTokens()
SPACING = SpacingTokens()
RADII = RadiusTokens()
BORDERS = BorderTokens()
ELEVATION = ElevationTokens()
CONTROLS = ControlTokens()
LAYOUT = LayoutTokens()
