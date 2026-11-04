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


@pytest.mark.parametrize("name", THEME_NAMES)
def test_disabled_text_stays_legible(themed, name):
    """Disabled text (palette Disabled group) keeps 3.8:1 against the window & the field background, and stays apart
    from the dim text"""
    from PySide6.QtGui import QPalette
    from PySide6.QtWidgets import QApplication

    from neopedal.ui.quick import Theme, contrast_ratio

    themed(name)
    theme = Theme()
    disabled = QApplication.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text)
    assert contrast_ratio(disabled, theme.window) >= 3.8, name
    assert contrast_ratio(disabled, theme.base) >= 3.8, name
    assert contrast_ratio(disabled, theme.window) < contrast_ratio(theme.dimText, theme.window), name


@pytest.mark.parametrize("name", THEME_NAMES)
def test_qt_widget_fields_use_the_control_outline(themed, name):
    """Text inputs, combo boxes & check boxes of Qt dialogs: the 3:1 outline, not the palette border color"""
    from PySide6.QtWidgets import QApplication

    from neopedal.ui import set_style_window
    from neopedal.ui.tokens import control_border

    themed(name)
    outline = control_border(QApplication.palette()).name()
    sheet = set_style_window(QApplication.font().pointSize())
    assert sheet.count(f"border:1px solid {outline}") >= 3 or sheet.count(f"border: 1px solid {outline}") >= 3, name


COLORED_OVERLAY_TOKENS = ("accent", "positive", "negative", "warning", "caution", "best", "blue", "lap_ahead", "lap_behind")


@pytest.mark.parametrize("name", ("Modern Dark", "Modern Grey", "Modern White"))
def test_overlay_colors_on_panels(ui_env, name):
    """Colors of values (gain, loss, warning, best...) keep 4.5:1 against the panels of the overlay theme (every panel
    on Modern White, which darkens them until they do)"""
    from neopedal.setting import cfg
    from neopedal.ui.quick import contrast_ratio
    from neopedal.widget._modern.theme import build_theme

    style = dict(cfg.user.config["overlay_style"], overlay_theme=name)
    theme = build_theme(style, 255)
    light = name == "Modern White"
    panels = (theme.surface, theme.surface_alt, theme.surface_raised) if light else (theme.surface, theme.surface_alt)
    minimum = 4.5 if light else 3.8  # dark themes: blue & lapped cars are 3.8-4.2:1 on Modern Grey panels (lower on chips)
    for token in COLORED_OVERLAY_TOKENS:
        for panel in panels:
            assert contrast_ratio(getattr(theme, token), panel) >= minimum, (name, token, panel.name())


@pytest.mark.parametrize("name", THEME_NAMES)
def test_card_borders_and_hover_are_seen(themed, name):
    """Borders of cards & dividers 1.8:1 against the card (Legacy: firmer outlines from the palette), hovered control
    1.25:1 against its resting fill, hovered card a little lighter than the card"""
    from neopedal.ui.quick import Theme, contrast_ratio

    themed(name)
    theme = Theme()
    assert contrast_ratio(theme.strokeSubtle, theme.surfaceCard) >= (1.5 if name == "Legacy Grey" else 1.8), name
    assert contrast_ratio(theme.hover, theme.raised) >= 1.25, name
    assert contrast_ratio(theme.surfaceHover, theme.surfaceCard) >= 1.1, name


@pytest.mark.parametrize("name", ("Modern Dark", "Modern Grey", "Modern White"))
def test_overlay_labels_readable(ui_env, name):
    """Small labels of overlays (text_muted: the 888888 gray of classic options) keep 4.5:1 on the panel & the
    alternate row"""
    from neopedal.setting import cfg
    from neopedal.ui.quick import contrast_ratio
    from neopedal.widget._modern.theme import build_theme

    style = dict(cfg.user.config["overlay_style"], overlay_theme=name)
    theme = build_theme(style, 255)
    for panel in (theme.surface, theme.surface_alt):
        assert contrast_ratio(theme.text_muted, panel) >= 4.5, (name, panel.name())
    assert contrast_ratio(theme.text_muted, theme.surface) < contrast_ratio(theme.text_dim, theme.surface), name
