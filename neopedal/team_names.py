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
Team name of every car (Le Mans Ultimate), from the game Rest API, vehicle name otherwise

GET /rest/watch/standings: [{"slotID", "fullTeamName", ...}, ...], read every 10 seconds while a driver list
shows team names. Online cars with a custom livery are "<car> Custom Team <year> #<number>" in shared memory
(team chosen by the players only in fullTeamName); official liveries are "<team> <year> #<number>:<series>",
team then taken from the vehicle name until the game answers. Year & car number cut off both.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from .game_rest_poll import RoutePoller

ROUTE = "/rest/watch/standings"
CHECK_SECONDS = 10.0
# Body bytes read per second at most: ~1.5 KB per car, a full grid of 60 cars read every 10 seconds
CHECK_BYTES_PER_SECOND = 12_000
# Livery name ending: " 2025 #7:LM", " #10:ELMS2", " 2026 #397", " 2026" (year & number of the entry)
_ENTRY_SUFFIX = re.compile(r"(?:\s+(?:19|20)\d\d)?(?:\s+#\s*\w+(?::\w+)?)?\s*$")
_NUMBER_SUFFIX = re.compile(r"\s+#\s*\w+(?::\w+)?\s*$")
PLACEHOLDER = "custom team"  # game name of custom liveries with no team chosen


@lru_cache(maxsize=512)
def clean_team_name(name: str) -> str:
    """Team name without year & car number, empty for a custom livery without team"""
    team = _ENTRY_SUFFIX.sub("", name.strip()).strip()
    return "" if PLACEHOLDER in team.casefold() else team


@lru_cache(maxsize=512)
def team_of_vehicle(vehicle: str) -> str:
    """Team of a livery name ending with car number ("BMW M Team WRT 2025 #15:LM"), empty if none"""
    if not _NUMBER_SUFFIX.search(vehicle):
        return ""
    return clean_team_name(vehicle)


def parse_teams(data: Any) -> dict[int, str]:
    """Team name of each car slot, cars without team left out"""
    teams: dict[int, str] = {}
    if not isinstance(data, list):
        return teams
    for car in data:
        if not isinstance(car, dict):
            continue
        slot = car.get("slotID")
        name = car.get("fullTeamName")
        if not isinstance(slot, int) or isinstance(slot, bool) or not isinstance(name, str):
            continue
        team = clean_team_name(name)
        if team:
            teams[slot] = team
    return teams


class TeamNames(RoutePoller[dict[int, str]]):
    """Team names of cars of session, read in background (see RoutePoller)"""

    def __init__(self, fetch=None, clock=None):
        super().__init__(ROUTE, parse_teams, {}, CHECK_SECONDS, fetch, clock, CHECK_BYTES_PER_SECOND)

    def team(self, slot: int, vehicle: str) -> str:
        """Team of car slot, from its vehicle name while the game gave none"""
        return self.value.get(slot) or team_of_vehicle(vehicle)


team_names = TeamNames()
