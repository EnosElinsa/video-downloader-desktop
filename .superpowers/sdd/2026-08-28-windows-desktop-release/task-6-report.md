# Task 6 packaging report

Date: 2026-08-28

## Implemented

- `packaging/video_downloader.spec` builds the `desktop_app.main` entry point in both one-folder and one-file modes, with `console=False`, the application icon, PySide6 platform plugins, yt-dlp/requests data and hidden imports, plus verified FFmpeg/ffprobe binaries.
- `packaging/build_windows.ps1 -Version <version>` runs the full pytest gate, uses repository-local `build/tmp` for `TEMP`/`TMP`, pins and SHA-256 verifies the Gyan FFmpeg 8.1.2 essentials archive when PATH does not contain FFmpeg, performs two PyInstaller invocations, writes a deterministic ZIP and `dist/SHA256SUMS.txt`.
- `packaging/smoke_test.py` executes a frozen executable with `--version` and validates the expected output/version.
- `desktop_app.main.main(argv)` now handles `--version` before creating `QApplication`; `desktop_app.download_core` points frozen yt-dlp runs at the bundled FFmpeg.
- `assets/video-downloader.ico` is a deterministic 16/24/32/48/64/128/256px ICO generated from `packaging/generate_icon.py`.

## Verification

### TDD and tests

- RED: `python -m pytest tests/test_packaging_config.py -q` failed with six expected missing-file/API failures before implementation.
- GREEN: `python -m pytest tests/test_packaging_config.py -q` -> `7 passed`.
- Full non-Qt/packaging regression run -> `53 passed` before the build gate.
- The build script's own test gate -> `53 passed` (two pytest cache warnings caused by the sandbox-owned cache directory).
- A post-build packaging-only run with a workspace-local temp directory and `-p no:cacheprovider` -> `7 passed`.

### Build and smoke

Command: `pwsh -NoProfile -File packaging/build_windows.ps1 -Version 0.1.0`

- One-folder output: `dist/VideoDownloader-windows-x64/` (232 files, 327,763,784 bytes); bundled `ffmpeg.exe` 101,897,728 bytes and `ffprobe.exe` 101,692,928 bytes.
- ZIP: `dist/VideoDownloader-windows-x64.zip` (133,305,909 bytes)
  - SHA-256: `bed9e271ecf3cd0935bcfa171a156bc616793d92eb1d33ff3b1687cc7382af48`
- One-file executable: `dist/VideoDownloader-windows-x64.exe` (129,410,811 bytes)
  - SHA-256: `82465c1b75aeadd713dbc0a33516621c91c33e6d6db3ade15dcc36ede137110c`
- Checksums: `dist/SHA256SUMS.txt` contains the exact two hashes above.
- `python packaging/smoke_test.py --exe dist/VideoDownloader-windows-x64.exe --expected-version 0.1.0` -> `Video Downloader 0.1.0`, exit 0.
- `python packaging/smoke_test.py --exe dist/VideoDownloader-windows-x64/VideoDownloader-windows-x64.exe --expected-version 0.1.0` -> `Video Downloader 0.1.0`, exit 0.

## Concerns

- This host initially blocked HTTPS sockets in the default sandbox; the build was rerun with approved elevated network access. The downloaded archive was checked against both the vendor `.sha256` endpoint and the pinned digest before extraction.
- PyInstaller emitted non-fatal collection warnings for browser-only `urllib3.contrib.emscripten` (`js` is unavailable) and non-package `curl_cffi`/`yt_dlp_ejs` data collection. The Windows build completed and both frozen `--version` smoke tests passed.
- Full Qt widget tests hang in this restricted headless host even with `QT_QPA_PLATFORM=offscreen`; the packaging test, all non-Qt tests, and the build's test gate were independently verified. CI should run the complete suite on a normal Windows runner.
- Build outputs are intentionally ignored by `.gitignore`; no binary FFmpeg or credentials are committed.
