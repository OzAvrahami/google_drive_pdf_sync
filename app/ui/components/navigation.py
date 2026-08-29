"""Dark work-rail primitives for the Panda 2.0 shell."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.models.queue_policy import QueueCounts
from app.ui.routes import AppRoute, ROUTES, RouteDefinition
from app.ui.theme.icons import IconTone, icon_for
from app.ui.models.task_list_model import TaskListModel
from app.ui.tasks.task_dock import TaskDock
from app.ui.components.buttons import ButtonVariant, PandaButton
from app.ui.theme.icons import IconName
from app.ui.theme.stylesheet import repolish, set_dynamic_property
from app.ui.theme.tokens import LAYOUT, SPACING
from app.ui.theme.typography import TypographyRole, apply_typography
from app.version import APP_VERSION


class NavigationButton(QPushButton):
    """One keyboard-accessible route row with a separately styled count."""

    def __init__(self, definition: RouteDefinition, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.definition = definition
        self._active = False
        self.setProperty("pandaComponent", "navigationButton")
        self.setProperty("active", False)
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(40)
        self.setAccessibleName(definition.label_he)
        self.setAccessibleDescription(definition.accessible_description)
        self.setToolTip(definition.accessible_description)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 12, 0)
        layout.setSpacing(SPACING.adjacent)

        self._accent = QFrame()
        self._accent.setProperty("pandaComponent", "navigationAccent")
        self._accent.setFixedWidth(3)
        self._accent.setVisible(False)
        layout.addWidget(self._accent)

        self._icon = QLabel()
        self._icon.setProperty("pandaComponent", "navigationIcon")
        self._icon.setFixedSize(18, 18)
        self._icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self._icon)

        self._label = QLabel(definition.label_he)
        self._label.setProperty("pandaComponent", "navigationLabel")
        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        apply_typography(self._label, TypographyRole.BODY)
        layout.addWidget(self._label, 1)

        self._count = QLabel("0")
        self._count.setProperty("pandaComponent", "navigationCount")
        self._count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._count.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        apply_typography(self._count, TypographyRole.BADGE)
        self._count.setVisible(definition.show_count)
        layout.addWidget(self._count)
        self._refresh_icon()

    @property
    def route(self) -> AppRoute:
        return self.definition.route

    @property
    def count(self) -> int | None:
        return int(self._count.text()) if self.definition.show_count else None

    @property
    def is_active(self) -> bool:
        return self._active

    def set_count(self, count: int) -> None:
        if not self.definition.show_count:
            return
        self._count.setText(str(max(0, int(count))))
        self._count.setAccessibleName(f"{count} מסמכים")

    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        self.setChecked(self._active)
        set_dynamic_property(self, "active", self._active)
        for child in (self._label, self._count):
            child.setProperty("active", self._active)
            repolish(child)
        self._accent.setVisible(self._active)
        self._refresh_icon()

    def _refresh_icon(self) -> None:
        icon = icon_for(self.definition.icon, tone=IconTone.ON_DARK, size=17)
        mode = QIcon.Mode.Selected if self._active else QIcon.Mode.Normal
        self._icon.setPixmap(icon.pixmap(QSize(17, 17), mode, QIcon.State.Off))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.click()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            ancestor = self.parentWidget()
            focus_relative = None
            while ancestor is not None and not callable(focus_relative):
                focus_relative = getattr(ancestor, "focus_relative", None)
                if not callable(focus_relative):
                    ancestor = ancestor.parentWidget()
            if callable(focus_relative):
                focus_relative(self, -1 if event.key() == Qt.Key.Key_Up else 1)
                event.accept()
                return
        super().keyPressEvent(event)


class NavigationRail(QFrame):
    routeRequested = Signal(str)
    taskCenterRequested = Signal()
    benchmarkRequested = Signal()

    def __init__(self, task_model: TaskListModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("pandaComponent", "workRail")
        self.setFixedWidth(LAYOUT.navigation_width)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        brand = QFrame()
        brand.setProperty("pandaComponent", "railBrand")
        brand.setFixedHeight(LAYOUT.screen_header_height)
        brand_row = QHBoxLayout(brand)
        brand_row.setContentsMargins(18, 0, 18, 0)
        brand_row.setSpacing(10)
        mark = QLabel("פ")
        mark.setProperty("pandaComponent", "brandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(28, 28)
        mark.setAccessibleName("Panda")
        name = QLabel("Panda")
        name.setProperty("pandaComponent", "brandName")
        apply_typography(name, TypographyRole.SECTION_TITLE)
        version = QLabel(APP_VERSION)
        version.setObjectName("applicationVersion")
        version.setProperty("pandaComponent", "brandVersion")
        version.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        apply_typography(version, TypographyRole.TECHNICAL)
        brand_row.addWidget(mark)
        brand_row.addWidget(name)
        brand_row.addStretch()
        brand_row.addWidget(version)
        root.addWidget(brand)

        navigation = QWidget()
        navigation.setProperty("pandaComponent", "navigationList")
        navigation_layout = QVBoxLayout(navigation)
        navigation_layout.setContentsMargins(10, 12, 10, 4)
        navigation_layout.setSpacing(4)
        self._buttons: dict[AppRoute, NavigationButton] = {}
        for definition in ROUTES:
            button = NavigationButton(definition, navigation)
            button.clicked.connect(
                lambda _checked=False, route=definition.route: self.routeRequested.emit(route.value)
            )
            self._buttons[definition.route] = button
            navigation_layout.addWidget(button)
        navigation_layout.addStretch()
        root.addWidget(navigation, 1)

        dock_container = QWidget()
        dock_container.setProperty("pandaComponent", "taskDockContainer")
        dock_layout = QVBoxLayout(dock_container)
        dock_layout.setContentsMargins(12, 12, 12, 12)
        dock_layout.setSpacing(SPACING.adjacent)
        self.benchmark_button = PandaButton(
            "PDF Benchmark",
            variant=ButtonVariant.DARK,
            icon_name=IconName.DOCUMENT,
        )
        self.benchmark_button.setProperty("pandaComponent", "developerToolButton")
        self.benchmark_button.setCheckable(True)
        self.benchmark_button.setToolTip(
            "סקירת אמת מידה מקומית לקורפוס PDF פרטי"
        )
        self.benchmark_button.setAccessibleDescription(
            "כלי מפתחים מקומי; אינו חלק מתורי העבודה התפעוליים"
        )
        self.benchmark_button.clicked.connect(self.benchmarkRequested.emit)
        dock_layout.addWidget(self.benchmark_button)
        self.task_dock = TaskDock(task_model)
        self.task_dock.taskCenterRequested.connect(self.taskCenterRequested.emit)
        dock_layout.addWidget(self.task_dock)
        root.addWidget(dock_container)

    @property
    def routes(self) -> tuple[AppRoute, ...]:
        return tuple(self._buttons)

    def button_for(self, route: AppRoute | str) -> NavigationButton:
        return self._buttons[AppRoute(route)]

    def set_active_route(self, route: AppRoute | str) -> None:
        active = AppRoute(route)
        self.set_benchmark_active(False)
        for item_route, button in self._buttons.items():
            button.set_active(item_route is active)

    def set_benchmark_active(self, active: bool) -> None:
        set_dynamic_property(self.benchmark_button, "active", bool(active))
        self.benchmark_button.setChecked(bool(active))
        if active:
            for button in self._buttons.values():
                button.set_active(False)

    def set_counts(self, counts: QueueCounts) -> None:
        for definition in ROUTES:
            if definition.queue_route is not None:
                self._buttons[definition.route].set_count(counts.for_route(definition.queue_route))

    def focus_relative(self, current: NavigationButton, offset: int) -> None:
        ordered = list(self._buttons.values())
        try:
            index = ordered.index(current)
        except ValueError:
            return
        ordered[(index + offset) % len(ordered)].setFocus(Qt.FocusReason.TabFocusReason)
