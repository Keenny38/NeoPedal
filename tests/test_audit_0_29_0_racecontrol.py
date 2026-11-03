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

"""Pre-release audit 0.29.0, RaceControl & Upcoming Races (report audit_0.29.0_2026-11-02.md, section 3): fakes
only, nothing asked to RaceControl or the game"""

from __future__ import annotations

import json
import threading
import time
from itertools import pairwise

from neopedal import race_schedule_info as info
from neopedal.process import driver_ranks as dr
from neopedal.process import field_ranks as fr
from neopedal.process import race_schedule as rs
from neopedal.process import raceos
from tests.test_field_ranks import make_field
from tests.test_online_ranks import PLAYER, FakeOnline, make_watcher, storage_text
from tests.test_race_schedule import NOW, answers, fresh_info, iso, page, race_config  # noqa: F401
from tests.test_raceos_fewer_requests import Http, client_of


# B2: drivers of a read not sent (local limits, waiting) or not answered asked again soon, not MISSING_SECONDS later
def test_b2_field_read_not_sent_asked_again_soon():
    field, source, clock = make_field()
    source.online = False  # post gives None: refused by the limiter, waiting after a 429, offline
    field.poll(["Ghost Driver", "Nick Cloat"])
    assert len(source.requests) == 1
    clock[0] = fr.CHECK_SECONDS
    field.poll(["Ghost Driver", "Nick Cloat"])
    assert len(source.requests) == 1  # not every check
    source.online = True
    clock[0] = fr.RETRY_SECONDS
    field.poll(["Ghost Driver", "Nick Cloat"])
    assert len(source.requests) == 2 and field.ranks_of("Nick Cloat") is not None
    # Answered without a profile: that one waits MISSING_SECONDS
    clock[0] = fr.RETRY_SECONDS * 2
    field.poll(["Ghost Driver", "Nick Cloat"])
    assert len(source.requests) == 2
    clock[0] = fr.RETRY_SECONDS + fr.MISSING_SECONDS
    field.poll(["Ghost Driver", "Nick Cloat"])
    assert len(source.requests) == 3 and "Ghost Driver" in source.requests[-1]


def test_b2_known_driver_read_failed_kept_and_asked_again_soon():
    field, source, clock = make_field()
    field.poll(["Nick Cloat"])
    clock[0] = fr.KEEP_SECONDS
    source.online = False
    field.poll(["Nick Cloat"])
    assert len(source.requests) == 2 and field.ranks_of("Nick Cloat") is not None  # known ranks kept
    source.online = True
    clock[0] = fr.KEEP_SECONDS + fr.RETRY_SECONDS
    field.poll(["Nick Cloat"])
    assert len(source.requests) == 3


# B3: room() (GUI thread) never waits for a request pacing on another thread
def test_b3_room_never_waits_for_a_paced_request():
    clock = [1000.0]
    sleeping, release = threading.Event(), threading.Event()
    blocking = [False]

    def sleep(seconds):
        if blocking[0]:
            sleeping.set()
            release.wait(5)
        clock[0] += seconds

    client = raceos.RaceOSClient(lambda: "ticket", http=Http(), clock=lambda: clock[0], wall_clock=lambda: NOW,
                                 pace=True, sleep=sleep)
    assert client.get("api/v1/hosted") == []  # signed in: token kept
    blocking[0] = True
    worker = threading.Thread(target=lambda: client.get("api/v1/hosted"), daemon=True)
    worker.start()
    try:
        assert sleeping.wait(5)  # worker waits REQUEST_GAP
        began = time.monotonic()
        room = client.room()
        assert time.monotonic() - began < 0.5
        assert room == raceos.MAX_PER_MINUTE - 2
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive() and client.room() == raceos.MAX_PER_MINUTE - 3


def test_b3_requests_still_paced_when_another_thread_sends_meanwhile():
    clock = [1000.0]
    client = None
    nested = []

    def sleep(seconds):
        clock[0] += seconds
        if not nested:  # another thread sends while this one sleeps (lock free: no deadlock)
            nested.append(client._pace("other"))

    http = Http()
    client = raceos.RaceOSClient(lambda: "ticket", http=http, clock=lambda: clock[0], wall_clock=lambda: NOW,
                                 pace=True, sleep=sleep)
    assert client.get("api/v1/hosted") == []
    assert nested == [True]
    sent = list(client._sent)
    assert len(sent) == 3 and all(later - earlier >= raceos.REQUEST_GAP for earlier, later in pairwise(sent))


