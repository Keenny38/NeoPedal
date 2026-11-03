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

"""Audit before 0.29.0 (2026-11-02), app shell: rail Tab stop kept with the title bar drawn by the app (B6),
keyboard focus ring of the option lists (B9), square shell popups where the system keeps square windows (L1), Alt
released after a caption drag (L2), Home page items placed by their layout (L3)"""

from __future__ import annotations

import os

import pytest
import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPoint, Qt
from PySide6.QtGui import QKeyEvent, QMoveEvent
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from tests.test_audit_0_29_0 import title_bar_on  # noqa: F401  (fixture)
from tests.test_audit_g_qml_keys import component, settings_window  # noqa: F401  (fixtures)
from tests.test_ui_audit_2026_10_29_shell import flush, window  # noqa: F401  (fixtures)


def wait(seconds: float):
    import time

    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QCoreApplication.processEvents()


# --- B6: NavButton of the title bar never makes the rail entries click-only
def test_title_bar_button_keeps_rail_tab_stop(title_bar_on, window):  # noqa: F811
    from neopedal.ui.app_tab_view import NavButton, rail_buttons

    window.show()
    flush()
    assert window.title_bar is not None
    menu = window.title_bar.button_menu
    rail = window.centralWidget()._rail
    entries = rail.findChildren(NavButton)
    assert entries and menu not in entries
    assert rail_buttons(menu) == [menu] and rail_buttons(menu, shown_only=False) == [menu]
    menu.setFocus(Qt.FocusReason.TabFocusReason)
    flush()
    assert menu.hasFocus()
    tab_stops = [item for item in entries if item.focusPolicy() == Qt.FocusPolicy.StrongFocus]
    assert len(tab_stops) == 1  # rail still one Tab stop
    QTest.keyClick(menu, Qt.Key.Key_Down)  # arrows of a title bar button stay out of the rail
    flush()
    assert not any(item.hasFocus() for item in entries)
    # Rail entries: one Tab stop & arrow keys among them, as before
    first = next(item for item in entries if item.isVisible() and item.isEnabled())
    assert rail_buttons(first) and all(item in entries for item in rail_buttons(first))


# --- B9: focus ring of the option lists shown on Tab / Backtab focus only (ListView has no focusReason)
def previous_in_focus_chain(target: QQuickItem) -> QQuickItem:
    """Item that Tab leaves for target (Tab chain of the page walked forward)"""
    item = target.nextItemInFocusChain(True)
    for _ in range(2000):
        following = item.nextItemInFocusChain(True)
        if following is target:
            return item
        item = following
    raise AssertionError("target not in Tab chain")


def check_list_focus_ring(view, ring_name: str):
    root = view.rootObject()
    ring = root.findChild(QQuickItem, ring_name)
    assert ring is not None, ring_name
    target = ring.parentItem()
    assert target.property("keyboardFocus") is False
    before = previous_in_focus_chain(target)
    before.forceActiveFocus(Qt.FocusReason.TabFocusReason)
    wait(0.05)
    QTest.keyClick(view, Qt.Key.Key_Tab)
    wait(0.05)
    assert target.hasActiveFocus()  # list, or its current row (focus scope)
    assert ring.isVisible()
    # Focus elsewhere: ring hidden; focus given back by the page (menu closed, Esc in a field): no ring
    before.forceActiveFocus(Qt.FocusReason.MouseFocusReason)
    wait(0.05)
    assert not ring.isVisible() and target.property("keyboardFocus") is False
    target.forceActiveFocus(Qt.FocusReason.OtherFocusReason)
    wait(0.05)
    assert target.hasActiveFocus() and not ring.isVisible()
    QTest.keyClick(view, Qt.Key.Key_Down)  # scrolls, no ring: focus not given by Tab
    wait(0.05)
    assert not ring.isVisible()


@pytest.fixture
def options_page(ui_env):
    from neopedal.ui.overlay_options import OverlayOptions
    from tests.test_ui_audit_2026_10_29_overlays import OptionsControl, settle

    page = OverlayOptions(None, OptionsControl())
    page.resize(1500, 800)
    page.show()
    page.activateWindow()
    settle()
    yield page
    if shiboken6.isValid(page):
        page.backend.discard()
        page.close()  # deleted once closed
    flush()


def test_overlay_options_list_focus_ring_on_tab(options_page):
    view = options_page.view
    assert not view.errors(), [error.toString() for error in view.errors()]
    view.setFocus()
    check_list_focus_ring(view, "optionsFocusRing")


