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

## Round 1 review fixes

- Added `packaging/build_checks.py` architecture/toolchain validation. The PowerShell build now fails before cleanup unless running Windows x64 (`win32`, AMD64/x86_64, 64-bit Python), Python 3.11–3.13, and PyInstaller 6.14.2.
- Corrected README ZIP instructions to launch the shipped inner path `VideoDownloader-windows-x64\\VideoDownloader-windows-x64.exe`.
- Custom `-FFmpegPath` handling now resolves before build cleanup and optional license/README discovery only checks the executable directory plus an immediate `bin` parent; ACL errors or whole-drive recursion cannot abort the build.
- Expanded packaging tests to 11 cases covering invalid architecture/toolchains, smoke failure, checksum parsing/coverage, ZIP executable layout, and the safe FFmpeg helper.

Round 1 verification: focused packaging tests `11 passed`; rebuilt both artifacts with the pinned FFmpeg downloader and architecture guard; build gate `57 passed` (two pre-existing pytest cache permission warnings); both one-folder and one-file smoke tests returned `Video Downloader 0.1.0`; checksum manifest matched the rebuilt ZIP/EXE exactly. The custom-path staging fix was exercised by the build script's path resolution before cleanup (the source path may reside under `build`/`dist`).

## Repeat-build temporary directory fix

- Moved build-time `TEMP`/`TMP` from the cleaned `build/tmp` tree to a unique, git-ignored `.test-tmp/packaging-temp/run-<guid>` directory. The script creates and validates this workspace-local path before cleaning only `build/` and `dist/`; it never recursively deletes `.test-tmp` or user/source directories.
- The build gate now always uses Qt offscreen mode, `C:\Windows\Fonts`, and disables pytest's cache provider, avoiding both display/font drift and repository-cache ACL warnings.
- Added a static regression contract that rejects any return to `$buildRoot/tmp` and asserts both temporary environment variables use the external run directory.
- Verification: focused packaging suite `12 passed`; complete suite with `QT_QPA_PLATFORM=offscreen`, `QT_QPA_FONTDIR=C:\Windows\Fonts`, workspace-local temp, and no pytest cache `72 passed`.
- Executed two complete builds back-to-back. The second used the first build's `dist/.../ffmpeg.exe` via `-FFmpegPath`, safely staged it before `build/dist` cleanup, passed the 72-test gate, rebuilt both artifacts, and passed both frozen `--version` smoke tests. This directly reproduces and clears the prior repeat-run failure mode.
