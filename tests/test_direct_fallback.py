from pathlib import Path

import pytest

from desktop_app.models import DownloadRequest, DownloadResult


class FakeResponse:
    def __init__(self, *, body=b"", text="", content_type="video/mp4", fail_after=None):
        self.status_code = 200
        self._body = body
        self.text = text
        self.headers = {
            "content-type": content_type,
            "content-length": str(len(body)) if body else "0",
        }
        self.fail_after = fail_after
        self.closed = False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        midpoint = max(1, len(self._body) // 2)
        chunks = (self._body[:midpoint], self._body[midpoint:])
        for index, chunk in enumerate(chunks):
            if self.fail_after is not None and index >= self.fail_after:
                raise OSError("transport dropped")
            if chunk:
                yield chunk

    def close(self):
        self.closed = True


def _fallback(get):
    from desktop_app.direct_fallback import DirectMediaFallback

    return DirectMediaFallback(get=get)


def test_direct_download_uses_part_and_never_overwrites_existing_file(tmp_path):
    """Catch a partial/colliding transfer writing under the final filename."""
    existing = tmp_path / "clip.mp4"
    existing.write_bytes(b"original")
    response = FakeResponse(body=b"abcdef")
    events = []

    result = _fallback(lambda *args, **kwargs: response).attempt(
        DownloadRequest("https://cdn.example/clip.mp4", tmp_path),
        events.append,
        lambda: False,
        lambda url: pytest.fail("direct files must not recurse into yt-dlp"),
    )

    assert result is not None and result.success is True
    output = Path(result.filename)
    assert output != existing
    assert output.read_bytes() == b"abcdef"
    assert existing.read_bytes() == b"original"
    assert list(tmp_path.glob("*.part")) == []
    assert [event.kind for event in events] == ["log", "progress", "progress", "finished"]
    assert response.closed is True


def test_direct_download_honors_explicit_batch_output_template(tmp_path):
    """Catch fallback success being written outside the batch-request target."""
    response = FakeResponse(body=b"batch-data")
    result = _fallback(lambda *args, **kwargs: response).attempt(
        DownloadRequest(
            "https://cdn.example/clip.mp4",
            tmp_path,
            output_template=str(tmp_path / "chapter" / "01_clip.%(ext)s"),
        ),
        lambda event: None,
        lambda: False,
        lambda url: pytest.fail("direct files must use the atomic direct path"),
    )

    assert result.success is True
    assert Path(result.filename) == tmp_path / "chapter" / "01_clip.mp4"
    assert Path(result.filename).read_bytes() == b"batch-data"


def test_direct_download_removes_partial_after_transport_failure(tmp_path):
    """Catch a failed stream leaving a corrupt final-looking or .part file."""
    response = FakeResponse(body=b"abcdef", fail_after=1)

    with pytest.raises(OSError, match="transport dropped"):
        _fallback(lambda *args, **kwargs: response).attempt(
            DownloadRequest("https://cdn.example/clip.mp4", tmp_path),
            lambda event: None,
            lambda: False,
            lambda url: DownloadResult(False, None, None, "download_failed", "unused"),
        )

    assert list(tmp_path.iterdir()) == []
    assert response.closed is True


def test_direct_download_removes_partial_and_reports_cancelled_mid_stream(tmp_path):
    """Catch cancellation being noticed only after a final file is published."""
    state = {"cancelled": False}

    class CancellingResponse(FakeResponse):
        def iter_content(self, chunk_size):
            yield b"abc"
            state["cancelled"] = True
            yield b"def"

    events = []
    result = _fallback(lambda *args, **kwargs: CancellingResponse(body=b"abcdef")).attempt(
        DownloadRequest("https://cdn.example/clip.mp4", tmp_path),
        events.append,
        lambda: state["cancelled"],
        lambda url: pytest.fail("direct files must not recurse into yt-dlp"),
    )

    assert result is not None and result.error_code == "cancelled"
    assert events[-1].kind == "cancelled"
    assert list(tmp_path.iterdir()) == []


def test_direct_download_rejects_truncated_content_and_cleans_partial(tmp_path):
    """Catch a short HTTP body being atomically promoted as complete."""
    response = FakeResponse(body=b"abc")
    response.headers["content-length"] = "10"

    with pytest.raises(OSError, match="incomplete"):
        _fallback(lambda *args, **kwargs: response).attempt(
            DownloadRequest("https://cdn.example/clip.mp4", tmp_path),
            lambda event: None,
            lambda: False,
            lambda url: pytest.fail("direct files must not recurse into yt-dlp"),
        )

    assert list(tmp_path.iterdir()) == []


def test_html_fallback_discovers_and_downloads_embedded_direct_media(tmp_path):
    """Catch HTML extraction existing only in the legacy wrapper."""
    page = FakeResponse(
        text='<video><source src="/media/embedded.mp4"></video>',
        content_type="text/html; charset=utf-8",
    )
    media = FakeResponse(body=b"media-bytes")
    requested_urls = []

    def get(url, **kwargs):
        requested_urls.append(url)
        return page if url.endswith("/watch") else media

    result = _fallback(get).attempt(
        DownloadRequest("https://example.test/watch", tmp_path),
        lambda event: None,
        lambda: False,
        lambda url: pytest.fail("an MP4 candidate should use the atomic direct path"),
    )

    assert result is not None and result.success is True
    assert Path(result.filename).read_bytes() == b"media-bytes"
    assert requested_urls == [
        "https://example.test/watch",
        "https://example.test/media/embedded.mp4",
    ]


def test_html_fallback_routes_manifest_to_nonrecursive_media_callback(tmp_path):
    """Catch manifest fallback recursively restarting HTML orchestration."""
    page = FakeResponse(
        text='<video><source src="/media/stream.m3u8"></video>',
        content_type="text/html",
    )
    called = []

    def download_manifest(url):
        called.append(url)
        return DownloadResult(True, "manifest.mp4", "Manifest", None, None)

    result = _fallback(lambda *args, **kwargs: page).attempt(
        DownloadRequest("https://example.test/watch", tmp_path),
        lambda event: None,
        lambda: False,
        download_manifest,
    )

    assert result is not None and result.success is True
    assert called == ["https://example.test/media/stream.m3u8"]
