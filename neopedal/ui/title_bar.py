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
Title bar of main window drawn by the app (Windows): window colors, menus in the title bar, flat caption buttons

Only the caption is removed from the native frame (WM_NCCALCSIZE), the frame itself is kept: shadow, rounded
corners (Windows 11), resize borders, snap (drag to screen edges, Win+arrows, Snap Layouts flyout over Maximize),
minimize & maximize animations and system menu (Alt+Space, right click on the title bar) stay the native ones.
"""

from __future__ import annotations

import contextlib
import ctypes
import sys
from _ctypes import FUNCFLAG_PYTHONAPI
from collections.abc import Callable
from ctypes import wintypes

import shiboken6
from PySide6.QtCore import (
    QAbstractNativeEventFilter,
    QCoreApplication,
    QEvent,
    QObject,
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QKeyEvent,
    QPainter,
    QPainterPath,
    QPalette,
    QWindow,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QSizePolicy,
    QSpacerItem,
    QWidget,
)

from ..const_app import APP_NAME, VERSION
from ..i18n import tr
from . import UIScaler
from .ordered_picker import icon_font_family

TITLE_BAR_HEIGHT = 38  # UIScaler pixels
CAPTION_BUTTON_WIDTH = 46  # UIScaler pixels, as Windows 11 caption buttons
CAPTION_GLYPH_SIZE = 10  # UIScaler pixels
ICON_SIZE = 16  # UIScaler pixels: app icon at the left of the title bar
ICON_LEFT = 10  # UIScaler pixels: space before it
PAGE_CORNER_RADIUS = 8  # UIScaler pixels: top left corner of the page area, see PageFrame
# Title bar slots of window widgets, see TitleBar.dock
DOCK_HISTORY = "history"
DOCK_STATUS = "status"
DOCK_TOOLS = "tools"
VERSION_FONT_SCALE = 0.9  # app version after Back & Forward
SAVING_SHOWN_AFTER_MS = 400  # saving state drawn only for slow saves (most take a few ms: no flash)
CLOSE_HOVER = QColor(0xC4, 0x2B, 0x1C)  # Windows 11 close button
CLOSE_PRESSED = QColor(0xC4, 0x2B, 0x1C, 0xE6)
# Caption buttons: Segoe Fluent Icons / MDL2 Assets glyph, letter without icon font
MINIMIZE = ("\ue921", "\u2013")
MAXIMIZE = ("\ue922", "\u25a1")
RESTORE = ("\ue923", "\u2750")
CLOSE = ("\ue8bb", "\u2715")
MENU = ("\ue700", "\u2261")  # global navigation (three lines)

# Windows 10 (build below 22000): no frame line drawn by the system above the client area, see TitleBar.paintEvent
WINDOWS_10_FRAME = sys.platform == "win32" and sys.getwindowsversion().build < 22000

# Caption colors of other windows (dwmapi.h, Windows 11), see CaptionColors
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36

# Window messages & hit test values (winuser.h)
WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
WM_NCLBUTTONDOWN = 0x00A1
WM_NCLBUTTONUP = 0x00A2
WM_NCLBUTTONDBLCLK = 0x00A3
MAXIMIZE_MESSAGES = frozenset((WM_NCLBUTTONDOWN, WM_NCLBUTTONUP, WM_NCLBUTTONDBLCLK))
LEAVE_CHECK_MS = 50  # Maximize hovered: mouse left it checked this often
HTCLIENT = 1
HTCAPTION = 2
HTMAXBUTTON = 9
HTTOP = 12
SM_CYSIZEFRAME = 33
SM_CXPADDEDBORDER = 92
# SetWindowPos: frame changed (caption removed), nothing else
SWP_FRAME_CHANGED = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020  # NOSIZE NOMOVE NOZORDER NOACTIVATE FRAMECHANGED
# Offset of message id in a MSG structure (after its HWND)
MESSAGE_OFFSET = ctypes.sizeof(ctypes.c_void_p)


def app_title_bar_supported() -> bool:
    """Title bar drawn by the app possible: Windows platform (native frame kept, see FrameHandler)"""
    return sys.platform == "win32" and QGuiApplication.platformName() == "windows"


class PageTitleState:
    """Shown page name in the title bar drawn by the app: page headers leave out the same name (see
    page_title_in_bar)"""

    shown = False


def page_title_in_bar() -> bool:
    """Page name shown in the title bar drawn by the app: not repeated by page headers"""
    return PageTitleState.shown


def window_handle(widget: QWidget) -> QWindow | None:
    """Native window of a widget. PySide may give the window as a wrapper of another type left at its address (a
    deleted QWidgetItem, seen once in 3 starts): that wrapper is dropped and the window wrapped again."""
    handle = widget.windowHandle()
    if handle is not None and not isinstance(handle, QWindow):
        shiboken6.invalidate(handle)
        handle = widget.windowHandle()
    return handle if isinstance(handle, QWindow) else None


def title_text(window: QWidget) -> str:
    """Window title as Windows shows it: "[*]" placeholder replaced by "*" while window is modified"""
    return window.windowTitle().replace("[*]", "*" if window.isWindowModified() else "")


def bar_title(window: QWidget) -> str:
    """Name shown in the title bar: shown page (unsaved changes marker included), app name if none. Full window
    title (app version) stays the one of taskbar & Alt+Tab."""
    page, separator, _ = title_text(window).rpartition(f" - {APP_NAME}")
    return page if separator and page else APP_NAME


class CaptionButton(QAbstractButton):
    """Minimize, maximize & close button: flat, full title bar height, red close as Windows 11"""

    def __init__(self, glyphs: tuple[str, str], icon_family: str, close: bool, parent: QWidget):
        super().__init__(parent)
        self.close_button = close
        self.nc_hovered = False  # Maximize: hovered as non-client area (Snap Layouts flyout), see FrameHandler
        self.nc_pressed = False
        self.glyph = ""
        self.icon_font = QFont(icon_family) if icon_family else QFont(self.font())
        self.icon_family = icon_family
        self.set_glyphs(glyphs)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # as native caption buttons: Alt+Space menu by keyboard
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)  # repainted when hovered
        self.icon_font.setPixelSize(UIScaler.pixel(CAPTION_GLYPH_SIZE))

    def set_glyphs(self, glyphs: tuple[str, str]):
        glyph = glyphs[0] if self.icon_family else glyphs[1]
        if glyph != self.glyph:
            self.glyph = glyph
            self.update()

    def set_nc_state(self, hovered: bool, pressed: bool):
        """Hover & press seen by FrameHandler (non-client area)"""
        if (hovered, pressed) != (self.nc_hovered, self.nc_pressed):
            self.nc_hovered = hovered
            self.nc_pressed = pressed
            self.update()

    def sizeHint(self) -> QSize:
        return QSize(UIScaler.pixel(CAPTION_BUTTON_WIDTH), UIScaler.pixel(TITLE_BAR_HEIGHT))

    def paintEvent(self, event):
        painter = QPainter(self)
        palette = self.palette()
        text = palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.WindowText)
        hovered = self.underMouse() or self.nc_hovered
        pressed = self.isDown() or self.nc_pressed
        if self.close_button and (hovered or pressed):
            painter.fillRect(self.rect(), CLOSE_PRESSED if pressed else CLOSE_HOVER)
            color = QColor(Qt.GlobalColor.white)
        else:
            if hovered or pressed:
                fill = QColor(text)
                fill.setAlphaF(0.06 if pressed else 0.1)
                painter.fillRect(self.rect(), fill)
            # Window inactive: muted glyphs, as native caption
            color = text if self.isActiveWindow() or hovered else palette.color(
                QPalette.ColorGroup.Active, QPalette.ColorRole.PlaceholderText)
        painter.setPen(color)
        painter.setFont(self.icon_font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.glyph)


OTHER_MODIFIERS = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.MetaModifier


class AltMenuKey(QObject):
    """Event filter of the main window (QWindow: every key reaches it first): Alt pressed then released with no other
    key nor click in between opens the window menus. AltGr (Ctrl+Alt) and Alt shortcuts (Alt+Tab, Alt+Left) don't."""

    def __init__(self, open_menu: Callable[[], None], parent: QObject):
        super().__init__(parent)
        self._open_menu = open_menu
        self._armed = False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if isinstance(event, QKeyEvent):
            is_alt = event.key() == Qt.Key.Key_Alt
            if event.type() == QEvent.Type.KeyPress:
                if not (is_alt and event.isAutoRepeat()):  # Alt held: still alone
                    # Modifiers of an Alt key event leave Alt out (Qt 6): AltGr comes with Ctrl
                    self._armed = is_alt and not event.modifiers() & OTHER_MODIFIERS
            elif self._armed and is_alt and not event.isAutoRepeat():  # released
                self._armed = False
                QTimer.singleShot(0, self._open_menu)  # after the key event (menu takes the keyboard)
        elif event.type() in (
            QEvent.Type.MouseButtonPress, QEvent.Type.Wheel, QEvent.Type.FocusOut, QEvent.Type.WindowDeactivate,
            # Window dragged by its caption (non-client mouse messages only, no mouse press reaches Qt)
            QEvent.Type.Move, QEvent.Type.NonClientAreaMouseButtonPress,
        ):
            self._armed = False
        return False


