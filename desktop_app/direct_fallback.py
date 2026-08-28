"""Cancellable HTML and direct-media fallback owned by ``DownloadService``."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .models import DownloadEvent, DownloadRequest, DownloadResult


_DIRECT_EXTENSIONS = (".mp4", ".mkv", ".avi", ".mov", ".flv", ".webm", ".m4v", ".ts")
_MANIFEST_EXTENSIONS = (".m3u8", ".mpd")


class DirectMediaFallback:
    """Try direct files and media embedded in an ordinary HTML page."""

    def __init__(self, get: Callable | None = None) -> None:
        if get is None:
            import requests

            get = requests.get
        self._get = get

    def attempt(self, request, emit, cancel, download_manifest):
        if _is_cancelled(cancel):
            return _cancelled(emit)

        path = urlsplit(request.url).path.lower()
        if path.endswith(_MANIFEST_EXTENSIONS):
            emit(DownloadEvent("log", message="Trying the direct streaming manifest."))
            return download_manifest(request.url)
        if path.endswith(_DIRECT_EXTENSIONS):
            return self._download_direct(request.url, request, emit, cancel)

        response = self._request(request.url, request, stream=False)
        try:
            _ensure_success(response)
            content_type = response.headers.get("content-type", "").lower()
            if content_type and not content_type.startswith("text/html"):
                return None
            from universal_video_downloader import extract_video_urls_from_html

            candidates = extract_video_urls_from_html(response.text, request.url)
        finally:
            _close(response)

        if not candidates:
            return None
        emit(
            DownloadEvent(
                "log", message=f"Found {len(candidates)} embedded media link(s)."
            )
        )
        for candidate in candidates:
            if _is_cancelled(cancel):
                return _cancelled(emit)
            candidate_path = urlsplit(candidate).path.lower()
            if candidate_path.endswith(_MANIFEST_EXTENSIONS):
                result = download_manifest(candidate)
            elif candidate_path.endswith(_DIRECT_EXTENSIONS):
                result = self._download_direct(candidate, request, emit, cancel)
            else:
                continue
            if result and result.success:
                return result
            if result and result.error_code == "cancelled":
                return result
        return None

    def _request(self, url, request, *, stream):
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": request.url,
        }
        kwargs = {"headers": headers, "timeout": 30}
        if stream:
            kwargs["stream"] = True
        if request.use_proxy and request.proxy_url:
            kwargs["proxies"] = {
                "http": request.proxy_url,
                "https": request.proxy_url,
            }
        return self._get(url, **kwargs)

    def _download_direct(self, url, request, emit, cancel):
        from universal_video_downloader import sanitize_filename

        parsed = urlsplit(url)
        filename = sanitize_filename(Path(unquote(parsed.path)).name)
        if not filename:
            suffix = Path(parsed.path).suffix or ".mp4"
            filename = f"video_{request.request_id}{suffix}"
        output_dir, filename = _requested_destination(url, request, filename)
        output_dir.mkdir(parents=True, exist_ok=True)
        final_path, part_path, handle = _reserve_destination(output_dir, filename)
        response = None
        try:
            emit(DownloadEvent("log", message=f"Downloading direct media: {filename}"))
            response = self._request(url, request, stream=True)
            _ensure_success(response)
            expected = int(response.headers.get("content-length", 0) or 0)
            downloaded = 0
            with handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if _is_cancelled(cancel):
                        return _cancelled(emit)
                    if not chunk:
                        continue
                    handle.write(chunk)
                    downloaded += len(chunk)
                    emit(
                        DownloadEvent(
                            "progress",
                            percent=downloaded / expected * 100 if expected else None,
                            filename=str(part_path),
                        )
                    )
                if _is_cancelled(cancel):
                    return _cancelled(emit)
                handle.flush()
                os.fsync(handle.fileno())
            if expected and downloaded != expected:
                raise OSError(
                    f"Direct download incomplete: expected {expected} bytes, received {downloaded}."
                )
            final_path = _publish_without_overwrite(part_path, final_path)
            emit(DownloadEvent("finished", filename=str(final_path)))
            return DownloadResult(True, str(final_path), final_path.stem, None, None)
        finally:
            if response is not None:
                _close(response)
            try:
                if not handle.closed:
                    handle.close()
            finally:
                part_path.unlink(missing_ok=True)


def _reserve_destination(output_dir: Path, filename: str):
    source = Path(filename)
    stem = source.stem or "video"
    suffix = source.suffix
    index = 0
    while True:
        candidate_name = filename if index == 0 else f"{stem}_{index}{suffix}"
        final_path = output_dir / candidate_name
        part_path = output_dir / f"{candidate_name}.part"
        index += 1
        if final_path.exists():
            continue
        try:
            handle = part_path.open("xb")
        except FileExistsError:
            continue
        return final_path, part_path, handle


def _requested_destination(url: str, request: DownloadRequest, fallback_name: str):
    """Resolve an optional yt-dlp template without evaluating arbitrary code."""
    from universal_video_downloader import sanitize_filename

    template = request.output_template
    if not template:
        return Path(request.output_dir), fallback_name
    suffix = Path(urlsplit(url).path).suffix.lstrip(".") or "mp4"
    stem = Path(fallback_name).stem or "video"
    rendered = re.sub(
        r"%\((ext|title|id)\)(?:\.\d+)?[A-Za-z]*",
        lambda match: {
            "ext": suffix,
            "title": sanitize_filename(stem),
            "id": request.request_id,
        }[match.group(1)],
        str(template),
    )
    desired = Path(rendered)
    if not desired.is_absolute():
        desired = Path(request.output_dir) / desired
    return desired.parent, desired.name


def _publish_without_overwrite(part_path: Path, final_path: Path) -> Path:
    source = final_path
    stem = source.stem
    suffix = source.suffix
    index = 0
    while True:
        candidate = final_path if index == 0 else final_path.with_name(f"{stem}_{index}{suffix}")
        index += 1
        try:
            os.link(part_path, candidate)
        except FileExistsError:
            continue
        except OSError as error:
            raise OSError(
                "The output filesystem does not support atomic no-overwrite publication."
            ) from error
        part_path.unlink()
        return candidate


def _is_cancelled(cancel) -> bool:
    if not cancel:
        return False
    try:
        return bool(cancel())
    except TypeError:
        return bool(getattr(cancel, "is_set", lambda: False)())


def _cancelled(emit) -> DownloadResult:
    message = "Download cancelled"
    emit(DownloadEvent("cancelled", message=message, error_code="cancelled"))
    return DownloadResult(False, None, None, "cancelled", message)


def _close(response) -> None:
    close = getattr(response, "close", None)
    if callable(close):
        close()


def _ensure_success(response) -> None:
    """Support both requests responses and tiny injected test doubles."""
    raise_for_status = getattr(response, "raise_for_status", None)
    if callable(raise_for_status):
        raise_for_status()
        return
    status = int(getattr(response, "status_code", 200))
    if status >= 400:
        raise OSError(f"HTTP error {status}")
