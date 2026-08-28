# Windows user guide

## Start the desktop app

Install the desktop dependencies, then launch the PySide6 interface:

```powershell
python -m pip install -r requirements-desktop.txt
python -m desktop_app
```

The older `python video_downloader_gui.py` command is retained as a shortcut
and opens this same desktop app. Use `python universal_video_downloader.py`
when you want the legacy terminal workflow and interactive format picker.

## Output directory

Choose an output directory in the desktop window before adding downloads. Pick
a folder you can write to, such as your Videos or Downloads folder, instead of
the application installation directory. Choosing a folder with **Browse**, or
finishing an edit to the directory field, saves it immediately in local Windows
application settings. Downloads already in the queue keep the output directory
they had when added.

Open **Settings** to change the output directory, proxy, cookie browser,
concurrent-download limit, startup behavior, or light/dark theme. Selecting
**Start minimized** makes the next launch open the app minimized.

## Cookies for sign-in, age checks, and private videos

Some sites require you to be signed in. In the app settings, select the browser
that already contains your signed-in session (for example Chrome, Edge, or
Firefox), then retry the download. Keep that browser installed and signed in.

Do not copy browser cookie files into the project, a release archive, or a
support message. The app uses the selected local browser profile and should
not print cookie values in its activity log.

## Proxy

For geo-restricted content, open settings, enable the proxy option, and enter
the proxy address supplied by your provider, for example
`socks5://127.0.0.1:1080`. If the download fails, first disable the proxy and
try again; then confirm the address, protocol, and account credentials with
the provider. Treat proxy URLs as private because they can contain credentials.

## Failed downloads and retries

Failed downloads remain in the queue. Read the activity log, correct the URL,
network, cookie, or proxy problem, and choose **Retry** for that row. Retrying
immediately starts a fresh download attempt; it does not mark a download
successful until the downloader itself has completed.

The desktop app defaults to **Automatic (best)** and also offers **Best single
file** in the Quality control. Run the CLI if you need to choose a specific
format interactively.

Activity is collapsed by default and can be cleared from the drawer. Detailed
level/item filtering is planned for post-v0.1; v0.1 always applies secret
sanitization before activity is shown.

## Microsoft SmartScreen

Early Windows builds may be unsigned, so SmartScreen can display a warning.
Only use an EXE or ZIP obtained from the project's GitHub Release, verify its
SHA-256 value against the release `SHA256SUMS.txt`, and scan it with your
security software. If the checksum matches and you trust the release, choose
**More info**, then **Run anyway**. Otherwise cancel the prompt and download a
fresh copy from the release page.
