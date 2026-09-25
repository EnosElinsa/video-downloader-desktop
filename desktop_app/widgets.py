"""Focused queue and progress widgets used by the main window."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
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


_SITE_COLORS = ("#7C5CFC", "#3D8BFD", "#39C887", "#F3B95F", "#F06A75", "#4CC2C9")


def _site_color(site: str) -> str:
    return _SITE_COLORS[sum(ord(char) for char in site) % len(_SITE_COLORS)]


def _draw_glyph(painter: QPainter, kind: str, rect, color: QColor) -> None:
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QPolygonF

    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(color)
    pen.setWidthF(1.4)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    cx = rect.center().x()
    cy = rect.center().y()
    if kind == "play":
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(cx - 4, cy - 5),
                    QPointF(cx - 4, cy + 5),
                    QPointF(cx + 5, cy),
                ]
            )
        )
    elif kind == "retry":
        painter.drawArc(int(cx - 5), int(cy - 5), 10, 10, 40 * 16, 280 * 16)
        painter.drawLine(int(cx + 4), int(cy - 5), int(cx + 1), int(cy - 2))
        painter.drawLine(int(cx + 4), int(cy - 5), int(cx + 4), int(cy - 1))
    elif kind == "cancel":
        painter.drawLine(int(cx - 4), int(cy - 4), int(cx + 4), int(cy + 4))
        painter.drawLine(int(cx + 4), int(cy - 4), int(cx - 4), int(cy + 4))
    elif kind == "open":
        painter.drawRect(int(cx - 6), int(cy - 2), 12, 8)
        painter.drawLine(int(cx - 6), int(cy - 2), int(cx - 2), int(cy - 6))
        painter.drawLine(int(cx - 2), int(cy - 6), int(cx + 2), int(cy - 6))
        painter.drawLine(int(cx + 2), int(cy - 6), int(cx + 2), int(cy - 2))
    elif kind == "remove":
        painter.drawLine(int(cx - 5), int(cy - 3), int(cx + 5), int(cy - 3))
        painter.drawRect(int(cx - 3), int(cy - 2), 6, 8)
        painter.drawLine(int(cx - 2), int(cy - 5), int(cx + 2), int(cy - 5))
    painter.restore()


class GlyphButton(QPushButton):
    def __init__(self, kind: str, tooltip: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.kind = kind
        self.setObjectName("iconButton")
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFixedSize(32, 32)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        color = self.palette().color(self.foregroundRole())
        _draw_glyph(painter, self.kind, self.rect(), color)


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
        dot = QLabel(self)
        dot.setObjectName("siteDot")
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(
            f"background:{_site_color(self._site)}; border-radius:4px;"
        )
        top.addWidget(dot, 0, Qt.AlignVCenter)

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
        self.detail_label.setObjectName("cardDetail")
        self.detail_label.setWordWrap(False)
        self.detail_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.detail_label.setMinimumWidth(210)
        progress_row.addWidget(self.detail_label)
        root.addLayout(progress_row)

        actions = QHBoxLayout()
        actions.setSpacing(4)
        actions.addStretch()
        self.start_button = GlyphButton("play", "Start download", self)
        self.retry_button = GlyphButton("retry", "Retry download", self)
        self.cancel_button = GlyphButton("cancel", "Cancel download", self)
        self.open_button = GlyphButton("open", "Open output folder", self)
        self.remove_button = GlyphButton("remove", "Remove download", self)
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
            guidance = guidance_for(error_code or status)
            self.detail_label.setText(guidance)
            self.detail_label.setToolTip(error or guidance)
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
