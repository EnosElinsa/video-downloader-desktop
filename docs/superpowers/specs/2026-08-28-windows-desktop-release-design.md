# Video Downloader Desktop — Windows 10/11 Design

## Goal

Turn the existing Python CLI downloader into a polished Windows 10/11
desktop application. The application keeps the existing yt-dlp-based download
capabilities, adds a responsive modern UI, and produces release artifacts that
users can download and run without installing Python.

The first release is Windows-only. GitHub Pages is not part of this product;
the public GitHub repository hosts source code and GitHub Releases host the
compiled desktop artifacts.

## Architecture

The application is split into three layers:

1. **Download core** — the downloader logic under `desktop_app`, exposed
   behind a small service interface. It owns URL normalization, site
   detection, yt-dlp options, cookies, proxies, retries, direct media fallback,
   and structured progress/error events. It must not import Qt or touch widgets.
2. **Desktop UI** — a PySide6 application that owns windows, settings, the
   download queue, progress presentation, and user actions. Each download runs
   in a worker (`QThreadPool`/`QRunnable` or an equivalent Qt-safe abstraction)
   and reports events to the UI thread.
3. **Packaging/release** — PyInstaller creates a portable Windows build. A
   GitHub Actions workflow builds both a one-folder ZIP (primary artifact) and
   a one-file EXE (convenience artifact), calculates SHA-256 checksums, and
   publishes them on version tags.

The existing command-line entry point remains available for diagnostics and
batch use. The batch extractor calls the same download-core service so behavior
does not diverge between CLI and GUI.

## User interface

The main window uses a restrained modern layout:

- Header with application name, settings button, and a primary “Add URL” action.
- URL composer with paste-friendly input, optional format/resolution hint, and
  output-directory selection.
- Queue table showing URL/title, site, selected quality, progress, speed, and
  status. Rows expose retry, open-folder, and remove actions.
- Bottom activity panel with sanitized logs and a clear-log action. Level/item
  filtering is planned for post-v0.1.
- Settings dialog for output directory, proxy, browser cookies, concurrent
  downloads, and startup behavior.
- Dark theme by default with a light-theme option, keyboard focus states, and
  Windows high-DPI scaling.

The GUI never calls `input()` and never blocks the event loop. Format selection
is represented by a GUI control; when the user leaves it on automatic, the core
uses `bv*+ba/b`. The CLI keeps its interactive format picker.

## Download flow

1. The user pastes one or more URLs.
2. The UI normalizes Markdown/chat formatting and validates the URL.
3. A queue item is created immediately with a cancellable worker.
4. The core tries site-specific handling first (including Rockstar CDN URL
   resolution), then yt-dlp with resilient format/retry options, then direct
   page-media fallback when appropriate.
5. Progress, metadata, warnings, and errors are emitted as typed events.
6. The UI updates only from those events and marks success only when the core
   completes without an exception.
7. Failed items remain in the queue with an actionable error and a retry action.

Cookies are read from a user-selected local browser profile and are never
written to the repository, logs, crash reports, or release artifacts. Proxy
values are stored in the local app configuration only.

## Configuration and data

Settings are stored under the Windows per-user application data directory (not
the repository and not the current working directory). The configuration is
versioned so future releases can migrate it safely. Download history contains
metadata and status only; it does not copy cookies.

## Packaging

PyInstaller is the packaging tool. The build must:

- target `windows-x64` on a pinned Python version supported by PySide6;
- include Qt platform plugins and the application icon;
- include a bundled FFmpeg binary if the selected yt-dlp workflows require
  merging separate streams;
- write downloads outside the installation directory by default;
- produce a smoke-testable executable before uploading artifacts.

The one-folder ZIP is the recommended artifact because it starts faster and is
less likely to trigger antivirus heuristics. The one-file EXE is also uploaded
for convenience. Neither artifact is code-signed in the initial release; the
release notes must state that Windows SmartScreen may show an unknown-publisher
warning.

## GitHub repository and release workflow

The repository will be public and named `video-downloader-desktop`. The local
checkout will be initialized as a Git repository, with a Python-focused
`.gitignore`, README, license placeholder only if the user chooses one, and no
cookies, downloaded media, build output, or local configuration files.

The workflow will:

1. run unit tests and compile checks on pushes and pull requests;
2. build Windows artifacts on a version tag such as `v0.1.0`;
3. run an executable smoke test (`--version` or equivalent headless check);
4. generate `SHA256SUMS.txt`;
5. create/update the GitHub Release and upload the ZIP, EXE, and checksums.

GitHub CLI installation and authentication are interactive. If `gh auth login`
requires a browser or device-code confirmation, the user will complete that
step; no token will be written into project files or shown in logs.

## Error handling

Errors are classified into invalid input, unavailable format, authentication/
cookies, network/proxy, missing FFmpeg, and unsupported site. Each class gets a
short UI message plus a detailed expandable log entry. Format errors retry with
the automatic selector. Authentication errors explain how to choose a browser
profile. Network errors use bounded retries and leave the item retryable.

No fallback may report success unless the underlying downloader returns without
an error. Partial files use temporary extensions and are cleaned or retained
explicitly for resume.

## Testing

- Unit tests cover URL normalization, site-specific URL generation, yt-dlp
  option construction, format fallback, browser-cookie propagation, queue state
  transitions, and structured error classification.
- UI tests use a headless Qt platform to verify adding a URL, starting/canceling
  a queue item, retrying a failed item, and displaying progress/error states.
- Packaging tests build the PyInstaller bundle and launch it in a clean
  Windows runner with a non-interactive smoke-test command.
- A manual Windows checklist verifies high-DPI layout, dark/light themes,
  browser cookie access, proxy operation, resume behavior, and opening the
  output folder.

## Acceptance criteria

The work is complete when a clean Windows 10/11 machine can download the ZIP,
extract it, launch the application without Python, add a supported URL, see
live progress, and find the resulting file in the configured output directory.
The public repository contains no local secrets or media, and a tagged commit
produces a GitHub Release with both requested runnable artifacts and checksums.
