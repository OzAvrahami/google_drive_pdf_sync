"""Offline visual harness for the Panda 2.0 TaskManager, Dock, and Task Center.

No DocumentStore, Drive client, PDF, Excel, environment file, or credential is read.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if "--snapshot" in sys.argv:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from app.application.task_manager import TaskAccess, TaskManager, TaskType
from app.ui.shell import PandaMainWindow
from app.ui.tasks.synthetic import SyntheticTaskRunner
from app.ui.theme.typography import register_bundled_fonts


class _EmptySource:
    def all(self) -> list:
        return []


def _window_size(value: str) -> tuple[int, int]:
    try:
        width, height = value.lower().split("x", 1)
        return int(width), int(height)
    except (ValueError, AttributeError) as exc:
        raise argparse.ArgumentTypeError("size must use WIDTHxHEIGHT") from exc


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=("idle", "queue", "outcomes"), default="queue")
    parser.add_argument("--size", type=_window_size, default=(1440, 900))
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--after-ms", type=int, default=650)
    parser.add_argument("--closed-center", action="store_true")
    return parser.parse_args()


def _submit_queue(manager: TaskManager, *, fast: bool) -> None:
    scale = 20 if fast else 180
    manager.submit(
        task_type=TaskType.DOCUMENT_PROCESSING,
        title="עיבוד 24 מסמכים — הדגמה",
        description="משימת כתיבה סינתטית",
        access=TaskAccess.WRITE,
        cancellable=True,
        runner=SyntheticTaskRunner(steps=24, interval_ms=scale, result_summary="24 מסמכי הדגמה עובדו"),
    )
    manager.submit(
        task_type=TaskType.EXCEL_EXPORT,
        title="ייצוא 12 רשומות — הדגמה",
        access=TaskAccess.WRITE,
        runner=SyntheticTaskRunner(steps=12, interval_ms=scale, result_summary="12 רשומות הדגמה יוצאו"),
    )
    manager.submit(
        task_type=TaskType.DRIVE_SCAN,
        title="סריקת Drive — הדגמה בלבד",
        access=TaskAccess.READ_ONLY,
        cancellable=True,
        runner=SyntheticTaskRunner(steps=40, interval_ms=scale, indeterminate=True),
    )
    manager.submit(
        task_type=TaskType.BULK_PROCESSING,
        title="משימת כשל סינתטית",
        access=TaskAccess.WRITE,
        runner=SyntheticTaskRunner(steps=8, interval_ms=scale, fail=True),
    )


def _submit_outcomes(manager: TaskManager) -> None:
    manager.submit(
        task_type=TaskType.DEVELOPMENT,
        title="משימה שהושלמה בהצלחה",
        access=TaskAccess.READ_ONLY,
        runner=SyntheticTaskRunner(steps=1, interval_ms=10, result_summary="18 מסמכי הדגמה עובדו"),
    )
    manager.submit(
        task_type=TaskType.DEVELOPMENT,
        title="משימה שנכשלה",
        access=TaskAccess.READ_ONLY,
        runner=SyntheticTaskRunner(steps=1, interval_ms=10, fail=True),
    )


def main() -> int:
    args = _args()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Panda 2.0 Task Gallery")
    register_bundled_fonts()
    manager = TaskManager(history_limit=20)
    window = PandaMainWindow(_EmptySource(), task_manager=manager)
    window.resize(*args.size)
    window.show()
    if args.scenario == "queue":
        _submit_queue(manager, fast=bool(args.snapshot))
    elif args.scenario == "outcomes":
        _submit_outcomes(manager)
    if not args.closed_center:
        window.task_center.open_panel()

    if args.snapshot:
        loop = QEventLoop()
        QTimer.singleShot(max(20, args.after_ms), loop.quit)
        loop.exec()
        args.snapshot.parent.mkdir(parents=True, exist_ok=True)
        if not window.grab().save(str(args.snapshot), "PNG"):
            return 1
        # Synthetic tasks are cooperatively cancellable only where advertised;
        # avoid closing the shell while any demo task is still active.
        return 0
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

