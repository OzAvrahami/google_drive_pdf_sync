"""Central SVG/QIcon loading with semantic state colors and safe fallback."""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from app.ui.theme.tokens import COLORS


ICON_DIRECTORY = Path(__file__).resolve().parents[1] / "assets" / "icons"
_SOURCE_COLOR = "#57534b"


class IconName(str, Enum):
    ARCHIVE = "archive"
    BACK = "back"
    CHECK = "check"
    CLOSE = "close"
    DOCUMENT = "document"
    ERROR = "error"
    INFO = "info"
    INBOX = "inbox"
    EXPORT = "export"
    OVERVIEW = "overview"
    PAGE_NEXT = "page-next"
    PAGE_PREVIOUS = "page-previous"
    SEARCH = "search"
    SCAN = "scan"
    PROCESS = "process"
    SUCCESS = "success"
    TRASH = "trash"
    WARNING = "warning"


class IconTone(str, Enum):
    DEFAULT = "default"
    BRAND = "brand"
    DESTRUCTIVE = "destructive"
    ON_DARK = "on_dark"


def available_icon_names() -> tuple[str, ...]:
    return tuple(icon.value for icon in IconName)


def icon_path(name: IconName | str) -> Path | None:
    value = name.value if isinstance(name, IconName) else str(name)
    path = ICON_DIRECTORY / f"{value}.svg"
    return path if path.is_file() else None


def _palette(tone: IconTone) -> tuple[str, str, str, str]:
    if tone is IconTone.DESTRUCTIVE:
        return (
            COLORS.error,
            COLORS.destructive,
            COLORS.destructive_pressed,
            COLORS.text_placeholder,
        )
    if tone is IconTone.BRAND:
        return (
            COLORS.brand,
            COLORS.brand_hover,
            COLORS.brand_pressed,
            COLORS.text_placeholder,
        )
    if tone is IconTone.ON_DARK:
        return (
            COLORS.navigation_text,
            COLORS.text_on_color,
            COLORS.navigation_accent,
            COLORS.text_muted,
        )
    return (
        COLORS.text_body,
        COLORS.brand,
        COLORS.brand_hover,
        COLORS.text_placeholder,
    )


def _render_svg(svg: bytes, color: str, size: int) -> QPixmap:
    recolored = svg.replace(_SOURCE_COLOR.encode("ascii"), color.encode("ascii"))
    renderer = QSvgRenderer(QByteArray(recolored))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pixmap


@lru_cache(maxsize=128)
def _cached_icon(name: str, tone: IconTone, size: int) -> QIcon:
    source = icon_path(name) or icon_path(IconName.DOCUMENT)
    if source is None:
        return QIcon()
    svg = source.read_bytes()
    normal, hover, active, disabled = _palette(tone)
    result = QIcon()
    result.addPixmap(_render_svg(svg, normal, size), QIcon.Mode.Normal, QIcon.State.Off)
    result.addPixmap(_render_svg(svg, hover, size), QIcon.Mode.Active, QIcon.State.Off)
    result.addPixmap(_render_svg(svg, active, size), QIcon.Mode.Selected, QIcon.State.On)
    result.addPixmap(_render_svg(svg, disabled, size), QIcon.Mode.Disabled, QIcon.State.Off)
    return result


def icon_for(
    name: IconName | str,
    *,
    tone: IconTone = IconTone.DEFAULT,
    size: int = 18,
) -> QIcon:
    """Return a state-aware icon; unknown names use the document fallback."""
    value = name.value if isinstance(name, IconName) else str(name)
    return _cached_icon(value, tone, size)
