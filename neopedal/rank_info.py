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
Player Driver Rank & Safety Rank (Le Mans Ultimate), shared by overlays, Home, Driver Stats & the Broadcast Director

Read from the game menu storage file of the game folder found like race results (folder chosen on race results
page, else Steam libraries), see process/driver_ranks.py: yours & your team members'. The game writes it less
often since 2026-10 (at game exit): the last ranks seen are kept with their date. Nothing is read online (RaceOS,
the online service of the game, is never asked: a developer of Le Mans Ultimate said third-party apps must not).
"""

from __future__ import annotations

import contextlib
import os
import re
from typing import NamedTuple

from .process import driver_ranks as dr
from .process import player_profile as pp
from .process import results_file as rf
from .setting import cfg

GAME = "LMU"  # only game with ranks
# Files of the former online reading (RaceOS, removed 2026-11-04) deleted from the config folder at start
FORMER_FILES = (".raceos_ranks.json", ".raceos_block.json", ".online_results.json", ".race_schedule.json")
_SUFFIX = re.compile(r"\s*#\d+\s*$")  # "#1234" the game adds to some names online


def locate() -> dr.Located:
    """Storage file of game folder, Steam ID & names of player (game profile)"""
    for folder in rf.results_folders(rf.chosen_results_folder(cfg.path.config)):
        if rf.game_of_path(folder) != GAME:
            continue
        accounts = pp.steam_accounts(rf.steam_folder())
        return dr.Located(os.path.join(rf.game_root(folder), dr.STORAGE_FILE),
                          accounts[0].steam_id if accounts else "", tuple(rf.profile_player_names(folder)),
                          tuple((account.steam_id, account.name, account.avatar) for account in accounts),
                          folder)
    return dr.Located("", "", ())


def history_path() -> str:
    return os.path.join(cfg.path.config, dr.HISTORY_FILE)


def remove_former_files(folder: str = "") -> list[str]:
    """Files of the former online reading removed from the config folder (sign in ranks, waits, RaceControl
    answers, online races with driver names), names removed"""
    folder = folder or cfg.path.config
    removed = []
    for name in FORMER_FILES:
        with contextlib.suppress(OSError):
            os.remove(os.path.join(folder, name))
            removed.append(name)
    return removed


def strip_suffix(name: str) -> str:
    """Driver name without "#1234" suffix the game adds online"""
    return _SUFFIX.sub("", name)


ranks = dr.RankWatcher(locate, lambda: history_path(), active_account=pp.active_steam_user)


def poll_ranks() -> None:
    """Player & team ranks read in background when due"""
    ranks.poll()


# Lookups of overlays (each row, each update) kept until ranks change: drivers list replaced whole when it changes
# (never changed in place), compared by identity & serial
MEMO_NAMES = 1024  # names kept at most (memo emptied beyond: names of many sessions while ranks never change)


class _Memo(NamedTuple):
    drivers: list[dr.DriverRanks]  # ranks.drivers when made
    serial: int  # ranks.serial when made
    ranks: dict[str, dr.DriverRanks | None]  # name -> ranks found


_memo = _Memo([], -1, {})


def _current_memo() -> _Memo:
    """Memo of current ranks, new one once they changed (any thread: replaced whole)"""
    global _memo
    drivers, serial = ranks.drivers, ranks.serial
    memo = _memo
    if memo.drivers is not drivers or memo.serial != serial:
        memo = _memo = _Memo(drivers, serial, {})
    return memo


def driver_ranks(name: str) -> dr.DriverRanks | None:
    """Ranks of a driver of session: player & team members (game menu file), None if unknown"""
    found_by_name = _current_memo().ranks
    try:
        return found_by_name[name]
    except KeyError:  # first lookup of name since ranks changed
        pass
    if len(found_by_name) >= MEMO_NAMES:
        found_by_name.clear()
    found = found_by_name[name] = ranks.find_name(strip_suffix(name))
    return found
