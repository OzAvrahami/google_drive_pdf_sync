"""Safe QTimer-backed task runner used only by tests and development harnesses."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer

from app.application.task_manager import TaskError, TaskReporter, TaskResult


class SyntheticTaskRunner(QObject):
    def __init__(
        self,
        *,
        steps: int = 10,
        interval_ms: int = 150,
        indeterminate: bool = False,
        fail: bool = False,
        result_summary: str = "המשימה הסינתטית הושלמה",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if steps <= 0 or interval_ms <= 0:
            raise ValueError("steps and interval_ms must be positive")
        self._steps = steps
        self._interval_ms = interval_ms
        self._indeterminate = indeterminate
        self._fail = fail
        self._result_summary = result_summary
        self._reporter: TaskReporter | None = None
        self._current = 0
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._tick)

    @property
    def is_running(self) -> bool:
        return self._timer.isActive()

    def start(self, reporter: TaskReporter) -> None:
        if self._reporter is not None:
            raise RuntimeError("synthetic runner can only be started once")
        self._reporter = reporter
        reporter.progress(message="מתחיל משימה סינתטית…")
        self._timer.start()

    def request_cancel(self) -> bool:
        if self._reporter is None or not self._timer.isActive():
            return False
        self._timer.stop()
        self._reporter.cancelled("המשימה הסינתטית בוטלה בבטחה")
        return True

    def _tick(self) -> None:
        assert self._reporter is not None
        self._current += 1
        item = f"synthetic/document_{self._current:03d}.pdf"
        if self._indeterminate:
            self._reporter.progress(
                message="סורק נתוני הדגמה…",
                current_item=item,
            )
        else:
            self._reporter.progress(
                current=self._current,
                total=self._steps,
                message=f"מעבד פריט {self._current} מתוך {self._steps}",
                current_item=item,
            )
        if self._current < self._steps:
            return
        self._timer.stop()
        if self._fail:
            self._reporter.fail(
                TaskError(
                    summary="כשל סינתטי לצורך המחשה",
                    detail="לא בוצעה פעולה תפעולית ולא השתנו נתונים.",
                    diagnostic="SyntheticTaskRunner configured with fail=True",
                )
            )
        else:
            self._reporter.succeed(
                TaskResult(
                    self._result_summary,
                    {"completed": self._steps, "synthetic": True},
                )
            )

