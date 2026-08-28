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
        return cls(**values)

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
