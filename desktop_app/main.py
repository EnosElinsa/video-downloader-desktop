"""Application entry point."""

import sys

from PySide6.QtWidgets import QApplication

from .download_core import DownloadService
from .main_window import MainWindow
from .settings import AppSettings


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    settings = AppSettings.load()
    window = MainWindow(settings, DownloadService())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
