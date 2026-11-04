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
Online races to come of Le Mans Ultimate, shared by Home & the Upcoming Races page

Read from RaceControl signed in with the game (option enable_online_driver_ranks, same sign in as the online
ranks, see rank_info.py & process/race_schedule.py), at most every READ_SECONDS while a page shows them. Last read
kept in memory & on disk (trimmed: no player names, no server addresses), shown while the game is closed.
"""

from __future__ import annotations

import contextlib
import logging
import math
import os
import threading
import time
from typing import Any, NamedTuple

from . import net_policy as policy
from .process import race_schedule as rs
from .setting import cfg

logger = logging.getLogger(__name__)

CACHE_FILE = ".race_schedule.json"
READ_SECONDS = policy.SCHEDULE_READ_SECONDS
LIVE_READ_SECONDS = policy.SCHEDULE_LIVE_READ_SECONDS
RETRY_SECONDS = policy.SCHEDULE_RETRY_SECONDS
FAILED_MAX_SECONDS = policy.SCHEDULE_FAILED_MAX_SECONDS
FAIL_STREAK = policy.SCHEDULE_FAIL_STREAK
GAME_LISTS_AGE = policy.SCHEDULE_GAME_LISTS_AGE
KEEP_ANSWER_SECONDS = policy.SCHEDULE_KEEP_ANSWER_SECONDS
# Routes that rarely change: read again only this late (a refresh asked on the page reads them all), hosted servers
# only while the Upcoming Races page shows
SLOW_ROUTES = frozenset(("schedule", "weekly", "special", "championships", "championships_upcoming", "coop"))
SLOW_ROUTE_SECONDS = policy.SCHEDULE_SLOW_ROUTE_SECONDS
# Routes only the Upcoming Races page shows (never asked for Home, Driver Stats or the race watch); hosted servers
# only while their tab shows
PAGE_ROUTES = frozenset(("championships", "championships_upcoming", "coop", "hosted"))
FRESH_MARGIN = policy.SCHEDULE_FRESH_MARGIN
# Routes whose answer changes at a moment it tells (seen 2026-11-03 in answers of RaceControl): read again at it
SCHEDULE_MAX_SECONDS = policy.SCHEDULE_MAX_SECONDS
ROUND_MAX_SECONDS = policy.SCHEDULE_ROUND_MAX_SECONDS
ROUND_MARGIN = policy.SCHEDULE_ROUND_MARGIN
NO_SPECIAL_STATUS = 500  # special events answer this when there is none: kept as an empty list like any answer
FORCE_SECONDS = policy.SCHEDULE_FORCE_SECONDS
# Routes each tab of the Upcoming Races page shows (Read Again asks the tab shown only, not the 10 routes)
TAB_ROUTES: dict[str, frozenset[str]] = {
    "daily": frozenset(("schedule", "daily_beginner", "daily_intermediate", "daily_advanced")),
    "events": frozenset(("weekly", "special")),
    "championships": frozenset(("championships", "championships_upcoming")),
    "coop": frozenset(("coop",)),
    "servers": frozenset(("hosted",)),
}

# Status of last read
READ = "read"  # read from RaceControl
OFF = "off"  # option enable_online_driver_ranks off
NO_GAME = "no_game"  # game not running (no sign in ticket)
NO_ACCOUNT = "no_account"  # no RaceControl account for this player
FAILED = "failed"  # signed in, nothing answered


class State(NamedTuple):
    schedule: rs.Schedule
    status: str  # READ, OFF, NO_GAME, NO_ACCOUNT, FAILED, "" before any read
    tried: float  # monotonic time of last read try, -1 if none
    serial: int  # changed when schedule or status changed
    disk_tried: float = -1.0  # monotonic time the disk copy was read from RaceControl, -1 if none
    failures: int = 0  # reads in a row signed in but nothing answered (FAILED)


_state = State(rs.EMPTY, "", -1.0, 0)
_lock = threading.Lock()  # one read at a time
_disk_read = False
_disk_account = ""  # game account the disk copy shown was read for, "" if told or not known yet
# Answers the schedule shown was made from: schedule, ROUTES key -> (read time since epoch, answer)
_answers: tuple[rs.Schedule | None, dict[str, tuple[float, object]]] = (None, {})


def cache_path() -> str:
    return os.path.join(cfg.path.config, CACHE_FILE)


def enabled() -> bool:
    from .rank_info import online_enabled

    return online_enabled()


def state() -> State:
    """Last schedule read & status (any thread: replaced whole)"""
    return _state


def _set(schedule: rs.Schedule, status: str, tried: float, failures: int | None = None) -> None:
    """State replaced (failures: kept when None)"""
    global _state
    old = _state
    serial = old.serial + (schedule is not old.schedule or status != old.status)
    _state = State(schedule, status, tried, serial, failures=old.failures if failures is None else failures)


def _kept_answers(answers: dict, now: float, fresh: set[str] | frozenset[str] = frozenset()) -> dict:
    """Answers of routes not answered now, from the schedule shown if read less than KEEP_ANSWER_SECONDS ago (routes
    not asked because their answer is still fresh: whatever its age, see _is_fresh)"""
    schedule, known = _answers
    if schedule is not _state.schedule:
        return {}
    return {key: answer for key, (read_time, answer) in known.items()
            if answers.get(key) is None and (key in fresh or 0 <= now - read_time < KEEP_ANSWER_SECONDS)}


def _remember(schedule: rs.Schedule, answers: dict, read_time: float, kept: dict,
              times: dict[str, float] | None = None) -> None:
    """Answers a schedule was made from: answered now (times: own read time of each, from a disk copy), or kept
    with their own read time"""
    global _answers
    known = {key: ((times or {}).get(key, read_time), answer) for key, answer in answers.items()
             if answer is not None}
    known.update((key, _answers[1][key]) for key in kept)
    _answers = (schedule, known)


def load_disk() -> None:
    """Schedule of last run read from disk, once (worker thread)"""
    global _disk_read, _disk_account, _state
    if _disk_read:
        return
    _disk_read = True
    with _results_lock:
        _disk_store("")  # online option off: file of the online races removed
    from .rank_info import ranks
    from .userfile import read_json

    saved = read_json(cache_path(), default=None, dict_only=True)
    found = rs.from_cache(saved)
    if found is None or _state.schedule.read_time:
        return
    saved_account, account = rs.cache_account(saved), ranks.account
    if saved_account and account and saved_account != account:  # read for another Steam account: its registrations
        logger.info("RACE SCHEDULE: saved schedule of another game account ignored")
        return
    _disk_account = saved_account
    answers, cars, tracks, read_time = found
    try:
        schedule = rs.parse_schedule(answers, cars, tracks, read_time)
    except (TypeError, ValueError, AttributeError) as error:  # file edited by hand
        logger.info("RACE SCHEDULE: saved schedule unreadable: %s", error)
        return
    _set(schedule, _state.status, _state.tried)
    age = time.time() - read_time
    if 0 <= age < KEEP_ANSWER_SECONDS:  # recent copy: counts as a read (an app restart asks nothing at once)
        _state = _state._replace(disk_tried=time.monotonic() - age)
    # kept after a restart too, each with the time it was read (not the time the copy was written)
    _remember(schedule, answers, read_time, {}, rs.cache_times(saved, answers, read_time))


def _check_disk_account(account: str) -> None:
    """Disk copy shown before the game account was known: dropped when it was read for another one (called with the
    lock held)"""
    global _answers, _disk_account, _state
    if not _disk_account or not account:
        return
    other = _disk_account != account
    _disk_account = ""
    if other:
        logger.info("RACE SCHEDULE: saved schedule of another game account dropped")
        _answers = (None, {})
        _state = State(rs.EMPTY, _state.status, _state.tried, _state.serial + 1, -1.0, _state.failures)


def _busy_for(client=None) -> float:
    """Seconds RaceControl asked to wait (429: too many requests) still to run, 0 if none"""
    if client is None:
        from .rank_info import online_client

        client = online_client()
    busy_for = getattr(client, "busy_for", None)  # client of tests without it: never asked to wait
    return busy_for() if busy_for is not None else 0.0


def read_seconds(live: bool) -> float:
    """Seconds between two reads (LIVE_READ_SECONDS while the Upcoming Races page shows), twice as long in economy mode"""
    return policy.stretch(LIVE_READ_SECONDS if live else READ_SECONDS)


def due(now: float | None = None, live: bool = False) -> bool:
    """Time to read again (never read, or last read old enough: LIVE_READ_SECONDS when live, the Upcoming Races
    page shown), never while RaceControl asks to wait"""
    current = _state
    now = time.monotonic() if now is None else now
    if _busy_for() > 0:
        return False
    if current.tried < 0:  # not read in this run: read unless the disk copy is recent
        return current.disk_tried < 0 or now - current.disk_tried >= read_seconds(live)
    if current.status == READ:
        wait = read_seconds(live)
    elif current.status == FAILED:  # RaceControl signed in, nothing answered: asked less and less often
        wait = min(RETRY_SECONDS * 2 ** min(max(current.failures, 1) - 1, 8), FAILED_MAX_SECONDS)
    else:
        wait = RETRY_SECONDS
    return now - current.tried >= wait


def _known() -> dict[str, tuple[float, object]]:
    """ROUTES key -> (read time, answer) of the schedule shown"""
    schedule, known = _answers
    return known if schedule is _state.schedule else {}


def hosted_stale(now: float | None = None) -> bool:
    """Hosted servers not read, or read LIVE_READ_SECONDS ago (their tab shown: read again)"""
    found = _known().get("hosted")
    now = time.time() if now is None else now
    return found is None or not 0 <= now - found[0] < policy.stretch(LIVE_READ_SECONDS) - FRESH_MARGIN


def _fresh_routes(now: float, live: bool, servers: bool) -> set[str]:
    """Routes not asked this read (now in seconds since epoch): answered recently enough (SLOW_ROUTES within
    SLOW_ROUTE_SECONDS, others within their read interval), routes of the page while it is hidden, hosted servers
    while their tab is not shown"""
    known = _known()
    interval = read_seconds(live) - FRESH_MARGIN
    fresh = set()
    for key in rs.ROUTES:
        if key in PAGE_ROUTES and (not live or (key == "hosted" and not servers)):
            fresh.add(key)
            continue
        found = known.get(key)
        if found is not None and _is_fresh(key, found, now, interval, live):
            fresh.add(key)
    return fresh


def _is_fresh(key: str, found: tuple[float, object], now: float, interval: float, live: bool) -> bool:
    """Answer (read time, answer) of a route not to ask again at `now`: the daily schedule until midnight UTC, active
    championships until their current round ends, daily lists of a tier for one race slot (page shown), other slow
    routes SLOW_ROUTE_SECONDS, the rest within the read interval"""
    read_time, answer = found
    age = now - read_time
    if age < 0:
        return False
    if key == "schedule":
        return read_time // 86400 == now // 86400 and age < SCHEDULE_MAX_SECONDS
    if key == "championships":
        return age < ROUND_MAX_SECONDS and now < rs.next_round_change(answer, read_time) + ROUND_MARGIN
    if key in SLOW_ROUTES:
        return age < policy.stretch(SLOW_ROUTE_SECONDS)
    if live and key.startswith("daily_"):  # the 3 next races of a tier move on at each race slot (15, 20, 30 minutes)
        slot = _state.schedule.frequency.get(key.removeprefix("daily_"), 0.0)
        return age < max(interval, slot - FRESH_MARGIN)
    return age < interval


def read(force: bool = False, live: bool = False, servers: bool = False, tab: str = "") -> State:
    """Read RaceControl if due (force: now and every route (tab: the routes of that tab of the page only), but never
    twice within FORCE_SECONDS, live: page shown,
    servers: its Hosted Servers tab shown, read once their answer is old, see due), only routes not answered
    recently (see _fresh_routes), blocking (worker thread); state after it"""
    with _lock:
        load_disk()
        if (force and enabled() and _state.status in (READ, FAILED) and _state.tried >= 0
                and time.monotonic() - _state.tried < FORCE_SECONDS):
            force = False  # RaceControl asked again at once: read only when due (game closed: nothing was asked)
        if not force and not due(live=live) and not (live and servers and hosted_stale()):
            return _state
        now = time.monotonic()
        if not enabled():
            _set(_state.schedule, OFF, now, 0)
            return _state
        from .rank_info import online_client, ranks

        client = online_client()
        if _busy_for(client) > 0:  # RaceControl asked to wait (429): nothing asked, read once the wait is over
            return _state
        account = ranks.account
        _check_disk_account(account)
        fresh = _fresh_routes(time.time(), live, servers) if not force else (
            set(rs.ROUTES) - TAB_ROUTES[tab] if tab in TAB_ROUTES else set())
        if not set(rs.ROUTES) - fresh:  # every answer recent: nothing asked
            _set(_state.schedule, _state.status, now)
            return _state
        get_status = getattr(client, "get_status", None)  # client of tests without it: special read like the others

        def get(path: str):
            if path != rs.ROUTES["special"] or get_status is None:
                return client.get(path, account)
            status, answer = get_status(path, account)
            return [] if status == NO_SPECIAL_STATUS else answer  # none to come: not asked again before its turn

        # rest not asked after a 429, nor once FAIL_STREAK routes in a row gave nothing (RaceControl down)
        answers = rs.read_answers(get, fresh, FAIL_STREAK)
        player = getattr(client, "player", ("", ""))[0]  # races the player is registered to marked (names dropped)
        answers = {key: rs.mark_registered(answer, player) for key, answer in answers.items()}
        if all(answer is None for answer in answers.values()):
            status = NO_ACCOUNT if client.no_account else NO_GAME if not _game_running() else FAILED
            _set(_state.schedule, status, now, _state.failures + 1 if status == FAILED else 0)
            return _state
        cars, tracks = _game_lists()
        old = _state.schedule
        read_time = time.time()
        kept = _kept_answers(answers, read_time, fresh)  # routes not answered now: last answer still recent
        try:
            schedule = rs.parse_schedule({**answers, **kept}, cars or old.cars, tracks or old.tracks, read_time)
        except Exception as error:  # answer the parser cannot read: old schedule kept, tried again like a failure
            logger.info("RACE SCHEDULE: answers unreadable: %r", error)
            _set(old, FAILED, now, _state.failures + 1)
            return _state
        # Routes not answered now told missing, even shown from a kept answer (reminders never judged on them);
        # routes not asked (recent answer) are not missing
        schedule = schedule._replace(missing=tuple(key for key in rs.ROUTES
                                                   if answers.get(key) is None and key not in fresh))
        # Registered or left from the page: told until RaceControl lists agree
        schedule = rs.with_registered(schedule, _registered_now(schedule))
        _remember(schedule, answers, read_time, kept)
        _set(schedule, READ, now, 0)
        # disk copy: every answer the schedule was made from, with the time each was read
        _save({key: found[1] for key, found in _answers[1].items()}, schedule,
              {key: found[0] for key, found in _answers[1].items()}, account)
        return _state


# Details read on demand (worker thread), never kept on disk: None when not read
FIELD_TAKE = 100  # drivers per page of an entry list
FIELD_PAGES = 5  # pages read at most (500 drivers)
COOP_TAKE = 100
COOP_PAGES = 5
BACKGROUND_RESERVE = 4  # requests a minute background reads leave to the player's own asks (register, leave, details)


def room() -> int:
    """Requests background reads (your places, live fields) may still send now: they stop at 0 and ask the rest
    later (RaceControl limits: requests refused, none sent)"""
    if not enabled():
        return 0
    from .rank_info import online_client

    return max(online_client().room() - BACKGROUND_RESERVE, 0)


def _get(path: str):
    if not enabled():
        return None
    from .rank_info import online_client, ranks

    return online_client().get(path, ranks.account)


def read_field(entry_type: str, event_id: str) -> rs.FieldLevel | None:
    """Drivers registered to a start (counts only, names dropped at once)"""
    from urllib.parse import quote

    pages = []
    for page in range(1, FIELD_PAGES + 1):
        answer = _get(f"api/v1/event/entries/{quote(entry_type)}/{quote(event_id)}?page={page}&take={FIELD_TAKE}")
        if not isinstance(answer, list):
            if page == 1:
                return None
            break
        pages.append(answer)
        if len(answer) < FIELD_TAKE:
            return rs.parse_field(pages, True)
    return rs.parse_field(pages, len(pages) < FIELD_PAGES)


def read_practice(event: rs.Event) -> tuple[rs.PracticeServer, ...] | None:
    """Practice servers of a daily, weekly or special race (players & end only), as the game lists them. Practice+
    servers (RaceControl Pro) not asked: refused without the subscription, and a refusal stops every request"""
    from urllib.parse import quote

    answer = _get(f"api/v1/practice/servers/{quote(event.entry_type)}/{quote(event.practice_tier)}"
                  f"?eventTitle={quote(event.title)}")
    return rs.parse_practice(answer) if isinstance(answer, list) else None


def read_championship(key: str, round_number: int) -> rs.ChampionshipDetail | None:
    """Sessions of the current round with registrations, attempts & practice servers of a championship"""
    from urllib.parse import quote

    detail = _get(f"api/v1/championship/{quote(key)}")
    if not isinstance(detail, dict):
        return None
    practice = _get(f"api/v1/championships/{quote(key)}/practice/{round_number}") if round_number > 0 else None
    return rs.parse_championship_detail(detail, practice)


def read_coop_board(name: str, player: str) -> rs.CoopBoard | None:
    """Best teams of a co-op event & the player's entry (pages read until found)"""
    from urllib.parse import quote

    pages = []
    for page in range(1, COOP_PAGES + 1):
        answer = _get(f"api/v1/coop/event/leaderboard/list?eventName={quote(name)}&page={page}&take={COOP_TAKE}")
        if not isinstance(answer, dict):
            if page == 1:
                return None
            break
        pages.append(answer)
        board = rs.parse_coop_board(pages, player)
        if board.mine is not None or len(answer.get("entries") or []) < COOP_TAKE:
            return board
    return rs.parse_coop_board(pages, player)


