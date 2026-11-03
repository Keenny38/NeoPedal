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

import itertools
import time

from neopedal import race_schedule_info as info
from neopedal.process import race_schedule as rs
from tests.test_race_schedule import NOW, fresh_info, page  # noqa: F401


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


class StatusClient:
    """FakeClient with the statuses of the real one: special events answer 500 when there are none"""

    def __init__(self, inner):
        self.inner = inner
        self.paths = inner.paths

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def get_status(self, path, account=""):
        answer = self.inner.get(path, account)
        return (200, answer) if answer is not None else (500, None)


def use_clock(monkeypatch, start: float):
    clock = [start]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    monkeypatch.setattr(time, "monotonic", lambda: clock[0] - NOW)
    return clock


def test_no_special_event_is_remembered_like_any_answer(fresh_info, monkeypatch):  # noqa: F811
    from neopedal import rank_info

    client = StatusClient(fresh_info)
    monkeypatch.setattr(rank_info, "online_client", lambda: client)
    clock = use_clock(monkeypatch, NOW)
    monkeypatch.setattr(info, "_game_running", lambda: True)
    state = info.read(live=True)  # special: 500, none to come
    assert state.status == info.READ and rs.ROUTES["special"] in fresh_info.paths
    assert "special" not in state.schedule.missing
    asked = fresh_info.paths.count(rs.ROUTES["special"])
    for _ in range(5):  # page shown for 50 minutes: never asked again
        clock[0] += info.LIVE_READ_SECONDS
        info.read(live=True)
    assert fresh_info.paths.count(rs.ROUTES["special"]) == asked
    clock[0] += info.SLOW_ROUTE_SECONDS  # an hour after the read: asked once more
    info.read(live=True)
    assert fresh_info.paths.count(rs.ROUTES["special"]) == asked + 1


