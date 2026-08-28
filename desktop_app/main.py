"""Application entry point."""

import sys

from PySide6.QtWidgets import QApplication

from .download_core import DownloadService
from .main_window import MainWindow
from .settings import AppSettings


def show_window(window: MainWindow, startup_behavior: str) -> None:
    """Show the main window using the locally saved startup preference."""
    if startup_behavior == "minimized":
        window.showMinimized()
    else:
        window.show()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    settings = AppSettings.load()
    window = MainWindow(settings, DownloadService())
    show_window(window, settings.startup_behavior)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