# B4: what the Upcoming Races page asked kept when the page is made again (released after a while hidden)
def test_b4_page_memory_kept_per_client(fresh_info, monkeypatch):  # noqa: F811
    from neopedal import rank_info

    memory = info.page_memory()
    assert info.page_memory() is memory and memory.places_time < 0
    other = object()
    monkeypatch.setattr(rank_info, "online_client", lambda: other)
    assert info.page_memory() is not memory  # other client (tests): nothing kept from the last one


def test_b4_page_made_again_asks_nothing_again(page, monkeypatch):  # noqa: F811
    from neopedal.ui.quick.schedule_backend import RaceScheduleBackend

    backend = page.backend
    backend._places_time = time.monotonic()
    backend.places_read({"board-a": (3, 10), "board-b": (0, 0)})
    backend._field_misses["ev-1"] = 2
    asked = []
    monkeypatch.setattr(info, "read_places", lambda boards, _asked=None: asked.append(sorted(boards)) or {})
    again = RaceScheduleBackend(page)
    try:
        assert again._places == {"board-a": (3, 10), "board-b": (0, 0)}  # shown at once
        assert "board-b" in again._unranked and again._field_misses == {"ev-1": 2}
        again.read_places_due()
        assert asked == []  # places read less than PLACES_SECONDS ago
        again._places_time = -1e9
        assert backend._places_time == -1e9  # one memory
    finally:
        again.deleteLater()


# B5: online ranks dated by the sign in that read them (reused sign in, saved by an earlier run), never "now"
class TimedOnline(FakeOnline):
    def __init__(self, ranks, read_time):
        super().__init__(ranks)
        self.read_time = read_time

    def fetch_timed(self, account, max_age=0.0):
        self.fetched.append(account)
        return (self.ranks, self.read_time) if self.ranks is not None else None


def test_b5_old_online_ranks_lose_to_newer_game_file(tmp_path):
    online = TimedOnline(raceos.player_ranks(PLAYER), 1_850_000_000.0)  # older than the game file (1.9e9)
    watcher, _path, _results, history = make_watcher(tmp_path, online, [0.0], storage_text())
    watcher.check()
    assert online.fetched and not watcher.online and watcher.player.driver.text == "Silver 2"
    assert all(entry.time != 2_000_000_000 for entry in dr.read_history(str(history)))  # no entry dated "now"


def test_b5_online_ranks_keep_their_sign_in_time(tmp_path):
    online = TimedOnline(raceos.player_ranks(PLAYER), 1_950_000_000.0)
    watcher, _path, _results, history = make_watcher(tmp_path, online, [0.0], storage_text())
    watcher.check()
    assert watcher.online and watcher.updated == 1_950_000_000
    assert dr.read_history(str(history))[-1].time == 1_950_000_000


def test_b5_client_tells_sign_in_time(tmp_path):
    wall = [NOW]
    auth = json.dumps({"accessToken": "tok", "expiresAt": iso(NOW + 3600), "player": PLAYER}).encode()

    def http(method, url, body, headers, timeout):
        return 200, auth

    ranks_file = str(tmp_path / ".raceos_ranks.json")
    client = raceos.RaceOSClient(lambda: "ticket", http=http, clock=lambda: 0.0, wall_clock=lambda: wall[0],
                                 ranks_file=ranks_file)
    found = client.fetch_timed()
    assert found is not None and found[1] == NOW
    wall[0] = NOW + 300  # sign in reused: its own time
    assert client.fetch_timed()[1] == NOW and client.fetch() == found[0]
    # Next run: ranks saved on disk, with their time
    again = raceos.RaceOSClient(lambda: "", http=http, clock=lambda: 0.0, wall_clock=lambda: wall[0],
                                ranks_file=ranks_file)
    assert again.fetch_timed() == (found[0], NOW)


# L1: registration not sent (limits, waiting) or sent without answer told apart from "did not answer"
def test_l1_send_tells_not_sent():
    clock = [1000.0]
    client = client_of(Http(), clock, pace=True)
    statuses = [client.send("POST", rs.REGISTER_ROUTE, {})[0] for _ in range(raceos.MAX_PER_MINUTE)]
    assert statuses[0] == 200 and statuses[-1] == raceos.NOT_SENT  # sign in counted: limit reached
    clock[0] += 60.0
    silent = client_of(Http(0), clock)  # sign in not answered: not signed in
    assert silent.send("POST", rs.REGISTER_ROUTE, {}) == (raceos.NOT_SIGNED, None)
    signed = client_of(Http(), clock)
    signed.sign_in()
    signed._http = lambda *args: (0, b"")  # sent, no answer (timeout)
    assert signed.send("POST", rs.REGISTER_ROUTE, {}) == (0, None)
    signed._busy_time = clock[0] + 60.0  # RaceControl asks to wait
    assert signed.send("POST", rs.REGISTER_ROUTE, {})[0] == raceos.NOT_SENT


