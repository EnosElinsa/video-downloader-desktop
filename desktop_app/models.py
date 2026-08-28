from dataclasses import dataclass
from pathlib import Path
from typing import Literal


DownloadEventKind = Literal["metadata", "progress", "log", "finished", "failed", "cancelled"]


@dataclass(frozen=True)
class DownloadRequest:
    url: str
    output_dir: Path
    format_selector: str = "bv*+ba/b"
    use_proxy: bool = False
    proxy_url: str | None = None
    cookie_browser: str | None = None
    output_template: str | None = None


@dataclass(frozen=True)
class DownloadEvent:
    kind: DownloadEventKind
    message: str = ""
    percent: float | None = None
    speed: float | None = None
    eta: float | None = None
    title: str | None = None
    filename: str | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class DownloadResult:
    success: bool
    filename: str | None
    title: str | None
    error_code: str | None
    error_message: str | None

    def __bool__(self) -> bool:
        """Keep legacy ``if download_video(...)`` callers truthful."""
        return self.success
