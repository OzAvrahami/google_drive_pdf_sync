"""Headless behavioral tests for Panda 2.0 theme foundations."""

from __future__ import annotations

import os
from dataclasses import fields
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

from app.ui.theme.direction import TextKind, direction_profile_for, isolate_ltr
from app.ui.theme.icons import IconName, available_icon_names, icon_for, icon_path
from app.ui.theme.stylesheet import apply_panda_theme, panda_stylesheet
from app.ui.theme.tokens import COLORS, CONTROLS, LAYOUT, RADII, SPACING, ColorTokens
from app.ui.theme.typography import (
    MONO_FONT_FALLBACKS,
    PRIMARY_FONT_FALLBACKS,
    TYPOGRAPHY,
    TypographyRole,
    font_for,
    register_bundled_fonts,
)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_all_color_tokens_are_canonical_lowercase_hex() -> None:
    values = [getattr(COLORS, item.name) for item in fields(ColorTokens)]

    assert len(values) >= 40
    assert all(value.startswith("#") and len(value) == 7 for value in values)
    assert all(value == value.lower() for value in values)


def test_spacing_radius_and_control_scales_match_desktop_density() -> None:
    assert [getattr(SPACING, item.name) for item in fields(type(SPACING))] == [
        4,
        8,
        12,
        14,
        16,
        20,
        24,
    ]
    assert RADII.checkbox < RADII.control < RADII.card < RADII.pill
    assert CONTROLS.compact_button_height == 30
    assert CONTROLS.button_height == 35
    assert CONTROLS.approval_button_height == 42
    assert CONTROLS.table_row_height == 56


def test_layout_tokens_cover_minimum_and_target_desktop_sizes() -> None:
    assert (LAYOUT.minimum_width, LAYOUT.minimum_height) == (1100, 680)
    assert (LAYOUT.target_width, LAYOUT.target_height) == (1440, 900)
    assert LAYOUT.workspace_queue_minimum_width < LAYOUT.workspace_queue_width
    assert LAYOUT.workspace_fields_minimum_width < LAYOUT.workspace_fields_width


@pytest.mark.parametrize("role", list(TypographyRole))
def test_every_typography_role_returns_a_pixel_sized_font(role: TypographyRole) -> None:
    font = font_for(role)

    assert role in TYPOGRAPHY
    assert font.pixelSize() == TYPOGRAPHY[role].pixel_size
    assert font.weight() == TYPOGRAPHY[role].weight


def test_typography_fallback_chains_keep_approved_fonts_first() -> None:
    assert PRIMARY_FONT_FALLBACKS == (
        "IBM Plex Sans Hebrew",
        "Segoe UI",
        "Arial",
        "sans-serif",
    )
    assert MONO_FONT_FALLBACKS[0] == "IBM Plex Mono"
    assert MONO_FONT_FALLBACKS[1] == "Cascadia Mono"
    assert "Consolas" in MONO_FONT_FALLBACKS


def test_metric_role_uses_ui_sans_not_monospace() -> None:
    metric = font_for(TypographyRole.METRIC)

    assert TYPOGRAPHY[TypographyRole.METRIC].monospace is False
    assert metric.families() == list(PRIMARY_FONT_FALLBACKS)
    assert metric.fixedPitch() is False


def test_missing_font_registration_is_safe_and_explicit(qapp, tmp_path: Path) -> None:
    missing = tmp_path / "missing.ttf"

    result = register_bundled_fonts([missing])

    assert result.loaded_families == ()
    assert result.failed_paths == (missing,)
    assert result.attempted_paths == (missing,)


def test_stylesheet_is_token_driven_and_does_not_target_legacy_main_window() -> None:
    stylesheet = panda_stylesheet()

    assert COLORS.brand in stylesheet
    assert COLORS.approval in stylesheet
    assert COLORS.focus in stylesheet
    assert 'variant="destructive"' in stylesheet
    assert 'variant="approval"]:focus' in stylesheet
    assert 'validationState="invalid"' in stylesheet
    assert "QMainWindow" not in stylesheet
    assert "QTableWidget" not in stylesheet


def test_theme_application_is_scoped_to_one_root(qapp) -> None:
    themed = QWidget()
    untouched = QWidget()

    apply_panda_theme(themed)

    assert themed.property("pandaThemeRoot") is True
    assert themed.styleSheet() == panda_stylesheet()
    assert untouched.styleSheet() == ""


@pytest.mark.parametrize("name", list(IconName))
def test_internal_svg_icons_are_available_and_renderable(qapp, name: IconName) -> None:
    assert icon_path(name).is_file()
    assert icon_for(name).isNull() is False


def test_unknown_icon_uses_non_null_document_fallback(qapp) -> None:
    assert icon_for("not-an-approved-icon").isNull() is False
    assert "document" in available_icon_names()


@pytest.mark.parametrize(
    "kind, direction, horizontal_alignment",
    [
        (TextKind.HEBREW, Qt.LayoutDirection.RightToLeft, Qt.AlignmentFlag.AlignRight),
        (TextKind.FILENAME, Qt.LayoutDirection.LeftToRight, Qt.AlignmentFlag.AlignLeft),
        (TextKind.PATH, Qt.LayoutDirection.LeftToRight, Qt.AlignmentFlag.AlignLeft),
        (TextKind.DOCUMENT_NUMBER, Qt.LayoutDirection.LeftToRight, Qt.AlignmentFlag.AlignRight),
        (TextKind.AMOUNT, Qt.LayoutDirection.LeftToRight, Qt.AlignmentFlag.AlignRight),
    ],
)
def test_direction_profiles_are_explicit(
    kind: TextKind,
    direction: Qt.LayoutDirection,
    horizontal_alignment: Qt.AlignmentFlag,
) -> None:
    profile = direction_profile_for(kind)

    assert profile.layout_direction is direction
    assert profile.alignment is horizontal_alignment


def test_ltr_isolation_wraps_mixed_content_without_changing_it() -> None:
    assert isolate_ltr("INV-100") == "\u2066INV-100\u2069"
