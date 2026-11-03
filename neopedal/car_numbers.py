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
Car number of every car (Le Mans Ultimate) as the game shows it, from the game Rest API

GET /rest/watch/standings: [{"slotID", "carNumber", ...}, ...], read every 5 seconds while a driver list
shows car numbers. Online, the server gives each car of a split its own number ("#1" to "#20"), whatever
its livery: shared memory only has the livery number in the vehicle name ("McLaren Custom Team 2026 #397"),
so nothing is shown while the game does not answer (rFactor 2, menus).
"""

from __future__ import annotations

from typing import Any

from .game_rest_poll import RoutePoller

ROUTE = "/rest/watch/standings"
CHECK_SECONDS = 5.0
# Body bytes read per second at most: ~1.5 KB per car, a full grid of 60 cars read every 7.5 seconds
CHECK_BYTES_PER_SECOND = 12_000
MAX_LENGTH = 4  # characters kept of a number ("007", "1234"): column sized for 3


def parse_numbers(data: Any) -> dict[int, str]:
    """Car number of each car slot, cars without number left out"""
    numbers: dict[int, str] = {}
    if not isinstance(data, list):
        return numbers
    for car in data:
        if not isinstance(car, dict):
            continue
        slot = car.get("slotID")
        number = car.get("carNumber")
        if not isinstance(slot, int) or isinstance(slot, bool) or isinstance(number, bool):
            continue
        if isinstance(number, int):
            number = str(number)
        if not isinstance(number, str):
            continue
        number = number.strip().lstrip("#").strip()[:MAX_LENGTH]
        if number:
            numbers[slot] = number
    return numbers


class CarNumbers(RoutePoller[dict[int, str]]):
    """Car numbers of cars of session, read in background (see RoutePoller)"""

    def __init__(self, fetch=None, clock=None):
        super().__init__(ROUTE, parse_numbers, {}, CHECK_SECONDS, fetch, clock, CHECK_BYTES_PER_SECOND)

    def number(self, slot: int) -> str:
        """Car number of car slot, empty if unknown"""
        return self.value.get(slot, "")


car_numbers = CarNumbers()
