"""Release-packaging contract tests."""

from pathlib import Path
import sys


ROOT = Path(__file__).parents[1]


def test_spec_packages_the_desktop_entrypoint_as_a_windowed_app():
    """Catch packaging the legacy launcher or accidentally opening a console."""
    spec = (ROOT / "packaging" / "video_downloader.spec").read_text(encoding="utf-8")

    assert '"desktop_app" / "main.py"' in spec
    assert "console=False" in spec
    assert 'name="VideoDownloader-windows-x64"' in spec


def test_spec_collects_runtime_dependencies_and_qt_platform_plugins():
    """Catch a build that starts locally but omits required frozen-app data."""
    spec = (ROOT / "packaging" / "video_downloader.spec").read_text(encoding="utf-8")

    assert "collect_submodules(\"yt_dlp\")" in spec
    assert "collect_data_files(\"requests\")" in spec
    assert "collect_data_files(\"PySide6\", subdir=\"plugins/platforms\")" in spec
    assert "VIDEO_DOWNLOADER_FFMPEG_PATH" in spec
    assert '"ffmpeg.exe"' in spec


def test_build_script_has_stable_artifact_names_and_release_gates():
    """Catch output-name drift or bypassing tests and checksum generation."""
    script = (ROOT / "packaging" / "build_windows.ps1").read_text(encoding="utf-8")

    for output_name in (
        "VideoDownloader-windows-x64",
        "VideoDownloader-windows-x64.zip",
        "VideoDownloader-windows-x64.exe",
        "SHA256SUMS.txt",
    ):
        assert output_name in script

    assert "param(" in script
    assert "[string]$Version" in script
    assert "python -m pytest" in script
    assert script.count("python -m PyInstaller") == 2
    assert "Get-FileHash" in script


def test_build_script_verifies_downloaded_ffmpeg_before_packaging():
    """Catch accepting a corrupted or substituted FFmpeg archive."""
    script = (ROOT / "packaging" / "build_windows.ps1").read_text(encoding="utf-8")

    assert "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-8.1.2-essentials_build.zip" in script
    assert "ffmpeg-8.1.2-essentials_build.zip.sha256" in script
    assert "db580001caa24ac104c8cb856cd113a87b0a443f7bdf47d8c12b1d740584a2ec" in script
    assert "FFmpeg archive checksum mismatch" in script
    assert "ffmpeg.exe" in script


def test_application_icon_is_a_real_windows_icon():
    """Catch shipping a renamed PNG or an empty icon placeholder."""
    icon = (ROOT / "assets" / "video-downloader.ico").read_bytes()

    assert icon[:4] == b"\x00\x00\x01\x00"
    assert len(icon) > 1024


def test_version_flag_does_not_initialize_qt(monkeypatch, capsys):
    """Catch a smoke-test path that still needs a display server or event loop."""
    import desktop_app.main as desktop_main

    class UnexpectedApplication:
        @classmethod
        def instance(cls):
            raise AssertionError("--version must not initialize QApplication")

    monkeypatch.setattr(desktop_main, "QApplication", UnexpectedApplication)

    assert desktop_main.main(["--version"]) == 0
    assert capsys.readouterr().out == "Video Downloader 0.1.0\n"


def test_frozen_downloads_use_the_bundled_ffmpeg(monkeypatch, tmp_path):
    """Catch yt-dlp falling back to a separately installed system FFmpeg."""
    import desktop_app.download_core as download_core
    from desktop_app.models import DownloadRequest

    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"test executable")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert download_core.bundled_ffmpeg_path() == str(ffmpeg)

    request = DownloadRequest("https://example.test/video", tmp_path)
    options = download_core._DefaultYtdlpBackend().build_options(
        request, "bv*+ba/b", lambda data: None, None
    )

    assert options["ffmpeg_location"] == str(ffmpeg)
