"""Focused queue and progress widgets used by the main window."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .errors import guidance_for
from .security import sanitize_message
from .urls import normalized_hostname


def _icon_button(widget: QWidget, icon, tooltip: str) -> QPushButton:
    button = QPushButton(widget)
    button.setObjectName("iconButton")
    button.setIcon(icon)
    button.setToolTip(tooltip)
    button.setAccessibleName(tooltip)
    button.setFocusPolicy(Qt.StrongFocus)
    return button


class ProgressCell(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("downloadProgress")
        self.bar = QProgressBar(self)
        self.bar.setObjectName("downloadProgressBar")
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setAlignment(Qt.AlignCenter)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.bar)

    def set_value(self, value: float | int | None) -> None:
        self.bar.setValue(max(0, min(100, int(value or 0))))

    def value(self) -> int:
        return self.bar.value()


class UrlInput(QPlainTextEdit):
    submit_requested = Signal()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and event.modifiers() in (
            Qt.NoModifier,
            Qt.ControlModifier,
            Qt.MetaModifier,
        ):
            self.submit_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class DownloadCard(QFrame):
    action_requested = Signal(str, str)

    def __init__(self, item_id: str, url: str, quality: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("downloadCard")
        self.item_id = item_id
        self.url = sanitize_message(url)
        self._site = normalized_hostname(url)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(10)
        avatar = QLabel(self._site[:1].upper())
        avatar.setFixedSize(30, 30)
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setStyleSheet(
            "border-radius:15px; background:#7C5CFC; color:white; font-weight:700;"
        )
        top.addWidget(avatar)

        info = QVBoxLayout()
        info.setSpacing(1)
        self.title_label = QLabel(self.url, self)
        self.title_label.setTextFormat(Qt.PlainText)
        self.title_label.setToolTip(self.url)
        self.title_label.setStyleSheet("font-weight:600;")
        self.meta_label = QLabel(
            f"{self._site}  ·  {self._quality_label(quality)}", self
        )
        self.meta_label.setObjectName("cardMeta")
        info.addWidget(self.title_label)
        info.addWidget(self.meta_label)
        top.addLayout(info, 1)

        self.status_label = QLabel("Queued", self)
        self.status_label.setObjectName("statusQueued")
        top.addWidget(self.status_label, 0, Qt.AlignTop)
        root.addLayout(top)

        progress_row = QHBoxLayout()
        progress_row.setSpacing(10)
        self.progress = ProgressCell(self)
        progress_row.addWidget(self.progress, 1)
        self.detail_label = QLabel("0%", self)
        self.detail_label.setObjectName("cardMeta")
        self.detail_label.setWordWrap(False)
        self.detail_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.detail_label.setMinimumWidth(210)
        progress_row.addWidget(self.detail_label)
        root.addLayout(progress_row)

        actions = QHBoxLayout()
        actions.setSpacing(4)
        actions.addStretch()
        style = self.style()
        self.start_button = _icon_button(
            self, style.standardIcon(style.StandardPixmap.SP_MediaPlay), "Start download"
        )
        self.retry_button = _icon_button(
            self,
            style.standardIcon(style.StandardPixmap.SP_BrowserReload),
            "Retry download",
        )
        self.cancel_button = _icon_button(
            self,
            style.standardIcon(style.StandardPixmap.SP_DialogCancelButton),
            "Cancel download",
        )
        self.open_button = _icon_button(
            self,
            style.standardIcon(style.StandardPixmap.SP_DirOpenIcon),
            "Open output folder",
        )
        self.remove_button = _icon_button(
            self,
            style.standardIcon(style.StandardPixmap.SP_TrashIcon),
            "Remove download",
        )
        for button, action in (
            (self.start_button, "start"),
            (self.retry_button, "retry"),
            (self.cancel_button, "cancel"),
            (self.open_button, "open"),
            (self.remove_button, "remove"),
        ):
            button.clicked.connect(
                lambda _checked=False, action=action: self.action_requested.emit(
                    self.item_id, action
                )
            )
            actions.addWidget(button)
        root.addLayout(actions)
        self.set_status("queued")

    @staticmethod
    def _quality_label(value: str) -> str:
        if value == "bv*+ba/b":
            return "Automatic"
        if value == "best":
            return "Best single file"
        return value

    def set_status(
        self,
        status: str,
        percent: float | None = None,
        speed: float | None = None,
        eta: float | None = None,
        error_code: str | None = None,
        error: str | None = None,
    ) -> None:
        display_status = status.title().replace("_", " ")
        self.status_label.setText(display_status)
        self.status_label.setObjectName(f"status{display_status.replace(' ', '')}")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

        self.start_button.setVisible(status == "queued")
        self.retry_button.setVisible(status in {"failed", "cancelled"})
        self.cancel_button.setVisible(
            status in {"queued", "running", "paused", "cancelling"}
        )
        self.open_button.setVisible(status == "success")
        self.remove_button.setVisible(
            status in {"queued", "success", "failed", "cancelled"}
        )

        progress = max(0, min(100, int(percent or 0)))
        self.progress.set_value(progress)
        details = [f"{progress}%"]
        if speed:
            details.append(f"{speed / 1000:.0f} KB/s")
        if eta is not None:
            details.append(f"ETA {int(eta)}s")
        if status in {"failed", "cancelled"}:
            self.detail_label.setWordWrap(True)
            self.detail_label.setText(guidance_for(error_code or status))
            self.detail_label.setToolTip(error or "")
        else:
            self.detail_label.setWordWrap(False)
            self.detail_label.setText("  ·  ".join(details))
            self.detail_label.setToolTip("")


class QueueList(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._cards: list[DownloadCard] = []
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(8)
        self.layout.addStretch()

    def add_card(self, card: DownloadCard) -> None:
        self._cards.append(card)
        self.layout.insertWidget(self.layout.count() - 1, card)
        card.show()

    def remove_card(self, card: DownloadCard) -> None:
        self._cards.remove(card)
        card.deleteLater()

    def card_at(self, row: int) -> DownloadCard:
        return self._cards[row]

    def rowCount(self) -> int:
        return len(self._cards)

    def cellWidget(self, row: int, column: int):
        return self._cards[row].progress if column == 3 else self._cards[row]


class RowActions(QWidget):
    """Compatibility adapter retained for callers of the former table UI."""

    def __init__(
        self,
        on_start,
        on_retry,
        on_cancel,
        on_open,
        on_remove=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.start = QPushButton("Start", self)
        self.retry = QPushButton("Retry", self)
        self.cancel = QPushButton("Cancel", self)
        self.open_folder = QPushButton("Folder", self)
        self.remove = QPushButton("Remove", self)
        self.start.clicked.connect(on_start)
        self.retry.clicked.connect(on_retry)
        self.cancel.clicked.connect(on_cancel)
        self.open_folder.clicked.connect(on_open)
        if on_remove is not None:
            self.remove.clicked.connect(on_remove)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 1, 2, 1)
        for button in (
            self.start,
            self.retry,
            self.cancel,
            self.open_folder,
            self.remove,
        ):
            layout.addWidget(button)
