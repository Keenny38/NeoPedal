"""UI/UX audit 2026-11-01, lot 3 (shell on the tokens): rail & menus drawn with the tokens of QML pages (one source,
ui/tokens.py), one em for widgets & QML, rail as one Tab stop with arrow keys and switch state not told by color
alone, shell popups rounded with an entry animation, small buttons with a 24 px click area"""

import os

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGridLayout, QWidget

from tests.test_audit_g_qml_keys import component  # noqa: F401  (fixture)

PALETTES = ("Modern Dark", "Modern White", "Legacy Grey", "Legacy Light")
QML = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "neopedal", "ui", "qml")


def flush():
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QCoreApplication.processEvents()


@pytest.fixture
def themed(ui_env):
    from neopedal.ui import set_style_palette

    yield set_style_palette
    set_style_palette("Modern Dark")


# 1. One source of tokens: shell colors equal the Theme ones in every theme
@pytest.mark.parametrize("name", PALETTES)
def test_shell_tokens_same_as_theme(themed, name):
    from neopedal.ui import legacy_style, tokens
    from neopedal.ui.quick import Theme

    themed(name)
    theme = Theme(None)
    palette = QApplication.palette()
    legacy = legacy_style()
    assert tokens.surface_card(palette) == theme.property("surfaceCard")
    assert tokens.surface_flyout(palette) == theme.property("surfaceFlyout")
    assert tokens.stroke_subtle(palette, legacy) == theme.property("strokeSubtle")
    assert tokens.hover_fill(palette) == theme.property("hover")
    for hovered in (False, True):
        assert tokens.selected_fill(palette, hovered) == theme.rowColor(hovered, True)
    em = theme.property("em")
    assert tokens.radius_px("radiusLg", em, legacy) == pytest.approx(theme.property("radiusLg"))
    assert theme.property("minTarget") >= 24 * em / 13.33 - 0.01  # 24 px at 100 % scale
    theme.deleteLater()


def test_quick_reads_tokens_from_one_source():
    from neopedal.ui import quick, tokens

    for name in ("RADIUS_SCALE", "SIZE_SCALE", "MOTION", "TINT_LEVELS", "TINT_SELECTED_LIGHT", "SURFACE_LIFT",
                 "LEGACY_RADIUS", "blended", "luminance"):
        assert getattr(quick, name) is getattr(tokens, name), name


@pytest.mark.parametrize("name", ("Modern Dark", "Legacy Light"))
def test_menus_and_rail_style_from_tokens(themed, name):
    from neopedal.ui import UIScaler, legacy_style, set_style_window, tokens

    themed(name)
    sheet = set_style_window(10)
    palette = QApplication.palette()
    assert f"background:{tokens.surface_flyout(palette).name()}" in sheet.replace(" ", "")
    hover = tokens.hover_fill(palette).name()
    selected = sheet.replace(" ", "").split("QMenu::item:selected{", 1)[1].split("}", 1)[0]
    assert f"background:{hover}" in selected and palette.highlight().color().name() not in selected
    radius = round(tokens.radius_px("radiusLg", UIScaler.FONT_PIXEL_SCALED, legacy_style()))
    assert f"border-radius:{radius}px" in sheet.replace(" ", "")


# 2. Rail: one em, one Tab stop, arrow keys, switch state drawn
def make_rail(count: int = 3, compact: bool = False):
    from neopedal.ui.app_tab_view import NavButton

    rail = QWidget()
    rail.setObjectName("navRail")
    layout = QGridLayout(rail)
    buttons = [NavButton(f"Entry {index}", "", chr(65 + index), "", rail, compact=compact) for index in range(count)]
    for index, button in enumerate(buttons):
        layout.addWidget(button, index, 0)
    return rail, buttons


def test_rail_sizes_in_em(ui_env):
    from neopedal.ui import UIScaler
    from neopedal.ui.app_tab_view import NavButton

    em = UIScaler.FONT_PIXEL_SCALED
    assert NavButton("Home", "", "H", "", compact=True).sizeHint().width() == round(em * 2.95)
    assert NavButton("Home", "", "H", "").sizeHint().height() == round(em * 4.55)
    flush()


