# Universal Video Downloader

A powerful Python application that can download videos from almost any website.

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

The legacy `setup.py` script remains available for the original CLI/launcher
workflow, but it is not required for the new desktop baseline.

### Manual Installation

If you prefer manual installation:

1. Install the CLI packages (or use `requirements-desktop.txt` for the desktop
   app):

```
pip install yt-dlp>=2023.3.4 requests>=2.25.0
```

2. The new desktop app uses PySide6 and does not require tkinter. The legacy
   `video_downloader_gui.py` launcher retains its tkinter dependency.

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
and launch `VideoDownloader.exe`; downloaded media and settings are kept
outside the installation directory. Initial unsigned builds may show a
Microsoft SmartScreen warning; verify the release checksum before choosing
**More info** and **Run anyway**.

### Command Line Interface

```
python universal_video_downloader.py
```

Follow the prompts to:
1. Enter the video URL
2. Choose download options
3. Configure settings like output directory and proxy

### Graphical User Interface

```
python video_downloader_gui.py
```

The GUI provides an easy-to-use interface for:
- Entering video URLs
- Selecting output directory
- Configuring proxy settings
- Monitoring download progress

## Configuration

The program saves your configuration preferences for:
- Output directory
- Proxy settings
- Format selection preferences
- Browser cookie source for authenticated videos

Configuration is stored in your home directory as `.video_downloader_config.json`.

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
6. **Legacy GUI not working**: Ensure tkinter is installed. The new PySide6
   desktop app instead requires the packages in `requirements-desktop.txt`.

The GUI always uses the automatic best-quality selector so downloads never wait
for a terminal prompt. Use the CLI if you need to choose an individual format.

## License

This software is open-source and free to use for personal purposes.

## Acknowledgments

Built with:
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - A powerful video downloader supporting many sites
- [requests](https://requests.readthedocs.io/en/latest/) - For direct URL downloading
- [PySide6](https://doc.qt.io/qtforpython-6/) - For the new desktop interface
- [tkinter](https://docs.python.org/3/library/tkinter.html) - For the legacy GUI launcher