class TitleBar(QWidget):
    """Title bar of main window: app icon, menu button (window menus), title, caption buttons (menu widget of the
    window)"""

    def __init__(self, window: QMainWindow):
        super().__init__(window)
        self.setObjectName("titleBar")
        self._window = window
        self.setFixedHeight(UIScaler.pixel(TITLE_BAR_HEIGHT))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(UIScaler.pixel(ICON_LEFT), 0, 0, 0)
        layout.setSpacing(0)
        layout.addSpacing(UIScaler.pixel(ICON_SIZE + 6))  # app icon, drawn
        icon_family = icon_font_family()
        # Window menus (Overlay, API, Settings, Tools, Window, Help) in one menu button, as a modern app: menus kept
        # by a hidden menu bar (AppWindow.menuBar, command palette)
        from .app_tab_view import NavButton

        self.button_menu = NavButton(f"{tr('Menu')} (F10)", MENU[0], MENU[1], icon_family, self, compact=True)
        self.button_menu.setObjectName("titleMenu")
        self.button_menu.setCheckable(False)
        self.button_menu.clicked.connect(self.show_menu)
        layout.addWidget(self.button_menu, 0, Qt.AlignmentFlag.AlignVCenter)
        # App version after Back & Forward, muted (kept on screenshots sent for support)
        self.label_version = QLabel(f"v{VERSION}", self)
        self.label_version.setObjectName("titleVersion")
        self.label_version.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        font = self.label_version.font()
        font.setPointSizeF(font.pointSizeF() * VERSION_FONT_SCALE)
        self.label_version.setFont(font)
        self.label_version.setContentsMargins(UIScaler.pixel(6), 0, 0, 0)
        layout.addWidget(self.label_version, 0, Qt.AlignmentFlag.AlignVCenter)
        self.menu_bar = QMenuBar(self)
        self.menu_bar.setObjectName("titleMenuBar")
        self.menu_bar.hide()
        # Back & Forward of the view inserted after the menu button, status chips & app tools before caption
        # buttons, see dock
        self._layout = layout
        self._docked: dict[str, tuple[QWidget, ...]] = {}
        self._free_space = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout.addItem(self._free_space)  # free area, see free_area
        self._caption_gap = QSpacerItem(UIScaler.pixel(8), 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        layout.addItem(self._caption_gap)
        self.button_minimize = CaptionButton(MINIMIZE, icon_family, False, self)
        self.button_maximize = CaptionButton(MAXIMIZE, icon_family, False, self)
        self.button_close = CaptionButton(CLOSE, icon_family, True, self)
        self.button_minimize.clicked.connect(window.showMinimized)
        self.button_maximize.clicked.connect(self.toggle_maximized)
        self.button_close.clicked.connect(window.close)
        for button in (self.button_minimize, self.button_maximize, self.button_close):
            layout.addWidget(button)
        # Saving state drawn at the right of the free area (nothing moves when shown), see set_saving
        self._saving_shown = False
        self._saving_timer = QTimer(self)
        self._saving_timer.setSingleShot(True)
        self._saving_timer.setInterval(SAVING_SHOWN_AFTER_MS)
        self._saving_timer.timeout.connect(lambda: self.show_saving(True))
        self.retranslate()
        window.installEventFilter(self)

    def set_saving(self, saving: bool):
        """Setting files being saved (app_signal.saving): shown once saving lasts"""
        if saving:
            if not self._saving_shown and not self._saving_timer.isActive():
                self._saving_timer.start()
        else:
            self._saving_timer.stop()
            self.show_saving(False)

    def show_saving(self, shown: bool):
        if shown != self._saving_shown:
            self._saving_shown = shown
            self.update()

    def dock(self, slot: str, widgets: tuple[QWidget, ...]):
        """Widgets of the window shown in the title bar: DOCK_HISTORY left of the menus (Back & Forward),
        DOCK_STATUS then DOCK_TOOLS left of the caption buttons (status chips, app tools). Those docked before in
        the slot (view replaced) are deleted."""
        for widget in self._docked.get(slot, ()):
            self._layout.removeWidget(widget)
            if widget not in widgets:
                widget.deleteLater()
        self._docked[slot] = widgets
        if slot == DOCK_HISTORY:
            index = self._layout.indexOf(self.button_menu) + 1
        else:
            tools = self._docked.get(DOCK_TOOLS, ()) if slot == DOCK_STATUS else ()
            index = self._layout.indexOf(tools[0]) if tools else self._layout.indexOf(self._caption_gap)
        for offset, widget in enumerate(widgets):
            if slot != DOCK_HISTORY:  # never grown (chips container): free middle area kept for the title
                policy = widget.sizePolicy()
                policy.setHorizontalPolicy(QSizePolicy.Policy.Maximum)
                widget.setSizePolicy(policy)
            self._layout.insertWidget(index + offset, widget, 0, Qt.AlignmentFlag.AlignVCenter)

    def show_menu(self, keyboard: bool = False):
        """Window menus below the menu button, first one selected if opened by keyboard (F10, Alt)"""
        menu = QMenu(self)
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        menu.addActions(self.menu_bar.actions())  # submenus of the menu bar, shared
        # Restart & Quit last, as the File menu of a Windows app (left out of the Window menu, see set_menu_bar)
        restart_app = getattr(self._window, "restart_app", None)
        quit_app = getattr(self._window, "quit_app", None)
        if callable(restart_app) and callable(quit_app):
            menu.addSeparator()
            menu.addAction(tr("Restart NeoPedal")).triggered.connect(restart_app)
            menu.addAction(tr("Quit")).triggered.connect(quit_app)
        menu.popup(self.button_menu.mapToGlobal(self.button_menu.rect().bottomLeft()))
        if keyboard and menu.actions():
            menu.setActiveAction(menu.actions()[0])

    def watch_alt_key(self):
        """Alt pressed & released alone opens the window menus, as a Windows menu bar (native window created)"""
        handle = window_handle(self._window)
        if handle is not None:
            handle.installEventFilter(AltMenuKey(lambda: self.show_menu(keyboard=True), self))

    def retranslate(self):
        """Button names in current language"""
        self.button_menu.setToolTip(f"{tr('Menu')} (F10)")
        self.button_menu.setAccessibleName(tr("Menu"))
        maximized = self._window.isMaximized()
        self.button_maximize.set_glyphs(RESTORE if maximized else MAXIMIZE)
        self.button_minimize.setAccessibleName(tr("Minimize"))
        self.button_maximize.setAccessibleName(tr("Restore") if maximized else tr("Maximize"))
        self.button_close.setAccessibleName(tr("Close"))
        # Tooltips as native caption buttons (Maximize: Snap Layouts flyout instead, hit as non-client area)
        self.button_minimize.setToolTip(tr("Minimize"))
        self.button_close.setToolTip(tr("Close"))

    def toggle_maximized(self):
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        kind = event.type()
        if kind == QEvent.Type.WindowStateChange:
            self.retranslate()  # Maximize or Restore
        if kind in (
            QEvent.Type.WindowTitleChange, QEvent.Type.ModifiedChange, QEvent.Type.ActivationChange,
            QEvent.Type.WindowIconChange, QEvent.Type.WindowStateChange,
        ):
            self.update()
            if kind == QEvent.Type.ActivationChange:
                for button in (self.button_minimize, self.button_maximize, self.button_close):
                    button.update()
        return False

    def event(self, event: QEvent) -> bool:
        handled = super().event(event)
        if event.type() == QEvent.Type.LayoutRequest:  # chip shown or hidden: free area changed, page name drawn again
            self.update()
        return handled

    def free_area(self) -> QRect:
        """Free area between both sides (drags the window, page name & saving state drawn there)"""
        space = self._free_space.geometry()
        gap = UIScaler.pixel(12)
        return QRect(space.left() + gap, 0, max(0, space.width() - 2 * gap), self.height())

    def paintEvent(self, event):
        painter = QPainter(self)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Window))
        # App icon
        size = UIScaler.pixel(ICON_SIZE)
        icon = self._window.windowIcon()
        if not icon.isNull():
            margin = UIScaler.pixel(ICON_LEFT)
            icon.paint(painter, QRect(margin, (self.height() - size) // 2, size, size))
        # Windows 10 draws no frame line above the client area (Windows 11 draws one all around the window)
        if WINDOWS_10_FRAME and not (self._window.isMaximized() or self._window.isFullScreen()):
            painter.setPen(palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Mid))
            painter.drawLine(0, 0, self.width(), 0)
        # Shown page name centered on the bar if it fits there, else centered in the free area (elided); saving
        # state at the right
        area = self.free_area()
        painter.setPen(palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.PlaceholderText))
        metrics = self.fontMetrics()
        if self._saving_shown:
            saving = tr("Saving\u2026")
            width = metrics.horizontalAdvance(saving)
            if width <= area.width():
                painter.drawText(area, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, saving)
                area.setRight(area.right() - width - UIScaler.pixel(12))
        title = bar_title(self._window)
        center = self.width() // 2
        half = min(center - area.left(), area.right() - center)
        if metrics.horizontalAdvance(title) > half * 2:  # buttons of one side too close to the middle
            center, half = area.center().x(), area.width() // 2
        if half > 0:
            text = metrics.elidedText(title, Qt.TextElideMode.ElideRight, half * 2)
            # Window inactive: muted, as caption buttons
            role = QPalette.ColorRole.WindowText if self.isActiveWindow() else QPalette.ColorRole.PlaceholderText
            painter.setPen(palette.color(QPalette.ColorGroup.Active, role))
            painter.drawText(QRect(center - half, 0, half * 2, self.height()), Qt.AlignmentFlag.AlignCenter, text)

    def hit_test(self, pos: QPoint) -> int:
        """Windows hit test value of a point of the title bar: caption (drag, double click), Maximize (Snap
        Layouts), else client (menus, buttons)"""
        child = self.childAt(pos)
        if child is self.button_maximize:
            return HTMAXBUTTON
        # Buttons (menu, Back & Forward, status chips, app tools, caption) clicked, other parts drag the window
        return HTCLIENT if isinstance(child, QAbstractButton) else HTCAPTION


