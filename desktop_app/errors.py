"""Download error classification and concise user guidance."""

from __future__ import annotations


ERROR_GUIDANCE = {
    "invalid_url": "Check the link and enter a valid HTTP(S) URL.",
    "format_unavailable": "Choose Automatic quality and retry.",
    "auth_required": "Select browser cookies in Settings, then retry.",
    "network_error": "Check your internet connection and retry.",
    "proxy_error": "Check the proxy settings or turn the proxy off.",
    "ffmpeg_missing": "Reinstall the app to restore the bundled FFmpeg tools.",
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
