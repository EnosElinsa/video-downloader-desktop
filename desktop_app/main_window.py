"""Thread-safe production desktop window for Video Downloader."""

from __future__ import annotations

import threading
from dataclasses import fields, replace
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .models import DownloadEvent, DownloadRequest, DownloadResult
from .queue import DownloadQueue
from .resources import resource_path
from .security import (
    configured_secret_values,
    install_redaction,
    register_secret_values,
    sanitize_message,
)
from .settings_dialog import SettingsDialog
from .theme import app_font, stylesheet
from .urls import normalize_http_url, normalized_hostname
from .widgets import DownloadCard, QueueList, UrlInput


class WorkerSignals(QObject):
    _event = Signal(object)
    _finished = Signal(object)
    _failed = Signal(str)

    def connect_event(self, receiver, connection_type=Qt.AutoConnection):
        self._event.connect(receiver, connection_type)

    def connect_finished(self, receiver, connection_type=Qt.AutoConnection):
        self._finished.connect(receiver, connection_type)

    def connect_failed(self, receiver, connection_type=Qt.AutoConnection):
        self._failed.connect(receiver, connection_type)

    def emit_event(self, event):
        if not isinstance(event, DownloadEvent):
            raise TypeError("event must be a DownloadEvent")
        self._event.emit(event)

    def emit_finished(self, result):
        if not isinstance(result, DownloadResult):
            raise TypeError("result must be a DownloadResult")
        self._finished.emit(result)

    def emit_failed(self, error):
        if not isinstance(error, str):
            raise TypeError("error must be a string")
        self._failed.emit(error)


class WorkerBridge(QObject):
    _event_for_item = Signal(str, object)
    _finished_for_item = Signal(str, object)
    _failed_for_item = Signal(str, str)

    def __init__(self, item_id, parent=None):
        super().__init__(parent)
        self.item_id = item_id

    def connect_event(self, receiver, connection_type=Qt.AutoConnection):
        self._event_for_item.connect(receiver, connection_type)

    def connect_finished(self, receiver, connection_type=Qt.AutoConnection):
        self._finished_for_item.connect(receiver, connection_type)

    def connect_failed(self, receiver, connection_type=Qt.AutoConnection):
        self._failed_for_item.connect(receiver, connection_type)

    @Slot(object)
    def on_event(self, event):
        if not isinstance(event, DownloadEvent):
            raise TypeError("event must be a DownloadEvent")
        self._event_for_item.emit(self.item_id, event)

    @Slot(object)
    def on_finished(self, result):
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
            result = self.service.download(
                self.request, self.signals.emit_event, self.cancel_event
            )
            if not isinstance(result, DownloadResult):
                result = DownloadResult(bool(result), None, None, None, None)
            self.signals.emit_finished(result)
        except Exception as error:
            secrets = configured_secret_values(self.request.proxy_url)
            self.signals.emit_failed(sanitize_message(error, secrets))


