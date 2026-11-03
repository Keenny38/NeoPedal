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
Broadcast Director (LMU): camera desk, automatic director & commentator screen, live or in a replay

Qt Quick page (ui/qml/BroadcastDirector.qml), state & game requests in quick/director_backend.py,
race events & shots in process/director.py. Everything goes through the game Rest API (see game_rest).

Spectate tab (former Spectate page, spectate_view.py): driver the overlays show, any game (rFactor 2 too). The page
opens on it when the selected game API is not Le Mans Ultimate (the director needs LMU).
"""

from contextlib import suppress

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QVBoxLayout, QWidget

from .. import app_signal
from ..i18n import tr
from ._common import BaseDialog, UIScaler
from .page_tabs import PageTab, PageTabs


class BroadcastDirector(BaseDialog):
    """Broadcast director of the session or replay open in game (LMU)"""

    KEEP_WHEN_HIDDEN = True  # auto mode keeps choosing cameras while streaming, window hidden
    ESC_CLOSES = False  # Esc never closes the page (a key slip mid-broadcast), see app_tab_view.DialogPage
    last_tab = ""  # tab shown last, opened again there while the app runs

    def __init__(self, parent):
        from .quick import create_quick_view
        from .quick.director_backend import DirectorBackend

        super().__init__(parent)
        self.set_utility_title(tr("Broadcast Director"))
        self.setMinimumSize(self.page_minimum_size())
        self.backend = DirectorBackend(self)
        self.view = create_quick_view(self, "BroadcastDirector.qml", {"backend": self.backend}, samples=0)
        self._director_shown = False  # director backend told the page is shown, see update_director_shown
        tabs = (PageTab("director", tr("Director"), self.director_page), PageTab("spectate", tr("Spectate"), spectate_page))
        current = next((index for index, tab in enumerate(tabs) if tab.key == BroadcastDirector.last_tab), -1)
        if current < 0:  # Spectate first without Le Mans Ultimate (no director)
            from ..const_api import API_LMU_CONFIG
            from ..setting import cfg

            current = 0 if cfg.api_key == API_LMU_CONFIG else 1
        self.tabs = PageTabs(self, tabs, current)
        self.tabs.current_changed.connect(self.tab_changed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)
        self.resize(UIScaler.size(100), UIScaler.size(56))
        # Spectate mode or driver changed elsewhere (hotkey, API menu, director cut): Spectate tab told
        app_signal.refresh.connect(self.refresh_spectate)
        app_signal.spectate_changed.connect(self.refresh_spectate)

    def director_page(self, parent: QWidget) -> QWidget:
        """Director tab: the Qt Quick page made with the dialog (its backend runs the director)"""
        self.view.setParent(parent)
        return self.view

    def show_tab(self, key: str) -> QWidget | None:
        """Tab shown ("director", "spectate"), its page returned"""
        return self.tabs.select(key)

    def tab_changed(self, _index: int):
        BroadcastDirector.last_tab = self.tabs.current_key()
        self.update_director_shown()

    def update_director_shown(self):
        """Director told when its tab shows or hides (game asked only while shown)"""
        shown = self.isVisible() and self.tabs.current_key() == "director"
        if shown != self._director_shown:
            self._director_shown = shown
            if shown:
                self.backend.page_shown()
            else:
                self.backend.page_hidden()

    def refresh_spectate(self, *_):
        page = self.tabs.page(self.tabs.index_of("spectate"))
        refresh = getattr(page, "refresh", None)
        if callable(refresh):
            refresh()

    @staticmethod
    def page_minimum_size() -> QSize:
        """Toolbar never cut (QML pages do not scroll): under 70 em the three columns are stacked in tabs"""
        return QSize(UIScaler.size(52), UIScaler.size(38))

    def keep_when_hidden(self) -> bool:
        """Director off: freed while hidden like any page"""
        return self.backend._enabled

    def showEvent(self, event):
        """Director tab: game asked at once, then about every second until the page closes"""
        super().showEvent(event)
        self.update_director_shown()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.update_director_shown()

    def closeEvent(self, event):
        self.release_page()
        super().closeEvent(event)

    def free_page(self):
        """Spectate tab released, then the director (QML before its backend, see BaseDialog.free_page)"""
        for signal in (app_signal.refresh, app_signal.spectate_changed):
            with suppress(RuntimeError, TypeError):
                signal.disconnect(self.refresh_spectate)
        page = self.tabs.page(self.tabs.index_of("spectate"))
        release_page = getattr(page, "release_page", None)
        if callable(release_page):
            release_page()
        super().free_page()


def spectate_page(parent: QWidget) -> QWidget:
    """Spectate tab: driver the overlays show"""
    from .spectate_view import SpectateList

    return SpectateList(parent)
