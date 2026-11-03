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
Online races to come of Le Mans Ultimate (RaceControl), without Qt

Same reads as the game menu (game web UI, RaceOS client), signed in with the game (see raceos.py):
    GET api/v1/daily/schedule -> {"tiers": {tier: [{eventname, track, scene, cars, duration, times}]}, "frequency"}
        (every daily race of the day: start times of each)
    GET api/v1/daily/list/<tier>?take=3 -> [event] (next daily races: sessions, weather, settings, registrations)
    GET api/v1/special-events/weekly | special -> [series {title, tier, configuration, events [{starts,
        registrations}]}] (special answers 500 when there is none)
    GET api/v1/championships/active | upcoming -> [{name, tier, type, rounds [{no, track, startsAt, endsAt,
        current, sessions}], schedule, registrations}]
    GET api/v1/coop/event/active?page=1&take=5 -> [{name, track, trackScene, length, starts, ends}]
    GET api/v1/hosted -> [server {name, track, session, currentPlayers, maxPlayers, hasPassword, region, official,
        configuration {track, cars}}] (servers players host)
Cars of the game (Rest API /rest/race/car) give the class, model name & ownership of each car folder named by
RaceControl. Entry: Safety Rank of the player at least the requirement of the tier (game menu rule, see
entry_requirement). Answers are kept trimmed on disk (no player names, no server addresses) for reading the
schedule while the game is closed.
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable, Iterable
from typing import Any, NamedTuple

from .raceos import parse_time

DAILY_TIERS = ("beginner", "intermediate", "advanced")  # game menu order
DAILY_TAKE = 3  # next daily races of each tier read with their details
CACHE_VERSION = 1
RANK_ORDER = ("Bronze", "Silver", "Gold", "Platinum")
# Default entry of a tier whose requirement is Bronze 0 (game menu getEntryRequirement)
TIER_ENTRY = {"beginner": ("Bronze", 0), "intermediate": ("Silver", 0), "advanced": ("Gold", 0)}
SESSION_NAMES = {"PRACTICE": "Practice", "QUALIFY": "Qualifying", "WARMUP": "Warmup", "RACE": "Race"}

# Request names (cache keys) -> RaceControl path
ROUTES: dict[str, str] = {
    "schedule": "api/v1/daily/schedule",
    **{f"daily_{tier}": f"api/v1/daily/list/{tier}?take={DAILY_TAKE}" for tier in DAILY_TIERS},
    "weekly": "api/v1/special-events/weekly",
    "special": "api/v1/special-events/special",
    "championships": "api/v1/championships/active",
    "championships_upcoming": "api/v1/championships/upcoming",
    "coop": "api/v1/coop/event/active?page=1&take=5",
    "hosted": "api/v1/hosted",
}
# Keys never kept on disk: other players & server addresses, signatures, images, settings not shown
_DROP_KEYS = frozenset((
    "entries", "taskArn", "taskPublicIP", "serverPort", "sig", "workshopId", "itemDefId", "version", "veh",
    "assists", "liveSteward", "ratings", "competitionMetadata", "heroImage", "heroimage", "smallImage", "cardImage",
    "cardimage", "setups", "bopFile", "baseRFM", "vehicleFilter", "favouriteAndFixedSetups", "servers", "splits",
    "history", "dlcAppIds", "saveFile", "avatar",
))
_DURATION = re.compile(r"(\d+(?:\.\d+)?)\s*([hms])", re.IGNORECASE)
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


class Board(NamedTuple):
    """Weekly leaderboard of a race (fastest laps), named as the game menu names it (Event.getLeaderboardId)"""

    event_type: str  # daily, specialevent, championship
    tier: str
    track_name: str  # RaceControl track name without "_"
    layout: str  # first layout name without spaces, "_" & "-"
    title: str  # event title (championship: name & "Week" & round), letters & digits only

    @property
    def key(self) -> str:
        return "-".join(self)

    def request(self, vehicle_class: str = "", page: int = 1, limit: int = 100, around: str = "") -> dict:
        """Body of api/v1/leaderboards/results-for-users: a page, or the entries around a player (RaceControl id)"""
        body: dict[str, Any] = {"lookup": "Steam", "ids": [], "eventType": self.event_type, "tier": self.tier,
                                "trackName": self.track_name, "trackLayout": self.layout, "eventTitle": self.title,
                                "carClass": vehicle_class, "limit": limit}
        if around:
            body["aroundUserId"] = around
        else:
            body["page"] = page
        return body


def board_of(event_type: str, tier: str, track: Any, title: str) -> Board | None:
    """Leaderboard of a race of a track ({name, subItems [{name}]}), None if the track has no layout"""
    track = _dict(track)
    layouts = _list(track.get("subItems"))
    layout = _text(_dict(layouts[0]).get("name")) if layouts else ""
    name = _text(track.get("name")).replace("_", "")
    title = re.sub(r"[^a-zA-Z0-9]", "", title)
    if not name or not layout or not title or not tier:
        return None
    return Board(event_type, tier, name, re.sub(r"[ _-]", "", layout), title)


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
    board: Board | None = None  # weekly leaderboard of the race (None: race details not read)
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


class Round(NamedTuple):
    number: int
    track: str
    scene: str
    starts: float
    ends: float
    current: bool
    race_seconds: float
    points: float = 1.0  # points multiplier
    board: Board | None = None  # fastest laps of the round