LEADERBOARD_ROUTE = "api/v1/leaderboards/results-for-users"
LEADERBOARD_PAGE = 100  # drivers per page (most RaceControl gives)
RESULTS_TAKE = 5  # online races per page of the results history (answers are heavy: full classifications)


def _post(path: str, payload) -> object:
    if not enabled():
        return None
    from .rank_info import online_client, ranks

    return online_client().post(path, payload, ranks.account)


def player_id() -> str:
    """RaceControl id of the player (last sign in), "" if not signed in yet"""
    from .rank_info import online_client

    return online_client().player[0]


def player_name() -> str:
    """RaceControl name of the player (last sign in), "" if not signed in yet"""
    from .rank_info import online_client

    return online_client().player[1]


def results_take(event_type: str) -> int:
    """Online races asked per page: 24 h races weigh several MB each"""
    return 2 if event_type == "specialevent" else RESULTS_TAKE


def read_leaderboard(board: rs.Board, vehicle_class: str = "", page: int = 1) -> rs.Leaderboard | None:
    """Page of the weekly leaderboard of a race (fastest laps), all classes or one"""
    return rs.parse_leaderboard(_post(LEADERBOARD_ROUTE, board.request(
        rs.leaderboard_class(vehicle_class), max(page, 1), LEADERBOARD_PAGE)))


