"""Inventory of the values drawn outside the design tokens: hard coded colors, pixel sizes, radii, durations

Usage: py tools/theme_inventory.py [--files]     (counts per area; --files: per file, highest first)
The ceilings of tests/test_hardcoded_colors.py are these counts: lower them when converting some to tokens.
"""

import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEX = re.compile(r"#(?:[0-9A-Fa-f]{8}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b")
PATTERNS = {
    "pixel font sizes": re.compile(r"font\.pixelSize:\s*\d"),
    "fixed radii": re.compile(r"\bradius:\s*\d"),
    "fixed durations": re.compile(r"\bduration:\s*\d"),
    "fixed spacings": re.compile(r"\b(spacing|[a-zA-Z]*[mM]argins?|[a-zA-Z]*[pP]adding):\s*\d"),
}
# Files that define colors: palettes of the themes, status & stream colors, user facing default colors
DEFINITIONS = ("neopedal/theme_data.py", "neopedal/template/", "neopedal/ui/tokens.py")
AREAS = {
    "QML pages": ("neopedal/ui/qml", (".qml",)),
    "Qt Quick backends & widgets": ("neopedal/ui", (".py",)),
    "Overlays (widget)": ("neopedal/widget", (".py",)),
    "Web pages (dashboard, stream)": ("neopedal", (".py",)),
}
WEB_FILES = ("web_dashboard.py", "stream_overlay.py", "stream_director_page.py", "stream_director_script.py")


def source_files(folder: str, suffixes: tuple[str, ...]):
    for base, _, names in os.walk(os.path.join(ROOT, folder)):
        if "__pycache__" in base:
            continue
        for name in names:
            if name.endswith(suffixes):
                yield os.path.join(base, name)


def is_definition(path: str) -> bool:
    relative = os.path.relpath(path, ROOT).replace("\\", "/")
    return relative.startswith(DEFINITIONS)


def hex_colors(path: str) -> int:
    """Color literals of a file, comment lines left out"""
    with open(path, encoding="utf-8") as file:
        return sum(len(HEX.findall(line)) for line in file if not line.strip().startswith(("//", "#")))


def area_files(area: str):
    folder, suffixes = AREAS[area]
    for path in source_files(folder, suffixes):
        name = os.path.basename(path)
        if area == "Web pages (dashboard, stream)":
            if name in WEB_FILES and os.path.dirname(path) == os.path.join(ROOT, "neopedal"):
                yield path
        elif area == "Qt Quick backends & widgets":
            if "/qml/" not in path.replace("\\", "/") and not is_definition(path):
                yield path
        elif not is_definition(path):
            yield path


def counts() -> dict[str, int]:
    """Hard coded colors per area"""
    return {area: sum(hex_colors(path) for path in area_files(area)) for area in AREAS}


def qml_patterns() -> dict[str, int]:
    totals: Counter = Counter()
    for path in source_files("neopedal/ui/qml", (".qml",)):
        with open(path, encoding="utf-8") as file:
            for line in file:
                if line.strip().startswith("//"):
                    continue
                for label, pattern in PATTERNS.items():
                    totals[label] += len(pattern.findall(line))
    return dict(totals)


def main(show_files: bool) -> int:
    print("Hard coded colors (#RGB, #RRGGBB, #AARRGGBB) outside the files that define them")
    for area, total in counts().items():
        print(f"  {area:34}{total:6}")
    print("Values of QML pages not taken from tokens")
    for label, total in qml_patterns().items():
        print(f"  {label:34}{total:6}")
    if show_files:
        rows = sorted(((hex_colors(path), os.path.relpath(path, ROOT)) for area in AREAS for path in area_files(area)),
                      reverse=True)
        print("Files with the most color literals")
        for total, name in rows[:40]:
            if total:
                print(f"  {total:5}  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main("--files" in sys.argv[1:]))
