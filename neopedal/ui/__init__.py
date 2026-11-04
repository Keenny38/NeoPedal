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
Application UI, style
"""

import html
import re
import sys

from PySide6 import QtGui
from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QIcon,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle, QWidget

from ..const_app import PLATFORM
from ..const_file import ImageFile
from ..theme_data import STATUS_COLORS, WINDOW_PALETTES

WINDOWS_THEME_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"

# Tags kept by safe_markup: text style & line breaks of messages, nothing that loads or opens anything
_SAFE_TAGS = re.compile(r"&lt;(/?)(b|i|br|code)&gt;")


def safe_markup(text: str) -> str:
    """Rich text of a message (toast, confirmation, status line) keeping only <b>, <i>, <br> & <code>

    Messages put file names, errors & names from the game or shared files in markup: an <img src="//host/a">
    there would load a picture from the network (address leaked, Windows file share login sent), a <font>
    or <a> would hide or fake lines. Values already escaped by the message (&lt;, &amp;) are shown the same.
    """
    return _SAFE_TAGS.sub(r"<\1\2>", html.escape(html.unescape(text), quote=False))


def message_text(text: str) -> str:
    """Text of a message box (Qt reads it as rich text when it starts like markup): kept to safe_markup when read
    as rich text, plain text as is"""
    return safe_markup(text) if QtGui.Qt.mightBeRichText(text) else text

_WINDOW_THEMES: dict[int, str] = {}  # window color (rgb) -> "Dark" or "Light"


def palette_theme(palette: QPalette | None = None) -> str:
    """Window color theme of palette (app palette if not set): "Dark" or "Light" (asked for at every status color)"""
    if palette is None:
        palette = QApplication.palette()
    window = palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Window)
    theme = _WINDOW_THEMES.get(window.rgb())
    if theme is None:
        theme = _WINDOW_THEMES[window.rgb()] = "Dark" if window.lightness() < 128 else "Light"
    return theme


def status_color(name: str, palette: QPalette | None = None) -> str:
    """Status color (see STATUS_COLORS) matching window color theme in use"""
    return STATUS_COLORS[palette_theme(palette)][name]


def has_keyboard_focus(widget: QWidget) -> bool:
    """Widget has focus reached by keyboard (Tab, shortcut), not by mouse click"""
    window = widget.window()
    return widget.hasFocus() and window is not None and window.testAttribute(
        Qt.WidgetAttribute.WA_KeyboardFocusChange)


def draw_focus_ring(painter: QPainter, widget: QWidget, area: QRectF, radius: float):
    """Accent outline around custom drawn button reached by keyboard: 2 px, a gap outside its shape (area), rounded
    like it, as FocusRing of QML pages (kept inside the widget)"""
    if not has_keyboard_focus(widget):
        return
    width = max(UIScaler.pixel(2), 2)
    gap = max(2.0, round(UIScaler.FONT_PIXEL_SCALED * 0.18))  # FocusRing.gap
    ring = area.adjusted(-gap, -gap, gap, gap).intersected(QRectF(widget.rect()))
    half = width / 2  # stroke centered on the path: inside the ring
    pen = QPen(widget.palette().color(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight))
    pen.setWidthF(width)
    painter.save()
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(ring.adjusted(half, half, -half, -half), radius + gap - half, radius + gap - half)
    painter.restore()


# Message box icons drawn in window color theme (native ones clash with app theme)
MESSAGE_ICON_KINDS = {
    QStyle.StandardPixmap.SP_MessageBoxInformation: "information",
    QStyle.StandardPixmap.SP_MessageBoxWarning: "warning",
    QStyle.StandardPixmap.SP_MessageBoxCritical: "critical",
    QStyle.StandardPixmap.SP_MessageBoxQuestion: "question",
}
MESSAGE_ICON_SIZE = 128  # pixels, scaled down by message box


def message_icon_color(kind: str, palette: QPalette | None = None) -> QColor:
    """Fill color of message box icon"""
    if kind == "warning":
        return QColor(status_color("badge_warning", palette))
    if kind == "critical":
        return QColor(status_color("badge_danger", palette))
    if palette is None:
        palette = QApplication.palette()
    return palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight)


def message_icon(kind: str, palette: QPalette | None = None) -> QIcon:
    """Message box icon: filled circle (triangle for warning) with glyph, in window color theme"""
    size = MESSAGE_ICON_SIZE
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(message_icon_color(kind, palette))
    margin = size * 0.06
    if kind == "warning":
        top, bottom = size * 0.1, size * 0.9
        painter.drawPolygon(QPolygonF((
            QPointF(size / 2, top), QPointF(size - margin, bottom), QPointF(margin, bottom))))
        glyph_area = QRectF(0, size * 0.32, size, size * 0.56)
    else:
        painter.drawEllipse(QRectF(margin, margin, size - margin * 2, size - margin * 2))
        glyph_area = QRectF(0, 0, size, size)
    glyph_color = QColor(status_color("badge_text", palette))
    if kind == "critical":  # cross
        pen = QPen(glyph_color)
        pen.setWidthF(size * 0.1)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        low, high = size * 0.34, size * 0.66
        painter.drawLine(QPointF(low, low), QPointF(high, high))
        painter.drawLine(QPointF(high, low), QPointF(low, high))
    else:
        font = QFont(QApplication.font())
        font.setBold(True)
        font.setPixelSize(round(glyph_area.height() * (0.75 if kind == "warning" else 0.6)))
        painter.setFont(font)
        painter.setPen(glyph_color)
        glyph = {"information": "i", "question": "?"}.get(kind, "!")
        painter.drawText(glyph_area, Qt.AlignmentFlag.AlignCenter, glyph)
    painter.end()
    return QIcon(pixmap)


class MessageIconStyle(QProxyStyle):
    """App style with message box icons drawn in window color theme"""

    def standardIcon(self, standard_icon, option=None, widget=None):
        kind = MESSAGE_ICON_KINDS.get(standard_icon)
        if kind is not None:
            return message_icon(kind)
        return super().standardIcon(standard_icon, option, widget)


_message_icon_style: list[MessageIconStyle] = []  # installed style, reference kept


def install_message_icons() -> bool:
    """Wrap app style (Fusion) to draw message box icons, once, True if installed now"""
    app = QApplication.instance()
    if not isinstance(app, QApplication) or _message_icon_style:
        return False
    style = MessageIconStyle(app.style().name())
    _message_icon_style.append(style)
    QApplication.setStyle(style)
    return True


class UIScaler:
    """UI font & size scaler"""
    # Global base font size in point (not counting dpi scale)
    FONT_POINT = QApplication.font().pointSize()
    FONT_DPI = QFontMetrics(QApplication.font()).fontDpi()
    # Global base font size in pixel (dpi scaled)
    # dpi scale = font dpi / 96
    # px = (pt * dpi scale) * 96 / 72
    # px = pt * font dpi / 72
    FONT_DPI_SCALE = FONT_DPI / 96
    FONT_PIXEL_SCALED = FONT_POINT * FONT_DPI / 72

    @classmethod
    def font(cls, scale: float) -> float:
        """Scale UI font size (points) by base font size (not counting dpi scale)"""
        return cls.FONT_POINT * scale

    @classmethod
    def size(cls, scale: float) -> int:
        """Scale UI size (pixels) by base font size (scaled with dpi)"""
        return round(cls.FONT_PIXEL_SCALED * scale)

    @classmethod
    def pixel(cls, pixel: int):
        """Scale pixel size by base font DPI scale"""
        return round(cls.FONT_DPI_SCALE * pixel)


class ColorblindState(QObject):
    """App wide "colorblind safe colors" state of pages (QML theme status colors follow it)"""

    changed = Signal()

    def __init__(self):
        super().__init__()
        self.enabled = False


_COLORBLIND: list[ColorblindState] = []


def colorblind_state() -> ColorblindState:
    """Shared state object, created on first use"""
    if not _COLORBLIND:
        _COLORBLIND.append(ColorblindState())
    return _COLORBLIND[0]


def set_colorblind(enabled: bool):
    """Status colors of app pages (gain, loss, warning, purple) in colorblind safe colors or not"""
    state = colorblind_state()
    if state.enabled != bool(enabled):
        state.enabled = bool(enabled)
        state.changed.emit()


def resolve_color_theme(color_theme: str) -> str:
    """Colors of window theme (see regex_pattern.THEME_NAMES): "Dark" (Modern Dark, Modern Grey, Legacy Grey) or
    "Light" (Modern White)"""
    return "Light" if color_theme == "Modern White" else "Dark"


def system_dark_mode() -> bool:
    """Whether OS taskbar & tray are dark (Windows mode, not app mode), else OS color scheme"""
    if PLATFORM.WINDOWS and sys.platform == "win32":  # platform check also read by type checker
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_THEME_KEY) as key:
                return winreg.QueryValueEx(key, "SystemUsesLightTheme")[0] == 0
        except OSError:  # older Windows without light / dark mode
            pass
    return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


def app_icon_file(dark: bool) -> str:
    """App icon file: white & gold for dark theme, black & gold for light theme"""
    return ImageFile.APP_ICON_DARK if dark else ImageFile.APP_ICON


_LEGACY = [False]  # palette set by set_style_palette is a Legacy one


def legacy_style() -> bool:
    """Legacy (classic) theme in use: QML pages tell it by tokens (smaller corners, firmer strokes, plain headers)"""
    return _LEGACY[0]


def palette_rows(color_theme: str):
    """QPalette rows (active, inactive, disabled, role) of a window theme (see theme_data.WINDOW_PALETTES)"""
    return tuple((active, inactive, disabled, getattr(QPalette.ColorRole, role))
                 for role, (active, inactive, disabled) in WINDOW_PALETTES[color_theme].items())


def window_palette(color_theme: str):
    """Palette rows of window theme: Modern Dark, Modern Grey, Modern White or Legacy Grey (classic colors)"""
    return palette_rows(color_theme if color_theme in WINDOW_PALETTES else "Modern Dark")


def palette_light():
    return palette_rows("Modern White")


def palette_dark():
    return palette_rows("Modern Dark")


def palette_grey():
    return palette_rows("Modern Grey")


def palette_legacy_grey():
    return palette_rows("Legacy Grey")


_GREY = [False]  # palette set by set_style_palette is Modern Grey


def grey_style() -> bool:
    """Modern Grey theme in use: neutral grays all through (QML pages draw overlay preview stages in neutral gray)"""
    return _GREY[0]


def theme_swatch(color_theme: str) -> list[str]:
    """Colors showing a window theme (window, card, text, accent), for the theme choice of Settings"""
    wanted = (QPalette.ColorRole.Window, QPalette.ColorRole.Base, QPalette.ColorRole.Text, QPalette.ColorRole.Highlight)
    colors = {role: active for active, _, _, role in window_palette(color_theme)}
    return [str(colors[role]) for role in wanted]


def set_style_palette(color_theme: str):
    """Set style palette of window theme (see window_palette)"""
    _LEGACY[0] = color_theme.startswith("Legacy")  # before the palette: pages read it on paletteChanged
    _GREY[0] = color_theme == "Modern Grey"
    palette_theme = window_palette(color_theme)

    palette = QGuiApplication.palette()
    group_active = QPalette.ColorGroup.Active
    group_inactive = QPalette.ColorGroup.Inactive
    group_disabled = QPalette.ColorGroup.Disabled
    for color_active, color_inactive, color_disabled, color_role in palette_theme:
        palette.setColor(group_active, color_role, color_active)
        palette.setColor(group_inactive, color_role, color_inactive)
        palette.setColor(group_disabled, color_role, color_disabled)
    QApplication.setPalette(palette)


_STYLE_SHEETS: dict[tuple, str] = {}  # (font size, palette, look) -> style sheet, a few kept for theme switches
STYLE_SHEETS_KEPT = 8


def set_style_window(base_font_pt: int) -> str:
    """Style sheet of the app window & dialogs (not affecting overlay), kept per font size, palette & look: switching
    back to a theme used before builds nothing"""
    key = (base_font_pt, QApplication.palette().cacheKey(), legacy_style(), grey_style())
    sheet = _STYLE_SHEETS.get(key)
    if sheet is None:
        if len(_STYLE_SHEETS) >= STYLE_SHEETS_KEPT:
            _STYLE_SHEETS.clear()
        sheet = _STYLE_SHEETS[key] = build_style_window(base_font_pt)
    return sheet


def build_style_window(base_font_pt: int) -> str:
    # Scale font (point size)
    font_pt_item_name = 1.2 * base_font_pt
    font_pt_item_button = 1.05 * base_font_pt
    font_pt_item_toggle = 1.0 * base_font_pt
    font_pt_text_browser = 0.9 * base_font_pt
    font_pt_app_name = 1.4 * base_font_pt

    # Size (Legacy themes: corners half as round, as QML pages): radius tokens of QML pages (ui/tokens.py)
    from .tokens import control_border, hover_fill, radius_px, stroke_subtle, surface_flyout

    legacy = legacy_style()
    corner = 0.5 if legacy else 1
    border_radius_button = 0.4 * corner  # em
    border_radius_input = round(radius_px("radiusSm", UIScaler.FONT_PIXEL_SCALED, legacy))  # px
    border_radius_card = round(radius_px("radiusLg", UIScaler.FONT_PIXEL_SCALED, legacy))  # px, list & search box

    # Color
    palette = QApplication.palette()
    palette.setCurrentColorGroup(QPalette.ColorGroup.Active)
    color_active_window_text = palette.windowText().color().name()
    color_active_window = palette.window().color().name()
    color_active_base = palette.base().color().name()
    color_active_button = palette.button().color().name()
    color_active_mid = palette.mid().color().name()
    color_active_midlight = palette.midlight().color().name()
    color_active_highlighted_text = palette.highlightedText().color().name()
    color_active_highlight = palette.highlight().color().name()
    color_selection = f"#CC{color_active_highlight[1:]}"  # 80% alpha highlight
    # Menus & rail as QML pages: flyout surface, subtle stroke, hovered item in the hover color of controls
    color_flyout = surface_flyout(palette).name()
    color_stroke_subtle = stroke_subtle(palette, legacy).name()
    color_hover = hover_fill(palette).name()
    color_control_border = control_border(palette).name()  # outline of fields, combo boxes & check boxes: 3:1

    palette.setCurrentColorGroup(QPalette.ColorGroup.Inactive)
    color_inactive_highlighted_text = palette.highlightedText().color().name()
    color_inactive_highlight = palette.highlight().color().name()

    palette.setCurrentColorGroup(QPalette.ColorGroup.Disabled)
    color_disabled_window_text = palette.windowText().color().name()
    color_disabled_highlight = palette.highlight().color().name()

    color_success_border = status_color("success_border", palette)
    color_danger = status_color("danger", palette)
    color_warning = status_color("warning", palette)
    color_info = status_color("info", palette)

    # Strip off indentation & comment
    return re.sub(r"\s{4,}|\/\*.*\/", "", f"""
        /* Misc */
        QSizeGrip {{
            image: none;
            width: 4px;
        }}
        QToolTip {{
            color: {color_active_window_text};
            background: {color_active_window};
            border: 1px solid {color_active_mid};
            padding: 0.2em 0.3em;
        }}
        QStatusBar::item {{
            border: none;
        }}

        /* Generic push button */
        QPushButton {{
            color: {color_active_window_text};
            background: {color_active_button};
            border: 1px solid {color_active_mid};
            border-radius: {border_radius_button}em;
            padding: 0.3em 0.8em;
        }}
        QPushButton:hover {{
            border-color: {color_active_highlight};
        }}
        QPushButton:pressed,
        QPushButton:checked {{
            color: {color_inactive_highlighted_text};
            background: {color_inactive_highlight};
            border-color: {color_inactive_highlight};
        }}
        QPushButton:default {{
            border-color: {color_active_highlight};
        }}
        QPushButton:disabled {{
            color: {color_disabled_window_text};
            background: {color_active_window};
        }}
        CompactButton {{
            padding: 0.2em 0.1em;
        }}

        /* Generic text input */
        QLineEdit,
        QPlainTextEdit,
        QTextEdit {{
            border: 1px solid {color_control_border};
            border-radius: {border_radius_input}px;
            padding: 0.1em 0.25em;
            selection-color: {color_active_highlighted_text};
            selection-background-color: {color_active_highlight};
        }}
        QLineEdit:focus,
        QPlainTextEdit:focus,
        QTextEdit:focus {{
            border-color: {color_active_highlight};
        }}
        QLineEdit:disabled {{
            color: {color_disabled_window_text};
        }}

        /* Generic combo box */
        QComboBox {{
            color: {color_active_window_text};
            background: {color_active_button};
            border: 1px solid {color_control_border};
            border-radius: {border_radius_input}px;
            padding: 0.1em 1.6em 0.1em 0.4em;
        }}
        QComboBox:hover {{
            border-color: {color_active_highlight};
        }}
        QComboBox:disabled {{
            color: {color_disabled_window_text};
        }}
        QComboBox QAbstractItemView {{
            background: {color_active_base};
            border: 1px solid {color_active_mid};
            selection-color: {color_active_highlighted_text};
            selection-background-color: {color_active_highlight};
            outline: none;
        }}

        /* Generic checkbox & radio button (filled square/dot, no checkmark glyph) */
        QCheckBox::indicator,
        QRadioButton::indicator {{
            width: 1em;
            height: 1em;
            border: 1px solid {color_control_border};
            background: {color_active_base};
        }}
        QCheckBox::indicator {{
            border-radius: {border_radius_input}px;
        }}
        QRadioButton::indicator {{
            border-radius: 0.5em;
        }}
        QCheckBox::indicator:hover,
        QRadioButton::indicator:hover {{
            border-color: {color_active_highlight};
        }}
        QCheckBox::indicator:checked,
        QRadioButton::indicator:checked {{
            background: {color_active_highlight};
            border-color: {color_active_highlight};
        }}
        QCheckBox:disabled,
        QRadioButton:disabled {{
            color: {color_disabled_window_text};
        }}
        QCheckBox::indicator:disabled,
        QRadioButton::indicator:disabled {{
            border-color: {color_disabled_window_text};
        }}

        /* Generic slider */
        QSlider::groove:horizontal {{
            height: 4px;
            background: {color_active_mid};
            border-radius: 2px;
        }}
        QSlider::sub-page:horizontal {{
            background: {color_active_highlight};
            border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            width: 1em;
            height: 1em;
            margin: -0.4em 0;
            border-radius: 0.5em;
            background: {color_active_window_text};
        }}
        QSlider::handle:horizontal:hover {{
            background: {color_active_highlight};
        }}

        /* Tabs */
        QTabWidget::pane {{
            border: none;
            border-top: 1px solid {color_active_mid};
        }}
        QTabBar::tab {{
            color: {color_disabled_window_text};
            background: transparent;
            border: none;
            border-bottom: 2px solid transparent;
            padding: 0.4em 0.5em;
            font-weight: 600;
        }}
        QTabBar::tab:hover {{
            color: {color_active_window_text};
            border-bottom-color: {color_active_mid};
        }}
        QTabBar::tab:selected {{
            color: {color_active_window_text};
            border-bottom-color: {color_active_highlight};
        }}

        /* Menu */
        QMenuBar {{
            background: {color_active_window};
            border-bottom: 1px solid {color_active_mid};
        }}
        QMenuBar::item {{
            padding: 0.25em 0.6em;
            border-radius: {border_radius_input}px;
            background: transparent;
        }}
        QMenuBar::item:selected {{
            background: {color_active_midlight};
        }}
        QMenu {{
            background: {color_flyout};
            border: 1px solid {color_stroke_subtle};
            padding: 0.2em;
        }}
        QMenu::item {{
            padding: 0.3em 1.5em 0.3em 1.8em;
            border-radius: {border_radius_input}px;
        }}
        QMenu::item:selected {{
            color: {color_active_window_text};
            background: {color_hover};
        }}
        QMenu::item:disabled {{
            color: {color_disabled_window_text};
            background: transparent;
        }}
        QMenu::separator {{
            height: 1px;
            background: {color_active_mid};
            margin: 0.2em 0.4em;
        }}

        /* Table header */
        QHeaderView::section {{
            color: {color_active_window_text};
            background: {color_active_window};
            border: none;
            border-right: 1px solid {color_active_mid};
            border-bottom: 1px solid {color_active_mid};
            padding: 0.2em 0.4em;
        }}
        QTableView {{
            gridline-color: {color_active_mid};
        }}

        /* Scroll bar */
        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 0;
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 10px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {color_active_mid};
            min-height: 24px;
            border-radius: 3px;
            margin: 2px;
        }}
        QScrollBar::handle:horizontal {{
            background: {color_active_mid};
            min-width: 24px;
            border-radius: 3px;
            margin: 2px;
        }}
        QScrollBar::handle:hover {{
            background: {color_disabled_window_text};
        }}
        QScrollBar::add-line,
        QScrollBar::sub-line {{
            width: 0;
            height: 0;
        }}
        QScrollBar::add-page,
        QScrollBar::sub-page {{
            background: none;
        }}

        /* Main window (font family: app font, see main.set_app_font) */
        AppWindow QMenuBar {{
            border-bottom: none;
            padding: 0.25em 0.3em;
        }}
        AppWindow QMenuBar::item {{
            padding: 0.3em 0.7em;
            border-radius: {border_radius_card}px;
        }}
        AppWindow QMenu {{
            border-radius: {border_radius_card}px;
            padding: 0.3em;
        }}
        #titleMenuBar {{
            background: transparent;
            padding: 0;
        }}
        #navRail {{
            background: {color_active_window};
            border-right: 1px solid {color_stroke_subtle};
        }}
        #navRail[merged="true"] {{
            border-right: none;
        }}
        #navRailScroll, #navRailList {{
            background: transparent;
        }}
        #navRailScroll QScrollBar:vertical {{
            width: 6px;
        }}
        #navRailScroll QScrollBar::handle:vertical {{
            margin: 1px;
        }}
        #pickerCard {{
            background: {color_active_base};
            border: 1px solid {color_active_midlight};
            border-radius: {border_radius_card}px;
        }}
        #pickerTitle {{
            font-size: {font_pt_item_button}pt;
            font-weight: bold;
        }}
        #pickerList {{
            background: transparent;
            border: none;
            outline: none;
        }}
        #pickerEmpty, #pickerHelp {{
            color: {color_disabled_window_text};
        }}
        #pickerEmpty {{
            padding: 1.5em 0.5em;
        }}
        #editorPrimary {{
            color: {color_active_highlighted_text};
            background: {color_active_highlight};
            border-color: {color_active_highlight};
            font-weight: bold;
        }}
        #toast {{
            color: {color_active_window_text};
            background: {color_active_base};
            border: 1px solid {color_active_highlight};
            border-radius: {border_radius_card}px;
        }}
        #toast[level="success"] {{
            border-color: {color_success_border};
        }}
        #toast[level="info"] {{
            border-color: {color_info};
        }}
        #toast[level="warning"] {{
            border-color: {color_warning};
        }}
        #toast[level="error"] {{
            border-color: {color_danger};
        }}
        #pageStack {{
            background: {color_active_window};
        }}

        /* Main status bar: notify bar & saving state */
        AppWindow QStatusBar {{
            border-top: 1px solid {color_active_midlight};
            padding: 0.15em 0.3em;
        }}
        AppWindow[modernFrame="true"] QStatusBar {{
            border-top: none;
        }}
        AppWindow QStatusBar #labelSaving {{
            font-size: {font_pt_text_browser}pt;
            color: {color_disabled_window_text};
            padding: 0 0.4em;
        }}

        /* Notify bar */
        NotifyBar QPushButton {{
            font-weight: bold;
            padding: 0.2em;
            border: none;
            border-radius: 0;
            color: {color_active_highlighted_text};
        }}
        NotifyBar QPushButton::menu-indicator {{
            image: none;
            width: 0;
        }}
        NotifyBar UpdatesNotifyButton {{
            background: {color_active_highlight};
        }}

        /* Base dialog */
        BaseDialog QStatusBar {{
            font-weight:bold;
        }}
        BaseDialog QTextBrowser {{
            font-size: {font_pt_text_browser}pt;
        }}
        BaseEditor QTableWidget ColorEdit {{
            border: none;
        }}

        /* Driver stats viewer: cards & key figure tiles */
        DriverStatsViewer #fuelCard,
        DriverStatsViewer #fuelTile {{
            background: {color_active_base};
            border: 1px solid {color_active_midlight};
            border-radius: {border_radius_card}px;
        }}
        DriverStatsViewer #fuelCardTitle {{
            font-size: {font_pt_item_button}pt;
            font-weight: bold;
        }}
        DriverStatsViewer #fuelTileValue {{
            font-size: {font_pt_app_name}pt;
            font-weight: bold;
        }}

        /* Driver stats viewer: table & level marks */
        DriverStatsViewer QTableWidget {{
            background: {color_active_base};
            alternate-background-color: {color_active_window};
        }}
        DriverStatsViewer #statsMark {{
            color: {color_active_highlight};
            font-weight: bold;
        }}
        DriverStatsViewer #statsTrack {{
            font-size: {font_pt_item_button}pt;
            font-weight: bold;
            padding: 0.2em 0.5em;
        }}

        /* About dialog */
        About QLabel {{
            font-size: {font_pt_text_browser}pt;
        }}
        About QTextBrowser {{
            border: none;
        }}
        About #labelAppName {{
            font-size: {font_pt_app_name}pt;
        }}

        /* Config dialog */
        UserConfig #widgetPreview {{
            background: #39424E;
        }}
        UserConfig OptionGroup {{
            font-size: {font_pt_item_name}pt;
            font-weight: bold;
            color: {color_active_window_text};
            background: {color_disabled_highlight};
            padding: 0.2em 0;
        }}
        UserConfig QLineEdit[invalid="true"] {{
            border-color: {color_danger};
        }}
        UserConfig QLineEdit[invalid="true"]:focus {{
            border: 2px solid {color_danger};
        }}
        UserConfig #optionError,
        UserConfig #optionInvalidStatus {{
            color: {color_danger};
            font-weight: bold;
        }}

        /* Tyre strategy planner (dialog) */
        TyreSetList {{
            font-size: {font_pt_item_toggle}pt;
            font-weight: bold;
            outline: none;
        }}
        TyreSetList::item {{
            margin: 1px;
            padding: 0.1em;
            border: 0.1em solid {color_disabled_highlight};
        }}
        TyreSetList::item:selected {{
            selection-color: {color_active_highlighted_text};
            background: {color_selection};
            border: 0.1em solid {color_active_highlight};
        }}
        TyreSetItemTag QLabel {{
            font-size: {font_pt_text_browser}pt;
            font-weight: bold;
            color: {color_active_highlighted_text};
            border-radius: {border_radius_button}em;
            margin-left: 0.2em;
        }}
        TyrePlanTable {{
            font-size: {font_pt_item_toggle}pt;
            font-weight: bold;
            outline: none;
        }}
        TyrePlanTable::item {{
            margin: 1px;
            padding: 0.1em;
            border: 0.1em solid {color_disabled_highlight};
        }}
        TyrePlanTable::item:selected {{
            margin: 1px;
            padding: 0.1em;
            selection-color: {color_active_highlighted_text};
            background: {color_selection};
        }}
        TyreStatusBar QLabel {{
            font-weight:bold;
        }}
        """)
