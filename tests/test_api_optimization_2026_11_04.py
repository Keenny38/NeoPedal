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

"""Journal of requests (request_log) and economy mode of the requests to RaceControl (net_policy): the journal tells
each request without name or address, economy mode stretches the waits and halves the hourly cap"""

from __future__ import annotations

import pytest

from neopedal import net_policy as policy
from neopedal import race_schedule_info as info
from neopedal import request_log
from neopedal.process import race_schedule as rs
from neopedal.process import raceos
from neopedal.setting import cfg
from tests.test_race_schedule import NOW  # noqa: F401
from tests.test_raceos_fewer_requests import Http, client_of


@pytest.fixture(autouse=True)
def clean_log():
    request_log.clear()
    yield
    request_log.clear()


def test_route_without_query_and_identifiers():
    assert request_log.route_of("api/v1/event/entries/12345?page=2") == "api/v1/event/entries/*"
    assert request_log.route_of("api/v1/championship/0f8fad5b-d9cb-469f-a165-70867728950e") == "api/v1/championship/*"
    assert request_log.route_of("api/v1/hosted") == "api/v1/hosted"
    assert len(request_log.route_of("a/" * 100)) <= 80


def test_journal_counts_last_hour_and_keeps_lines():
    for index in range(50):
        request_log.record("RaceControl", "GET api/v1/hosted", 200, 12, now=1000.0 + index)
    request_log.record("RaceControl", "GET api/v1/hosted", request_log.NOT_SENT, now=1100.0)
    snapshot = request_log.snapshot(now=1200.0)["RaceControl"]
    assert snapshot["hour"] == 50  # a request not sent is not counted
    assert len(snapshot["lines"]) == request_log.KEEP_LINES and snapshot["lines"][0].status == request_log.NOT_SENT
    assert request_log.sent_last_hour("RaceControl", now=1000.0 + 3600.0 + 25) == 24  # older than an hour dropped
    assert request_log.sent_last_hour("Nobody") == 0


def test_raceos_requests_are_in_the_journal():
    clock = [1000.0]
    client = client_of(Http(), clock, pace=True)
    assert client.get("api/v1/event/entries/987?x=1") == []
    lines = request_log.snapshot()["RaceControl"]["lines"]
    assert [line.route for line in lines] == ["GET api/v1/event/entries/*", "POST authenticate"]
    assert all(line.status == 200 for line in lines)
    assert "987" not in repr(lines) and "x=1" not in repr(lines)


