from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from .ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Zyvarnth")
    app.setOrganizationName("Zyvarnth")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

