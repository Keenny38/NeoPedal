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
Driver stats completed from a mysimrace.com data export (no Qt: worker thread)

The export (JSON, `temps_au_tour`) lists laps of Le Mans Ultimate: lap & sector times (ms), track, car, class,
session type, local time the lap ended. Laps are valid timed laps only (checked on LMU results files of the same
sessions: each lap found as a timed lap). Laps in a row of one track, car & session type make a session, added as
history record & stats as results_import does (apply_import).

Never counted twice: a session with a history record (stint end) while it ran or after it (before the next
session), or inside a session of an LMU results file (imported from results instead: better data), is left out.

The export lacks invalid laps, race results (position, finish), fuel and road conditions: left unknown. Distance
is laps x track length of an LMU results file of the track, 0 if none.
"""

from __future__ import annotations

import json
import logging
import math
from bisect import bisect_left
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import NamedTuple

from ..const_common import MAX_LAPTIME
from ..userfile.driver_history import SessionRecord, parse_record, record_line, session_record
from ..userfile.driver_stats import DriverStats
from . import results_file as rf
from . import results_index as ri
from .results_import import ImportedSession, lmu_brand

logger = logging.getLogger(__name__)

LAPS_KEY = "temps_au_tour"
MAX_FILE_BYTES = 64 * 1024 * 1024  # an export of years of laps is a few MB
SESSION_GAP = 30 * 60.0  # s between laps of one session at most (pit stops, driver swaps)
HISTORY_AFTER = 30 * 60.0  # s, history record (stint end) after the last lap of a session: same session
RESULTS_MARGIN = 60.0  # s around a session of a results file
SESSIONS = {"Practice": 1, "Qualifying": 2, "Qualify": 2, "Warmup": 3, "Race": 4}
# mysimrace class -> LMU class name: other classes (another game) left out
CLASSES = {"Hypercar": "Hyper", "Hyper": "Hyper", "LMP2": "LMP2", "LMP2_ELMS": "LMP2_ELMS", "LMP3": "LMP3",
           "GT3": "GT3", "GTE": "GTE"}
# mysimrace track name -> LMU layout name (driver stats key, results <TrackCourse>), others the same
TRACKS = {
    "Circuit de la Sarthe (24H)": "Circuit de la Sarthe",
    "Circuit de Barcelona-Catalunya": "Circuit de Barcelona",
    "Daytona International Speedway": "Daytona International Speedway Road Course",
    "Streets of Long Beach Circuit": "Grand Prix of Long Beach",
    "Paul Ricard - Layout 1A V2 Short": "Paul Ricard - 1A-V2-Short",
}
COMPOUND_LENGTH = 12  # longest compound name kept ("Intermediate"): export also holds garbage bytes


class ExportLap(NamedTuple):
    """Lap of a mysimrace export"""

    end: float  # lap end (Unix time)
    laptime: float  # s
    track: str  # mysimrace track name
    car: str  # car model ("Ferrari 499P")
    car_class: str  # LMU class name
    session: int  # driver history session type
    compound: str  # "" if unknown


@dataclass(frozen=True)
class ExportSessions:
    """Sessions of an export ready to add, counts of what was left out"""

    sessions: tuple[ImportedSession, ...]
    recorded: int  # sessions already in history
    in_results: int  # sessions of an LMU results file (import from results)


def parse_time(text: object) -> float:
    """Unix time of export local time text ("2026-10-03 17:57:05"), 0 if invalid"""
    if not isinstance(text, str):
        return 0.0
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%d %H:%M:%S").timestamp()
    except (ValueError, OverflowError, OSError):
        return 0.0


def clean_compound(value: object) -> str:
    """Compound name ("Medium"), "" if none or garbage"""
    if not isinstance(value, str):
        return ""
    value = value.strip()
    return value if 0 < len(value) <= COMPOUND_LENGTH and value.isascii() and value.isalpha() else ""


def parse_lap(data: object) -> ExportLap | None:
    """Lap of export, None if invalid or not a lap of LMU"""
    if not isinstance(data, dict):
        return None
    laptime_ms = data.get("lap_time_ms")
    if isinstance(laptime_ms, bool) or not isinstance(laptime_ms, (int, float)) or not math.isfinite(laptime_ms):
        return None
    laptime = laptime_ms / 1000
    end = parse_time(data.get("recorded_at"))
    track, car, car_class = (data.get(name) for name in ("track_name", "car_name", "car_class"))
    if not 0 < laptime < MAX_LAPTIME or end <= 0 or not isinstance(track, str) or not isinstance(car, str):
        return None
    game_class = CLASSES.get(car_class) if isinstance(car_class, str) else None
    if game_class is None or not track.strip() or not car.strip():
        return None
    session_type = data.get("session_type")
    session = SESSIONS.get(session_type, 1) if isinstance(session_type, str) else 1
    return ExportLap(end, laptime, track.strip(), car.strip(), game_class, session,
                     clean_compound(data.get("tire_compound")))


def read_export(path: str) -> tuple[list[ExportLap], int]:
    """Laps of a mysimrace export file & laps left out (invalid, another game)

    Raises:
        OSError: file not read.
        ValueError: not a mysimrace export, or no lap of LMU in it.
    """
    with open(path, "rb") as file:
        data = file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("file too big")
    try:  # compound names hold bytes that are not UTF-8 (garbage of the export)
        export = json.loads(data.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, RecursionError) as error:
        raise ValueError("not JSON") from error
    entries = export.get(LAPS_KEY) if isinstance(export, dict) else None
    if not isinstance(entries, list):
        raise ValueError("not a mysimrace export")
    laps = [lap for lap in map(parse_lap, entries) if lap is not None]
    if not laps:
        raise ValueError("no lap of Le Mans Ultimate")
    return laps, len(entries) - len(laps)


def group_sessions(laps: Iterable[ExportLap]) -> list[list[ExportLap]]:
    """Laps in a row of one track, car & session type, less than SESSION_GAP apart (oldest first)"""
    groups: list[list[ExportLap]] = []
    for lap in sorted(laps, key=lambda lap: lap.end):
        if groups:
            last = groups[-1][-1]
            if ((lap.track, lap.car, lap.session) == (last.track, last.car, last.session)
                    and lap.end - last.end <= SESSION_GAP + lap.laptime):
                groups[-1].append(lap)
                continue
        groups.append([lap])
    return groups


def track_key(name: str, known: Mapping[str, str]) -> str:
    """Driver stats track key of mysimrace track name (known: stats keys by lower case name)"""
    name = TRACKS.get(name, name)
    return known.get(name.casefold(), name)


def vehicle_key(lap: ExportLap, classification: str, known: Mapping[str, str], brands: Iterable[str]) -> str:
    """Driver stats vehicle key of lap car (see module_stats.stats_keys), spelt as a key already used or a brand
    of brands preset ("ORECA" -> "Oreca"); vehicle name unknown in export: car model instead"""
    if classification == "Class":
        key = lap.car_class
    elif classification == "Class - Brand":
        brand = lmu_brand(lap.car)
        brand = next((name for name in brands if name.casefold() == brand.casefold()), brand)
        key = f"{lap.car_class} - {brand}" if brand else lap.car_class
    else:
        key = lap.car
    return known.get(key.casefold(), key)


def track_lengths(summaries: Iterable[ri.ResultSummary], tracks: Iterable[str]) -> dict[str, float]:
    """Track length (m) of tracks from an LMU results file of each (one file read per track)"""
    wanted = {track.casefold() for track in tracks}
    lengths: dict[str, float] = {}
    for summary in summaries:
        name = (summary.course or summary.track).casefold()
        if summary.game != "LMU" or name not in wanted or name in lengths:
            continue
        try:
            length = rf.read_results(summary.path, (), keep=False).track_length
        except (OSError, ValueError) as error:
            logger.debug("MYSIMRACE IMPORT: %s not read: %s", summary.path, error)
            continue
        if length > 0:
            lengths[name] = length
    return lengths


def export_session(laps: Sequence[ExportLap], track: str, vehicle: str, length: float) -> tuple[SessionRecord,
                                                                                                DriverStats]:
    """History record & stats of a session of export laps"""
    best_lap = min(laps, key=lambda lap: lap.laptime)
    session = laps[0].session
    stats = DriverStats(valid=len(laps), seconds=round(sum(lap.laptime for lap in laps), 3),
                        meters=round(len(laps) * max(length, 0.0), 1))
    stats.pb = best_lap.laptime
    if session == 2:
        stats.qb = best_lap.laptime
    elif session == 4:
        stats.rb = best_lap.laptime
    record = session_record(
        track=track, vehicle=vehicle, session=session, best=best_lap.laptime, valid=stats.valid, invalid=0,
        meters=stats.meters, seconds=stats.seconds, position=0, finish=0, time=laps[-1].end,
        vehicle_class=laps[0].car_class, compound=best_lap.compound,
    )
    saved = parse_record(json.loads(record_line(record)))  # as read back from file: undo finds it there
    return saved if saved is not None else record, stats


def export_sessions(laps: Iterable[ExportLap], path: str, stats_user: Mapping, records: Sequence[SessionRecord],
                    summaries: Sequence[ri.ResultSummary], classification: str, brands: Iterable[str],
                    lengths: Mapping[str, float] | None = None) -> ExportSessions:
    """Sessions of export laps never recorded, as history records & stats (add with results_import.apply_import)

    Args:
        stats_user: driver stats file content (keys spelt as already used).
        records: session history.
        summaries: LMU results files (sessions left to import from results).
        brands: brand names of brands preset.
        lengths: track length (m) by lower case track key, read from results files if None.
    """
    known_tracks = {str(track).casefold(): str(track) for track in stats_user}
    known_tracks.update((record.track.casefold(), record.track) for record in records)
    known_vehicles = {str(vehicle).casefold(): str(vehicle) for vehicles in stats_user.values()
                      if isinstance(vehicles, dict) for vehicle in vehicles}
    known_vehicles.update((record.vehicle.casefold(), record.vehicle) for record in records)
    brands = tuple(dict.fromkeys(brand for brand in brands if isinstance(brand, str) and brand))
    groups = group_sessions(laps)
    if lengths is None:
        lengths = track_lengths(summaries, {track_key(group[0].track, known_tracks) for group in groups})
    stint_ends = sorted(record.time for record in records)
    windows = [(summary.start - RESULTS_MARGIN, summary.end + RESULTS_MARGIN) for summary in summaries
               if summary.game == "LMU" and summary.start > 0]
    sessions = []
    recorded = in_results = 0
    starts = [group[0].end - group[0].laptime for group in groups]
    for number, group in enumerate(groups):
        start, end = starts[number], group[-1].end
        # Stint end of session: after its last lap, before the next session (its own stint end comes later)
        latest = end + HISTORY_AFTER
        if number + 1 < len(groups):
            latest = max(min(latest, starts[number + 1]), end)
        index = bisect_left(stint_ends, start - RESULTS_MARGIN)
        if index < len(stint_ends) and stint_ends[index] <= latest:
            recorded += 1
            continue
        if any(first <= end and start <= last for first, last in windows):
            in_results += 1
            continue
        track = track_key(group[0].track, known_tracks)
        vehicle = vehicle_key(group[0], classification, known_vehicles, brands)
        record, stats = export_session(group, track, vehicle, lengths.get(track.casefold(), 0.0))
        sessions.append(ImportedSession(path, record, stats))
    return ExportSessions(tuple(sessions), recorded, in_results)
