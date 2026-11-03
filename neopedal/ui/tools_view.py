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
Tools: opening tool pages by path (Tools menu, navigation bar, command palette, links of other pages), former paths
of merged tools
"""

import logging
from importlib import import_module

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from ..i18n import tr
from ..template.page_registry import DATA_EDITOR_TABS, MAP_VIEWER_PATH, tool_pages, tool_sections
from ._common import find_dialog_host

logger = logging.getLogger(__name__)

# Sections: (title, ((label, icon glyph in Segoe Fluent Icons / MDL2 Assets, "module.DialogClass"), ...)),
# see template.page_registry.PAGES. Dialog modules are imported when first opened, to keep startup light
TOOL_SECTIONS = tool_sections()
# Tools of Tools menu & command palette (Settings left out: own menu, gear button of the rail & Ctrl+,; Plugin
# Manager: Overlays page)
LISTED_TOOL_SECTIONS = tool_sections(listed_only=True)


# Former tools merged into another one: old path (saved open pages, navigation bar) -> new path
RENAMED_TOOLS = {
    "fuel_calculator.FuelCalculator": "race_calculator.RaceCalculator",
    "tyre_strategy_planner.TyreStrategyPlanner": "race_calculator.RaceCalculator",
    "game_replays.GameReplays": "race_results_viewer.RaceResultsViewer",  # replays list of results & replays
}
SHOW_REPLAYS = "game_replays.GameReplays"  # former path: replays list shown
# Former pages now a tab of another page: old path -> (page path, tab key). Editors: tabs of Data Editors (Track Map
# Viewer: map of its Tracks tab), Spectate page: Spectate tab of Broadcast Director
DATA_EDITORS = "data_editors.DataEditors"
DIRECTOR = "broadcast_director.BroadcastDirector"
SPECTATE_PATH = "spectate_view.SpectateList"  # links of the former Spectate page (notice, home check)
PAGE_TABS = {path: (DATA_EDITORS, key) for key, _, path in DATA_EDITOR_TABS}
PAGE_TABS[MAP_VIEWER_PATH] = (DATA_EDITORS, "track_info_editor")
PAGE_TABS[SPECTATE_PATH] = (DIRECTOR, "spectate")
RENAMED_TOOLS.update({path: page for path, (page, _) in PAGE_TABS.items()})
# Former Preset Comparison tool: compare panel of the Presets page (path kept: palette, saved pages & shortcuts)
SHOW_PRESET_COMPARE = "preset_compare.PresetCompare"
RENAMED_TOOL_KEYS = {old.split(".", 1)[0]: new.split(".", 1)[0] for old, new in RENAMED_TOOLS.items()}
RENAMED_TOOL_KEYS["preset_compare"] = "preset"  # navigation bar & quick access entry: Presets page
RENAMED_TOOL_KEYS["pacenotes"] = "data_editors"  # former Pace Notes page: Notes tab of Data Editors
# Former Modules & Hotkeys pages: categories of the Settings page
RENAMED_TOOL_KEYS.update(module="app_settings", hotkey="app_settings")
RENAMED_TOOL_KEYS["spectate"] = "broadcast_director"  # former Spectate page: Spectate tab of Broadcast Director
# Extra words finding a tool in command palette (former names, what it covers), both languages
TOOL_KEYWORDS = {page.dialog: page.keywords for page in tool_pages() if page.keywords}


def open_tool(dialog_path: str, parent):
    """Open tool dialog from "module.DialogClass" path relative to ui package, opened dialog returned

    Returns:
        Dialog shown (already open one brought to front), None if unable to open.
    """
    if dialog_path == SHOW_REPLAYS:
        dialog = open_tool(RENAMED_TOOLS[dialog_path], parent)
        show_replays = getattr(dialog, "show_replays", None)
        if callable(show_replays):
            show_replays()
        return dialog
    if dialog_path == SHOW_PRESET_COMPARE:
        return show_preset_compare(parent)
    if dialog_path in PAGE_TABS:  # former page: its tab of another page, the page of the tab returned
        page_path, tab = PAGE_TABS[dialog_path]
        dialog = open_tool(page_path, parent)
        show_tab = getattr(dialog, "show_tab", None)
        return show_tab(tab) if callable(show_tab) else dialog
    dialog_path = RENAMED_TOOLS.get(dialog_path, dialog_path)
    module_name, class_name = dialog_path.rsplit(".", 1)
    host = find_dialog_host(parent)
    if host is not None and host.activate_dialog_page(class_name):  # already open as page in app
        return next((page.dialog for page in host.dialog_pages()
                     if page.dialog is not None and type(page.dialog).__name__ == class_name), None)
    for widget in QApplication.topLevelWidgets():  # already open: bring to front instead of warning
        if type(widget).__name__ == class_name and widget.isVisible():
            if widget.isMinimized():
                widget.showNormal()
            widget.raise_()
            widget.activateWindow()
            return widget
    try:
        dialog_class = getattr(import_module(f"{__package__}.{module_name}"), class_name)
    except (ImportError, AttributeError):  # slot exceptions are silent in the windowed build
        logger.exception("TOOLS: unable to open %s", dialog_path)
        from .quick import dialogs

        dialogs.alert(parent, tr("Error"), tr("Unable to open tool, see log for details."))
        return None
    _dialog = dialog_class(parent)
    _dialog.show()
    return _dialog


def show_preset_compare(parent):
    """Presets page shown with its compare panel open (loaded preset with another one), the page returned, None if
    no main window"""
    from .nav_rail import PAGE_INDEX
    from .preset_view import PresetList

    host = find_dialog_host(parent)
    if host is None:
        return None
    host.select_page(PAGE_INDEX["preset"])
    page = host.window().findChild(PresetList)
    if page is None or page.ensure_view() is None:
        return None
    QTimer.singleShot(0, page, lambda: page.backend.openPage("compare"))  # once the page is shown & laid out
    return page
