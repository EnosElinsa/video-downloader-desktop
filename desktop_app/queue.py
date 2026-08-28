"""Thread-safe in-memory download queue state."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from threading import RLock
from typing import Any
from uuid import uuid4

from .models import DownloadRequest

STATUSES = frozenset({"queued", "running", "paused", "success", "failed", "cancelled"})
_TRANSITIONS = {
    "queued": {"running", "cancelled"},
    "running": {"paused", "success", "failed", "cancelled"},
    "paused": {"running", "cancelled"},
    "success": set(),
    "failed": set(),
    "cancelled": set(),
}


@dataclass
class QueueItem:
    id: str
    request: DownloadRequest
    status: str = "queued"
    title: str | None = None
    percent: float | None = None
    speed: float | None = None
    eta: float | None = None
    filename: str | None = None
    error: str | None = None
    error_code: str | None = None


class DownloadQueue:
    def __init__(self) -> None:
        self._items: OrderedDict[str, QueueItem] = OrderedDict()
        self._lock = RLock()

    def __contains__(self, item_id: str) -> bool:
        with self._lock:
            return item_id in self._items

    def add(self, request: DownloadRequest) -> str:
        if not isinstance(request, DownloadRequest):
            raise TypeError("request must be a DownloadRequest")
        with self._lock:
            item_id = uuid4().hex
            self._items[item_id] = QueueItem(item_id, request)
            return item_id

    def _item(self, item_id: str) -> QueueItem:
        try:
            return self._items[item_id]
        except KeyError:
            raise KeyError(f"unknown queue item: {item_id}") from None

    def update_status(self, item_id: str, status: str, **updates: Any) -> None:
        if status not in STATUSES:
            raise ValueError(f"invalid queue status: {status}")
        with self._lock:
            item = self._item(item_id)
            if status != item.status and status not in _TRANSITIONS[item.status]:
                raise ValueError(f"cannot transition {item.status} to {status}")
            item.status = status
            for key, value in updates.items():
                if key not in {"title", "percent", "speed", "eta", "filename", "error", "error_code"}:
                    raise ValueError(f"invalid queue field: {key}")
                setattr(item, key, value)

    def cancel(self, item_id: str) -> None:
        with self._lock:
            item = self._item(item_id)
            if item.status not in {"queued", "running", "paused"}:
                raise ValueError(f"cannot cancel {item.status} item")
            item.status = "cancelled"

    def retry(self, item_id: str) -> None:
        with self._lock:
            item = self._item(item_id)
            if item.status not in {"failed", "cancelled"}:
                raise ValueError(f"cannot retry {item.status} item")
            item.status = "queued"
            item.title = item.percent = item.speed = item.eta = item.filename = None
            item.error = item.error_code = None

    def remove(self, item_id: str) -> None:
        with self._lock:
            self._item(item_id)
            del self._items[item_id]

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {"id": i.id, "url": i.request.url, "output_dir": str(i.request.output_dir),
                 "format_selector": i.request.format_selector, "status": i.status,
                 "title": i.title, "percent": i.percent, "speed": i.speed, "eta": i.eta,
                 "filename": i.filename, "error": i.error, "error_code": i.error_code}
                for i in self._items.values()
            ]
