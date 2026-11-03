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
Navigation rail entries: pages of main window & tool dialogs, chosen & ordered by user

Rail content is saved in application setting "rail_items": entry keys separated by comma,
page keys (see NAV_PAGES) or tool dialog module names (see tools_view.TOOL_SECTIONS).
Entries are dragged in the rail to another place, onto More (left out) or from More (added back); pages left
out are listed by More, under the entries, and stay reachable from command palette (Ctrl+K).
"""

from __future__ import annotations

from typing import NamedTuple

from ..const_file import ConfigType
from ..i18n import tr
from ..setting import cfg
from ..template.page_registry import main_pages, tool_pages
from ..template.setting_global import GLOBAL_DEFAULT
from .tools_view import RENAMED_TOOL_KEYS, TOOL_SECTIONS

# Pages: (key, label, icon glyph in Segoe Fluent Icons / MDL2 Assets, fallback letter), see template.page_registry
NAV_PAGES = tuple((page.name, page.label, page.glyph, page.letter) for page in main_pages())
PAGE_INDEX = {key: index for index, (key, *_) in enumerate(NAV_PAGES)}

# Short rail label of tools (rail buttons are narrow), full name in tooltip
TOOL_SHORT_LABELS = {page.name: page.short_label for page in tool_pages() if page.short_label}
# Rail label of pages named in plural there (English: "Modules", "Presets", "Hotkeys")
PAGE_SHORT_LABELS = {page.name: page.short_label for page in main_pages() if page.short_label}


def rail_text(short: str, full: str) -> str:
    """Rail label in app language: short label (plural page names, short tool names), else full label"""
    return tr(short) if short else tr(full)


def page_name(index: int) -> str:
    """Name of main window page in app language, as in the rail (plural: "Modules", "Presets", "Hotkeys")"""
    key, label, *_ = NAV_PAGES[index]
    return rail_text(PAGE_SHORT_LABELS.get(key, ""), label)


class RailEntry(NamedTuple):
    """Navigation rail entry"""

    key: str
    label: str  # short label under icon
    tooltip: str  # full name
    glyph: str
    letter: str  # drawn without icon font
    page: int = -1  # page index, -1 for tool
    dialog: str = ""  # "module.DialogClass" of tool


def rail_entries() -> dict[str, RailEntry]:
    """Every possible rail entry by key, pages first then tools"""
    entries = {
        key: RailEntry(key, PAGE_SHORT_LABELS.get(key, label), PAGE_SHORT_LABELS.get(key, label), glyph, letter,
                       page=index)  # page named the same in tooltip, quick access (plural "Modules")
        for index, (key, label, glyph, letter) in enumerate(NAV_PAGES)
    }
    for _, tools in TOOL_SECTIONS:
        for label, glyph, dialog_path in tools:
            key = dialog_path.split(".", 1)[0]
            short = TOOL_SHORT_LABELS.get(key, label)
            entries[key] = RailEntry(key, short, label, glyph, short[:1], dialog=dialog_path)
    return entries


def parse_rail_items(text: str) -> list[str]:
    """Known & unique entry keys of rail setting text, in order"""
    known = rail_entries()
    keys: list[str] = []
    for key in (text or "").split(","):
        key = RENAMED_TOOL_KEYS.get(key.strip(), key.strip())  # merged tools: new tool
        if key in known and key not in keys:
            keys.append(key)
    return keys


def default_rail_items() -> list[str]:
    application: dict = GLOBAL_DEFAULT["application"]  # type: ignore[assignment]
    return parse_rail_items(str(application["rail_items"]))


def current_rail_items() -> list[str]:
    """Rail entry keys from setting, default rail if setting has no valid entry"""
    return parse_rail_items(cfg.application.get("rail_items", "")) or default_rail_items()


def hidden_rail_items() -> list[str]:
    """Every page & tool left out of the rail, pages first: listed when its More entry is unfolded"""
    shown = set(current_rail_items())
    return [key for key in rail_entries() if key not in shown]


def save_rail_items(keys: list[str]):
    """Rail entries saved (at least one entry kept)"""
    if keys:
        cfg.application["rail_items"] = ",".join(keys)
        cfg.save(config_type=ConfigType.CONFIG)