class Championship(NamedTuple):
    key: str  # RaceControl id
    name: str
    tier: str
    kind: str  # solo, endurance, team...
    requirement: Requirement
    registrations: int
    registered: bool
    rounds: tuple[Round, ...]
    starts: tuple[float, ...]  # sessions of the current round (schedule)
    cars: tuple[str, ...]
    drop_rounds: int
    upcoming: bool  # not begun yet
    attempts: int = 0  # races of a round that count (0 unknown)

    def current_round(self, now: float) -> Round | None:
        """Round being run (flagged by RaceControl, else the one whose dates hold now), None if none"""
        for item in self.rounds:
            if item.current:
                return item
        return next((item for item in self.rounds if item.starts <= now < item.ends), None)


class CoopEvent(NamedTuple):
    """Endurance event driven with friends (co-op), open between starts & ends"""

    name: str
    track: str
    scene: str
    length: float  # seconds
    starts: float
    ends: float


class Server(NamedTuple):
    """Server hosted by players (no address kept)"""

    name: str
    track: str
    scene: str
    session: str  # Practice, Qualifying, Race...
    players: int
    max_players: int
    password: bool
    region: str
    official: bool
    team: bool
    cars: tuple[str, ...]
    sessions: tuple[Session, ...] = ()
    forecast: tuple[Weather, ...] = ()


class Schedule(NamedTuple):
    read_time: float  # seconds since epoch of the read (0: never read)
    events: tuple[Event, ...]
    championships: tuple[Championship, ...]
    coop: tuple[CoopEvent, ...]
    servers: tuple[Server, ...]
    cars: dict[str, CarInfo]  # car folder (lower case) -> car of the game
    tracks: dict[str, TrackInfo]  # track scene (lower case) -> layout of the game
    missing: tuple[str, ...]  # requests not answered (ROUTES keys)
    frequency: dict[str, float] = {}  # daily tier -> seconds between starts

    @property
    def empty(self) -> bool:
        return not (self.events or self.championships or self.coop or self.servers)


EMPTY = Schedule(0.0, (), (), (), (), {}, {}, tuple(ROUTES))


class FieldLevel(NamedTuple):
    """Drivers registered to a start: count, by class & by Driver Rank / Safety Rank (names never kept)"""

    drivers: int
    classes: tuple[tuple[str, int], ...]  # class, drivers (most first)
    driver_ranks: tuple[tuple[str, int], ...]  # rank (Bronze...Platinum), drivers
    safety_ranks: tuple[tuple[str, int], ...]
    complete: bool  # every page read


class PracticeServer(NamedTuple):
    """Practice server of a championship round or of a race (address & password never kept)"""

    players: int
    max_players: int
    ends: float


class ChampionshipDetail(NamedTuple):
    sessions: tuple[Start, ...]  # sessions of the current round with registrations
    attempts_used: int
    attempts_total: int
    practice: tuple[PracticeServer, ...]


class CoopEntry(NamedTuple):
    position: int
    team: str  # team name, else drivers joined
    drivers: tuple[str, ...]
    vehicle_class: str
    fastest_lap: float
    average_lap: float


class CoopBoard(NamedTuple):
    teams: int  # teams ranked
    top: tuple[CoopEntry, ...]
    mine: CoopEntry | None  # entry with the player among its drivers


class Friend(NamedTuple):
    """Friend of the player on RaceControl (Steam friends playing LMU)"""

    player_id: str
    name: str


class Profile(NamedTuple):
    """Public profile of a driver"""

    name: str
    nationality: str
    driver_rank: tuple[str, int]
    safety_rank: tuple[str, int]
    badge: str


class LeaderEntry(NamedTuple):
    """Driver of a weekly leaderboard: rank, fastest lap & its sectors (seconds), car, class, tyres, ranks, team"""

    rank: int
    player_id: str
    name: str
    seconds: float
    sectors: tuple[float, ...]
    car: str
    vehicle_class: str
    compound: str
    driver_rank: tuple[str, int]
    safety_rank: tuple[str, int]
    team: str


class Leaderboard(NamedTuple):
    drivers: int  # drivers ranked
    entries: tuple[LeaderEntry, ...]


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
    dr_change: float | None  # Driver Rank change (None if not given)
    sr_change: float | None
    reasons: tuple[str, ...]  # why ranks changed (RaceControl texts)
    lap_times: tuple[float, ...] = ()  # seconds, 0 for a lap without time
    lap_positions: tuple[int, ...] = ()  # position at the end of each lap
    drivers: tuple[str, ...] = ()  # drivers of the car (team races), else the row name
    driver_rank: tuple[str, int] = ("", 0)  # after the race (rank, tier), ("", 0) unknown
    safety_rank: tuple[str, int] = ("", 0)


class DriverResult(NamedTuple):
    """Driver of an online race: Driver & Safety Rank changes, why & ranks after the race (see ResultRow)"""

    name: str
    dr_change: float | None
    sr_change: float | None
    reasons: tuple[str, ...]
    driver_rank: tuple[str, int]
    safety_rank: tuple[str, int]


class OnlineResult(NamedTuple):
    """Online race the player drove: race classification (names shown, never kept on disk)"""

    event_id: str
    split: int
    time: float
    event_type: str  # daily, specialevent, championship
    tier: str
    title: str
    track: str  # track scene
    rows: tuple[ResultRow, ...]
    # Rank changes & ranks of each driver (team races: rows are cars, these are not on them), names shown only
    players: tuple[DriverResult, ...] = ()


# Values
def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)) and math.isfinite(value):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except (ValueError, OverflowError):  # OverflowError: "1e999", "inf"
            return default
    return default


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def _bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _time(value: Any) -> float:
    """Seconds since epoch, 0 if unreadable or empty date of RaceControl ("0001-01-01T00:00:00Z")"""
    moment = parse_time(value)
    return 0.0 if math.isnan(moment) or moment <= 0 else moment


