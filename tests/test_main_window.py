from pathlib import Path

import pytest

from desktop_app.models import DownloadEvent, DownloadResult
from desktop_app.settings import AppSettings

pytest.importorskip("PySide6")
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

from desktop_app.main_window import MainWindow, WorkerSignals


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


def test_retry_failed_item_requeues_it(qtbot, tmp_path):
    window = _window(qtbot, tmp_path, FailingService())
    window.add_urls("https://example.test/a")
    item_id = window.queue.snapshot()[0]["id"]
    window.start_item(item_id)
    qtbot.waitUntil(lambda: window.queue.snapshot()[0]["status"] == "failed")

    window.retry_item(item_id)

    assert window.queue.snapshot()[0]["status"] == "queued"
    assert window.queue.snapshot()[0]["error"] is None


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


def test_cancel_retry_discards_late_events_from_old_worker(qtbot, tmp_path):
    import threading

    class RaceService:
        def __init__(self):
            self.started = threading.Event()
            self.calls = 0

        def download(self, request, emit, cancel=None):
            self.calls += 1
            if self.calls == 1:
                self.started.set()
                while not cancel.is_set():
                    self.started.wait(0.005)
                # This event belongs to the cancelled run and must be ignored.
                emit(DownloadEvent("progress", percent=99))
                return DownloadResult(False, None, None, "cancelled", "cancelled")
            emit(DownloadEvent("progress", percent=10))
            return DownloadResult(True, "new.mp4", "new", None, None)

    service = RaceService()
    window = _window(qtbot, tmp_path, service)
    window.add_urls("https://example.test/a")
    item_id = window.queue.snapshot()[0]["id"]
    window.start_item(item_id)
    qtbot.waitUntil(service.started.is_set)
    window.cancel_item(item_id)
    window.retry_item(item_id)
    window.start_item(item_id)
    qtbot.waitUntil(lambda: window.queue.snapshot()[0]["status"] == "success")

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
