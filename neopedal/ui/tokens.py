#  NeoPedal is an open-source overlay application for racing simulation.
#  Copyright (C) 2022-2026 TinyPedal developers, see contributors.md file
#
#  This file is part of NeoPedal.
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
Design tokens shared by Qt Quick pages (quick.Theme) and the Qt Widgets shell (navigation rail, menus, page header,
style sheet): one source for sizes, corner radii, tints, surfaces & durations

Pure values and color math on a palette: no Qt Quick import (the shell reads them at startup, before any page).
Sizes are factors of em, the base font size in pixels (UIScaler.FONT_PIXEL_SCALED): QML pages and widgets use the
same em (never the line height of a font). tests/test_shell_tokens.py checks the shell colors equal the Theme ones.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

# Corner radius: factor of em
RADIUS_SCALE = {"radiusXs": 0.2, "radiusSm": 0.3, "radiusMd": 0.45, "radiusLg": 0.6, "radiusXl": 0.75}
# Control & row heights: factor of em
SIZE_SCALE = {
    "controlHeight": 2.3,  # buttons, switches, segmented controls, search fields
    "controlHeightSm": 1.85,  # compact toolbars, buttons inside rows
    "controlHeightXs": 1.5,  # buttons inside chips & tags (drawn size: their click area is minTarget at least)
    "fieldHeight": 2.05,  # text & number fields, combo boxes
    "rowCompact": 2.1,  # dense tables, menus
    "row": 2.8,  # lists
    "rowTall": 3.4,  # lists with two text lines
    "headerHeight": 1.9,  # column header row of tables
    # Smallest click area (WCAG 2.5.8: 24 px at 100 % scale, em = 13.3 px): small buttons keep their drawn size,
    # their mouse area grows to this (theme.minTarget)
    "minTarget": 1.85,
}
# Animation durations (ms), 0 when Windows animations are off
MOTION = {"motionFast": 120, "motionBase": 180, "motionSlow": 250}
# Time (ms) a toast stays (ui/toast.toast_duration, TpToast.shownTime): long enough to read its text, errors longer,
# a button (undo) longer
TOAST_TIMES = {"toastMinimumTime": 3000, "toastTimePerCharacter": 55, "toastReadStartTime": 1500,
               "toastActionExtraTime": 3000}
TOAST_ERROR_FACTOR = 1.5
# Tint alpha (color over a surface): named levels of theme.tint(color, level)
TINT_LEVELS = {"subtle": 0.1, "selected": 0.18, "strong": 0.28,
               "outline": 0.5,  # border of a tinted chip or notice
               "stripe": 0.03}  # odd rows of dense tables (theme.text tint)
TINT_SELECTED_LIGHT = 0.12  # selected rows of light themes (dim text stays 4.5:1 on them)
# Surfaces (elevation): share of white (dark themes) or text color (light themes) mixed into the card color
SURFACE_LIFT = {"card": 0.035, "flyout": 0.05, "hover": 0.05, "sunken": 0.05}
LEGACY_RADIUS = 0.5  # Legacy themes: corners half as round (classic look)


def luminance(color: QColor) -> float:
    """WCAG relative luminance of a color (0 black to 1 white)"""
    channels = [
        value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
        for value in (color.redF(), color.greenF(), color.blueF())
    ]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def blended(color: QColor, background: QColor, alpha: float) -> QColor:
    """Opaque color of a translucent color over a background"""
    return QColor.fromRgbF(*(top * alpha + bottom * (1 - alpha) for top, bottom in (
        (color.redF(), background.redF()), (color.greenF(), background.greenF()), (color.blueF(), background.blueF()))))


# Colors of shared tokens from a palette (same results as quick.Theme properties of the same name)
def _color(palette: QPalette, role: QPalette.ColorRole) -> QColor:
    return palette.color(QPalette.ColorGroup.Active, role)


