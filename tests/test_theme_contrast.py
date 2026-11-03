"""Contrast ratchet of the four window themes: every text, accent & status color against every surface it is drawn on

WCAG 2.x: text 4.5:1 (main text 7:1), outlines of controls 3:1. A new color or surface that breaks one of these fails
here (tools/theme_contrast.py prints the whole table).
"""

import pytest
from PySide6.QtGui import QColor

from neopedal.regex_pattern import THEME_NAMES

SURFACES = ("surfacePage", "surfaceCard", "surfaceFlyout", "surfaceSunken", "surfaceHover", "raised")
STATUS_TEXT = ("gain", "loss", "warning", "purple", "gold")


@pytest.fixture
def themed(ui_env):
    from neopedal.ui import set_style_palette

    yield set_style_palette
    set_style_palette("Modern Dark")


@pytest.mark.parametrize("name", THEME_NAMES)
def test_text_on_every_surface(themed, name):
    from neopedal.ui.quick import Theme, contrast_ratio

    themed(name)
    theme = Theme()
    for surface_name in SURFACES:
        surface = getattr(theme, surface_name)
        assert contrast_ratio(theme.text, surface) >= 7, (name, surface_name, "text")
        assert contrast_ratio(theme.dimText, surface) >= 4.5, (name, surface_name, "dim text")


@pytest.mark.parametrize("name", THEME_NAMES)
def test_accent_and_status_text_on_every_surface(themed, name):
    from neopedal.ui.quick import Theme, contrast_ratio

    themed(name)
    theme = Theme()
    for surface_name in SURFACES:
        surface = getattr(theme, surface_name)
        for color_name in ("accent", "info", *STATUS_TEXT):
            assert contrast_ratio(getattr(theme, color_name), surface) >= 4.5, (name, surface_name, color_name)


@pytest.mark.parametrize("name", THEME_NAMES)
def test_white_on_filled_buttons(themed, name):
    from neopedal.ui.quick import Theme, contrast_ratio

    themed(name)
    theme = Theme()
    for fill in (theme.accentFill, theme.accentHover, theme.accentPressed, theme.lossFill, theme.lossHover):
        assert contrast_ratio(QColor("white"), fill) >= 4.5, (name, fill.name())


@pytest.mark.parametrize("name", THEME_NAMES)
def test_control_outline_three_to_one(themed, name):
    """Outline of fields, combo boxes & switches: 3:1 against the page, the cards & the field background"""
    from neopedal.ui.quick import Theme, contrast_ratio

    themed(name)
    theme = Theme()
    for surface in (theme.surfacePage, theme.surfaceCard, theme.surfaceFlyout, theme.surfaceSunken, theme.base, theme.window):
        assert contrast_ratio(theme.controlBorder, surface) >= 3, (name, surface.name())
    assert contrast_ratio(theme.strokeStrong, theme.surfaceCard) >= 3, name  # hovered control keeps it
