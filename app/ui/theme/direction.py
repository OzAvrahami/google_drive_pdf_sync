"""Shared RTL/LTR conventions for Hebrew-first mixed-direction UI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget


class TextKind(str, Enum):
    HEBREW = "hebrew"
    AUTO = "auto"
    FILENAME = "filename"
    PATH = "path"
    DOCUMENT_NUMBER = "document_number"
    DATE = "date"
    AMOUNT = "amount"
    PERCENTAGE = "percentage"
    TECHNICAL = "technical"


@dataclass(frozen=True, slots=True)
class DirectionProfile:
    layout_direction: Qt.LayoutDirection
    alignment: Qt.AlignmentFlag


_PROFILES = {
    TextKind.HEBREW: DirectionProfile(
        Qt.LayoutDirection.RightToLeft, Qt.AlignmentFlag.AlignRight
    ),
    TextKind.AUTO: DirectionProfile(
        Qt.LayoutDirection.LayoutDirectionAuto, Qt.AlignmentFlag.AlignRight
    ),
    TextKind.FILENAME: DirectionProfile(
        Qt.LayoutDirection.LeftToRight, Qt.AlignmentFlag.AlignLeft
    ),
    TextKind.PATH: DirectionProfile(
        Qt.LayoutDirection.LeftToRight, Qt.AlignmentFlag.AlignLeft
    ),
    TextKind.DOCUMENT_NUMBER: DirectionProfile(
        Qt.LayoutDirection.LeftToRight, Qt.AlignmentFlag.AlignRight
    ),
    TextKind.DATE: DirectionProfile(
        Qt.LayoutDirection.LeftToRight, Qt.AlignmentFlag.AlignRight
    ),
    TextKind.AMOUNT: DirectionProfile(
        Qt.LayoutDirection.LeftToRight, Qt.AlignmentFlag.AlignRight
    ),
    TextKind.PERCENTAGE: DirectionProfile(
        Qt.LayoutDirection.LeftToRight, Qt.AlignmentFlag.AlignRight
    ),
    TextKind.TECHNICAL: DirectionProfile(
        Qt.LayoutDirection.LeftToRight, Qt.AlignmentFlag.AlignLeft
    ),
}


def direction_profile_for(kind: TextKind) -> DirectionProfile:
    return _PROFILES[kind]


def apply_text_direction(widget: QWidget, kind: TextKind) -> None:
    profile = direction_profile_for(kind)
    widget.setProperty("textDirection", kind.value)
    widget.setLayoutDirection(profile.layout_direction)
    set_alignment = getattr(widget, "setAlignment", None)
    if callable(set_alignment):
        set_alignment(profile.alignment | Qt.AlignmentFlag.AlignVCenter)


def isolate_ltr(text: str) -> str:
    """Wrap LTR data for safe interpolation inside Hebrew labels."""
    return f"\u2066{text}\u2069"
