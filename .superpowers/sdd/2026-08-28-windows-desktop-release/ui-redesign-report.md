# UI Redesign Report

## Files
- `desktop_app/main_window.py`: production shell, card queue wiring, activity drawer, grouped settings dialog, stable object names.
- `desktop_app/widgets.py`: responsive DownloadCard/QueueList and compatibility progress/action adapters.
- `desktop_app/theme.py`: dark/light Fluent-inspired palette, typography, focus and state styles.
- `tools/render_ui.py`: deterministic offscreen visual QA renderer.
- `tests/test_ui_redesign.py`: object-name, card-state, drawer, settings, theme and minimum-size coverage.

## Tests
- `QT_QPA_PLATFORM=offscreen`, workspace-local `.test-tmp`, `python -m pytest -q -p no:cacheprovider`
- Result: **64 passed**.

## Screenshots
- `.test-tmp/ui-redesign/empty-dark.png` (1366x768)
- `.test-tmp/ui-redesign/populated-dark.png` (1366x768)
- `.test-tmp/ui-redesign/populated-light.png` (1180x760)

## Visual decisions
- 68px header with real application icon, theme toggle, settings action, and queue summary.
- Compact composer with multiline URL field, output folder, quality selector, and primary Add to queue action.
- Scrollable state-aware cards replace the clipped table; action buttons are icon-only with tooltips and stable accessible names.
- Empty queue is centered and purposeful; activity is collapsed by default and clears from inside its drawer.
- Settings are split into General and Network & access groups with Save/Cancel semantics.

## Known deviations
- Offscreen CI image inspection shows square glyph placeholders because this host's Qt runtime reports a missing font directory; the stylesheet requests Segoe UI Variable/Segoe UI and renders normally on Windows 10/11.

## Commit
- `b18ea581d2bc1696a512effe3d73f9458ec5cbd5`
