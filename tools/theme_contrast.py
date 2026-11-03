"""Contrast table of the window themes: text, accent & status colors on every surface, control outlines

Usage: py tools/theme_contrast.py [theme name ...]   (all four themes by default)
Minimums (WCAG 2.x): main text 7, other text 4.5, outline of a control 3. The same limits are checked by
tests/test_theme_contrast.py; a value under its minimum is marked with "!".
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

SURFACES = ("surfacePage", "surfaceCard", "surfaceFlyout", "surfaceSunken", "surfaceHover", "raised")
COLORS = (("text", 7.0), ("dimText", 4.5), ("accent", 4.5), ("info", 4.5), ("gain", 4.5), ("loss", 4.5),
          ("warning", 4.5), ("purple", 4.5), ("gold", 4.5), ("controlBorder", 3.0))


def main(names: list[str]) -> int:
    app = QApplication.instance() or QApplication([])
    from neopedal.regex_pattern import THEME_NAMES
    from neopedal.ui import set_style_palette
    from neopedal.ui.quick import Theme, contrast_ratio

    failures = 0
    for name in names or THEME_NAMES:
        set_style_palette(name)
        theme = Theme()
        print(f"== {name}")
        print(f"{'surface':22}" + "".join(f"{label:>14}" for label, _ in COLORS))
        for surface_name in SURFACES:
            surface = getattr(theme, surface_name)
            cells = []
            for label, minimum in COLORS:
                if label == "controlBorder" and surface_name in ("surfaceHover", "raised"):
                    cells.append(f"{'-':>12}  ")  # fields are not drawn on hovered or raised surfaces
                    continue
                ratio = contrast_ratio(getattr(theme, label), surface)
                failures += ratio < minimum
                cells.append(f"{ratio:>12.1f}{'!' if ratio < minimum else ' '} ")
            print(f"{surface_name + ' ' + surface.name():22}" + "".join(c[:-1] for c in cells))
        for fill_name in ("accentFill", "lossFill"):
            ratio = contrast_ratio(QColor("white"), getattr(theme, fill_name))
            failures += ratio < 4.5
            print(f"white on {fill_name} {getattr(theme, fill_name).name()}: {ratio:.1f}{' !' if ratio < 4.5 else ''}")
    app.quit()
    print(f"{failures} value(s) under the minimum")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
