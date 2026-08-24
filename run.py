"""
Entry point for the local accountant tool.

Usage:
    python run.py             # legacy production UI
    python run.py --panda2    # Panda 2.0 development shell
"""
import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from app.config import ensure_dirs
from app.services.document_store import DocumentStore, DocumentStoreLoadError
from app.ui.main_window import MainWindow
from app.ui.shell import PandaMainWindow

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)


PANDA2_DEVELOPMENT_FLAG = "--panda2"


def panda2_requested(arguments: list[str]) -> bool:
    return PANDA2_DEVELOPMENT_FLAG in arguments[1:]


def qt_arguments(arguments: list[str]) -> list[str]:
    return [argument for argument in arguments if argument != PANDA2_DEVELOPMENT_FLAG]


def main(arguments: list[str] | None = None) -> int:
    startup_arguments = list(sys.argv if arguments is None else arguments)
    use_panda2 = panda2_requested(startup_arguments)
    ensure_dirs()

    app = QApplication(qt_arguments(startup_arguments))
    app.setApplicationName("Panda 2.0" if use_panda2 else "כלי חשבונאות")
    app.setOrganizationName("Internal")

    # Right-to-left UI for Hebrew
    from PySide6.QtCore import Qt
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    # Legacy styling remains scoped to the default legacy startup path.
    if not use_panda2:
        app.setStyleSheet(_STYLESHEET)

    try:
        store = DocumentStore()
    except DocumentStoreLoadError as exc:
        logger.critical("Panda refused to start with an unsafe document store: %s", exc)
        QMessageBox.critical(
            None,
            "Panda — שגיאת אחסון",
            "לא ניתן לטעון בבטחה את מאגר המסמכים המקומי.\n\n"
            "Panda לא תמשיך כדי למנוע סיכון לאובדן נתונים. "
            "המאגר לא שונה.\n\n"
            f"פרטים: {exc}",
        )
        return 1

    window = PandaMainWindow(store) if use_panda2 else MainWindow(store)
    window.show()

    logger.info("Application started.")
    return app.exec()


_STYLESHEET = """
QMainWindow, QDialog {
    background: #FAFAFA;
    font-family: Arial, sans-serif;
    font-size: 10pt;
}
QToolBar {
    background: #1E2A3A;
    border: none;
}
QTableWidget {
    border: 1px solid #E0E0E0;
    gridline-color: #E0E0E0;
    selection-background-color: #BBDEFB;
    alternate-background-color: #F5F5F5;
}
QTableWidget::item {
    padding: 4px 8px;
}
QHeaderView::section {
    background: #37474F;
    color: white;
    font-weight: bold;
    padding: 6px 8px;
    border: none;
    border-right: 1px solid #546E7A;
}
QGroupBox {
    font-weight: bold;
    border: 1px solid #BDBDBD;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 4px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}
QPushButton {
    padding: 5px 14px;
    border: 1px solid #BDBDBD;
    border-radius: 4px;
    background: #FFFFFF;
}
QPushButton:hover {
    background: #E3F2FD;
    border-color: #1565C0;
}
QPushButton:checked {
    background: #1565C0;
    color: white;
    border-color: #1565C0;
}
QLineEdit {
    border: 1px solid #BDBDBD;
    border-radius: 3px;
    padding: 4px 6px;
}
QLineEdit:focus {
    border-color: #1565C0;
}
QComboBox {
    border: 1px solid #BDBDBD;
    border-radius: 3px;
    padding: 4px 6px;
}
QStatusBar {
    background: #ECEFF1;
    border-top: 1px solid #CFD8DC;
    font-size: 9pt;
}
"""


if __name__ == "__main__":
    sys.exit(main())
