"""Ratchet: colors & sizes drawn outside the design tokens never grow (tools/theme_inventory.py prints the counts)

Convert some to tokens (theme.* in QML, theme_data for the themes) and lower the ceilings; a new color goes in
theme_data, tokens.py or setting_status_colors, not in a page.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import theme_inventory

COLOR_CEILINGS = {
    "QML pages": 14,
    "Qt Quick backends & widgets": 171,
    "Overlays (widget)": 42,
    "Web pages (dashboard, stream)": 54,
}
PATTERN_CEILINGS = {
    "pixel font sizes": 0,
    "fixed radii": 11,
    "fixed durations": 1,
    "fixed spacings": 147,
}


def test_hard_coded_colors_do_not_grow():
    found = theme_inventory.counts()
    assert set(found) == set(COLOR_CEILINGS)
    grown = {area: (found[area], ceiling) for area, ceiling in COLOR_CEILINGS.items() if found[area] > ceiling}
    assert not grown, f"color literals above the ceiling (found, ceiling): {grown}"


def test_hard_coded_sizes_do_not_grow():
    found = theme_inventory.qml_patterns()
    grown = {label: (found.get(label, 0), ceiling) for label, ceiling in PATTERN_CEILINGS.items()
             if found.get(label, 0) > ceiling}
    assert not grown, f"QML sizes above the ceiling (found, ceiling): {grown}"


def test_theme_colors_live_in_theme_data():
    """The four themes are defined in theme_data only: no palette literal left in the window module"""
    path = os.path.join(theme_inventory.ROOT, "neopedal", "ui", "__init__.py")
    with open(path, encoding="utf-8") as file:
        assert theme_inventory.hex_colors(path) <= 2, "palette colors belong in neopedal/theme_data.py"
        assert "QPalette.ColorRole.Window)," not in file.read()