def is_dark(palette: QPalette) -> bool:
    return _color(palette, QPalette.ColorRole.Window).lightness() < 128


def lift(palette: QPalette, surface: QColor, share: str) -> QColor:
    """Surface raised (dark themes: toward white) or tinted (light themes: toward text) by a SURFACE_LIFT share"""
    toward = QColor("white") if is_dark(palette) else _color(palette, QPalette.ColorRole.Text)
    return blended(toward, surface, SURFACE_LIFT[share])


def surface_card(palette: QPalette) -> QColor:
    """Cards, panels & tiles (theme.surfaceCard)"""
    window, base = _color(palette, QPalette.ColorRole.Window), _color(palette, QPalette.ColorRole.Base)
    if is_dark(palette) and luminance(base) <= luminance(window):  # Legacy Grey: base darker than the page
        return lift(palette, window, "card")
    return base


def surface_flyout(palette: QPalette) -> QColor:
    """Popups & menus (theme.surfaceFlyout)"""
    card = surface_card(palette)
    return lift(palette, card, "flyout") if is_dark(palette) else card


SUBTLE_STROKE_CONTRAST = 1.8  # card borders, dividers & menu borders: seen against the card, never a frame


def stroke_subtle(palette: QPalette, legacy: bool) -> QColor:
    """Border of cards, menus, dividers (theme.strokeSubtle): the card color moved toward white (dark themes) or toward
    the text color (light themes) until it holds SUBTLE_STROKE_CONTRAST against the card; Legacy themes: firmer
    outlines from the palette border color"""
    mid = _color(palette, QPalette.ColorRole.Mid)
    if legacy:
        return mid.lighter(115) if is_dark(palette) else mid.darker(112)
    card = surface_card(palette)
    toward = QColor("white") if is_dark(palette) else _color(palette, QPalette.ColorRole.Text)
    color = card
    for step in range(1, 51):
        color = blended(toward, card, step * 0.01)
        if contrast(color, card) >= SUBTLE_STROKE_CONTRAST:
            break
    return color


CONTROL_BORDER_CONTRAST = 3.0  # WCAG 1.4.11: outline of a field, combo or switch against its surroundings


def contrast(first: QColor, second: QColor) -> float:
    """WCAG contrast ratio (1 to 21) of two colors"""
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def control_border(palette: QPalette) -> QColor:
    """Outline of fields, combo boxes & switches (theme.controlBorder): the palette border color (Mid), moved toward
    the text color until it keeps 3:1 against the page, the cards & the menus it sits on"""
    color = QColor(_color(palette, QPalette.ColorRole.Mid))
    toward = _color(palette, QPalette.ColorRole.Text)
    surfaces = (_color(palette, QPalette.ColorRole.Window), surface_card(palette),
                _color(palette, QPalette.ColorRole.Base), surface_flyout(palette))
    for step in range(1, 41):
        if min(contrast(color, surface) for surface in surfaces) >= CONTROL_BORDER_CONTRAST:
            break
        color = blended(toward, _color(palette, QPalette.ColorRole.Mid), step * 0.02)
    return color


def hover_fill(palette: QPalette) -> QColor:
    """Hovered control or row (theme.hover)"""
    return _color(palette, QPalette.ColorRole.Midlight)


def selected_fill(palette: QPalette, hovered: bool = False) -> QColor:
    """Selected row or entry: accent tint, a third stronger hovered (theme.rowColor(hovered, true))"""
    color = QColor(_color(palette, QPalette.ColorRole.Highlight))
    alpha = TINT_LEVELS["selected"] if is_dark(palette) else TINT_SELECTED_LIGHT
    color.setAlphaF(alpha * (4 / 3 if hovered else 1))
    return color


def radius_px(name: str, em: float, legacy: bool) -> float:
    """Corner radius in pixels (theme.radiusXx): half as round on Legacy themes"""
    return em * RADIUS_SCALE[name] * (LEGACY_RADIUS if legacy else 1)
