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

"""Few RaceControl requests (2026-11-02: this connection refused for hours, the game's too, after many reads):
sign ins reused, requests counted per hour, wait after a 403 kept across restarts, rare routes read rarely"""

from __future__ import annotations

import json
import time

from neopedal import race_schedule_info as info
from neopedal.process import race_schedule as rs
from neopedal.process import raceos
from tests.test_race_schedule import NOW, fresh_info, iso, page  # noqa: F401

AUTH = json.dumps({"accessToken": "tok", "expiresAt": iso(NOW + 3600), "player": None}).encode()


class Http:
    """RaceControl answers: sign in answered, reads answered with status (200 by default)"""

    def __init__(self, status: int = 200):
        self.status = status
        self.calls: list[str] = []

    def __call__(self, method, url, body, headers, timeout):
        self.calls.append(url)
        if url == raceos.AUTH_URL:
            return (200, AUTH) if self.status == 200 else (self.status, b"")
        return self.status, b"[]"


def client_of(http, clock, block_file="", pace=False):
    def sleep(seconds):
        clock[0] += seconds

    return raceos.RaceOSClient(lambda: "ticket", http=http, clock=lambda: clock[0], wall_clock=lambda: NOW,
                               pace=pace, sleep=sleep, block_file=block_file)


def test_sign_in_answer_reused_for_a_while():
    clock = [1000.0]
    http = Http()
    client = client_of(http, clock)
    assert client.sign_in() is not None and client.sign_in() is not None
    assert http.calls.count(raceos.AUTH_URL) == 1  # player ranks of the recent sign in
    clock[0] += raceos.SIGN_IN_SECONDS
    assert client.sign_in() is not None and http.calls.count(raceos.AUTH_URL) == 2


def test_requests_counted_per_hour():
    clock = [1000.0]
    http = Http()
    client = client_of(http, clock, pace=True)
    for _ in range(raceos.MAX_PER_HOUR + 20):
        client.get("api/v1/hosted")
        clock[0] += 60.0 / raceos.MAX_PER_MINUTE  # never above the count per minute
    assert len(http.calls) == raceos.MAX_PER_HOUR
    clock[0] += 3600.0
    client.get("api/v1/hosted")
    assert len(http.calls) == raceos.MAX_PER_HOUR + 1


def test_wait_after_403_kept_across_restarts(tmp_path):
    path = str(tmp_path / ".raceos_block.json")
    clock = [1000.0]
    refused = Http(403)
    client = client_of(refused, clock, path)
    assert client.sign_in() is None and client.blocked_for() == raceos.BLOCK_SECONDS
    saved = json.loads((tmp_path / ".raceos_block.json").read_text(encoding="utf-8"))
    assert saved == {"until": NOW + raceos.BLOCK_SECONDS, "wait": 2 * raceos.BLOCK_SECONDS}
    # App started again: nothing asked before the end of the wait
    http = Http()
    again = client_of(http, [5.0], path)
    assert again.blocked_for() == raceos.BLOCK_SECONDS and again.get("api/v1/hosted") is None and not http.calls
    # Wait over: read again, file removed once answered
    later = raceos.RaceOSClient(lambda: "ticket", http=http, clock=lambda: 5.0,
                                wall_clock=lambda: NOW + raceos.BLOCK_SECONDS, block_file=path)
    assert later.blocked_for() == 0 and later.get("api/v1/hosted") == []
    assert not (tmp_path / ".raceos_block.json").exists()


def test_403_wait_doubled_up_to_longest():
    clock = [1000.0]
    client = client_of(Http(403), clock)
    waits = []
    for _ in range(5):
        client.sign_in()
        waits.append(client.blocked_for())
        clock[0] += client.blocked_for()
    assert waits == [3600.0, 7200.0, 14400.0, 21600.0, 21600.0]


def test_unreadable_block_file_ignored(tmp_path):
    path = tmp_path / ".raceos_block.json"
    for text in ("{", '{"until": "x"}', '{"until": true}', "[]", '{"until": 1e999}'):
        path.write_text(text, encoding="utf-8")
        assert client_of(Http(), [0.0], str(path)).blocked_for() == 0


