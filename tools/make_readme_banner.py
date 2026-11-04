"""
Render the README banner (images/readme_banner.png) and the repository social preview
(images/social_preview.png, 1280 x 640, set by hand in GitHub Settings > Social preview)

Logo, name and tagline, then a few overlays placed like on a game screen, drawn with
default modern settings on the simulated race of the README preview (same data setup).

Run from project root after visual changes to widgets (optional output folder):
    python tools/make_readme_banner.py [folder]
"""

from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import make_readme_preview as preview
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPen, QPixmap, QRadialGradient

MARGIN = 56
GOLD = QColor(201, 162, 39)
TEXT = QColor(255, 255, 255, 235)
TEXT_DIM = QColor(255, 255, 255, 150)
CHIPS = ("93 overlays", "Telemetry viewer", "Race calculator", "Driver stats", "Broadcast director",
         "Free & open source")
# Images made: file name, size, title scale, right end of the chip rows, caption, overlay: top left corner
LAYOUTS = (
    ("readme_banner.png", (1600, 910), 1.0, 1000, True, {
        "standings": (1041, 56),
        "relative": (MARGIN, 330),
        "deltabest": (MARGIN, 575),
        "radar": (650, 300),
        "fuel": (MARGIN, 690),
        "virtual_energy": (MARGIN + 306, 690),
        "tyre_overview": (774, 690),
        "black_box": (1182, 590),
    }),
    ("social_preview.png", (1280, 640), 0.78, 680, False, {
        "standings": (729, 64),
        "relative": (MARGIN, 310),
        "deltabest": (MARGIN, 548),
        "speed_delta": (MARGIN + 322, 540),
    }),
)


def draw_background(painter: QPainter, width: int, height: int):
    """Dark gradient, gold glow behind the title, faint racing stripes"""
    gradient = QLinearGradient(0, 0, width, height)
    gradient.setColorAt(0, QColor(22, 25, 30))
    gradient.setColorAt(1, QColor(12, 13, 16))
    painter.fillRect(0, 0, width, height, gradient)
    glow = QRadialGradient(QPointF(260, 120), 620)
    glow.setColorAt(0, QColor(201, 162, 39, 46))
    glow.setColorAt(1, QColor(201, 162, 39, 0))
    painter.fillRect(0, 0, width, height, glow)
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    for index, alpha in enumerate((14, 9, 5)):
        painter.setBrush(QColor(255, 255, 255, alpha))
        offset = width * 0.33 + index * 90
        painter.drawPolygon([QPointF(offset, height), QPointF(offset + 46, height),
                             QPointF(offset + 46 + height * 0.7, 0), QPointF(offset + height * 0.7, 0)])
    painter.restore()
    painter.fillRect(QRectF(0, 0, width, 4), GOLD)


def draw_title(painter: QPainter, icon: QPixmap, scale: float, chips_end: int):
    """Icon, name, tagline and feature chips"""
    painter.drawPixmap(QRectF(MARGIN, MARGIN, 96 * scale, 96 * scale), icon, QRectF(icon.rect()))
    font = QFont("Barlow", round(64 * scale))
    font.setWeight(QFont.Weight.Bold)
    painter.setFont(font)
    painter.setPen(TEXT)
    painter.drawText(QRectF(MARGIN + 120 * scale, MARGIN - 8 * scale, 800, 110 * scale),
                     Qt.AlignmentFlag.AlignVCenter, "NeoPedal")
    font = QFont("Barlow", round(22 * scale))
    font.setWeight(QFont.Weight.Medium)
    painter.setFont(font)
    painter.setPen(TEXT_DIM)
    painter.drawText(QRectF(MARGIN, MARGIN + 120 * scale, 960, 40 * scale), Qt.AlignmentFlag.AlignVCenter,
                     "Overlays & telemetry tools for Le Mans Ultimate and rFactor 2")
    font = QFont("Barlow", 13)
    font.setWeight(QFont.Weight.DemiBold)
    painter.setFont(font)
    metrics = painter.fontMetrics()
    x, y = MARGIN, MARGIN + 182 * scale
    for index, chip in enumerate(CHIPS):
        width = metrics.horizontalAdvance(chip) + 28
        if x + width > chips_end:
            x, y = MARGIN, y + 40
        rect = QRectF(x, y, width, 30)
        accent = index == 0
        painter.setPen(QPen(GOLD if accent else QColor(255, 255, 255, 40), 1))
        painter.setBrush(QColor(201, 162, 39, 40) if accent else QColor(255, 255, 255, 12))
        painter.drawRoundedRect(rect, 15, 15)
        painter.setPen(GOLD.lighter(130) if accent else TEXT)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, chip)
        x += width + 10


def draw_overlay(painter: QPainter, pixmap: QPixmap, x: int, y: int):
    """Overlay with a soft shadow, as over the game picture"""
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    for spread, alpha in ((14, 18), (8, 28), (3, 40)):
        painter.setBrush(QBrush(QColor(0, 0, 0, alpha)))
        painter.drawRoundedRect(QRectF(x - spread, y - spread + 6, pixmap.width() + spread * 2,
                                       pixmap.height() + spread * 2), 12 + spread, 12 + spread)
    painter.restore()
    painter.drawPixmap(x, y, pixmap)


def compose(pixmaps: dict[str, QPixmap], icon: QPixmap, size: tuple[int, int], scale: float, chips_end: int,
            caption: bool, places: dict[str, tuple[int, int]]) -> QPixmap:
    width, height = size
    image = QPixmap(width, height)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    draw_background(painter, width, height)
    draw_title(painter, icon, scale, chips_end)
    for name, (x, y) in places.items():
        draw_overlay(painter, pixmaps[name], x, y)
    if caption:
        painter.setFont(QFont("JetBrains Mono", 11))
        painter.setPen(QColor(255, 255, 255, 90))
        painter.drawText(QRectF(MARGIN, height - 30, width - MARGIN * 2, 20), Qt.AlignmentFlag.AlignRight,
                         "modern design · simulated race data")
    painter.end()
    return image


def main():
    preview.load_bundled_fonts()
    preview.cfg.default.set_default()
    for name in preview.cfg.user.__slots__:
        setattr(preview.cfg.user, name, preview.copy_setting(getattr(preview.cfg.default, name)))
    preview.without_game_pictures()
    sim, data = preview.lmu_api()
    preview.api._api, preview.api.read = sim, sim.reader()
    preview.set_telemetry(sim, data)
    preview.set_vehicles()
    preview.set_modules()

    pixmaps = preview.render_widgets(data)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    icon = QPixmap(os.path.join(root, "images", "icon_dark.png"))
    folder = sys.argv[1] if len(sys.argv) > 1 else "images"
    for file_name, size, scale, chips_end, caption, places in LAYOUTS:
        output = os.path.join(folder, file_name)
        image = compose(pixmaps, icon, size, scale, chips_end, caption, places)
        image.save(output)
        print(f"saved {output} {image.width()}x{image.height()} ({math.floor(os.path.getsize(output) / 1024)} KB)")


if __name__ == "__main__":
    main()
