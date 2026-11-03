"""
Render overview images of every widget: images/readme_preview.png (README, 2 columns) and
images/readme_preview_wide.png (wiki Home, 3 columns)

Every widget is built with default modern settings on simulated LMU data: a GT3 car at
speed mid race at Road Atlanta, in a 20 car multi-class field. Data modules do not run
here, so their outputs (minfo) are filled directly. Widgets are then grouped by Overlays
page category, one titled panel per category (largest first inside), panels laid out in
columns.

The simulated race (neopedal/demo_data.py) is the one overlay pictures of the app show.

Run from project root after visual changes to widgets (optional output folder):
    python tools/make_readme_preview.py [folder]
"""

from __future__ import annotations

import math
import os
import pkgutil
import sys
from importlib import import_module
from itertools import product

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QRect, QRectF, Qt, QTimerEvent
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

APP = QApplication.instance() or QApplication(sys.argv)

from neopedal import demo_data
from neopedal.api_control import api
from neopedal.demo_data import GAP_WIDGETS, HISTORY_WIDGETS, LAP_WIDGETS, SAMPLE_WIDGETS, lmu_api, set_telemetry
from neopedal.main import load_bundled_fonts
from neopedal.module_info import minfo
from neopedal.setting import cfg
from neopedal.userfile.json_setting import copy_setting
from neopedal.widget._modern import create_widget

# Images made: file name, width, columns of panels (widest overlay must fit a 3 columns panel)
LAYOUTS = (
    ("readme_preview.png", 1920, 2),
    ("readme_preview_wide.png", 2000, 3),
)
MARGIN = 24
SPACING = 14
GAP_COLLAPSE = 64  # empty columns inside a widget narrowed to 2 x SPACING when wider
PANEL_GAP = 18
PANEL_PADDING = 16
PANEL_HEADER = 40
BACKGROUND = QColor(28, 31, 36)
PANEL_BACKGROUND = QColor(38, 42, 49)
PANEL_BORDER = QColor(255, 255, 255, 18)

__all__ = ("HISTORY_WIDGETS", "api", "copy_setting", "lmu_api", "load_bundled_fonts", "set_telemetry")


def set_vehicles():
    """Vehicles and relative module outputs (see neopedal.demo_data)"""
    demo_data.set_vehicles(minfo, cfg.user.setting["standings"], api.read)
    sample_driver_ranks()


def sample_driver_ranks():
    """Driver & Safety Rank of simulated drivers (rank column & field level, when switched on), as overlay
    pictures of the app: nothing read from the game folder nor online"""
    from neopedal import rank_info
    from neopedal.process import driver_ranks as dr
    from neopedal.process import field_ranks as fr
    from neopedal.userfile.badge_icons import icons
    from neopedal.widget._modern.drivers import SAMPLE_RANKS

    rank_info.ranks.poll = lambda: None
    rank_info.field.poll = lambda names: None
    icons.request = lambda key: None  # badge icons never downloaded (dots of badge colors)
    rank_info.field._ranks = {
        fr.driver_key(veh.driverName): dr.DriverRanks(
            veh.driverName, "", "", "", dr.Rank(*sample[:2], 50), dr.Rank(*sample[2:4], 50), sample[4])
        for veh in minfo.vehicles.dataSet if veh.driverName
        for sample in (SAMPLE_RANKS[veh.positionOverall % len(SAMPLE_RANKS)],)
    }


def set_modules():
    """Data module outputs the widgets read (see neopedal.demo_data)"""
    demo_data.set_modules(minfo)


# Packing orders tried, the shortest result kept: tallest, widest or largest first
PACK_ORDERS = (
    lambda size: (-size[1], -size[0]),
    lambda size: (-size[0], -size[1]),
    lambda size: (-size[0] * size[1],),
)


def pack(sizes: dict[str, tuple[int, int]], width: int) -> tuple[dict[str, tuple[int, int]], int]:
    """Pack rectangles into a fixed width, shortest of the packing orders"""
    return min((pack_ordered(sizes, width, order) for order in PACK_ORDERS), key=lambda packed: packed[1])


def pack_ordered(sizes: dict[str, tuple[int, int]], width: int, order) -> tuple[dict[str, tuple[int, int]], int]:
    """Pack rectangles in order(size) into a fixed width, using skyline bottom-left placement"""
    skyline = [(0, width, 0)]  # segments: x, width, top y
    positions = {}
    for name, (w, h) in sorted(sizes.items(), key=lambda item: order(item[1])):
        best = None
        for start, (seg_x, _, _) in enumerate(skyline):
            if seg_x + w > width:
                break
            # Lowest y where the rect fits starting at this segment
            top, span, index = 0, 0, start
            while span < w and index < len(skyline):
                top = max(top, skyline[index][2])
                span = skyline[index][0] + skyline[index][1] - seg_x
                index += 1
            if span < w:
                continue
            if best is None or top < best[1] or (top == best[1] and seg_x < best[0]):
                best = (seg_x, top)
        x, y = best
        positions[name] = (x, y)
        # Update skyline
        new_skyline = []
        for seg_x, seg_w, seg_y in skyline:
            seg_end = seg_x + seg_w
            if seg_end <= x or seg_x >= x + w:
                new_skyline.append((seg_x, seg_w, seg_y))
                continue
            if seg_x < x:
                new_skyline.append((seg_x, x - seg_x, seg_y))
            if seg_end > x + w:
                new_skyline.append((x + w, seg_end - x - w, seg_y))
        new_skyline.append((x, w, y + h))
        new_skyline.sort()
        skyline = new_skyline
    return positions, max(y + sizes[name][1] for name, (_, y) in positions.items())


