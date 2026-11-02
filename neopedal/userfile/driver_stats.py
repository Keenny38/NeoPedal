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
Driver stats file function

Stats file is read, changed & saved by stats module (its thread) and driver stats viewer (page):
STATS_LOCK keeps each read-modify-save whole (session history file too).
"""

from __future__ import annotations

import copy
import json
import logging
import os
import shutil
import threading
from collections.abc import KeysView, Sequence
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from time import sleep
from typing import Any, get_type_hints

from ..const_common import MAX_SECONDS
from ..const_file import FileExt, StatsFile
from ..validator import convert_value_type, purge_data_key
from . import read_json
from .json_setting import (
    create_backup_file,
    create_versioned_backup,
    save_and_verify_json_file,
    save_json_file,
    set_backup_timestamp,
)

logger = logging.getLogger(__name__)

STATS_LOCK = threading.RLock()  # stats & session history files: one read-modify-save at a time
BACKUP_COUNT = 10  # automatic backups kept before viewer edits


@dataclass
class DriverStats:
    """Driver stats data

    Attributes:
        pb: personal best lap time.
        qb: qualifying best lap time.
        rb: race best lap time.
        meters: meters driven.
        seconds: seconds spent driving.
        liters: liters of fuel consumed.
        valid: valid laps.
        invalid: invalid laps.
        penalties: penalties recieved in race.
        races: number of races completed.
        wins: number of wins.
        podiums: number of podiums.
        starts: number of race starts (race session driven after green flag).
        dnf: number of races not finished or disqualified.
        positions: sum of finish positions (average finish = positions / placed).
        placed: number of finishes with recorded position.
    """

    pb: float = MAX_SECONDS
    qb: float = MAX_SECONDS
    rb: float = MAX_SECONDS
    meters: float = 0.0
    seconds: float = 0.0
    liters: float = 0.0
    valid: int = 0
    invalid: int = 0
    penalties: int = 0
    races: int = 0
    wins: int = 0
    podiums: int = 0
    starts: int = 0
    dnf: int = 0
    positions: int = 0
    placed: int = 0

    @classmethod
    def keys(cls) -> KeysView[str]:
        """Get key name list"""
        return cls.__annotations__.keys()

    @staticmethod
    def is_lap_time(key: str) -> bool:
        """Is lap time"""
        return key in ("pb", "qb", "rb")


def combined_stats(first: DriverStats, second: DriverStats) -> DriverStats:
    """Stats of two stints of a vehicle as one (stint not saved, added to the next one): counters added, best
    lap times kept"""
    values = {}
    for key, old in first.__dict__.items():
        new = getattr(second, key)
        values[key] = min(old, new) if DriverStats.is_lap_time(key) else old + new
    return DriverStats(**values)


def validate_stats_file(stats_user: dict) -> dict:
    """Validate stats file

    Full validation for every primary key (track name) and secondary key (vehicle name), and value
    type of every stat (text, null or bool replaced by number, default if not a number, NaN & infinity too).
    Only required for loading file in Driver Stats Viewer.
    """
    default_dict = DriverStats.__dict__
    default_type = get_type_hints(DriverStats)
    for key in stats_user:
        if not isinstance(stats_user[key], dict):
            stats_user[key] = {}
        sub_value = stats_user[key]
        for sub_key in sub_value:
            vehicle_stats = sub_value[sub_key]
            if not isinstance(vehicle_stats, dict):
                sub_value[sub_key] = {}
                continue
            for name, value in vehicle_stats.items():
                value_type = default_type.get(name)
                if value_type is not None and (isinstance(value, bool) or not isinstance(value, value_type)):
                    value = vehicle_stats[name] = convert_value_type(value, default_dict[name], value_type)
                if value_type is not None and isinstance(value, float) and not isfinite(value):
                    vehicle_stats[name] = default_dict[name]
    return stats_user


def stats_entry(stats_user: dict, path: Sequence[str]) -> Any:
    """Copy of stats value at path (track, vehicle, stat name), None if not found"""
    value: Any = stats_user
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return copy.deepcopy(value)


def set_stats_entry(stats_user: dict, path: Sequence[str], value: Any) -> None:
    """Set stats value at path (track, vehicle, stat name), parents created, removed if value is None"""
    if not path:
        return
    parent = stats_user
    for key in path[:-1]:
        parent = get_sub_dict(parent, key)
    if value is None:
        parent.pop(path[-1], None)
    else:
        parent[path[-1]] = copy.deepcopy(value)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def best_lap_time(*values: Any) -> float:
    """Fastest valid lap time of values, 0 if none"""
    times = [float(value) for value in values if is_number(value) and 0 < value < MAX_SECONDS]
    return min(times) if times else 0.0


def merge_vehicle_stats(current: dict, restored: dict) -> dict:
    """Restored vehicle stats (undo) merged with stats recorded since: counters added, best lap times kept"""
    merged = copy.deepcopy(current)
    for key, value in restored.items():
        old = merged.get(key)
        if DriverStats.is_lap_time(key):
            merged[key] = best_lap_time(old, value) or copy.deepcopy(value)
        elif is_number(value) and is_number(old):
            merged[key] = old + value
        elif key not in merged:
            merged[key] = copy.deepcopy(value)
    return merged


def stats_since(current: dict, saved: dict) -> dict:
    """Stats recorded since file held saved stats (whole files): counters increase, improved best lap times"""
    since: dict = {}
    for track, vehicles in current.items():
        saved_vehicles = saved.get(track)
        if not isinstance(vehicles, dict):
            continue
        for vehicle, stats in vehicles.items():
            old = saved_vehicles.get(vehicle) if isinstance(saved_vehicles, dict) else None
            if not isinstance(stats, dict):
                continue
            if not isinstance(old, dict):
                old = {}
            added = {}
            for key, value in stats.items():
                previous = old.get(key)
                if DriverStats.is_lap_time(key):
                    best = best_lap_time(value)
                    if best and best < (best_lap_time(previous) or MAX_SECONDS) - 0.0005:
                        added[key] = best
                elif is_number(value) and value > (previous if is_number(previous) else 0):
                    added[key] = value - (previous if is_number(previous) else 0)
            if added:
                since.setdefault(track, {})[vehicle] = added
    return since


def merge_stats_since(stats_user: dict, since: dict) -> dict:
    """Whole stats file (undo, redo, backup restored) with stats recorded since added (see stats_since)"""
    merged = copy.deepcopy(stats_user)
    for track, vehicles in since.items():
        merged_vehicles = get_sub_dict(merged, track)
        for vehicle, stats in vehicles.items():
            known = merged_vehicles.get(vehicle)
            merged_vehicles[vehicle] = (merge_vehicle_stats(known, stats) if isinstance(known, dict)
                                        else copy.deepcopy(stats))
    return merged


def redo_stats_entry(current: Any, before: Any, after: Any, path: Sequence[str]) -> Any:
    """Stats at path (track, vehicle or stat) of an edit applied again (redo, before: value the edit replaced),
    stats recorded since the edit kept: a track or vehicle removed again keeps the stints driven since"""
    if len(path) == 3:
        if not DriverStats.is_lap_time(path[-1]):
            return copy.deepcopy(after)
        best = best_lap_time(current)
        return best if best and best < (best_lap_time(before) or MAX_SECONDS) - 0.0005 else copy.deepcopy(after)
    if len(path) not in (1, 2) or not isinstance(current, dict):
        return copy.deepcopy(after)

    def wrap(value: Any) -> dict:
        """Vehicles of track (vehicle: as a track of one vehicle)"""
        if not isinstance(value, dict):
            return {}
        return value if len(path) == 1 else {"": value}

    since = stats_since({"": wrap(current)}, {"": wrap(before)}).get("", {})
    merged = merge_stats_since({"": wrap(after)}, {"": since})[""] if since else wrap(after)
    if len(path) == 2:
        return merged.get("")
    return merged or None


def merge_stats_entry(current: Any, restored: Any, path: Sequence[str]) -> Any:
    """Restored stats at path (track, vehicle or stat) merged with current stats there

    Current stats at a removed path were all recorded after removal: added to restored ones.
    """
    if restored is None:
        return copy.deepcopy(current)
    if current is None:
        return copy.deepcopy(restored)
    if len(path) == 1 and isinstance(current, dict) and isinstance(restored, dict):  # track
        merged = copy.deepcopy(current)
        for vehicle, stats in restored.items():
            if isinstance(merged.get(vehicle), dict) and isinstance(stats, dict):
                merged[vehicle] = merge_vehicle_stats(merged[vehicle], stats)
            elif vehicle not in merged:
                merged[vehicle] = copy.deepcopy(stats)
        return merged
    if len(path) == 2 and isinstance(current, dict) and isinstance(restored, dict):  # vehicle
        return merge_vehicle_stats(current, restored)
    if len(path) == 3 and DriverStats.is_lap_time(path[-1]):  # lap time: best kept
        return best_lap_time(current, restored) or copy.deepcopy(restored)
    return copy.deepcopy(restored)


def backup_prefix(filename: str = StatsFile.DRIVER) -> str:
    return f"{filename}{FileExt.STATS}{FileExt.BACKUP}-auto-"


HISTORY_BACKUP_PREFIX = "driver.history.backup-auto-"  # session history copied with a stats backup, same time


def backup_stats_file(filepath: str, filename: str = StatsFile.DRIVER, with_history: bool = False) -> bool:
    """Automatic backup of stats file before an edit (last BACKUP_COUNT kept), True if created

    Args:
        with_history: session history file copied too (edit changing it), named with the time of the stats
            backup (restored with it, see history_backup_path); copies of stats backups removed since deleted.
    """
    created = create_versioned_backup(f"{filename}{FileExt.STATS}", filepath, max_count=BACKUP_COUNT,
                                      min_interval=0)
    if with_history and created and filename == StatsFile.DRIVER:
        backups = list_stats_backups(filepath, filename)
        if backups:
            backup_history_file(filepath, backups[0][0][len(backup_prefix(filename)):])
    return created


def backup_history_file(filepath: str, stamp: str) -> None:
    """Session history copied for the stats backup of stamp, copies of stats backups no longer kept removed"""
    from .driver_history import HISTORY_FILE

    source = os.path.join(filepath, HISTORY_FILE)
    try:
        if os.path.exists(source):
            shutil.copyfile(source, os.path.join(filepath, f"{HISTORY_BACKUP_PREFIX}{stamp}"))
        stamps = {name[len(backup_prefix()):] for name, _ in list_stats_backups(filepath)}
        for name in os.listdir(filepath):
            if name.startswith(HISTORY_BACKUP_PREFIX) and name[len(HISTORY_BACKUP_PREFIX):] not in stamps:
                os.remove(os.path.join(filepath, name))
    except OSError as error:
        logger.error("USERDATA: unable to back up %s: %s", HISTORY_FILE, error)


def history_backup_path(filepath: str, name: str, filename: str = StatsFile.DRIVER) -> str:
    """Session history copied with stats backup name, empty if none"""
    if not name.startswith(backup_prefix(filename)) or os.path.basename(name) != name:
        return ""
    path = os.path.join(filepath, f"{HISTORY_BACKUP_PREFIX}{name[len(backup_prefix(filename)):]}")
    return path if os.path.isfile(path) else ""


def list_stats_backups(filepath: str, filename: str = StatsFile.DRIVER) -> list[tuple[str, float]]:
    """Automatic backups of stats file (name, creation time), newest first"""
    prefix = backup_prefix(filename)
    backups = []
    try:
        names = [name for name in os.listdir(filepath) if name.startswith(prefix)]
    except OSError:
        return []
    for name in names:
        try:  # timestamp in name: copy keeps modified time of stats file
            created = datetime.strptime(name[len(prefix):][:19], "%Y-%m-%d-%H-%M-%S").timestamp()
        except ValueError:
            continue
        backups.append((name, created))
    backups.sort(key=lambda backup: backup[0], reverse=True)
    return backups


def load_stats_backup(filepath: str, name: str, filename: str = StatsFile.DRIVER) -> dict | None:
    """Stats of an automatic backup, None if invalid"""
    if not name.startswith(backup_prefix(filename)) or os.path.basename(name) != name:
        return None
    return read_json(os.path.join(filepath, name), strict=False, dict_only=True)


def get_sub_dict(source: dict, key_name: str) -> dict:
    """Get sub dict, create new if not exist"""
    sub_dict = source.get(key_name)
    if not isinstance(sub_dict, dict):
        source[key_name] = {}
        sub_dict = source[key_name]
    return sub_dict


def load_driver_stats(
    key_list: tuple[str, str], filepath: str, filename: str = StatsFile.DRIVER
) -> DriverStats:
    """Load driver stats"""
    stats_user = load_stats_json_file(
        filepath=filepath,
        filename=filename,
    )
    if stats_user is None:
        return DriverStats()
    # Get data from matching key
    loaded_dict = stats_user
    for key in key_list:
        temp_dict = loaded_dict.get(key)
        if not isinstance(temp_dict, dict):  # not exist, set to default
            return DriverStats()
        loaded_dict = temp_dict
    # Add data to DriverStats, value of wrong type (null, text, bool) converted or reverted to default
    default_dict = DriverStats.__dict__
    default_type = get_type_hints(DriverStats)
    try:
        stats = purge_data_key(loaded_dict, DriverStats.keys())
        for key, value in stats.items():
            if isinstance(value, bool) or not isinstance(value, default_type[key]):
                value = stats[key] = convert_value_type(value, default_dict[key], default_type[key])
            # "nan", "inf" text or NaN/Infinity literal: a best (nan) never improved, default
            if isinstance(value, float) and not isfinite(value):
                stats[key] = default_dict[key]
        return DriverStats(**stats)
    except (AttributeError, TypeError, KeyError, ValueError):
        return DriverStats()


def save_driver_stats(
    key_list: tuple[str, str], stats_update: DriverStats, filepath: str, filename: str = StatsFile.DRIVER
) -> bool:
    """Save driver stats, True if saved (or nothing to save: invalid key name)

    File not accessible (held by antivirus or cloud sync): not saved, never reset (stats kept by caller).
    """
    if not key_list or not all(key_list):  # ignore invalid key name
        return True
    # Load stats with limited attempts, STATS_LOCK held from load to save (viewer edit not saved between)
    # but released while waiting to try again (viewer page never waits long)
    load_attempts = 10
    while load_attempts > 0:
        with STATS_LOCK:
            stats_user = load_stats_json_file(
                filepath=filepath,
                filename=filename,
                show_log=False,
            )
            if stats_user is not None:
                return add_driver_stats(stats_user, key_list, stats_update, filepath, filename)
        load_attempts -= 1
        logger.info("USERDATA: unable to load %s%s, %s attempt(s) left", filename, FileExt.STATS, load_attempts)
        sleep(0.05)
    # Create backup if failed to load stats
    with STATS_LOCK:
        stats_user = load_stats_json_file(filepath=filepath, filename=filename, show_log=False)
        if stats_user is None:  # still invalid (not saved by viewer meanwhile)
            if not is_invalid_stats_file(filepath, filename):  # held by another program: never reset
                logger.warning("USERDATA: %s%s not accessible, stats not saved", filename, FileExt.STATS)
                return False
            logger.info("USERDATA: unable to load %s%s, creating backup", filename, FileExt.STATS)
            if not create_backup_file(f"{filename}{FileExt.STATS}", filepath, set_backup_timestamp(), show_log=True):
                return False  # abort saving if failed to create backup
            stats_user = {}  # reset stats
        return add_driver_stats(stats_user, key_list, stats_update, filepath, filename)


def is_invalid_stats_file(
    filepath: str, filename: str = StatsFile.DRIVER, extension: str = FileExt.STATS
) -> bool:
    """File read but holds no stats (not a JSON object), False if missing or not accessible now (locked)"""
    try:
        with open(f"{filepath}{filename}{extension}", "rb") as file:
            data = file.read()
    except OSError:
        return False
    try:
        stats_user = json.loads(data.decode("utf-8-sig"))
    except (ValueError, RecursionError):  # UnicodeDecodeError is a ValueError
        return True
    return not isinstance(stats_user, dict)


def add_driver_stats(
    stats_user: dict, key_list: tuple[str, str], stats_update: DriverStats, filepath: str, filename: str
) -> bool:
    """Add stats to saved stats loaded (best lap times kept) & save, STATS_LOCK held, see save_driver_stats

    Returns:
        True if saved & verified.
    """
    # Get data from matching key
    loaded_dict = stats_user
    for key in key_list:
        loaded_dict = get_sub_dict(loaded_dict, key)
    # Verify and update new data
    default_dict = DriverStats.__dict__
    default_type = get_type_hints(DriverStats)
    for key, value in stats_update.__dict__.items():
        # Add new default value if not exists
        if key not in loaded_dict:
            loaded_dict[key] = default_dict[key]
        # Check value type, auto correct if mismatch
        if not isinstance(loaded_dict[key], default_type[key]):
            loaded_dict[key] = convert_value_type(loaded_dict[key], default_dict[key], default_type[key])
        # Reset NaN & infinity (json accepts them): never replaced by any new value otherwise
        if isinstance(loaded_dict[key], float) and not isfinite(loaded_dict[key]):
            loaded_dict[key] = default_dict[key]
        # Update laptime value faster than old value
        if DriverStats.is_lap_time(key):
            if loaded_dict[key] <= 0:  # reset invalid time
                loaded_dict[key] = MAX_SECONDS
            if loaded_dict[key] > value > 0:
                loaded_dict[key] = value
            continue
        # Update value (increment)
        loaded_dict[key] += value
    # Save new data
    return save_stats_json_file(
        stats_user=stats_user,
        filepath=filepath,
        filename=filename,
    )


def load_stats_json_file(
    filepath: str, filename: str = StatsFile.DRIVER, extension: str = FileExt.STATS, show_log: bool = True
) -> dict | None:
    """Load stats json file, create new if not exists, or returns "None" if invalid"""
    try:
        with open(f"{filepath}{filename}{extension}", encoding="utf-8-sig") as jsonfile:  # BOM if edited by user
            stats_user = json.load(jsonfile)
            if not isinstance(stats_user, dict):
                raise TypeError
            return stats_user
    except FileNotFoundError:
        if show_log:
            logger.info("MISSING: %s stats (%s) data, create new stats", filename, extension)
        stats_user = {}
        save_json_file(stats_user, filename, filepath, extension, compact_json=True)
        return stats_user
    except (AttributeError, TypeError, KeyError, ValueError, OSError, RecursionError):
        if show_log:
            logger.info("MISSING: invalid %s stats (%s) data", filename, extension)
    return None


def save_stats_json_file(
    stats_user: dict, filepath: str, filename: str = StatsFile.DRIVER, extension: str = FileExt.STATS
) -> bool:
    """Save stats to json file, True if saved & verified"""
    return save_and_verify_json_file(
        dict_user=stats_user,
        filename=f"{filename}{extension}",
        filepath=filepath,
        max_attempts=10,
        compact_json=True,
    )
