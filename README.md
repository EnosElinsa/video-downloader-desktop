# Universal Video Downloader

A powerful Python application that can download videos from almost any website.

Public repository: [EnosElinsa/video-downloader-desktop](https://github.com/EnosElinsa/video-downloader-desktop) · [Download the latest Windows release](https://github.com/EnosElinsa/video-downloader-desktop/releases/latest)

## Features

- **Wide compatibility**: Downloads videos from YouTube, Bilibili, Vimeo, Twitter, Instagram, and many more sites
- **Format selection**: Choose video resolution, quality, and format before downloading
- **Proxy support**: Use proxies to bypass geo-restrictions
- **GUI and CLI**: Both graphical and command-line interfaces available
- **Progress tracking**: Real-time download progress and speed information
- **Fallback methods**: Multiple download strategies for maximum compatibility
- **Robust URL handling**: Accepts URLs copied from Markdown links and chat apps
- **Rockstar Games support**: Resolves `/videos/<id>` pages to their public CDN files
- **Authentication support**: Can read cookies from Chrome, Edge, Firefox, Brave, Opera, or Chromium

## Installation

### Quick Setup

1. Make sure you have Python 3.11 or newer installed.
2. Install the desktop runtime dependencies:

```
python -m pip install -r requirements-desktop.txt
```

The package provides desktop, terminal, and Markdown batch entry points from
the same `desktop_app` codebase.

### Manual Installation

If you prefer manual installation:

1. Install the CLI packages (or use `requirements-desktop.txt` for the desktop
   app):

```
pip install yt-dlp>=2023.3.4 requests>=2.25.0
```

2. The desktop app uses PySide6.

## Usage

### Local development

The desktop application targets Python 3.11 or newer. Create an isolated
environment and install the development dependencies:

```
python -m venv .venv
.venv\\Scripts\\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The CLI-only runtime remains available through `requirements.txt`; install
`requirements-desktop.txt` when working on the PySide6 desktop application.

### Windows release artifacts

Windows 10/11 x64 builds are distributed as a portable one-folder ZIP and a
convenience EXE from GitHub Releases. Extract the ZIP to a writable location
and launch `VideoDownloader-windows-x64\VideoDownloader-windows-x64.exe`; downloaded media and settings are kept
outside the installation directory. Initial unsigned builds may show a
Microsoft SmartScreen warning; verify the release checksum before choosing
**More info** and **Run anyway**.

#### Building and publishing a release

Push a semantic-version tag (for example, `v0.1.1`) to run the Windows release
workflow. It installs Python 3.11 and the desktop/development requirements,
runs the offscreen test suite, compiles the desktop package, executes packaged
`--version` and offscreen GUI launch probes for both artifact forms, and attaches these files to the GitHub
Release:

```
VideoDownloader-windows-x64.zip
VideoDownloader-windows-x64.exe
SHA256SUMS.txt
```

Repository maintainers can also start the workflow with **Run workflow** and
provide a semantic version. To build locally on Windows, use PowerShell:

```
python -m pip install -r requirements-desktop.txt
python -m pip install -r requirements-dev.txt
./packaging/build_windows.ps1 -Version 0.1.1
```

The normal release build ignores any `ffmpeg.exe` on `PATH` and downloads the
pinned SHA-256-verified FFmpeg distribution. Advanced `-FFmpegPath` use requires
an adjacent `ffmpeg.exe.sha256`, adjacent license/provenance documentation, and
an exact digest listed in `VIDEO_DOWNLOADER_ALLOWED_FFMPEG_SHA256`.

The initial Windows 10/11 artifacts are unsigned, so SmartScreen may warn
users on first launch. Verify `SHA256SUMS.txt` against the downloaded ZIP or
EXE before running it.

### Command Line Interface

```
python -m desktop_app.cli
```

Follow the prompts to:
1. Enter the video URL
2. Choose download options
3. Configure settings like output directory and proxy

### Graphical User Interface

```
python -m desktop_app
```

The GUI provides an easy-to-use interface for:
- Entering video URLs
- Selecting output directory
- Configuring proxy settings
- Monitoring download progress

See [the Windows user guide](docs/windows-user-guide.md)
for cookies, proxy, output-directory, retry, and SmartScreen guidance.

### Markdown batch downloader

```powershell
python -m desktop_app.batch --source input.md --output videos
```

This optional command retains the structured chapter/section batch workflow
without maintaining a separate legacy script.

## Configuration

The program saves your configuration preferences for:
- Output directory
- Proxy settings
- Format selection preferences
- Browser cookie source for authenticated videos

The desktop app stores its settings under `%LOCALAPPDATA%\VideoDownloader`.
The terminal CLI stores its independent preferences in the user's home folder.

## Supported Sites

The downloader supports a wide range of websites including:

- YouTube
- Bilibili
- Twitter
- Facebook
- Instagram
- TikTok
- Vimeo
- DailyMotion
- Twitch
- And many more!

For direct video links (URLs ending with .mp4, .webm, etc.), the downloader will use direct download methods.

## Troubleshooting

If you encounter issues:

1. **Bilibili reports “Requested format is not available”**: The downloader now retries with `bv*+ba/b`, which supports Bilibili's separate video/audio streams. Update yt-dlp with `python -m pip install -U yt-dlp` if the site has changed.
2. **YouTube reports “Sign in to confirm your age”**: In the GUI choose the browser under **Cookies from browser**, then retry while that browser is installed and logged in. The CLI has the same setting under `c` → `5`.
3. **Rockstar page is unsupported**: The downloader recognizes current `/videos/<id>` pages and tries the public CDN variants (including the requested `resolution` query). If a variant is unavailable it falls back through lower resolutions.
4. **Geo-restricted content**: Configure a proxy.
5. **Dependencies issues**: Run `pip install -r requirements.txt`.
6. **Desktop app will not start**: Install the packages in
   `requirements-desktop.txt` and launch it with `python -m desktop_app`.

The GUI defaults to **Automatic (best)** and also offers **Best single file**.
Use the CLI if you need to choose an individual format interactively.

## License

No license is granted by this repository yet. Add a license before redistributing
the source or artifacts.

## Acknowledgments

Built with:
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - A powerful video downloader supporting many sites
- [requests](https://requests.readthedocs.io/en/latest/) - For direct URL downloading
- [PySide6](https://doc.qt.io/qtforpython-6/) - For the new desktop interface