def replay_history(widget, data):
    """Feed a widget drawing input history a corner, ending at the simulated state"""
    demo_data.replay_history(widget, data, minfo)


def without_game_pictures():
    """No car brand logo nor picture of the game (trademarks never published in repo images): empty
    brand logo & game picture folders (user's own logos left out), never fetched from a running game"""
    import tempfile

    from neopedal.userfile import game_images

    cfg.path.game_image = tempfile.mkdtemp(prefix="preview_pictures_")
    cfg.path.brand_logo = tempfile.mkdtemp(prefix="preview_logos_") + os.sep
    game_images.fetch_from_game = lambda *args, **kwargs: (0, b"")


def trim(pixmap: QPixmap) -> QPixmap:
    """Pixmap cropped to its drawn pixels, wide empty columns inside narrowed: widgets sized for hidden
    items (flag) or drawn on screen edges (spotter) leave no empty area in the preview"""
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    width, stride = image.width(), image.bytesPerLine()
    bits = bytes(image.constBits())
    drawn_rows = []
    columns = 0  # alpha of every row OR-ed: column drawn if not zero
    for y in range(image.height()):
        alpha = bits[y * stride + 3: y * stride + width * 4: 4]  # ARGB32 little endian: alpha 4th byte
        if alpha.strip(bytes(1)):
            drawn_rows.append(y)
            columns |= int.from_bytes(alpha, "big")
    if not drawn_rows:
        return pixmap
    drawn = columns.to_bytes(width, "big")
    spans = []  # drawn column ranges, gaps narrower than GAP_COLLAPSE kept
    for x in range(width):
        if not drawn[x]:
            continue
        if spans and x - spans[-1][1] <= GAP_COLLAPSE:
            spans[-1][1] = x + 1
        else:
            spans.append([x, x + 1])
    top, height = drawn_rows[0], drawn_rows[-1] - drawn_rows[0] + 1
    if len(spans) == 1:
        return pixmap.copy(QRect(spans[0][0], top, spans[0][1] - spans[0][0], height))
    trimmed = QPixmap(sum(end - start for start, end in spans) + SPACING * 2 * (len(spans) - 1), height)
    trimmed.fill(Qt.GlobalColor.transparent)
    painter = QPainter(trimmed)
    x = 0
    for start, end in spans:
        painter.drawPixmap(x, 0, pixmap, start, top, end - start, height)
        x += end - start + SPACING * 2
    painter.end()
    return trimmed


def render_widgets(data) -> dict[str, QPixmap]:
    names = sorted(
        module.name
        for module in pkgutil.iter_modules(import_module("neopedal.widget").__path__)
        if not module.name.startswith("_")
    )
    pixmaps = {}
    for name in names:
        widget = create_widget(import_module(f"neopedal.widget.{name}"), cfg, name)
        widget.adjustSize()
        if name in HISTORY_WIDGETS:
            replay_history(widget, data)
        elif name in LAP_WIDGETS:
            demo_data.replay_lap(widget, data, minfo)
        elif name in GAP_WIDGETS:
            demo_data.replay_gaps(widget, data, minfo)
        if name not in SAMPLE_WIDGETS:  # as Overlays page previews: sample of every item, never updated
            for _ in range(3):  # a few updates, so smoothed values settle
                widget.timerEvent(QTimerEvent(0))
        widget.adjustSize()  # rows shown on update (standings, relative) change the size
        # Render on transparent pixmap: grab() fills translucent areas with an opaque background
        pixmap = QPixmap(widget.size())
        pixmap.fill(Qt.GlobalColor.transparent)
        widget.render(pixmap, renderFlags=QWidget.RenderFlag.DrawChildren)
        pixmaps[name] = trim(pixmap)
        widget.deleteLater()
    return pixmaps


def main():
    load_bundled_fonts()
    cfg.default.set_default()
    for name in cfg.user.__slots__:
        setattr(cfg.user, name, copy_setting(getattr(cfg.default, name)))
    without_game_pictures()
    sim, data = lmu_api()
    api._api, api.read = sim, sim.reader()
    set_telemetry(sim, data)
    set_vehicles()
    set_modules()

    pixmaps = render_widgets(data)
    folder = sys.argv[1] if len(sys.argv) > 1 else "images"
    for file_name, width, columns in LAYOUTS:
        output = os.path.join(folder, file_name)
        image = compose(pixmaps, width, columns)
        image.save(output)
        print(f"saved {output} {image.width()}x{image.height()} ({math.floor(os.path.getsize(output) / 1024)} KB)")


