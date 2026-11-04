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

"""Hosted races & community events of the public RaceControl pages (no sign in), field pace of the Session overlay
(community level of the best laps of your class, from shared memory & the cached lap times sheet)"""

from __future__ import annotations

import calendar

from neopedal.process import public_schedule as ps
from neopedal.process import race_schedule as rs
from neopedal.widget._modern import session

NOW = float(calendar.timegm((2026, 11, 4, 14, 14, 0)))


def item(name: str, body: str) -> str:
    return (f'<dl class="d-flex"> <dt class="d-flex"> <i class="fa fa-x"></i> <span class="d-none ms-md-2"> {name} '
            f"</span> </dt> <dd class=\"m-0 text-md-end\"> {body} </dd> </dl>")


def card(title: str, href: str, items: str, extra: str = "") -> str:
    return (f'<div class="col"> <div class="community-event-card card event-card"> {extra} <div class="card-body"> '
            f'<h3 class="fs-xl mb-0"> <a class="text-rc-black" href="{href}">{title}</a> </h3> </div> '
            f'<div class="card-footer"> <div class="info-block"> {items} </div> </div> </div> </div>')


HOSTED = ("<html>" + card("SROL WEC 2026 - Round 8 - Monza", "/hosted_races/186713", item(
    "Registrations", '<div class="badge"> <span class="slots-entered">36</span> <span class="slots-capacity">38</span> '
    "</div>") + item("Date", '<time datetime="2026-11-04T19:00:00Z" title="x">Nov 04 at 7:00pm</time>')
    + item("Drivers", "Solo") + item("Track", "Monza (WEC)") + item("Classes", "Hypercar and LMGT3")
    + item("Sessions", "<span class='badge badge-secondary rounded-pill'>P 50m</span> "
           "<span class='badge badge-secondary rounded-pill'>R 1h30m</span>"))
    + card("Old race", "/hosted_races/1", item("Date", '<time datetime="2026-11-01T19:00:00Z">Nov 01</time>'))
    + card("Full race", "/hosted_races/2", item(
        "Registrations", '<span class="slots-entered">20</span> <span class="slots-capacity">20</span>')
        + item("Date", '<time datetime="2026-11-04T16:00:00Z">Nov 04</time>'))
    + "<footer></footer></html>")

LMU = '<span class="badge badge-platform me-1"> <i class="fa-solid fa-fw fa-gamepad me-1"></i> LMU </span>'
RF2 = '<span class="badge badge-platform me-1"> <i class="fa-solid fa-fw fa-gamepad me-1"></i> rF2 </span>'
ORGANIZER = '<div class="community"> <span class="logo"></span> <span class="fs-xs"><a href="x">Racing Stories</a></span> </div>'
EVENTS = ("<html>" + card("Apex Amigos", "/events/25331", item(
    "Start Date", '<time datetime="2026-10-05T18:15:00Z" data-format="%l:%M%P"> 6:15pm</time> on '
    '<span><time datetime="2026-10-05T18:15:00Z" data-format="%A">Monday</time></span>s')
    + item("Drivers", "Solo") + item("Rounds", "7 Rounds"), LMU + ORGANIZER)
    + card("Done series", "/events/1", item("Start Date", "Event Completed <i class='x'></i>"), LMU)
    + card("rF2 series", "/events/2", item("Start Date", '<time datetime="2026-11-05T18:00:00Z">x</time>'), RF2)
    + "<footer></footer></html>")


def test_hosted_races_to_come_soonest_first():
    found = ps.parse_public_events(HOSTED, "hosted", NOW)
    assert [event.title for event in found] == ["Full race", "SROL WEC 2026 - Round 8 - Monza"]  # over one left out
    race = found[1]
    assert race.start == calendar.timegm((2026, 11, 4, 19, 0, 0)) and not race.weekly
    assert (race.registered, race.capacity, race.track, race.classes, race.drivers) == (
        36, 38, "Monza (WEC)", "Hypercar and LMGT3", "Solo")
    assert race.sessions == ("P 50m", "R 1h30m") and race.url == "https://www.racecontrol.gg/hosted_races/186713"