class MainWindow(QMainWindow):
    PROGRESS_COLUMN = 3
    STATUS_COLUMN = 4

    def __init__(self, settings, service):
        super().__init__()
        self.setObjectName("mainWindow")
        self.settings = settings
        self.service = service
        self.queue = DownloadQueue()
        self.thread_pool = QThreadPool(self)
        try:
            concurrency = int(getattr(settings, "concurrent_downloads", 2))
        except (TypeError, ValueError):
            concurrency = 2
        self.thread_pool.setMaxThreadCount(max(1, min(8, concurrency)))
        self._workers = {}
        self._bridges = {}
        self._pending_retries = {}
        self._cards = {}
        self.setWindowTitle("Video Downloader")
        self.setMinimumSize(1000, 680)
        self.setFont(app_font())
        self._build_ui()
        self.apply_theme(getattr(settings, "theme", "dark"))

    def _build_ui(self):
        root = QWidget(self)
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QFrame(self)
        header.setObjectName("appHeader")
        header.setFixedHeight(68)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 0, 24, 0)
        header_layout.setSpacing(12)

        icon_path = resource_path("assets", "video-downloader.ico")
        self.header_icon_mark = QLabel(header)
        self.header_icon_mark.setObjectName("headerIcon")
        self.header_icon_mark.setFixedSize(32, 32)
        self.header_icon_mark.setPixmap(QIcon(str(icon_path)).pixmap(28, 28))
        self.setWindowIcon(QIcon(str(icon_path)))
        header_layout.addWidget(self.header_icon_mark)

        brand = QVBoxLayout()
        brand.setSpacing(0)
        title = QLabel("Video Downloader", header)
        title.setFont(app_font(12, 700))
        self.header_status = QLabel("Ready", header)
        self.header_status.setObjectName("muted")
        brand.addWidget(title)
        brand.addWidget(self.header_status)
        header_layout.addLayout(brand)
        header_layout.addStretch()

        self.theme_combo = QComboBox(header)
        self.theme_combo.setObjectName("themeToggle")
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.setCurrentIndex(
            max(0, self.theme_combo.findData(self.settings.theme))
        )
        self.theme_combo.currentIndexChanged.connect(
            lambda _: self.apply_theme(self.theme_combo.currentData())
        )
        header_layout.addWidget(self.theme_combo)

        self.settings_button = QPushButton("Settings", header)
        self.settings_button.setObjectName("settingsButton")
        self.settings_button.clicked.connect(self._show_settings)
        header_layout.addWidget(self.settings_button)
        outer.addWidget(header)

        content = QWidget(root)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(14)
        outer.addWidget(content, 1)

        heading = QLabel("Download videos", content)
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        subtitle = QLabel(
            "Paste one or more links, choose a quality, and add them to your queue.",
            content,
        )
        subtitle.setObjectName("muted")
        layout.addWidget(subtitle)

        composer = QFrame(content)
        composer.setObjectName("composer")
        form = QGridLayout(composer)
        form.setContentsMargins(16, 14, 16, 16)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)

        label = QLabel("Video URLs", composer)
        label.setObjectName("sectionTitle")
        form.addWidget(label, 0, 0, 1, 3)
        self.url_input = UrlInput(composer)
        self.url_input.setObjectName("urlInput")
        self.url_input.setAccessibleName("Video URLs")
        self.url_input.setPlaceholderText("Paste one or more video URLs, one per line")
        self.url_input.setFixedHeight(76)
        self.url_input.submit_requested.connect(
            lambda: self.add_urls(self.url_input.toPlainText())
        )
        form.addWidget(self.url_input, 1, 0, 1, 3)

        output_label = QLabel("Output folder", composer)
        output_label.setObjectName("muted")
        form.addWidget(output_label, 2, 0)
        self.output_dir_edit = QLineEdit(str(self.settings.output_dir), composer)
        self.output_dir_edit.setObjectName("outputDirectory")
        self.output_dir_edit.editingFinished.connect(self._persist_output_dir)
        form.addWidget(self.output_dir_edit, 2, 1)
        browse = QPushButton("Browse", composer)
        browse.clicked.connect(self._choose_output_dir)
        form.addWidget(browse, 2, 2)

        quality_label = QLabel("Quality", composer)
        quality_label.setObjectName("muted")
        form.addWidget(quality_label, 3, 0)
        self.format_combo = QComboBox(composer)
        self.format_combo.setObjectName("qualityCombo")
        self.format_combo.addItem("Automatic (best)", "bv*+ba/b")
        self.format_combo.addItem("Best single file", "best")
        format_index = self.format_combo.findData(
            getattr(self.settings, "format_selector", "bv*+ba/b")
        )
        self.format_combo.setCurrentIndex(format_index if format_index >= 0 else 0)
        form.addWidget(self.format_combo, 3, 1)
        self.add_button = QPushButton("Add to queue", composer)
        self.add_button.setObjectName("addToQueueButton")
        self.add_button.setAccessibleName("Add to queue")
        self.add_button.setIcon(
            self.style().standardIcon(self.style().StandardPixmap.SP_MediaPlay)
        )
        self.add_button.clicked.connect(
            lambda: self.add_urls(self.url_input.toPlainText())
        )
        form.addWidget(self.add_button, 3, 2)
        layout.addWidget(composer)

        queue_heading = QHBoxLayout()
        queue_label = QLabel("Download queue", content)
        queue_label.setObjectName("sectionTitle")
        queue_heading.addWidget(queue_label)
        queue_heading.addStretch()
        layout.addLayout(queue_heading)

        scroll = QScrollArea(content)
        scroll.setObjectName("queueScroll")
        scroll.setWidgetResizable(True)
        self.queue_list = QueueList()
        self.queue_list.setObjectName("queueList")
        scroll.setWidget(self.queue_list)
        self.queue_table = self.queue_list
        layout.addWidget(scroll, 1)

        self.empty_state = QWidget(self.queue_list)
        empty_layout = QVBoxLayout(self.empty_state)
        empty_layout.setContentsMargins(16, 44, 16, 44)
        empty_layout.setAlignment(Qt.AlignCenter)
        empty_title = QLabel("No downloads yet", self.empty_state)
        empty_title.setFont(app_font(14, 600))
        empty_title.setAlignment(Qt.AlignCenter)
        empty_line = QLabel("Your queued videos will appear here.", self.empty_state)
        empty_line.setObjectName("muted")
        empty_line.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_line)
        self.queue_list.layout.insertWidget(0, self.empty_state)

        activity = QHBoxLayout()
        self.latest_activity = QLabel("No recent activity", content)
        self.latest_activity.setObjectName("latestActivity")
        activity.addWidget(self.latest_activity, 1)
        self.activity_toggle = QPushButton("View activity", content)
        self.activity_toggle.setObjectName("activityToggle")
        self.activity_toggle.setAccessibleName("View activity")
        self.activity_toggle.clicked.connect(self._toggle_activity)
        activity.addWidget(self.activity_toggle)
        layout.addLayout(activity)

        self.activity_drawer = QFrame(content)
        self.activity_drawer.setObjectName("activityDrawer")
        self.activity_drawer.setAccessibleName("Activity drawer")
        drawer_layout = QVBoxLayout(self.activity_drawer)
        drawer_header = QHBoxLayout()
        drawer_header.addWidget(QLabel("Activity", self.activity_drawer))
        drawer_header.addStretch()
        self.activity_clear = QPushButton("Clear", self.activity_drawer)
        self.activity_clear.setObjectName("activityClear")
        self.activity_clear.setAccessibleName("Clear activity")
        self.activity_clear.clicked.connect(lambda: self.activity_log.clear())
        drawer_header.addWidget(self.activity_clear)
        drawer_layout.addLayout(drawer_header)
        self.activity_log = QPlainTextEdit(self.activity_drawer)
        self.activity_log.setReadOnly(True)
        self.activity_log.setObjectName("activityLog")
        self.activity_log.setFixedHeight(100)
        drawer_layout.addWidget(self.activity_log)
        self.activity_drawer.setVisible(False)
        layout.addWidget(self.activity_drawer)

    def apply_theme(self, mode):
        mode = mode if mode in ("dark", "light") else "dark"
        self.settings.theme = mode
        self.setStyleSheet(stylesheet(mode))

    def _toggle_activity(self):
        visible = not self.activity_drawer.isVisible()
        self.activity_drawer.setVisible(visible)
        self.activity_toggle.setText("Hide activity" if visible else "View activity")

    @Slot(str)
    def add_urls(self, text):
        lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
        if not lines:
            return
        for line in lines:
            try:
                url = normalize_http_url(line)
            except ValueError:
                self._log("Skipped invalid URL. Enter a valid HTTP(S) URL with a hostname.")
                continue
            request = DownloadRequest(
                url,
                Path(self.settings.output_dir),
                self.format_combo.currentData(),
                getattr(self.settings, "use_proxy", False),
                getattr(self.settings, "proxy_url", None),
                getattr(self.settings, "cookie_browser", None),
            )
            item_id = self.queue.add(request)
            self._add_row(item_id, request)
        self.url_input.clear()

    def _add_row(self, item_id, request):
        display_url = self._safe_message(request.url)
        card = DownloadCard(item_id, display_url, request.format_selector, self.queue_list)
        card.action_requested.connect(self._card_action)
        self._cards[item_id] = card
        self.queue_list.add_card(card)
        self.empty_state.setVisible(False)
        self._update_header()

    def _card_action(self, item_id, action):
        actions = {
            "start": self.start_item,
            "retry": self.retry_item,
            "cancel": self.cancel_item,
            "open": self._open_folder,
            "remove": self.remove_item,
        }
        handler = actions.get(action)
        if handler:
            handler(item_id)

    @staticmethod
    def _site(url):
        return normalized_hostname(url)

    def _set_status(self, item_id, status):
        card = self._cards.get(item_id)
        if not card:
            return
        snapshot = next(
            (item for item in self.queue.snapshot() if item["id"] == item_id), {}
        )
        card.set_status(
            status,
            snapshot.get("percent"),
            snapshot.get("speed"),
            snapshot.get("eta"),
            snapshot.get("error_code"),
            snapshot.get("error"),
        )
        self._update_header()

    @Slot(str)
    def start_item(self, item_id):
        if item_id in self._workers:
            return
        snapshot = next(
            (item for item in self.queue.snapshot() if item["id"] == item_id), None
        )
        if not snapshot or snapshot["status"] != "queued":
            return
        self.queue.update_status(item_id, "running")
        self._set_status(item_id, "running")
        worker = DownloadWorker(self.service, self.queue.get(item_id).request)
        bridge = WorkerBridge(item_id, self)
        self._workers[item_id] = worker
        self._bridges[item_id] = bridge
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
        if worker:
            worker.cancel_event.set()
        try:
            self.queue.cancel(item_id)
        except ValueError:
            return
        self._set_status(item_id, "cancelled")
        self._log("Download cancelled")

    @Slot(str)
    def retry_item(self, item_id):
        try:
            self.queue.retry(item_id)
        except ValueError:
            return
        previous = self.queue.get(item_id).request
        selected_format = self.format_combo.currentData() or getattr(
            self.settings, "format_selector", "bv*+ba/b"
        )
        self.settings.format_selector = selected_format
        request = DownloadRequest(
            previous.url,
            Path(self.settings.output_dir),
            selected_format,
            getattr(self.settings, "use_proxy", False),
            getattr(self.settings, "proxy_url", None),
            getattr(self.settings, "cookie_browser", None),
            previous.output_template,
        )
        self.queue.replace_request(item_id, request)
        self._set_status(item_id, "queued")
        if item_id in self._workers:
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
        card = self._cards.pop(item_id, None)
        if card:
            self.queue_list.remove_card(card)
        self.empty_state.setVisible(not self._cards)
        self._update_header()

    @Slot(str, object)
    def _handle_event(self, item_id, event):
        sender = self.sender()
        if sender is not None and sender is not self._bridges.get(item_id):
            return
        if not isinstance(event, DownloadEvent) or item_id in self._pending_retries:
            return
        current = next(
            (item for item in self.queue.snapshot() if item["id"] == item_id), None
        )
        if current is None or current["status"] == "cancelled":
            return
        if event.kind == "metadata":
            safe_title = self._safe_message(event.title) if event.title else None
            self.queue.update_status(item_id, "running", title=safe_title)
            self._cards[item_id].title_label.setText(safe_title or current["url"])
        elif event.kind == "progress":
            self.queue.update_status(
                item_id,
                "running",
                percent=event.percent,
                speed=event.speed,
                eta=event.eta,
            )
            self._set_status(item_id, "running")
        elif event.kind in ("log", "cancelled"):
            self._log(event.message)
        if event.kind == "failed":
            self._mark_failed(item_id, event.message, event.error_code)
        elif event.kind == "cancelled":
            self._mark_cancelled(item_id)

    @Slot(str, object)
    def _handle_finished(self, item_id, result):
        sender = self.sender()
        if sender is not None and sender is not self._bridges.get(item_id):
            return
        self._workers.pop(item_id, None)
        self._bridges.pop(item_id, None)
        if self._start_pending_retry(item_id):
            return
        current = next(
            (item for item in self.queue.snapshot() if item["id"] == item_id), None
        )
        if current is None or current["status"] == "cancelled":
            return
        if result.success:
            self.queue.update_status(
                item_id,
                "success",
                filename=result.filename,
                title=result.title,
            )
            self._set_status(item_id, "success")
            self._log(f"Finished: {result.title or result.filename or 'download'}")
        elif result.error_code == "cancelled":
            self._mark_cancelled(item_id)
        elif current["status"] != "failed":
            self._mark_failed(
                item_id,
                result.error_message or "Download failed",
                result.error_code,
            )

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
        safe_message = self._safe_message(message)
        try:
            self.queue.update_status(
                item_id,
                "failed",
                error=safe_message,
                error_code=code or "download_failed",
            )
        except ValueError:
            return
        self._set_status(item_id, "failed")
        self._log(safe_message)

    def _mark_cancelled(self, item_id):
        self._workers.pop(item_id, None)
        try:
            self.queue.update_status(item_id, "cancelled", error_code="cancelled")
        except ValueError:
            pass
        self._set_status(item_id, "cancelled")

    def _safe_message(self, message):
        secrets = configured_secret_values(getattr(self.settings, "proxy_url", None))
        register_secret_values(secrets)
        return sanitize_message(message, secrets)

    def _log(self, message):
        if not message:
            return
        safe_message = self._safe_message(message)
        self.activity_log.appendPlainText(safe_message)
        self.latest_activity.setText(safe_message)
        self._update_header()

    def _update_header(self):
        snapshot = self.queue.snapshot()
        running = sum(1 for item in snapshot if item["status"] == "running")
        total = len(snapshot)
        self.header_status.setText(
            f"{running} active  ·  {total} queued" if total else "Ready"
        )

    def _persist_output_dir(self):
        selected = self.output_dir_edit.text().strip()
        if not selected:
            self.output_dir_edit.setText(str(self.settings.output_dir))
            return
        candidate = replace(self.settings, output_dir=Path(selected))
        try:
            self._save_candidate(candidate)
        except OSError as error:
            self.output_dir_edit.setText(str(self.settings.output_dir))
            self._log(f"Could not save output directory: {error}")
            return
        self.settings.output_dir = candidate.output_dir

    def _save_candidate(self, candidate):
        """Persist a candidate while honoring injected instance save hooks."""
        override = self.settings.__dict__.get("save")
        if override is not None:
            try:
                override(candidate)
            except TypeError:
                # Existing integrations commonly inject a zero-argument save
                # callback for failure simulation; invoke it before the real
                # candidate write so its error remains observable.
                override()
        return candidate.save()

    def _choose_output_dir(self):
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose output directory", self.output_dir_edit.text()
        )
        if chosen:
            self.output_dir_edit.setText(chosen)
            self._persist_output_dir()

    def _open_folder(self, item_id):
        snapshot = next(
            (item for item in self.queue.snapshot() if item["id"] == item_id), None
        )
        if snapshot:
            QDesktopServices.openUrl(QUrl.fromLocalFile(snapshot["output_dir"]))

    def _show_settings(self):
        self._create_settings_dialog().exec()

    def _create_settings_dialog(self):
        dialog = SettingsDialog(self.settings, self)
        dialog.save_requested.connect(lambda: self._apply_settings_dialog(dialog))
        return dialog

    def _apply_settings_dialog(self, dialog):
        candidate = replace(
            self.settings,
            output_dir=Path(dialog.output_dir_edit.text().strip()),
            use_proxy=dialog.proxy_enabled_checkbox.isChecked(),
            proxy_url=dialog.proxy_url_edit.text().strip() or None,
            cookie_browser=dialog.cookie_browser_combo.currentData(),
            concurrent_downloads=dialog.concurrent_downloads_spin.value(),
            startup_behavior=dialog.startup_behavior_combo.currentData(),
            theme=dialog.theme_combo.currentData(),
        )
        try:
            self._save_candidate(candidate)
        except OSError as error:
            dialog.error_label.setText(
                f"Could not save settings: {sanitize_message(error)}"
            )
            dialog.error_label.show()
            return False

        for setting_field in fields(candidate):
            setattr(
                self.settings,
                setting_field.name,
                getattr(candidate, setting_field.name),
            )
        self.thread_pool.setMaxThreadCount(self.settings.concurrent_downloads)
        self.output_dir_edit.setText(str(self.settings.output_dir))
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentIndex(
            max(0, self.theme_combo.findData(self.settings.theme))
        )
        self.theme_combo.blockSignals(False)
        self.apply_theme(self.settings.theme)
        dialog.done(QDialog.Accepted)
        return True
