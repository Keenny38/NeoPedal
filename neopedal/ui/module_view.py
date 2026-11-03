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
Modules: data modules as cards (what each computes, state, overlays depending on it), search & filter, a category of
the Settings page (former Modules page); its Performance button opens the Overlay Performance page

Qt Quick page (qml/config/Modules.qml, context "moduleBackend") shown by the Settings page (app_settings.py), state &
actions in quick/module_backend.py. sort_key & highlight live here (imported by many pages): this module imports
nothing heavy.
"""

from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

    from ..module_control import ModuleControl
    from .quick.module_backend import ModuleBackend


def sort_key(text: str) -> str:
    """Alphabetical sort key in any language: ignore case & accents (é = e)"""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def highlight(text: str, words: tuple[str, ...]) -> str:
    """Label as rich text, searched words in bold (case & accent folded match): option searches of every page"""
    folded = sort_key(text)
    if len(folded) != len(text) or not words:  # folding changed length: no safe mapping
        return html.escape(text)
    marks = [False] * len(text)
    for word in words:
        for match in re.finditer(re.escape(word), folded):
            for index in range(match.start(), match.end()):
                marks[index] = True
    parts, bold = [], False
    for char, mark in zip(text, marks):
        if mark != bold:
            parts.append("<b>" if mark else "</b>")
            bold = mark
        parts.append(html.escape(char))
    if bold:
        parts.append("</b>")
    return "".join(parts)



class ModulesHost:
    """Modules category of the Settings page: backend of its page & what the backend asks of the page

    Args:
        page: Settings page (dialogs, toasts; backend parent).
        open_section: Settings category of a module's options shown.
        module_control: module control, mctrl if not set.
        widget_control: widget control (overlays depending on each module), wctrl if not set.
    """

    def __init__(self, page: QWidget, open_section: Callable[[str], None],
                 module_control: ModuleControl | None = None, widget_control: ModuleControl | None = None):
        from ..module_control import mctrl, wctrl
        from .quick.module_backend import ModuleBackend

        self.page = page
        self._open_section = open_section
        self.backend: ModuleBackend = ModuleBackend(
            page, module_control or mctrl, widget_control or wctrl, open_section, self.confirm, self.show_log,
            self.reset_data, self.ask, open_performance=self.open_performance,
        )

    def page_shown(self):
        self.backend.page_shown()  # states read again: overlays switched on other pages, modules started
        self.backend.loadDependenciesLater()

    def page_hidden(self):
        self.backend.page_hidden()  # app refresh signals no longer read every module & overlay while hidden

    def refresh(self, *_):
        """Setting, preset or module state changed elsewhere (hotkey, tray, other page): once shown if hidden"""
        self.backend.settings_changed()

    def release(self):
        """Settings page closed (its QML gone first): jobs, timers & deferred work stopped"""
        self.backend.release()

    def confirm(self, text: str) -> bool:
        from ..i18n import tr
        from ._common import confirm_action

        return confirm_action(self.page, tr("Confirm"), text, tr("Confirm"))

    def ask(self, text: str, on_result):
        """Confirmation over the page (QML dialog of its TpDialogHost), answer by callback"""
        from ..i18n import tr
        from .quick.dialogs import confirm

        confirm(self.page, tr("Confirm"), text, tr("Confirm"), on_result)

    def show_log(self):
        from .log_info import LogInfo

        LogInfo(self.page.window()).show()

    def reset_data(self, method: str):
        """Reset saved data (delta best, fuel delta...): asked first, see menu.ResetDataMenu"""
        from ..i18n import tr
        from .menu import ResetDataMenu

        menu = ResetDataMenu(tr("Reset Data"), self.page.window())
        try:
            getattr(menu, method)()
        finally:
            menu.deleteLater()

    def open_performance(self):
        """Overlay Performance page: CPU time of each overlay & module, game data state"""
        from ..template.page_registry import PERFORMANCE_PATH
        from .tools_view import open_tool

        open_tool(PERFORMANCE_PATH, self.page)
