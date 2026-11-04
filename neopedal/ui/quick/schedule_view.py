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
Rows of online races to come shown by the Upcoming Races page & the Home card (texts in app language)

Built from a race_schedule.Schedule (daily races of the public RaceControl site) & the time now: starts over are
left out. Your online races of Results & Replays (results files) are worded here too.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable

from ...formatter import class_style
from ...i18n import plural, tr
from ...process import race_schedule as rs
from .formatting import clock_minutes, day_month_minutes

LATER_STARTS = 8  # following starts listed under a race before "+n more"
SOON_SECONDS = 900.0  # start shown as soon (accent) this close
IMMINENT_SECONDS = 120.0  # start pulses this close
TIMELINE_HOURS = 6  # hours of the day timeline
TIER_LABELS = {"beginner": "Beginner", "intermediate": "Intermediate", "advanced": "Advanced"}
Logo = Callable[[str], str]  # track name -> logo url ("" if none)


def _filled(text: str, *values: str) -> str:
    """Translated text with %1, %2... replaced by values"""
    text = tr(text)
    for index, value in enumerate(values, 1):
        text = text.replace(f"%{index}", value)
    return text


def counted(count: int, one: str, many: str) -> str:
    """Count & translated noun: "3 drivers" """
    return f"{count} {plural(count, one, many)}"


def tier_text(tier: str) -> str:
    label = TIER_LABELS.get(tier)
    return tr(label, "tier") if label else tier.capitalize()


def day_offset(moment: float, now: float) -> int:
    """Calendar days from now to moment (local time): 0 today, 1 tomorrow"""
    first, second = time.localtime(now), time.localtime(moment)
    return round((time.mktime((*second[:3], 12, 0, 0, 0, 0, -1)) - time.mktime((*first[:3], 12, 0, 0, 0, 0, -1)))
                 / 86400)


def start_text(start: float, now: float) -> str:
    """Time of a start today (18:25), tomorrow ("Tomorrow 01:00"), else day & time (05/11 18:25)"""
    offset = day_offset(start, now)
    if offset == 0:
        return clock_minutes(start)
    if offset == 1:
        return f"{tr('Tomorrow')} {clock_minutes(start)}"
    return day_month_minutes(start)


def length_text(seconds: float) -> str:
    """Length of a race: "20 min", "1 h 30", "10 h", "" if unknown"""
    minutes = round(max(seconds, 0) / 60)
    if minutes <= 0:
        return ""
    hours, minutes = divmod(minutes, 60)
    if not hours:
        return f"{minutes} min"
    return f"{hours} h {minutes:02d}" if minutes else f"{hours} h"


def until_text(start: float, now: float, length: float = 0.0) -> str:
    """Time until a start: "Running", "in 12 min", "in 2 h 05", "in 3 days" """
    if start <= now:
        return tr("Running", "race") if now < start + max(length, 1.0) else ""
    seconds = start - now
    if seconds < 60:
        return tr("Starting soon")
    if seconds < 86400:
        return _filled("in %1", length_text(seconds))
    return _filled("in %1", counted(max(round(seconds / 86400), 1), "day", "days"))


def frequency_text(seconds: float) -> str:
    """Time between daily starts of a tier: "every 15 min", "" if unknown"""
    return _filled("every %1", length_text(seconds)) if seconds > 0 else ""


def owned_note(track: bool | None) -> str:
    """Track you do not own ("" if owned or unknown)"""
    return tr("Track not owned") if track is False else ""


def track_of(scene: str, fallback: str, schedule: rs.Schedule) -> tuple[str, bool | None]:
    """Layout name of a track scene as every page shows it (see process.track_names) & owned (None if unknown)"""
    from ...userfile.game_images import images

    name, owned = rs.track_of(scene, fallback, schedule.tracks)
    return images.track_name(name, fallback, scene=scene), owned


def race_key(event: rs.Event, events: Iterable[rs.Event]) -> str:
    """Key of a race (menu, details, timeline, reminders "<key>@<start>"): "<kind>/<tier>/<title>", "#<scene>" added
    only when another race of the tier has the same title (keys of the others kept: reminders set stay valid)"""
    key = f"{event.kind}/{event.tier}/{event.title}"
    twins = sum(1 for other in events if (other.kind, other.tier, other.title) == (event.kind, event.tier, event.title))
    return f"{key}#{event.scene}" if twins > 1 else key


def event_row(event: rs.Event, schedule: rs.Schedule, now: float, logo: Logo) -> dict | None:
    """Daily race, None once its starts are over"""
    length = event.length
    starts = rs.next_starts(event, now)
    if not starts:
        return None
    starts = [start for start in starts if start.time > now] or starts[:1]  # next to enter, else the running one
    first = starts[0]
    track, track_owned = track_of(event.scene, event.track, schedule)
    key = race_key(event, schedule.events)
    return {
        "key": key,
        "startKey": f"{key}@{int(first.time)}",
        "kind": event.kind,
        "tier": event.tier,
        "tierText": tier_text(event.tier),
        "title": event.title,
        "track": track,
        "scene": event.scene,
        "trackLogo": logo(track),
        "start": start_text(first.time, now),
        "until": until_text(first.time, now, length),
        "running": first.time <= now,
        "soon": 0 < first.time - now <= SOON_SECONDS,
        "imminent": 0 < first.time - now <= IMMINENT_SECONDS,
        "startTime": first.time,
        "endTime": first.time + length,
        "later": [start_text(start.time, now) for start in starts[1:]],
        "laterFirst": [start_text(start.time, now) for start in starts[1:1 + LATER_STARTS]],
        "length": length_text(length),
        "sessions": f"{tr('Race')} {length_text(length)}" if length > 0 else "",
        "owned": owned_note(track_owned),
        "trackOwned": track_owned is not False,
        "search": " ".join((event.title, track, event.track, tier_text(event.tier))).casefold(),
    }


