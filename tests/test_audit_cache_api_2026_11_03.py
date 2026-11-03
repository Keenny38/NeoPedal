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

"""Cache & API audit 2026-11-03: RaceControl down (5xx, no answer) is not asked route after route every 5 minutes"""

from __future__ import annotations

import time

from neopedal import race_schedule_info as info
from neopedal.process import race_schedule as rs
from tests.test_race_schedule import NOW, fresh_info  # noqa: F401


def test_outage_stops_the_read_after_a_few_routes_in_a_row(fresh_info, monkeypatch):  # noqa: F811
    fresh_info.data = {}  # signed in, nothing answered (RaceControl down)
    monkeypatch.setattr(info, "_game_running", lambda: True)
    state = info.read(live=True)
    assert state.status == info.FAILED
    assert len(fresh_info.paths) == info.FAIL_STREAK  # not the 10 routes of the page one after another
    assert set(state.schedule.missing) == set(rs.ROUTES)


def test_route_without_answer_alone_does_not_stop_the_read(fresh_info, monkeypatch):  # noqa: F811
    """Special events answer 500 when there is none: the routes after it are still asked"""
    monkeypatch.setattr(info, "_game_running", lambda: True)
    fresh_info.data = {key: [] for key in rs.ROUTES}
    fresh_info.data["special"] = None
    state = info.read(live=True, servers=True)
    assert state.status == info.READ and len(fresh_info.paths) == len(rs.ROUTES)


def test_failed_reads_wait_longer_each_time(fresh_info, monkeypatch):  # noqa: F811
    clock = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(time, "time", lambda: NOW + clock[0])
    monkeypatch.setattr(info, "_game_running", lambda: True)
    fresh_info.data = {}
    waits = []
    for _ in range(6):
        info.read()
        state = info.state()
        assert state.status == info.FAILED
        wait = 0.0
        while not info.due(clock[0] + wait):
            wait += 1.0
        waits.append(wait)
        clock[0] += wait
    assert waits[0] == info.RETRY_SECONDS
    assert waits[1] == 2 * info.RETRY_SECONDS and waits[2] == 4 * info.RETRY_SECONDS
    assert max(waits) == info.FAILED_MAX_SECONDS == waits[-1]
    # An answer ends the doubling: read again at the usual interval, failures forgotten
    fresh_info.data = {key: [] for key in rs.ROUTES}
    info.read(force=True)
    state = info.state()
    assert state.status == info.READ and state.failures == 0
    assert not info.due(clock[0] + info.READ_SECONDS - 1) and info.due(clock[0] + info.READ_SECONDS)


def test_game_closed_keeps_the_short_wait(fresh_info, monkeypatch):  # noqa: F811
    """No request is sent while the game is closed: the wait stays short so that the races load once it runs"""
    clock = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(info, "_game_running", lambda: False)
    fresh_info.data = {}
    for _ in range(4):
        info.read()
        assert info.state().status == info.NO_GAME and not info.due(clock[0] + info.RETRY_SECONDS - 1)
        assert info.due(clock[0] + info.RETRY_SECONDS)
        clock[0] += info.RETRY_SECONDS
