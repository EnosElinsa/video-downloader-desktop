"""Central secret scrubbing for service, legacy, worker, and UI messages."""

from __future__ import annotations

import re
from collections.abc import Iterable
import logging
from urllib.parse import unquote, urlsplit


_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
_URL_USERINFO = re.compile(
    r"(?i)(?P<scheme>\b[a-z][a-z0-9+.-]*://)(?:[^\s/@]+(?::[^\s/@]*)?@)"
)
_SENSITIVE_ASSIGNMENT = re.compile(
    r"""(?ix)
    \b(
        cookie(?:s)?|set-cookie|session(?:id)?|sid|token|access[_-]?token|
        refresh[_-]?token|authorization|proxy-authorization|password|passwd|
        secret|api[_-]?key
    )
    \s*[:=]\s*
    ("[^"]*"|'[^']*'|[^;,\s]+)
    """
)
_AUTH_HEADER = re.compile(
    r"(?ix)\b(proxy-authorization|authorization)\s*:\s*[^\r\n;,]+"
)


def configured_secret_values(proxy_url: str | None = None) -> tuple[str, ...]:
    """Return credential values that may appear outside their original URL."""
    if not proxy_url:
        return ()
    try:
        parsed = urlsplit(str(proxy_url))
    except ValueError:
        return ()
    values = []
    for value in (parsed.username, parsed.password):
        if value:
            values.extend((value, unquote(value)))
    return tuple(dict.fromkeys(value for value in values if value))


def sanitize_message(value: object, secrets: Iterable[str] = ()) -> str:
    """Remove terminal escapes, URL userinfo, assignments, and known values."""
    message = _ANSI_ESCAPE.sub("", str(value))
    message = _URL_USERINFO.sub(lambda match: match.group("scheme"), message)
    message = _AUTH_HEADER.sub(lambda match: f"{match.group(1)}: <redacted>", message)
    message = _SENSITIVE_ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}=<redacted>", message
    )
    for secret in sorted(
        {str(secret) for secret in secrets if secret}, key=len, reverse=True
    ):
        message = message.replace(secret, "<redacted>")
    return message


class SecretRedactionFilter(logging.Filter):
    """Redact messages at the logger boundary, including legacy callers."""

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self._secrets = set(str(secret) for secret in secrets if secret)

    def add_secrets(self, secrets: Iterable[str]) -> None:
        self._secrets.update(str(secret) for secret in secrets if secret)

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = sanitize_message(record.getMessage(), self._secrets)
        record.args = ()
        return True


_GLOBAL_FILTER = SecretRedactionFilter()


def install_redaction(logger: logging.Logger) -> SecretRedactionFilter:
    """Install one idempotent redaction filter on a logger."""
    if _GLOBAL_FILTER not in logger.filters:
        logger.addFilter(_GLOBAL_FILTER)
    for handler in logger.handlers:
        if _GLOBAL_FILTER not in handler.filters:
            handler.addFilter(_GLOBAL_FILTER)
    return _GLOBAL_FILTER


def register_secret_values(values: Iterable[str]) -> None:
    _GLOBAL_FILTER.add_secrets(values)
