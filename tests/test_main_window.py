from pathlib import Path

import pytest
import yt_dlp

from desktop_app.download_core import DownloadService
from desktop_app.models import DownloadEvent, DownloadResult
from desktop_app.settings import AppSettings

pytest.importorskip("PySide6")
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

from desktop_app.main_window import DownloadWorker, MainWindow, WorkerSignals


class FakeService:
    def __init__(self):
        self.calls = []

    def download(self, request, emit, cancel=None):
        self.calls.append(request)
        emit(DownloadEvent("metadata", title="Demo"))
        emit(DownloadEvent("progress", percent=42.0, speed=1000, eta=3))
        emit(DownloadEvent("finished", filename="demo.mp4"))
        return DownloadResult(True, "demo.mp4", "Demo", None, None)


class FailingService:
    def download(self, request, emit, cancel=None):
        emit(DownloadEvent("failed", message="network down", error_code="download_failed"))
        return DownloadResult(False, None, None, "download_failed", "network down")


def _window(qtbot, tmp_path, service=None):
    window = MainWindow(AppSettings(output_dir=tmp_path), service or FakeService())
    qtbot.addWidget(window)
    window.show()
    return window


def test_multiline_paste_creates_one_row_per_url(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window.add_urls("https://example.test/a\n\n https://example.test/b ")

    assert window.queue_table.rowCount() == 2
    assert len(window.queue.snapshot()) == 2


def test_add_urls_normalizes_markdown_and_rejects_invalid_lines_with_feedback(qtbot, tmp_path):
    """Catch malformed input entering the queue or Markdown leaking into cards."""
    window = _window(qtbot, tmp_path)

    window.add_urls(
        "[Demo](HTTPS://Example.Test/video?a=1\\&b=2)\n"
        "ftp://example.test/file\n"
        "not a url"
    )

    snapshot = window.queue.snapshot()
    assert len(snapshot) == 1
    assert snapshot[0]["url"] == "https://example.test/video?a=1&b=2"
    assert "example.test" in window.queue_list.card_at(0).meta_label.text()
    assert "invalid" in window.activity_log.toPlainText().lower()
    assert "http(s)" in window.activity_log.toPlainText().lower()


def test_start_item_marks_running_and_worker_updates_progress(qtbot, tmp_path):
    service = FakeService()
    window = _window(qtbot, tmp_path, service)
    window.add_urls("https://example.test/a")
    item_id = window.queue.snapshot()[0]["id"]

    window.start_item(item_id)
    qtbot.waitUntil(lambda: window.queue.snapshot()[0]["status"] == "success")

    assert service.calls
    assert window.queue_table.cellWidget(0, window.PROGRESS_COLUMN).value() == 42


def test_cancel_item_sets_cancelled_status(qtbot, tmp_path):
    class BlockingService:
        def download(self, request, emit, cancel=None):
            emit(DownloadEvent("progress", percent=10))
            return DownloadResult(False, None, None, "cancelled", "Download cancelled")

    window = _window(qtbot, tmp_path, BlockingService())
    window.add_urls("https://example.test/a")
    item_id = window.queue.snapshot()[0]["id"]
    window.start_item(item_id)
    window.cancel_item(item_id)

    assert window.queue.snapshot()[0]["status"] == "cancelled"


def test_retry_failed_item_starts_a_fresh_download(qtbot, tmp_path):
    class RetryService:
        def __init__(self):
            self.calls = 0
            self.requests = []

        def download(self, request, emit, cancel=None):
            self.calls += 1
            self.requests.append(request)
            if self.calls == 1:
                emit(DownloadEvent("failed", message="network down", error_code="download_failed"))
                return DownloadResult(False, None, None, "download_failed", "network down")
            return DownloadResult(True, "retried.mp4", "retried", None, None)

    service = RetryService()
    window = _window(qtbot, tmp_path, service)
    window.add_urls("https://example.test/a")
    item_id = window.queue.snapshot()[0]["id"]
    window.start_item(item_id)
    qtbot.waitUntil(lambda: window.queue.snapshot()[0]["status"] == "failed")

    window.settings.output_dir = tmp_path / "new-output"
    window.settings.use_proxy = True
    window.settings.proxy_url = "socks5://127.0.0.1:1080"
    window.settings.cookie_browser = "firefox"
    window.settings.format_selector = "best"
    window.format_combo.setCurrentIndex(window.format_combo.findData("best"))

    window.retry_item(item_id)

    qtbot.waitUntil(lambda: window.queue.snapshot()[0]["status"] == "success")
    assert service.calls == 2
    assert service.requests[1].output_dir == tmp_path / "new-output"
    assert service.requests[1].use_proxy is True
    assert service.requests[1].proxy_url == "socks5://127.0.0.1:1080"
    assert service.requests[1].cookie_browser == "firefox"
    assert service.requests[1].format_selector == "best"


def test_retry_uses_the_current_visible_format_selector(qtbot, tmp_path):
    class RetryService:
        def __init__(self):
            self.requests = []

        def download(self, request, emit, cancel=None):
            self.requests.append(request)
            if len(self.requests) == 1:
                return DownloadResult(False, None, None, "download_failed", "network down")
            return DownloadResult(True, "retried.mp4", "retried", None, None)

    service = RetryService()
    settings = AppSettings(output_dir=tmp_path, format_selector="best")
    window = MainWindow(settings, service)
    qtbot.addWidget(window)
    window.show()
    window.add_urls("https://example.test/a")
    item_id = window.queue.snapshot()[0]["id"]
    window.start_item(item_id)
    qtbot.waitUntil(lambda: window.queue.snapshot()[0]["status"] == "failed")

    window.format_combo.setCurrentIndex(window.format_combo.findData("bv*+ba/b"))
    window.retry_item(item_id)

    qtbot.waitUntil(lambda: window.queue.snapshot()[0]["status"] == "success")
    assert service.requests[0].format_selector == "best"
    assert service.requests[1].format_selector == "bv*+ba/b"


def test_settings_dialog_saves_download_preferences_and_updates_window(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    window = _window(qtbot, tmp_path)
    dialog = window._create_settings_dialog()
    qtbot.addWidget(dialog)
    selected_output = tmp_path / "chosen-output"

    dialog.output_dir_edit.setText(str(selected_output))
    dialog.proxy_enabled_checkbox.setChecked(True)
    dialog.proxy_url_edit.setText("socks5://127.0.0.1:1080")
    dialog.cookie_browser_combo.setCurrentText("Firefox")
    dialog.concurrent_downloads_spin.setValue(3)
    dialog.startup_behavior_combo.setCurrentText("Start minimized")
    dialog.theme_combo.setCurrentText("Light")
    dialog.accept()

    assert window.settings.output_dir == selected_output
    assert window.settings.use_proxy is True
    assert window.settings.proxy_url == "socks5://127.0.0.1:1080"
    assert window.settings.cookie_browser == "firefox"
    assert window.settings.concurrent_downloads == 3
    assert window.settings.startup_behavior == "minimized"
    assert window.settings.theme == "light"
    assert window.thread_pool.maxThreadCount() == 3
    assert window.output_dir_edit.text() == str(selected_output)
    assert window.theme_combo.currentText() == "Light"
    saved = AppSettings.load()
    assert saved.output_dir == selected_output
    assert saved.proxy_url == "socks5://127.0.0.1:1080"


def test_browse_output_directory_persists_selection(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    window = _window(qtbot, tmp_path)
    selected_output = tmp_path / "selected"
    monkeypatch.setattr(
        "desktop_app.main_window.QFileDialog.getExistingDirectory",
        lambda *_: str(selected_output),
    )

    window._choose_output_dir()

    assert window.output_dir_edit.text() == str(selected_output)
    assert AppSettings.load().output_dir == selected_output


def test_worker_events_are_delivered_on_gui_thread(qtbot, tmp_path):
    window = _window(qtbot, tmp_path, FakeService())
    received_threads = []
    original = window._handle_event

    def record_thread(item_id, event):
        received_threads.append(QThread.currentThread())
        original(item_id, event)

    # start_item must connect through a QObject receiver; a lambda connection
    # runs this callback on the worker thread and mutates widgets unsafely.
    window._handle_event = record_thread
    window.add_urls("https://example.test/a")
    window.start_item(window.queue.snapshot()[0]["id"])
    qtbot.waitUntil(lambda: window.queue.snapshot()[0]["status"] == "success")

    assert received_threads
    assert all(thread == QApplication.instance().thread() for thread in received_threads)


def test_cancel_retry_waits_for_old_worker_before_starting_replacement(qtbot, tmp_path):
    import threading

    class RaceService:
        def __init__(self):
            self.started = threading.Event()
            self.release_old_worker = threading.Event()
            self.calls = 0
            self.active_calls = 0
            self.max_active_calls = 0

        def download(self, request, emit, cancel=None):
            self.calls += 1
            self.active_calls += 1
            self.max_active_calls = max(self.max_active_calls, self.active_calls)
            try:
                if self.calls == 1:
                    self.started.set()
                    self.release_old_worker.wait()
                    return DownloadResult(False, None, None, "cancelled", "cancelled")
                emit(DownloadEvent("progress", percent=10))
                return DownloadResult(True, "new.mp4", "new", None, None)
            finally:
                self.active_calls -= 1

    service = RaceService()
    window = _window(qtbot, tmp_path, service)
    window.add_urls("https://example.test/a")
    item_id = window.queue.snapshot()[0]["id"]
    window.start_item(item_id)
    qtbot.waitUntil(service.started.is_set)
    window.cancel_item(item_id)
    window.retry_item(item_id)

    qtbot.wait(100)
    assert service.calls == 1
    assert service.max_active_calls == 1

    service.release_old_worker.set()
    qtbot.waitUntil(lambda: window.queue.snapshot()[0]["status"] == "success")

    assert service.calls == 2
    assert service.max_active_calls == 1
    assert window.queue_table.cellWidget(0, window.PROGRESS_COLUMN).value() == 10


def test_worker_signal_api_validates_typed_payloads(qtbot):
    signals = WorkerSignals()
    received = []
    signals.connect_event(received.append)
    event = DownloadEvent("progress", percent=25)

    signals.emit_event(event)

    assert received == [event]
    with pytest.raises(TypeError, match="DownloadEvent"):
        signals.emit_event("not an event")
    with pytest.raises(TypeError, match="DownloadResult"):
        signals.emit_finished("not a result")


def test_worker_signal_api_has_no_public_raw_emit_bypass():
    signals = WorkerSignals()

    # QObject itself has an event(QEvent) method; it must not be an emit-able
    # public signal carrying arbitrary Python values.
    assert not hasattr(signals.event, "emit")
    assert not hasattr(signals, "finished")
    assert not hasattr(signals, "failed")
    assert callable(signals.connect_event)
    assert callable(signals.connect_finished)


def test_gui_worker_succeeds_after_ytdlp_failure_via_shared_fallback(qtbot, tmp_path):
    """Catch the desktop app bypassing the service-owned HTML fallback."""
    class UnsupportedBackend:
        def build_options(self, request, format_selector, progress_hook, logger):
            return {"format": format_selector, "progress_hooks": [progress_hook]}

        def extract_info(self, url, options):
            raise yt_dlp.utils.DownloadError("Unsupported URL: no suitable extractor")

        def download(self, url, options):
            raise AssertionError("download must not run after failed extraction")

    class EmbeddedFallback:
        def attempt(self, request, emit, cancel, download_manifest):
            filename = str(tmp_path / "embedded.mp4")
            emit(DownloadEvent("finished", filename=filename))
            return DownloadResult(True, filename, "Embedded", None, None)

    service = DownloadService(UnsupportedBackend(), fallback=EmbeddedFallback())
    window = _window(qtbot, tmp_path, service)
    window.add_urls("https://example.test/watch")
    item_id = window.queue.snapshot()[0]["id"]

    window.start_item(item_id)
    qtbot.waitUntil(lambda: window.queue.snapshot()[0]["status"] == "success")

    assert window.queue.snapshot()[0]["filename"] == str(tmp_path / "embedded.mp4")


def test_worker_unexpected_exception_is_sanitized_before_failed_signal(tmp_path):
    """Catch raw worker exceptions bypassing service event sanitization."""
    class CrashingService:
        def download(self, request, emit, cancel=None):
            raise RuntimeError(
                "alice p%40ssword http://alice:p%40ssword@proxy.example "
                "token=worker-token"
            )

    from desktop_app.models import DownloadRequest

    worker = DownloadWorker(
        CrashingService(),
        DownloadRequest(
            "https://example.test/video",
            tmp_path,
            use_proxy=True,
            proxy_url="http://alice:p%40ssword@proxy.example",
        ),
    )
    failures = []
    worker.signals.connect_failed(failures.append)

    worker.run()

    assert len(failures) == 1
    for secret in ("alice", "p%40ssword", "worker-token"):
        assert secret not in failures[0]
    assert "http://proxy.example" in failures[0]
