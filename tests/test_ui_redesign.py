from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from desktop_app.main_window import MainWindow
from desktop_app.models import DownloadResult
from desktop_app.settings import AppSettings


class IdleService:
    def download(self, request, emit, cancel=None):
        return DownloadResult(False, None, None, "download_failed", "idle")


def _window(qtbot, tmp_path):
    window = MainWindow(AppSettings(output_dir=tmp_path), IdleService())
    qtbot.addWidget(window)
    window.resize(1067, 750)
    window.show()
    return window


def test_redesign_exposes_stable_primary_controls_and_empty_state(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    assert window.objectName() == "mainWindow"
    assert window.url_input.objectName() == "urlInput"
    assert window.add_button.objectName() == "addToQueueButton"
    assert window.queue_list.objectName() == "queueList"
    assert window.activity_toggle.objectName() == "activityToggle"
    assert window.queue_list.rowCount() == 0
    assert window.empty_state.isVisible()


def test_redesign_card_actions_follow_queue_state(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window.add_urls("https://example.test/video")
    card = window.queue_list.card_at(0)
    assert card.objectName() == "downloadCard"
    assert card.progress.objectName() == "downloadProgress"
    assert card.start_button.isVisible()
    assert not card.retry_button.isVisible()
    window.queue.update_status(card.item_id, "running")
    window.queue.update_status(card.item_id, "failed", error="network down")
    window._set_status(card.item_id, "failed")
    assert card.retry_button.isVisible()
    assert not card.start_button.isVisible()


def test_activity_drawer_is_collapsed_and_toggles(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    assert not window.activity_drawer.isVisible()
    window.activity_toggle.click()
    assert window.activity_drawer.isVisible()
    window.activity_clear.click()
    assert window.activity_log.toPlainText() == ""
    window.activity_toggle.click()
    assert not window.activity_drawer.isVisible()


def test_settings_dialog_has_groups_and_cancel_does_not_save(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    dialog = window._create_settings_dialog()
    qtbot.addWidget(dialog)
    assert dialog.general_group is not None
    assert dialog.network_group is not None
    original = window.settings.output_dir
    dialog.output_dir_edit.setText(str(tmp_path / "changed"))
    dialog.reject()
    assert window.settings.output_dir == original


def test_light_theme_switch_updates_application_style(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window.apply_theme("light")
    assert window.settings.theme == "light"
    assert "#F7F9FC" in window.styleSheet()
