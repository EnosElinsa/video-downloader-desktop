"""Shared normalization and validation for user-supplied download URLs."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit


def normalize_http_url(raw_url: object) -> str:
    """Return one normalized HTTP(S) URL or raise ``ValueError``."""
    from universal_video_downloader import normalize_url

    value = normalize_url(raw_url)
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ValueError("Enter a valid HTTP(S) URL with a hostname.") from error
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Enter a valid HTTP(S) URL with a hostname.")
    hostname = parsed.hostname.strip().rstrip(".").lower()
    if not hostname or any(character.isspace() for character in hostname):
        raise ValueError("Enter a valid HTTP(S) URL with a hostname.")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        labels = hostname.split(".")
        if any(
            not label
            or len(label) > 63
            or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label)
            for label in labels
        ):
            raise ValueError("Enter a valid HTTP(S) URL with a hostname.")
    host = f"[{hostname}]" if ":" in hostname else hostname
    if parsed.username is not None:
        userinfo = parsed.username
        if parsed.password is not None:
            userinfo += f":{parsed.password}"
        host = f"{userinfo}@{host}"
    if port is not None:
        host = f"{host}:{port}"
    return urlunsplit((parsed.scheme.lower(), host, parsed.path or "", parsed.query, ""))


def normalized_hostname(url: object) -> str:
    """Return a display-safe normalized hostname."""
    try:
        return urlsplit(normalize_http_url(url)).hostname or "Unknown site"
    except ValueError:
        return "Unknown site"
