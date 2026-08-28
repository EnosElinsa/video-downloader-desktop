from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame, QLabel

from desktop_app.main_window import MainWindow
from desktop_app.models import DownloadResult
from desktop_app.settings import AppSettings
from desktop_app.settings_dialog import SettingsDialog
from desktop_app.theme import stylesheet


class IdleService:
    def download(self, request, emit, cancel=None):
        return DownloadResult(False, None, None, "download_failed", "idle")


def _window(qtbot, tmp_path, *, width=1002, height=691):
    window = MainWindow(AppSettings(output_dir=tmp_path), IdleService())
    qtbot.addWidget(window)
    window.resize(width, height)
    window.show()
    QApplication.processEvents()
    return window


def test_theme_keeps_labels_and_layout_containers_transparent():
    dark = stylesheet("dark")

    assert "QWidget { background:" not in dark
    assert "QLabel { background: transparent" in dark
    assert "QComboBox::drop-down" in dark
    assert "QComboBox::down-arrow" not in dark
    assert "QSpinBox::up-button" in dark
    assert "QSpinBox::down-button" in dark
    assert "QSpinBox::up-arrow" not in dark
    assert "QSpinBox::down-arrow" not in dark


def test_comboboxes_and_spinbox_use_deterministic_painted_arrows(qtbot, tmp_path):
    from desktop_app.controls import ChevronComboBox, ChevronSpinBox

    window = _window(qtbot, tmp_path)
    dialog = SettingsDialog(window.settings)
    qtbot.addWidget(dialog)
    dialog.show()
    QApplication.processEvents()

    assert isinstance(window.theme_combo, ChevronComboBox)
    assert isinstance(window.format_combo, ChevronComboBox)
    assert isinstance(dialog.startup_behavior_combo, ChevronComboBox)
    assert isinstance(dialog.theme_combo, ChevronComboBox)
    assert isinstance(dialog.cookie_browser_combo, ChevronComboBox)
    assert isinstance(dialog.concurrent_downloads_spin, ChevronSpinBox)


def test_expanding_activity_does_not_compress_or_clip_composer(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    composer = window.findChild(QFrame, "composer")
    assert composer is not None
    initial_height = composer.height()

    window.activity_toggle.click()
    QApplication.processEvents()

    assert composer.height() == initial_height
    assert composer.height() >= composer.minimumSizeHint().height()
    assert composer.contentsRect().contains(window.add_button.geometry().bottomRight())
    assert window.activity_drawer.isVisible()
    assert window.content_widget.contentsRect().contains(
        window.activity_drawer.geometry().bottomRight()
    )


def test_progress_has_one_readable_percent_indicator_at_compact_width(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window.add_urls("https://example.test/video")
    item_id = window.queue.snapshot()[0]["id"]
    window.queue.update_status(item_id, "running", percent=8, speed=4_390_000, eta=522)
    window._set_status(item_id, "running")
    QApplication.processEvents()
    card = window.queue_list.card_at(0)

    assert not card.progress.bar.isTextVisible()
    assert card.detail_label.text() == "8%  ·  4390 KB/s  ·  ETA 522s"
    assert not card.detail_label.wordWrap()
    assert card.detail_label.width() >= card.detail_label.sizeHint().width()
    assert card.contentsRect().contains(card.detail_label.geometry().bottomRight())


def test_settings_dialog_has_production_minimum_and_unclipped_form_labels(qtbot, tmp_path):
    dialog = SettingsDialog(AppSettings(output_dir=tmp_path))
    qtbot.addWidget(dialog)
    dialog.resize(502, 544)
    dialog.show()
    QApplication.processEvents()

    assert dialog.width() >= 620
    assert dialog.height() >= 600
    labels = {
        label.text(): label
        for label in dialog.findChildren(QLabel)
        if label.text()
        in {
            "Output directory",
            "Concurrent downloads",
            "Startup",
            "Theme",
            "Proxy",
            "Proxy address",
            "Browser cookies",
        }
    }
    assert len(labels) == 7
    assert all(label.width() >= label.sizeHint().width() for label in labels.values())
    assert dialog.save_button.isVisible()
    assert dialog.cancel_button.isVisible()
    assert dialog.network_group.title() == "Network && access"
    assert dialog.save_button.hasFocus()
    assert dialog.output_dir_edit.cursorPosition() == 0


def test_compact_render_geometry_keeps_card_actions_inside_queue(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window.add_urls("https://www.rockstargames.com/videos/rk721912")
    item_id = window.queue.snapshot()[0]["id"]
    window.queue.update_status(item_id, "running", percent=8, speed=4_390_000, eta=522)
    window._set_status(item_id, "running")
    QApplication.processEvents()
    card = window.queue_list.card_at(0)

    assert card.height() >= card.minimumSizeHint().height()
    assert card.contentsRect().contains(card.cancel_button.geometry().bottomRight())
    assert card.status_label.width() >= card.status_label.sizeHint().width()
