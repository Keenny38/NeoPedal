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
Online races to come of Le Mans Ultimate & your online races, shared by Home, the Upcoming Races page, the race
reminders and Results & Replays

Races to come: daily races of the public home page of RaceControl (process/public_schedule.py, option
enable_public_race_schedule), as a web browser shows it: no game ticket, no account, nothing about the player
sent, at most every READ_SECONDS. Your online races: the results files of the game (process/local_online.py), no
request. Nothing is read from RaceOS (the online service of the game): a developer of Le Mans Ultimate said
third-party apps must not call it (2026-11-04).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import NamedTuple

from . import net_policy as policy
from .process import race_schedule as rs
from .setting import cfg

logger = logging.getLogger(__name__)

READ_SECONDS = policy.SCHEDULE_PUBLIC_SECONDS
RETRY_SECONDS = policy.SCHEDULE_RETRY_SECONDS
FORCE_SECONDS = policy.SCHEDULE_FORCE_SECONDS
GAME_LISTS_AGE = policy.SCHEDULE_GAME_LISTS_AGE
RESULTS_TAKE = 5  # your online races per page of the Online list (each one a whole results file)

# Status of last read
PUBLIC = "public"  # daily races of the public page read
OFF = "off"  # option enable_public_race_schedule off: nothing read
FAILED = "failed"  # public page not read (offline, error) or changed (no race found)


class State(NamedTuple):
    schedule: rs.Schedule
    status: str  # PUBLIC, OFF, FAILED, "" before any read
    tried: float  # monotonic time of last read try, -1 if none
    serial: int  # changed when schedule or status changed
    failures: int = 0  # reads in a row not read


_state = State(rs.EMPTY, "", -1.0, 0)
_lock = threading.Lock()  # one read at a time


def enabled() -> bool:
    """Daily races read from the public page of RaceControl (option enable_public_race_schedule)"""
    return bool(cfg.application.get("enable_public_race_schedule", True))


def state() -> State:
    """Last schedule read & status (any thread: replaced whole)"""
    return _state


def _set(schedule: rs.Schedule, status: str, tried: float, failures: int = 0) -> None:
    global _state
    old = _state
    serial = old.serial + (schedule is not old.schedule or status != old.status)
    _state = State(schedule, status, tried, serial, failures)


def due(now: float | None = None) -> bool:
    """Time to read again: never read, READ_SECONDS after a read (its starts cover hours), RETRY_SECONDS after a
    failed one, at once when the option was turned on or off"""
    current = _state
    now = time.monotonic() if now is None else now
    if current.tried < 0 or (current.status == OFF) == enabled():
        return True
    wait = RETRY_SECONDS if current.status == FAILED or current.failures else READ_SECONDS
    return now - current.tried >= wait


def read(force: bool = False) -> State:
    """Read the public page if due (force: now, never twice within FORCE_SECONDS), blocking (worker thread); state
    after it"""
    with _lock:
        now = time.monotonic()
        if force and _state.tried >= 0 and now - _state.tried < FORCE_SECONDS and (_state.status == OFF) != enabled():
            force = False  # asked again at once: read only when due
        if not force and not due(now):
            return _state
        if not enabled():
            _set(rs.EMPTY, OFF, now)
            return _state
        from .process import public_schedule

        found = public_schedule.read()
        if found is not None:  # scenes from the track catalog of the game (local, kept from before if closed)
            cars, tracks = _game_lists()
            found = public_schedule.with_game_lists(found, cars or _state.schedule.cars,
                                                    tracks or _state.schedule.tracks)
            old = _state.schedule  # a list page not read: the races of its last read kept
            found = found._replace(hosted=found.hosted if "hosted" not in found.missing else old.hosted,
                                   community=found.community if "community" not in found.missing else old.community)
            _set(found, PUBLIC, now)
        elif _state.status == PUBLIC:  # not read: races of the last read stay shown, tried again soon
            _set(_state.schedule, PUBLIC, now, _state.failures + 1)
        else:
            _set(_state.schedule, FAILED, now, _state.failures + 1)
        return _state


def _game_lists() -> tuple[dict[str, rs.CarInfo], dict[str, rs.TrackInfo]]:
    """Cars & tracks of the game (class, names & owned: local Rest API of the game), empty if not answered"""
    from .game_rest_cache import rest_cache

    return (rs.parse_car_catalog(rest_cache.json("/rest/race/car", GAME_LISTS_AGE)),
            rs.parse_track_catalog(rest_cache.json("/rest/race/track", GAME_LISTS_AGE)))


# Your online races: results files of the game
class ResultsPage(list[rs.OnlineResult]):
    """Online races of a page & files of the page (a file may be unreadable: last page when fewer than
    RESULTS_TAKE files)"""

    answered = 0


def read_results(page: int = 1) -> ResultsPage:
    """Page of your online races (newest first) from the results files of the game"""
    from .process import local_online

    races, answered = local_online.read_page(_local_folders(), max(page, 1), RESULTS_TAKE, _local_names())
    found = ResultsPage(races)
    found.answered = answered
    return found


def read_result(path: str) -> rs.OnlineResult | None:
    """One of your online races with its laps (results file), None if not readable"""
    from .process import local_online

    return local_online.read_race(path, _local_names())


def player_name() -> str:
    """Your driver name in the results files of the game, "" before any race read"""
    from .process import local_online

    return local_online.player_name()


def _local_folders() -> tuple[str, ...]:
    from .process.driver_history import results_folders

    return results_folders()


def _local_names() -> tuple[str, ...]:
    """Player names of the game profiles (your car marked in the results files)"""
    from .process.results_index import player_names

    names: dict[str, None] = {}
    for found in player_names(_local_folders()).values():
        names.update(dict.fromkeys(found))
    return tuple(names)
