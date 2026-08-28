from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading

import pytest
import yt_dlp

from desktop_app.download_core import DownloadService
from desktop_app.models import DownloadEvent, DownloadRequest, DownloadResult


class FakeBackend:
    def __init__(self, fail_first=False, auth_error=False):
        self.fail_first = fail_first
        self.auth_error = auth_error
        self.options = []
        self.requests = []
        self.download_calls = 0

    def build_options(self, request, format_selector, progress_hook, logger):
        self.requests.append(request)
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


def test_service_redacts_cookie_values_from_authentication_events_and_results(tmp_path):
    class SecretBackend(FakeBackend):
        def extract_info(self, url, options):
            raise yt_dlp.utils.DownloadError(
                'authentication failed: cookies=SESSION_VALUE; '
                'Cookie: session=abc; token=xyz; cookie="quoted-secret"'
            )

    events = []
    result = DownloadService(SecretBackend()).download(
        DownloadRequest("https://example.test/v", tmp_path), events.append
    )

    exposed = " ".join(event.message for event in events) + " " + (result.error_message or "")
    for secret in ("SESSION_VALUE", "abc", "xyz", "quoted-secret"):
        assert secret not in exposed


def test_service_converts_sanitized_ytdlp_diagnostics_to_log_events(tmp_path):
    class LoggingBackend(FakeBackend):
        def extract_info(self, url, options):
            options["logger"].warning("upstream warning Cookie: session=abc; token=xyz")
            return super().extract_info(url, options)

    events = []
    result = DownloadService(LoggingBackend()).download(
        DownloadRequest("https://example.test/v", tmp_path), events.append
    )

    assert result.success is True
    log_events = [event for event in events if event.kind == "log"]
    assert len(log_events) == 1
    assert "upstream warning" in log_events[0].message
    assert "abc" not in log_events[0].message
    assert "xyz" not in log_events[0].message


class NullFallback:
    def __init__(self):
        self.calls = 0

    def attempt(self, request, emit, cancel, download_manifest):
        self.calls += 1
        return None


def test_service_runs_injected_embedded_media_fallback_once_after_ytdlp_failure(tmp_path):
    """Catch GUI/CLI divergence or recursive fallback orchestration."""
    class UnsupportedBackend(FakeBackend):
        def extract_info(self, url, options):
            raise yt_dlp.utils.DownloadError("Unsupported URL: no suitable extractor")

    class SuccessfulFallback:
        def __init__(self):
            self.calls = 0

        def attempt(self, request, emit, cancel, download_manifest):
            self.calls += 1
            emit(DownloadEvent("log", message="Found embedded media"))
            emit(DownloadEvent("finished", filename=str(tmp_path / "embedded.mp4")))
            return DownloadResult(True, str(tmp_path / "embedded.mp4"), "Embedded", None, None)

    backend = UnsupportedBackend()
    fallback = SuccessfulFallback()
    events = []

    result = DownloadService(backend, fallback=fallback).download(
        DownloadRequest("https://example.test/watch", tmp_path), events.append
    )

    assert result.success is True
    assert result.filename == str(tmp_path / "embedded.mp4")
    assert fallback.calls == 1
    assert backend.download_calls == 0
    assert [event.kind for event in events] == ["log", "finished"]


def test_service_runs_real_html_media_fallback_after_ytdlp_failure(tmp_path):
    """Catch a service seam that is tested only with a success stub, not HTML media."""
    from desktop_app.direct_fallback import DirectMediaFallback

    class UnsupportedBackend:
        def build_options(self, request, format_selector, progress_hook, logger):
            return {"format": format_selector, "progress_hooks": [progress_hook]}

        def extract_info(self, url, options):
            raise yt_dlp.utils.DownloadError("Unsupported URL: no suitable extractor")

        def download(self, url, options):
            raise AssertionError("the unsupported page must use the injected fallback")

    page = type(
        "Response",
        (),
        {
            "status_code": 200,
            "headers": {"content-type": "text/html"},
            "text": '<video><source src="/media/embedded.mp4"></video>',
            "raise_for_status": lambda self: None,
            "close": lambda self: None,
        },
    )()
    media = type(
        "Response",
        (),
        {
            "status_code": 200,
            "headers": {"content-length": "8", "content-type": "video/mp4"},
            "iter_content": lambda self, chunk_size: iter((b"embedded",)),
            "raise_for_status": lambda self: None,
            "close": lambda self: None,
        },
    )()

    def get(url, **kwargs):
        return page if url.endswith("/watch") else media

    result = DownloadService(
        UnsupportedBackend(), fallback=DirectMediaFallback(get=get)
    ).download(DownloadRequest("https://example.test/watch", tmp_path), lambda event: None)

    assert result.success is True
    assert Path(result.filename).read_bytes() == b"embedded"


def test_same_tick_concurrent_requests_receive_distinct_stable_templates(tmp_path):
    """Catch two workers targeting the same whole-second output name."""
    class ConcurrentBackend:
        def __init__(self):
            self.barrier = threading.Barrier(2)
            self.templates = []
            self.lock = threading.Lock()

        def build_options(self, request, format_selector, progress_hook, logger):
            with self.lock:
                self.templates.append(request.output_template)
            return {"format": format_selector, "progress_hooks": [progress_hook]}

        def extract_info(self, url, options):
            self.barrier.wait(timeout=3)
            return {"title": "Concurrent"}

        def download(self, url, options):
            return f"{threading.get_ident()}.mp4"

    backend = ConcurrentBackend()
    service = DownloadService(backend, fallback=NullFallback())
    requests = [
        DownloadRequest("https://example.test/a", tmp_path),
        DownloadRequest("https://example.test/b", tmp_path),
    ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda request: service.download(request, lambda event: None), requests))

    assert all(result.success for result in results)
    assert len(set(backend.templates)) == 2
    assert all(template and str(tmp_path) in template for template in backend.templates)