def test_requests_not_sent_are_in_the_journal(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(raceos, "MAX_PER_HOUR", 3)
    client = client_of(Http(), clock, pace=True)
    for _ in range(6):
        client.get("api/v1/hosted")
        clock[0] += 10.0
    statuses = [line.status for line in request_log.snapshot()["RaceControl"]["lines"]]
    assert request_log.NOT_SENT in statuses and request_log.snapshot()["RaceControl"]["hour"] == 3


def test_economy_off_changes_nothing(ui_env, monkeypatch):
    monkeypatch.setitem(cfg.application, "enable_online_requests_economy", False)
    assert not policy.economy() and policy.stretch(600.0) == 600.0 and policy.hour_cap(120) == 120
    assert info.read_seconds(True) == info.LIVE_READ_SECONDS and info.read_seconds(False) == info.READ_SECONDS


def test_economy_stretches_waits_and_halves_the_cap(ui_env, monkeypatch):
    monkeypatch.setitem(cfg.application, "enable_online_requests_economy", True)
    assert policy.economy() and policy.stretch(600.0) == 1200.0 and policy.hour_cap(120) == policy.ECONOMY_HOUR_CAP
    assert policy.hour_cap(30) == 30  # never raised
    assert info.read_seconds(True) == 2 * info.LIVE_READ_SECONDS and info.read_seconds(False) == 2 * info.READ_SECONDS


def test_economy_sends_half_the_requests_in_an_hour(ui_env, monkeypatch):
    def sent_in_an_hour(economy: bool) -> int:
        monkeypatch.setitem(cfg.application, "enable_online_requests_economy", economy)
        clock = [1000.0]
        http = Http()
        client = client_of(http, clock, pace=True)
        for _ in range(raceos.MAX_PER_HOUR + 30):
            client.get("api/v1/hosted")
            clock[0] += 5.0
        return len(http.calls)

    assert sent_in_an_hour(False) == raceos.MAX_PER_HOUR
    assert sent_in_an_hour(True) == policy.ECONOMY_HOUR_CAP


def test_economy_no_second_read_before_twice_the_wait(ui_env, monkeypatch):
    monkeypatch.setitem(cfg.application, "enable_online_requests_economy", True)
    monkeypatch.setattr(info, "_state", info.State(rs.EMPTY, info.READ, 1000.0, 0))
    monkeypatch.setattr(info, "_busy_for", lambda: 0.0)
    assert not info.due(1000.0 + info.READ_SECONDS + 1)  # normal mode would read now
    assert info.due(1000.0 + 2 * info.READ_SECONDS)
    monkeypatch.setitem(cfg.application, "enable_online_requests_economy", False)
    assert info.due(1000.0 + info.READ_SECONDS)


def test_economy_option_is_declared_and_translated():
    import json
    import os

    from neopedal.template.setting_global import GLOBAL_DEFAULT

    assert GLOBAL_DEFAULT["application"]["enable_online_requests_economy"] is False
    base = os.path.join(os.path.dirname(info.__file__), "i18n", "data")
    with open(os.path.join(base, "fr_options.json"), encoding="utf-8") as file:
        assert "enable_online_requests_economy" in json.load(file)


# The page: age of the last read, requests dialog
from tests.test_race_schedule import fresh_info, item_named, page, pump, qml_warnings  # noqa: F401


def test_page_tells_age_and_lists_requests(qml_warnings, page):  # noqa: F811
    backend = page.backend
    backend.publish_status()
    assert backend.status["age"] and backend.status["readFull"]  # "Just now" / "5 min ago" and the exact moment
    assert backend.requestsReport() == []
    request_log.record(request_log.RACE_CONTROL, "GET api/v1/hosted", 200, 35)
    request_log.record(request_log.RACE_CONTROL, "GET api/v1/special-events/special", request_log.NOT_SENT)
    request_log.record(request_log.GITHUB, "GET repos/*/releases/latest", 0)
    report = {entry["name"]: entry for entry in backend.requestsReport()}
    assert f"1 requests in the last hour (limit {raceos.MAX_PER_HOUR})" == report["RaceControl"]["summary"]
    assert [line["text"] for line in report["RaceControl"]["lines"]] == [
        "GET api/v1/special-events/special  ·  not sent (limits)", "GET api/v1/hosted  ·  200  ·  35 ms"]
    assert report["GitHub"]["summary"] == "1 requests in the last hour (limit 60)"
    assert report["GitHub"]["lines"][0]["text"].endswith("no answer")
    pump(0.1)
    assert item_named(page.view.rootObject(), "requestsButton").isVisible()
    assert not qml_warnings, qml_warnings


def test_requests_dialog_opens_with_the_report(qml_warnings, page):  # noqa: F811
    from PySide6.QtCore import QMetaObject, QObject

    request_log.record(request_log.RACE_CONTROL, "GET api/v1/hosted", 200, 35)
    root = page.view.rootObject()
    dialog = root.findChild(QObject, "requestsDialog")
    dialog.setProperty("report", page.backend.requestsReport())
    QMetaObject.invokeMethod(dialog, "open")
    pump(0.3)
    assert dialog.property("opened") is True
    assert not qml_warnings, qml_warnings
    QMetaObject.invokeMethod(dialog, "close")
    pump(0.1)