def test_rail_one_tab_stop_and_arrow_keys(ui_env):
    from PySide6.QtGui import QFocusEvent

    from neopedal.ui.app_tab_view import NavButton

    rail, buttons = make_rail()
    try:
        rail.show()
        QCoreApplication.processEvents()
        NavButton.set_tab_stop(buttons[1])
        policies = [button.focusPolicy() for button in buttons]
        assert policies == [Qt.FocusPolicy.ClickFocus, Qt.FocusPolicy.StrongFocus, Qt.FocusPolicy.ClickFocus]
        # Entry focused (click or arrow key): the Tab stop now (focus events sent: offscreen windows never activate)
        QApplication.sendEvent(buttons[0], QFocusEvent(QEvent.Type.FocusIn, Qt.FocusReason.OtherFocusReason))
        assert [button.focusPolicy() == Qt.FocusPolicy.StrongFocus for button in buttons] == [True, False, False]
        moved: list[int] = []
        for index, button in enumerate(buttons):
            button.setFocus = lambda *args, number=index: moved.append(number)  # type: ignore[method-assign]
        for start, key in ((0, Qt.Key.Key_Down), (0, Qt.Key.Key_End), (2, Qt.Key.Key_Down), (2, Qt.Key.Key_Home),
                           (1, Qt.Key.Key_Up), (1, Qt.Key.Key_Right)):
            QTest.keyClick(buttons[start], key)
        assert moved == [1, 2, 2, 0, 0, 2]  # last stays last, first stays first
    finally:
        rail.close()
        rail.deleteLater()
        flush()


def test_rail_switch_on_drawn_with_a_bar(ui_env):
    """A switch on (Lock, Auto Hide, VR) is told by a bar under its icon, not by its fill color alone"""
    _rail, buttons = make_rail(1, compact=True)
    button = buttons[0]
    button.setCheckable(True)
    button.resize(button.sizeHint())

    def bottom_band(checked: bool) -> list[int]:
        button.setChecked(checked)
        image = QImage(button.size(), QImage.Format.Format_ARGB32)
        image.fill(QColor("#101010"))
        painter = QPainter(image)
        button.render(painter, QPoint(0, 0))
        painter.end()
        y = round(button.height() * 0.85)
        return [image.pixel(x, y) for x in range(button.width())]

    off, on = bottom_band(False), bottom_band(True)
    accent = QApplication.palette().highlight().color().rgb()
    assert accent in on and accent not in off
    _rail.deleteLater()
    flush()


# 3. Shell popups: rounded, entry animation, sizes in em
def test_shell_popups_rounded_and_animated():
    for name in ("CommandPalette", "Shortcuts", "NotificationCenter"):
        with open(os.path.join(QML, "shell", f"{name}.qml"), encoding="utf-8") as file:
            text = file.read()
        assert "radius: theme.radiusLg" in text and "TpEnter { target: popupContent }" in text, name


def test_popup_size_and_corners(ui_env):
    from neopedal.ui import UIScaler
    from neopedal.ui.quick.shell_popup import popup_size, round_window_corners

    window = QWidget()
    window.resize(4000, 3000)
    size = popup_size(window, 10, 5)
    assert (size.width(), size.height()) == (round(10 * UIScaler.FONT_PIXEL_SCALED), round(5 * UIScaler.FONT_PIXEL_SCALED))
    window.show()
    assert round_window_corners(window) in (True, False)  # never raises (Windows 10 & offscreen refuse it)
    window.close()
    window.deleteLater()
    flush()


# 4. Small buttons: click area of 24 px at least
def test_small_button_click_area(component):  # noqa: F811
    view = component("""
Item {
    width: 200; height: 100
    property int clicks: 0
    TpButton {
        objectName: "small"
        x: 80; y: 40
        size: "xs"
        glyph: ""
        fallback: "x"
        onClicked: parent.clicks += 1
    }
}""")
    root = view.rootObject()
    small = root.findChild(QObject, "small")
    theme_min = view.rootContext().contextProperty("theme").property("minTarget")
    background = small.property("background")
    assert background.property("height") < theme_min  # drawn size kept
    assert small.property("height") >= theme_min and small.property("width") >= theme_min  # click area grown
    # Just outside the drawn button, inside the 24 px area around it
    point = small.mapToScene(QPointF(small.property("width") / 2, background.property("y") - 1)).toPoint()
    QTest.mouseClick(view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
    QCoreApplication.processEvents()
    assert root.property("clicks") == 1
    far = small.mapToScene(QPointF(small.property("width") / 2, -2)).toPoint()
    QTest.mouseClick(view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, far)
    QCoreApplication.processEvents()
    assert root.property("clicks") == 1  # beyond the area: not the button