def test_rare_routes_read_rarely(fresh_info, monkeypatch):  # noqa: F811
    clock = [NOW]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    info.read(live=True, servers=True)  # page shown on Hosted Servers: every route
    assert len(fresh_info.paths) == len(rs.ROUTES)
    monkeypatch.setattr(info, "_state", info.state()._replace(tried=info.state().tried - info.READ_SECONDS))
    clock[0] += info.READ_SECONDS
    count = len(fresh_info.paths)
    state = info.read()  # Home: rare routes not asked again (unless not answered), page routes never
    asked = fresh_info.paths[count:]
    answered = {key for key in rs.ROUTES if fresh_info.data.get(key) is not None}
    assert asked == [route for key, route in rs.ROUTES.items() if key not in info.PAGE_ROUTES
                     and (key.startswith("daily_") or key not in answered)]
    assert {"schedule", "weekly", "championships", "hosted"} <= answered
    assert state.status == info.READ and len(state.schedule.events) == 3 and state.schedule.championships
    assert set(state.schedule.missing) == set(rs.ROUTES) - answered - info.PAGE_ROUTES  # not asked: not missing
    # Disk copy keeps the answers not asked again, and counts as a read: an app restart asks nothing at once
    monkeypatch.setattr(info, "_state", info.State(rs.EMPTY, "", -1.0, 0))
    monkeypatch.setattr(info, "_disk_read", False)
    count = len(fresh_info.paths)
    restarted = info.read()
    assert len(fresh_info.paths) == count and len(restarted.schedule.events) == 3
    assert restarted.schedule.championships and not info.due() and not info.due(live=True)
    # An hour later (page shown, Daily tab): every route asked again but hosted servers
    clock[0] += info.SLOW_ROUTE_SECONDS
    monkeypatch.setattr(info, "_state", state._replace(tried=state.tried - info.SLOW_ROUTE_SECONDS))
    count = len(fresh_info.paths)
    info.read(live=True)
    assert fresh_info.paths[count:] == [route for key, route in rs.ROUTES.items() if key != "hosted"]


def test_old_disk_copy_read_again(fresh_info, monkeypatch):  # noqa: F811
    clock = [NOW]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    info.read()
    monkeypatch.setattr(info, "_state", info.State(rs.EMPTY, "", -1.0, 0))
    monkeypatch.setattr(info, "_disk_read", False)
    clock[0] += info.READ_SECONDS  # app started again 30 min later: read at once
    count = len(fresh_info.paths)
    info.read()
    assert len(fresh_info.paths) > count


def test_own_ranks_kept_across_restarts(tmp_path):
    path = str(tmp_path / ".raceos_ranks.json")
    player = {"name": "Keenny Hess", "id": "rc-1",
              "driverRank": {"rank": "Silver", "tier": 2, "progress": 40}, "safetyRank": None}

    class Http:
        calls = 0

        def __call__(self, method, url, body, headers, timeout):
            Http.calls += 1
            return 200, json.dumps({"accessToken": "tok", "expiresAt": iso(NOW + 1500), "player": player}).encode()

    wall = [NOW]

    def client():
        return raceos.RaceOSClient(lambda: "ticket", http=Http(), clock=lambda: 0.0, wall_clock=lambda: wall[0],
                                   ranks_file=path)

    first = client().fetch("7656", 1800.0)
    assert first is not None and first.driver.text == "Silver 2" and Http.calls == 1
    saved = (tmp_path / ".raceos_ranks.json").read_text(encoding="utf-8")
    assert "tok" not in saved and "ticket" not in saved  # ranks only, never the token
    wall[0] += 600  # app started again 10 min later: ranks of the file, no sign in
    assert client().fetch("7656", 1800.0) == first and Http.calls == 1
    assert client().fetch("other", 1800.0) is not None and Http.calls == 2  # other Steam account: signed in
    assert client().fetch("7656", 0.0) == first and Http.calls == 3  # after a session: new sign in asked
    wall[0] += 1800
    assert client().fetch("other", 1800.0) is not None and Http.calls == 4  # old: signed in again
    again = client()
    again.forget()  # option turned off: file removed
    assert not (tmp_path / ".raceos_ranks.json").exists()


