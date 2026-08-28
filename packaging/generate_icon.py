"""Generate the deterministic multi-resolution Windows application icon."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen


SIZES = (16, 24, 32, 48, 64, 128, 256)


def render_png(size: int) -> bytes:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    scale = size / 256

    background = QPainterPath()
    background.addRoundedRect(QRectF(8 * scale, 8 * scale, 240 * scale, 240 * scale), 52 * scale, 52 * scale)
    gradient = QLinearGradient(QPointF(28 * scale, 16 * scale), QPointF(228 * scale, 240 * scale))
    gradient.setColorAt(0, QColor("#6D5EF8"))
    gradient.setColorAt(1, QColor("#1677FF"))
    painter.fillPath(background, gradient)

    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#FFFFFF"))
    play = QPainterPath()
    play.moveTo(76 * scale, 61 * scale)
    play.lineTo(76 * scale, 142 * scale)
    play.lineTo(145 * scale, 101.5 * scale)
    play.closeSubpath()
    painter.drawPath(play)

    pen = QPen(QColor("#FFFFFF"), max(2.0, 17 * scale), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.drawLine(QPointF(168 * scale, 92 * scale), QPointF(168 * scale, 176 * scale))
    painter.drawLine(QPointF(135 * scale, 145 * scale), QPointF(168 * scale, 178 * scale))
    painter.drawLine(QPointF(201 * scale, 145 * scale), QPointF(168 * scale, 178 * scale))
    painter.drawLine(QPointF(128 * scale, 202 * scale), QPointF(208 * scale, 202 * scale))
    painter.end()

    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError(f"Could not render {size}px icon")
    return bytes(data)


def build_ico() -> bytes:
    images = [(size, render_png(size)) for size in SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries = []
    payloads = []
    for size, payload in images:
        dimension = 0 if size == 256 else size
        entries.append(
            struct.pack("<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(payload), offset)
        )
        payloads.append(payload)
        offset += len(payload)
    return header + b"".join(entries) + b"".join(payloads)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("assets/video-downloader.ico"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(build_ico())
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
