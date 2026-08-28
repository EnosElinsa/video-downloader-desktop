"""PyInstaller specification for the portable and single-file Windows builds."""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


ROOT = Path(SPECPATH).resolve().parent
BUILD_MODE = os.environ.get("VIDEO_DOWNLOADER_BUILD_MODE", "onedir")
GENERATED_DIR = Path(os.environ["VIDEO_DOWNLOADER_GENERATED_DIR"]).resolve()
FFMPEG_PATH = Path(os.environ["VIDEO_DOWNLOADER_FFMPEG_PATH"]).resolve()

if BUILD_MODE not in {"onedir", "onefile"}:
    raise ValueError(f"Unsupported VIDEO_DOWNLOADER_BUILD_MODE: {BUILD_MODE}")
if not FFMPEG_PATH.is_file() or FFMPEG_PATH.name.lower() != "ffmpeg.exe":
    raise FileNotFoundError(f"A verified ffmpeg.exe is required: {FFMPEG_PATH}")

datas = []
icon_path = ROOT / "assets" / "video-downloader.ico"
if not icon_path.is_file():
    raise FileNotFoundError(f"Runtime icon is required: {icon_path}")
datas.append((str(icon_path), "assets"))
datas += collect_data_files("PySide6", subdir="plugins/platforms")
datas += collect_data_files("yt_dlp")
datas += collect_data_files("requests")

for variable in ("VIDEO_DOWNLOADER_FFMPEG_LICENSE", "VIDEO_DOWNLOADER_FFMPEG_README"):
    document = os.environ.get(variable)
    if document and Path(document).is_file():
        datas.append((document, "third_party/ffmpeg"))

binaries = [(str(FFMPEG_PATH), ".")]
ffprobe_path = FFMPEG_PATH.with_name("ffprobe.exe")
if ffprobe_path.is_file():
    binaries.append((str(ffprobe_path), "."))

hiddenimports = sorted(
    set(
        collect_submodules("yt_dlp")
        + collect_submodules("requests")
        + ["video_downloader_build_version"]
    )
)

analysis = Analysis(
    [str(ROOT / "desktop_app" / "main.py")],
    pathex=[str(ROOT), str(GENERATED_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)

exe_options = dict(
    name="VideoDownloader-windows-x64",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ROOT / "assets" / "video-downloader.ico"),
)

if BUILD_MODE == "onefile":
    app = EXE(
        pyz,
        analysis.scripts,
        analysis.binaries,
        analysis.datas,
        [],
        **exe_options,
    )
else:
    app = EXE(
        pyz,
        analysis.scripts,
        [],
        exclude_binaries=True,
        contents_directory=".",
        **exe_options,
    )
    bundle = COLLECT(
        app,
        analysis.binaries,
        analysis.datas,
        strip=False,
        upx=False,
        name="VideoDownloader-windows-x64",
    )