def read_place(board: rs.Board, vehicle_class: str = "") -> tuple[int, int] | None:
    """Rank of the player in a weekly leaderboard & drivers ranked: (0, count) if not ranked, None if not read"""
    if not player_id():
        _get(rs.ROUTES["schedule"])  # signs in (player id of the answer)
    me = player_id()
    if not me:
        return None
    board_class = rs.leaderboard_class(vehicle_class)
    around = rs.parse_leaderboard(_post(LEADERBOARD_ROUTE, board.request(board_class, limit=1, around=me)))
    if around is None:
        return None
    rank = next((entry.rank for entry in around.entries if entry.player_id == me), 0)
    if rank:  # count of an "around" answer: of the entries given, page 1 tells the whole board
        whole = rs.parse_leaderboard(_post(LEADERBOARD_ROUTE, board.request(board_class, 1, 1)))
        return rank, whole.drivers if whole is not None else 0
    return 0, 0


def read_places(boards: dict[str, rs.Board], asked: set[str] | None = None) -> dict[str, tuple[int, int]]:
    """Rank of the player in the weekly leaderboard of each race (by key), races not read left out; stops once
    room() lacks the 2 requests of a place (asked: keys asked added, the others to ask later)"""
    places = {}
    for key, board in boards.items():
        if room() < 2:
            break
        if asked is not None:
            asked.add(key)
        place = read_place(board)
        if place is not None:
            places[key] = place
    return places


