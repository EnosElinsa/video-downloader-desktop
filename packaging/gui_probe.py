"""Headless GUI launch probe for source and frozen Windows artifacts."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

from desktop_app.download_core import DownloadService
from desktop_app.main_window import MainWindow
from desktop_app.settings import AppSettings


def _probe_current_process(output_dir: str) -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = MainWindow(AppSettings(output_dir=output_dir), DownloadService())
    window.show()
    app.processEvents()
    image = window.grab()
    pixmap = window.header_icon_mark.pixmap()
    platform_name = app.platformName()
    if (
        image.isNull()
        or pixmap is None
        or pixmap.isNull()
        or not window.isVisible()
        or not platform_name
    ):
        return 1
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe")
    parser.add_argument("--output-dir", default=".")
    args = parser.parse_args(argv)
    if args.exe:
        executable = Path(args.exe).resolve()
        if not executable.is_file():
            return 2
        try:
            result = subprocess.run(
                [str(executable), "--gui-probe", "--output-dir", args.output_dir],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return 1
        return result.returncode
    return _probe_current_process(args.output_dir)


if __name__ == "__main__":
    raise SystemExit(main())
