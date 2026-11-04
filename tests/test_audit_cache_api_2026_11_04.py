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

"""Cache & API audit follow-up 2026-11-04: online races kept in memory and on disk once settled (file tied to the game
account, bounded, removed with the online option), schedule disk copy tied to a game account"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from neopedal import race_schedule_info as info
from neopedal.process import race_schedule as rs
from tests.test_race_schedule import NOW, RESULT, FakeClient, fresh_info, iso  # noqa: F401


class ResultsClient(FakeClient):
    """Results history of RaceControl: races newest first, 2 per page, asked paths counted"""

    def __init__(self, races):
        super().__init__({})
        self.races = races

    def get(self, path, account=""):
        self.paths.append(path)
        if path.startswith("api/v1/results?"):
            page = int(path.split("page=")[1].split("&")[0])
            take = int(path.split("take=")[1].split("&")[0])
            return self.races[(page - 1) * take:page * take]
        if path.startswith("api/v1/result?"):
            event = path.split("eventId=")[1].split("&")[0]
            return next(race for race in self.races if race["eventId"] == event)
        return None


def race(number: int, hours_ago: float) -> dict:
    return {**RESULT, "eventId": f"race-{number}", "date": iso(NOW - hours_ago * 3600)}


@pytest.fixture
def results_info(monkeypatch, tmp_path):
    from neopedal import rank_info

    monkeypatch.setattr(info, "_page_heads", {})
    monkeypatch.setattr(info, "_kept_pages", {})
    monkeypatch.setattr(info, "_kept_races", {})
    monkeypatch.setattr(info, "_disk_results", None)
    monkeypatch.setattr(info, "_account", lambda: "")  # account not known: nothing on disk (see the disk tests)
    monkeypatch.setattr(info.cfg.path, "config", str(tmp_path) + os.sep)
    monkeypatch.setattr(info, "results_take", lambda _type: 2)
    monkeypatch.setattr(time, "time", lambda: NOW)
    monkeypatch.setattr(rank_info, "online_enabled", lambda: True)
    clients = []

    def make(races):
        client = ResultsClient(races)
        monkeypatch.setattr(rank_info, "online_client", lambda: client)
        clients.append(client)
        return client

    return make


def test_old_result_pages_asked_once_while_no_race_was_added(results_info):
    client = results_info([race(1, 2), race(2, 30), race(3, 40), race(4, 50), race(5, 60)])
    first = info.read_results("daily", 1)
    second = info.read_results("daily", 2)
    assert [item.event_id for item in first] == ["race-1", "race-2"] and second.answered == 2
    assert len(client.paths) == 2
    # Page reopened (new backend): page 1 asked again, page 2 not asked again (nothing driven since)
    assert [item.event_id for item in info.read_results("daily", 1)] == ["race-1", "race-2"]
    again = info.read_results("daily", 2)
    assert [item.event_id for item in again] == ["race-3", "race-4"] and again.answered == 2
    assert len(client.paths) == 3
    # A race driven meanwhile moves every page: the pages kept are dropped
    client.races.insert(0, race(0, 0.2))
    assert info.read_results("daily", 1)[0].event_id == "race-0"
    moved = info.read_results("daily", 2)
    assert [item.event_id for item in moved] == ["race-2", "race-3"]
    assert len(client.paths) == 5


def test_recent_race_pages_never_kept(results_info):
    client = results_info([race(1, 1), race(2, 3), race(3, 5), race(4, 7)])
    info.read_results("daily", 1)
    info.read_results("daily", 2)
    info.read_results("daily", 1)
    info.read_results("daily", 2)  # over for a few hours: ranks & penalties may still move
    assert len(client.paths) == 4


def test_page_without_the_first_one_is_not_kept(results_info):
    client = results_info([race(1, 30), race(2, 40), race(3, 50), race(4, 60)])
    info.read_results("daily", 2)
    info.read_results("daily", 2)
    assert len(client.paths) == 2  # head of the list unknown: nothing to tell it is still the same


def test_laps_of_a_settled_race_kept_in_memory(results_info, tmp_path):
    client = results_info([race(1, 2), race(2, 30)])
    assert info.read_result("race-2", 2) is not None and info.read_result("race-2", 2) is not None
    assert len(client.paths) == 1  # over for a day: laps kept
    info.read_result("race-1", 2)
    info.read_result("race-1", 2)
    assert len(client.paths) == 3  # over for 2 hours: asked again
    assert not (tmp_path / info.RESULTS_FILE).exists()  # game account not known: nothing on disk


def forget_memory(monkeypatch):
    """App restarted: memory empty, file read again"""
    monkeypatch.setattr(info, "_page_heads", {})
    monkeypatch.setattr(info, "_kept_pages", {})
    monkeypatch.setattr(info, "_kept_races", {})
    monkeypatch.setattr(info, "_disk_results", None)


def test_settled_races_and_pages_kept_on_disk_for_the_account(results_info, monkeypatch, tmp_path):
    monkeypatch.setattr(info, "_account", lambda: "76561198000000001")
    client = results_info([race(1, 2), race(2, 30), race(3, 40), race(4, 50), race(5, 60)])
    info.read_results("daily", 1)
    info.read_results("daily", 2)
    info.read_result("race-2", 2)
    info.read_result("race-1", 2)  # over for 2 hours: not kept
    saved = json.loads((tmp_path / info.RESULTS_FILE).read_text(encoding="utf-8"))
    assert saved["account"] == "76561198000000001" and list(saved["races"]) == [
        "api/v1/result?eventId=race-2&splitNo=2"] and list(saved["pages"]) == ["daily/2/2"]
    assert len(client.paths) == 4
    forget_memory(monkeypatch)  # restart: page 1 asked (it tells if a race was driven), the rest read from disk
    assert [item.event_id for item in info.read_results("daily", 1)] == ["race-1", "race-2"]
    assert [item.event_id for item in info.read_results("daily", 2)] == ["race-3", "race-4"]
    assert info.read_result("race-2", 2) is not None
    assert len(client.paths) == 5  # only page 1 (and race-1 still asked: not settled)


def test_disk_pages_dropped_when_a_race_was_driven(results_info, monkeypatch, tmp_path):
    monkeypatch.setattr(info, "_account", lambda: "76561198000000001")
    client = results_info([race(1, 2), race(2, 30), race(3, 40), race(4, 50)])
    info.read_results("daily", 1)
    info.read_results("daily", 2)
    forget_memory(monkeypatch)
    client.races.insert(0, race(0, 0.2))  # driven since: every page moves
    assert info.read_results("daily", 1)[0].event_id == "race-0"
    assert [item.event_id for item in info.read_results("daily", 2)] == ["race-2", "race-3"]
    assert len(client.paths) == 4  # page 2 asked again, not read from the old copy


def test_disk_results_of_another_account_or_option_off(results_info, monkeypatch, tmp_path):
    from neopedal import rank_info

    monkeypatch.setattr(info, "_account", lambda: "76561198000000001")
    client = results_info([race(1, 2), race(2, 30)])
    info.read_result("race-2", 2)
    forget_memory(monkeypatch)
    monkeypatch.setattr(info, "_account", lambda: "76561198000000002")  # another Steam account
    info.read_result("race-2", 2)
    assert len(client.paths) == 2
    forget_memory(monkeypatch)
    monkeypatch.setattr(rank_info, "online_enabled", lambda: False)  # online option off: file removed
    info.read_result("race-2", 2)
    assert not (tmp_path / info.RESULTS_FILE).exists()


def test_disk_results_bounded_and_invalid_file_ignored(results_info, monkeypatch, tmp_path):
    monkeypatch.setattr(info, "_account", lambda: "76561198000000001")
    (tmp_path / info.RESULTS_FILE).write_text("{not json", encoding="utf-8")
    races = [race(number, 30 + number) for number in range(info.RACES_KEEP + 4)]
    client = results_info(races)
    for number in range(len(races)):
        info.read_result(f"race-{number}", 2)
    assert len(json.loads((tmp_path / info.RESULTS_FILE).read_text(encoding="utf-8"))["races"]) == info.RACES_KEEP
    assert len(client.paths) == len(races)


def test_kept_races_are_bounded(results_info):
    races = [race(number, 30 + number) for number in range(info.RACES_KEEP + 5)]
    client = results_info(races)
    for number in range(len(races)):
        info.read_result(f"race-{number}", 2)
    assert len(info._kept_races) == info.RACES_KEEP
    info.read_result("race-0", 2)  # the oldest read was dropped: asked again
    assert len(client.paths) == len(races) + 1


def test_disk_copy_of_another_game_account_is_not_shown(fresh_info, monkeypatch):  # noqa: F811
    from neopedal import rank_info

    monkeypatch.setattr(info, "_game_running", lambda: True)
    monkeypatch.setattr(type(rank_info.ranks), "account", property(lambda _self: "steam-a"), raising=False)
    info.read()
    saved = rs.cache_account(json.loads(Path(info.cache_path()).read_text(encoding="utf-8")))
    assert saved == "steam-a"
    # Another Steam account starts the app: the copy (registrations marked for the first player) is ignored
    monkeypatch.setattr(info, "_state", info.State(rs.EMPTY, "", -1.0, 0))
    monkeypatch.setattr(info, "_disk_read", False)
    monkeypatch.setattr(info, "_answers", (None, {}))
    monkeypatch.setattr(type(rank_info.ranks), "account", property(lambda _self: "steam-b"), raising=False)
    info.load_disk()
    assert not info.state().schedule.read_time
    # Same account: shown
    monkeypatch.setattr(info, "_disk_read", False)
    monkeypatch.setattr(type(rank_info.ranks), "account", property(lambda _self: "steam-a"), raising=False)
    info.load_disk()
    assert info.state().schedule.read_time


def test_disk_copy_shown_before_the_account_is_known_dropped_when_it_differs(fresh_info, monkeypatch):  # noqa: F811
    from neopedal import rank_info

    monkeypatch.setattr(info, "_game_running", lambda: True)
    monkeypatch.setattr(type(rank_info.ranks), "account", property(lambda _self: "steam-a"), raising=False)
    info.read()
    monkeypatch.setattr(info, "_state", info.State(rs.EMPTY, "", -1.0, 0))
    monkeypatch.setattr(info, "_disk_read", False)
    monkeypatch.setattr(info, "_answers", (None, {}))
    monkeypatch.setattr(type(rank_info.ranks), "account", property(lambda _self: ""), raising=False)  # not located yet
    info.load_disk()
    assert info.state().schedule.read_time  # shown meanwhile
    monkeypatch.setattr(type(rank_info.ranks), "account", property(lambda _self: "steam-b"), raising=False)
    with info._lock:
        info._check_disk_account("steam-b")
    assert not info.state().schedule.read_time and info._known() == {}


class EtagHttp:
    """RaceControl that tags its answers (ETag) and answers 304 to the same tag: not known whether it does, only
    sent when it gives one"""

    def __init__(self, tag: str = '"v1"', body: bytes = b'[{"title": "WEC Weekly"}]'):
        self.tag, self.body = tag, body
        self.requests: list[dict] = []

    def __call__(self, method, url, body, headers, timeout):
        from neopedal.process import raceos

        self.requests.append(dict(headers))
        if url == raceos.AUTH_URL:
            return 200, b'{"accessToken": "tok", "expiresAt": "2099-01-01T00:00:00Z", "player": null}'
        if not self.tag:
            return raceos.Reply(200, self.body)
        if headers.get("If-None-Match") == self.tag:
            return raceos.Reply(304, b"", "", self.tag)
        return raceos.Reply(200, self.body, "", self.tag)


def etag_client(http):
    from neopedal.process import raceos

    return raceos.RaceOSClient(lambda: "ticket", http=http, clock=lambda: 1000.0, wall_clock=lambda: NOW, pace=False)


def test_unchanged_answer_asked_with_its_etag(fresh_info):  # noqa: F811
    http = EtagHttp()
    client = etag_client(http)
    assert client.get("api/v1/special-events/weekly") == [{"title": "WEC Weekly"}]
    assert "If-None-Match" not in http.requests[-1]  # first time: nothing to compare
    assert client.get("api/v1/special-events/weekly") == [{"title": "WEC Weekly"}]  # 304: answer kept
    assert http.requests[-1]["If-None-Match"] == '"v1"'
    http.tag, http.body = '"v2"', b'[{"title": "Next week"}]'  # changed: sent again, new tag kept
    assert client.get("api/v1/special-events/weekly") == [{"title": "Next week"}]
    assert client.get("api/v1/special-events/weekly") == [{"title": "Next week"}]
    assert http.requests[-1]["If-None-Match"] == '"v2"'


def test_no_etag_given_nothing_sent_or_kept(fresh_info):  # noqa: F811
    http = EtagHttp(tag="")
    client = etag_client(http)
    client.get("api/v1/hosted")
    client.get("api/v1/hosted")
    assert all("If-None-Match" not in request for request in http.requests) and not client._etags


def test_etag_answers_dropped_with_the_account_and_bounded(fresh_info):  # noqa: F811
    from neopedal.process import raceos

    http = EtagHttp()
    client = etag_client(http)
    for number in range(raceos.ETAG_ENTRIES + 5):
        client.get(f"api/v1/route-{number}")
    assert len(client._etags) == raceos.ETAG_ENTRIES
    client.forget()  # option off or account switched: nothing compared with another player's answer
    assert not client._etags
    client.get("api/v1/hosted")
    assert "If-None-Match" not in http.requests[-1]
    http.body = b"x" * (raceos.ETAG_MAX_BYTES + 1)
    client.get("api/v1/big")
    assert "api/v1/big" not in client._etags  # large answers are not kept


def test_every_online_duration_lives_in_net_policy_with_its_reason():
    """One place for the durations of requests to online services, each one saying why it is what it is"""
    import re

    from neopedal import net_policy

    source = Path(net_policy.__file__).read_text(encoding="utf-8")
    assignments = re.findall(r"^([A-Z][A-Z0-9_]*) = .*$", source, re.MULTILINE)
    assert len(assignments) > 50
    for line in source.splitlines():
        if re.match(r"^[A-Z][A-Z0-9_]* = ", line):
            assert "  # " in line, f"no reason given: {line}"
    assert net_policy.RACEOS_MAX_PER_HOUR == 120 and net_policy.RACEOS_MAX_PER_MINUTE == 12  # RaceControl limits


def test_modules_use_the_policy_values():
    from neopedal import net_policy, race_schedule_info
    from neopedal.process import driver_ranks, field_ranks, raceos

    assert raceos.MAX_PER_HOUR == net_policy.RACEOS_MAX_PER_HOUR
    assert race_schedule_info.READ_SECONDS == net_policy.SCHEDULE_READ_SECONDS
    assert driver_ranks.ONLINE_SECONDS == net_policy.RANKS_ONLINE_SECONDS
    assert field_ranks.KEEP_SECONDS == net_policy.FIELD_KEEP_SECONDS


def test_results_file_removed_at_startup_when_option_off(results_info, monkeypatch, tmp_path):
    from neopedal import rank_info

    (tmp_path / info.RESULTS_FILE).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(rank_info, "online_enabled", lambda: False)
    monkeypatch.setattr(info, "_disk_read", False)
    info.load_disk()
    assert not (tmp_path / info.RESULTS_FILE).exists()