def duration_seconds(value: Any) -> float:
    """Seconds of a RaceControl duration ("1h12m30s", "90m", "30s", "10h"), 0 if unreadable"""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) * 60 if math.isfinite(value) and value > 0 else 0.0
    total = 0.0
    for amount, unit in _DURATION.findall(_text(value)):
        total += float(amount) * {"h": 3600, "m": 60, "s": 1}[unit.lower()]
    return total


def rank_number(rank: str, tier: int) -> int:
    """Order of a rank (game menu rankToNumber: Bronze 0-9, Silver 10-19...), -1 if unknown"""
    try:
        return RANK_ORDER.index(rank) * 10 + tier
    except ValueError:
        return -1


def entry_requirement(tier: Any) -> Requirement:
    """Safety Rank needed for a tier ({name, entryRequirement {rank, tier}}): Bronze 0 of a daily tier stands for
    the tier default (game menu getEntryRequirement), none if not given"""
    tier = _dict(tier)
    needed = _dict(tier.get("entryRequirement"))
    rank, level = _text(needed.get("rank")), _int(needed.get("tier"))
    if not rank:
        return Requirement("", 0)
    if rank == "Bronze" and level == 0:
        rank, level = TIER_ENTRY.get(_text(tier.get("name")).lower(), (rank, level))
    return Requirement(rank, level)


def can_enter(requirement: Requirement, rank: str, tier: int) -> bool | None:
    """Player of Safety Rank (rank, tier) may enter, None if not known (rank unknown)"""
    if not requirement.rank:
        return True
    if not rank:
        return None
    return rank_number(rank, tier) >= requirement.number


def track_name(track: Any, fallback: str = "") -> str:
    """Name of a RaceControl track ({friendly, name, subItems [{name, scn}]}): its friendly name, layout name when
    the friendly name is a folder name ("PortimaoWEC_2023"), fallback if none"""
    track = _dict(track)
    friendly = _text(track.get("friendly"))
    if friendly and "_" not in friendly:
        return friendly
    layouts = _list(track.get("subItems"))
    layout = _dict(layouts[0]) if layouts else {}
    return _text(layout.get("name")) or friendly.replace("_", " ") or _text(track.get("name")) or fallback


def track_scene(track: Any) -> str:
    track = _dict(track)
    layouts = _list(track.get("subItems"))
    return _text(_dict(layouts[0]).get("scn")) if layouts else _text(track.get("name"))


def car_folders(cars: Any) -> tuple[str, ...]:
    """Car folders of a car list (folder names, or {friendly} objects), in list order, once each"""
    found: dict[str, None] = {}
    for car in _list(cars):
        name = _text(car) or _text(_dict(car).get("friendly")) or _text(_dict(car).get("name"))
        if name:
            found.setdefault(name, None)
    return tuple(found)


def session_kind(value: Any) -> str:
    """Session name of a RaceControl or game session ("Practice", "QUALIFY1", "RACE1")"""
    text = _text(value)
    key = text.rstrip("0123456789").upper()
    return SESSION_NAMES.get(key, text.title())


def time_of_day(value: Any) -> str:
    """Time on track of a RaceControl session ("19h20m", "9h0m") as "19:20", "" if unreadable"""
    seconds = duration_seconds(value) if isinstance(value, str) else 0.0
    if not math.isfinite(seconds) or (not seconds and _text(value) not in ("0h0m", "0m")):
        return ""
    minutes = round(seconds / 60) % 1440
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def parse_sessions(sessions: Any) -> tuple[Session, ...]:
    return tuple(Session(session_kind(item.get("type")), duration_seconds(item.get("duration")),
                         time_of_day(item.get("timeOfDay")))
                 for item in map(_dict, _list(sessions)) if _text(item.get("type")))


def race_forecast(sessions: Any) -> tuple[Weather, ...]:
    """Weather nodes of the race (first at race start): temperature (Celsius) & rain chance (percent)"""
    races = [item for item in map(_dict, _list(sessions)) if session_kind(item.get("type")) == "Race"]
    forecast = []
    for node in map(_dict, _list(races[0].get("weather")) if races else ()):
        rain = _number(node.get("rainChange", node.get("rainChance")))
        weather = Weather(_number(node.get("temperature")), round(rain) if rain is not None else None)
        if weather != (None, None):
            forecast.append(weather)
    return tuple(forecast)


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


# Answers
def _daily_details(answer: Any) -> dict[str, list[dict]]:
    """Daily race list of a tier by title"""
    found: dict[str, list[dict]] = {}
    for event in map(_dict, _list(answer)):
        title = _text(_dict(event.get("configuration")).get("title")) or _text(event.get("title"))
        if title:
            found.setdefault(title, []).append(event)
    return found