_places: dict[str, tuple[int, int]] = {}  # your places last read (leaderboard key -> rank, drivers ranked)


def set_places(places: dict[str, tuple[int, int]]) -> None:
    """Your places in the weekly leaderboards (read by the Upcoming Races page), told on the Home card"""
    global _places
    _places = dict(places)


def places() -> dict[str, tuple[int, int]]:
    return _places


class PageMemory:
    """What the Upcoming Races page asked RaceControl, kept while the page is released & made again (released after
    a while hidden): an opened page never asks every leaderboard place again"""

    def __init__(self) -> None:
        self.places_time = -math.inf  # monotonic time your places were last asked, -inf if never
        self.places_left: dict[str, rs.Board] = {}  # leaderboards not asked at the last read (RaceControl limits)
        self.unranked: dict[str, float] = {}  # leaderboard key -> monotonic time your place was found 0
        self.field_misses: dict[str, int] = {}  # event id -> live reads in a row not answered (forbidden list)


_page_memory: tuple[object, PageMemory] | None = None  # RaceControl client & memory of its requests


def page_memory() -> PageMemory:
    """Memory of the Upcoming Races page: one per RaceControl client (the app's own; tests: one per fake client)"""
    global _page_memory
    from .rank_info import online_client

    client = online_client()
    if _page_memory is None or _page_memory[0] is not client:
        _page_memory = (client, PageMemory())
    return _page_memory[1]


