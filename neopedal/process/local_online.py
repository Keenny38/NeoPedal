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
Your online races from the results files of the game (UserData/Log/Results), without RaceControl

Used by the Online list of Results & Replays when the online option (sign in with the game ticket) is off: race
sessions of the files whose <Setting> is Multiplayer, newest first, as online results (classification, lap times &
positions lap by lap). What only RaceControl knows is left out: Driver & Safety Rank changes and their reasons,
the kind of event (daily, weekly, championship: every race is listed with the daily races) and races driven on
another computer. Nothing is sent anywhere.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from collections.abc import Iterable

from . import race_schedule as rs
from . import results_file as rf

logger = logging.getLogger(__name__)

PREFIX = "local:"  # event id of a race read from a results file: "local:<path>"
SETTING_BYTES = 4096  # <Setting> comes first in a results file
_setting = re.compile(rb"<Setting>([^<]*)</Setting>")
_race_name = re.compile(r"R\d+\.xml$", re.I)  # "2026_11_03_14_42_57-81R1.xml": race session
_lock = threading.Lock()
_online: dict[str, tuple[int, int, bool]] = {}  # path: (modified ns, size, online race), read once per file
_player = ""  # your name in the last race read (online races are yours: the game marks your car)


def player_name() -> str:
    """Your driver name in the races read from the results files, "" before any"""
    return _player


def is_online_race(path: str) -> bool:
    """Race session of an online server (<Setting>Multiplayer</Setting>), header read once per file version"""
    if not _race_name.search(os.path.basename(path)):
        return False
    try:
        stat = os.stat(path)
    except OSError:
        return False
    with _lock:
        known = _online.get(path)
    if known is not None and known[:2] == (stat.st_mtime_ns, stat.st_size):
        return known[2]
    try:
        with open(path, "rb") as file:
            found = _setting.search(file.read(SETTING_BYTES))
    except OSError:
        return False
    online = found is not None and b"multiplayer" in found.group(1).lower()
    with _lock:
        if len(_online) > 5000:
            _online.clear()
        _online[path] = (stat.st_mtime_ns, stat.st_size, online)
    return online


def online_races(folders: Iterable[str]) -> list[str]:
    """Results files of your online races, newest first"""
    paths = [path for folder in folders for path in rf.results_files(folder)]
    paths.sort(key=os.path.basename, reverse=True)  # names start with the date
    return [path for path in paths if is_online_race(path)]


def _status(entry: rf.Entry) -> str:
    """Finish status as RaceControl tells it"""
    if entry.status.upper() == "FINISHED" or entry.status == "Finished Normally":
        return "Finished Normally"
    return entry.dnf_reason or entry.status or "DNF"


def online_result(result: rf.SessionResult, with_laps: bool = True) -> rs.OnlineResult:
    """Online result of a race session of a results file"""
    global _player
    rows = []
    for entry in result.entries:
        laps = entry.laps if with_laps else ()
        rows.append(rs.ResultRow(
            position=entry.position, class_position=entry.class_position, grid=entry.grid, name=entry.name,
            car=entry.car or entry.vehicle, vehicle_class=entry.car_class, number=entry.number, team=entry.team,
            best_lap=entry.best_lap, total=entry.finish_time, laps=entry.laps_completed, status=_status(entry),
            dr_change=None, sr_change=None, reasons=(),
            lap_times=tuple(lap.time for lap in laps), lap_positions=tuple(lap.position for lap in laps),
            drivers=tuple(dict.fromkeys(swap.driver for swap in entry.swaps)) or (entry.name,)))
        if entry.player:
            _player = entry.name
    title = result.server or result.track
    return rs.OnlineResult(f"{PREFIX}{result.path}", 1, result.time, "daily", "", title, result.track, tuple(rows))


def read_race(event_id: str, names: Iterable[str] = ()) -> rs.OnlineResult | None:
    """Race of a results file ("local:<path>") with its laps, None if not readable"""
    try:
        return online_result(rf.read_results(event_id.removeprefix(PREFIX), names, keep=False))
    except (OSError, ValueError) as error:
        logger.info("LOCAL ONLINE: race not read: %s", error)
        return None


def read_page(folders: Iterable[str], page: int, take: int, names: Iterable[str] = ()) -> list[rs.OnlineResult]:
    """Page of your online races (newest first), take per page; files not readable left out"""
    start = (max(page, 1) - 1) * take
    found = []
    for path in online_races(folders)[start:start + take]:
        try:
            found.append(online_result(rf.read_results(path, names, keep=False)))
        except (OSError, ValueError) as error:
            logger.info("LOCAL ONLINE: %s not read: %s", os.path.basename(path), error)
    return found
