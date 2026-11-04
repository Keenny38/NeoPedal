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
Daily races of Le Mans Ultimate from the public home page of RaceControl (www.racecontrol.gg), without signing in

Used when the online option (enable_online_driver_ranks: sign in with the game ticket) is off: no Steam ticket, no
account, nothing about the player is sent; one GET of a public page, as a web browser does. The page lists the next
daily races of each tier (title, tier, duration, track, start times in UTC: "4 Nov at 2:45pm", seen 2026-11-04);
no registrations, cars, sessions or fields (those need the sign in). The page is HTML made for people: when it
changes, nothing is found and the page says so (no wrong race shown).
"""

from __future__ import annotations

import calendar
import html
import itertools
import logging
import re
import time
import urllib.error
import urllib.request
from collections.abc import Iterable

from . import race_schedule as rs

logger = logging.getLogger(__name__)

PUBLIC_URL = "https://www.racecontrol.gg/"
MAX_PAGE = 2 * 1024 * 1024
TIMEOUT = 10.0
TIERS = ("beginner", "intermediate", "advanced")
_MONTHS = {name: number for number, name in enumerate(calendar.month_abbr) if name}
_section = re.compile(r"Upcoming Daily Races</h2>(.*?)(?=<h2[ >])", re.S)
_card = re.compile(r'class="scheduled-race-card(.*?)(?=class="scheduled-race-card|\Z)', re.S)
_tier = re.compile(r'tier-badge">\s*(?:<i[^>]*></i>)?\s*([A-Za-z]+)\s*<')
_title = re.compile(r"<h4[^>]*>([^<]+)</h4>")
_rows = re.compile(r"</i>\s*([A-Za-z ]+?)\s*</span>\s*<hr[^>]*>\s*<span[^>]*>\s*([^<]+?)\s*</span>", re.S)
_start = re.compile(r">\s*(\d{1,2}) ([A-Z][a-z]{2}) at (\d{1,2}):(\d{2})\s*([ap]m)\s*<")
_minutes = re.compile(r"(\d+)\s*min")
_hours = re.compile(r"(\d+)\s*h(?:ours?)?\s*(\d+)?")


def start_time(day: int, month: str, hour: int, minute: int, meridiem: str, now: float) -> float:
    """Seconds since epoch of "4 Nov at 2:45pm" (UTC), year of now (next year when that date is over 6 months ago)"""
    hour = hour % 12 + (12 if meridiem == "pm" else 0)
    year = time.gmtime(now).tm_year
    stamp = calendar.timegm((year, _MONTHS[month], day, hour, minute, 0))
    if stamp < now - 183 * 86400:  # "2 Jan" read on 31 December: next year
        stamp = calendar.timegm((year + 1, _MONTHS[month], day, hour, minute, 0))
    return float(stamp)


def duration_seconds(text: str) -> float:
    """Seconds of "30 minutes", "1 h 13", "2 hours", "45" (minutes), 0 if unreadable"""
    text = text.strip().casefold()
    hours = _hours.search(text)
    if hours:
        return float(int(hours.group(1)) * 3600 + int(hours.group(2) or 0) * 60)
    minutes = _minutes.search(text) or re.fullmatch(r"(\d+)", text)
    return float(int(minutes.group(1)) * 60) if minutes else 0.0


def lmu_section(page: str) -> str:
    """Daily races block of Le Mans Ultimate (the page also lists rFactor 2 races), "" if not found"""
    for match in _section.finditer(page):
        if "lmu_logo" in match.group(1)[:1500]:
            return match.group(1)
    return ""


def parse_daily(page: str, now: float) -> tuple[rs.Event, ...]:
    """Daily races of Le Mans Ultimate of the public home page, starts soonest first, empty if none found"""
    events = []
    for match in _card.finditer(lmu_section(page)):
        card = match.group(1)
        tier = _tier.search(card)
        title = _title.search(card)
        if tier is None or title is None or tier.group(1).lower() not in TIERS:
            continue
        rows = {name.strip().lower(): html.unescape(value) for name, value in _rows.findall(card)}
        starts = sorted({start_time(int(day), month, int(hour), int(minute), meridiem, now)
                         for day, month, hour, minute, meridiem in _start.findall(card) if month in _MONTHS})
        if not starts:
            continue
        race = duration_seconds(rows.get("duration", ""))
        events.append(rs.Event(
            kind="daily", tier=tier.group(1).lower(), title=html.unescape(title.group(1)).strip(),
            track=rows.get("track", "").strip(), scene="", starts=tuple(rs.Start(start) for start in starts),
            total=race, sessions=(rs.Session("Race", race),) if race else (), cars=(),
            requirement=rs.Requirement("", 0), tier_label=tier.group(1).lower()))
    order = {tier: index for index, tier in enumerate(TIERS)}
    return tuple(sorted(events, key=lambda event: (order[event.tier], event.starts[0].time)))


def frequency(events: tuple[rs.Event, ...]) -> dict[str, float]:
    """Seconds between two starts of a tier (its races start one after another), as the daily schedule tells"""
    found: dict[str, float] = {}
    for tier in TIERS:
        starts = sorted({start.time for event in events if event.tier == tier for start in event.starts})
        gaps = [later - earlier for earlier, later in itertools.pairwise(starts) if later > earlier]
        if gaps:
            found[tier] = min(gaps)
    return found


def scene_of(track: str, scenes: Iterable[str]) -> str:
    """Track scene of the game (catalog of the game, lower case) of a track named by the public page: "Fuji Wec 2023"
    -> "fujiwec", "Le Mans" -> "lemanswec" (shortest scene starting with the name, year left out), "" if none"""
    key = re.sub(r"\d{4}$", "", re.sub(r"[^a-z0-9]", "", track.casefold()))
    if not key:
        return ""
    found = sorted((scene for scene in scenes if re.sub(r"[^a-z0-9]", "", scene).startswith(key)),
                   key=lambda scene: (len(scene), scene))
    return found[0] if found else ""


def with_game_lists(schedule: rs.Schedule, cars: dict[str, rs.CarInfo],
                    tracks: dict[str, rs.TrackInfo]) -> rs.Schedule:
    """Schedule with the scene of each race found in the track catalog of the game (names, logos, your laps on it)"""
    events = tuple(event._replace(scene=scene_of(event.track, tracks)) for event in schedule.events)
    return schedule._replace(events=events, cars=cars, tracks=tracks)


def fetch(timeout: float = TIMEOUT) -> str:
    """Public home page of RaceControl (raise OSError if not read)"""
    from .. import request_log, version
    from ..const_app import APP_NAME

    request = urllib.request.Request(PUBLIC_URL, headers={"User-Agent": f"{APP_NAME}/{version.__version__}",
                                                          "Accept": "text/html"})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(MAX_PAGE + 1)
            status = response.status
    except urllib.error.HTTPError as error:
        request_log.record(request_log.PUBLIC_SITE, "GET /", error.code, (time.monotonic() - started) * 1000)
        raise
    except OSError:
        request_log.record(request_log.PUBLIC_SITE, "GET /", 0, (time.monotonic() - started) * 1000)
        raise
    request_log.record(request_log.PUBLIC_SITE, "GET /", status, (time.monotonic() - started) * 1000)
    if len(data) > MAX_PAGE:
        raise OSError("public page too large")
    return data.decode("utf-8", "replace")


def read(now: float | None = None) -> rs.Schedule | None:
    """Daily races of the public page as a schedule (other tabs empty), None if not read or nothing found"""
    now = time.time() if now is None else now
    try:
        events = parse_daily(fetch(), now)
    except (OSError, ValueError) as error:
        logger.info("PUBLIC SCHEDULE: not read: %s", error)
        return None
    if not events:
        logger.warning("PUBLIC SCHEDULE: no daily race found on the public page (page changed?)")
        return None
    missing = tuple(key for key in rs.ROUTES if not key.startswith("daily"))
    return rs.EMPTY._replace(read_time=now, events=events, missing=missing, frequency=frequency(events))