FRIENDS_SECONDS = policy.SCHEDULE_FRIENDS_SECONDS
_friends: tuple[float, tuple[rs.Friend, ...]] = (-FRIENDS_SECONDS, ())


def read_friends() -> tuple[rs.Friend, ...]:
    """Your RaceControl friends (Steam friends playing LMU), kept FRIENDS_SECONDS in memory"""
    global _friends
    now = time.monotonic()
    if now - _friends[0] < FRIENDS_SECONDS:
        return _friends[1]
    answer = _post("api/v1/player/friends-list", {"platform": "steam", "game": "lmu", "sync": False})
    if answer is None:
        return _friends[1]
    _friends = (now, rs.parse_friends(answer))
    return _friends[1]


def read_friend_places(board: rs.Board, vehicle_class: str = "") -> list[rs.LeaderEntry]:
    """Entries of you & your friends ranked in a weekly leaderboard (one ask each), fastest first"""
    board_class = rs.leaderboard_class(vehicle_class)
    people = [rs.Friend(player_id(), "")] if player_id() else []
    found = []
    for friend in (*people, *read_friends()):
        around = rs.parse_leaderboard(_post(LEADERBOARD_ROUTE, board.request(board_class, limit=1,
                                                                              around=friend.player_id)))
        found += [entry for entry in (around.entries if around is not None else ())
                  if entry.player_id == friend.player_id]
    return sorted(found, key=lambda entry: entry.rank)


def read_profile(name: str) -> rs.Profile | None:
    """Public profile of a driver by name (RaceControl players)"""
    answer = _post("api/v1/players", {"usernames": [name.split("#", 1)[0].strip()]})
    return rs.parse_profile(answer, name)


