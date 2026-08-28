from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton

from desktop_app.main_window import MainWindow
from desktop_app.main_window import WorkerBridge
from desktop_app.models import DownloadEvent
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


def test_card_quality_labels_distinguish_automatic_and_single_file(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window.add_urls("https://example.test/auto")
    window.format_combo.setCurrentIndex(window.format_combo.findData("best"))
    window.add_urls("https://example.test/best")
    assert "Automatic" in window.queue_list.card_at(0).meta_label.text()
    assert "Best single file" in window.queue_list.card_at(1).meta_label.text()


def test_url_input_enter_and_ctrl_enter_add_to_queue(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window.url_input.setFocus()
    window.url_input.insertPlainText("https://example.test/enter")
    qtbot.keyClick(window.url_input, Qt.Key_Return)
    assert window.queue_list.rowCount() == 1
    window.url_input.insertPlainText("https://example.test/ctrl")
    qtbot.keyClick(window.url_input, Qt.Key_Return, Qt.ControlModifier)
    assert window.queue_list.rowCount() == 2


def test_controls_have_stable_object_and_accessibility_names(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    dialog = window._create_settings_dialog(); qtbot.addWidget(dialog)
    for widget in (dialog.startup_behavior_combo, dialog.theme_combo, dialog.proxy_enabled_checkbox, dialog.proxy_url_edit, dialog.cookie_browser_combo, dialog.save_button, dialog.cancel_button):
        assert widget.objectName()
        assert widget.accessibleName()
    assert dialog.findChild(QPushButton, "settingsBrowse") is not None
    assert window.activity_clear.objectName() == "activityClear"
    assert window.activity_drawer.objectName() == "activityDrawer"


def test_invalid_settings_show_inline_error_and_do_not_save(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    dialog = window._create_settings_dialog(); qtbot.addWidget(dialog)
    dialog.output_dir_edit.setText("   ")
    dialog.accept()
    assert dialog.error_label.text()
    assert window.settings.output_dir == tmp_path
    dialog.output_dir_edit.setText(str(tmp_path / "valid"))
    dialog.proxy_enabled_checkbox.setChecked(True)
    dialog.proxy_url_edit.setText("not a proxy")
    dialog.accept()
    assert dialog.error_label.text()


def test_card_controls_fit_at_minimum_size(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window.add_urls("https://example.test/video")
    card = window.queue_list.card_at(0)
    window.layout().activate()
    for button in (card.start_button, card.retry_button, card.cancel_button, card.open_button, card.remove_button):
        assert card.rect().contains(card.mapFromGlobal(button.mapToGlobal(button.rect().topLeft())))


def test_stale_bridge_events_are_ignored_after_retry_generation_changes(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window.add_urls("https://example.test/video")
    item_id = window.queue.snapshot()[0]["id"]
    old_bridge = WorkerBridge(item_id, window)
    new_bridge = WorkerBridge(item_id, window)
    window._bridges[item_id] = new_bridge
    old_bridge.connect_event(window._handle_event, Qt.DirectConnection)
    old_bridge.on_event(DownloadEvent("progress", percent=91))
    assert window.queue.snapshot()[0]["percent"] is None


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
