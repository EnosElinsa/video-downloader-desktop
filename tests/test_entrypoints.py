import importlib
import inspect
from pathlib import Path

import pytest


def test_desktop_package_module_runs_the_desktop_main(monkeypatch):
    """Catch a missing ``python -m desktop_app`` entry point."""
    desktop_main = importlib.import_module("desktop_app.main")

    def fake_main():
        return 23

    monkeypatch.setattr(desktop_main, "main", fake_main)

    import runpy

    with pytest.raises(SystemExit) as exit_result:
        runpy.run_module("desktop_app", run_name="__main__")

    assert exit_result.value.code == 23


def test_legacy_gui_launcher_forwards_to_desktop_main(monkeypatch):
    """Catch a regression that sends legacy GUI users back to Tkinter."""
    desktop_main = importlib.import_module("desktop_app.main")

    def fake_main():
        return 17

    monkeypatch.setattr(desktop_main, "main", fake_main)
    legacy_gui = importlib.import_module("video_downloader_gui")
    legacy_gui = importlib.reload(legacy_gui)

    assert legacy_gui.main is fake_main


def test_download_video_keeps_the_legacy_callable_parameters():
    """Catch accidental removal of CLI options consumed by existing callers."""
    from universal_video_downloader import download_video

    assert list(inspect.signature(download_video).parameters) == [
        "url",
        "output_dir",
        "use_proxy",
        "proxy_url",
        "select_format",
        "cookie_browser",
        "output_template",
    ]


def test_readme_uses_the_desktop_module_command():
    """Catch documentation that directs new GUI users to the retired Tk UI."""
    readme = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")

    assert "python -m desktop_app" in readme