def find_driver(board: rs.Board, vehicle_class: str, name: str) -> int:
    """Rank of a driver (by name) in a weekly leaderboard, 0 if not found"""
    answer = _post("api/v1/players", {"usernames": [name.split("#", 1)[0].strip()]})
    key = name.split("#", 1)[0].strip().casefold()
    ids = [str(item.get("id")) for item in (answer if isinstance(answer, list) else ())
           if isinstance(item, dict) and str(item.get("name", "")).split("#", 1)[0].strip().casefold() == key]
    for driver_id in ids[:3]:
        around = rs.parse_leaderboard(_post(LEADERBOARD_ROUTE, board.request(
            rs.leaderboard_class(vehicle_class), limit=1, around=driver_id)))
        rank = next((entry.rank for entry in (around.entries if around else ()) if entry.player_id == driver_id), 0)
        if rank:
            return rank
    return 0


CHAMPIONSHIP_PAGES = 4  # pages of your championship races read to find the races of one championship


def read_championship_results(name: str) -> list[rs.OnlineResult] | None:
    """Your races of a championship (titles "<name>: Week <n>"), newest first"""
    found: list[rs.OnlineResult] = []
    key = name.casefold()
    for page in range(1, CHAMPIONSHIP_PAGES + 1):
        results = read_results("championship", page)
        if results is None:
            return found or None
        found += [result for result in results if result.title.casefold().startswith(key)]
        # end of the list told by the races answered (a race may be unreadable)
        answered = results.answered if isinstance(results, ResultsPage) else len(results)
        if answered < results_take("championship"):
            break
    return found


# Online races read, kept in memory while the app runs and on disk (RESULTS_FILE, names of drivers included: your
# choice of 2026-11-04, see the online results options of the wiki): a race over for a day no longer changes (rank
# changes & penalties settled), asking it again at each opening of the page was a 335 KB page of 5 races, 174 KB for
# the laps of one. The file is tied to the game account, bounded, removed when the online option is turned off.
RESULTS_SETTLED_SECONDS = policy.SCHEDULE_RESULTS_SETTLED_SECONDS
RESULTS_KEEP = policy.SCHEDULE_RESULTS_KEEP
RACES_KEEP = policy.SCHEDULE_RACES_KEEP
_results_lock = threading.Lock()
_page_heads: dict[str, str] = {}  # event type -> newest race of page 1 last read
_kept_pages: dict[tuple[str, int], tuple[str, ResultsPage]] = {}  # (event type, page) -> head when read, page
_kept_races: dict[tuple[str, int], rs.OnlineResult] = {}  # (event id, split) -> race with its laps
RESULTS_FILE = ".online_results.json"
RESULTS_FILE_VERSION = 1
_disk_results: dict[str, Any] | None = None  # file read once: {"account", "races": {path: answer}, "pages": {...}}


def _results_path() -> str:
    return os.path.join(cfg.path.config, RESULTS_FILE)


def _disk_store(account: str) -> dict[str, Any] | None:
    """Settled answers kept on disk for the game account (read once), None while the account is not known or the online
    option is off (the file is removed then). Call with _results_lock held."""
    global _disk_results
    if not enabled():
        if _disk_results is not None or os.path.isfile(_results_path()):
            _disk_results = None
            with contextlib.suppress(OSError):
                os.remove(_results_path())
        return None
    if not account:
        return None
    if _disk_results is None or _disk_results.get("account") != account:
        from .userfile import read_json

        saved = read_json(_results_path(), default=None, dict_only=True)
        valid = (isinstance(saved, dict) and saved.get("version") == RESULTS_FILE_VERSION
                 and saved.get("account") == account and isinstance(saved.get("races"), dict)
                 and isinstance(saved.get("pages"), dict))
        _disk_results = ({"account": account, "races": dict(saved["races"]), "pages": dict(saved["pages"])}
                         if valid else {"account": account, "races": {}, "pages": {}})
    return _disk_results


def _disk_save(store: dict[str, Any]) -> None:
    from .userfile import write_json

    try:
        write_json(_results_path(), {"version": RESULTS_FILE_VERSION, **store}, fsync=False)
    except (OSError, TypeError, ValueError) as error:
        logger.info("RACE SCHEDULE: online results not saved: %s", error)


def _account() -> str:
    from .rank_info import ranks

    return ranks.account