def test_format_retry_reuses_one_request_template(tmp_path):
    """Catch a retry producing a second unrelated output target."""
    backend = FakeBackend(fail_first=True)

    result = DownloadService(backend, fallback=NullFallback()).download(
        DownloadRequest("https://example.test/v", tmp_path), lambda event: None
    )

    assert result.success is True
    assert len(backend.requests) == 2
    assert backend.requests[0].output_template == backend.requests[1].output_template
    assert backend.requests[0].output_template is not None


@pytest.mark.parametrize(
    ("message", "expected_code"),
    [
        ("Requested format is not available", "format_unavailable"),
        ("Sign in to confirm; login required", "auth_required"),
        ("Temporary failure in name resolution", "network_error"),
        ("ProxyError: 407 Proxy Authentication Required", "proxy_error"),
        ("ffmpeg not found. Please install ffmpeg", "ffmpeg_missing"),
        ("Unsupported URL: no suitable extractor", "unsupported_site"),
        ("unexpected extractor crash", "download_failed"),
    ],
)
def test_service_classifies_every_release_error_family(tmp_path, message, expected_code):
    """Catch actionable failures collapsing back into generic download_failed."""
    class ErrorBackend(FakeBackend):
        def extract_info(self, url, options):
            raise RuntimeError(message)

    result = DownloadService(ErrorBackend(), fallback=NullFallback()).download(
        DownloadRequest("https://example.test/v", tmp_path), lambda event: None
    )

    assert result.error_code == expected_code


@pytest.mark.parametrize("url", ["", "ftp://example.test/video", "https:///missing-host", "not a url"])
def test_service_rejects_invalid_http_input_before_backends(tmp_path, url):
    """Catch invalid input reaching yt-dlp or the network fallback."""
    backend = FakeBackend()
    fallback = NullFallback()

    result = DownloadService(backend, fallback=fallback).download(
        DownloadRequest(url, tmp_path), lambda event: None
    )

    assert result.error_code == "invalid_url"
    assert backend.options == []
    assert fallback.calls == 0


def test_service_redacts_proxy_userinfo_and_configured_credentials_everywhere(tmp_path):
    """Catch proxy credentials escaping through logger, failure event, or result."""
    class SecretBackend(FakeBackend):
        def extract_info(self, url, options):
            options["logger"].warning(
                "proxy http://alice:p%40ssword@proxy.example token=logger-token"
            )
            raise RuntimeError(
                "worker for alice failed with p%40ssword at "
                "http://alice:p%40ssword@proxy.example session=worker-session"
            )

    events = []
    request = DownloadRequest(
        "https://example.test/v",
        tmp_path,
        use_proxy=True,
        proxy_url="http://alice:p%40ssword@proxy.example",
    )

    result = DownloadService(SecretBackend(), fallback=NullFallback()).download(request, events.append)

    exposed = " ".join(event.message for event in events) + " " + (result.error_message or "")
    for secret in ("alice", "p%40ssword", "logger-token", "worker-session"):
        assert secret not in exposed
    assert "http://proxy.example" in exposed


def test_service_redacts_success_result_fields_before_ui_consumes_them(tmp_path):
    """Catch a successful title/path bypassing the typed result scrubber."""
    class SecretSuccessBackend(FakeBackend):
        def extract_info(self, url, options):
            return {"title": "clip-secret-user"}

        def download(self, url, options):
            return "clip-secret-user.mp4"

    request = DownloadRequest(
        "https://example.test/v",
        tmp_path,
        proxy_url="http://secret-user:secret-pass@proxy.example",
        use_proxy=True,
    )
    result = DownloadService(SecretSuccessBackend()).download(request, lambda event: None)

    assert "secret-user" not in (result.title or "")
    assert "secret-user" not in (result.filename or "")


def test_secret_scrubber_removes_complete_authorization_header_values():
    """Catch bearer credentials left behind after redacting only the header key."""
    from desktop_app.security import sanitize_message

    message = sanitize_message("Authorization: Bearer super-secret-token")

    assert "super-secret-token" not in message
    assert "Authorization=<redacted>" in message


def test_service_owns_rockstar_candidate_orchestration(tmp_path):
    """Catch the legacy wrapper becoming a second orchestration layer."""
    class CapturingBackend(FakeBackend):
        def __init__(self):
            super().__init__()
            self.urls = []

        def extract_info(self, url, options):
            self.urls.append(url)
            return super().extract_info(url, options)

    backend = CapturingBackend()
    result = DownloadService(backend, fallback=NullFallback()).download(
        DownloadRequest(
            "https://www.rockstargames.com/videos/rk721912?resolution=2160p",
            tmp_path,
        ),
        lambda event: None,
    )

    assert result.success is True
    assert backend.urls == [
        "https://videos-rockstargames-com.akamaized.net/v4/rk721912/flv/en-us-2160p.mp4"
    ]
