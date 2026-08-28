from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from desktop_app.main_window import MainWindow
from desktop_app.resources import resource_path
from desktop_app.settings import AppSettings


class IdleService:
    def download(self, request, emit, cancel=None):
        raise AssertionError("probe must not start a download")


def test_resource_resolver_finds_icon_in_source_and_frozen_roots(monkeypatch, tmp_path):
    """Catch a frozen bundle resolving the header icon from the checkout path."""
    source_icon = resource_path("assets", "video-downloader.ico")
    assert source_icon.is_file()

    frozen_root = tmp_path / "bundle"
    frozen_icon = frozen_root / "assets" / "video-downloader.ico"
    frozen_icon.parent.mkdir(parents=True)
    frozen_icon.write_bytes(source_icon.read_bytes())
    monkeypatch.setattr(__import__("sys"), "frozen", True, raising=False)
    monkeypatch.setattr(__import__("sys"), "_MEIPASS", str(frozen_root), raising=False)

    assert resource_path("assets", "video-downloader.ico") == frozen_icon


def test_offscreen_gui_probe_constructs_shows_grabs_and_has_window_icon(qtbot, tmp_path):
    """Catch packaging smoke tests that only exercise ``--version``."""
    app = QApplication.instance() or QApplication([])
    window = MainWindow(AppSettings(output_dir=tmp_path), IdleService())
    qtbot.addWidget(window)
    window.show()
    app.processEvents()

    image = window.grab()

    assert not image.isNull()
    assert not window.windowIcon().isNull() or not window.header_icon_mark.pixmap().isNull()
    assert window.isVisible()
