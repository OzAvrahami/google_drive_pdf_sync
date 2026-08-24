"""Panda typography roles and optional bundled-font registration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QWidget


PRIMARY_FONT_FALLBACKS = (
    "IBM Plex Sans Hebrew",
    "Segoe UI",
    "Arial",
    "sans-serif",
)
MONO_FONT_FALLBACKS = (
    "IBM Plex Mono",
    "Cascadia Mono",
    "Consolas",
    "Courier New",
    "monospace",
)
FONT_ASSET_DIRECTORY = Path(__file__).resolve().parents[1] / "assets" / "fonts"
_FONT_EXTENSIONS = frozenset({".ttf", ".otf"})


class TypographyRole(str, Enum):
    APPLICATION_TITLE = "application_title"
    PAGE_TITLE = "page_title"
    SECTION_TITLE = "section_title"
    BODY = "body"
    COMPACT_BODY = "compact_body"
    TABLE = "table"
    LABEL = "label"
    HELPER = "helper"
    METRIC = "metric"
    BADGE = "badge"
    TECHNICAL = "technical"


@dataclass(frozen=True, slots=True)
class TypographySpec:
    pixel_size: int
    weight: QFont.Weight
    monospace: bool = False


@dataclass(frozen=True, slots=True)
class FontRegistrationResult:
    loaded_families: tuple[str, ...]
    failed_paths: tuple[Path, ...]
    attempted_paths: tuple[Path, ...]


TYPOGRAPHY: dict[TypographyRole, TypographySpec] = {
    TypographyRole.APPLICATION_TITLE: TypographySpec(21, QFont.Weight.Bold),
    TypographyRole.PAGE_TITLE: TypographySpec(17, QFont.Weight.Bold),
    TypographyRole.SECTION_TITLE: TypographySpec(16, QFont.Weight.Bold),
    TypographyRole.BODY: TypographySpec(13, QFont.Weight.Normal),
    TypographyRole.COMPACT_BODY: TypographySpec(12, QFont.Weight.Normal),
    TypographyRole.TABLE: TypographySpec(13, QFont.Weight.Medium),
    TypographyRole.LABEL: TypographySpec(12, QFont.Weight.DemiBold),
    TypographyRole.HELPER: TypographySpec(11, QFont.Weight.Normal),
    TypographyRole.METRIC: TypographySpec(36, QFont.Weight.DemiBold),
    TypographyRole.BADGE: TypographySpec(11, QFont.Weight.DemiBold),
    TypographyRole.TECHNICAL: TypographySpec(12, QFont.Weight.Normal, True),
}


def _default_font_assets() -> tuple[Path, ...]:
    if not FONT_ASSET_DIRECTORY.exists():
        return ()
    return tuple(
        path
        for path in sorted(FONT_ASSET_DIRECTORY.iterdir())
        if path.is_file() and path.suffix.lower() in _FONT_EXTENSIONS
    )


def register_bundled_fonts(
    paths: Iterable[str | Path] | None = None,
) -> FontRegistrationResult:
    """Register supplied/local fonts without downloading or searching globally."""
    candidates = tuple(Path(path) for path in paths) if paths is not None else _default_font_assets()
    loaded: list[str] = []
    failed: list[Path] = []
    for path in candidates:
        if not path.is_file() or path.suffix.lower() not in _FONT_EXTENSIONS:
            failed.append(path)
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            failed.append(path)
            continue
        loaded.extend(QFontDatabase.applicationFontFamilies(font_id))
    return FontRegistrationResult(tuple(dict.fromkeys(loaded)), tuple(failed), candidates)


def font_for(role: TypographyRole) -> QFont:
    spec = TYPOGRAPHY[role]
    font = QFont()
    font.setFamilies(list(MONO_FONT_FALLBACKS if spec.monospace else PRIMARY_FONT_FALLBACKS))
    font.setPixelSize(spec.pixel_size)
    font.setWeight(spec.weight)
    if spec.monospace:
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFixedPitch(True)
    return font


def apply_typography(widget: QWidget, role: TypographyRole) -> None:
    widget.setProperty("typographyRole", role.value)
    widget.setFont(font_for(role))
