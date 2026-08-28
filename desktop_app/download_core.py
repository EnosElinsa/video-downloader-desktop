"""Qt-free, injectable download orchestration."""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Callable, Protocol, Any

from .models import DownloadEvent, DownloadRequest, DownloadResult


def bundled_ffmpeg_path() -> str | None:
    """Return the packaged FFmpeg executable without consulting global PATH."""
    if not getattr(sys, "frozen", False):
        return None

    roots = [Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)), Path(sys.executable).parent]
    for root in roots:
        candidate = root / "ffmpeg.exe"
        if candidate.is_file():
            return str(candidate)
    return None


class YtdlpBackend(Protocol):
    def build_options(self, request: DownloadRequest, format_selector: str,
                      progress_hook: Callable[[dict[str, Any]], None], logger: logging.Logger) -> dict[str, Any]: ...

    def extract_info(self, url: str, options: dict[str, Any]) -> dict[str, Any] | None: ...

    def download(self, url: str, options: dict[str, Any]) -> str | None: ...


class _DefaultYtdlpBackend:
    def build_options(self, request, format_selector, progress_hook, logger):
        from universal_video_downloader import build_ytdlp_options

        options = build_ytdlp_options(
            request.url, str(request.output_dir), request.use_proxy, request.proxy_url,
            format_selector=format_selector, cookie_browser=request.cookie_browser,
            output_template=request.output_template,
        )
        options["progress_hooks"] = [progress_hook]
        ffmpeg_path = bundled_ffmpeg_path()
        if ffmpeg_path:
            options["ffmpeg_location"] = ffmpeg_path
        return options

    def extract_info(self, url, options):
        import yt_dlp

        with yt_dlp.YoutubeDL(options) as ydl:
            return ydl.extract_info(url, download=False)

    def download(self, url, options):
        import yt_dlp

        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])
        return None


class _DownloadCancelled(Exception):
    pass


class _YtdlpEventLogger:
    """Adapt yt-dlp diagnostics to the service's typed event boundary."""

    def __init__(self, emit, sanitize):
        self._emit = emit
        self._sanitize = sanitize

    def debug(self, message):
        self._log(message)

    def info(self, message):
        self._log(message)

    def warning(self, message):
        self._log(message)

    def error(self, message):
        self._log(message)

    def _log(self, message):
        self._emit(DownloadEvent("log", message=self._sanitize(message)))


class DownloadService:
    def __init__(self, backend: YtdlpBackend | None = None, logger: logging.Logger | None = None):
        self.backend = backend or _DefaultYtdlpBackend()
        self.logger = logger or logging.getLogger(__name__)

    def download(self, request: DownloadRequest, emit: Callable[[DownloadEvent], None],
                 cancel: Callable[[], bool] | None = None) -> DownloadResult:
        from universal_video_downloader import get_rockstar_video_urls, normalize_url

        normalized = normalize_url(request.url)
        if not normalized:
            return self._fail(emit, "invalid_url", "The URL is empty or invalid.")
        if self._is_cancelled(cancel):
            return self._cancelled(emit)

        urls = get_rockstar_video_urls(normalized) or []
        urls.append(normalized)
        selectors = [request.format_selector or "bv*+ba/b", "best"]
        if selectors[0] == "best":
            selectors = ["best"]

        last_error: Exception | None = None
        for source_url in urls:
            for attempt, selector in enumerate(selectors):
                if self._is_cancelled(cancel):
                    return self._cancelled(emit)
                filename_holder: list[str | None] = [None]

                def progress_hook(data: dict[str, Any]) -> None:
                    if self._is_cancelled(cancel):
                        raise _DownloadCancelled()
                    status = data.get("status")
                    if status == "downloading":
                        downloaded = data.get("downloaded_bytes", 0) or 0
                        total = data.get("total_bytes", 0) or data.get("total_bytes_estimate", 0) or 0
                        percent = downloaded / total * 100 if total else None
                        emit(DownloadEvent("progress", percent=percent, speed=data.get("speed"), eta=data.get("eta"), filename=data.get("filename")))
                    elif status == "finished":
                        filename_holder[0] = data.get("filename") or filename_holder[0]
                        emit(DownloadEvent("finished", filename=filename_holder[0]))

                try:
                    options = self._build_options(request, selector, progress_hook)
                    options["logger"] = _YtdlpEventLogger(emit, self._safe_message)
                    info = self._extract_info(source_url, options)
                    if not info:
                        raise RuntimeError("No video information was returned.")
                    title = info.get("title") if isinstance(info, dict) else None
                    emit(DownloadEvent("metadata", title=title, message=f"Video found: {title or 'Unknown title'}"))
                    downloaded_filename = self._download(source_url, options)
                    filename = downloaded_filename or filename_holder[0]
                    return DownloadResult(True, filename, title, None, None)
                except _DownloadCancelled:
                    return self._cancelled(emit)
                except Exception as error:
                    last_error = error
                    code = self._classify_error(error)
                    if code == "format_unavailable" and attempt == 0 and len(selectors) > 1:
                        continue
                    if source_url != urls[-1] and code in {"download_failed", "format_unavailable"}:
                        break
                    return self._fail(emit, code, self._safe_message(error), title=locals().get("title"))
        return self._fail(emit, self._classify_error(last_error), self._safe_message(last_error))

    def _build_options(self, request, selector, progress_hook):
        try:
            return self.backend.build_options(request, selector, progress_hook, self.logger)
        except TypeError as error:
            # Permit minimal test/adaptor backends that do not need a logger.
            try:
                return self.backend.build_options(request, selector, progress_hook)
            except TypeError:
                raise error

    def _download(self, url, options):
        try:
            return self.backend.download(url, options)
        except TypeError as error:
            try:
                return self.backend.download([url], options)
            except TypeError:
                raise error

    def _extract_info(self, url, options):
        try:
            return self.backend.extract_info(url, options)
        except TypeError as error:
            try:
                return self.backend.extract_info(url, download=False, options=options)
            except TypeError:
                raise error

    @staticmethod
    def _is_cancelled(cancel):
        try:
            return bool(cancel and cancel())
        except TypeError:
            return bool(cancel and getattr(cancel, "is_set", lambda: False)())

    def _cancelled(self, emit):
        emit(DownloadEvent("cancelled", message="Download cancelled", error_code="cancelled"))
        return DownloadResult(False, None, None, "cancelled", "Download cancelled")

    def _fail(self, emit, code, message, title=None):
        emit(DownloadEvent("failed", message=message, title=title, error_code=code))
        return DownloadResult(False, None, title, code, message)

    @staticmethod
    def _classify_error(error):
        if error is None:
            return "download_failed"
        message = str(error).lower()
        if any(p in message for p in ("requested format is not available", "format is not available", "requested format not available", "no video formats found")):
            return "format_unavailable"
        if any(p in message for p in ("sign in to confirm", "authentication", "login required", "requires authentication", "cookies")):
            return "auth_required"
        return "download_failed"

    @staticmethod
    def _safe_message(error):
        if error is None:
            return "Download failed"
        message = re.sub(r"\x1b\[[0-9;]*m", "", str(error))
        sensitive_assignment = re.compile(
            r"""(?ix)
            \b(cookie(?:s)?|session(?:id)?|token|authorization|password|secret)
            \s*[:=]\s*
            ("[^"]*"|'[^']*'|[^;,\s]+)
            """
        )
        return sensitive_assignment.sub(lambda match: f"{match.group(1)}=<redacted>", message)
