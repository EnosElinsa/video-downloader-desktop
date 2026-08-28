"""Command-line entry point and programmatic compatibility interface."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from .direct_fallback import DirectMediaFallback
from .download_core import DownloadService
from .filenames import sanitize_filename
from .models import DownloadRequest, DownloadResult
from .security import configured_secret_values, install_redaction, sanitize_message
from .urls import (
    extract_video_urls_from_html,
    get_rockstar_video_urls,
    normalize_http_url,
    normalize_url,
)
from .yt_dlp_adapter import (
    build_ytdlp_options,
    choose_format_for_context,
    download_with_ytdlp,
    log_download_error as _log_download_error,
)

logger = logging.getLogger(__name__)
install_redaction(logger)


def download_video(
    url,
    output_dir=".",
    use_proxy=False,
    proxy_url=None,
    select_format=False,
    cookie_browser=None,
    output_template=None,
):
    """Download one URL through the shared desktop download interface."""
    try:
        normalized = normalize_http_url(url)
    except ValueError:
        message = "Enter a valid HTTP(S) URL with a hostname."
        logger.error(message)
        return DownloadResult(False, None, None, "invalid_url", message)
    logger.info(
        "Attempting to download video from: %s",
        sanitize_message(normalized, configured_secret_values(proxy_url)),
    )
    # Only the terminal workflow needs the interactive picker.
    if select_format:
        for candidate in get_rockstar_video_urls(normalized):
            if download_with_ytdlp(
                candidate,
                output_dir,
                use_proxy,
                proxy_url,
                True,
                cookie_browser,
                output_template,
            ):
                return DownloadResult(True, None, None, None, None)
        if download_with_ytdlp(
            normalized,
            output_dir,
            use_proxy,
            proxy_url,
            True,
            cookie_browser,
            output_template,
        ):
            return DownloadResult(True, None, None, None, None)

    request = DownloadRequest(
        normalized,
        Path(output_dir),
        use_proxy=use_proxy,
        proxy_url=proxy_url,
        cookie_browser=cookie_browser,
        output_template=output_template,
    )

    def emit(event):
        if event.message:
            logger.info(
                "%s", sanitize_message(event.message, configured_secret_values(proxy_url))
            )
        if event.kind == "finished" and event.filename:
            logger.info("Download complete: %s", sanitize_message(event.filename))

    return DownloadService().download(request, emit)


def try_fallback_methods(
    url,
    output_dir=".",
    use_proxy=False,
    proxy_url=None,
    cookie_browser=None,
):
    """Run the direct-media adapter explicitly for diagnostic callers."""
    try:
        normalized = normalize_http_url(url)
    except ValueError:
        return False
    request = DownloadRequest(
        normalized,
        Path(output_dir),
        use_proxy=use_proxy,
        proxy_url=proxy_url,
        cookie_browser=cookie_browser,
    )

    def manifest(media_url):
        result = download_with_ytdlp(
            media_url,
            output_dir,
            use_proxy,
            proxy_url,
            False,
            cookie_browser,
            request.output_template,
        )
        return DownloadResult(bool(result), None, None, None if result else "download_failed", None)

    result = DirectMediaFallback().attempt(
        request,
        lambda event: logger.info("%s", sanitize_message(event.message)) if event.message else None,
        lambda: False,
        manifest,
    )
    return bool(result)


def check_dependencies() -> None:
    """Install core CLI dependencies only when the user runs the source CLI."""
    for import_name, package in (("yt_dlp", "yt-dlp"), ("requests", "requests")):
        try:
            __import__(import_name)
        except ImportError:
            logger.info("Installing %s...", package)
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])


def _config_path() -> Path:
    return Path.home() / ".video_downloader_config.json"


def load_config() -> dict:
    defaults = {
        "output_dir": ".",
        "use_proxy": False,
        "proxy_url": "",
        "select_format": False,
        "cookie_browser": "",
    }
    try:
        if _config_path().is_file():
            value = json.loads(_config_path().read_text(encoding="utf-8"))
            if isinstance(value, dict):
                defaults.update(value)
    except (OSError, ValueError) as error:
        logger.error("Could not load CLI settings: %s", sanitize_message(error))
    return defaults


def save_config(config: dict) -> None:
    try:
        _config_path().write_text(json.dumps(config, indent=2), encoding="utf-8")
    except OSError as error:
        logger.error("Could not save CLI settings: %s", sanitize_message(error))


def _configure(config: dict) -> None:
    print("\nConfiguration")
    print(f"1. Output directory: {config['output_dir']}")
    print(f"2. Use proxy: {config['use_proxy']}")
    print(f"3. Proxy address: {'configured' if config.get('proxy_url') else 'none'}")
    print(f"4. Interactive format picker: {config['select_format']}")
    print(f"5. Browser cookies: {config.get('cookie_browser') or 'none'}")
    choice = input("Select an option to change (Enter to return): ").strip()
    if choice == "1":
        output = input("Output directory: ").strip()
        if output:
            Path(output).mkdir(parents=True, exist_ok=True)
            config["output_dir"] = output
    elif choice == "2":
        config["use_proxy"] = input("Use proxy? (y/n): ").strip().lower() == "y"
    elif choice == "3":
        config["proxy_url"] = input("Proxy URL: ").strip()
    elif choice == "4":
        config["select_format"] = input("Pick a format interactively? (y/n): ").strip().lower() == "y"
    elif choice == "5":
        config["cookie_browser"] = input("Browser (chrome/edge/firefox/brave or blank): ").strip().lower()
    save_config(config)


def main() -> int:
    """Run the optional interactive terminal downloader."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    check_dependencies()
    config = load_config()
    print("\nVideo Downloader CLI")
    print("Enter a URL, 'c' for configuration, or 'q' to quit.\n")
    while True:
        value = input("Video URL: ").strip()
        if value.lower() == "q":
            return 0
        if value.lower() == "c":
            _configure(config)
            continue
        if not value:
            continue
        normalized = normalize_url(value)
        result = download_video(
            normalized,
            config["output_dir"],
            config["use_proxy"],
            config["proxy_url"],
            config["select_format"],
            config.get("cookie_browser"),
        )
        logger.info("Video downloaded successfully." if result else "Download failed.")


if __name__ == "__main__":
    raise SystemExit(main())
