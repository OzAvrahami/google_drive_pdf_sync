"""Headless behavior tests for the Phase E Panda 2.0 shell."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QScrollArea

import run
from app.models.document import Document
from app.services.document_store import DocumentStoreLoadError
from app.ui.models.queue_policy import calculate_queue_counts
from app.ui.routes import AppRoute, ROUTES
from app.ui.shell import PandaMainWindow
from app.ui.theme.icons import icon_for
from app.ui.theme.tokens import LAYOUT
from app.ui.views.document_queue import DocumentQueueView
from app.ui.views.ready import ReadyView
from app.version import APP_VERSION


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _document(document_id: str, status: str = "processed", **overrides) -> Document:
    values = {
        "drive_file_id": document_id,
        "id": f"record-{document_id}",
        "file_name": f"{document_id}.pdf",
        "folder_path": "2026",
        "status": status,
    }
    values.update(overrides)
    return Document(**values)


class ReadOnlySource:
    def __init__(self, documents=()) -> None:
        self.documents = list(documents)
        self.all_calls = 0
        self.write_calls = 0

    def all(self) -> list[Document]:
        self.all_calls += 1
        return list(self.documents)

    def upsert(self, _document) -> None:
        self.write_calls += 1
        raise AssertionError("Panda 2.0 shell must not write")

    def upsert_many(self, _documents) -> None:
        self.write_calls += 1
        raise AssertionError("Panda 2.0 shell must not write")


def _mixed_documents() -> list[Document]:
    return [
        _document("new", "new"),
        _document("review", "needs_review"),
        _document("failed", "failed"),
        _document("duplicate", "processed", is_duplicate_suspected=True),
        _document("processed", "processed"),
        _document("approved", "approved"),
        _document("irrelevant", "confirmed_irrelevant"),
        _document("excluded", "excluded"),
        _document("history", "exported"),
    ]


def test_shell_constructs_read_only_and_defaults_to_overview(qapp) -> None:
    source = ReadOnlySource(_mixed_documents())

    shell = PandaMainWindow(source)

    assert source.all_calls == 1
    assert source.write_calls == 0
    assert shell.current_route is AppRoute.OVERVIEW
    assert shell.stack.currentWidget() is shell.overview
    assert shell.navigation.button_for(AppRoute.OVERVIEW).is_active


def test_central_route_definition_has_six_unique_destinations_and_one_ready(qapp) -> None:
    assert [definition.label_he for definition in ROUTES] == [
        "סקירה",
        "נכנסו",
        "דורש טיפול",
        "מוכן",
        "לא רלוונטי",
        "היסטוריה",
    ]
    assert len({definition.route for definition in ROUTES}) == 6
    assert sum(definition.route is AppRoute.READY for definition in ROUTES) == 1
    assert all(not icon_for(definition.icon).isNull() for definition in ROUTES)


@pytest.mark.parametrize("route", list(AppRoute))
def test_route_switching_selects_real_destination_widget(qapp, route: AppRoute) -> None:
    shell = PandaMainWindow(ReadOnlySource())

    shell.navigate(route)

    assert shell.current_route is route
    assert shell.stack.currentWidget() is shell.view_for(route)
    assert shell.navigation.button_for(route).is_active
    assert shell.header_title.text() == next(
        definition.label_he for definition in ROUTES if definition.route is route
    )
    assert shell.header.isHidden() is (route is not AppRoute.OVERVIEW)


def test_all_six_routes_are_real_views_without_placeholders(qapp) -> None:
    shell = PandaMainWindow(ReadOnlySource())

    for route in AppRoute:
        if route in {
            AppRoute.INBOX,
            AppRoute.ATTENTION,
            AppRoute.IRRELEVANT,
            AppRoute.HISTORY,
        }:
            assert isinstance(shell.view_for(route), DocumentQueueView)
        elif route is AppRoute.READY:
            assert isinstance(shell.view_for(route), ReadyView)


def test_navigation_button_click_activates_route(qapp) -> None:
    shell = PandaMainWindow(ReadOnlySource())
    changed = QSignalSpy(shell.routeChanged)

    shell.navigation.button_for(AppRoute.ATTENTION).click()

    assert shell.current_route is AppRoute.ATTENTION
    assert changed.count() == 1


def test_pdf_benchmark_is_secondary_tool_not_seventh_business_route(qapp, tmp_path) -> None:
    shell = PandaMainWindow(ReadOnlySource(), pdf_corpus_root=tmp_path)

    shell.navigation.benchmark_button.click()

    assert len(ROUTES) == 6
    assert shell.current_route is AppRoute.OVERVIEW
    assert shell.benchmark_active
    assert shell.mode_stack.currentWidget() is shell.benchmark_page
    assert shell.navigation.benchmark_button.property("active") is True
    assert shell.navigation.task_dock.isVisibleTo(shell.navigation)

    shell.benchmark_page.backRequested.emit()

    assert not shell.benchmark_active
    assert shell.stack.currentWidget() is shell.overview


def test_pdf_benchmark_can_block_route_navigation_for_unsaved_review(qapp, tmp_path) -> None:
    shell = PandaMainWindow(ReadOnlySource(), pdf_corpus_root=tmp_path)
    shell.open_benchmark()

    with patch.object(shell.benchmark_page, "confirm_discard_changes", return_value=False):
        changed = shell.navigate(AppRoute.ATTENTION)

    assert changed is False
    assert shell.benchmark_active
    assert shell.current_route is AppRoute.OVERVIEW


def test_keyboard_enter_activates_focused_navigation_item(qapp) -> None:
    shell = PandaMainWindow(ReadOnlySource())
    shell.show()
    button = shell.navigation.button_for(AppRoute.HISTORY)
    button.setFocus()

    QTest.keyClick(button, Qt.Key.Key_Return)

    assert shell.current_route is AppRoute.HISTORY
    shell.close()


def test_arrow_key_moves_navigation_focus(qapp) -> None:
    shell = PandaMainWindow(ReadOnlySource())
    shell.show()
    shell.activateWindow()
    qapp.processEvents()
    overview = shell.navigation.button_for(AppRoute.OVERVIEW)
    inbox = shell.navigation.button_for(AppRoute.INBOX)
    overview.setFocus()
    qapp.processEvents()

    QTest.keyClick(overview, Qt.Key.Key_Down)

    assert shell.focusWidget() is inbox
    shell.close()


def test_rail_and_overview_share_counts_including_duplicate_override(qapp) -> None:
    documents = _mixed_documents()
    shell = PandaMainWindow(ReadOnlySource(documents))
    counts = calculate_queue_counts(documents)

    assert shell.navigation.button_for(AppRoute.INBOX).count == counts.inbox
    assert shell.navigation.button_for(AppRoute.ATTENTION).count == counts.attention == 3
    assert shell.navigation.button_for(AppRoute.READY).count == counts.ready == 2
    assert shell.navigation.button_for(AppRoute.IRRELEVANT).count == 2
    assert shell.navigation.button_for(AppRoute.HISTORY).count == 1
    assert shell.overview.cards["attention"].count == counts.attention


def test_refresh_updates_counts_without_reconstructing_shell(qapp) -> None:
    source = ReadOnlySource([_document("one", "new")])
    shell = PandaMainWindow(source)
    overview = shell.overview
    source.documents.append(_document("two", "approved"))

    shell.refresh()

    assert shell.overview is overview
    assert source.all_calls == 2
    assert source.write_calls == 0
    assert shell.navigation.button_for(AppRoute.READY).count == 1
    assert shell.overview.cards["ready_to_export"].count == 1


def test_overview_attention_breakdown_and_ready_cards(qapp) -> None:
    shell = PandaMainWindow(ReadOnlySource(_mixed_documents()))
    attention = shell.overview.cards["attention"]

    assert attention.breakdown["needs_review"].value == 1
    assert attention.breakdown["failed"].value == 1
    assert attention.breakdown["suspected_duplicate"].value == 1
    assert shell.overview.cards["ready_to_approve"].count == 1
    assert shell.overview.cards["ready_to_export"].count == 1


def test_overview_zero_count_state_is_numeric_and_stable(qapp) -> None:
    shell = PandaMainWindow(ReadOnlySource())

    assert all(card.count == 0 for card in shell.overview.cards.values())
    assert all(cell.value == 0 for cell in shell.overview.metrics.values())


def test_overview_card_routes_without_starting_operations(qapp) -> None:
    source = ReadOnlySource(_mixed_documents())
    shell = PandaMainWindow(source)

    shell.overview.cards["ready_to_approve"].action_button.click()

    assert shell.current_route is AppRoute.READY
    assert source.write_calls == 0


def test_header_operational_actions_are_visible_but_development_safe(qapp) -> None:
    shell = PandaMainWindow(ReadOnlySource())

    assert shell.scan_button.isEnabled() is False
    assert shell.process_button.isEnabled() is False
    assert "זמינה רק" in shell.scan_button.toolTip()
    assert shell.process_button.accessibleDescription()


def test_task_dock_starts_in_real_idle_state(qapp) -> None:
    shell = PandaMainWindow(ReadOnlySource())
    dock = shell.navigation.task_dock

    assert dock.state.active_count == 0
    assert dock.state.title == "אין משימות פעילות"
    assert dock.state.semantic == "idle"


def test_minimum_layout_keeps_rail_routes_and_overview_sections(qapp) -> None:
    shell = PandaMainWindow(ReadOnlySource(_mixed_documents()))
    shell.resize(LAYOUT.minimum_width, LAYOUT.minimum_height)
    shell.show()
    qapp.processEvents()

    assert shell.minimumSize().width() == 1100
    assert shell.minimumSize().height() == 680
    assert shell.navigation.width() == LAYOUT.navigation_width
    assert shell.navigation.geometry().right() == shell.centralWidget().geometry().right()
    assert all(shell.navigation.button_for(route).isVisible() for route in AppRoute)
    assert shell.overview.question_label.isVisible()
    scroll = shell.overview.findChild(QScrollArea)
    assert scroll is not None
    assert scroll.horizontalScrollBarPolicy() is Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    shell.close()


def test_target_layout_uses_approved_dimensions(qapp) -> None:
    shell = PandaMainWindow(ReadOnlySource())

    assert shell.size().width() == LAYOUT.target_width
    assert shell.size().height() == LAYOUT.target_height


def test_development_selector_is_explicit_and_removed_from_qt_arguments() -> None:
    assert run.panda2_requested(["run.py", "--panda2"])
    assert not run.panda2_requested(["run.py"])
    assert run.qt_arguments(["run.py", "--panda2", "-style", "Fusion"]) == [
        "run.py",
        "-style",
        "Fusion",
    ]


def test_run_selects_panda2_only_with_explicit_flag() -> None:
    source = ReadOnlySource()
    with (
        patch("run.ensure_dirs"),
        patch("run.QApplication") as application_class,
        patch("run.DocumentStore", return_value=source),
        patch("run.MainWindow") as legacy_window,
        patch("run.PandaMainWindow") as panda_window,
    ):
        application_class.return_value.exec.return_value = 0
        result = run.main(["run.py", "--panda2"])

    assert result == 0
    panda_window.assert_called_once_with(source, export_enabled=True)
    legacy_window.assert_not_called()
    application_class.return_value.setApplicationVersion.assert_called_once_with(
        APP_VERSION
    )
    application_class.return_value.setStyleSheet.assert_not_called()


def test_run_default_remains_legacy() -> None:
    source = ReadOnlySource()
    with (
        patch("run.ensure_dirs"),
        patch("run.QApplication") as application_class,
        patch("run.DocumentStore", return_value=source),
        patch("run.MainWindow") as legacy_window,
        patch("run.PandaMainWindow") as panda_window,
    ):
        application_class.return_value.exec.return_value = 0
        result = run.main(["run.py"])

    assert result == 0
    legacy_window.assert_called_once_with(source)
    panda_window.assert_not_called()
    application_class.return_value.setStyleSheet.assert_called_once()


def test_panda2_selector_preserves_fail_closed_store_startup() -> None:
    error = DocumentStoreLoadError(Path("data/documents.json"), "malformed_json", "bad")
    with (
        patch("run.ensure_dirs"),
        patch("run.QApplication") as application_class,
        patch("run.DocumentStore", side_effect=error),
        patch("run.PandaMainWindow") as panda_window,
        patch("run.QMessageBox.critical") as critical,
    ):
        result = run.main(["run.py", "--panda2"])

    assert result == 1
    panda_window.assert_not_called()
    application_class.return_value.exec.assert_not_called()
    critical.assert_called_once()
