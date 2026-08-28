"""Shared normalization and validation for user-supplied download URLs."""

from __future__ import annotations

import html
import ipaddress
import re
from urllib.parse import parse_qs, unquote, urljoin, urlsplit, urlunsplit


def normalize_url(raw_url: object) -> str:
    """Normalize URLs copied from Markdown, HTML, or chat applications."""
    if raw_url is None:
        return ""
    value = html.unescape(str(raw_url)).strip()
    markdown_match = re.fullmatch(r"\[([^\]]+)\]\(([^)]+)\)", value)
    if markdown_match:
        value = markdown_match.group(2).strip()
    value = value.replace(r"\&", "&").replace(r"\/", "/")
    value = value.strip("<>")
    value = re.sub(r"[\]\)>;,\.]+$", "", value)
    if value and not re.match(r"^[a-z][a-z0-9+.-]*://", value, re.IGNORECASE):
        value = "https://" + value
    return value


def _append_unique_url(urls: list[str], candidate: object, base_url: str) -> None:
    if not candidate:
        return
    value = html.unescape(str(candidate)).strip().strip('"\'<>')
    value = value.replace(r"\/", "/").replace(r"\u0026", "&")
    value = unquote(value)
    value = urljoin(base_url, value)
    if value.startswith(("http://", "https://")) and value not in urls:
        urls.append(value)


def extract_video_urls_from_html(html_content: str, page_url: str) -> list[str]:
    """Extract direct media URLs from HTML, including relative/JSON URLs."""
    urls: list[str] = []
    patterns = (
        r'<meta[^>]+property\s*=\s*["\']og:video(?::secure_url)?["\'][^>]+content\s*=\s*["\']([^"\']+)',
        r'<meta[^>]+content\s*=\s*["\']([^"\']+)["\'][^>]+property\s*=\s*["\']og:video(?::secure_url)?["\']',
        r'<(?:video|source)[^>]+src\s*=\s*["\']([^"\']+)',
        r'(?:https?:)?//[^"\'\\\s<>]+\.(?:mp4|m4v|webm|mov|flv|m3u8|mpd)(?:\?[^"\'\\\s<>]*)?',
        r'["\']([^"\']+\.(?:mp4|m4v|webm|mov|flv|m3u8|mpd)(?:\?[^"\']*)?)["\']',
    )
    for pattern in patterns:
        for match in re.findall(pattern, html_content, flags=re.IGNORECASE):
            _append_unique_url(urls, match, page_url)
    return urls


def get_rockstar_video_urls(url: object) -> list[str]:
    """Return current Rockstar public CDN variants for a `/videos/<id>` URL."""
    parsed = urlsplit(normalize_url(url))
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if hostname not in ("rockstargames.com", "www.rockstargames.com") and not hostname.endswith(".rockstargames.com"):
        return []
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    try:
        videos_index = next(i for i, part in enumerate(parts) if part.lower() == "videos")
    except StopIteration:
        return []
    if videos_index + 1 >= len(parts):
        return []
    video_id = parts[videos_index + 1]
    if video_id.lower() == "video" and videos_index + 2 < len(parts):
        video_id = parts[videos_index + 2]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", video_id):
        return []
    query = parse_qs(parsed.query)
    requested = query.get("resolution", [""])[0].lower()
    if not re.fullmatch(r"\d{3,4}p", requested):
        requested = ""
    resolutions = [requested] if requested else []
    resolutions.extend(
        value for value in ("2160p", "1440p", "1080p", "720p", "480p", "360p")
        if value not in resolutions
    )
    locale = query.get("locale", ["en-us"])[0].lower().replace("_", "-")
    if not re.fullmatch(r"[a-z]{2}(?:-[a-z]{2})?", locale):
        locale = "en-us"
    return [
        f"https://videos-rockstargames-com.akamaized.net/v4/{video_id}/flv/{locale}-{resolution}.mp4"
        for resolution in resolutions
    ]


def normalize_http_url(raw_url: object) -> str:
    """Return one normalized HTTP(S) URL or raise ``ValueError``."""
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