def test_settings_list_focus_ring_on_tab(settings_window):  # noqa: F811
    from neopedal.ui.menu import open_config_application

    page = open_config_application(settings_window)
    wait(0.5)
    page.view.setFocus()
    check_list_focus_ring(page.view, "settingsFocusRing")


# --- L1: shell popups square when the system keeps a square window (Windows 10)
@pytest.mark.parametrize("rounded", [False, True])
def test_shell_popup_corners_follow_window_corners(window, monkeypatch, rounded):  # noqa: F811
    from neopedal.ui.command_palette import CommandPalette
    from neopedal.ui.quick import shell_popup
    from neopedal.ui.quick.shell_popup import ShellBackend

    assert ShellBackend().property("roundedCorners") is False  # square until the system rounds the window
    monkeypatch.setattr(shell_popup, "round_window_corners", lambda widget: rounded)
    window.show()
    palette = CommandPalette(window)
    flush()
    root = palette.view.rootObject()
    theme = palette.view.rootContext().contextProperty("theme")
    assert palette.backend.property("roundedCorners") is rounded
    assert root.property("radius") == (theme.property("radiusLg") if rounded else 0)
    palette.close()
    flush()


def test_shell_popup_pages_radius_follows_backend():
    from neopedal.ui.quick import QML_FOLDER

    for name in ("CommandPalette", "Shortcuts", "NotificationCenter"):
        with open(os.path.join(QML_FOLDER, "shell", f"{name}.qml"), encoding="utf-8") as file:
            assert "radius: theme.radiusLg * (backend.roundedCorners ? 1 : 0)" in file.read(), name


# --- L2: Alt pressed, window dragged by its caption, Alt released: no menus
def alt_event(kind: QEvent.Type) -> QKeyEvent:
    return QKeyEvent(kind, Qt.Key.Key_Alt, Qt.KeyboardModifier.NoModifier)


@pytest.mark.parametrize("between", [None, QEvent.Type.Move, QEvent.Type.NonClientAreaMouseButtonPress])
def test_alt_released_after_caption_drag_opens_nothing(ui_env, between):
    from PySide6.QtGui import QMouseEvent

    from neopedal.ui.title_bar import AltMenuKey

    opened = []
    owner = QObject()
    watcher = AltMenuKey(lambda: opened.append(True), owner)
    watcher.eventFilter(owner, alt_event(QEvent.Type.KeyPress))
    if between == QEvent.Type.Move:
        watcher.eventFilter(owner, QMoveEvent(QPoint(10, 10), QPoint(0, 0)))
    elif between is not None:
        point = QPoint(5, 5)
        watcher.eventFilter(owner, QMouseEvent(
            between, point, point, point, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.AltModifier))
    watcher.eventFilter(owner, alt_event(QEvent.Type.KeyRelease))
    wait(0.02)
    assert opened == ([] if between else [True])
    owner.deleteLater()
    flush()


# --- L3: Home game card status dot sized by its layout (no width set on a layout item), same place & size
DOT_ROW = """
Item {
    width: 400; height: 60
    RowLayout {
        objectName: "row"
        width: parent.width
        spacing: theme.space3
        TpPulseDot {
            objectName: "dot"
            %s
            Layout.alignment: Qt.AlignVCenter
        }
        Text { Layout.fillWidth: true; text: "Spa - Race"; font.pointSize: theme.fontSubtitle }
    }
}"""


def test_home_status_dot_geometry_kept(component):  # noqa: F811
    def geometry(sizing: str) -> tuple:
        view = component("import QtQuick.Layouts\n" + DOT_ROW % sizing)
        dot = view.rootObject().findChild(QQuickItem, "dot")
        return dot.x(), dot.y(), dot.width(), dot.height()

    before = geometry("width: Math.round(theme.em * 0.6)")
    after = geometry("Layout.preferredWidth: Math.round(theme.em * 0.6); Layout.preferredHeight: Layout.preferredWidth")
    assert after == before and after[2] == after[3] > 0


def test_home_layout_items_not_placed_by_hand():
    from neopedal.ui.quick import QML_FOLDER

    with open(os.path.join(QML_FOLDER, "home", "Home.qml"), encoding="utf-8") as file:
        text = file.read()
    assert "TpPulseDot {\n                            width:" not in text
    assert "Layout.preferredWidth: Math.round(theme.em * 0.6)" in text
