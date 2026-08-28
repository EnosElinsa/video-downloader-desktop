"""Modern, Qt-thread-safe desktop shell for the downloader."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QUrl, Signal, Slot
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow,
    QLineEdit, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .models import DownloadEvent, DownloadRequest, DownloadResult
from .queue import DownloadQueue
from .theme import app_font, stylesheet
from .widgets import ProgressCell, RowActions


class WorkerSignals(QObject):
    event = Signal(object)
    finished = Signal(object)
    failed = Signal(str)


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
            result = self.service.download(self.request, self.signals.event.emit, self.cancel_event)
            if not isinstance(result, DownloadResult):
                result = DownloadResult(bool(result), None, None, None, None)
            self.signals.finished.emit(result)
        except Exception as exc:  # worker failures are always marshalled as data
            self.signals.failed.emit(str(exc))


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
        browse = QPushButton("Browse"); browse.clicked.connect(self._choose_output_dir); form.addWidget(browse, 2, 2)
        form.addWidget(QLabel("Format"), 3, 0)
        self.format_combo = QComboBox(); self.format_combo.addItem("Automatic (best video + audio)", "bv*+ba/b"); self.format_combo.addItem("Best single file", "best"); form.addWidget(self.format_combo, 3, 1)
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
        self.settings.output_dir = Path(self.output_dir_edit.text().strip() or self.settings.output_dir)
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
        item = self.queue._items[item_id]
        worker = DownloadWorker(self.service, item.request); self._workers[item_id] = worker
        worker.signals.event.connect(lambda event, i=item_id: self._handle_event(i, event)); worker.signals.finished.connect(lambda result, i=item_id: self._handle_finished(i, result)); worker.signals.failed.connect(lambda error, i=item_id: self._handle_failed(i, error)); self.thread_pool.start(worker)

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
        self._set_status(item_id, "queued"); row = self._row_for_item.get(item_id)
        if row is not None:
            self.queue_table.cellWidget(row, self.PROGRESS_COLUMN).set_value(0)
            self.queue_table.item(row, 0).setText(self.queue.snapshot()[row]["url"])

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

    def _handle_event(self, item_id, event):
        if not isinstance(event, DownloadEvent): return
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

    def _handle_finished(self, item_id, result):
        self._workers.pop(item_id, None)
        current = next((i for i in self.queue.snapshot() if i["id"] == item_id), None)
        if current is None or current["status"] == "cancelled":
            return
        if result.success:
            self.queue.update_status(item_id, "success", filename=result.filename, title=result.title); self._set_status(item_id, "success"); self._log(f"Finished: {result.title or result.filename or 'download'}")
        else: self._mark_cancelled(item_id) if result.error_code == "cancelled" else self._mark_failed(item_id, result.error_message or "Download failed", result.error_code)

    def _handle_failed(self, item_id, error): self._workers.pop(item_id, None); self._mark_failed(item_id, error, "download_failed")
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
    def _choose_output_dir(self):
        chosen = QFileDialog.getExistingDirectory(self, "Choose output directory", self.output_dir_edit.text())
        if chosen: self.output_dir_edit.setText(chosen)
    def _open_folder(self, item_id):
        snapshot = next((i for i in self.queue.snapshot() if i["id"] == item_id), None)
        if snapshot: QDesktopServices.openUrl(QUrl.fromLocalFile(snapshot["output_dir"]))
    def _show_settings(self):
        self.settings.save()
