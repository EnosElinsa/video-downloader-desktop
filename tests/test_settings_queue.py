import json
from pathlib import Path

import pytest

from desktop_app.models import DownloadRequest
from desktop_app.queue import DownloadQueue
from desktop_app.settings import AppSettings


def test_settings_defaults_and_migration(tmp_path, monkeypatch):
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    settings = AppSettings.load()
    assert settings.cookie_browser is None
    assert settings.output_dir == local / "VideoDownloader" / "videos"
    settings.save()
    payload = json.loads((local / "VideoDownloader" / "settings.json").read_text())
    assert payload["version"] == AppSettings.VERSION
    payload.pop("cookie_browser", None)
    (local / "VideoDownloader" / "settings.json").write_text(json.dumps(payload))
    assert AppSettings.load().cookie_browser is None


def test_settings_future_schema_is_ignored_without_downgrade(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"version": AppSettings.VERSION + 1, "output_dir": "future"}))
    loaded = AppSettings.load(path)
    assert loaded.output_dir == AppSettings.default_output_dir()
    loaded.save(path)
    assert json.loads(path.read_text())["version"] == AppSettings.VERSION


@pytest.mark.parametrize("version", [1.5, True, "1"])
def test_settings_malformed_schema_version_uses_safe_defaults(tmp_path, version):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"version": version, "output_dir": "malformed"}))
    loaded = AppSettings.load(path)
    assert loaded.output_dir == AppSettings.default_output_dir()


def test_settings_save_is_atomic_and_custom_path(tmp_path):
    path = tmp_path / "nested" / "settings.json"
    settings = AppSettings(output_dir=tmp_path / "downloads", cookie_browser="chrome")
    settings.save(path)
    loaded = AppSettings.load(path)
    assert loaded.output_dir == tmp_path / "downloads"
    assert loaded.cookie_browser == "chrome"
    assert not path.with_suffix(".tmp").exists()


def test_queue_ids_retry_and_sanitized_snapshot(tmp_path):
    request = DownloadRequest("https://example.test", tmp_path, proxy_url="http://secret", cookie_browser="chrome")
    queue = DownloadQueue()
    item_id = queue.add(request)
    assert queue.snapshot()[0]["status"] == "queued"
    queue.update_status(item_id, "running")
    queue.update_status(item_id, "failed", error="nope")
    queue.retry(item_id)
    assert item_id in queue
    assert queue.snapshot()[0]["status"] == "queued"
    snapshot = queue.snapshot()[0]
    assert "cookie_browser" not in snapshot and "proxy_url" not in snapshot
    assert snapshot["error"] is None


def test_queue_validates_transitions_and_remove(tmp_path):
    queue = DownloadQueue()
    item_id = queue.add(DownloadRequest("https://example.test", tmp_path))
    queue.update_status(item_id, "running")
    queue.cancel(item_id)
    assert queue.snapshot()[0]["status"] == "cancelled"
    with pytest.raises(ValueError):
        queue.cancel(item_id)
    queue.remove(item_id)
    assert queue.snapshot() == []


def test_queue_get_exposes_item_without_private_storage_access(tmp_path):
    queue = DownloadQueue()
    request = DownloadRequest("https://example.test", tmp_path)
    item_id = queue.add(request)

    item = queue.get(item_id)

    assert item.id == item_id
    assert item.request is request
    with pytest.raises(KeyError, match="unknown queue item"):
        queue.get("missing")


def test_queue_replaces_a_queued_request_before_retry(tmp_path):
    queue = DownloadQueue()
    item_id = queue.add(DownloadRequest("https://example.test", tmp_path))
    replacement = DownloadRequest(
        "https://example.test", tmp_path / "new-output", use_proxy=True,
        proxy_url="socks5://127.0.0.1:1080", cookie_browser="firefox",
        format_selector="best",
    )

    queue.replace_request(item_id, replacement)

    assert queue.get(item_id).request == replacement
