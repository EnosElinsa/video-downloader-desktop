"""Deterministic native controls for Qt stylesheets and Windows DPI modes."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainter, QPalette, QPolygonF
from PySide6.QtWidgets import QComboBox, QSpinBox


def _draw_chevron(widget, painter: QPainter, x: float, y: float, *, up: bool) -> None:
    group = QPalette.Active if widget.isEnabled() else QPalette.Disabled
    color = widget.palette().color(group, QPalette.Text)
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    if up:
        points = (QPointF(x - 4, y + 2), QPointF(x + 4, y + 2), QPointF(x, y - 3))
    else:
        points = (QPointF(x - 4, y - 2), QPointF(x + 4, y - 2), QPointF(x, y + 3))
    painter.drawPolygon(QPolygonF(points))
    painter.restore()


class ChevronComboBox(QComboBox):
    """Combo box with a readable, theme-independent down chevron."""

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        _draw_chevron(self, painter, self.width() - 17, self.height() / 2, up=False)


class ChevronSpinBox(QSpinBox):
    """Spin box with readable up/down chevrons."""

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        x = self.width() - 15
        _draw_chevron(self, painter, x, self.height() * 0.27, up=True)
        _draw_chevron(self, painter, x, self.height() * 0.73, up=False)
