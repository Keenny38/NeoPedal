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
Your laps on the track of an online race to come (Upcoming Races page): personal best & community level of each
class driven there, recorded laps folders, as the Driver Stats page tells them

Read in background from the Driver Stats files (stats, session history), the community lap times kept from the
last download and the recorded laps folders; tracks of RaceControl matched to stats tracks by the names the game
gives each track scene.
"""

from __future__ import annotations

from typing import Any, NamedTuple

from ...setting import cfg
from ...userfile import lap_reference
from ...userfile.lap_reference import LapReferenceTable
from .stats_analysis import scene_names, track_names
from .stats_common import GAME_TRACKS_AGE, class_prefix, combo_name, list_lap_folders, valid_laptime


class Best(NamedTuple):
    """Personal best of a class on a track"""

    vehicle_class: str
    vehicle: str  # driver stats vehicle key
    seconds: float
    level: int  # community level index (lap_reference.LEVELS), -1 if unknown
    laps_folder: str  # recorded laps folder of the track & class, "" if none


class PersonalData(NamedTuple):
    stats: dict  # driver stats: track -> vehicle -> values
    classes: dict[str, str]  # vehicle key -> game class
    last_driven: dict[str, float]  # track -> last session time
    references: LapReferenceTable
    names: dict[str, tuple[str, ...]]  # track scene (casefold) -> names the game gives it
    folders: frozenset[str]  # recorded laps folders


EMPTY = PersonalData({}, {}, {}, LapReferenceTable(), {}, frozenset())


def read_personal() -> PersonalData:
    """Driver stats, session history classes, community lap times, game track names & laps folders (worker)"""
    from ...game_rest_cache import rest_cache
    from ...userfile.driver_history import load_history, track_last_driven, vehicle_classes
    from ...userfile.driver_stats import STATS_LOCK, load_stats_json_file, validate_stats_file

    with STATS_LOCK:
        stats = load_stats_json_file(filepath=cfg.path.config)
        records = load_history(cfg.path.config)
    stats = validate_stats_file(stats) if stats is not None else {}
    text, _ = lap_reference.load_cache(cfg.path.config)
    references = lap_reference.parse_lap_references(text) if text else LapReferenceTable()
    names = track_names(rest_cache.json("/rest/race/track", GAME_TRACKS_AGE))
    return PersonalData(stats, vehicle_classes(records), track_last_driven(records), references, names,
                        frozenset(list_lap_folders()[1]))


def stats_track(data: PersonalData, track: str, scene: str) -> str:
    """Driver stats track of a RaceControl track ("" if never driven there): layout of its scene, else its own
    name"""
    wanted = scene_names(scene, data.names) | {track.casefold()}
    return next((key for key in data.stats if key and key.casefold() in wanted), "")


def bests_on(data: PersonalData, track: str, use_reference: bool = True) -> list[Best]:
    """Personal best of each class driven on a driver stats track (fastest vehicle of the class), class order"""
    vehicles = data.stats.get(track, {}) if track else {}
    found: dict[str, tuple[float, str]] = {}
    for vehicle, values in vehicles.items() if isinstance(vehicles, dict) else ():
        best = valid_laptime(values.get("pb", 0)) if isinstance(values, dict) else 0.0
        vehicle_class = data.classes.get(str(vehicle)) or class_prefix(str(vehicle))
        if best and (vehicle_class not in found or best < found[vehicle_class][0]):
            found[vehicle_class] = (best, str(vehicle))
    bests = []
    for vehicle_class, (best, vehicle) in sorted(found.items()):
        reference = data.references.find(track, vehicle, vehicle_class) if use_reference else None
        folder = combo_name(track, vehicle_class)
        bests.append(Best(vehicle_class, vehicle, best, reference.level(best) if reference else -1,
                          folder if folder in data.folders else ""))
    return bests


def personal_row(data: PersonalData, track: str, scene: str, level_color: Any, use_reference: bool = True) -> dict:
    """What the page shows of your laps on a race track: known (driven there), stats track, bests (class, time,
    level & its color & letter, vehicle, laps folder), last driven time"""
    from ...calculation import sec2laptime_full
    from .stats_common import level_letter, level_text

    key = stats_track(data, track, scene)
    bests = [{
        "vehicleClass": best.vehicle_class, "vehicle": best.vehicle, "best": sec2laptime_full(best.seconds),
        "seconds": best.seconds, "level": level_text(best.level) if best.level >= 0 else "",
        "letter": level_letter(best.level), "color": level_color(best.level), "lapsFolder": best.laps_folder,
    } for best in bests_on(data, key, use_reference)]
    return {"known": bool(key), "statsTrack": key, "bests": bests, "lastDriven": data.last_driven.get(key, 0.0)}
