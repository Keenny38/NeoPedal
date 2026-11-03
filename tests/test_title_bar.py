"""Title bar drawn by the app (Windows): hit test areas, title, Back & Forward, Maximize clicks"""

import ctypes
import sys
from ctypes import wintypes

import pytest
from PySide6.QtCore import QEvent, QPoint
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton

from neopedal.ui import title_bar
from neopedal.ui.title_bar import (
    HTCAPTION,
    HTCLIENT,
    HTMAXBUTTON,
    MAXIMIZE,
    RESTORE,
    WM_NCLBUTTONDBLCLK,
    WM_NCLBUTTONDOWN,
    WM_NCLBUTTONUP,
    TitleBar,
    app_title_bar_supported,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def bar(qapp):
    window = QMainWindow()
    title = TitleBar(window)
    window.setMenuWidget(title)
    title.menu_bar.addMenu("Overlay")
    title.menu_bar.addMenu("Help")
    window.resize(900, 400)
    window.show()
    qapp.processEvents()
    yield title
    window.close()
    window.deleteLater()
    qapp.processEvents()


def center(widget, bar):
    return widget.mapTo(bar, widget.rect().center())


def test_not_used_off_windows_platform(qapp):
    assert not app_title_bar_supported()  # tests run offscreen: native menu bar kept


def test_python_window_messages_only_with_app_title_bar(monkeypatch):
    """A Python nativeEvent is called for every window message (each waits for the GIL while another thread runs
    Python code): only the main window with the app title bar has one, and its user32 calls keep the GIL"""
    from neopedal.ui import app

    assert "nativeEvent" not in vars(app.AppWindow) and "nativeEvent" in vars(app.FramedAppWindow)
    monkeypatch.setattr(app, "AppWindow", lambda: "plain")
    monkeypatch.setattr(app, "FramedAppWindow", lambda: "framed")
    for used, window in ((True, "framed"), (False, "plain")):
        monkeypatch.setattr(app, "use_app_title_bar", lambda used=used: used)
        assert app.main_window() == window
    if sys.platform == "win32":
        from _ctypes import FUNCFLAG_PYTHONAPI

        assert type(title_bar.load_user32(keep_gil=True))._func_flags_ & FUNCFLAG_PYTHONAPI
        assert not type(title_bar.load_user32())._func_flags_ & FUNCFLAG_PYTHONAPI  # SetWindowPos sends messages


def test_hit_test_areas(bar):
    assert not bar.menu_bar.isVisible()  # menus in the menu button
    assert bar.hit_test(center(bar.button_menu, bar)) == HTCLIENT
    assert bar.hit_test(QPoint(bar.free_area().center().x(), 5)) == HTCAPTION  # drag, double click
    assert bar.hit_test(center(bar.button_maximize, bar)) == HTMAXBUTTON  # Snap Layouts flyout
    assert bar.hit_test(center(bar.button_minimize, bar)) == HTCLIENT
    assert bar.hit_test(center(bar.button_close, bar)) == HTCLIENT


def test_menu_button_opens_window_menus(bar, qapp):
    from PySide6.QtWidgets import QMenu

    bar.show_menu()
    qapp.processEvents()
    menu = next(widget for widget in qapp.topLevelWidgets() if isinstance(widget, QMenu) and widget.isVisible())
    assert [action.text() for action in menu.actions()] == ["Overlay", "Help"]  # menus of the menu bar
    assert menu.actions()[0].menu() is bar.menu_bar.actions()[0].menu()  # shared, not copied
    assert menu.geometry().top() >= bar.button_menu.mapToGlobal(bar.button_menu.rect().bottomLeft()).y()
    menu.close()
    qapp.processEvents()
    assert bar.menu_bar.actions()[0].menu() is not None  # kept by the menu bar once the popup is deleted


def test_maximize_glyph_and_name_follow_window_state(bar, qapp):
    window = bar.window()
    assert bar.button_maximize.glyph in MAXIMIZE and bar.button_maximize.accessibleName() == "Maximize"
    bar.toggle_maximized()
    qapp.processEvents()
    assert window.isMaximized()
    assert bar.button_maximize.glyph in RESTORE and bar.button_maximize.accessibleName() == "Restore"
    bar.toggle_maximized()
    qapp.processEvents()
    assert not window.isMaximized() and bar.button_maximize.glyph in MAXIMIZE


def test_history_buttons_left_of_menus(bar, qapp):
    back, forward = QPushButton("<"), QPushButton(">")
    bar.dock(title_bar.DOCK_HISTORY, (back, forward))
    qapp.processEvents()
    assert back.parent() is bar and forward.parent() is bar
    assert bar.button_menu.geometry().right() < back.geometry().left() < forward.geometry().left()
    assert forward.geometry().right() < bar.label_version.geometry().left() < bar.free_area().left()  # version
    assert bar.hit_test(center(bar.label_version, bar)) == HTCAPTION  # drags the window
    assert bar.hit_test(center(back, bar)) == HTCLIENT
    # View rebuilt (language changed): buttons of the replaced view deleted
    deleted = []
    back.destroyed.connect(lambda: deleted.append("back"))
    bar.dock(title_bar.DOCK_HISTORY, (QPushButton("<"), forward))
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    qapp.processEvents()
    assert deleted == ["back"]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows messages")
def test_maximize_clicks_handled_only_while_hovered(bar, qapp, monkeypatch):
    handler = title_bar.FrameHandler(bar.window(), bar)
    handler._hwnd = 1234  # window handle of attach(): Qt created another one since, messages carry the current one
    hwnd_now = int(bar.window().winId())
    toggled = []
    monkeypatch.setattr(bar, "toggle_maximized", lambda: toggled.append(True))
    filters = []
    monkeypatch.setattr(QApplication, "installNativeEventFilter", lambda self, f: filters.append(f))
    monkeypatch.setattr(QApplication, "removeNativeEventFilter", lambda self, f: filters.remove(f))

    def send(message, hit=HTMAXBUTTON, hwnd=hwnd_now):
        msg = wintypes.MSG(hwnd, message, hit, 0)
        return handler.handle_click(ctypes.addressof(msg))

    handler.hover_maximize(True)
    assert filters == [handler._filter] and bar.button_maximize.nc_hovered
    handler.hover_maximize(True)  # hit tests on each mouse move: installed once
    assert len(filters) == 1
    assert not send(WM_NCLBUTTONDOWN, hwnd=99)  # another window of the app
    assert not send(WM_NCLBUTTONDOWN, hit=HTCAPTION)  # left to Windows (drag)
    assert send(WM_NCLBUTTONDOWN) and bar.button_maximize.nc_pressed and not toggled
    assert send(WM_NCLBUTTONUP) and toggled == [True] and not bar.button_maximize.nc_pressed
    assert send(WM_NCLBUTTONUP) and toggled == [True]  # release without press: nothing
    assert send(WM_NCLBUTTONDBLCLK) and send(WM_NCLBUTTONUP) and len(toggled) == 2
    # Mouse off the button: hover ends, filter removed (no message of the app filtered any more)
    monkeypatch.setattr(title_bar.QCursor, "pos", staticmethod(lambda: QPoint(-10000, -10000)))
    handler.check_maximize_left()
    assert filters == [] and not bar.button_maximize.nc_hovered and not handler._leave_timer.isActive()
    handler.hover_maximize(True)
    bar.deleteLater()  # window closed while hovered: filter never left installed
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    assert filters == []


def test_page_frame_corner_over_pages(qapp):
    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtWidgets import QStackedWidget, QWidget

    from neopedal.ui.title_bar import PageFrame

    host = QWidget()
    stack = QStackedWidget()
    frame = PageFrame(host, stack)
    page = QWidget()
    page.setAutoFillBackground(True)
    palette = page.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#ff0000"))
    page.setPalette(palette)
    stack.addWidget(page)  # page added after the corner: still under it
    frame.resize(200, 120)
    image = frame.grab().toImage()
    window = frame.palette().color(QPalette.ColorGroup.Active, QPalette.ColorRole.Window)
    line = frame.palette().color(QPalette.ColorGroup.Active, QPalette.ColorRole.Midlight)
    radius = frame.corners[0].radius
    bottom = frame.height() - 1
    assert image.pixel(1, 1) == window.rgb() and image.pixel(1, bottom - 1) == window.rgb()  # outside corners
    assert image.pixel(radius + 4, 0) == line.rgb() and image.pixel(0, radius + 4) == line.rgb()
    assert image.pixel(radius + 4, bottom) == line.rgb() and image.pixel(0, bottom - radius - 4) == line.rgb()
    assert image.pixel(radius + 4, radius + 4) == QColor("#ff0000").rgb()  # page inside
    assert image.pixel(radius + 4, bottom - radius - 4) == QColor("#ff0000").rgb()
    host.deleteLater()


def test_status_chips_left_of_caption_buttons(bar, qapp):
    from PySide6.QtWidgets import QHBoxLayout, QWidget

    chips = QWidget()  # chips container, as NotifyBar: its free part drags the window
    layout = QHBoxLayout(chips)
    layout.setContentsMargins(0, 0, 0, 0)
    chip = QPushButton("Preset Locked")
    layout.addWidget(chip)
    layout.addSpacing(30)
    bar.dock(title_bar.DOCK_STATUS, (chips,))
    qapp.processEvents()
    assert chips.geometry().right() < bar.button_minimize.geometry().left()
    assert bar.free_area().right() < chips.geometry().left()
    assert bar.hit_test(center(chip, bar)) == HTCLIENT
    assert bar.hit_test(QPoint(chips.geometry().right() - 5, bar.height() // 2)) == HTCAPTION


def test_saving_state_shown_only_when_slow_and_moves_nothing(bar, qapp, monkeypatch):
    chips = QPushButton("Global Hotkey Enabled")
    bar.dock(title_bar.DOCK_STATUS, (chips,))
    qapp.processEvents()
    before = chips.geometry()
    bar.set_saving(True)
    bar.set_saving(False)  # usual save: a few ms, never drawn
    assert not bar._saving_shown and not bar._saving_timer.isActive()
    bar.set_saving(True)
    bar._saving_timer.timeout.emit()  # still saving after a while: drawn
    assert bar._saving_shown
    qapp.processEvents()
    assert chips.geometry() == before  # drawn in the free area: nothing moves
    bar.set_saving(False)
    assert not bar._saving_shown


def test_app_tools_right_of_status_chips(bar, qapp):
    tools = (QPushButton("Search"), QPushButton("Bell"))
    bar.dock(title_bar.DOCK_TOOLS, tools)
    chips = QPushButton("Preset Locked")
    bar.dock(title_bar.DOCK_STATUS, (chips,))  # view rebuilt after: chips still left of the tools
    qapp.processEvents()
    assert bar.free_area().right() < chips.geometry().left() < tools[0].geometry().left()
    assert tools[0].geometry().right() < tools[1].geometry().left() < bar.button_minimize.geometry().left()
    assert all(bar.hit_test(center(tool, bar)) == HTCLIENT for tool in tools)


def test_ampersand_shown_in_menus_and_palette(qapp):
    from neopedal.ui.command_palette import plain_menu_text
    from neopedal.ui.menu import menu_text

    assert menu_text("Results & Replays") == "Results && Replays"  # not "Results _Replays" (mnemonic)
    assert plain_menu_text(menu_text("Results & Replays")) == "Results & Replays"  # palette entry
    assert plain_menu_text("&Overlay") == "Overlay"


def test_bar_shows_page_name_centered_even_with_wide_right_side(bar, qapp):
    from PySide6.QtGui import QPalette
    from PySide6.QtWidgets import QHBoxLayout, QWidget

    from neopedal.const_app import APP_NAME, VERSION
    from neopedal.ui.title_bar import bar_title

    window = bar.window()
    window.setWindowTitle(f"Pacenotes[*] - {APP_NAME} v{VERSION}")
    assert bar_title(window) == "Pacenotes"
    window.setWindowModified(True)
    assert bar_title(window) == "Pacenotes*"
    window.setWindowModified(False)
    window.setWindowTitle(f"{APP_NAME} v{VERSION}")
    assert bar_title(window) == APP_NAME
    # Chips & tools make the right side wider than the left one: page name still on the middle of the bar
    tools = tuple(QPushButton(str(index)) for index in range(4))
    for tool in tools:
        tool.setFixedWidth(35)  # icon buttons
    bar.dock(title_bar.DOCK_TOOLS, tools)
    chips = QWidget()  # as NotifyBar: chips then a stretch
    layout = QHBoxLayout(chips)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(QPushButton("Global Hotkey Enabled"))
    layout.addStretch(1)
    bar.dock(title_bar.DOCK_STATUS, (chips,))
    window.resize(1100, 400)
    window.setWindowTitle(f"Broadcast Director - {APP_NAME} v{VERSION}")
    qapp.processEvents()
    background = bar.palette().color(QPalette.ColorGroup.Active, QPalette.ColorRole.Window).rgb()
    image = bar.grab().toImage()
    area = bar.free_area()
    assert area.center().x() < bar.width() // 2  # free area off center
    columns = [x for x in range(area.left(), area.right())
               if any(image.pixel(x, y) != background for y in range(bar.height()))]
    assert abs((columns[0] + columns[-1]) / 2 - bar.width() / 2) < 4
    assert chips.geometry().right() < tools[0].geometry().left() <= chips.geometry().right() + 8  # never grown


def test_page_headers_told_name_is_in_the_bar(qapp, monkeypatch):
    from neopedal.ui.quick import Theme
    from neopedal.ui.title_bar import PageTitleState, page_title_in_bar

    assert not page_title_in_bar()  # native title bar (tests run offscreen): page headers show the name
    theme = Theme()
    assert theme.property("pageTitleInBar") is False
    monkeypatch.setattr(PageTitleState, "shown", True)  # set by the main window with the title bar drawn by the app
    assert page_title_in_bar() and theme.property("pageTitleInBar") is True


def test_page_name_drawn_again_when_a_chip_shows(bar, qapp, monkeypatch):
    chip = QPushButton("Broadcast Director On")
    chip.hide()
    bar.dock(title_bar.DOCK_STATUS, (chip,))
    qapp.processEvents()
    updates = []
    monkeypatch.setattr(bar, "update", lambda *args: updates.append(args))
    chip.show()  # free area shrinks: page name placed again
    qapp.processEvents()
    assert updates


def test_alt_alone_opens_window_menus(qapp):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QKeyEvent, QMouseEvent

    from neopedal.ui.title_bar import AltMenuKey

    opened = []
    alt_key = AltMenuKey(lambda: opened.append(True), None)
    alt, none, ctrl_alt = (Qt.KeyboardModifier.AltModifier, Qt.KeyboardModifier.NoModifier,
                           Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ControlModifier)

    def key(kind, code, modifiers, repeat=False):
        alt_key.eventFilter(None, QKeyEvent(kind, code, modifiers, "", repeat))

    def run(*steps):
        opened.clear()
        for step in steps:
            step()
        qapp.processEvents()
        return bool(opened)

    press, release = QEvent.Type.KeyPress, QEvent.Type.KeyRelease
    alt_down = lambda: key(press, Qt.Key.Key_Alt, alt)
    alt_up = lambda: key(release, Qt.Key.Key_Alt, none)
    assert run(alt_down, alt_up)
    assert run(alt_down, lambda: key(press, Qt.Key.Key_Alt, alt, True), alt_up)  # Alt held a while: still alone
    assert not run(alt_down, lambda: key(press, Qt.Key.Key_Left, alt), alt_up)  # Alt+Left: Back
    assert not run(lambda: key(press, Qt.Key.Key_Alt, ctrl_alt), alt_up)  # AltGr (French "@", "€")
    click = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(1, 1), QPointF(1, 1), Qt.MouseButton.LeftButton,
                        Qt.MouseButton.LeftButton, alt)
    assert not run(alt_down, lambda: alt_key.eventFilter(None, click), alt_up)  # Alt+click
    assert not run(alt_down, lambda: alt_key.eventFilter(None, QEvent(QEvent.Type.WindowDeactivate)), alt_up)  # Alt+Tab


def test_keyboard_menu_selects_first_menu_and_caption_tooltips(bar, qapp):
    from PySide6.QtWidgets import QMenu

    assert bar.button_minimize.toolTip() == "Minimize" and bar.button_close.toolTip() == "Close"
    bar.show_menu(keyboard=True)
    qapp.processEvents()
    menu = next(widget for widget in qapp.topLevelWidgets() if isinstance(widget, QMenu) and widget.isVisible())
    assert menu.activeAction() is menu.actions()[0]  # arrows & Enter go on from there
    menu.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DWM")
def test_dialog_captions_in_window_colors(qapp, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPalette
    from PySide6.QtWidgets import QDialog, QWidget

    from neopedal.ui.title_bar import DWMWA_CAPTION_COLOR, DWMWA_TEXT_COLOR, CaptionColors, colorref

    main = QWidget()
    colors = CaptionColors(main)
    calls = []
    monkeypatch.setattr(colors, "_set_attribute", lambda hwnd, attribute, value, size: calls.append(
        (attribute, ctypes.cast(value, ctypes.POINTER(wintypes.DWORD)).contents.value)))
    dialog = QDialog()
    dialog.show()
    colors.apply(dialog.windowHandle())
    palette = QApplication.palette()
    assert calls == [
        (DWMWA_CAPTION_COLOR, colorref(palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Window))),
        (DWMWA_TEXT_COLOR, colorref(palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.WindowText))),
    ]
    calls.clear()
    main.show()
    colors.apply(main.windowHandle())  # main window: no caption (title bar drawn by the app)
    frameless = QWidget(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)  # overlays, edit toolbar
    frameless.show()
    colors.apply(frameless.windowHandle())
    colors.apply(None)
    assert calls == []
    assert colorref(QColor(0x12, 0x34, 0x56)) == 0x563412
    for widget in (dialog, main, frameless):
        widget.close()
