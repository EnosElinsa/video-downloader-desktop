from pathlib import Path

import yt_dlp

from desktop_app.download_core import DownloadService
from desktop_app.models import DownloadRequest


class FakeBackend:
    def __init__(self, fail_first=False, auth_error=False):
        self.fail_first = fail_first
        self.auth_error = auth_error
        self.options = []
        self.download_calls = 0

    def build_options(self, request, format_selector, progress_hook, logger):
        options = {"format": format_selector, "progress_hooks": [progress_hook]}
        self.options.append(options)
        return options

    def extract_info(self, url, options):
        if self.fail_first and options["format"] == "bv*+ba/b":
            raise yt_dlp.utils.DownloadError("Requested format is not available")
        if self.auth_error:
            raise yt_dlp.utils.DownloadError("Sign in to confirm your age")
        return {"title": "Demo", "duration": 12, "formats": []}

    def download(self, url, options):
        self.download_calls += 1
        hook = options["progress_hooks"][0]
        hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100, "speed": 25, "eta": 2})
        hook({"status": "finished", "filename": "demo.mp4"})
        return "demo.mp4"


def test_service_normalizes_markdown_url_and_emits_events(tmp_path):
    backend = FakeBackend()
    events = []
    result = DownloadService(backend).download(
        DownloadRequest(r"[Demo](example.test/video?a=1\&b=2)", tmp_path), events.append
    )

    assert result.success is True
    assert result.filename == "demo.mp4"
    assert [event.kind for event in events] == ["metadata", "progress", "finished"]
    assert events[0].title == "Demo"
    assert events[1].percent == 50
    assert backend.options[0]["format"] == "bv*+ba/b"


def test_service_retries_format_error_with_best(tmp_path):
    backend = FakeBackend(fail_first=True)
    events = []
    result = DownloadService(backend).download(DownloadRequest("https://example.test/v", tmp_path), events.append)

    assert result.success is True
    assert [options["format"] for options in backend.options] == ["bv*+ba/b", "best"]


def test_service_cancellation_emits_cancelled(tmp_path):
    backend = FakeBackend()
    events = []
    result = DownloadService(backend).download(
        DownloadRequest("https://example.test/v", tmp_path), events.append, cancel=lambda: True
    )

    assert result.success is False
    assert result.error_code == "cancelled"
    assert events[-1].kind == "cancelled"
    assert backend.download_calls == 0


def test_service_classifies_authentication_without_cookie_values(tmp_path):
    backend = FakeBackend(auth_error=True)
    events = []
    result = DownloadService(backend).download(
        DownloadRequest("https://example.test/v", tmp_path, cookie_browser="chrome"), events.append
    )

    assert result.success is False
    assert result.error_code == "auth_required"
    assert events[-1].kind == "failed"
    assert "chrome" not in (result.error_message or "")
