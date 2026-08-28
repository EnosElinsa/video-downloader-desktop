# Task 7 Report: CI Tests and Tagged Windows Release Workflow

## Implemented

- Added `.github/workflows/ci.yml` for Windows-latest CI on pushes and pull requests.
- CI provisions Python 3.11, installs desktop and development requirements,
  runs `compileall`, and executes pytest with `QT_QPA_PLATFORM=offscreen`.
- Added `.github/workflows/release.yml` for `v*.*.*` tags and manual dispatch.
  The workflow grants `contents: write`, builds with
  `packaging/build_windows.ps1`, runs the packaged `--version` smoke test, and
  publishes the ZIP, EXE, and `SHA256SUMS.txt` with `softprops/action-gh-release`.
- Added `tests/test_workflows.py` contract tests. PyYAML is pinned in
  `requirements-dev.txt`; tests also include a small fallback parser so local
  validation works in minimal environments without PyYAML installed.
- Documented tag/manual release operation, local PowerShell builds, artifact
  names, checksums, and unsigned SmartScreen behavior in `README.md`.

## Verification

- `python -m pytest tests/test_workflows.py -q` -> **2 passed**.
- `python -m pytest -q` was started twice (including with
  `QT_QPA_PLATFORM=offscreen`); both reached the existing test suite but did
  not complete within the local timeout and were interrupted. No failure was
  reported before interruption.
- Both workflow files parse successfully through the test parser; the focused
  tests validate trigger, runner, Python version, permissions, build/smoke
  commands, and all three release artifact paths.

## Concerns

- A full test run could not be completed in this environment because Qt tests
  exceed the available command timeout. CI runs the same suite on a Windows
  runner with the offscreen platform setting.
- The initial Windows artifacts are intentionally unsigned, so SmartScreen
  warnings are expected and called out in release notes and README guidance.

## Round 1 Review Fixes

- Release publication now uses `softprops/action-gh-release@v3` and sets
  `fail_on_unmatched_files: true`, preventing an incomplete release when any
  required artifact is missing.
- Workflow contract tests assert the supported release-action major, the
  unmatched-file failure gate, all artifact names in the build script, and the
  offscreen environment on the build step.
- The release build step exports `QT_QPA_PLATFORM=offscreen`, so the
  build script's duplicate pytest gate runs under the same headless Qt
  configuration as the explicit workflow test step.