class PageFrame(QWidget):
    """Page area framed as a panel inside title bar, rail & status bar (one piece in window color): line along its
    top, left & bottom edges, rounded left corners (drawn over the pages by PageCorner)"""

    def __init__(self, parent: QWidget, pages: QWidget):
        super().__init__(parent)
        self.setObjectName("pageFrame")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(1, 1, 0, 1)  # lines
        layout.addWidget(pages)
        self.corners = (PageCorner(self, False), PageCorner(self, True))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        bottom = self.corners[1]
        bottom.move(0, self.height() - bottom.height())

    def paintEvent(self, event):
        painter = QPainter(self)
        palette = self.palette()
        radius = self.corners[0].radius
        bottom = self.height() - 1
        painter.fillRect(self.rect(), palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Window))
        painter.setPen(palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Midlight))
        painter.drawLine(radius, 0, self.width(), 0)
        painter.drawLine(0, radius, 0, bottom - radius)
        painter.drawLine(radius, bottom, self.width(), bottom)


class PageCorner(QWidget):
    """Rounded top or bottom left corner of PageFrame: window color outside the arc, line along it, over the page"""

    def __init__(self, frame: PageFrame, bottom: bool):
        super().__init__(frame)
        self.radius = UIScaler.pixel(PAGE_CORNER_RADIUS)
        self.bottom = bottom
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.resize(self.radius + 1, self.radius + 1)
        self.raise_()  # pages are children of the stack below it

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        palette = self.palette()
        size = float(self.radius * 2)
        # Line centered on the pixels of the straight lines (first column, first or last row)
        top = self.height() - 0.5 - size if self.bottom else 0.5
        arc = QRectF(0.5, top, size, size)
        outside = QPainterPath()
        outside.addRect(QRectF(self.rect()))
        inside = QPainterPath()
        inside.addEllipse(arc)
        painter.fillPath(outside.subtracted(inside), palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Window))
        painter.setPen(palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Midlight))
        painter.drawArc(arc, 180 * 16 if self.bottom else 90 * 16, 90 * 16)