def test_routes_asked_again_only_when_they_can_have_changed(fresh_info, monkeypatch):  # noqa: F811
    """Three days of simulated time, page shown all along: the daily schedule is read at midnight UTC or every 6 hours, the active
    championships once their current round ended (and not before), 0 requests in between for them"""
    from neopedal import rank_info

    client = StatusClient(fresh_info)
    monkeypatch.setattr(rank_info, "online_client", lambda: client)
    monkeypatch.setattr(info, "_game_running", lambda: True)
    end = fresh_info.data["championships"][0]["rounds"][0]["endsAt"]  # NOW + 1 day: round ends
    round_end = rs.parse_time(end)
    clock = use_clock(monkeypatch, NOW)
    stop = NOW + 3 * 86400
    seen = {"schedule": [], "championships": []}
    while clock[0] < stop:
        before = len(fresh_info.paths)
        info.read(live=True)
        for key in seen:
            if rs.ROUTES[key] in fresh_info.paths[before:]:
                seen[key].append(clock[0])
        clock[0] += info.LIVE_READ_SECONDS
    reads = seen["schedule"]  # 35 reads in 3 days before: every hour
    assert len(reads) <= 13
    assert all(later - earlier >= info.SCHEDULE_MAX_SECONDS or later // 86400 != earlier // 86400
               for earlier, later in itertools.pairwise(reads))  # again at midnight UTC or 6 h at most
    assert any(reads[0] // 86400 < moment // 86400 for moment in reads)
    rounds = seen["championships"]
    assert rounds[0] == NOW and len(rounds) <= 13  # 35 reads in 3 days before: every hour
    assert any(round_end <= moment < round_end + info.ROUND_MARGIN + info.LIVE_READ_SECONDS for moment in rounds)
    assert all(later - earlier >= info.ROUND_MAX_SECONDS or earlier < round_end <= later
               for earlier, later in itertools.pairwise(rounds))  # 6 h at most, or the moment the round ended


def test_disk_copy_keeps_the_read_time_of_each_route(fresh_info, monkeypatch):  # noqa: F811
    """A route not asked again keeps its own time in the copy on disk: an app restart does not make it look new"""
    from neopedal import rank_info

    client = StatusClient(fresh_info)
    monkeypatch.setattr(rank_info, "online_client", lambda: client)
    monkeypatch.setattr(info, "_game_running", lambda: True)
    clock = use_clock(monkeypatch, NOW)
    info.read()
    clock[0] += info.READ_SECONDS  # dailies read again, weekly (slow) kept
    info.read()
    saved = info._answers[1]
    assert saved["weekly"][0] == NOW and saved["daily_beginner"][0] == NOW + info.READ_SECONDS
    monkeypatch.setattr(info, "_state", info.State(rs.EMPTY, "", -1.0, 0))
    monkeypatch.setattr(info, "_disk_read", False)
    monkeypatch.setattr(info, "_answers", (None, {}))
    clock[0] += 600.0  # app started again
    info.load_disk()
    loaded = info._known()
    assert loaded["weekly"][0] == NOW and loaded["daily_beginner"][0] == NOW + info.READ_SECONDS
    assert info.state().schedule.read_time == NOW + info.READ_SECONDS


def test_daily_lists_follow_the_race_slot_while_the_page_shows(fresh_info, monkeypatch):  # noqa: F811
    """Beginner races start every 15 minutes (schedule frequency): its list is read once a slot, not every 10 min"""
    from neopedal import rank_info

    client = StatusClient(fresh_info)
    monkeypatch.setattr(rank_info, "online_client", lambda: client)
    monkeypatch.setattr(info, "_game_running", lambda: True)
    clock = use_clock(monkeypatch, NOW)
    info.read(live=True)
    assert info.state().schedule.frequency["beginner"] == 900
    beginner = rs.ROUTES["daily_beginner"]
    asked = fresh_info.paths.count(beginner)
    clock[0] += info.LIVE_READ_SECONDS
    info.read(live=True)
    assert fresh_info.paths.count(beginner) == asked  # 10 minutes: same slot
    clock[0] += info.LIVE_READ_SECONDS
    info.read(live=True)
    assert fresh_info.paths.count(beginner) == asked + 1  # 20 minutes: next slot


def test_places_asked_only_for_tracks_driven_this_week(page, monkeypatch):  # noqa: F811
    from neopedal.ui.quick.schedule_personal import PersonalData
    from neopedal.userfile.lap_reference import LapReferenceTable
    from tests.test_race_schedule import pump

    backend = page.backend
    asked = []
    monkeypatch.setattr(info, "read_places", lambda boards, _asked=None: asked.append(sorted(boards)) or {
        key: (3, 40) for key in boards})
    events = [event for event in info.state().schedule.events if event.board is not None]
    track = events[0].track
    wanted = sorted(event.board.key for event in events if event.track == track)

    def read_with(last_driven: float):
        backend._personal = PersonalData({track: {}}, {}, {track: last_driven}, LapReferenceTable(), {}, frozenset())
        backend._places_time = -1e9
        count = len(asked)
        backend.read_places_due()
        for _ in range(50):
            pump(0.02)
            if len(asked) > count and not backend.jobs.is_busy("places"):
                break
        return asked[count:]

    assert read_with(NOW - 3 * 86400) == [wanted]  # driven this week: only the leaderboards of that track
    assert read_with(NOW - 9 * 86400) == []  # a week ago and more: nothing asked, no ranking possible


def test_offline_session_end_asks_no_sign_in(tmp_path):
    """Results files are written for every session: ranks only move after an online one"""
    import os

    from tests.test_online_ranks import PLAYER, FakeOnline, make_watcher
    from tests.test_online_ranks import raceos as ranks_raceos

    online = FakeOnline(ranks_raceos.player_ranks(PLAYER))
    clock = [0.0]
    watcher, _path, results, _history = make_watcher(tmp_path, online, clock)
    watcher.check()
    assert len(online.fetched) == 1
    ended = []
    watcher._session_ended = lambda: ended.append(1)

    def end_session(setting: str, stamp: int):
        (results / f"2026-11-03-{stamp}R1.xml").write_text(
            f"<rFactorXML><RaceResults><Setting>{setting}</Setting><TrackVenue>Spa</TrackVenue></RaceResults>"
            "</rFactorXML>", encoding="utf-8")
        os.utime(results, (stamp, stamp))
        watcher.check()

    clock[0] = 100.0
    end_session("Race Weekend", 1_950_000_000)  # solo: no sign in 3 & 15 minutes later
    clock[0] = 100.0 + dr_delays()[1]
    watcher.check()
    assert len(online.fetched) == 1 and not ended
    clock[0] = 1000.0
    end_session("Multiplayer", 1_960_000_000)  # online: read after it
    clock[0] = 1000.0 + dr_delays()[0]
    watcher.check()
    assert len(online.fetched) == 2 and ended == [1]
    # A results file nobody can read keeps the old behaviour (sign in)
    clock[0] = 1500.0
    (results / "2026-11-03-bad.xml").write_bytes(b"\x00\x01")
    os.utime(results / "2026-11-03-bad.xml", (1_970_000_000, 1_970_000_000))
    os.utime(results, (1_970_000_000, 1_970_000_000))
    watcher.check()
    assert ended == [1, 1]


def dr_delays():
    from neopedal.process import driver_ranks

    return driver_ranks.ONLINE_RESULTS_DELAYS


def test_read_again_asks_the_shown_tab_only_and_not_twice_in_five_minutes(page, monkeypatch):  # noqa: F811
    from tests.test_race_schedule import pump

    backend = page.backend
    reads = []
    monkeypatch.setattr(info, "read", lambda force=False, live=False, servers=False, tab="": reads.append(
        (force, tab)) or info.state())
    backend.setTab(2)
    backend.readAgain()
    pump(0.3)
    backend.readAgain()  # a minute later: only what is due
    pump(0.3)
    assert reads[0] == (True, "championships") and reads[1] == (False, "")


def test_forced_read_asks_the_routes_of_the_tab_only(fresh_info, monkeypatch):  # noqa: F811
    from neopedal import rank_info

    client = StatusClient(fresh_info)
    monkeypatch.setattr(rank_info, "online_client", lambda: client)
    monkeypatch.setattr(info, "_game_running", lambda: True)
    use_clock(monkeypatch, NOW)
    info.read(force=True, tab="events")
    assert fresh_info.paths == [rs.ROUTES["weekly"], rs.ROUTES["special"]]
    fresh_info.paths.clear()
    monkeypatch.setattr(info, "_state", info.state()._replace(tried=-1000.0))
    info.read(force=True)  # no tab (after a registration): everything
    assert len(fresh_info.paths) == len(rs.ROUTES)
