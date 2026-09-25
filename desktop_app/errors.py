"""Download error classification and concise user guidance."""

from __future__ import annotations


ERROR_GUIDANCE = {
    "invalid_url": "Check the link and enter a valid HTTP(S) URL.",
    "format_unavailable": "Choose Automatic quality and retry.",
    "auth_required": "Choose Firefox under Browser cookies in Settings, then retry while signed in.",
    "cookie_database_locked": "Close that browser completely, or choose Firefox in Settings, then retry.",
    "cookie_decrypt_failed": "Chromium cookies cannot be decrypted on Windows. Choose Firefox in Settings, then retry.",
    "js_runtime_missing": "Install Deno, restart the app, then retry.",
    "challenge_solver_missing": "The YouTube challenge solver did not run. Check the network, then retry.",
    "network_error": "Check your internet connection and retry.",
    "proxy_error": "Check the proxy settings or turn the proxy off.",
    "ffmpeg_missing": "Install FFmpeg and restart the app, or reinstall the packaged app.",
    "unsupported_site": "This site is unsupported; try a direct media link.",
    "cancelled": "Download cancelled.",
    "download_failed": "Retry, or open Activity for technical details.",
}


def classify_error(error: object | None) -> str:
    """Map dependency exceptions into the public release error taxonomy."""
    if error is None:
        return "download_failed"
    message = str(error).lower()
    error_name = type(error).__name__.lower()

    if any(
        phrase in message
        for phrase in (
            "requested format is not available",
            "format is not available",
            "requested format not available",
            "no video formats found",
        )
    ):
        return "format_unavailable"

    if "could not copy chrome cookie database" in message or (
        "could not copy" in message and "cookie" in message
    ):
        return "cookie_database_locked"

    if "failed to decrypt with dpapi" in message or "app-bound encryption" in message:
        return "cookie_decrypt_failed"

    if any(
        phrase in message
        for phrase in (
            "no supported javascript runtime",
            "only deno is enabled",
            "js-runtimes",
        )
    ):
        return "js_runtime_missing"

    if any(
        phrase in message
        for phrase in (
            "n challenge solving failed",
            "challenge solver",
            "the page needs to be reloaded",
        )
    ):
        return "challenge_solver_missing"

    if error_name in {"proxyerror", "proxyexception"} or any(
        phrase in message
        for phrase in (
            "proxyerror",
            "proxy error",
            "proxy authentication",
            "proxy connection",
            "tunnel connection failed",
            "http error 407",
            "status code 407",
        )
    ):
        return "proxy_error"

    if "ffmpeg" in message and any(
        phrase in message
        for phrase in (
            "ffmpeg not found",
            "ffprobe not found",
            "ffmpeg is not installed",
            "unable to locate ffmpeg",
            "please install ffmpeg",
        )
    ):
        return "ffmpeg_missing"

    if any(
        phrase in message
        for phrase in (
            "sign in to confirm",
            "authentication",
            "login required",
            "requires authentication",
            "cookies",
            "unauthorized",
        )
    ):
        return "auth_required"

    if any(
        phrase in message
        for phrase in (
            "unsupported url",
            "unsupported site",
            "no suitable extractor",
            "no media links",
            "could not find any video",
        )
    ):
        return "unsupported_site"

    if error_name in {"timeout", "timeouterror", "connectionerror"} or any(
        phrase in message
        for phrase in (
            "temporary failure in name resolution",
            "name or service not known",
            "network is unreachable",
            "connection refused",
            "connection reset",
            "remote disconnected",
            "timed out",
            "timeout",
            "ssl error",
            "certificate verify failed",
            "http error 408",
            "http error 429",
            "http error 500",
            "http error 502",
            "http error 503",
            "http error 504",
            "unable to download webpage",
        )
    ):
        return "network_error"

    return "download_failed"


def guidance_for(code: str | None) -> str:
    return ERROR_GUIDANCE.get(code or "download_failed", ERROR_GUIDANCE["download_failed"])