def home_card(schedule: rs.Schedule, now: float, logo: Logo, count: int) -> list[dict]:
    """Next races, one row per race, soonest start first"""
    rows = [row for event in schedule.events if (row := event_row(event, schedule, now, logo)) is not None]
    rows.sort(key=lambda row: row["startTime"])
    return rows[:count]


def timeline(groups: Iterable[tuple[str, list[dict]]], schedule: rs.Schedule, now: float,
             hours: int = TIMELINE_HOURS) -> dict:
    """Day timeline: hours marks & one lane per race (tier told on the first lane of each tier) holding its starts
    in the next hours (start & width as fractions of the period: starts of a race never overlap)"""
    period = hours * 3600.0
    start_hour = time.mktime((*time.localtime(now)[:4], 0, 0, 0, 0, -1))  # whole hour of the local clock
    marks = [{"text": clock_minutes(start_hour + index * 3600), "at": (start_hour + index * 3600 - now) / period}
             for index in range(hours + 1) if start_hour + index * 3600 >= now - 1]
    events = {race_key(event, schedule.events): event for event in schedule.events}
    lanes = []
    for tier, rows in groups:
        for index, row in enumerate(sorted(rows, key=lambda row: row["title"].casefold())):
            event = events.get(row["key"])
            if event is None:
                continue
            length = event.length or 1800.0
            items = []
            for start in rs.next_starts(event, now):
                if start.time >= now + period:
                    break
                # Start & end, not places: the page places blocks from now (lanes kept while time goes by)
                items.append({
                    "key": row["key"], "start": start.time, "end": start.time + length, "title": row["title"],
                    "track": row["track"], "time": start_text(start.time, now), "running": start.time <= now,
                    "soon": 0 < start.time - now <= SOON_SECONDS,
                    "tip": " · ".join((start_text(start.time, now), row["title"], row["track"])),
                })
            lanes.append({"tier": tier, "tierText": tier_text(tier) if index == 0 else "", "title": row["title"],
                          "track": row["track"], "key": row["key"], "items": items})
    return {"marks": marks, "lanes": lanes, "hours": hours, "now": now, "period": period}


# Online results
def result_view(result: rs.OnlineResult, schedule: rs.Schedule, player: str, now: float, logo: Logo) -> dict:
    """Online race you drove: date, title, track, your place, whole classification (rows: position, class position,
    driver, car, number, class badge, best lap, laps, status)"""
    from ...calculation import sec2laptime_full
    from .formatting import date_text

    key = player.split("#", 1)[0].strip().casefold()
    rows, mine = [], None
    for row in result.rows:
        alias, color = class_style(row.vehicle_class) if row.vehicle_class else ("", "")
        me = bool(key) and any(name.split("#", 1)[0].strip().casefold() == key for name in (row.name, *row.drivers))
        shown = {
            "position": f"P{row.position}" if row.position else "",
            "classPosition": f"P{row.class_position}" if row.class_position else "",
            "grid": f"P{row.grid}" if row.grid else "", "name": row.name, "car": row.car, "number": row.number,
            "team": row.team, "classLabel": alias, "classColor": color,
            "best": sec2laptime_full(row.best_lap) if row.best_lap > 0 else "", "laps": str(row.laps or ""),
            "status": "" if row.status in ("Finished Normally", "") else row.status, "me": me,
            "drivers": ", ".join(row.drivers) if row.drivers and row.drivers != (row.name,) else "",
            "nameLine": f"#{row.number} {row.name}" if row.number else row.name,
            "lapsLine": " · ".join(part for part in (counted(row.laps, "lap", "laps") if row.laps else "",
                                                     "" if row.status in ("Finished Normally", "") else row.status)
                                   if part),
        }
        rows.append(shown)
        if me and mine is None:
            mine = shown
    track = track_of(result.track, result.track, schedule)[0]
    return {
        "key": f"result/{result.path}",
        "title": result.title, "date": date_text(result.time), "track": track, "trackLogo": logo(track),
        "drivers": counted(len(result.rows), "driver", "drivers"),
        "mine": mine or {}, "rows": rows,
    }


# Calendar export
def ics_event(uid: str, title: str, start: float, end: float, location: str, description: str) -> dict:
    return {"uid": uid, "title": title, "start": start, "end": max(end, start + 60), "location": location,
            "description": description}


def is_player(name: str, player: str) -> bool:
    """Name of a driver is the player's (tags "#1234" left out, case not minded)"""
    key = player.split("#", 1)[0].strip().casefold()
    return bool(key) and name.split("#", 1)[0].strip().casefold() == key


def csv_text(header: list[str], rows: list[list[str]]) -> str:
    """CSV of a table (comma separated, quoted when needed, header first)"""
    import csv
    import io

    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return out.getvalue()