def _registrations(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    return _int(value, -1)


def _start_of(item: dict, time: float) -> Start:
    """Start of a race at time from a daily race or a weekly event of RaceControl"""
    config = _dict(item.get("configuration"))
    opens = _time(config.get("registrationOpens")) or _time(item.get("registrationOpens"))
    registered = item.get("isRegistered") is True or item.get("registered") is True
    return Start(time, _registrations(item.get("registrations")), opens, registered, _text(item.get("id")))


def _event_from_config(kind: str, tier: Any, title: str, config: dict, starts: list[Start],
                       total: float = 0.0, cars: tuple[str, ...] = (), track: str = "", scene: str = "",
                       team: bool = False) -> Event | None:
    content = _dict(config.get("content"))
    settings = _dict(config.get("settings"))
    sessions = config.get("sessions")
    parsed_sessions = parse_sessions(sessions)
    known = {start.time: start for start in starts if start.time > 0}  # one per time (details over schedule)
    track = track or track_name(content.get("track"))
    if not title or not track or not known:
        return None
    tier_name = _text(_dict(tier).get("name")).lower() or kind
    board = board_of("daily" if kind == "daily" else "specialevent", _text(_dict(tier).get("name")),
                     content.get("track"), title)
    return Event(
        board=board,
        kind=kind, tier=tier_name, title=title, track=track, scene=scene or track_scene(content.get("track")),
        starts=tuple(known[time] for time in sorted(known)),
        total=total or sum(session.seconds for session in parsed_sessions),
        sessions=parsed_sessions, cars=cars or car_folders(content.get("cars")),
        requirement=entry_requirement(tier), forecast=race_forecast(sessions),
        fixed_setup=_bool(settings.get("fixedSetup")), tyre_warmers=_bool(settings.get("tyreWarmers")),
        max_players=_int(settings.get("maxPlayers")), team=team, tier_label=_text(_dict(tier).get("name")) or kind,
    )


def parse_daily(schedule: Any, lists: dict[str, Any]) -> list[Event]:
    """Daily races of each tier: start times of the day (schedule) with details of the next ones (lists by tier);
    from the lists alone when the schedule was not read"""
    events: list[Event] = []
    tiers = _dict(_dict(schedule).get("tiers"))
    for tier in DAILY_TIERS:
        details = _daily_details(lists.get(tier))
        # Tier without details (list not read): Bronze 0 stands for the tier default (game menu rule, TIER_ENTRY)
        default_tier = {"name": tier, "entryRequirement": {"rank": "Bronze", "tier": 0}}
        tier_info = default_tier
        done = set()
        for entry in map(_dict, _list(tiers.get(tier))):
            title = _text(entry.get("eventname"))
            matches = details.get(title, [])
            config = _dict(matches[0].get("configuration")) if matches else {}
            if matches:
                tier_info = _dict(config.get("tier")) or tier_info
            # configuration.starts (practice start) gives the schedule times, raceStartsAt only when it is missing
            details_of = {start.time: start for item in matches
                          if (start := _start_of(item, _time(_dict(item.get("configuration")).get("starts"))
                                                 or _time(item.get("raceStartsAt")))).time}
            times = set(map(_time, _list(entry.get("times"))))
            starts = [details_of.get(time, Start(time)) for time in times]
            # Starts of the list past the UTC day of the schedule (next day 00:00 after the last start of the day)
            starts += [start for time, start in details_of.items() if time not in times]
            track = _text(entry.get("track"))
            if not track or "_" in track:  # folder name ("PortimaoWEC_2023"): name of the race details
                track = track_name(_dict(config.get("content")).get("track"), track.replace("_", " "))
            event = _event_from_config(
                "daily", tier_info if matches else default_tier, title, config, starts,
                duration_seconds(entry.get("duration")), car_folders(entry.get("cars")), track,
                _text(entry.get("scene")), bool(entry.get("teamEvent")))
            if event is not None:
                events.append(event)
                done.add(title)
        for title, matches in details.items():  # schedule not read: next races of the list
            if title in done:
                continue
            config = _dict(matches[0].get("configuration"))
            starts = [_start_of(item, _time(_dict(item.get("configuration")).get("starts"))
                                or _time(item.get("raceStartsAt"))) for item in matches]
            event = _event_from_config("daily", _dict(config.get("tier")) or default_tier, title, config, starts,
                                       team=bool(config.get("teamEvent")))
            if event is not None:
                events.append(event)
    return events


def parse_series(kind: str, answer: Any) -> list[Event]:
    """Weekly or special events (series with their events to come)"""
    events = []
    for series in map(_dict, _list(answer)):
        starts = [_start_of(item, _time(item.get("starts"))) for item in map(_dict, _list(series.get("events")))]
        if not starts:
            starts = [Start(_time(series.get("starts")))]
        event = _event_from_config(kind, series.get("tier"), _text(series.get("title")),
                                   _dict(series.get("configuration")), starts, team=bool(series.get("teamEvent")))
        if event is not None:
            events.append(event)
    return events


def parse_championships(answer: Any, upcoming: bool = False) -> list[Championship]:
    championships = []
    for item in map(_dict, _list(answer)):
        name = _text(item.get("name"))
        if not name:
            continue
        rounds = []
        for entry in map(_dict, _list(item.get("rounds"))):
            sessions = parse_sessions(entry.get("sessions"))
            rounds.append(Round(
                number=_int(entry.get("no")), track=track_name(entry.get("track")),
                scene=track_scene(entry.get("track")), starts=_time(entry.get("startsAt")),
                ends=_time(entry.get("endsAt")), current=entry.get("current") is True,
                race_seconds=sum(session.seconds for session in sessions if session.kind == "Race"),
                points=_number(entry.get("pointsMultiplier")) or 1.0,
                board=board_of("championship", _text(_dict(item.get("tier")).get("name")), entry.get("track"),
                               f"{name}Week{_int(entry.get('no'))}")))
        rounds.sort(key=lambda entry: entry.number)
        attempts = item.get("attempts")
        championships.append(Championship(
            key=_text(item.get("id")), attempts=_int(_dict(attempts).get("total") if isinstance(attempts, dict)
                                                     else attempts),
            name=name, tier=_text(_dict(item.get("tier")).get("name")).lower(), kind=_text(item.get("type")),
            requirement=entry_requirement(item.get("tier")), registrations=_registrations(item.get("registrations")),
            registered=item.get("registered") is True, rounds=tuple(rounds),
            starts=tuple(sorted({moment for moment in map(_time, _list(item.get("schedule"))) if moment})),
            cars=car_folders(item.get("cars")), drop_rounds=_int(item.get("dropRounds")), upcoming=upcoming))
    return championships


def parse_coop(answer: Any) -> list[CoopEvent]:
    events = []
    for item in map(_dict, _list(answer)):
        name = _text(item.get("name"))
        if not name:
            continue
        events.append(CoopEvent(
            name=name, track=_text(item.get("track")).replace("_", " ") or _text(item.get("trackScene")),
            scene=_text(item.get("trackScene")), length=duration_seconds(item.get("length")),
            starts=_time(item.get("starts")), ends=_time(item.get("ends"))))
    return events


def parse_hosted(answer: Any) -> list[Server]:
    servers = []
    for item in map(_dict, _list(answer)):
        name = _text(item.get("name"))
        if not name or item.get("public") is False:
            continue
        config = _dict(item.get("configuration"))
        players = item.get("currentPlayers", item.get("players"))
        servers.append(Server(
            name=name, track=track_name(config.get("track"), _text(item.get("track")).replace("_", " ")),
            scene=track_scene(config.get("track")),
            session=session_kind(item.get("session")), players=max(_int(players), 0),
            max_players=max(_int(item.get("maxPlayers")), 0), password=item.get("hasPassword") is True,
            region=_text(item.get("region")), official=item.get("official") is True,
            team=item.get("teamEvent") is True, cars=car_folders(config.get("cars")),
            sessions=parse_sessions(config.get("sessions")), forecast=race_forecast(config.get("sessions"))))
    servers.sort(key=lambda server: (-server.players, server.name.lower()))
    return servers


def parse_schedule(answers: dict[str, Any], cars: dict[str, CarInfo], tracks: dict[str, TrackInfo],
                   read_time: float) -> Schedule:
    """Schedule from RaceControl answers by ROUTES key (None: not answered)"""
    events = parse_daily(answers.get("schedule"), {tier: answers.get(f"daily_{tier}") for tier in DAILY_TIERS})
    events += parse_series("weekly", answers.get("weekly"))
    events += parse_series("special", answers.get("special"))
    championships = parse_championships(answers.get("championships"))
    known = {item.name for item in championships}
    championships += [item for item in parse_championships(answers.get("championships_upcoming"), True)
                      if item.name not in known]
    return Schedule(
        read_time=read_time, events=tuple(events), championships=tuple(championships),
        coop=tuple(parse_coop(answers.get("coop"))), servers=tuple(parse_hosted(answers.get("hosted"))),
        cars=cars, tracks=tracks, missing=tuple(key for key in ROUTES if answers.get(key) is None),
        frequency={tier: seconds for tier, every in _dict(_dict(answers.get("schedule")).get("frequency")).items()
                   if (seconds := duration_seconds(_text(every).replace("mins", "m").replace("min", "m")))})


# Details read on demand (never kept on disk)
def parse_field(pages: Iterable[Any], complete: bool) -> FieldLevel:
    """Drivers registered to a start (event/entries pages): count by class, Driver Rank & Safety Rank"""
    classes: dict[str, int] = {}
    driver_ranks: dict[str, int] = {}
    safety_ranks: dict[str, int] = {}
    drivers = 0
    for page in pages:
        for entry in _list(page):
            if not isinstance(entry, dict):
                continue
            drivers += 1
            for counts, value in ((classes, _text(entry.get("class"))),
                                  (driver_ranks, _text(_dict(entry.get("dr")).get("rank"))),
                                  (safety_ranks, _text(_dict(entry.get("sr")).get("rank")))):
                if value:
                    counts[value] = counts.get(value, 0) + 1

    def by_rank(counts: dict[str, int]) -> tuple[tuple[str, int], ...]:
        return tuple(sorted(counts.items(), key=lambda item: (-rank_number(item[0], 0), item[0])))

    return FieldLevel(drivers, tuple(sorted(classes.items(), key=lambda item: (-item[1], item[0]))),
                      by_rank(driver_ranks), by_rank(safety_ranks), complete)


def parse_championship_detail(detail: Any, practice: Any) -> ChampionshipDetail:
    """Sessions of the current round with registrations, attempts, practice servers (players only)"""
    detail = _dict(detail)
    sessions = sorted((Start(time, _registrations(item.get("registrations")), event_id=_text(item.get("eventId")))
                       for item in map(_dict, _list(detail.get("events"))) if (time := _time(item.get("time")))),
                      key=lambda start: start.time)
    attempts = _dict(detail.get("attempts"))
    return ChampionshipDetail(tuple(sessions), _int(attempts.get("used")), _int(attempts.get("total")),
                              parse_practice(practice))


def parse_practice(answer: Any) -> tuple[PracticeServer, ...]:
    """Practice servers of a championship round or of a race: players & end only (address, password dropped)"""
    return tuple(PracticeServer(max(_int(item.get("currentPlayers")), 0), max(_int(item.get("maxPlayers")), 0),
                                _time(item.get("endsAt"))) for item in map(_dict, _list(answer)))


def _coop_entry(item: dict) -> CoopEntry:
    meta = _dict(item.get("metadata"))
    drivers = tuple(name for name in (_text(_dict(driver).get("name")) for driver in _list(meta.get("drivers")))
                    if name)
    return CoopEntry(
        position=_int(item.get("position")), team=_text(meta.get("teamName")) or _text(item.get("name")),
        drivers=drivers, vehicle_class=_text(meta.get("vehicleClass")),
        fastest_lap=_number(meta.get("fastestLap")) or 0.0, average_lap=_number(meta.get("averageLapTime")) or 0.0)


def parse_coop_board(pages: Iterable[Any], player: str, top: int = 5) -> CoopBoard:
    """Co-op event leaderboard pages: best teams & the entry of the player (by name, any of its drivers)"""
    entries: list[CoopEntry] = []
    count = 0
    for page in pages:
        page = _dict(page)
        count = max(count, _int(page.get("count")))
        entries.extend(_coop_entry(item) for item in map(_dict, _list(page.get("entries"))))
    entries.sort(key=lambda entry: entry.position or 1 << 30)
    key = player.split("#", 1)[0].strip().casefold()
    mine = next((entry for entry in entries if key and any(
        name.split("#", 1)[0].strip().casefold() == key for name in entry.drivers)), None)
    return CoopBoard(count or len(entries), tuple(entries[:top]), mine)


def _rank_of(value: Any) -> tuple[str, int]:
    value = _dict(value)
    return _text(value.get("rank")), _int(value.get("tier"))


def parse_leaderboard(answer: Any) -> Leaderboard | None:
    """Page of a weekly leaderboard ({count, entries [{id, name, rank, score (ms), metadata}]}), None if unreadable"""
    answer = _dict(answer) if isinstance(answer, dict) else None
    if answer is None:
        return None
    entries = []
    for item in map(_dict, _list(answer.get("entries"))):
        meta = _dict(item.get("metadata"))
        score = _number(item.get("score"))
        compounds = [part.split(",", 1)[-1] for part in map(_text, _list(meta.get("compound"))) if part]
        entries.append(LeaderEntry(
            rank=_int(item.get("rank")), player_id=_text(item.get("id")), name=_text(item.get("name")),
            seconds=score / 1000 if score and score > 0 else 0.0,
            sectors=tuple(value for value in map(_number, _list(meta.get("sectors"))) if value is not None),
            car=_text(meta.get("car")), vehicle_class=_text(meta.get("class")),
            compound=" / ".join(dict.fromkeys(compounds)), driver_rank=_rank_of(meta.get("dr")),
            safety_rank=_rank_of(meta.get("sr")), team=_text(meta.get("teamName"))))
    return Leaderboard(max(_int(answer.get("count")), len(entries)), tuple(entries))


def parse_friends(answer: Any) -> tuple[Friend, ...]:
    """Friends of api/v1/player/friends-list (RaceControl players)"""
    friends = []
    for item in map(_dict, _list(answer)):
        player_id, name = _text(item.get("id")), _text(item.get("name"))
        if player_id and name:
            friends.append(Friend(player_id, name))
    return tuple(friends)


def parse_profile(answer: Any, name: str) -> Profile | None:
    """Profile of a driver from api/v1/players (name without "#1234" asked), None if not found"""
    key = name.split("#", 1)[0].strip().casefold()
    for item in map(_dict, _list(answer)):
        if _text(item.get("name")).split("#", 1)[0].strip().casefold() == key:
            profile = _dict(item.get("profile"))
            return Profile(_text(item.get("name")), _text(profile.get("nationality")), _rank_of(item.get("driverRank")),
                           _rank_of(item.get("safetyRank")), _text(profile.get("badge")))
    return None


def percentile(rank: int, count: int) -> float:
    """Share of the drivers ranked at or above a rank, percent (0 if unknown)"""
    return min(100.0 * rank / count, 100.0) if rank > 0 and count > 0 else 0.0


# Leaderboard classes are game class names, but Hypercar is "Hyper" there
LEADERBOARD_CLASSES = {"Hypercar": "Hyper"}


def leaderboard_class(vehicle_class: str) -> str:
    return LEADERBOARD_CLASSES.get(vehicle_class, vehicle_class)


def _reasons(value: Any) -> tuple[str, ...]:
    texts = []
    for item in map(_dict, _list(value)):
        reason = _text(item.get("reason"))
        impact = _number(item.get("impact"))
        if reason:  # change told only when it has one
            sign = "+" if item.get("positive") is True else "-"
            texts.append(f"{reason} ({sign}{abs(impact):g})" if impact else reason)
    return tuple(texts)


def parse_result(item: Any) -> OnlineResult | None:
    """Online race of the results history (api/v1/results) or of one race (api/v1/result), None if unreadable"""
    item = _dict(item)
    event_id = _text(item.get("eventId"))
    race = _dict(item.get("race"))
    sessions = [_dict(entry) for entry in _list(race.get("races"))]
    if not event_id or not sessions:
        return None
    changes = {}
    ranks = {}
    for driver in map(_dict, _list(item.get("drivers"))):
        name = _text(driver.get("name"))
        if name:
            changes[name] = (_number(driver.get("driverRankAdjustment")), _number(driver.get("safetyRankAdjustment")),
                             _reasons(driver.get("drReasons")) + _reasons(driver.get("srReasons")))
            ranks[name] = (_rank_of(driver.get("driverRank")), _rank_of(driver.get("safetyRank")))
    teams: dict[str, tuple[str, ...]] = {}  # team name -> drivers (team races: rows are cars named by their team)
    for team in map(_dict, _list(item.get("teams"))):
        members = tuple(name for name in (_text(_dict(member).get("name")) for member in _list(team.get("teamMembers")))
                        if name)
        if _text(team.get("name")) and members:
            teams.setdefault(_text(team.get("name")), members)
    rows = []
    for entry in map(_dict, _list(sessions[-1].get("results"))):
        name = _text(entry.get("name"))
        dr_change, sr_change, reasons = changes.get(name, (None, None, ()))
        laps = [_dict(lap) for lap in _list(entry.get("laps"))]
        drivers = (name,) if name in changes else teams.get(_text(entry.get("teamName")), (name,))
        dr_rank, sr_rank = ranks.get(name, (("", 0), ("", 0)))
        rows.append(ResultRow(
            lap_times=tuple(_number(lap.get("lapTime")) or 0.0 for lap in laps),
            lap_positions=tuple(_int(lap.get("p")) for lap in laps), drivers=drivers,
            driver_rank=dr_rank, safety_rank=sr_rank,
            position=_int(entry.get("position")), class_position=_int(entry.get("classPosition")),
            grid=_int(entry.get("gridPos")), name=name, car=_text(entry.get("carType")) or _text(entry.get("vehName")),
            vehicle_class=_text(entry.get("carClass")), number=_text(entry.get("carNumber")),
            team=_text(entry.get("teamName")), best_lap=_number(entry.get("bestLapTime")) or 0.0,
            total=_number(entry.get("finishTime")) or 0.0, laps=_int(entry.get("Laps")),
            status=_text(entry.get("finishStatus")), dr_change=dr_change, sr_change=sr_change, reasons=reasons))
    rows.sort(key=lambda row: row.position or 1 << 30)
    tier = item.get("tier")
    return OnlineResult(event_id, _int(item.get("splitNo"), 1), _time(item.get("date")), _text(item.get("eventType")),
                        _text(_dict(tier).get("name")) if isinstance(tier, dict) else _text(tier),
                        _text(item.get("title")), _text(item.get("trackScene")) or _text(item.get("track")),
                        tuple(rows), tuple(DriverResult(name, *changes[name], *ranks[name]) for name in changes))


def read_answers(get: Callable[[str], Any], skip: Iterable[str] = ()) -> dict[str, Any]:
    """Answers of every request (get: RaceControl GET path -> JSON, None if not read), blocking (worker thread)"""
    skipped = set(skip)
    return {key: get(path) for key, path in ROUTES.items() if key not in skipped}


# Disk copy
def trimmed(value: Any) -> Any:
    """Answer without what is never shown (players, server addresses, signatures, images): kept on disk"""
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key in _DROP_KEYS:
                continue
            if key == "registrations" and isinstance(item, list):
                result[key] = len(item)  # counted, names dropped
            elif key == "cars" and isinstance(item, list):
                result[key] = list(car_folders(item))
            else:
                result[key] = trimmed(item)
        return result
    if isinstance(value, list):
        return [trimmed(item) for item in value]
    return value


def cache_data(answers: dict[str, Any], cars: dict[str, CarInfo], tracks: dict[str, TrackInfo],
               read_time: float) -> dict:
    return {
        "version": CACHE_VERSION, "read": read_time,
        "answers": {key: trimmed(value) for key, value in answers.items() if value is not None},
        "cars": {folder: list(car) for folder, car in cars.items()},
        "tracks": {scene: list(track) for scene, track in tracks.items()},
    }


def from_cache(data: Any) -> tuple[dict[str, Any], dict[str, CarInfo], dict[str, TrackInfo], float] | None:
    """Answers, cars, tracks & read time of a disk copy, None if not one of this version"""
    data = _dict(data)
    if data.get("version") != CACHE_VERSION:
        return None
    read_time = _number(data.get("read")) or 0.0
    cars = {}
    for folder, car in _dict(data.get("cars")).items():
        car = _list(car)
        if len(car) == 3 and isinstance(folder, str):
            cars[folder] = CarInfo(_text(car[0]), _text(car[1]), car[2] is True)
    tracks = {}
    for scene, track in _dict(data.get("tracks")).items():
        track = _list(track)
        if len(track) == 2 and isinstance(scene, str):
            tracks[scene] = TrackInfo(_text(track[0]), track[1] is True)
    return _dict(data.get("answers")), cars, tracks, read_time


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


# Registration (Upcoming Races page: the player registers to a race or leaves it, same requests as the game menu)
#   POST api/v1/event/overview {game, eventType, eventId} -> event (configuration.content.cars with every livery
#       file allowed, registrations)
#   POST api/v1/event/register {eventType, eventId, carClass, car, team} -> {status: "OK" | "ERROR", message, errors}
#       (car: item of the event car list with only the livery chosen, carClass: class of the game path tree)
#   DELETE api/v1/event/unregister {eventType, eventId} -> {status}
# Team events need a team & line-up chosen in the game: never registered from here.
OVERVIEW_ROUTE = "api/v1/event/overview"
REGISTER_ROUTE = "api/v1/event/register"
UNREGISTER_ROUTE = "api/v1/event/unregister"


class CarChoice(NamedTuple):
    """Car the player may register with: livery of the event car list, owned in the game"""

    veh: str  # livery file ("8_TOYOTAWEBFCA0DCD.VEH")
    vehicle_class: str  # class of the game path tree ("Hypercar", "LMP2_ELMS")
    model: str  # "Toyota GR010"
    livery: str  # livery name of the event list ("Toyota Gazoo Racing #8:LM")


def is_registered(event: Any, player_id: str) -> bool:
    """Player among the registrations of a RaceControl event (driver, or driver of a team line-up)"""
    if not player_id:
        return False
    for registration in map(_dict, _list(_dict(event).get("registrations"))):
        if _text(_dict(registration.get("driver")).get("id")) == player_id:
            return True
        lineup = _dict(_dict(registration.get("team")).get("lineup"))
        if any(_text(_dict(driver).get("driverId")) == player_id for driver in _list(lineup.get("drivers"))):
            return True
    return False


def mark_registered(value: Any, player_id: str) -> Any:
    """Answers with "registered": true on each event whose registrations hold the player (marked before the disk
    copy counts registrations: the mark is kept, names never)"""
    if not player_id:
        return value
    if isinstance(value, dict):
        result = {key: mark_registered(item, player_id) for key, item in value.items()}
        if isinstance(value.get("registrations"), list) and is_registered(value, player_id):
            result["registered"] = True
        return result
    if isinstance(value, list):
        return [mark_registered(item, player_id) for item in value]
    return value


def _event_cars(event: Any) -> list[dict]:
    return list(map(_dict, _list(_dict(_dict(_dict(event).get("configuration")).get("content")).get("cars"))))


def _veh_name(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def car_choices(event: Any, game_cars: Any) -> tuple[CarChoice, ...]:
    """Liveries of an event (overview answer) the player owns in the game (/rest/race/car), by class, model &
    livery; custom team liveries left out (registered through the team car flow of the game menu)"""
    allowed: dict[str, str] = {}
    for car in _event_cars(event):
        for item in map(_dict, _list(car.get("subItems"))):
            veh, name = _text(item.get("veh")), _text(item.get("name"))
            if veh and "custom team" not in name.casefold():
                allowed.setdefault(veh.lower(), name)
    choices: dict[str, CarChoice] = {}
    for item in map(_dict, _list(game_cars)):
        veh = _veh_name(_text(item.get("vehFile")))
        livery = allowed.get(veh.lower())
        tree = [part.strip() for part in _text(item.get("fullPathTree")).split(",")]
        if item.get("owned") is not True or livery is None or len(tree) < 2 or not tree[1]:
            continue
        model = tree[2] if len(tree) > 2 and tree[2] else _text(item.get("manufacturer"))
        choices.setdefault(veh.lower(), CarChoice(veh, tree[1], model, livery or _text(item.get("name"))))
    return tuple(sorted(choices.values(),
                        key=lambda car: (car.vehicle_class.casefold(), car.model.casefold(), car.livery.casefold())))


def register_request(event: Any, choice: CarChoice) -> dict | None:
    """Registration of the player to an event (overview answer) with a livery, None if the event does not allow it
    (livery not in its list, team event, no id)"""
    event = _dict(event)
    event_type, event_id = _text(event.get("type")), _text(event.get("id"))
    if not event_type or not event_id or event.get("teamEvent") is True:
        return None
    for car in _event_cars(event):
        items = [item for item in map(_dict, _list(car.get("subItems")))
                 if _text(item.get("veh")).lower() == choice.veh.lower()]
        if items:
            return {"eventType": event_type, "eventId": event_id, "carClass": choice.vehicle_class,
                    "car": {**car, "subItems": items[:1]}, "team": None}
    return None


def answer_ok(status: int, answer: Any) -> bool:
    """Registration (or leave) accepted: answered 200 with status OK"""
    return status == 200 and _text(_dict(answer).get("status")).upper() == "OK"


def answer_message(answer: Any) -> str:
    """Why RaceControl refused: message & first error of its answer, "" if none"""
    data = _dict(answer)
    errors = [text for text in map(_text, _list(data.get("errors"))) if text]
    return " ".join(part for part in (_text(data.get("message")), errors[0] if errors else "") if part)


def with_registered(schedule: Schedule, registered: dict[str, bool]) -> Schedule:
    """Schedule with the player registered (or not) to the starts of these event ids (registered or left from the
    page: told at once, before RaceControl lists answer it)"""
    if not registered:
        return schedule
    changed = False
    events = []
    for event in schedule.events:
        starts = tuple(start._replace(registered=registered[start.event_id])
                       if start.event_id in registered and start.registered != registered[start.event_id] else start
                       for start in event.starts)
        if starts != event.starts:
            changed = True
            event = event._replace(starts=starts)
        events.append(event)
    return schedule._replace(events=tuple(events)) if changed else schedule


# Your race followed live (see ui/quick/race_watch.py), game menu request: GET api/v1/event/my-split/<event type>/
# <event id> -> {splitNo, numOfSplits, server {host, port, password, auth}} (500 when not registered); the game menu
# lets you join once host & password are given. Address & password never kept: ready or not.
SPLIT_ROUTE = "api/v1/event/my-split"


class SplitState(NamedTuple):
    """Server of your split of a race: ready to join, split number & count (0 unknown)"""

    ready: bool
    split: int = 0
    splits: int = 0


def parse_split(data: Any) -> SplitState | None:
    """Your split (my-split answer), None if not answered"""
    if not isinstance(data, dict):
        return None
    server = _dict(data.get("server"))
    return SplitState(bool(_text(server.get("host"))) and bool(_text(server.get("password"))),
                      _int(data.get("splitNo")), _int(data.get("numOfSplits")))


def event_cancelled(event: Any) -> bool:
    """Event (overview answer) cancelled by RaceControl"""
    return _text(_dict(event).get("status")).casefold() in ("cancelled", "canceled")


def race_end(event: Event, start: Start) -> float:
    """End of a start (practice start + whole length), the start itself if its length is unknown"""
    return start.time + (event.total or event.race_seconds)
