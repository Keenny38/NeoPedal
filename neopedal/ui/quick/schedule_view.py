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
from ...i18n import percent_sign, plural, tr
from ...process import race_schedule as rs
from .formatting import (
    clock_minutes,
    day_month_minutes,
    number_text,
    temperature_text,
    temperature_value,
)

LATER_STARTS = 8  # following starts listed under a race before "+n more"
SOON_SECONDS = 900.0  # start shown as soon (accent) this close
IMMINENT_SECONDS = 120.0  # start pulses this close
FORECAST_NODES = 4  # race weather nodes worded at most
TIMELINE_HOURS = 6  # hours of the day timeline
TIER_LABELS = {"beginner": "Beginner", "intermediate": "Intermediate", "advanced": "Advanced",
               "weekly": "Weekly", "special": "Special Event"}
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


def requirement_text(requirement: rs.Requirement) -> str:
    """Safety Rank needed ("SR Silver 2"), "" if none"""
    if not requirement.rank:
        return ""
    return f"SR {requirement.rank} {requirement.tier}" if requirement.tier else f"SR {requirement.rank}"


def open_state(requirement: rs.Requirement, safety: tuple[str, int]) -> int:
    """1 player may enter, 0 rank too low, -1 rank unknown"""
    state = rs.can_enter(requirement, *safety)
    return -1 if state is None else int(state)


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


def sessions_text(sessions: Iterable[rs.Session]) -> str:
    """Sessions & lengths: "Practice 3 min · Qualifying 10 min · Race 20 min" """
    return " · ".join(" ".join(part for part in (tr(session.kind), length_text(session.seconds)) if part)
                      for session in sessions)


def weather_text(temperature: float | None, rain: int | None) -> str:
    """Weather of a node: "25 °C · Dry", "16 °C · Rain 100 %", "" if unknown"""
    parts = []
    if temperature is not None:
        parts.append(temperature_text(temperature))
    if rain is not None:
        parts.append(tr("Dry", "weather") if rain <= 0 else f"{tr('Rain', 'weather')} {rain}{percent_sign()}")
    return " · ".join(parts)


def forecast_text(forecast: Iterable[rs.Weather]) -> str:
    """Race weather from start to end: temperature at start & end, rain changes only: "22 → 19 °C · Dry",
    "16 °C · Rain 100 % → Rain 80 % → Dry" """
    nodes = list(forecast)
    temperatures = [node.temperature for node in nodes if node.temperature is not None]
    rains: list[str] = []
    for node in nodes:
        if node.rain is not None:
            text = weather_text(None, node.rain)
            if not rains or rains[-1] != text:
                rains.append(text)
    if len(rains) > FORECAST_NODES:
        rains = rains[:FORECAST_NODES - 1] + rains[-1:]
    parts = []
    if temperatures:
        first, last = temperature_text(temperatures[0]), temperature_text(temperatures[-1])
        parts.append(first if first == last else f"{number_text(temperature_value(temperatures[0]), 0)} → {last}")
    if rains:
        parts.append(" → ".join(rains))
    return " · ".join(parts)


def track_time_text(sessions: Iterable[rs.Session]) -> str:
    """Time on track at race start: "Track time 19:20", "" if unknown"""
    race = next((session for session in sessions if session.kind == "Race" and session.time_of_day), None)
    return _filled("Track time %1", race.time_of_day) if race is not None else ""


def class_rows(classes: Iterable[str]) -> list[dict]:
    """Class badges: alias, full name, color (vehicle class editor)"""
    rows = []
    for name in classes:
        alias, color = class_style(name)
        rows.append({"label": alias, "full": name, "color": color})
    return rows


def owned_note(cars: bool | None, track: bool | None) -> str:
    """What the player does not own ("" if all owned or unknown)"""
    if cars is False and track is False:
        return tr("Car & track not owned")
    if cars is False:
        return tr("No car owned")
    if track is False:
        return tr("Track not owned")
    return ""


def registration_text(start: rs.Start, now: float) -> str:
    """Registration state of a start: "Registered", "Registration opens 02:15", "Registration open", ""."""
    if start.registered:
        return tr("Registered")
    if start.opens > now:
        return _filled("Registration opens %1", start_text(start.opens, now))
    if 0 < start.opens <= now < start.time:
        return tr("Registration open")
    return ""


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


