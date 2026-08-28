"""Focused settings editor with validation and explicit save intent."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class SettingsDialog(QDialog):
    save_requested = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsDialog")
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(500)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        self.general_group = QGroupBox("General", self)
        general = QFormLayout(self.general_group)
        general.setSpacing(10)

        output = QWidget(self)
        output_layout = QHBoxLayout(output)
        output_layout.setContentsMargins(0, 0, 0, 0)
        self.output_dir_edit = QLineEdit(str(settings.output_dir), output)
        self.output_dir_edit.setObjectName("settingsOutputDirectory")
        browse = QPushButton("Browse", output)
        browse.setObjectName("settingsBrowse")
        browse.setAccessibleName("Browse output directory")
        browse.clicked.connect(self._choose_output_dir)
        output_layout.addWidget(self.output_dir_edit, 1)
        output_layout.addWidget(browse)
        general.addRow("Output directory", output)

        self.concurrent_downloads_spin = QSpinBox(self)
        self.concurrent_downloads_spin.setRange(1, 8)
        self.concurrent_downloads_spin.setValue(settings.concurrent_downloads)
        self.concurrent_downloads_spin.setObjectName("concurrentDownloads")
        general.addRow("Concurrent downloads", self.concurrent_downloads_spin)

        self.startup_behavior_combo = QComboBox(self)
        self.startup_behavior_combo.setObjectName("startupBehavior")
        self.startup_behavior_combo.setAccessibleName("Startup behavior")
        self.startup_behavior_combo.addItem("Open normally", "normal")
        self.startup_behavior_combo.addItem("Start minimized", "minimized")
        self.startup_behavior_combo.setCurrentIndex(
            max(0, self.startup_behavior_combo.findData(settings.startup_behavior))
        )
        general.addRow("Startup", self.startup_behavior_combo)

        self.theme_combo = QComboBox(self)
        self.theme_combo.setObjectName("settingsTheme")
        self.theme_combo.setAccessibleName("Theme")
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(settings.theme)))
        general.addRow("Theme", self.theme_combo)
        root.addWidget(self.general_group)

        self.network_group = QGroupBox("Network & access", self)
        network = QFormLayout(self.network_group)
        network.setSpacing(10)

        self.proxy_enabled_checkbox = QCheckBox("Use proxy", self)
        self.proxy_enabled_checkbox.setObjectName("proxyEnabled")
        self.proxy_enabled_checkbox.setAccessibleName("Use proxy")
        self.proxy_enabled_checkbox.setChecked(settings.use_proxy)
        network.addRow("Proxy", self.proxy_enabled_checkbox)

        self.proxy_url_edit = QLineEdit(settings.proxy_url or "", self)
        self.proxy_url_edit.setObjectName("proxyUrl")
        self.proxy_url_edit.setAccessibleName("Proxy URL")
        self.proxy_url_edit.setPlaceholderText("socks5://127.0.0.1:1080")
        self.proxy_enabled_checkbox.toggled.connect(self.proxy_url_edit.setEnabled)
        self.proxy_url_edit.setEnabled(self.proxy_enabled_checkbox.isChecked())
        network.addRow("Proxy address", self.proxy_url_edit)

        self.cookie_browser_combo = QComboBox(self)
        self.cookie_browser_combo.setObjectName("browserCookies")
        self.cookie_browser_combo.setAccessibleName("Browser cookies")
        for label, value in (
            ("None", None),
            ("Chrome", "chrome"),
            ("Edge", "edge"),
            ("Firefox", "firefox"),
            ("Brave", "brave"),
            ("Opera", "opera"),
            ("Chromium", "chromium"),
        ):
            self.cookie_browser_combo.addItem(label, value)
        self.cookie_browser_combo.setCurrentIndex(
            max(0, self.cookie_browser_combo.findData(settings.cookie_browser))
        )
        network.addRow("Browser cookies", self.cookie_browser_combo)
        root.addWidget(self.network_group)

        self.error_label = QLabel(self)
        self.error_label.setObjectName("settingsError")
        self.error_label.setStyleSheet("color:#F06A75;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        root.addWidget(self.error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel, self
        )
        self.save_button = buttons.button(QDialogButtonBox.Save)
        self.save_button.setObjectName("settingsSave")
        self.save_button.setAccessibleName("Save settings")
        self.cancel_button = buttons.button(QDialogButtonBox.Cancel)
        self.cancel_button.setObjectName("settingsCancel")
        self.cancel_button.setAccessibleName("Cancel settings")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _choose_output_dir(self):
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose output directory", self.output_dir_edit.text()
        )
        if chosen:
            self.output_dir_edit.setText(chosen)

    def _validate(self):
        raw = self.output_dir_edit.text().strip()
        if not raw:
            self.error_label.setText("Choose an output directory.")
            self.error_label.show()
            return False
        try:
            path = Path(raw)
            if path.exists() and not path.is_dir():
                raise OSError("path is not a directory")
            path.mkdir(parents=True, exist_ok=True)
            if not os.access(path, os.W_OK):
                raise OSError("directory is not writable")
        except OSError as error:
            self.error_label.setText(f"Output directory is not writable: {error}")
            self.error_label.show()
            return False
        if self.proxy_enabled_checkbox.isChecked():
            parsed = urlparse(self.proxy_url_edit.text().strip())
            if parsed.scheme not in {"http", "https", "socks5", "socks5h"} or not parsed.hostname:
                self.error_label.setText(
                    "Enter a valid proxy URL, such as socks5://127.0.0.1:1080."
                )
                self.error_label.show()
                return False
        self.error_label.hide()
        return True

    def accept(self):
        if self._validate():
            self.save_requested.emit()
