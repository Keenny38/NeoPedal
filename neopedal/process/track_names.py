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
Track layout names shown by the app: one name per layout on every page

LMU names a layout several ways (seen on game 1.3, 39 layouts):

    layout   shared memory mTrackName, results <TrackCourse>, getTracksAll properTrackName, replay names,
             driver stats keys & every file named after a track ("Circuit de la Sarthe", "Bahrain Outer
             Circuit", "Paul Ricard - ELMS")
    event    results <TrackEvent>, getTracksAll eventName, /rest/race/track name, RaceControl layouts
             ("24 Heures du Mans", "6 Hours of Monza"; layout name for other layouts)
    venue    results <TrackVenue>, getTracksAll trackName, /rest/race/track shortName (with version):
             shared by every layout of a circuit, never a layout name
    folder   getTracksAll cmpName, RaceControl friendly ("PortimaoWEC_2023", "Spa_2023")
    scene    sceneDesc ("SPAWEC_ENDCE"), RaceControl scn ("SpaWEC_Endce")

The layout name is shown: the game list /rest/sessions/getTracksAll gives it for any other name. Names are
only shown this way, stored keys & file names keep the name they were saved with.
"""

from __future__ import annotations

import re
from typing import Any

VERSION = re.compile(r"\s+v?\d+(?:\.\d+)+$")  # " 1.31" after a /rest/race/track short name
LOST = "�"  # character the game could not encode
ALIASES = ("sceneDesc", "eventName", "grandPrixName", "name")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def clean(name: str) -> str:
    """Name of a track unknown to the game list as shown: version dropped, folder name spaced
    ("PortimaoWEC_2023" -> "PortimaoWEC 2023")"""
    name = VERSION.sub("", _text(name))
    return name.replace("_", " ") if " " not in name else name


def parse_track_names(data: Any) -> dict[str, str]:
    """Every name of game track list (/rest/sessions/getTracksAll, lower case) -> layout name

    Layout, scene & event names lead to their layout; a folder name only when its main layouts (those
    without layoutName) share one name; venue names never (shared by different layouts).
    """
    names: dict[str, str] = {}
    folders: dict[str, set[str]] = {}
    items = [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
    layouts = [(item, layout) for item in items if (layout := _text(item.get("properTrackName")))]
    for _, layout in layouts:  # a layout name always leads to itself
        names[layout.lower()] = layout
    for item, layout in layouts:
        for field in ALIASES:
            alias = _text(item.get(field))
            if alias:
                names.setdefault(alias.lower(), layout)
        folder = _text(item.get("cmpName"))
        if folder and not _text(item.get("layoutName")):
            folders.setdefault(folder.lower(), set()).add(layout)
    for folder, found in folders.items():
        if len(found) == 1:
            names.setdefault(folder, found.pop())
    return names


def _fits(lost: str, name: str) -> bool:
    """Whether a name is the layout name whose lost characters (U+FFFD) it spells"""
    pattern = "".join("." if char == LOST else re.escape(char) for char in lost.casefold())
    return LOST not in name and re.fullmatch(pattern, name.casefold()) is not None


def layout_name(names: dict[str, str], *candidates: str, scene: str = "") -> str:
    """Layout name shown for the scene or first candidate the game list knows (layout, event or folder name),
    else first candidate cleaned (a scene name is never shown); "" if none given

    A layout name with characters lost by the game (U+FFFD) is replaced by a candidate spelling it (shared memory
    spells it right), else by the first unknown candidate without lost characters.
    """
    given = [name for name in (_text(candidate) for candidate in candidates) if name]
    for name in (_text(scene), *given):
        layout = names.get(name.lower()) or names.get(clean(name).lower()) if name else ""
        if not layout:
            continue
        if LOST not in layout:
            return layout
        spelled = next((other for other in given if _fits(layout, other)), "")
        return spelled or next((clean(other) for other in given
                                if LOST not in other and other.lower() not in names), layout)
    return next((clean(name) for name in given if LOST not in name), clean(given[0]) if given else "")
