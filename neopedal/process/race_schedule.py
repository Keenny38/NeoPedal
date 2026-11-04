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
of the game (process/local_online.py), cars & tracks of the game (local Rest API /rest/race/car & /rest/race/track:
class, model name & ownership of each car folder, names & ownership of each track scene). Nothing is read from RaceOS
(online service of the game): a developer of Le Mans Ultimate said third-party apps must not call it (2026-11-04).
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterable
from typing import Any, NamedTuple

DAILY_TIERS = ("beginner", "intermediate", "advanced")  # game menu order
RANK_ORDER = ("Bronze", "Silver", "Gold", "Platinum")
_VERSION = re.compile(r"\s+v?\d+(?:\.\d+)+$")  # " 1.27" after a track short name


class Requirement(NamedTuple):
    """Safety Rank needed (rank "" for none)"""

    rank: str
    tier: int

    @property
    def number(self) -> int:
        return rank_number(self.rank, self.tier)


class CarInfo(NamedTuple):
    """Car of the game: class ("Hyper", "LMP2_ELMS", "GT3"...), model name, owned (DLC bought)"""

    car_class: str
    model: str
    owned: bool


class TrackInfo(NamedTuple):
    """Track layout of the game: short name ("Algarve International Circuit"), owned (DLC bought)"""

    name: str
    owned: bool


class Session(NamedTuple):
    kind: str  # Practice, Qualifying, Warmup, Race
    seconds: float
    time_of_day: str = ""  # time on track at session start ("19:20"), "" if unknown


class Weather(NamedTuple):
    """Weather node of the race forecast"""

    temperature: float | None  # Celsius
    rain: int | None  # rain chance, percent


class Start(NamedTuple):
    """One start of a race: time, registrations (-1 unknown), registration opening (0 unknown), player registered,
    RaceControl event id ("" unknown: field not readable)"""

    time: float
    registrations: int = -1
    opens: float = 0.0
    registered: bool = False
    event_id: str = ""


class Event(NamedTuple):
    """Daily, weekly or special race: every start known (soonest first)"""

    kind: str  # daily, weekly, special
    tier: str  # beginner, intermediate, advanced, weekly...
    title: str
    track: str
    scene: str
    starts: tuple[Start, ...]
    total: float  # practice to race end, seconds (0 unknown)
    sessions: tuple[Session, ...]
    cars: tuple[str, ...]  # car folders of RaceControl ("Oreca_07_ELMS_2023")
    requirement: Requirement
    forecast: tuple[Weather, ...] = ()  # race weather nodes, first at race start
    fixed_setup: bool | None = None
    tyre_warmers: bool | None = None
    max_players: int = 0
    team: bool = False
    tier_label: str = ""  # tier name as RaceControl writes it (practice server lists of a daily race)

    @property
    def race_seconds(self) -> float:
        return sum(session.seconds for session in self.sessions if session.kind == "Race")

    @property
    def temperature(self) -> float | None:
        return self.forecast[0].temperature if self.forecast else None

    @property
    def rain(self) -> int | None:
        return self.forecast[0].rain if self.forecast else None

    @property
    def entry_type(self) -> str:
        """Event type of RaceControl entry lists"""
        return "daily" if self.kind == "daily" else "specialevent"

    @property
    def practice_tier(self) -> str:
        """Tier of RaceControl practice server lists, as the game asks: tier of a daily race, title of the others"""
        return self.tier_label if self.kind == "daily" else self.title


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
    cars: dict[str, CarInfo]  # car folder (lower case) -> car of the game
    tracks: dict[str, TrackInfo]  # track scene (lower case) -> layout of the game
    missing: tuple[str, ...] = ()  # kinds of race not read ("daily", "hosted", "community"): earlier ones kept
    frequency: dict[str, float] = {}  # daily tier -> seconds between starts
    hosted: tuple[PublicEvent, ...] = ()  # hosted races to come, soonest first
    community: tuple[PublicEvent, ...] = ()  # community events to come (series), soonest first

    @property
    def empty(self) -> bool:
        return not self.events


EMPTY = Schedule(0.0, (), {}, {}, ("daily",))


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


def rank_number(rank: str, tier: int) -> int:
    """Order of a rank (game menu rankToNumber: Bronze 0-9, Silver 10-19...), -1 if unknown"""
    try:
        return RANK_ORDER.index(rank) * 10 + tier
    except ValueError:
        return -1


def can_enter(requirement: Requirement, rank: str, tier: int) -> bool | None:
    """Player of Safety Rank (rank, tier) may enter, None if not known (rank unknown)"""
    if not requirement.rank:
        return True
    if not rank:
        return None
    return rank_number(rank, tier) >= requirement.number


def parse_car_catalog(data: Any) -> dict[str, CarInfo]:
    """Cars of the game (/rest/race/car) by folder (lower case): class & model from the path tree
    ("ELMS 2025, LMP2_ELMS, Oreca 07"), owned"""
    cars: dict[str, CarInfo] = {}
    for item in map(_dict, _list(data)):
        parts = _text(item.get("vehFile")).replace("\\", "/").split("/")
        folder = ""
        for index, part in enumerate(parts[:-1]):
            if part.lower() == "vehicles":
                folder = parts[index + 1]
                break
        tree = [part.strip() for part in _text(item.get("fullPathTree")).split(",")]
        if not folder or len(tree) < 2:
            continue
        known = cars.get(folder.lower())
        owned = item.get("owned") is True or (known is not None and known.owned)
        cars[folder.lower()] = CarInfo(tree[1], tree[2] if len(tree) > 2 else _text(item.get("manufacturer")), owned)
    return cars


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
    length = event.total or event.race_seconds
    return [start for start in event.starts if start.time + length > now]


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


def classes_of(cars: Iterable[str], catalog: dict[str, CarInfo]) -> tuple[str, ...]:
    """Classes of cars (game names), in first seen order"""
    found: dict[str, None] = {}
    for car in cars:
        info = catalog.get(car.lower())
        if info is not None and info.car_class:
            found.setdefault(info.car_class, None)
    return tuple(found)


def owned_state(cars: Iterable[str], catalog: dict[str, CarInfo]) -> bool | None:
    """At least one car owned (any car known: base game ones are owned), None if none known"""
    known = [catalog[car.lower()] for car in cars if car.lower() in catalog]
    if not known:
        return None
    return any(car.owned for car in known)

