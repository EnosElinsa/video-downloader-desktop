# Task 5 report: CLI/GUI compatibility and documentation

## Delivered

- Added `python -m desktop_app` through `desktop_app/__main__.py`.
- Replaced the Tkinter GUI implementation with a compatibility launcher that
  forwards `video_downloader_gui.py` to `desktop_app.main.main`.
- Kept `universal_video_downloader.py` as the legacy interactive CLI and
  preserved the `download_video` parameter list.
- Pointed the installed `video-downloader-gui` script at the PySide6 entry
  point.
- Updated the README and added `docs/windows-user-guide.md`, including cookies,
  proxy, output directory, retries, and Microsoft SmartScreen guidance.

## Verification

Run from the repository root with `QT_QPA_PLATFORM=offscreen`, no pytest cache,
and bytecode generation disabled:

```powershell
python -m pytest tests/test_entrypoints.py -q
# 4 passed
python -m pytest -q
# 39 passed
```

## Notes

- The desktop module runner opens the GUI in normal use; the automated test
  substitutes `desktop_app.main.main` so it remains headless.
- The legacy CLI continues to own its interactive format-selection path.