def read_result(event_id: str, split: int) -> rs.OnlineResult | None:
    """One online race with its laps (the results history gives none), None if not read; a race over for a day is
    kept in memory (RACES_KEEP)"""
    from urllib.parse import quote

    key = (event_id, max(split, 1))
    path = f"api/v1/result?eventId={quote(event_id)}&splitNo={key[1]}"
    account = _account()
    with _results_lock:
        kept = _kept_races.pop(key, None)
        if kept is not None:
            _kept_races[key] = kept  # most recently used last
            return kept
        store = _disk_store(account)
        saved = store["races"].get(path) if store is not None else None
    answer = saved if saved is not None else _get(path)
    found = rs.parse_result(answer)
    if found is None and saved is not None:  # copy on disk not valid: read again
        found = rs.parse_result(answer := _get(path))
        saved = None
    if found is not None and time.time() - found.time >= RESULTS_SETTLED_SECONDS:
        with _results_lock:
            _kept_races[key] = found
            while len(_kept_races) > RACES_KEEP:
                del _kept_races[next(iter(_kept_races))]
            store = _disk_store(account)
            if store is not None and saved is None:
                store["races"].pop(path, None)
                store["races"][path] = answer
                while len(store["races"]) > RACES_KEEP:
                    del store["races"][next(iter(store["races"]))]
                _disk_save(store)
    return found


class ResultsPage(list[rs.OnlineResult]):
    """Online races of a results page read & races answered (a race may be unreadable: last page when fewer answered
    than results_take)"""

    answered = 0


def read_results(event_type: str, page: int = 1) -> ResultsPage | None:
    """Page of the online races the player drove (newest first) with their classifications"""
    from urllib.parse import quote

    page = max(page, 1)
    take = results_take(event_type)
    disk_key = f"{event_type}/{page}/{take}"
    account = _account()
    with _results_lock:
        head = _page_heads.get(event_type, "")
        kept = _kept_pages.get((event_type, page)) if page > 1 else None
        if kept is not None and head and kept[0] == head:  # no race added since: the page is the same
            copy = ResultsPage(kept[1])
            copy.answered = kept[1].answered
            return copy
        store = _disk_store(account) if page > 1 and head else None
        saved = store["pages"].get(disk_key) if store is not None else None
    if isinstance(saved, dict) and saved.get("head") == head and isinstance(saved.get("answer"), list):
        found = _results_page(saved["answer"])  # settled when saved, no race added since
        if found.answered == len(found):
            with _results_lock:
                _kept_pages[(event_type, page)] = (head, found)
            return found
    answer = _get(f"api/v1/results?eventType={quote(event_type)}&page={page}&take={take}")
    if not isinstance(answer, list):
        return None
    found = _results_page(answer)
    with _results_lock:
        if page == 1:  # newest race of the list: a race driven since moves every later page
            new_head = f"{found[0].event_id}/{found[0].split}" if found else ""
            if new_head != _page_heads.get(event_type, ""):
                for key in [key for key in _kept_pages if key[0] == event_type]:
                    del _kept_pages[key]
            _page_heads[event_type] = new_head
        elif (_page_heads.get(event_type) and found and found.answered == len(found)
              and all(time.time() - result.time >= RESULTS_SETTLED_SECONDS for result in found)):
            _kept_pages[(event_type, page)] = (_page_heads[event_type], found)
            while sum(len(item[1]) for item in _kept_pages.values()) > RESULTS_KEEP and len(_kept_pages) > 1:
                del _kept_pages[next(iter(_kept_pages))]
            store = _disk_store(account)
            if store is not None:
                heads = _page_heads[event_type]
                for old in [name for name, item in store["pages"].items()  # pages of an earlier head: no longer valid
                            if name.split("/", 1)[0] == event_type and item.get("head") != heads]:
                    del store["pages"][old]
                store["pages"].pop(disk_key, None)
                store["pages"][disk_key] = {"head": heads, "answer": answer}
                while len(store["pages"]) > 1 and sum(
                        len(item["answer"]) for item in store["pages"].values()) > RESULTS_KEEP:
                    del store["pages"][next(iter(store["pages"]))]
                _disk_save(store)
    return found


def _results_page(answer: list) -> ResultsPage:
    found = ResultsPage(result for result in map(rs.parse_result, answer) if result is not None)
    found.answered = len(answer)
    return found


def unread_status() -> str:
    """Why a detail was not read (OFF, NO_ACCOUNT, NO_GAME or FAILED, see read), blocking (worker thread: the game
    is asked)"""
    if not enabled():
        return OFF
    from .rank_info import online_client

    return NO_ACCOUNT if online_client().no_account else NO_GAME if not _game_running() else FAILED


def _game_running() -> bool:
    from .rank_info import OnlineRanks

    return OnlineRanks.game_running()


def _game_lists() -> tuple[dict[str, rs.CarInfo], dict[str, rs.TrackInfo]]:
    """Cars & tracks of the game (class, names & owned), empty if not answered"""
    from .game_rest_cache import rest_cache

    return (rs.parse_car_catalog(rest_cache.json("/rest/race/car", GAME_LISTS_AGE)),
            rs.parse_track_catalog(rest_cache.json("/rest/race/track", GAME_LISTS_AGE)))


