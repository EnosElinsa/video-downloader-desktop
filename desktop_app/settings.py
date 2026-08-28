"""Per-user, versioned application settings."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any


@dataclass
class AppSettings:
    VERSION = 1

    output_dir: Path | None = None
    format_selector: str = "bv*+ba/b"
    use_proxy: bool = False
    proxy_url: str | None = None
    cookie_browser: str | None = None
    concurrent_downloads: int = 2
    startup_behavior: str = "normal"
    theme: str = "dark"

    def __post_init__(self) -> None:
        if not isinstance(self.output_dir, (str, os.PathLike)) or not str(self.output_dir).strip():
            self.output_dir = self.default_output_dir()
        else:
            try:
                self.output_dir = Path(self.output_dir)
                if self.output_dir.exists() and not self.output_dir.is_dir():
                    self.output_dir = self.default_output_dir()
            except (TypeError, ValueError, OSError):
                self.output_dir = self.default_output_dir()
        if not isinstance(self.format_selector, str) or self.format_selector not in {"bv*+ba/b", "best"}:
            self.format_selector = "bv*+ba/b"
        self.use_proxy = self._coerce_bool(self.use_proxy, False)
        if not isinstance(self.proxy_url, str) or not self.proxy_url.strip():
            self.proxy_url = None
        else:
            self.proxy_url = self.proxy_url.strip()
        allowed_browsers = {"chrome", "edge", "firefox", "brave", "opera", "chromium"}
        if isinstance(self.cookie_browser, str):
            self.cookie_browser = self.cookie_browser.strip().lower() or None
        if self.cookie_browser not in allowed_browsers:
            self.cookie_browser = None
        self.concurrent_downloads = self._bounded_int(
            self.concurrent_downloads, default=2, minimum=1, maximum=8
        )
        if self.startup_behavior not in {"normal", "minimized"}:
            self.startup_behavior = "normal"
        if self.theme not in {"dark", "light"}:
            self.theme = "dark"
        if self.proxy_url:
            from urllib.parse import urlparse

            parsed_proxy = urlparse(self.proxy_url)
            try:
                parsed_proxy.port
            except ValueError:
                parsed_proxy = None
            if parsed_proxy is None or parsed_proxy.scheme not in {"http", "https", "socks5", "socks5h"} or not parsed_proxy.hostname:
                self.proxy_url = None
                self.use_proxy = False

    @staticmethod
    def _coerce_bool(value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "yes", "1", "on"}:
                return True
            if lowered in {"false", "no", "0", "off"}:
                return False
        return default

    @staticmethod
    def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
        if isinstance(value, bool):
            return default
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return max(minimum, min(maximum, parsed))

    @classmethod
    def app_dir(cls) -> Path:
        local = os.environ.get("LOCALAPPDATA")
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        return base / "VideoDownloader"

    @classmethod
    def default_output_dir(cls) -> Path:
        return cls.app_dir() / "videos"

    @classmethod
    def load(cls, path: str | Path | None = None) -> "AppSettings":
        target = Path(path) if path is not None else cls.app_dir() / "settings.json"
        if not target.exists():
            return cls()
        try:
            raw: Any = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("settings must be an object")
        except (OSError, ValueError, json.JSONDecodeError):
            return cls()
        # Missing ``version`` is the original v0 schema.  Keep migrations
        # named and explicit so a future payload is never silently downgraded.
        raw_version = raw.get("version", 0)
        # ``bool`` is an ``int`` subclass, and JSON numbers/strings must not
        # be coerced into a schema version.
        if type(raw_version) is not int:
            return cls()
        version = raw_version
        if version > cls.VERSION or version < 0:
            return cls()
        values = {f.name: raw[f.name] for f in fields(cls) if f.name in raw}
        values.pop("VERSION", None)
        while version < cls.VERSION:
            migration = getattr(cls, f"_migrate_v{version}_to_v{version + 1}", None)
            if migration is None:
                return cls()
            values = migration(values)
            version += 1
        defaults = cls()
        if not isinstance(values.get("output_dir"), (str, os.PathLike)):
            values["output_dir"] = defaults.output_dir
        if not isinstance(values.get("format_selector"), str) or values.get("format_selector") not in {"bv*+ba/b", "best"}:
            values["format_selector"] = defaults.format_selector
        if not isinstance(values.get("proxy_url"), (str, type(None))):
            values["proxy_url"] = defaults.proxy_url
        if not isinstance(values.get("cookie_browser"), (str, type(None))):
            values["cookie_browser"] = defaults.cookie_browser
        if not isinstance(values.get("startup_behavior"), str):
            values["startup_behavior"] = defaults.startup_behavior
        if not isinstance(values.get("theme"), str):
            values["theme"] = defaults.theme
        try:
            return cls(**values)
        except (TypeError, ValueError, OSError):
            return defaults

    @staticmethod
    def _migrate_v0_to_v1(values: dict[str, Any]) -> dict[str, Any]:
        # v0 had no cookie_browser (or any of the newer optional fields).
        # Dataclass defaults supply those fields when absent.
        return values

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path is not None else self.app_dir() / "settings.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": self.VERSION}
        for f in fields(self):
            value = getattr(self, f.name)
            payload[f.name] = str(value) if isinstance(value, Path) else value
        # Keep the temporary file beside the destination so replace is atomic.
        fd, temp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, target)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
        return target