class NCCalcSizeParams(ctypes.Structure):
    _fields_ = (("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p))


def colorref(color: QColor) -> int:
    """Windows COLORREF (0x00BBGGRR) of a color"""
    return color.red() | color.green() << 8 | color.blue() << 16


class CaptionColors:
    """Native caption of the other windows of the app (dialogs, message boxes, setup wizard) in the window colors
    (Windows 11, nothing on Windows 10): same background as their contents, as the title bar of the main window

    Applied when a window gets focus (shown dialogs do), again for every shown window when the theme changes.
    """

    _main_window: QWidget
    _set_attribute: Callable[..., int]  # DwmSetWindowAttribute

    def __init__(self, main_window: QWidget):
        if sys.platform != "win32":
            raise OSError("Windows only")
        self._main_window = main_window
        dwmapi = ctypes.WinDLL("dwmapi")
        dwmapi.DwmSetWindowAttribute.argtypes = (wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD)
        dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
        self._set_attribute = dwmapi.DwmSetWindowAttribute
        app = QGuiApplication.instance()
        if isinstance(app, QGuiApplication):
            app.focusWindowChanged.connect(self.apply)

    def apply(self, window: QWindow | None):
        """Caption colors of a window with a native caption (not the main window, overlays, popups, tool windows)"""
        if not shiboken6.isValid(self._main_window):  # main window deleted (app connection left): stop following
            app = QGuiApplication.instance()
            if isinstance(app, QGuiApplication):
                with contextlib.suppress(RuntimeError, TypeError):
                    app.focusWindowChanged.disconnect(self.apply)
            return
        if not isinstance(window, QWindow) or window is window_handle(self._main_window) or not window.isVisible():
            return
        flags = window.flags()
        kind = flags & Qt.WindowType.WindowType_Mask
        if flags & Qt.WindowType.FramelessWindowHint or kind not in (Qt.WindowType.Window, Qt.WindowType.Dialog):
            return
        palette = QGuiApplication.palette()
        hwnd = int(window.winId())
        for attribute, role in ((DWMWA_CAPTION_COLOR, QPalette.ColorRole.Window),
                                (DWMWA_TEXT_COLOR, QPalette.ColorRole.WindowText)):
            value = wintypes.DWORD(colorref(palette.color(QPalette.ColorGroup.Active, role)))
            self._set_attribute(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value))

    def refresh(self):
        """Theme changed: shown windows in the new colors"""
        for window in QGuiApplication.topLevelWindows():
            self.apply(window)


def load_user32(keep_gil: bool = False):
    """user32 functions used by FrameHandler, own prototypes (not shared ctypes.windll ones)

    Args:
        keep_gil: functions called for window messages (hit test on each mouse move): GIL kept. A ctypes call
            releases it, and taking it back waits for the switch interval (5 ms) whenever another thread runs
            Python code (hit test measured 16-20 ms per message with one busy thread, 10 ms with GIL kept). Only
            for functions that return at once and send nothing to other threads (never SetWindowPos).
    """
    if sys.platform != "win32":
        raise OSError("Windows only")
    if keep_gil:  # functions of a WinDLL subclass flagged as PyDLL ones (GIL kept during call)
        held = type("HeldGilDLL", (ctypes.WinDLL,), {"_func_flags_": ctypes.WinDLL._func_flags_ | FUNCFLAG_PYTHONAPI})
        user32 = held("user32")
    else:
        user32 = ctypes.WinDLL("user32")
    user32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    user32.DefWindowProcW.restype = ctypes.c_ssize_t
    user32.SetWindowPos.argtypes = (
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT)
    user32.ScreenToClient.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.POINT))
    user32.IsZoomed.argtypes = (wintypes.HWND,)
    user32.GetDpiForWindow.argtypes = (wintypes.HWND,)
    user32.GetDpiForWindow.restype = wintypes.UINT
    user32.GetSystemMetricsForDpi.argtypes = (ctypes.c_int, wintypes.UINT)
    return user32


