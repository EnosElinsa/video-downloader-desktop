"""yt-dlp option building and interactive CLI adapter.

The desktop download interface lives in :mod:`desktop_app.download_core`.
This module contains the concrete yt-dlp mechanics shared by that interface
and the optional terminal format picker.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Callable
from uuid import uuid4

from .security import configured_secret_values, register_secret_values, sanitize_message
from .urls import normalize_http_url

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)


def default_output_template(output_dir: str | os.PathLike[str] = ".") -> str:
    token = uuid4().hex
    return os.path.join(str(output_dir), f"video_%(title).120B_%(id)s_{token}.%(ext)s")


def build_ytdlp_options(
    url: str,
    output_dir: str | os.PathLike[str] = ".",
    use_proxy: bool = False,
    proxy_url: str | None = None,
    format_selector: str = "bv*+ba/b",
    cookie_browser: str | None = None,
    output_template: str | None = None,
    progress_hook: Callable[[dict], None] | None = None,
) -> dict:
    """Build resilient yt-dlp options for GUI, CLI, and batch callers."""
    options = {
        "format": format_selector,
        "outtmpl": output_template or default_output_template(output_dir),
        "noplaylist": True,
        "progress_hooks": [progress_hook or print_progress],
        "verbose": False,
        "no_warnings": False,
        "ignoreerrors": False,
        "geo_bypass": True,
        "retries": 3,
        "fragment_retries": 3,
        "file_access_retries": 3,
        "continuedl": True,
        "http_headers": {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": url,
        },
        "merge_output_format": "mp4",
    }
    if use_proxy and proxy_url:
        options["proxy"] = proxy_url
    if cookie_browser and str(cookie_browser).strip():
        options["cookiesfrombrowser"] = (str(cookie_browser).strip().lower(),)
    return options


def choose_format_for_context(formats: list[dict], requested: bool = False) -> str | None:
    """Prompt for a format only when an interactive terminal is present."""
    if not requested or not formats:
        return None
    stdin = getattr(sys, "stdin", None)
    if stdin is None or not stdin.isatty():
        logger.warning("Format selection is unavailable here; using automatic best quality.")
        return None
    return get_user_format_choice(formats)


def get_user_format_choice(formats: list[dict]) -> str:
    """Present the useful video/audio formats and return one yt-dlp selector."""
    choices: dict[int, str] = {}
    print("\nAvailable formats:")
    option = 1
    for fmt in sorted(
        formats,
        key=lambda item: (item.get("height") or 0, item.get("tbr") or item.get("abr") or 0),
        reverse=True,
    ):
        has_video = fmt.get("vcodec") != "none"
        has_audio = fmt.get("acodec") != "none"
        if not has_video and not has_audio:
            continue
        if has_video:
            label = f"{fmt.get('height') or '?'}p {fmt.get('ext', '?')}"
            if not has_audio:
                label += " (video only)"
        else:
            label = f"Audio {fmt.get('abr') or '?'} kbps {fmt.get('ext', '?')}"
        print(f"{option}. {label}")
        choices[option] = str(fmt.get("format_id", "best"))
        option += 1
    common = {
        option: ("Best video + audio", "bv*+ba/b"),
        option + 1: ("Best single file", "best"),
        option + 2: ("Best audio only", "bestaudio"),
    }
    for number, (label, selector) in common.items():
        print(f"{number}. {label}")
        choices[number] = selector
    while True:
        value = input("\nSelect format number (Enter for automatic): ").strip()
        if not value:
            return "bv*+ba/b"
        try:
            return choices[int(value)]
        except (ValueError, KeyError):
            print("Please enter one of the listed numbers.")


def _is_format_error(error: object) -> bool:
    message = str(error).lower()
    return any(
        phrase in message
        for phrase in (
            "requested format is not available",
            "format is not available",
            "requested format not available",
            "no video formats found",
        )
    )


def log_download_error(error: object, proxy_url: str | None = None) -> None:
    secrets = configured_secret_values(proxy_url)
    register_secret_values(secrets)
    message = sanitize_message(error, secrets)
    lower = message.lower()
    if "sign in to confirm your age" in lower or "age-restricted" in lower:
        logger.error(
            "YouTube requires authentication. Select browser cookies and retry while signed in."
        )
    elif _is_format_error(error):
        logger.warning("The requested format is unavailable; trying an automatic fallback.")
    logger.error("yt-dlp could not download this video: %s", message)


def download_with_ytdlp(
    url: str,
    output_dir: str | os.PathLike[str] = ".",
    use_proxy: bool = False,
    proxy_url: str | None = None,
    select_format: bool = False,
    cookie_browser: str | None = None,
    output_template: str | None = None,
) -> bool:
    """Run the optional interactive CLI yt-dlp workflow."""
    import yt_dlp

    try:
        normalized = normalize_http_url(url)
    except ValueError:
        logger.error("The URL is empty or invalid.")
        return False
    register_secret_values(configured_secret_values(proxy_url))
    template = output_template or default_output_template(output_dir)
    selectors = ["bv*+ba/b", "best"]
    interactive_pending = select_format
    for attempt, selector in enumerate(selectors):
        options = build_ytdlp_options(
            normalized,
            output_dir,
            use_proxy,
            proxy_url,
            selector,
            cookie_browser,
            template,
        )
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(normalized, download=False)
                if not info:
                    raise yt_dlp.utils.DownloadError("No video information was returned.")
                logger.info(
                    "Video found: %s",
                    sanitize_message(info.get("title", "Unknown title"), configured_secret_values(proxy_url)),
                )
                selected = choose_format_for_context(
                    info.get("formats", []), requested=interactive_pending
                )
                interactive_pending = False
            if selected:
                options = build_ytdlp_options(
                    normalized,
                    output_dir,
                    use_proxy,
                    proxy_url,
                    selected,
                    cookie_browser,
                    template,
                )
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([normalized])
            return True
        except yt_dlp.utils.DownloadError as error:
            log_download_error(error, proxy_url)
            if attempt == 0 and _is_format_error(error):
                continue
            break
        except Exception as error:
            logger.error("Download failed: %s", sanitize_message(error, configured_secret_values(proxy_url)))
            break
    return False


def format_size(byte_count: float | int | None) -> str:
    if not byte_count:
        return "Unknown"
    value = float(byte_count)
    for suffix in ("B", "KB", "MB", "GB"):
        if value < 1024 or suffix == "GB":
            return f"{value:.1f} {suffix}" if suffix != "B" else f"{int(value)} B"
        value /= 1024
    return "Unknown"


def format_duration(seconds: float | int | None) -> str:
    if not seconds:
        return "Unknown"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def print_progress(data: dict) -> None:
    status = data.get("status")
    if status == "downloading":
        downloaded = data.get("downloaded_bytes", 0) or 0
        total = data.get("total_bytes", 0) or data.get("total_bytes_estimate", 0) or 0
        progress = (
            f"{downloaded / total * 100:.1f}% ({format_size(downloaded)}/{format_size(total)})"
            if total
            else f"{format_size(downloaded)} downloaded"
        )
        if data.get("speed"):
            progress += f" at {format_size(data['speed'])}/s"
        if data.get("eta"):
            progress += f", ETA {format_duration(data['eta'])}"
        print(f"\r{progress}", end="", flush=True)
    elif status == "finished":
        print()
        logger.info("Download complete: %s", sanitize_message(data.get("filename", "")))


__all__ = [
    "build_ytdlp_options",
    "choose_format_for_context",
    "default_output_template",
    "download_with_ytdlp",
    "format_duration",
    "format_size",
    "get_user_format_choice",
    "log_download_error",
    "print_progress",
]