def event_row(event: rs.Event, schedule: rs.Schedule, safety: tuple[str, int], now: float, logo: Logo) -> dict | None:
    """Daily, weekly or special race, None once its starts are over"""
    length = event.total or event.race_seconds
    starts = rs.next_starts(event, now)
    if not starts:
        return None
    starts = [start for start in starts if start.time > now] or starts[:1]  # next to enter, else the running one
    first = starts[0]
    track, track_owned = track_of(event.scene, event.track, schedule)
    cars_owned = rs.owned_state(event.cars, schedule.cars)
    classes = rs.classes_of(event.cars, schedule.cars)
    settings = []
    if event.fixed_setup is not None:
        settings.append(tr("Fixed setup") if event.fixed_setup else tr("Open setup"))
    if event.tyre_warmers:
        settings.append(tr("Tyre warmers"))
    if event.team:
        settings.append(tr("Team race"))
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
        "length": length_text(event.race_seconds),
        "total": length_text(event.total),
        "sessions": sessions_text(event.sessions),
        "trackTime": track_time_text(event.sessions),
        "weather": forecast_text(event.forecast),
        "wet": any((node.rain or 0) > 0 for node in event.forecast),
        "settings": " · ".join(settings),
        "registered": (counted(first.registrations, "driver registered", "drivers registered")
                       if first.registrations > 0 else ""),
        "registration": registration_text(first, now),
        # open as for every race until its start: not told on cards (registered, opening time told)
        "registrationOpen": not first.registered and 0 < first.opens <= now < first.time,
        "registeredMe": first.registered,
        "maxPlayers": event.max_players,
        "requirement": requirement_text(event.requirement),
        "open": open_state(event.requirement, safety),
        "owned": owned_note(cars_owned, track_owned),
        "carsOwned": cars_owned is not False and track_owned is not False,
        "classes": class_rows(classes),
        "classNames": list(classes),
        "eventId": first.event_id,
        "entryType": event.entry_type,
        "search": " ".join((event.title, track, event.track, tier_text(event.tier), *classes)).casefold(),
    }


def upcoming_races(schedule: rs.Schedule, safety: tuple[str, int], now: float, logo: Logo,
                   open_only: bool = False) -> list[dict]:
    """Daily, weekly & special races, soonest start first"""
    rows = [row for event in schedule.events
            if (row := event_row(event, schedule, safety, now, logo)) is not None
            and not (open_only and row["open"] == 0)]
    rows.sort(key=lambda row: row["startTime"])
    return rows


def home_card(schedule: rs.Schedule, safety: tuple[str, int], now: float, logo: Logo, count: int) -> list[dict]:
    """Next races the player may enter (or rank unknown), one row per race, soonest first"""
    return upcoming_races(schedule, safety, now, logo, open_only=True)[:count]


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
            length = event.total or event.race_seconds or 1800.0
            items = []
            for start in rs.next_starts(event, now):
                if start.time >= now + period:
                    break
                # Start & end, not places: the page places blocks from now (lanes kept while time goes by)
                items.append({
                    "key": row["key"], "start": start.time, "end": start.time + length, "title": row["title"],
                    "track": row["track"], "time": start_text(start.time, now), "running": start.time <= now,
                    "open": row["open"], "soon": 0 < start.time - now <= SOON_SECONDS,
                    "tip": " · ".join((start_text(start.time, now), row["title"], row["track"])),
                })
            lanes.append({"tier": tier, "tierText": tier_text(tier) if index == 0 else "", "title": row["title"],
                          "track": row["track"], "open": row["open"], "key": row["key"], "items": items})
    return {"marks": marks, "lanes": lanes, "hours": hours, "now": now, "period": period}


# Details read on demand
# Weekly leaderboards & online results
def rank_text(rank: tuple[str, int]) -> str:
    return f"{rank[0]} {rank[1]}" if rank[0] and rank[1] else rank[0]


def change_text(value: float | None) -> str:
    """Rank change of a race: "+1", "-2", "0", "" if unknown"""
    if value is None:
        return ""
    return f"{value:+g}" if value else "0"


