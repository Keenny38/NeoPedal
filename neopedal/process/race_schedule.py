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
Online races to come of Le Mans Ultimate & your online races, without Qt: what the pages show of them

Daily races of the public RaceControl site (process/public_schedule.py), your online races of the results files
of the game (process/local_online.py), tracks of the game (local Rest API /rest/race/track: names & ownership of each
track scene). Nothing is read from RaceOS
(online service of the game): a developer of Le Mans Ultimate said third-party apps must not call it (2026-11-04).
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterable
from typing import Any, NamedTuple

DAILY_TIERS = ("beginner", "intermediate", "advanced")  # game menu order
_VERSION = re.compile(r"\s+v?\d+(?:\.\d+)+$")  # " 1.27" after a track short name


class TrackInfo(NamedTuple):
    """Track layout of the game: short name ("Algarve International Circuit"), owned (DLC bought)"""

    name: str
    owned: bool


class Start(NamedTuple):
    """One start of a race"""

    time: float  # seconds since epoch


class Event(NamedTuple):
    """Daily race of the public page: every start known (soonest first)"""

    kind: str  # daily
    tier: str  # beginner, intermediate, advanced
    title: str
    track: str  # as the page writes it
    scene: str  # track scene of the game ("" if not found in its track list)
    starts: tuple[Start, ...]
    length: float  # race length, seconds (0 unknown)


class PublicEvent(NamedTuple):
    """Hosted race or community event of the public pages of RaceControl (no sign in): what a visitor sees"""

    kind: str  # "hosted" (privately organised race), "community" (series of a community)
    title: str
    url: str  # its page on www.racecontrol.gg
    start: float  # next start (seconds since epoch), 0 if not told
    weekly: bool = False  # starts every week at that day & time (community series)
    organizer: str = ""
    drivers: str = ""  # "Solo", "Teams"... as the page writes it
    track: str = ""
    classes: str = ""
    sessions: tuple[str, ...] = ()  # "P 50m", "Q 10m", "R 1h30m"
    registered: int = -1  # registrations, -1 unknown
    capacity: int = 0  # places, 0 unknown
    rounds: str = ""  # "6 Rounds"


class Schedule(NamedTuple):
    read_time: float  # seconds since epoch of the read (0: never read)
    events: tuple[Event, ...]
    tracks: dict[str, TrackInfo]  # track scene (lower case) -> layout of the game
    missing: tuple[str, ...] = ()  # kinds of race not read ("daily", "hosted", "community"): earlier ones kept
    frequency: dict[str, float] = {}  # daily tier -> seconds between starts
    hosted: tuple[PublicEvent, ...] = ()  # hosted races to come, soonest first
    community: tuple[PublicEvent, ...] = ()  # community events to come (series), soonest first

    @property
    def empty(self) -> bool:
        return not self.events


EMPTY = Schedule(0.0, (), {}, ("daily",))


class ResultRow(NamedTuple):
    """Driver of an online race result"""

    position: int
    class_position: int
    grid: int
    name: str
    car: str
    vehicle_class: str
    number: str
    team: str
    best_lap: float  # seconds, 0 if none
    total: float  # race time, seconds
    laps: int
    status: str  # finish status of the game ("Finished Normally", "DNF"...)
    lap_times: tuple[float, ...] = ()  # seconds, 0 for a lap without time
    lap_positions: tuple[int, ...] = ()  # position at the end of each lap
    drivers: tuple[str, ...] = ()  # drivers of the car (team races), else the row name


class OnlineResult(NamedTuple):
    """Online race the player drove, from a results file of the game: race classification (names shown, never kept
    on disk)"""

    path: str  # results file
    time: float
    title: str  # server name, else track
    track: str  # track as the results file names it
    rows: tuple[ResultRow, ...]


# Values
def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def parse_track_catalog(data: Any) -> dict[str, TrackInfo]:
    """Track layouts of the game (/rest/race/track) by scene (lower case): short name without version, owned"""
    tracks: dict[str, TrackInfo] = {}
    for item in map(_dict, _list(data)):
        scene = _text(item.get("sceneDesc")).lower()
        display = _dict(item.get("displayProperties"))
        name = _VERSION.sub("", _text(display.get("shortName")) or _text(item.get("shortName")))
        if scene:  # name with characters lost by the game (U+FFFD): RaceControl name shown instead
            tracks[scene] = TrackInfo("" if "�" in name else name, item.get("owned") is True)
    return tracks


# Views
def next_starts(event: Event, now: float) -> list[Start]:
    """Starts not over yet (running: started less than its whole length ago)"""
    return [start for start in event.starts if start.time + event.length > now]


def _ics_value(text: str) -> str:
    """Text of an iCalendar property: \\ ; , escaped, line breaks as \\n"""
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\n").replace("\n", "\\n"))


def _ics_fold(line: str) -> list[str]:
    """Lines of 75 bytes at most (RFC 5545), continuation lines starting with a space"""
    folded: list[str] = []
    current = ""
    for char in line:
        if len((current + char).encode("utf-8")) > (75 if not folded else 74):
            folded.append(current)
            current = char
        else:
            current += char
    folded.append(current)
    return [folded[0]] + [f" {part}" for part in folded[1:]]


def ics_text(events: Iterable[dict], stamp: float, product: str = "-//NeoPedal//Upcoming Races//EN") -> str:
    """iCalendar file of events (uid, title, start, end, location, description; times in seconds since epoch)"""
    def utc(moment: float) -> str:
        return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(moment))

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{product}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
    for event in events:
        lines += ["BEGIN:VEVENT", f"UID:{_ics_value(str(event['uid']))}@neopedal", f"DTSTAMP:{utc(stamp)}",
                  f"DTSTART:{utc(event['start'])}", f"DTEND:{utc(event['end'])}",
                  f"SUMMARY:{_ics_value(event['title'])}"]
        if event.get("location"):
            lines.append(f"LOCATION:{_ics_value(event['location'])}")
        if event.get("description"):
            lines.append(f"DESCRIPTION:{_ics_value(event['description'])}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(part for line in lines for part in _ics_fold(line)) + "\r\n"


def track_of(scene: str, fallback: str, tracks: dict[str, TrackInfo]) -> tuple[str, bool | None]:
    """Name of a track scene in the game (fallback if unknown) & owned (None if unknown)"""
    info = tracks.get(scene.lower())
    return (info.name or fallback, info.owned) if info is not None else (fallback, None)
