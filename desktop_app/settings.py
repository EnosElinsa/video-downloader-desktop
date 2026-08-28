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
        if self.output_dir is None:
            self.output_dir = self.default_output_dir()
        else:
            self.output_dir = Path(self.output_dir)

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
        # Version 0 files had no version and may omit fields introduced later.
        values = {f.name: raw[f.name] for f in fields(cls) if f.name in raw}
        values.pop("VERSION", None)
        return cls(**values)

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
