"""
Build country flag sheet from flag-icons (MIT, https://github.com/lipis/flag-icons)

Draws every 4x3 SVG flag of an unpacked flag-icons npm package into one PNG (cells in code order) and
writes its index, read by neopedal/flags.py. Only needed again to update flags.

Usage, from project root:
    curl -L -o flag-icons.tgz https://registry.npmjs.org/flag-icons/-/flag-icons-7.2.3.tgz
    tar xzf flag-icons.tgz   (in an empty folder)
    python tools/build_flags.py <folder>/package
"""

from __future__ import annotations

import json
import math
import os
import shutil
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

CELL_WIDTH, CELL_HEIGHT = 64, 48  # 4:3, drawn smaller in overlays (sharp up to 48 px rows)
COLUMNS = 16
SKIPPED = {"xx"}  # "unknown" flag: no flag drawn instead
OUTPUT_IMAGE = "images/flags.png"
OUTPUT_INDEX = "images/flags.json"
OUTPUT_LICENSE = "docs/licenses/LICENSE.flag-icons.txt"


def main(package: str) -> None:
    folder = os.path.join(package, "flags", "4x3")
    codes = sorted(name[:-4] for name in os.listdir(folder) if name.endswith(".svg") and name[:-4] not in SKIPPED)
    rows = math.ceil(len(codes) / COLUMNS)
    sheet = QImage(COLUMNS * CELL_WIDTH, rows * CELL_HEIGHT, QImage.Format.Format_ARGB32)
    sheet.fill(Qt.GlobalColor.transparent)
    painter = QPainter(sheet)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    for index, code in enumerate(codes):
        renderer = QSvgRenderer(os.path.join(folder, f"{code}.svg"))
        if not renderer.isValid():
            raise SystemExit(f"invalid flag: {code}")
        column, row = index % COLUMNS, index // COLUMNS
        renderer.render(painter, QRectF(column * CELL_WIDTH, row * CELL_HEIGHT, CELL_WIDTH, CELL_HEIGHT))
    painter.end()
    if not sheet.save(OUTPUT_IMAGE, "PNG", 0):  # 0 = smallest file
        raise SystemExit(f"not written: {OUTPUT_IMAGE}")
    with open(OUTPUT_INDEX, "w", encoding="utf-8", newline="\n") as file:
        json.dump({"cell": [CELL_WIDTH, CELL_HEIGHT], "columns": COLUMNS, "codes": codes}, file, separators=(",", ":"))
        file.write("\n")
    shutil.copyfile(os.path.join(package, "LICENSE"), OUTPUT_LICENSE)
    print(f"{len(codes)} flags, {os.path.getsize(OUTPUT_IMAGE) // 1024} kB")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    app = QGuiApplication(sys.argv[:1])
    main(sys.argv[1])
