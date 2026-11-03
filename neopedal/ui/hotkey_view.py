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
Hotkeys: key bindings by section (search, assigned only), key capture in a dialog, a category of the Settings page
(former Hotkeys page)

Qt Quick page (qml/config/Hotkeys.qml, context "hotkeyBackend") shown by the Settings page (app_settings.py), state,
key capture & actions in quick/hotkey_backend.py.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from .quick.hotkey_backend import HotkeyBackend


class HotkeysHost:
    """Hotkeys category of the Settings page: backend of its page & its toasts

    Args:
        page: Settings page (toasts, key capture of its window; backend parent).
    """

    def __init__(self, page: QWidget):
        self.page = page
        self.backend = HotkeyBackend(page, page.window)
        self.backend.notice.connect(self.show_notice)

    def page_shown(self):
        self.backend.page_shown()

    def page_hidden(self):
        self.backend.page_hidden()  # page left with capture open: key capture closed

    def refresh(self, *_):
        """Bindings or presets changed elsewhere: rows read again (once shown if hidden)"""
        self.backend.refresh()

    def release(self):
        """Settings page closed (its QML gone first): key capture closed"""
        self.backend.release()

    def show_notice(self, text: str, undoable: bool):
        """Toast of the page (TpDialogHost), Undo of the last clear"""
        from ..i18n import tr
        from .toast import show_toast

        show_toast(self.page, text, action_text=tr("Undo") if undoable else "",
                   action=self.backend.undo if undoable else None)
