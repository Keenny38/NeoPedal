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
Driver stats completed from game results files (no Qt: worker thread)

Sessions the stats module never recorded (driven before NeoPedal was installed, module off) are found in the
results files the game keeps (LMU: UserData/Log/Results) and added as session history records & stats of their
track & vehicle, keys made as the stats module makes them (see module_stats.stats_keys).

Never counted twice: a session linked to a history record, or with a stint recorded on its track while it ran
(link missed), is left out; so is a session older than the session history of a track & vehicle whose stats
count laps the history doesn't (stats recorded before session history existed may count it already).

Results files lack what only live data gives: fuel (fraction of tank in files), road wetness & track
temperature, distance off the racing line (laps x track length).
"""

from __future__ import annotations

import json
import logging
import os
from bisect import bisect_left
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict
from typing import NamedTuple

from ..regex_pattern import rex_lmu_brand_extract
from ..userfile.driver_history import SessionRecord, parse_record, record_line, session_record, worth_recording
from ..userfile.driver_stats import DriverStats, get_sub_dict, merge_vehicle_stats
from . import results_file as rf
from . import results_index as ri
from .results_file import Entry, Lap, SessionResult

logger = logging.getLogger(__name__)

IMPORT_GAMES = ("LMU",)  # lap entries of results files checked on LMU files only
HISTORY_SESSION = {"Practice": 1, "Qualifying": 2, "Warmup": 3, "Race": 4}
FINISH_STATE = {rf.FINISHED: 1, "DNF": 2, "DQ": 3}
MAX_LAP_RATIO = 2.0  # lap time over twice the usual lap time: not a lap time (joined late, time spent capped)
IN_LAP = 0.5  # part of usual lap driven on a lap back to garage without sector time (time & distance)
HALF_LAP = 0.5  # lap without time shorter than this part of usual lap time: not completed (back to garage)
LAP_SPEED = 50.0  # m/s: usual lap time from track length when no car set a lap time


class ImportedSession(NamedTuple):
    """Session of a results file as the stats module would have recorded it"""

    path: str
    record: SessionRecord
    stats: DriverStats


def lmu_brand(car: str) -> str:
    """Brand of LMU car model ("Ferrari 499P" -> "Ferrari"), as brands preset fills it (brands.py)"""
    match = rex_lmu_brand_extract.search(car)
    return match.group().strip() if match is not None else ""


def stats_track_key(summary: ri.ResultSummary) -> str:
    """Driver stats track key of session: game track name (layout), else event name"""
    return summary.course or summary.track


def stats_vehicle_key(summary: ri.ResultSummary, classification: str, brands: Mapping[str, str]) -> str:
    """Driver stats vehicle key of player car (see module_stats.stats_keys), "" if class unknown"""
    if classification == "Class":
        return summary.car_class
    if classification == "Class - Brand":
        if not summary.car_class:
            return ""
        brand = brands.get(summary.vehicle) or lmu_brand(summary.car)
        return f"{summary.car_class} - {brand}" if brand else summary.car_class
    return summary.vehicle


def own_laps(entry: Entry, drivers: set[str]) -> list[Lap]:
    """Laps driven by player (laps of teammates left out in team races)"""
    teammates = [swap for swap in entry.swaps if swap.driver not in drivers]
    if not teammates:
        return list(entry.laps)
    own = [swap for swap in entry.swaps if swap.driver in drivers]
    return [lap for lap in entry.laps if any(swap.start_lap <= lap.number <= swap.end_lap for swap in own)]


def reference_lap(result: SessionResult) -> float:
    """Usual lap time of session (s): median best lap of cars (player best lap may be wrong: session joined
    late), else from track length (no lap timed), 0 if unknown"""
    bests = sorted(entry.best_lap for entry in result.entries if entry.best_lap > 0)
    if bests:
        return bests[len(bests) // 2]
    return max(result.track_length, 0.0) / LAP_SPEED


class LapCounts(NamedTuple):
    """Laps of a session as the stats module counts them (see module_stats): valid & invalid laps completed,
    time spent, laps driven (partial laps as fractions, distance = laps x track length)"""

    valid: int
    invalid: int
    seconds: float
    laps: float
    best: Lap | None


def count_laps(entry: Entry, laps: Iterable[Lap], reference: float) -> LapCounts:
    """Laps of results file sorted as the stats module sees them

    Lap entries of LMU results: a lap without start time (lap 1 started in garage) or without sector time is an
    out lap (sector timing starts at the line), a timed lap is valid, a lap without time followed by another lap
    is completed & invalid (track limits: last sectors missing; race start lap), unless shorter than half a lap
    (back to garage, out again), a lap followed by none is left on track (garage, session end). A lap time far
    over the usual lap time (session joined late) is not a lap time: lap counted invalid, time spent capped.
    """
    laps = list(laps)
    starts = {lap.number: lap.start for lap in laps if lap.start >= 0}
    valid = invalid = 0
    seconds = driven = 0.0
    best = None
    longest = reference * MAX_LAP_RATIO if reference > 0 else 0.0
    for lap in laps:
        timed = sum(sector for sector in lap.sectors if sector > 0)
        following = starts.get(lap.number + 1, -1.0)
        spent = following - lap.start if lap.start >= 0 and following > lap.start else 0.0  # 0 if unknown
        if longest:
            spent = min(spent, longest)
        if lap.time > 0 and (not longest or lap.time <= longest):
            valid += 1
            seconds += lap.time
            driven += 1
            if best is None or lap.time < best.time:
                best = lap
        elif lap.start < 0 or not timed:  # out lap: line reached (next lap), else back to garage
            if lap.number + 1 in starts:
                part = min(spent, reference) if spent else reference
            else:
                part = reference * IN_LAP if lap.start >= 0 else 0.0
            seconds += part
            driven += part / reference if reference else 0.0
        elif spent and spent >= reference * HALF_LAP:  # completed, invalid
            invalid += not lap.pit  # invalid pit laps never counted (stats module)
            seconds += spent
            driven += 1
        else:  # left on track
            seconds += spent or timed
            driven += min(sum(sector > 0 for sector in lap.sectors) / len(lap.sectors), 1.0)
    return LapCounts(valid, invalid, round(seconds, 3), driven, best)


def import_session(result: SessionResult, summary: ri.ResultSummary, names: Iterable[str], classification: str,
                   brands: Mapping[str, str], podium_by_class: bool) -> ImportedSession | None:
    """Session of player as history record & stats, None if not worth recording (no lap, keys unknown)"""
    entry = result.player_entry
    session = HISTORY_SESSION.get(summary.kind)
    track = stats_track_key(summary)
    vehicle = stats_vehicle_key(summary, classification, brands)
    if entry is None or session is None or not track or not vehicle:
        return None
    counts = count_laps(entry, own_laps(entry, ri.own_drivers(entry, names)), reference_lap(result))
    stats = DriverStats(
        valid=counts.valid, invalid=counts.invalid, seconds=counts.seconds,
        meters=round(counts.laps * max(result.track_length, 0.0), 1),
    )
    if not worth_recording(stats.valid, stats.invalid, stats.seconds):
        return None
    best_lap = counts.best
    if best_lap is not None:
        stats.pb = best_lap.time
        if summary.kind == "Qualifying":
            stats.qb = best_lap.time
        elif summary.kind == "Race":
            stats.rb = best_lap.time
    position = start = finish = 0
    if summary.kind == "Race":
        stats.penalties = summary.penalties
        stats.starts = 1
        finish = FINISH_STATE.get(summary.status, 0)
        start = summary.class_grid if podium_by_class else summary.grid
        if finish == 1:
            position = summary.class_position if podium_by_class else summary.position
            stats.races = 1
            if position > 0:
                stats.positions, stats.placed = position, 1
                stats.wins = int(position == 1)
                stats.podiums = int(position <= 3)
        elif finish in (2, 3):
            stats.dnf = 1
    record = session_record(
        track=track, vehicle=vehicle, session=session, best=best_lap.time if best_lap is not None else 0.0,
        valid=stats.valid, invalid=stats.invalid, meters=stats.meters, seconds=stats.seconds,
        position=position, finish=finish, time=summary.end, vehicle_class=summary.car_class,
        game_version=summary.game_version, compound=best_lap.compound if best_lap is not None else "",
        start_position=start, online=int(summary.setting == "Multiplayer") if summary.setting else -1,
    )
    saved = parse_record(json.loads(record_line(record)))  # as read back from file: undo finds it there
    return ImportedSession(summary.path, saved if saved is not None else record, stats)


def counted_before_history(stats_user: dict, records: Iterable[SessionRecord]) -> set[tuple[str, str]]:
    """Track & vehicle whose stats count more laps than their session history (stats recorded before session
    history existed)"""
    laps: dict[tuple[str, str], int] = {}
    for record in records:
        key = (record.track, record.vehicle)
        laps[key] = laps.get(key, 0) + record.valid + record.invalid
    found = set()
    for track, vehicles in stats_user.items():
        if not isinstance(vehicles, dict):
            continue
        for vehicle, data in vehicles.items():
            if not isinstance(data, dict):
                continue
            counted = sum(value for name in ("valid", "invalid")
                          if isinstance(value := data.get(name, 0), int) and not isinstance(value, bool))
            if counted > laps.get((track, str(vehicle)), 0):
                found.add((track, str(vehicle)))
    return found


def import_candidates(summaries: Iterable[ri.ResultSummary], records: Sequence[SessionRecord],
                      linked: Iterable[str], checkpoints: Iterable[tuple[str, float]] = ()) -> list[ri.ResultSummary]:
    """Player sessions of results files never recorded: not linked to a history record, no stint recorded on
    their track while they ran (link missed), a lap driven

    Args:
        linked: results paths linked to history records.
        checkpoints: (track, time) of stints whose stats were saved at a checkpoint with no history record
            (NeoPedal stopped while driving): their session counted already.
    """
    linked = set(linked)
    stints: dict[str, list[float]] = {}  # track (casefolded): stint end (or checkpoint) times
    for record in records:
        stints.setdefault(record.track.strip().casefold(), []).append(record.time)
    for track, when in checkpoints:
        stints.setdefault(track.strip().casefold(), []).append(when)
    for times in stints.values():
        times.sort()
    found = []
    for summary in summaries:
        if summary.game not in IMPORT_GAMES or summary.path in linked or summary.kind not in HISTORY_SESSION:
            continue
        if summary.laps <= 1 and summary.best_lap <= 0:  # lap 1 only: started in garage, never driven
            continue
        recorded = False
        for name in {summary.course.casefold(), summary.track.casefold(), summary.venue.casefold()} - {""}:
            times = stints.get(name, [])
            index = bisect_left(times, summary.start - ri.STINT_BEFORE_START)
            if index < len(times) and times[index] <= summary.end + ri.STINT_AFTER_END:
                recorded = True
                break
        if not recorded:
            found.append(summary)
    return found


def read_sessions(candidates: Iterable[ri.ResultSummary], classification: str, brands: Mapping[str, str],
                  podium_by_class: bool) -> list[ImportedSession]:
    """Sessions of candidates read from their results files (worker thread), unreadable files left out"""
    names: dict[str, tuple[str, ...]] = {}
    sessions = []
    for summary in candidates:
        folder = os.path.dirname(summary.path)
        if folder not in names:
            names.update(ri.player_names([folder]))
        try:
            result = rf.read_results(summary.path, names.get(folder, ()), keep=False)
        except (OSError, ValueError) as error:
            logger.debug("RESULTS IMPORT: %s not read: %s", summary.path, error)
            continue
        session = import_session(result, summary, names.get(folder, ()), classification, brands, podium_by_class)
        if session is not None:
            sessions.append(session)
    return sessions


def apply_import(stats_user: dict, records: Sequence[SessionRecord], sessions: Iterable[ImportedSession]
                 ) -> list[ImportedSession]:
    """Stats of sessions added to stats_user (counters added, best lap times kept), sessions added returned:
    a session older than the history of a track & vehicle counted before history existed is left out"""
    counted = counted_before_history(stats_user, records)
    history_start = min((record.time for record in records), default=float("inf"))
    added = []
    for session in sessions:
        record = session.record
        if (record.track, record.vehicle) in counted and record.time < history_start:
            continue
        vehicles = get_sub_dict(stats_user, record.track)
        current = vehicles.get(record.vehicle)
        vehicles[record.vehicle] = merge_vehicle_stats(current if isinstance(current, dict) else {},
                                                       asdict(session.stats))
        added.append(session)
    return added