def test_community_events_of_lmu_with_their_next_weekly_start():
    found = ps.parse_public_events(EVENTS, "community", NOW)
    assert [event.title for event in found] == ["Apex Amigos"]  # completed & other game left out
    series = found[0]
    assert series.weekly and series.organizer == "Racing Stories" and series.rounds == "7 Rounds"
    assert series.start == calendar.timegm((2026, 11, 9, 18, 15, 0))  # next Monday 18:15 UTC


def test_public_read_keeps_a_list_not_read(monkeypatch):
    from tests.test_local_alternatives_2026_11_04 import PAGE

    pages = {"": PAGE, ps.HOSTED_PATH: HOSTED}

    def fetch(timeout=ps.TIMEOUT, path=""):
        if path not in pages:
            raise OSError("offline")
        return pages[path]

    monkeypatch.setattr(ps, "fetch", fetch)
    found = ps.read(NOW)
    assert found is not None and len(found.hosted) == 2 and found.community == () and found.missing == ("community",)
    pages[ps.EVENTS_PATH] = EVENTS
    assert ps.read(NOW).missing == ()


def test_public_row_texts():
    from neopedal.ui.quick.schedule_backend import public_row

    race = ps.parse_public_events(HOSTED, "hosted", NOW)[1]
    row = public_row(race, NOW)
    assert row["places"] == "36/38" and not row["full"] and row["sessions"] == "P 50m  ·  R 1h30m"
    assert "monza" in row["search"] and row["url"].startswith(ps.SITE)
    full = public_row(ps.parse_public_events(HOSTED, "hosted", NOW)[0], NOW)
    assert full["full"] is True
    weekly = public_row(ps.parse_public_events(EVENTS, "community", NOW)[0], NOW)
    assert weekly["when"].endswith("every week") and weekly["details"] == "Solo  ·  7 Rounds"


class Reference:
    def level(self, laptime):
        return 0 if laptime < 100 else 2 if laptime < 102 else 4


class Table:
    def __init__(self):
        self.asked = []

    def find(self, track, vehicle_key, vehicle_class=""):
        self.asked.append((track, vehicle_class))
        return Reference() if track == "Monza" and vehicle_class == "LMGT3" else None


def test_field_pace_median_level_of_your_class():
    cars = [("LMGT3", 99.0), ("LMGT3", 101.0), ("LMGT3", 101.5), ("LMGT3", 103.0), ("Hypercar", 90.0),
            ("LMGT3", 0.0), ("LMGT3", 1e9)]
    assert session.field_level(Table(), "Monza", "LMGT3", cars) == 2  # middle of 0, 2, 2, 4
    assert session.field_level(Table(), "Spa", "LMGT3", cars) == -1  # no sheet line
    assert session.field_level(Table(), "Monza", "LMGT3", [("LMGT3", 0.0)]) == -1  # no best lap yet
    assert session.field_level(Table(), "", "LMGT3", cars) == -1


def test_field_pace_worked_out_every_few_seconds(monkeypatch):
    clock = [0.0]
    pace = session.FieldPace(clock=lambda: clock[0])
    table = Table()
    monkeypatch.setattr(pace, "table", lambda: table)
    levels = iter((2, 4))
    monkeypatch.setattr(session, "field_level", lambda *args: next(levels))
    from types import SimpleNamespace

    read = SimpleNamespace(session=SimpleNamespace(track_name=lambda: "Monza"),
                           vehicle=SimpleNamespace(class_name=lambda index=None: "LMGT3"))
    monkeypatch.setattr(session, "api", SimpleNamespace(read=read))
    assert pace.level() == 2
    clock[0] += session.PACE_SECONDS - 1
    assert pace.level() == 2  # kept
    clock[0] += 1
    assert pace.level() == 4


def test_schedule_lists_default_empty():
    assert rs.EMPTY.hosted == () and rs.EMPTY.community == ()