def test_request_count_logged(caplog):
    clock = [1000.0]
    client = client_of(Http(), clock, pace=True)
    with caplog.at_level("INFO", logger="neopedal.process.raceos"):
        client.get("api/v1/hosted?page=1")
    assert "GET api/v1/hosted (2 requests in the last hour)" in caplog.text  # sign in, then the read
    assert "page=1" not in caplog.text


def test_refresh_never_twice_at_once(fresh_info):  # noqa: F811
    info.read(force=True)
    count = len(fresh_info.paths)
    info.read(force=True)  # asked again at once: not due, nothing asked
    assert len(fresh_info.paths) == count


# 2026-11-02 log: startup reads filled the minute, then "your places" asked 12 requests refused at once (12 log
# lines, places lost for 30 min) and a live field refused was counted as a miss
def test_room_left_and_one_line_per_refusal(caplog):
    clock = [1000.0]
    client = client_of(Http(), clock, pace=True)
    assert client.room() == raceos.MAX_PER_MINUTE
    with caplog.at_level("INFO", logger="neopedal.process.raceos"):
        for _ in range(raceos.MAX_PER_MINUTE + 5):
            client.get("api/v1/hosted")
    assert client.room() == 0
    assert caplog.text.count("requests not sent") == 1  # told once for the whole refusal
    clock[0] += 60.0
    assert client.room() == raceos.MAX_PER_MINUTE
    client._busy_time = clock[0] + 10  # RaceControl asked to wait
    assert client.room() == 0


def test_places_stop_without_room(fresh_info, monkeypatch):  # noqa: F811
    from tests.test_race_schedule import board_answer

    fresh_info.data[info.LEADERBOARD_ROUTE] = board_answer
    # room for the 2 requests of one place only (reserve left to the player's own asks)
    monkeypatch.setattr(fresh_info, "room", lambda: info.BACKGROUND_RESERVE + 3 - len(fresh_info.__dict__.get(
        "posts", [])), raising=False)
    boards = {key: rs.Board("daily", "beginner", "Track", "Layout", key) for key in ("a", "b", "c")}
    asked: set[str] = set()
    assert info.read_places(boards, asked) == {"a": (150, 250)}
    assert asked == {"a"} and len(fresh_info.posts) == 2


def test_places_left_asked_at_next_tick(page, monkeypatch):  # noqa: F811
    from tests.test_audit_g_qml_pages import pump

    backend = page.backend
    calls = []

    def read_places(boards, asked=None):
        calls.append(sorted(boards))
        if len(calls) == 1:  # no room: nothing asked
            return {}
        asked.update(boards)
        return {key: (3, 10) for key in boards}

    monkeypatch.setattr(info, "read_places", read_places)
    backend.read_places_due(force=True)
    for _ in range(100):
        pump(0.02)
        if calls and not backend.jobs.is_busy("places"):
            break
    assert calls and sorted(backend._places_left) == calls[0]  # kept for later, not lost for PLACES_SECONDS
    backend.read_places_left()
    for _ in range(100):
        pump(0.02)
        if len(calls) == 2 and not backend.jobs.is_busy("places"):
            break
    assert calls[1] == calls[0] and not backend._places_left
    assert all(backend._places[key] == (3, 10) for key in calls[0])


def test_live_field_not_asked_is_no_miss(page, monkeypatch):  # noqa: F811
    from neopedal.ui.quick import schedule_backend

    monkeypatch.setattr(info, "room", lambda: 0)
    assert schedule_backend.read_fields([("field:x", "daily", "ev-1", {"eventId": "ev-1"})]) == []
    backend = page.backend
    backend._live_fields["field:x"] = time.monotonic()
    backend.live_fields_read([], ("field:x",))
    assert "field:x" not in backend._live_fields  # asked again at a next tick
    assert backend._field_misses.get("ev-1", 0) == 0