def compose(pixmaps: dict[str, QPixmap], width: int, columns: int) -> QPixmap:
    """Image of category panels in columns, caption below"""
    panels = layout_panels(pixmaps, width, columns)
    height = max(panel["origin"][1] + panel["height"] for panel in panels) - MARGIN

    caption_height = 40
    image = QPixmap(width, height + MARGIN * 2 + caption_height)
    image.fill(BACKGROUND)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    for panel in panels:
        draw_panel(painter, panel, pixmaps)
    painter.setFont(QFont("JetBrains Mono", 13))
    painter.setPen(QColor(255, 255, 255, 140))
    painter.drawText(
        QRectF(MARGIN, image.height() - MARGIN - 24, width - MARGIN * 2, 24),
        Qt.AlignmentFlag.AlignRight,
        f"NeoPedal · all {len(pixmaps)} widgets · simulated data",
    )
    painter.end()
    return image


def balanced_columns(heights: list[int], columns: int) -> tuple[int, ...]:
    """Column of each panel (kept in order inside a column), longest column the shortest possible"""
    def longest(placed: tuple[int, ...]) -> int:
        totals = [0] * columns
        for height, column in zip(heights, placed):
            totals[column] += height + PANEL_GAP
        return max(totals)

    return min(product(range(columns), repeat=len(heights)), key=longest)


def layout_panels(pixmaps: dict[str, QPixmap], image_width: int, columns: int) -> list[dict]:
    """One panel per Overlays page category (chips order), widgets packed inside, panels shared out
    between columns of even length; panels holding a widget wider than a column span every column, below"""
    from neopedal.template.widget.registry import CATEGORY_COLORS, OTHER, category_of

    of = category_of()
    full_width = image_width - MARGIN * 2
    column_width = (full_width - PANEL_GAP * (columns - 1)) // columns
    panels = []
    for category, color in CATEGORY_COLORS.items():
        names = [name for name in pixmaps if of.get(name, OTHER) == category]
        if not names:
            continue
        spans = max(pixmaps[name].width() for name in names) > column_width - PANEL_PADDING * 2
        width = full_width if spans else column_width
        sizes = {name: (pixmaps[name].width() + SPACING, pixmaps[name].height() + SPACING) for name in names}
        positions, packed = pack(sizes, width - PANEL_PADDING * 2 + SPACING)
        panels.append({
            "category": category, "color": QColor(color), "positions": positions, "spans": spans,
            "width": width, "height": PANEL_HEADER + packed - SPACING + PANEL_PADDING,
        })
    in_columns = [panel for panel in panels if not panel["spans"]]
    tops = [MARGIN] * columns
    last: list[dict | None] = [None] * columns
    for panel, column in zip(in_columns, balanced_columns([panel["height"] for panel in in_columns], columns)):
        panel["origin"] = (MARGIN + column * (column_width + PANEL_GAP), tops[column])
        tops[column] += panel["height"] + PANEL_GAP
        last[column] = panel
    top = max(tops)
    for column, panel in enumerate(last):  # last panels reach the bottom of the longest column
        if panel is not None:
            panel["height"] += top - tops[column]
    for panel in panels:
        if panel["spans"]:
            panel["origin"] = (MARGIN, top)
            top += panel["height"] + PANEL_GAP
    return panels


def draw_panel(painter: QPainter, panel: dict, pixmaps: dict[str, QPixmap]):
    """Rounded panel, category header (color dot, name, overlay count) and its widgets"""
    x, y = panel["origin"]
    painter.setPen(PANEL_BORDER)
    painter.setBrush(PANEL_BACKGROUND)
    painter.drawRoundedRect(QRectF(x + 0.5, y + 0.5, panel["width"] - 1, panel["height"] - 1), 10, 10)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(panel["color"])
    painter.drawEllipse(QRectF(x + PANEL_PADDING, y + 16, 10, 10))
    font = QFont("Barlow", 15)
    font.setWeight(QFont.Weight.DemiBold)
    painter.setFont(font)
    painter.setPen(QColor(255, 255, 255, 225))
    header = QRectF(x + PANEL_PADDING + 18, y + 6, panel["width"] - PANEL_PADDING * 2 - 18, 30)
    painter.drawText(header, Qt.AlignmentFlag.AlignVCenter, panel["category"].upper())
    painter.setFont(QFont("JetBrains Mono", 12))
    painter.setPen(QColor(255, 255, 255, 110))
    count = len(panel["positions"])
    painter.drawText(header, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                     f"{count} overlay{'s' if count > 1 else ''}")
    for name, (wx, wy) in panel["positions"].items():
        painter.drawPixmap(x + PANEL_PADDING + wx, y + PANEL_HEADER + wy, pixmaps[name])


if __name__ == "__main__":
    main()
