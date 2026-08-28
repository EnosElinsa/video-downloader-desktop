"""Render deterministic UI states for release visual QA."""
from pathlib import Path
import os
import sys
ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
from PySide6.QtWidgets import QApplication
from desktop_app.main_window import MainWindow
from desktop_app.models import DownloadResult
from desktop_app.settings import AppSettings
from desktop_app.settings_dialog import SettingsDialog
from desktop_app.theme import stylesheet

OUT = ROOT / ".test-tmp" / "ui-redesign"

class RenderService:
    def download(self, request, emit, cancel=None):
        return DownloadResult(False, None, None, "download_failed", "render")

def make(mode, size, name, populated=False):
    settings = AppSettings(output_dir=ROOT / ".test-tmp" / "videos", theme=mode)
    window = MainWindow(settings, RenderService()); window.resize(*size); window.show()
    if populated:
        window.add_urls("https://www.youtube.com/watch?v=release-demo\nhttps://vimeo.com/123456\nhttps://example.test/failed")
        cards = [window.queue_list.card_at(i) for i in range(3)]
        for card, status, percent in zip(cards, ("queued", "running", "failed"), (0, 54, 100)):
            if status == "running": window.queue.update_status(card.item_id, "running", percent=percent, speed=1_250, eta=38)
            elif status == "failed": window.queue.update_status(card.item_id, "running"); window.queue.update_status(card.item_id, "failed", percent=percent, error="Network unavailable")
            window._set_status(card.item_id, status)
        window._log("Download failed: network unavailable")
        # Keep the activity drawer collapsed in the queue-focused release captures.
        window.activity_drawer.hide()
    QApplication.processEvents()
    OUT.mkdir(parents=True, exist_ok=True)
    window.grab().save(str(OUT / name))
    window.close(); window.deleteLater(); QApplication.processEvents()

def make_compact_running(name, *, activity=False):
    settings = AppSettings(output_dir=ROOT / ".test-tmp" / "videos", theme="dark")
    window = MainWindow(settings, RenderService()); window.resize(1002, 691); window.show()
    window.add_urls("https://www.rockstargames.com/videos/rk721912")
    item_id = window.queue.snapshot()[0]["id"]
    window.queue.update_status(item_id, "running", percent=8, speed=4_390_000, eta=522)
    window._set_status(item_id, "running")
    window._log("[download] 8.0% of 2.32GiB at 4.19MiB/s ETA 08:42")
    if activity:
        window.activity_toggle.click()
    QApplication.processEvents()
    OUT.mkdir(parents=True, exist_ok=True)
    window.grab().save(str(OUT / name))
    window.close(); window.deleteLater(); QApplication.processEvents()

def make_settings():
    settings = AppSettings(output_dir=ROOT / ".test-tmp" / "videos", theme="dark")
    dialog = SettingsDialog(settings)
    dialog.setStyleSheet(stylesheet("dark"))
    dialog.show(); QApplication.processEvents()
    OUT.mkdir(parents=True, exist_ok=True)
    dialog.grab().save(str(OUT / "settings-dark.png"))
    dialog.close(); dialog.deleteLater(); QApplication.processEvents()

if __name__ == "__main__":
    app = QApplication.instance() or QApplication([])
    make("dark", (1366, 768), "empty-dark.png")
    make("dark", (1366, 768), "populated-dark.png", True)
    make("light", (1180, 760), "populated-light.png", True)
    make("dark", (1067, 750), "empty-dark-1067x750.png")
    make("dark", (1067, 750), "populated-dark-1067x750.png", True)
    make_compact_running("compact-running-dark-1002x691.png")
    make_compact_running("compact-activity-dark-1002x691.png", activity=True)
    make_settings()