def result_view(result: rs.OnlineResult, schedule: rs.Schedule, player: str, now: float, logo: Logo) -> dict:
    """Online race you drove: date, title, track, tier, split, your place & rank changes (and why), whole
    classification (rows: position, class position, driver, car, number, class badge, best lap, laps, status, Driver
    & Safety Rank changes, why)"""
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
            "status": "" if row.status in ("Finished Normally", "") else row.status,
            "dr": change_text(row.dr_change), "sr": change_text(row.sr_change),
            "drTone": 0 if not row.dr_change else (1 if row.dr_change > 0 else -1),
            "srTone": 0 if not row.sr_change else (1 if row.sr_change > 0 else -1),
            "reasons": reasons_text(row.reasons), "me": me,
            "drivers": ", ".join(row.drivers) if row.drivers and row.drivers != (row.name,) else "",
            "nameLine": f"#{row.number} {row.name}" if row.number else row.name,
            "lapsLine": " · ".join(part for part in (counted(row.laps, "lap", "laps") if row.laps else "",
                                                     "" if row.status in ("Finished Normally", "") else row.status)
                                   if part),
            "ranksLine": " · ".join(f"{label} {text}" for label, text in (("DR", change_text(row.dr_change)),
                                                                          ("SR", change_text(row.sr_change))) if text),
        }
        rows.append(shown)
        if me and mine is None:
            mine = shown
    track = track_of(result.track, result.track, schedule)[0]
    return {
        "key": f"result/{result.event_id}/{result.split}",
        "title": result.title, "date": date_text(result.time), "track": track, "trackLogo": logo(track),
        "tierText": tier_text(result.tier) if result.tier else "",
        "split": _filled("Split %1", str(result.split)) if result.split else "",
        "drivers": counted(len(result.rows), "driver", "drivers"),
        "mine": mine or {}, "rows": rows,
    }


# Calendar export
def ics_event(uid: str, title: str, start: float, end: float, location: str, description: str) -> dict:
    return {"uid": uid, "title": title, "start": start, "end": max(end, start + 60), "location": location,
            "description": description}


# Why your ranks changed: RaceControl texts in app language (names & numbers kept)
REASONS = (
    (r"^(Quali|Race) (\d+) clean laps$", ("Qualifying: %2 clean laps", "Race: %2 clean laps")),
    (r"^(Quali|Race) (\d+) invalid laps$", ("Qualifying: %2 invalid laps", "Race: %2 invalid laps")),
    (r"^(Quali|Race) contact with Barrier \(x(\d+)\)$", ("Qualifying: barrier contact (x%2)", "Race: barrier contact (x%2)")),
    (r"^(Quali|Race) contact with Barrier$", ("Qualifying: barrier contact", "Race: barrier contact")),
    (r"^(Quali|Race) contact with Immovable$", ("Qualifying: contact with an object", "Race: contact with an object")),
    (r"^(Quali|Race) contact with another vehicle (.+?) \(x(\d+)\)$",
     ("Qualifying: contact with %2 (x%3)", "Race: contact with %2 (x%3)")),
    (r"^(Quali|Race) contact with another vehicle (.+)$", ("Qualifying: contact with %2", "Race: contact with %2")),
    (r"^(Qualifying|Race) you finished (\d+)\w* of (\d+)$", ("Qualifying: finished %2 of %3", "Race: finished %2 of %3")),
    (r"^(Qualifying|Race) you beat (\d+) drivers with a higher Driver Rank$",
     ("Qualifying: beat %2 drivers of higher Driver Rank", "Race: beat %2 drivers of higher Driver Rank")),
    (r"^(Qualifying|Race) you lost to (\d+) drivers with a lower Driver Rank$",
     ("Qualifying: beaten by %2 drivers of lower Driver Rank", "Race: beaten by %2 drivers of lower Driver Rank")),
    (r"^(Race) DNF$", ("", "Race: did not finish")),
    (r"^(Split) Strength of Field (\w+)$", ("Strength of field of the split: %2", "Strength of field of the split: %2")),
    (r"^(Team) Participation Ratio (\d+)% for (\d+) laps$",
     ("Part in the team race: %2% of %3 laps", "Part in the team race: %2% of %3 laps")),
    (r"^(You) gained Driver Rank$", ("Driver Rank gained", "Driver Rank gained")),
    (r"^(You) lost Driver Rank$", ("Driver Rank lost", "Driver Rank lost")),
    (r"^(You) were expected to finish (\d+)\w*$", ("Expected place: %2", "Expected place: %2")),
)


def reason_text(text: str) -> str:
    """A reason of a rank change in app language ("Race 5 clean laps" -> "Race: 5 clean laps"), as given if
    unknown; its change ("(+2)") kept"""
    import re

    change = ""
    found = re.match(r"^(.*?)( \([+-][\d.]+\))?$", text)
    if found:
        text, change = found.group(1), found.group(2) or ""
    for pattern, (qualifying, race) in REASONS:
        match = re.match(pattern, text)
        if match:
            template = qualifying if match.group(1) in ("Quali", "Qualifying") else race
            if not template:
                break
            return _filled(template, *match.groups()) + change
    return text + change


def reasons_text(reasons) -> str:
    """Reasons of rank changes, one a line, "" if RaceControl gave none"""
    return "\n".join(reason_text(reason) for reason in reasons)


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
