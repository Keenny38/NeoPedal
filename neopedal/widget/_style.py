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
Overlay themes & style

Themes: Modern Dark, Modern Grey, Modern White, Legacy Grey (classic look),
each with an optional colorblind safe variant. Only options that still use default value
are restyled, any user customized option is kept as it is.
"""

from __future__ import annotations

import colorsys
import re
from collections.abc import Mapping
from functools import lru_cache
from types import MappingProxyType
from typing import Any, NamedTuple

from .. import regex_pattern as rxp
from ..template.setting_status_colors import COLORBLIND_STATUS_COLORS
from ..theme_data import MODERN_GREY_NEUTRALS, MODERN_LIGHT_NEUTRALS, MODERN_PALETTE

MODERN_LIGHT_PANEL = "E5E9EF"  # darkest light panel: colors drawn on panels stay readable on it
MINIMUM_CONTRAST = 4.5  # WCAG AA for text: colors drawn on a light panel are darkened to this contrast against it
NEUTRAL_SPREAD = 24  # gray: RGB channels differ by this much at most

# Colorblind safe variant of every theme (Okabe-Ito): red / green pairs become orange / blue, status colors
# (loss, gain, warning, gold, best purple, player) same as app pages & stream pages (setting_status_colors)
_CB = {role: dark[1:].upper() for role, (dark, _) in COLORBLIND_STATUS_COLORS.items()}
COLORBLIND_COLORS = MappingProxyType({
    "FF2200": _CB["loss"],
    "FF4400": _CB["loss"],
    "DD5500": _CB["loss"],
    "EE6600": _CB["warning"],
    "FF6600": _CB["warning"],
    "FFAA00": _CB["gold"],
    "FFCC00": _CB["gold"],
    "FFFF00": _CB["gold"],
    "009900": "0072B2",
    "22AA00": "0072B2",
    "22CC22": _CB["gain"],
    "448800": "0072B2",
    "44FF00": _CB["gain"],
    "66EE00": _CB["gain"],
    "66FF00": _CB["gain"],
    "88FF00": _CB["gain"],
    "00CCEE": _CB["player"],
    "00CCFF": _CB["player"],
    "66CCFF": _CB["player"],
    "9900FF": _CB["purple"],
    "CC22CC": "CC79A7",
    "FF44FF": "CC79A7",
    "FF66FF": "CC79A7",
    "FF0000": _CB["loss"], "EE0000": _CB["loss"], "FF2222": _CB["loss"], "DD2200": _CB["loss"],
    "FF4422": _CB["loss"], "00FF00": _CB["gain"], "22EE22": _CB["gain"], "22FF00": _CB["gain"],
    "00CC00": _CB["gain"], "44CC00": _CB["gain"], "77FF00": _CB["gain"], "88FF88": _CB["gain"],
    "008800": "0072B2", "44AA00": "0072B2", "00AAFF": "0072B2", "0088FF": "0072B2",
    "0099FF": "0072B2", "FF00FF": "CC79A7", "EE00EE": "CC79A7", "CC00CC": "CC79A7",
    # Black box: warning & hot, cold & low, good, between, yellow, blue, magenta
    "FF3D3D": _CB["loss"], "3DC8FF": _CB["gain"], "2FC46A": _CB["player"], "FF9F1C": _CB["warning"],
    "FFC400": _CB["gold"], "3D8BFF": "0072B2", "B0106A": "CC79A7",
})

# Overlay themes: design (modern, or legacy: classic look) & colors (dark slate, gray or light)
THEME_NAMES = rxp.THEME_NAMES
DEFAULT_THEME = THEME_NAMES[0]

# Color option roles on light themes
BACKGROUND = "background"  # panel, cell background: grays inverted, colors kept
FOREGROUND = "foreground"  # text, bar or mark on panel: grays inverted, colors darkened
ON_COLOR = "on_color"  # text on a colored background: kept
# Background options also drawn as text or mark on panel (deltabest gain & loss: delta text & bar mark)
COLORED_ON_PANEL = frozenset(("background_color_time_gain", "background_color_time_loss"))

_HEX_RGB = re.compile(r"[0-9A-F]{6}")


class OverlayTheme(NamedTuple):
    """Overlay theme: design & colors"""

    modern: bool  # modern design, else legacy (classic look)
    light: bool  # light panels & dark text
    colorblind: bool  # colorblind safe colors
    grey: bool = False  # neutral gray panels (Modern Grey)

    @property
    def recolors(self) -> bool:
        """Whether classic colors are changed"""
        return self.modern or self.light or self.colorblind  # grey is a modern theme


def overlay_theme(style: dict) -> OverlayTheme:
    """Overlay theme of global overlay style setting"""
    name = style.get("overlay_theme")
    if name not in THEME_NAMES:
        name = DEFAULT_THEME
    return OverlayTheme(
        modern=not name.startswith("Legacy"),
        light=name == "Modern White",
        colorblind=bool(style.get("enable_colorblind_colors", False)),
        grey=name == "Modern Grey",
    )


def _channels(rgb: str) -> tuple[int, int, int]:
    return int(rgb[0:2], 16), int(rgb[2:4], 16), int(rgb[4:6], 16)


def _is_neutral(rgb: str) -> bool:
    channels = _channels(rgb)
    return max(channels) - min(channels) <= NEUTRAL_SPREAD


def _luminance(rgb: str) -> float:
    """WCAG relative luminance"""
    red, green, blue = (
        value / 3294.6 if value <= 10 else ((value / 255 + 0.055) / 1.055) ** 2.4  # 3294.6 = 255 x 12.92
        for value in _channels(rgb)
    )
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast(first: str, second: str) -> float:
    """WCAG contrast ratio (1 to 21)"""
    lighter, darker = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _hls(rgb: str) -> tuple[float, float, float]:
    red, green, blue = _channels(rgb)
    return colorsys.rgb_to_hls(red / 255, green / 255, blue / 255)


def _from_hls(hue: float, lightness: float, saturation: float) -> str:
    return "".join(f"{round(value * 255):02X}" for value in colorsys.hls_to_rgb(hue, lightness, saturation))


def _inverted(rgb: str) -> str:
    """Gray of light theme: same hue, lightness inverted"""
    hue, lightness, saturation = _hls(rgb)
    return _from_hls(hue, 1 - lightness, saturation)


def _darkened(rgb: str, panel: str) -> str:
    """Color of light theme: same hue, darkened until readable on light panel"""
    hue, lightness, saturation = _hls(rgb)
    color = rgb
    while lightness > 0 and _contrast(color, panel) < MINIMUM_CONTRAST:
        lightness = max(lightness - 0.02, 0.0)
        color = _from_hls(hue, lightness, saturation)
    return color


@lru_cache(maxsize=4096)
def theme_rgb(rgb: str, theme: OverlayTheme, role: str = FOREGROUND) -> str:
    """Theme color of classic color (RRGGBB, upper case)"""
    if theme.colorblind and rgb in COLORBLIND_COLORS:
        color = COLORBLIND_COLORS[rgb]
    elif theme.modern:
        color = MODERN_PALETTE.get(rgb, rgb)
        if theme.grey:
            color = MODERN_GREY_NEUTRALS.get(rgb, color)
    else:
        color = rgb
    if not theme.light or role == ON_COLOR:
        return color
    if _is_neutral(rgb):
        return MODERN_LIGHT_NEUTRALS.get(rgb) or _inverted(color)
    if role == BACKGROUND:
        return color
    return _darkened(color, MODERN_LIGHT_PANEL)


# Web pages (dashboard, stream editor, Broadcast Director) are drawn in the slate grays of Modern Dark; with the Modern
# Grey overlay theme they use the neutral grays of the overlays (same table as the overlays, one source)
_PAGE_HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")
SLATE_TO_GREY = MappingProxyType({MODERN_PALETTE[key]: grey for key, grey in MODERN_GREY_NEUTRALS.items()
                                  if key in MODERN_PALETTE})


def grey_of(rgb: str) -> str:
    """Neutral gray of a slate (low saturation, blue) color RRGGBB: the Modern Grey gray of the overlays, else a gray of
    the same lightness; other colors unchanged"""
    rgb = rgb.upper()
    if rgb in SLATE_TO_GREY:
        return SLATE_TO_GREY[rgb]
    hue, lightness, saturation = _hls(rgb)
    if 0 < saturation < 0.4 and 0.5 < hue < 0.75:
        level = round(lightness * 255)
        return f"{level:02X}{level:02X}{level:02X}"
    return rgb


SLATE_TO_LIGHT = MappingProxyType({MODERN_PALETTE[key]: light for key, light in MODERN_LIGHT_NEUTRALS.items()
                                   if key in MODERN_PALETTE})


def light_of(rgb: str) -> str:
    """Light theme color of a slate (low saturation, blue) color RRGGBB of a dark page: the Modern White gray of the
    overlays, else the same color with its lightness inverted; other colors unchanged"""
    rgb = rgb.upper()
    if rgb in SLATE_TO_LIGHT:
        return SLATE_TO_LIGHT[rgb]
    hue, _lightness, saturation = _hls(rgb)
    if 0 < saturation < 0.4 and 0.5 < hue < 0.75:
        return _inverted(rgb)
    return rgb


def is_grey_theme(style: Mapping[str, Any] | None) -> bool:
    """Overlay theme of global overlay style is Modern Grey"""
    return bool(style) and style.get("overlay_theme") == "Modern Grey"  # type: ignore[union-attr]


def is_light_theme(style: Mapping[str, Any] | None) -> bool:
    """Overlay theme of global overlay style is Modern White"""
    return bool(style) and style.get("overlay_theme") == "Modern White"  # type: ignore[union-attr]


def _swap_colors(page: str, convert) -> str:
    def swap(match: re.Match) -> str:
        text = match.group()
        color = convert(text[1:])
        color = color.lower() if text[1:] == text[1:].lower() else color
        return f"#{color}"

    return _PAGE_HEX.sub(swap, page)


def grey_page(page: str) -> str:
    """Page text with its slate colors (#RRGGBB) turned neutral gray, case of the hex digits kept"""
    return _swap_colors(page, grey_of)


def light_page(page: str) -> str:
    """Page text with its slate colors (#RRGGBB) turned into the light grays of Modern White"""
    return _swap_colors(page, light_of)


def themed_page(page: str, style: Mapping[str, Any] | None, graphics: bool = False) -> str:
    """Page in the colors of the overlay theme: Modern Grey neutral grays, Modern White light grays, else unchanged.
    graphics: a page drawing graphics for a video (stream results, Broadcast Director) keeps its dark colors on
    Modern White, only the grays of Modern Grey apply."""
    if is_grey_theme(style):
        return grey_page(page)
    if is_light_theme(style) and not graphics:
        return light_page(page)
    return page


def _option_rgb(value: Any) -> str | None:
    """RGB part (upper case) of #RRGGBB or #AARRGGBB color, None if not a color"""
    if not isinstance(value, str) or len(value) not in (7, 9) or value[0] != "#":
        return None
    rgb = value[-6:].upper()
    return rgb if _HEX_RGB.fullmatch(rgb) else None


def theme_color(color: str, theme: OverlayTheme, role: str = FOREGROUND) -> str:
    """Theme color of classic color (#RRGGBB or #AARRGGBB, alpha kept), other formats unchanged"""
    rgb = _option_rgb(color)
    if rgb is None:
        return color
    themed = theme_rgb(rgb, theme, role)
    if themed == rgb:
        return color
    return f"{color[:-6]}{themed}"


def option_role(key: str, options: dict) -> str:
    """Role of color option on light themes, from classic default colors of widget

    Text colors are paired with background of same suffix (font_color_x, background_color_x):
    text on a colored background (flags, warnings) or on another colored element keeps its color.
    """
    if key in COLORED_ON_PANEL:
        return FOREGROUND
    if "background" in key:
        return BACKGROUND
    if not key.startswith("font_color"):
        return FOREGROUND
    text = _option_rgb(options.get(key))
    if text is None:
        return FOREGROUND
    background = _option_rgb(options.get(f"background_color{key[len('font_color'):]}"))
    if background is None:  # text on panel, unless dark text (drawn on a colored element)
        return FOREGROUND if not _is_neutral(text) or _luminance(text) > 0.18 else ON_COLOR
    if not _is_neutral(background) or _contrast(text, background) < 2:
        return ON_COLOR
    return FOREGROUND


def theme_overrides(wcfg: Mapping[str, Any], default: dict, style: dict) -> dict:
    """Get overlay theme overrides for options that still use default value

    Colors follow theme (modern palette, light & colorblind variants), modern design also sets
    modern font & minimum bar gap.

    Args:
        wcfg: widget user setting.
        default: widget default setting.
        style: global overlay style setting.

    Returns:
        Dictionary of overridden options.
    """
    theme = overlay_theme(style)
    overrides: dict[str, Any] = {}
    min_gap = max(int(style["minimum_bar_gap"]), 0)
    for key, value in wcfg.items():
        if value != default.get(key):  # user customized
            continue
        if "color" in key and isinstance(value, str):
            if theme.recolors:
                new_color = theme_color(value, theme, option_role(key, default))
                if new_color != value:
                    overrides[key] = new_color
        elif not theme.modern:
            continue
        elif style["enable_modern_font"] and key.endswith("font_name"):
            overrides[key] = style["modern_font_name"]
        elif key == "bar_gap" and isinstance(value, int) and value < min_gap:
            overrides[key] = min_gap
    return overrides


# Pixel size options scaled by global overlay scale (other geometry derives from them)
SCALED_OPTION = re.compile(
    r"(^|_)font_size$"
    r"|^display_(size|width|height)$"
    r"|(^|_)bar_(height|width)$"
    r"|^(led|wheel)_(width|height)$"
    r"|^(icon|dot|area|vehicle|brake_input)_size$"
    r"|^(delta_)?bar_length$|^bar_width_(unfiltered|filtered)$|^maximum_indicator_height$"  # pedal, deltabest
    r"|^parts_(maximum_)?(width|height)$"  # damage
    r"|^global_scale$"  # radar: pixels per meter
)
OVERLAY_SCALE_RANGE = (0.5, 3.0)
# Widgets whose "bar_width" is a number of characters (already follows font size)
CHARACTER_BAR_WIDTH = frozenset((
    "acceleration", "fuel", "fuel_energy_saver", "pit_stop_estimate", "relative_finish_order", "traffic",
    "virtual_energy",
))


def is_scaled_option(widget_name: str, key: str, value: Any) -> bool:
    """Whether option is a pixel size, scaled with widget"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if key == "bar_width" and widget_name in CHARACTER_BAR_WIDTH:
        return False
    return SCALED_OPTION.search(key) is not None


def scale_overrides(wcfg: Mapping[str, Any], scale: float, widget_name: str = "") -> dict:
    """Pixel size options multiplied by global overlay scale

    Args:
        wcfg: widget setting (with style overrides).
        scale: global overlay scale, 1 = unchanged.
        widget_name: widget name.

    Returns:
        Dictionary of scaled options.
    """
    scale = min(max(scale, OVERLAY_SCALE_RANGE[0]), OVERLAY_SCALE_RANGE[1])
    if scale == 1:
        return {}
    overrides: dict[str, Any] = {}
    for key, value in wcfg.items():
        if not is_scaled_option(widget_name, key, value):
            continue
        if isinstance(value, int):  # 0 (part hidden, maximum_indicator_height) kept, never turned on
            overrides[key] = max(round(value * scale), 1) if value > 0 else value
        else:
            overrides[key] = value * scale
    return overrides


def overlay_opacity_scale(style: Mapping[str, Any]) -> float:
    """Global overlay opacity (overlay style "overlay_opacity_percentage"), multiplies each overlay opacity:
    1 = unchanged, invalid value: unchanged"""
    percent = style.get("overlay_opacity_percentage", 100)
    if isinstance(percent, bool) or not isinstance(percent, (int, float)) or percent != percent:  # NaN
        return 1.0
    return min(max(percent, 10), 100) / 100


class StyledConfig(dict):
    """Widget setting with style overrides applied

    Reading returns overridden value; writing (such as saving widget position)
    is passed through to user setting, so overrides are never saved to file.
    """

    __slots__ = ("_source",)

    def __init__(self, source: Any, overrides: dict):  # user setting dict (typed widget setting)
        super().__init__(source)
        super().update(overrides)
        self._source = source

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self._source[key] = value