def test_l1_register_reasons(fresh_info, monkeypatch):  # noqa: F811
    from neopedal.ui.quick.schedule_backend import not_done_text

    reply = [(raceos.NOT_SENT, None)]
    fresh_info.send = lambda method, path, payload, account="": reply[0]
    assert info.unregister("daily", "e") == (False, info.NOT_SENT)
    reply[0] = (0, None)
    assert info.unregister("daily", "e") == (False, info.NO_ANSWER)
    reply[0] = (raceos.NOT_SIGNED, None)
    assert info.unregister("daily", "e") == (False, "")
    reply[0] = (400, {"status": "ERROR", "message": "Closed"})
    assert info.unregister("daily", "e") == (False, "Closed")
    texts = [not_done_text(reason, "Refused: %1", "Silent") for reason in (info.NOT_SENT, info.NO_ANSWER, "", "X")]
    assert texts[0].startswith("Not sent: too many requests") and "may be done" in texts[1]
    assert texts[2:] == ["Silent", "Refused: X"]


# L2: server of your split asked from the start to SPLIT_SECONDS after it, stopped after SPLIT_MISSES misses
def test_l2_split_reads_stop(ui_env, fresh_info, monkeypatch):  # noqa: F811
    from neopedal import rank_info
    from neopedal.ui.quick import race_watch as rw

    monkeypatch.setattr(rank_info.ranks, "read_soon", lambda: None)

    data = answers()
    mine = race_config("LMP2 Fixed", NOW + 600)
    mine["registrations"] = [{"driver": {"id": "me-id"}}]
    data["daily_beginner"] = [mine]
    fresh_info.data = data
    info.read()
    event = next(item for item in info.state().schedule.events if item.title == "LMP2 Fixed")
    start = next(item for item in event.starts if item.event_id == "id-LMP2 Fixed")
    clock = [start.time - 30]
    watch = rw.RaceWatch(None, clock=lambda: clock[0])
    watch._timer.stop()
    runs = []
    monkeypatch.setattr(watch._jobs, "run", lambda name, *args, **kwargs: runs.append(name))
    monkeypatch.setattr(info, "read", lambda *args, **kwargs: info.state())
    watch.check()
    assert runs[-1] == "your race"
    for _ in range(rw.SPLIT_MISSES):
        runs.clear()
        watch.check()
        assert "your server" in runs
        watch.split_read(event, start, None)
    runs.clear()
    watch.check()
    assert "your server" not in runs  # never answered: no longer asked
    watch._misses.clear()
    monkeypatch.setattr(info, "room", lambda: 0)  # RaceControl asks to wait: not asked, no miss
    watch.check()
    assert "your server" not in runs and not watch._misses
    monkeypatch.setattr(info, "room", lambda: 8)
    watch.split_read(event, start, rs.SplitState(False))  # answered, not ready yet
    clock[0] = start.time + rw.SPLIT_SECONDS + 1
    watch.check()
    assert "your server" not in runs  # long after the start: no longer asked


# L3: answers kept for the schedule once a registration changed it on the page
def test_l3_answers_follow_registered_schedule(fresh_info, monkeypatch):  # noqa: F811
    monkeypatch.setattr(info, "_registered", {})
    info.read()
    known = info._known()
    assert known
    info._set_registered("id-LMP2 Fixed", True)
    assert info._known() == known and info._answers[0] is info.state().schedule


# L4: wins & podiums counted in your class in multi-class races, clean races over races with a place
def _row(position: int, class_position: int, name: str, vehicle_class: str, sr_change: float | None = 0.5):
    return rs.ResultRow(position, class_position, 0, name, "", vehicle_class, "", "", 0.0, 0.0, 0, "", 0.0,
                        sr_change, ())


def _race(*rows):
    return rs.OnlineResult("e", 1, NOW, "daily", "", "Race", "Track", rows)


def test_l4_summary_in_class_places():
    from neopedal.ui.quick.online_results import summary_of

    multi = _race(_row(1, 1, "Hyper", "Hypercar"), _row(2, 1, "Me", "LMP2"))
    single = _race(_row(1, 1, "Other", "GT3"), _row(2, 2, "Me", "GT3"))
    unplaced = _race(_row(0, 0, "Me", "GT3"), _row(1, 1, "Other", "GT3"))
    figures = {item["label"]: item["value"] for item in summary_of([multi, single, unplaced], "Me")["figures"]}
    assert figures["Wins"] == "1" and figures["Podiums"] == "2" and figures["Avg. Finish"] == "P1.5"
    assert figures["Clean Races"] == "2/2"  # the race without your place left out of both counts