def _save(answers: dict, schedule: rs.Schedule, times: dict[str, float], account: str = "") -> None:
    from .userfile import write_json

    try:
        write_json(cache_path(), rs.cache_data(answers, schedule.cars, schedule.tracks, schedule.read_time, times,
                                               account),
                   fsync=False, raise_error=True)
    except (OSError, TypeError, ValueError) as error:
        logger.info("RACE SCHEDULE: schedule not saved: %s", error)


# Registration asked from the page (worker thread), see process/race_schedule.py "Registration"
REGISTERED_SECONDS = policy.SCHEDULE_REGISTERED_SECONDS

_registered: dict[str, tuple[bool, float]] = {}  # event id -> registered, monotonic time of the change
_registered_lock = threading.Lock()


def _registered_now(schedule: rs.Schedule | None = None) -> dict[str, bool]:
    """Registrations changed from the page that RaceControl lists may not give yet: each dropped once a read agrees
    with it (schedule), or REGISTERED_SECONDS after it"""
    now = time.monotonic()
    seen = {start.event_id: start.registered for event in schedule.events for start in event.starts
            if start.event_id} if schedule is not None else {}
    with _registered_lock:
        for event_id, (value, changed) in list(_registered.items()):
            if now - changed >= REGISTERED_SECONDS or seen.get(event_id) == value:
                del _registered[event_id]
        return {event_id: value for event_id, (value, _changed) in _registered.items()}


def _set_registered(event_id: str, value: bool) -> None:
    """Start of event_id told registered (or not) at once on the schedule shown"""
    global _answers
    with _registered_lock:
        _registered[event_id] = (value, time.monotonic())
    current = _state
    schedule = rs.with_registered(current.schedule, {event_id: value})
    _set(schedule, current.status, current.tried)
    if _answers[0] is current.schedule:  # answers it was made from kept (routes not answered at the next read)
        _answers = (schedule, _answers[1])


NOT_SENT = "\0not sent"  # reason of register / unregister: not sent (RaceControl limits, or asked to wait)
NO_ANSWER = "\0no answer"  # reason of register / unregister: sent, not answered (done or not: read again)


def _send(method: str, path: str, payload: dict) -> tuple[int, object]:
    from .process import raceos

    if not enabled():
        return raceos.NOT_SIGNED, None
    from .rank_info import online_client, ranks

    return online_client().send(method, path, payload, ranks.account)


def _refusal(status: int, answer: object) -> str:
    """Why a registration (or leave) was not done: RaceControl reason, NOT_SENT, NO_ANSWER, "" if not signed in"""
    from .process import raceos

    if status == raceos.NOT_SENT:
        return NOT_SENT
    if status == 0:
        return NO_ANSWER
    return rs.answer_message(answer) if status > 0 else ""


def read_overview(event_type: str, event_id: str) -> dict | None:
    """Event with its car list & registrations (memory only: names of other drivers), None if not read"""
    answer = _post(rs.OVERVIEW_ROUTE, {"game": "lmu", "eventType": event_type, "eventId": event_id})
    return answer if isinstance(answer, dict) else None


def game_cars() -> object:
    """Cars of the game (/rest/race/car answer: liveries, owned), None if not answered"""
    from .game_rest_cache import rest_cache

    return rest_cache.json("/rest/race/car", GAME_LISTS_AGE)


def register(event: dict, choice: rs.CarChoice) -> tuple[bool, str]:
    """Player registered to event (overview answer) with a livery: accepted & why when not (see _refusal)"""
    request = rs.register_request(event, choice)
    if request is None:
        return False, ""
    status, answer = _send("POST", rs.REGISTER_ROUTE, request)
    if not rs.answer_ok(status, answer):
        logger.info("RACE SCHEDULE: registration refused (status %s)", status)
        return False, _refusal(status, answer)
    _set_registered(request["eventId"], True)
    return True, ""


def unregister(event_type: str, event_id: str) -> tuple[bool, str]:
    """Player no longer registered to an event: done & why when not (see _refusal)"""
    status, answer = _send("DELETE", rs.UNREGISTER_ROUTE, {"eventType": event_type, "eventId": event_id})
    if not rs.answer_ok(status, answer):
        logger.info("RACE SCHEDULE: leaving the race refused (status %s)", status)
        return False, _refusal(status, answer)
    _set_registered(event_id, False)
    return True, ""


def read_split(entry_type: str, event_id: str) -> rs.SplitState | None:
    """Your split of a race (server ready to join or not, never its address), None if not read"""
    from urllib.parse import quote

    return rs.parse_split(_get(f"{rs.SPLIT_ROUTE}/{quote(entry_type, safe='')}/{quote(event_id, safe='')}"))


def blocked_minutes() -> int:
    """Minutes RaceControl still refuses this connection (403: nothing asked meanwhile), 0 if not"""
    from .rank_info import online_client

    blocked_for = getattr(online_client(), "blocked_for", None)  # client of tests without it: never blocked
    seconds = blocked_for() if blocked_for is not None else 0.0
    return -int(-seconds // 60) if seconds > 0 else 0
