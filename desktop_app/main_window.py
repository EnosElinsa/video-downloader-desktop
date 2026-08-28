"""Modern, Qt-thread-safe desktop shell for the downloader."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QMainWindow, QLineEdit, QPlainTextEdit,
    QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .models import DownloadEvent, DownloadRequest, DownloadResult
from .queue import DownloadQueue
from .theme import app_font, stylesheet
from .widgets import ProgressCell, RowActions


class WorkerSignals(QObject):
    """Typed service-to-worker signal contract.

    PySide exposes user-defined Python dataclasses to Qt as ``PyObject`` at
    the meta-object layer. Raw Qt signals therefore stay private; the public
    connect/emit methods provide and validate the typed contract.
    """

    _event = Signal(object)
    _finished = Signal(object)
    _failed = Signal(str)

    def connect_event(self, receiver: Callable[[DownloadEvent], None], connection_type: Qt.ConnectionType = Qt.AutoConnection) -> None:
        self._event.connect(receiver, connection_type)

    def connect_finished(self, receiver: Callable[[DownloadResult], None], connection_type: Qt.ConnectionType = Qt.AutoConnection) -> None:
        self._finished.connect(receiver, connection_type)

    def connect_failed(self, receiver: Callable[[str], None], connection_type: Qt.ConnectionType = Qt.AutoConnection) -> None:
        self._failed.connect(receiver, connection_type)

    def emit_event(self, event: DownloadEvent) -> None:
        if not isinstance(event, DownloadEvent):
            raise TypeError("event must be a DownloadEvent")
        self._event.emit(event)

    def emit_finished(self, result: DownloadResult) -> None:
        if not isinstance(result, DownloadResult):
            raise TypeError("result must be a DownloadResult")
        self._finished.emit(result)

    def emit_failed(self, error: str) -> None:
        if not isinstance(error, str):
            raise TypeError("error must be a string")
        self._failed.emit(error)


class WorkerBridge(QObject):
    """QObject receiver that marshals worker callbacks onto the GUI thread."""

    _event_for_item = Signal(str, object)
    _finished_for_item = Signal(str, object)
    _failed_for_item = Signal(str, str)

    def __init__(self, item_id, parent=None):
        super().__init__(parent)
        self.item_id = item_id

    def connect_event(self, receiver: Callable[[str, DownloadEvent], None], connection_type: Qt.ConnectionType = Qt.AutoConnection) -> None:
        self._event_for_item.connect(receiver, connection_type)

    def connect_finished(self, receiver: Callable[[str, DownloadResult], None], connection_type: Qt.ConnectionType = Qt.AutoConnection) -> None:
        self._finished_for_item.connect(receiver, connection_type)

    def connect_failed(self, receiver: Callable[[str, str], None], connection_type: Qt.ConnectionType = Qt.AutoConnection) -> None:
        self._failed_for_item.connect(receiver, connection_type)

    @Slot(DownloadEvent)
    def on_event(self, event: DownloadEvent) -> None:
        if not isinstance(event, DownloadEvent):
            raise TypeError("event must be a DownloadEvent")
        self._event_for_item.emit(self.item_id, event)

    @Slot(DownloadResult)
    def on_finished(self, result: DownloadResult) -> None:
        if not isinstance(result, DownloadResult):
            raise TypeError("result must be a DownloadResult")
        self._finished_for_item.emit(self.item_id, result)

    @Slot(str)
    def on_failed(self, error):
        self._failed_for_item.emit(self.item_id, error)


class DownloadWorker(QRunnable):
    def __init__(self, service, request):
        super().__init__()
        self.service = service
        self.request = request
        self.cancel_event = threading.Event()
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            result = self.service.download(self.request, self.signals.emit_event, self.cancel_event)
            if not isinstance(result, DownloadResult):
                result = DownloadResult(bool(result), None, None, None, None)
            self.signals.emit_finished(result)
        except Exception as exc:  # worker failures are always marshalled as data
            self.signals.emit_failed(str(exc))


class SettingsDialog(QDialog):
    """Editable, local-only desktop preferences."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        form = QFormLayout(self)

        output_row = QWidget(self)
        output_layout = QHBoxLayout(output_row)
        output_layout.setContentsMargins(0, 0, 0, 0)
        self.output_dir_edit = QLineEdit(str(settings.output_dir), output_row)
        self.output_dir_browse_button = QPushButton("Browse", output_row)
        self.output_dir_browse_button.clicked.connect(self._choose_output_dir)
        output_layout.addWidget(self.output_dir_edit)
        output_layout.addWidget(self.output_dir_browse_button)
        form.addRow("Output directory", output_row)

        self.proxy_enabled_checkbox = QCheckBox("Use proxy", self)
        self.proxy_enabled_checkbox.setChecked(bool(settings.use_proxy))
        form.addRow("Proxy", self.proxy_enabled_checkbox)
        self.proxy_url_edit = QLineEdit(settings.proxy_url or "", self)
        self.proxy_url_edit.setPlaceholderText("socks5://127.0.0.1:1080")
        self.proxy_enabled_checkbox.toggled.connect(self.proxy_url_edit.setEnabled)
        self.proxy_url_edit.setEnabled(self.proxy_enabled_checkbox.isChecked())
        form.addRow("Proxy address", self.proxy_url_edit)

        self.cookie_browser_combo = QComboBox(self)
        for label, value in (("None", None), ("Chrome", "chrome"), ("Edge", "edge"),
                             ("Firefox", "firefox"), ("Brave", "brave"),
                             ("Opera", "opera"), ("Chromium", "chromium")):
            self.cookie_browser_combo.addItem(label, value)
        current_cookie = settings.cookie_browser or None
        cookie_index = self.cookie_browser_combo.findData(current_cookie)
        self.cookie_browser_combo.setCurrentIndex(max(0, cookie_index))
        form.addRow("Cookies from browser", self.cookie_browser_combo)

        self.concurrent_downloads_spin = QSpinBox(self)
        self.concurrent_downloads_spin.setRange(1, 8)
        self.concurrent_downloads_spin.setValue(max(1, int(settings.concurrent_downloads)))
        form.addRow("Concurrent downloads", self.concurrent_downloads_spin)

        self.startup_behavior_combo = QComboBox(self)
        self.startup_behavior_combo.addItem("Open normally", "normal")
        self.startup_behavior_combo.addItem("Start minimized", "minimized")
        startup_index = self.startup_behavior_combo.findData(settings.startup_behavior)
        self.startup_behavior_combo.setCurrentIndex(max(0, startup_index))
        form.addRow("Startup", self.startup_behavior_combo)

        self.theme_combo = QComboBox(self)
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.addItem("Light", "light")
        theme_index = self.theme_combo.findData(settings.theme)
        self.theme_combo.setCurrentIndex(max(0, theme_index))
        form.addRow("Theme", self.theme_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _choose_output_dir(self):
        chosen = QFileDialog.getExistingDirectory(self, "Choose output directory", self.output_dir_edit.text())
        if chosen:
            self.output_dir_edit.setText(chosen)


class MainWindow(QMainWindow):
    PROGRESS_COLUMN = 3
    STATUS_COLUMN = 4

    def __init__(self, settings, service):
        super().__init__()
        self.settings = settings
        self.service = service
        self.queue = DownloadQueue()
        self.thread_pool = QThreadPool(self)
        self.thread_pool.setMaxThreadCount(max(1, int(getattr(settings, "concurrent_downloads", 2))))
        self._workers = {}
        self._bridges = {}
        self._pending_retries = {}
        self._row_for_item = {}
        self.setWindowTitle("Video Downloader")
        self.setMinimumSize(900, 620)
        self.setFont(app_font())
        self._build_ui()
        self.apply_theme(getattr(settings, "theme", "dark"))

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Video Downloader")
        title.setFont(app_font(18, 700))
        subtitle = QLabel("Fast, private downloads")
        subtitle.setObjectName("muted")
        heading = QVBoxLayout(); heading.addWidget(title); heading.addWidget(subtitle)
        header.addLayout(heading); header.addStretch()
        self.theme_combo = QComboBox(); self.theme_combo.addItems(["Dark", "Light"])
        self.theme_combo.setCurrentText(str(getattr(self.settings, "theme", "dark")).title())
        self.theme_combo.currentTextChanged.connect(lambda text: self.apply_theme(text.lower()))
        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(self._show_settings)
        header.addWidget(self.theme_combo); header.addWidget(self.settings_button)
        layout.addLayout(header)

        composer = QFrame(); composer.setObjectName("panel")
        form = QGridLayout(composer); form.setContentsMargins(14, 12, 14, 12); form.setSpacing(8)
        form.addWidget(QLabel("URLs"), 0, 0)
        self.url_input = QPlainTextEdit(); self.url_input.setPlaceholderText("Paste one or more video URLs, one per line"); self.url_input.setFixedHeight(82)
        form.addWidget(self.url_input, 1, 0, 1, 3)
        form.addWidget(QLabel("Output directory"), 2, 0)
        self.output_dir_edit = QLineEdit(str(self.settings.output_dir)); form.addWidget(self.output_dir_edit, 2, 1)
        self.output_dir_edit.editingFinished.connect(self._persist_output_dir)
        browse = QPushButton("Browse"); browse.clicked.connect(self._choose_output_dir); form.addWidget(browse, 2, 2)
        form.addWidget(QLabel("Format"), 3, 0)
        self.format_combo = QComboBox(); self.format_combo.addItem("Automatic (best video + audio)", "bv*+ba/b"); self.format_combo.addItem("Best single file", "best")
        format_index = self.format_combo.findData(self.settings.format_selector)
        if format_index >= 0:
            self.format_combo.setCurrentIndex(format_index)
        form.addWidget(self.format_combo, 3, 1)
        self.add_button = QPushButton("Add URL"); self.add_button.setObjectName("primaryButton"); self.add_button.clicked.connect(lambda: self.add_urls(self.url_input.toPlainText())); form.addWidget(self.add_button, 3, 2)
        layout.addWidget(composer)

        queue_label = QLabel("Download queue"); queue_label.setFont(app_font(12, 600)); layout.addWidget(queue_label)
        self.queue_table = QTableWidget(0, 6)
        self.queue_table.setHorizontalHeaderLabels(["Title / URL", "Quality", "Site", "Progress", "Status", "Actions"])
        self.queue_table.setSelectionBehavior(QTableWidget.SelectRows); self.queue_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.queue_table.horizontalHeader().setStretchLastSection(True); self.queue_table.horizontalHeader().setSectionResizeMode(0, self.queue_table.horizontalHeader().ResizeMode.Stretch)
        layout.addWidget(self.queue_table, 1)

        activity_label = QLabel("Activity"); activity_label.setFont(app_font(12, 600)); layout.addWidget(activity_label)
        activity_row = QHBoxLayout(); self.activity_log = QPlainTextEdit(); self.activity_log.setReadOnly(True); self.activity_log.setMaximumHeight(110); activity_row.addWidget(self.activity_log)
        clear = QPushButton("Clear"); clear.clicked.connect(self.activity_log.clear); activity_row.addWidget(clear, 0, )
        layout.addLayout(activity_row)

    def apply_theme(self, mode):
        mode = mode if mode in ("dark", "light") else "dark"
        self.settings.theme = mode
        self.setStyleSheet(stylesheet(mode))

    @Slot(str)
    def add_urls(self, text):
        lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
        if not lines:
            return
        self._persist_output_dir()
        for url in lines:
            request = DownloadRequest(url, Path(self.settings.output_dir), self.format_combo.currentData(), getattr(self.settings, "use_proxy", False), getattr(self.settings, "proxy_url", None), getattr(self.settings, "cookie_browser", None))
            item_id = self.queue.add(request)
            self._add_row(item_id, request)
        self.url_input.clear()

    def _add_row(self, item_id, request):
        row = self.queue_table.rowCount(); self.queue_table.insertRow(row); self._row_for_item[item_id] = row
        self.queue_table.setItem(row, 0, QTableWidgetItem(request.url)); self.queue_table.setItem(row, 1, QTableWidgetItem(request.format_selector)); self.queue_table.setItem(row, 2, QTableWidgetItem(self._site(request.url)))
        progress = ProgressCell(); self.queue_table.setCellWidget(row, self.PROGRESS_COLUMN, progress); self.queue_table.setItem(row, self.STATUS_COLUMN, QTableWidgetItem("Queued"))
        actions = RowActions(lambda i=item_id: self.start_item(i), lambda i=item_id: self.retry_item(i), lambda i=item_id: self.cancel_item(i), lambda i=item_id: self._open_folder(i), lambda i=item_id: self.remove_item(i)); self.queue_table.setCellWidget(row, 5, actions); actions.retry.setEnabled(False); actions.cancel.setEnabled(True)

    @staticmethod
    def _site(url):
        from urllib.parse import urlparse
        return urlparse(url).netloc or "—"

    def _set_status(self, item_id, status):
        row = self._row_for_item.get(item_id)
        if row is None: return
        self.queue_table.item(row, self.STATUS_COLUMN).setText(status.title())
        actions = self.queue_table.cellWidget(row, 5)
        if actions:
            actions.start.setEnabled(status == "queued")
            actions.retry.setEnabled(status in ("failed", "cancelled"))
            actions.cancel.setEnabled(status in ("queued", "running", "paused"))

    @Slot(str)
    def start_item(self, item_id):
        if item_id in self._workers: return
        snapshot = next((i for i in self.queue.snapshot() if i["id"] == item_id), None)
        if not snapshot or snapshot["status"] != "queued": return
        self.queue.update_status(item_id, "running"); self._set_status(item_id, "running")
        item = self.queue.get(item_id)
        worker = DownloadWorker(self.service, item.request)
        bridge = WorkerBridge(item_id, self)
        self._workers[item_id] = worker
        self._bridges[item_id] = bridge
        # Explicit QObject receivers plus queued delivery prevent worker
        # threads from ever touching widgets, even for Python callables.
        worker.signals.connect_event(bridge.on_event, Qt.QueuedConnection)
        worker.signals.connect_finished(bridge.on_finished, Qt.QueuedConnection)
        worker.signals.connect_failed(bridge.on_failed, Qt.QueuedConnection)
        bridge.connect_event(self._handle_event, Qt.QueuedConnection)
        bridge.connect_finished(self._handle_finished, Qt.QueuedConnection)
        bridge.connect_failed(self._handle_failed, Qt.QueuedConnection)
        self.thread_pool.start(worker)

    @Slot(str)
    def cancel_item(self, item_id):
        worker = self._workers.get(item_id)
        if worker: worker.cancel_event.set()
        try: self.queue.cancel(item_id)
        except ValueError: return
        self._set_status(item_id, "cancelled"); self._log("Download cancelled")

    @Slot(str)
    def retry_item(self, item_id):
        try: self.queue.retry(item_id)
        except ValueError: return
        previous_request = self.queue.get(item_id).request
        request = DownloadRequest(
            url=previous_request.url,
            output_dir=Path(self.settings.output_dir),
            format_selector=self.settings.format_selector,
            use_proxy=self.settings.use_proxy,
            proxy_url=self.settings.proxy_url,
            cookie_browser=self.settings.cookie_browser,
            output_template=previous_request.output_template,
        )
        self.queue.replace_request(item_id, request)
        self._set_status(item_id, "queued"); row = self._row_for_item.get(item_id)
        if row is not None:
            self.queue_table.cellWidget(row, self.PROGRESS_COLUMN).set_value(0)
            self.queue_table.item(row, 0).setText(self.queue.snapshot()[row]["url"])
        if item_id in self._workers:
            # Cancellation is cooperative; retain the bridge and defer the
            # new worker until the previous worker has actually returned.
            self._pending_retries[item_id] = request
            self._set_status(item_id, "cancelling")
            self._log("Waiting for cancelled download to stop before retrying")
            return
        self.start_item(item_id)

    @Slot(str)
    def remove_item(self, item_id):
        if item_id in self._workers:
            return
        try:
            self.queue.remove(item_id)
        except KeyError:
            return
        row = self._row_for_item.pop(item_id, None)
        if row is not None:
            self.queue_table.removeRow(row)
            self._row_for_item = {key: (value - 1 if value > row else value) for key, value in self._row_for_item.items()}

    @Slot(str, DownloadEvent)
    def _handle_event(self, item_id: str, event: DownloadEvent) -> None:
        if not isinstance(event, DownloadEvent): return
        sender = self.sender()
        if sender is not None and sender is not self._bridges.get(item_id):
            return
        if item_id in self._pending_retries:
            return
        current = next((i for i in self.queue.snapshot() if i["id"] == item_id), None)
        if current is None or current["status"] == "cancelled":
            return
        if event.kind == "metadata":
            self.queue.update_status(item_id, "running", title=event.title); row = self._row_for_item.get(item_id); self.queue_table.item(row, 0).setText(event.title or self.queue.snapshot()[row]["url"])
        elif event.kind == "progress":
            self.queue.update_status(item_id, "running", percent=event.percent, speed=event.speed, eta=event.eta); self.queue_table.cellWidget(self._row_for_item[item_id], self.PROGRESS_COLUMN).set_value(event.percent)
        elif event.kind in ("log", "failed", "cancelled"): self._log(event.message)
        if event.kind == "failed": self._mark_failed(item_id, event.message, event.error_code)
        elif event.kind == "cancelled": self._mark_cancelled(item_id)

    @Slot(str, DownloadResult)
    def _handle_finished(self, item_id: str, result: DownloadResult) -> None:
        sender = self.sender()
        if sender is not None and sender is not self._bridges.get(item_id):
            return
        self._workers.pop(item_id, None)
        self._bridges.pop(item_id, None)
        if self._start_pending_retry(item_id):
            return
        current = next((i for i in self.queue.snapshot() if i["id"] == item_id), None)
        if current is None or current["status"] == "cancelled":
            return
        if result.success:
            self.queue.update_status(item_id, "success", filename=result.filename, title=result.title); self._set_status(item_id, "success"); self._log(f"Finished: {result.title or result.filename or 'download'}")
        else: self._mark_cancelled(item_id) if result.error_code == "cancelled" else self._mark_failed(item_id, result.error_message or "Download failed", result.error_code)

    @Slot(str, str)
    def _handle_failed(self, item_id, error):
        sender = self.sender()
        if sender is not None and sender is not self._bridges.get(item_id):
            return
        self._workers.pop(item_id, None)
        self._bridges.pop(item_id, None)
        if self._start_pending_retry(item_id):
            return
        self._mark_failed(item_id, error, "download_failed")
    def _start_pending_retry(self, item_id):
        if self._pending_retries.pop(item_id, None) is None:
            return False
        self._set_status(item_id, "queued")
        self.start_item(item_id)
        return True
    def _mark_failed(self, item_id, message, code):
        try: self.queue.update_status(item_id, "failed", error=message, error_code=code)
        except ValueError: return
        self._set_status(item_id, "failed"); self._log(message)
    def _mark_cancelled(self, item_id):
        self._workers.pop(item_id, None); self._set_status(item_id, "cancelled")
        try: self.queue.update_status(item_id, "cancelled")
        except ValueError: pass

    def _log(self, message):
        if message: self.activity_log.appendPlainText(str(message))
    def _persist_output_dir(self):
        selected = self.output_dir_edit.text().strip()
        if not selected:
            self.output_dir_edit.setText(str(self.settings.output_dir))
            return
        self.settings.output_dir = Path(selected)
        try:
            self.settings.save()
        except OSError as error:
            self._log(f"Could not save output directory: {error}")
    def _choose_output_dir(self):
        chosen = QFileDialog.getExistingDirectory(self, "Choose output directory", self.output_dir_edit.text())
        if chosen:
            self.output_dir_edit.setText(chosen)
            self._persist_output_dir()
    def _open_folder(self, item_id):
        snapshot = next((i for i in self.queue.snapshot() if i["id"] == item_id), None)
        if snapshot: QDesktopServices.openUrl(QUrl.fromLocalFile(snapshot["output_dir"]))
    def _show_settings(self):
        self._create_settings_dialog().exec()

    def _create_settings_dialog(self):
        dialog = SettingsDialog(self.settings, self)
        dialog.accepted.connect(lambda: self._apply_settings_dialog(dialog))
        return dialog

    def _apply_settings_dialog(self, dialog):
        output_dir = dialog.output_dir_edit.text().strip()
        if output_dir:
            self.settings.output_dir = Path(output_dir)
        self.settings.use_proxy = dialog.proxy_enabled_checkbox.isChecked()
        self.settings.proxy_url = dialog.proxy_url_edit.text().strip() or None
        self.settings.cookie_browser = dialog.cookie_browser_combo.currentData()
        self.settings.concurrent_downloads = dialog.concurrent_downloads_spin.value()
        self.settings.startup_behavior = dialog.startup_behavior_combo.currentData()
        self.settings.theme = dialog.theme_combo.currentData()
        self.settings.save()
        self.thread_pool.setMaxThreadCount(self.settings.concurrent_downloads)
        self.output_dir_edit.setText(str(self.settings.output_dir))
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentText(self.settings.theme.title())
        self.theme_combo.blockSignals(False)
        self.apply_theme(self.settings.theme)
