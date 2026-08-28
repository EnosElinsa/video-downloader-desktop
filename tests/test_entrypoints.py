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


def test_legacy_gui_launcher_exits_with_desktop_main_result(monkeypatch):
    """Catch a wrapper that imports the app but does not execute it as a script."""
    desktop_main = importlib.import_module("desktop_app.main")
    monkeypatch.setattr(desktop_main, "main", lambda: 17)

    import runpy

    with pytest.raises(SystemExit) as exit_result:
        runpy.run_module("video_downloader_gui", run_name="__main__")

    assert exit_result.value.code == 17


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


def test_release_metadata_agrees_on_v010_and_does_not_claim_tkinter_or_unlicensed_use():
    """Catch stale installer guidance and unsupported public license claims."""
    root = Path(__file__).parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8").lower()
    setup = (root / "setup.py").read_text(encoding="utf-8").lower()
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8").lower()

    assert 'version="0.1.0"' in setup
    assert 'version = "0.1.0"' in pyproject
    assert "tkinter" not in setup
    assert "always uses the automatic" not in readme
    assert "open-source and free" not in readme
    assert "best single file" in readme


def test_release_hygiene_ignores_internal_reports_and_local_inputs():
    """Catch internal review artifacts or user source material entering a release."""
    ignore = (Path(__file__).parents[1] / ".gitignore").read_text(encoding="utf-8")
    for entry in (".superpowers/sdd/", ".tools/", ".test-tmp/", ".temp-green/", ".full-temp/", ".red-temp/", ".stale-build-acl/", "source.md", "build/", "dist/"):
        assert entry in ignore


def test_installed_gui_entry_point_declares_pyside6_runtime_dependency():
    """Catch either documented installer creating a GUI script without Qt."""
    import ast
    import tomllib

    root = Path(__file__).parents[1]
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

    setup_tree = ast.parse((root / "setup.py").read_text(encoding="utf-8"))
    setup_call = next(
        node for node in ast.walk(setup_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "setup"
    )
    setup_keywords = {keyword.arg: keyword.value for keyword in setup_call.keywords}
    setup_dependencies = [item.value for item in setup_keywords["install_requires"].elts]
    entry_points = setup_keywords["entry_points"]
    console_scripts = next(
        value for key, value in zip(entry_points.keys, entry_points.values)
        if key.value == "console_scripts"
    )
    setup_scripts = [item.value for item in console_scripts.elts]

    assert any(dependency.lower().startswith("pyside6") for dependency in metadata["project"]["dependencies"])
    assert metadata["project"]["scripts"]["video-downloader-gui"] == "desktop_app.main:main"
    assert any(dependency.lower().startswith("pyside6") for dependency in setup_dependencies)
    assert "video-downloader-gui=desktop_app.main:main" in setup_scripts


def test_startup_behavior_opens_the_window_minimized_when_selected():
    """Catch a persisted startup preference that has no effect at launch."""
    from desktop_app.main import show_window

    class FakeWindow:
        def __init__(self):
            self.visible = None

        def show(self):
            self.visible = "normal"

        def showMinimized(self):
            self.visible = "minimized"

    window = FakeWindow()
    show_window(window, "minimized")

    assert window.visible == "minimized"
