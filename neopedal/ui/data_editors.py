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
Data editors: what overlays read about cars & tracks (classes, brands, compounds, brakes, heatmaps, tracks) and
track & pace notes, one tab each (former editor pages, see template.page_registry.DATA_EDITOR_TABS)

Each tab is the former editor page, made when first shown, with its own undo history, Save & unsaved changes:
Ctrl+S saves the tab shown, closing the page asks for every tab with unsaved changes (tab marked "•"). Pace notes
playback (former Pace Notes page) is in the Notes tab. Old links to an editor open its tab (tools_view.open_tool).
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from importlib import import_module

from PySide6.QtCore import QCoreApplication, QEvent, QSize, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..i18n import tr
from ..template.page_registry import DATA_EDITOR_TABS
from ._common import BaseDialog, UIScaler
from .page_tabs import PageTab, PageTabs


def make_editor(dialog_path: str, parent: QWidget) -> BaseDialog:
    """Editor page of a tab from "module.DialogClass" path relative to ui package, shown inside Data Editors"""
    module_name, class_name = dialog_path.rsplit(".", 1)
    editor = getattr(import_module(f"{__package__}.{module_name}"), class_name)(parent)
    editor.in_app_page = True  # part of a page: own Ctrl+S never added, its dialogs open over it
    return editor


class DataEditors(BaseDialog):
    """Data editors page: one tab per former editor page"""

    page_minimum_changed = Signal()  # tab shown changed: page area minimum of its editor (DialogPage)
    last_tab = ""  # tab shown last, opened again there while the app runs

    def __init__(self, parent):
        super().__init__(parent)
        self.set_utility_title(tr("Data Editors"))
        tabs = [PageTab(key, tr(label), partial(make_editor, path)) for key, label, path in DATA_EDITOR_TABS]
        current = next((index for index, tab in enumerate(tabs) if tab.key == DataEditors.last_tab), 0)
        self.tabs = PageTabs(self, tabs, current)
        self.tabs.page_built.connect(self.editor_built)
        self.tabs.current_changed.connect(self.tab_changed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)
        self.resize(UIScaler.size(84), UIScaler.size(48))

    def editors(self) -> list[BaseDialog]:
        """Editors made so far, tab order"""
        return [editor for _, editor in self.tabs.built_pages() if isinstance(editor, BaseDialog)]

    def current_editor(self) -> BaseDialog | None:
        editor = self.tabs.page(self.tabs.current_index())
        return editor if isinstance(editor, BaseDialog) else None

    def show_tab(self, key: str) -> BaseDialog | None:
        """Tab of editor shown (key: former tool name, see DATA_EDITOR_TABS), its editor returned"""
        editor = self.tabs.select(key)
        return editor if isinstance(editor, BaseDialog) else None

    def editor_built(self, index: int):
        editor = self.tabs.page(index)
        if isinstance(editor, BaseDialog):
            editor.modified_changed.connect(partial(self.editor_modified, index))
            editor.installEventFilter(self)  # Esc closes the page, not the tab (see eventFilter)
            self.editor_modified(index)

    def editor_modified(self, index: int, *_):
        editor = self.tabs.page(index)
        if isinstance(editor, BaseDialog):
            self.tabs.set_modified(index, editor.has_unsaved_changes())
        self.refresh_modified()

    def tab_changed(self, index: int):
        DataEditors.last_tab = self.tabs.current_key()
        self.page_minimum_changed.emit()

    # Unsaved changes: of every tab
    def is_modified(self) -> bool:
        return any(editor.has_unsaved_changes() for editor in self.editors())

    def set_unmodified(self):
        """Changes dropped (tests, page closed without asking)"""
        for editor in self.editors():
            set_unmodified = getattr(editor, "set_unmodified", None)
            if callable(set_unmodified):
                set_unmodified()

    def confirm_discard(self) -> bool:
        """Changes of each tab saved, discarded or kept (Cancel, saving failed: tab shown, True to close)"""
        for index, editor in self.tabs.built_pages():
            if not isinstance(editor, BaseDialog) or not editor.has_unsaved_changes():
                continue
            confirm = getattr(editor, "confirm_discard", None)
            if callable(confirm):
                self.tabs.show_index(index)  # asked over the tab it is about
                if not confirm():
                    return False
        return True

    def save_action(self) -> Callable[[], object] | None:
        """Ctrl+S: save of the tab shown"""
        editor = self.current_editor()
        return editor.save_action() if editor is not None else None

    def page_minimum_size(self) -> QSize:
        """Page area minimum while shown in app window: of the editor shown, below the tabs"""
        editor = self.current_editor()
        minimum = getattr(editor, "page_minimum_size", None)
        size = minimum() if callable(minimum) else QSize(0, 0)
        return QSize(size.width(), size.height() + self.tabs.tab_bar.sizeHint().height())

    def eventFilter(self, watched, event):
        # Esc not used by an editor (QDialog would close the tab alone): sent to this page, closed like any page
        # (DialogPage keeps pages without Close button open)
        if (event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent)
                and event.key() == Qt.Key.Key_Escape and watched in self.editors()):
            QCoreApplication.sendEvent(self, QKeyEvent(event.type(), event.key(), event.modifiers()))
            return True
        return super().eventFilter(watched, event)

    def reject(self):
        """Esc: closed like Close (unsaved changes asked)"""
        self.close()

    def closeEvent(self, event):
        """Unsaved changes asked first (Cancel or saving failed: page kept open). QDialog.closeEvent not called:
        it would call reject(), closing again (ignored as nested: page left open)"""
        if not self._page_released and not self.confirm_discard():
            event.ignore()
            return
        self.release_page()
        event.accept()

    def free_page(self):
        """Each editor freed (QML views before their backends, see BaseDialog.free_page)"""
        for editor in self.editors():
            editor.release_page()
