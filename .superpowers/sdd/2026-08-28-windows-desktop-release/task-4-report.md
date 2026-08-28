# Task 4 report — modern PySide6 desktop shell

## Implemented

- Added `desktop_app.main.main()` as the Qt application entry point.
- Added a `QMainWindow` shell with a Windows-friendly header, dark/light theme selector, URL composer, output-directory picker, format selector, queue table, and activity log.
- Multiline URL input creates one `DownloadRequest` and queue row per non-empty line.
- Added a reusable progress cell and row actions for retry, cancel, open-folder, and remove.
- Added `QThreadPool`/`QRunnable` workers with a cancellation `threading.Event`.
- Worker signals (`event`, `finished`, `failed`) are delivered to the GUI thread; workers never access widgets.
- Queue transitions are driven by typed `DownloadEvent`/`DownloadResult` values. Late events after cancellation are ignored, and duplicate starts are prevented while a worker is active.
- Output folders are opened with `QDesktopServices.openUrl`.

## Tests

- `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_main_window.py -q` → **4 passed**.
- `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_main_window.py tests/test_download_core.py tests/test_settings_queue.py -q` → **18 passed**.
- `QT_QPA_PLATFORM=offscreen python -m pytest -q -p no:cacheprovider` → **30 passed**.
- `python -m compileall -q desktop_app` → passed.

## Concerns / follow-up

- The header Settings action currently persists the current settings and is intentionally non-blocking; a full modal settings editor for proxy, cookies, concurrency, and startup behavior can be added in a later task without changing the worker boundary.
- The queue is in-memory for this shell; persistent history is outside Task 4 and remains owned by the settings/queue layer.

## Round 1 review fixes

- Replaced lambda-based worker connections with `WorkerBridge` QObject receivers and explicit `Qt.QueuedConnection` links for event, finished, and failed signals.
- Added sender/bridge identity filtering and invalidation on retry, preventing late callbacks from a cancelled run from mutating or completing the retried row.
- Added regression coverage for GUI-thread event delivery and cancel→retry→late-event races.
