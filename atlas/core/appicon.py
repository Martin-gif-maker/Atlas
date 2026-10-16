"""The app icon: a paper-coloured rounded square with the app's symbol drawn in ink blue."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer


def image(glyph: str, size: int = 1024) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    s = size / 1024
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    body = QPainterPath()
    body.addRoundedRect(QRectF(100 * s, 100 * s, 824 * s, 824 * s), 185 * s, 185 * s)
    p.fillPath(body, QColor("#F6F4F0"))
    p.setPen(QPen(QColor("#D9D4CB"), max(1.0, 4 * s)))
    p.drawPath(body)
    if glyph:
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" stroke="#1F4FD8" '
               f'stroke-width="1.15" stroke-linecap="round" stroke-linejoin="round">{glyph}</svg>')
        QSvgRenderer(QByteArray(svg.encode())).render(p, QRectF(232 * s, 232 * s, 560 * s, 560 * s))
    p.end()
    return img


def icon(glyph: str) -> QIcon:
    result = QIcon()
    for px in (32, 64, 128, 256, 512):
        result.addPixmap(QPixmap.fromImage(image(glyph, px)))
    return result
