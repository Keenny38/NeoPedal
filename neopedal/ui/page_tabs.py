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
Tabs of a page made of former pages (Data Editors, Modules & Performance)

Underlined tab bar (QTabBar look of the app style sheet, as TpTabBar) above the pages, each page made when its tab
is first shown (memory: most tabs are never opened). Dialog pages (BaseDialog) are shown inside as plain widgets.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import NamedTuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QStackedWidget, QTabBar, QVBoxLayout, QWidget

from ._common import MODIFIED_MARKER, UIScaler

PAGE_MARGIN = 0.8  # em, tabs lined up with page contents (padPage of Qt Quick pages)


class PageTab(NamedTuple):
    """Tab: key (deep links, saved choice), label (translated), page factory (parent -> page)"""

    key: str
    label: str
    factory: Callable[[QWidget], QWidget]


class PageTabs(QWidget):
    """Tab bar & pages made when first shown

    Emits page_built with the index of a page made, current_changed with the index of the page shown.
    """

    page_built = Signal(int)
    current_changed = Signal(int)

    def __init__(self, parent, tabs: Sequence[PageTab], current: int = 0):
        super().__init__(parent)
        self.tabs = tuple(tabs)
        self._pages: dict[int, QWidget] = {}
        self.tab_bar = QTabBar(self)
        self.tab_bar.setObjectName("pageTabs")
        self.tab_bar.setDrawBase(False)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setDocumentMode(True)
        self.tab_bar.setUsesScrollButtons(True)  # narrow window: tabs scroll, page keeps its width
        self.tab_bar.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        for tab in self.tabs:
            self.tab_bar.addTab(tab.label)
        self.stack = QStackedWidget(self)
        layout = QVBoxLayout(self)
        margin = round(UIScaler.FONT_PIXEL_SCALED * PAGE_MARGIN)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        bar_layout = QVBoxLayout()
        bar_layout.setContentsMargins(margin, UIScaler.pixel(2), margin, 0)
        bar_layout.addWidget(self.tab_bar, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(bar_layout)
        layout.addWidget(self.stack, stretch=1)
        self.tab_bar.setCurrentIndex(max(0, min(current, len(self.tabs) - 1)))
        self.tab_bar.currentChanged.connect(self.show_index)

    def index_of(self, key: str) -> int:
        """Tab index of key, -1 if unknown"""
        return next((index for index, tab in enumerate(self.tabs) if tab.key == key), -1)

    def current_index(self) -> int:
        return self.tab_bar.currentIndex()

    def current_key(self) -> str:
        index = self.current_index()
        return self.tabs[index].key if 0 <= index < len(self.tabs) else ""

    def page(self, index: int) -> QWidget | None:
        """Page of tab, None if not made yet"""
        return self._pages.get(index)

    def built_pages(self) -> list[tuple[int, QWidget]]:
        """Pages made so far: (tab index, page), tab order"""
        return sorted(self._pages.items(), key=lambda item: item[0])

    def ensure_page(self, index: int) -> QWidget:
        """Page of tab, made if needed"""
        page = self._pages.get(index)
        if page is None:
            page = self.tabs[index].factory(self.stack)
            if isinstance(page, QDialog):  # dialog page shown inside, never as a window
                page.setWindowFlags(Qt.WindowType.Widget)
            self._pages[index] = page
            self.stack.addWidget(page)
            self.page_built.emit(index)
        return page

    def show_current(self) -> QWidget | None:
        """Page of current tab made & shown (first show of the tabs)"""
        index = self.current_index()
        if not 0 <= index < len(self.tabs):
            return None
        page = self.ensure_page(index)
        if self.stack.currentWidget() is not page:
            self.stack.setCurrentWidget(page)
        return page

    def show_index(self, index: int):
        """Tab chosen: its page made & shown"""
        if not 0 <= index < len(self.tabs):
            return
        if self.tab_bar.currentIndex() != index:
            self.tab_bar.setCurrentIndex(index)  # calls back here
            return
        self.show_current()
        self.current_changed.emit(index)

    def select(self, key: str) -> QWidget | None:
        """Tab of key shown, its page returned (None if unknown key)"""
        index = self.index_of(key)
        if index < 0:
            return None
        self.show_index(index)
        return self.ensure_page(index)

    def set_modified(self, index: int, modified: bool):
        """Unsaved changes marker on tab label"""
        if 0 <= index < len(self.tabs):
            label = self.tabs[index].label
            self.tab_bar.setTabText(index, f"{MODIFIED_MARKER}{label}" if modified else label)

    def showEvent(self, event):
        self.show_current()  # first tab page made once the tabs are shown (not when built)
        super().showEvent(event)