class MaximizeFilter(QAbstractNativeEventFilter):
    """Clicks of Maximize, hit as non-client area (Snap Layouts flyout): handled here, also so Windows never
    draws its classic caption button on press

    Mouse messages are queued: Qt gives them to application filters only, not to QWidget.nativeEvent. Installed
    while mouse is over Maximize only (see FrameHandler.hover_maximize), every message of the app passes through it.
    """

    def __init__(self, handler: FrameHandler):
        super().__init__()
        self._handler = handler

    def nativeEventFilter(self, event_type, message):
        return self._handler.handle_click(int(message)), 0


class FrameHandler:
    """Window messages of main window with app title bar (Windows): caption removed from the native frame,
    title bar areas told to Windows (drag, Maximize for Snap Layouts, resize border at the top)"""

    def __init__(self, window: QMainWindow, title_bar: TitleBar):
        self._window = window
        self._title_bar = title_bar
        self._user32 = load_user32(keep_gil=True)  # window messages
        self._hwnd = 0
        # Maximize hovered: told by hit tests (sent on each mouse move over window), left once mouse is off it
        # (checked by timer: mouse may leave the window at once, Windows leave messages come early)
        self._filter = MaximizeFilter(self)
        self._hovered = False
        self._leave_timer = QTimer(title_bar)
        self._leave_timer.setInterval(LEAVE_CHECK_MS)
        self._leave_timer.timeout.connect(self.check_maximize_left)
        title_bar.destroyed.connect(self.remove_filter)

    def attach(self):
        """Native window created: frame computed again without caption (see handle_calc_size)"""
        self._hwnd = int(self._window.winId())
        load_user32().SetWindowPos(self._hwnd, None, 0, 0, 0, 0, SWP_FRAME_CHANGED)  # sends messages: GIL released

    def handle(self, address: int) -> tuple[bool, int] | None:
        """Result of a window message (MSG at address), None to leave it to Qt"""
        message = ctypes.c_uint.from_address(address + MESSAGE_OFFSET).value
        if message == WM_NCCALCSIZE:
            return self.handle_calc_size(wintypes.MSG.from_address(address))
        if message == WM_NCHITTEST:
            return True, self.hit_test(wintypes.MSG.from_address(address))
        return None  # most messages: no structure built

    def hover_maximize(self, hovered: bool):
        """Maximize hovered: drawn hovered, its clicks handled (filter installed) until mouse leaves it"""
        button = self._title_bar.button_maximize
        button.set_nc_state(hovered, hovered and button.nc_pressed)
        if hovered == self._hovered:
            return
        app = QCoreApplication.instance()
        if app is None:
            return
        self._hovered = hovered
        if hovered:
            app.installNativeEventFilter(self._filter)
            self._leave_timer.start()
        else:
            app.removeNativeEventFilter(self._filter)
            self._leave_timer.stop()

    def check_maximize_left(self):
        button = self._title_bar.button_maximize
        if not (button.isVisible() and button.rect().contains(button.mapFromGlobal(QCursor.pos()))):
            self.hover_maximize(False)

    def remove_filter(self):
        """Title bar deleted (window closed): filter never left installed"""
        app = QCoreApplication.instance()
        if self._hovered and app is not None:
            app.removeNativeEventFilter(self._filter)
        self._hovered = False

    def handle_click(self, address: int) -> bool:
        """Click of Maximize (MSG at address) handled, see MaximizeFilter"""
        message = ctypes.c_uint.from_address(address + MESSAGE_OFFSET).value
        if message not in MAXIMIZE_MESSAGES:
            return False
        msg = wintypes.MSG.from_address(address)
        if msg.hWnd != int(self._window.winId()) or msg.wParam != HTMAXBUTTON:  # not the one of attach: Qt may recreate it
            return False
        button = self._title_bar.button_maximize
        if message == WM_NCLBUTTONUP:
            if button.nc_pressed:
                button.set_nc_state(True, False)
                self._title_bar.toggle_maximized()
        else:  # pressed (down, or second press of a double click)
            button.set_nc_state(True, True)
        return True

    def border_height(self, hwnd: int | None) -> int:
        """Height of resize border (physical pixels) at window DPI"""
        dpi = self._user32.GetDpiForWindow(hwnd) or 96
        return (self._user32.GetSystemMetricsForDpi(SM_CYSIZEFRAME, dpi)
                + self._user32.GetSystemMetricsForDpi(SM_CXPADDEDBORDER, dpi))

    def handle_calc_size(self, msg: wintypes.MSG) -> tuple[bool, int] | None:
        """Client area: native one (side & bottom borders kept) up to window top (no caption)"""
        if not msg.wParam:
            return None
        params = NCCalcSizeParams.from_address(msg.lParam)
        top = params.rgrc[0].top
        self._user32.DefWindowProcW(msg.hWnd, msg.message, msg.wParam, msg.lParam)
        params.rgrc[0].top = top
        if self._user32.IsZoomed(msg.hWnd):  # maximized window overlaps screen by its border: not shown
            params.rgrc[0].top += self.border_height(msg.hWnd)
        return True, 0

    def hit_test(self, msg: wintypes.MSG) -> int:
        """Native borders, resize border at the top, title bar areas, else client"""
        result = self._user32.DefWindowProcW(msg.hWnd, msg.message, msg.wParam, msg.lParam)
        if result != HTCLIENT:  # side & bottom borders
            if self._hovered:
                self.hover_maximize(False)
            return result
        point = wintypes.POINT(ctypes.c_short(msg.lParam & 0xFFFF).value,
                               ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value)
        self._user32.ScreenToClient(msg.hWnd, ctypes.byref(point))
        window = self._window
        if point.y < self.border_height(msg.hWnd) and not (window.isMaximized() or window.isFullScreen()):
            return HTTOP
        title_bar = self._title_bar
        if not title_bar.isVisible():
            return HTCLIENT
        ratio = window.devicePixelRatioF()
        pos = title_bar.mapFrom(window, QPoint(int(point.x / ratio), int(point.y / ratio)))
        result = title_bar.hit_test(pos) if title_bar.rect().contains(pos) else HTCLIENT
        if result == HTMAXBUTTON or self._hovered:
            self.hover_maximize(result == HTMAXBUTTON)
        return result
