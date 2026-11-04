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
Nationality of the drivers of a session (country code as given: "FR"), without Qt

Player: game profile ("Nationality" of UserData/player/Settings.JSON, read on its own thread). Other drivers
of an online server: the nationality the game gives for them (local Rest API, /rest/multiplayer/teams).
Drivers without either (AI, offline): real drivers whose names LMU gives its AI, from FIA WEC, Le Mans & ELMS
entry lists (data/driver_nations.json), matched by name without accents, dots, case or "Jr." suffixes.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import re
import threading
import time
import unicodedata

from .validator import NAME_CUT_BYTES

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "driver_nations.json")
PLAYER_SECONDS = 300.0  # game profile read again this late (nationality changed in game menus)
TEAMS_ROUTE = "/rest/multiplayer/teams"  # game Rest API, online server: drivers {name: {nationality, teamName...}}
TEAMS_SECONDS = 30.0  # asked again this late while overlays ask nationalities (local request, null when not online)
# Letters NFKD leaves alone (no combining accent)
PLAIN_LETTERS = str.maketrans({"\u0131": "i", "ł": "l", "ø": "o", "đ": "d", "ß": "ss", "æ": "ae", "œ": "oe", "-": " ",
                               ".": " ", "'": "", "\u2019": ""})  # dotless i, right single quote
SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}
_ONLINE_SUFFIX = re.compile(r"\s*#\d+\s*$")  # "#1234" the game adds to online names

logger = logging.getLogger(__name__)


def name_key(name: str) -> str:
    """Driver name compared: no accents, dots, case, "Jr." / "III" suffix; initials joined ("P. J. Hyett" ->
    "pj hyett")"""
    text = unicodedata.normalize("NFKD", _ONLINE_SUFFIX.sub("", name).casefold())
    words = "".join(char for char in text if not unicodedata.combining(char)).translate(PLAIN_LETTERS).split()
    while len(words) > 2 and words[-1] in SUFFIXES:
        words.pop()
    joined: list[str] = []
    initials = False  # last word made of single letters
    for word in words:  # single letters (initials) joined into one word
        if len(word) == 1 and initials:
            joined[-1] += word
        else:
            joined.append(word)
            initials = len(word) == 1
    return " ".join(joined)


@functools.cache
def known_drivers() -> dict[str, str]:
    """Real drivers' nationality by name key, empty if data file missing"""
    try:
        with open(DATA_FILE, encoding="utf-8") as file:
            drivers = json.load(file)["drivers"]
        return {name_key(name): code for name, code in drivers.items() if isinstance(code, str)}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        logger.warning("DRIVER NATIONS: not read: %s", DATA_FILE)
        return {}


@functools.lru_cache(maxsize=1024)
def known_nationality(name: str) -> str:
    """Nationality of a real driver of WEC / ELMS entry lists, "" if unknown or several match

    Names as shared memory gives them: an accent not decoded (game encoding unlike the one set) matches any letter,
    a name cut by the game name field (31 bytes) matches the names it starts.
    """
    if not name:
        return ""
    drivers = known_drivers()
    key = name_key(name.rstrip("�"))  # character cut in half dropped
    code = drivers.get(key)
    if code is not None:
        return code
    cut = len(name.encode("utf-8")) >= NAME_CUT_BYTES
    if "�" not in key and not cut:
        return ""
    pattern = re.compile(".".join(re.escape(part) for part in key.split("�")) + ("" if cut else "$"))
    found = {code for known, code in drivers.items() if pattern.match(known)}
    return found.pop() if len(found) == 1 else ""


class PlayerNation:
    """Player nationality of game profile, read on its own thread when due ("" meanwhile & if unknown)"""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._code = ""
        self._read_at: float | None = None
        self._busy = False

    def code(self) -> str:
        now = self._clock()
        if not self._busy and (self._read_at is None or now - self._read_at >= PLAYER_SECONDS):
            self._busy = True
            self._read_at = now
            threading.Thread(target=self._read, name="player nation", daemon=True).start()
        return self._code

    def _read(self) -> None:
        try:
            self._code = read_player_code()
        except Exception:  # any error of files: read again later
            logger.exception("DRIVER NATIONS: game profile not read")
        finally:
            self._busy = False


def read_player_code() -> str:
    """Nationality of game profile of the game folder found like race results, "" if none"""
    from .process import player_profile as pp
    from .process import results_file as rf
    from .setting import cfg

    for folder in rf.results_folders(rf.chosen_results_folder(cfg.path.config)):
        profile = pp.read_profile(rf.game_root(folder))
        if profile is not None and profile.nationality:
            return profile.nationality
    return ""


player_nation = PlayerNation()


def team_values(data: object, field: str, depth: int = 0) -> dict[str, str]:
    """Driver name key -> value of field ("nationality", "badge") of the answer of TEAMS_ROUTE (every "drivers"
    mapping found, any depth), "none" & empty values left out"""
    found: dict[str, str] = {}
    if depth > 8:
        return found
    if isinstance(data, dict):
        drivers = data.get("drivers")
        if isinstance(drivers, dict):
            for name, driver in drivers.items():
                value = driver.get(field) if isinstance(driver, dict) else None
                if isinstance(name, str) and isinstance(value, str) and value.strip().lower() not in ("", "none"):
                    found[name_key(name)] = value.strip()
        for value in data.values():
            if isinstance(value, (dict, list)):
                found.update(team_values(value, field, depth + 1))
    elif isinstance(data, list):
        for value in data:
            found.update(team_values(value, field, depth + 1))
    return found


def team_nationalities(data: object) -> dict[str, str]:
    """Driver name key -> nationality of the answer of TEAMS_ROUTE"""
    return team_values(data, "nationality")


class TeamNations:
    """Nationalities & badges the game gives for the drivers of an online server (local Rest API, no RaceControl),
    read on its own thread when due (empty meanwhile, outside online servers & if the game gives none)"""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._codes: dict[str, str] = {}
        self._badges: dict[str, str] = {}
        self._read_at: float | None = None
        self._busy = False

    def _due(self) -> None:
        now = self._clock()
        if not self._busy and (self._read_at is None or now - self._read_at >= TEAMS_SECONDS):
            self._busy = True
            self._read_at = now
            threading.Thread(target=self._read, name="team nations", daemon=True).start()

    def code(self, name: str) -> str:
        self._due()
        return self._codes.get(name_key(name), "")

    def badge(self, name: str) -> str:
        """Game badge of a driver of the online server ("" if none told)"""
        self._due()
        return self._badges.get(name_key(name), "")

    def _read(self) -> None:
        try:
            from .game_rest_cache import rest_cache

            answer = rest_cache.json(TEAMS_ROUTE, TEAMS_SECONDS)
            self._codes, self._badges = team_nationalities(answer), team_values(answer, "badge")
        except Exception:  # any error of the game: read again later
            logger.exception("DRIVER NATIONS: online teams not read")
        finally:
            self._busy = False


team_nations = TeamNations()


def nationality(name: str, player: bool) -> str:
    """Nationality of a driver of session: game profile (player), RaceControl profile (online), real driver of
    the same name (AI), "" if unknown"""
    if player:
        code = player_nation.code()
        if code:
            return code
    from .rank_info import driver_ranks

    found = driver_ranks(name)
    if found is not None and found.nationality:
        return found.nationality
    code = team_nations.code(name)  # online server: the game tells (no RaceControl needed)
    if code:
        return code
    return known_nationality(name)
