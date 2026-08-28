# UI Redesign Report

## Evidence

The production shell is implemented in `desktop_app/main_window.py`, with
focused queue widgets in `desktop_app/widgets.py`, theme definitions in
`desktop_app/theme.py`, and deterministic offscreen captures from
`tools/render_ui.py`.

## Tests

The final release-hardening suite uses `QT_QPA_PLATFORM=offscreen`,
`QT_QPA_FONTDIR=C:\\Windows\\Fonts`, workspace-local `.test-tmp`, and
`python -m pytest -q -p no:cacheprovider`.

The final release-head evidence is **124 passed** across the full suite
(including the redesign regressions), replacing the earlier 64-test
intermediate count.

## Screenshots

- `.test-tmp/ui-redesign/empty-dark.png` (1366x768)
- `.test-tmp/ui-redesign/populated-dark.png` (1366x768)
- `.test-tmp/ui-redesign/populated-light.png` (1180x760)
- `.test-tmp/ui-redesign/empty-dark-1067x750.png` (1067x750)
- `.test-tmp/ui-redesign/populated-dark-1067x750.png` (1067x750)

## Deferred scope

Activity level/item filtering is explicitly post-v0.1; v0.1 provides collapsed,
clearable, secret-sanitized activity details.
