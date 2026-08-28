from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import uuid4


DownloadEventKind = Literal["metadata", "progress", "log", "finished", "failed", "cancelled"]
DownloadErrorCode = Literal[
    "invalid_url",
    "format_unavailable",
    "auth_required",
    "network_error",
    "proxy_error",
    "ffmpeg_missing",
    "unsupported_site",
    "cancelled",
    "download_failed",
]


@dataclass(frozen=True)
class DownloadRequest:
    url: str
    output_dir: Path
    format_selector: str = "bv*+ba/b"
    use_proxy: bool = False
    proxy_url: str | None = None
    cookie_browser: str | None = None
    output_template: str | None = None
    def __post_init__(self) -> None:
        # Keep the public constructor compatible with the original seven
        # fields while giving each logical request a stable private token.
        object.__setattr__(self, "_request_id", uuid4().hex)

    @property
    def request_id(self) -> str:
        return self._request_id


@dataclass(frozen=True)
class DownloadEvent:
    kind: DownloadEventKind
    message: str = ""
    percent: float | None = None
    speed: float | None = None
    eta: float | None = None
    title: str | None = None
    filename: str | None = None
    error_code: DownloadErrorCode | None = None


@dataclass(frozen=True)
class DownloadResult:
    success: bool
    filename: str | None
    title: str | None
    error_code: DownloadErrorCode | None
    error_message: str | None

    def __bool__(self) -> bool:
        """Keep legacy ``if download_video(...)`` callers truthful."""
        return self.success
