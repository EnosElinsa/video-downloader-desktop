"""Application entry point, including a headless release-version probe."""

import ctypes
import os
import sys
from importlib import metadata

from PySide6.QtWidgets import QApplication

from desktop_app.download_core import DownloadService
from desktop_app.main_window import MainWindow
from desktop_app.settings import AppSettings


def _resolve_version() -> str:
    try:
        from video_downloader_build_version import VERSION

        return VERSION
    except ImportError:
        try:
            return metadata.version("video-downloader")
        except metadata.PackageNotFoundError:
            return "0.1.1"


APP_VERSION = _resolve_version()


def _write_version(message: str) -> None:
    """Write to a redirected handle even in a PyInstaller windowed process."""
    if sys.stdout is not None:
        print(message)
        return
    if os.name != "nt":
        return

    data = (message + "\n").encode("utf-8")
    handle = ctypes.windll.kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
    if handle in (0, -1):
        return
    written = ctypes.c_ulong(0)
    ctypes.windll.kernel32.WriteFile(handle, data, len(data), ctypes.byref(written), None)


def show_window(window: MainWindow, startup_behavior: str) -> None:
    """Show the main window using the locally saved startup preference."""
    if startup_behavior == "minimized":
        window.showMinimized()
    else:
        window.show()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--version" in args:
        _write_version(f"Video Downloader {APP_VERSION}")
        return 0

    gui_probe = "--gui-probe" in args
    if gui_probe:
        args = [arg for arg in args if arg != "--gui-probe"]

    qt_argv = sys.argv if argv is None else [sys.argv[0], *args]
    app = QApplication.instance() or QApplication(qt_argv)
    settings = AppSettings.load()
    window = MainWindow(settings, DownloadService())
    show_window(window, settings.startup_behavior)
    if gui_probe:
        app.processEvents()
        return 0 if not window.grab().isNull() else 1
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
