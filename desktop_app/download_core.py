"""Qt-free, injectable download orchestration."""

from __future__ import annotations

import logging
import inspect
import sys
from dataclasses import replace
from pathlib import Path
from typing import Callable, Protocol, Any

from .errors import classify_error
from .models import DownloadEvent, DownloadRequest, DownloadResult
from .security import (
    configured_secret_values,
    install_redaction,
    register_secret_values,
    sanitize_message,
)
from .urls import normalize_http_url


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


class FallbackBackend(Protocol):
    def attempt(
        self,
        request: DownloadRequest,
        emit: Callable[[DownloadEvent], None],
        cancel: Callable[[], bool] | None,
        download_manifest: Callable[[str], DownloadResult],
    ) -> DownloadResult | None: ...


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
    def __init__(
        self,
        backend: YtdlpBackend | None = None,
        logger: logging.Logger | None = None,
        fallback: FallbackBackend | None = None,
    ):
        self.backend = backend or _DefaultYtdlpBackend()
        self.logger = logger or logging.getLogger(__name__)
        install_redaction(self.logger)
        if fallback is None:
            from .direct_fallback import DirectMediaFallback

            fallback = DirectMediaFallback()
        self.fallback = fallback

    def download(self, request: DownloadRequest, emit: Callable[[DownloadEvent], None],
                 cancel: Callable[[], bool] | None = None) -> DownloadResult:
        from universal_video_downloader import get_rockstar_video_urls

        try:
            normalized = normalize_http_url(request.url)
        except ValueError:
            return self._fail(emit, "invalid_url", "The URL is empty or invalid.")
        if self._is_cancelled(cancel):
            return self._cancelled(emit)

        request = self._prepare_request(request, normalized)
        secrets = configured_secret_values(request.proxy_url)
        register_secret_values(secrets)

        def safe_emit(event: DownloadEvent) -> None:
            emit(
                replace(
                    event,
                    message=sanitize_message(event.message, secrets),
                    title=sanitize_message(event.title, secrets) if event.title else event.title,
                    filename=(
                        sanitize_message(event.filename, secrets)
                        if event.filename
                        else event.filename
                    ),
                )
            )

        rockstar_urls = get_rockstar_video_urls(normalized) or []
        urls = [*rockstar_urls, normalized]
        last_error: Exception | None = None
        for source_url in urls:
            result, error = self._download_ytdlp_url(
                source_url, request, safe_emit, cancel, secrets
            )
            if result is not None:
                return self._sanitize_result(result, secrets)
            if isinstance(error, _DownloadCancelled):
                return self._cancelled(safe_emit)
            last_error = error
            if source_url in rockstar_urls:
                continue
            break

        if self._is_cancelled(cancel):
            return self._cancelled(safe_emit)
        error_code = self._classify_error(last_error)
        if error_code in {"auth_required", "ffmpeg_missing", "network_error", "proxy_error"}:
            return self._fail(
                safe_emit,
                error_code,
                sanitize_message(
                    last_error if last_error is not None else "Download failed", secrets
                ),
            )
        try:
            fallback_result = self._run_fallback(
                request,
                safe_emit,
                cancel,
                lambda media_url: self._download_manifest(
                    media_url, request, safe_emit, cancel, secrets
                ),
            )
            if fallback_result is not None:
                if isinstance(fallback_result, DownloadResult):
                    sanitized = self._sanitize_result(fallback_result, secrets)
                    if sanitized.success or sanitized.error_code == "cancelled":
                        return sanitized
                    last_error = sanitized.error_message or last_error
                elif fallback_result:
                    return DownloadResult(True, None, None, None, None)
        except _DownloadCancelled:
            return self._cancelled(safe_emit)
        except Exception as error:
            last_error = error

        return self._fail(
            safe_emit,
            self._classify_error(last_error),
            sanitize_message(last_error if last_error is not None else "Download failed", secrets),
        )

    @staticmethod
    def _prepare_request(request: DownloadRequest, normalized_url: str) -> DownloadRequest:
        output_template = request.output_template
        if not output_template:
            output_template = str(
                Path(request.output_dir)
                / f"video_%(title).120B_%(id)s_{request.request_id}.%(ext)s"
            )
        return replace(request, url=normalized_url, output_template=output_template)

    def _download_ytdlp_url(self, source_url, request, emit, cancel, secrets):
        selectors = [request.format_selector or "bv*+ba/b", "best"]
        if selectors[0] == "best":
            selectors = ["best"]
        last_error = None
        for attempt, selector in enumerate(selectors):
            if self._is_cancelled(cancel):
                return None, _DownloadCancelled()
            filename_holder: list[str | None] = [None]

            def progress_hook(data: dict[str, Any]) -> None:
                if self._is_cancelled(cancel):
                    raise _DownloadCancelled()
                status = data.get("status")
                if status == "downloading":
                    downloaded = data.get("downloaded_bytes", 0) or 0
                    total = (
                        data.get("total_bytes", 0)
                        or data.get("total_bytes_estimate", 0)
                        or 0
                    )
                    emit(
                        DownloadEvent(
                            "progress",
                            percent=downloaded / total * 100 if total else None,
                            speed=data.get("speed"),
                            eta=data.get("eta"),
                            filename=data.get("filename"),
                        )
                    )
                elif status == "finished":
                    filename_holder[0] = data.get("filename") or filename_holder[0]
                    emit(DownloadEvent("finished", filename=filename_holder[0]))

            try:
                options = self._build_options(request, selector, progress_hook)
                options["logger"] = _YtdlpEventLogger(
                    emit, lambda message: sanitize_message(message, secrets)
                )
                info = self._extract_info(source_url, options)
                if not info:
                    raise RuntimeError("No video information was returned.")
                title = info.get("title") if isinstance(info, dict) else None
                emit(
                    DownloadEvent(
                        "metadata",
                        title=title,
                        message=f"Video found: {title or 'Unknown title'}",
                    )
                )
                downloaded_filename = self._download(source_url, options)
                filename = downloaded_filename or filename_holder[0]
                return DownloadResult(True, filename, title, None, None), None
            except _DownloadCancelled as error:
                return None, error
            except Exception as error:
                if self._is_cancelled(cancel):
                    return None, _DownloadCancelled()
                last_error = error
                if (
                    self._classify_error(error) == "format_unavailable"
                    and attempt == 0
                    and len(selectors) > 1
                ):
                    continue
                break
        return None, last_error

    def _download_manifest(self, url, request, emit, cancel, secrets):
        result, error = self._download_ytdlp_url(url, request, emit, cancel, secrets)
        if result is not None:
            return result
        if isinstance(error, _DownloadCancelled):
            raise error
        return DownloadResult(
            False,
            None,
            None,
            self._classify_error(error),
            sanitize_message(error if error is not None else "Download failed", secrets),
        )

    def _run_fallback(self, request, emit, cancel, download_manifest):
        fallback = self.fallback
        attempt = getattr(fallback, "attempt", None)
        target = attempt if callable(attempt) else fallback
        if callable(target):
            try:
                parameters = inspect.signature(target)
            except (TypeError, ValueError):
                parameters = None
            if parameters is not None:
                try:
                    parameters.bind(request, emit, cancel, download_manifest)
                except TypeError:
                    parameters.bind(request, emit, cancel)
                    return target(request, emit, cancel)
            return target(request, emit, cancel, download_manifest)
        raise TypeError("fallback must provide attempt() or be callable")

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
        safe_message = sanitize_message(message)
        emit(DownloadEvent("failed", message=safe_message, title=title, error_code=code))
        return DownloadResult(False, None, title, code, safe_message)

    @staticmethod
    def _classify_error(error):
        return classify_error(error)

    @staticmethod
    def _safe_message(error):
        if error is None:
            return "Download failed"
        return sanitize_message(error)

    @staticmethod
    def _sanitize_result(result: DownloadResult, secrets) -> DownloadResult:
        return replace(
            result,
            filename=(
                sanitize_message(result.filename, secrets)
                if result.filename
                else result.filename
            ),
            title=sanitize_message(result.title, secrets) if result.title else result.title,
            error_message=(
                sanitize_message(result.error_message, secrets)
                if result.error_message
                else result.error_message
            ),
        )
