"""Application release-version contract."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from app.application.task_manager import TaskManager
from app.ui.components.navigation import NavigationRail
from app.ui.models.task_list_model import TaskListModel
from app.version import APP_VERSION, __version__


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_application_version_is_the_first_formal_release() -> None:
    assert APP_VERSION == "2.0.0"
    assert __version__ == APP_VERSION


def test_navigation_displays_the_authoritative_application_version(qapp) -> None:
    navigation = NavigationRail(TaskListModel(TaskManager()))

    version_label = navigation.findChild(QLabel, "applicationVersion")

    assert version_label is not None
    assert version_label.text() == APP_VERSION
