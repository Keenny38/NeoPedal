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

"""Journal of requests (request_log): each request told without name or address, counted over the last hour, shown
by the Requests dialog of Upcoming Races; RaceOS options gone with their files (migration 2.51.13)"""

from __future__ import annotations

import pytest

from neopedal import request_log
from tests.test_race_schedule import fresh_info, item_named, page, pump, qml_warnings  # noqa: F401


@pytest.fixture(autouse=True)
def clean_log():
    request_log.clear()
    yield
    request_log.clear()


def test_journal_counts_last_hour_and_keeps_lines():
    for index in range(50):
        request_log.record(request_log.GITHUB, "GET repos/*/releases/latest", 200, 12, now=1000.0 + index)
    request_log.record(request_log.GITHUB, "GET repos/*/releases/latest", request_log.NOT_SENT, now=1100.0)
    snapshot = request_log.snapshot(now=1200.0)[request_log.GITHUB]
    assert snapshot["hour"] == 50  # a request not sent is not counted
    assert len(snapshot["lines"]) == request_log.KEEP_LINES and snapshot["lines"][0].status == request_log.NOT_SENT
    assert request_log.snapshot(now=1000.0 + 3600.0 + 25)[request_log.GITHUB]["hour"] == 24  # older than an hour
    assert "Nobody" not in request_log.snapshot()


def test_raceos_options_and_files_removed(tmp_path):
    from neopedal import rank_info
    from neopedal.setting_preupdate import preupdate_global_setting, preupdate_user_setting
    from neopedal.template.setting_global import GLOBAL_DEFAULT

    application = {"enable_online_driver_ranks": True, "enable_online_requests_economy": False, "theme": "x"}
    setting = {"application": dict(application)}
    preupdate_global_setting((2, 51, 12), setting)
    assert setting["application"] == {"theme": "x"}
    setting = {"application": dict(application)}
    preupdate_global_setting((2, 51, 13), setting)  # current setting: untouched
    assert setting["application"] == application
    user = {"standings": {"show_class_sof": True, "show_class_header": True},
            "session": {"show_field_level": True, "display_order_field_level": 4, "layout": 0}}
    preupdate_user_setting((2, 51, 12), user)
    assert user == {"standings": {"show_class_header": True}, "session": {"layout": 0}}
    assert "enable_online_driver_ranks" not in GLOBAL_DEFAULT["application"]
    assert GLOBAL_DEFAULT["application"]["enable_public_race_schedule"] is True
    for name in rank_info.FORMER_FILES:
        (tmp_path / name).write_text("{}", encoding="utf-8")
    (tmp_path / "kept.json").write_text("{}", encoding="utf-8")
    assert sorted(rank_info.remove_former_files(str(tmp_path))) == sorted(rank_info.FORMER_FILES)
    assert [path.name for path in tmp_path.iterdir()] == ["kept.json"]
    assert rank_info.remove_former_files(str(tmp_path)) == []  # nothing left: nothing done


# The page: age of the last read, requests dialog
def test_page_tells_age_and_lists_requests(qml_warnings, page):  # noqa: F811
    backend = page.backend
    backend.publish_status()
    assert backend.status["age"] and backend.status["readFull"]  # "Just now" / "5 min ago" and the exact moment
    assert backend.requestsReport() == []
    request_log.record(request_log.PUBLIC_SITE, "GET /", 200, 35)
    request_log.record(request_log.GITHUB, "GET repos/*/releases/latest", 0)
    report = {entry["name"]: entry for entry in backend.requestsReport()}
    assert report[request_log.PUBLIC_SITE]["summary"] == "1 requests in the last hour"
    assert [line["text"] for line in report[request_log.PUBLIC_SITE]["lines"]] == ["GET /  ·  200  ·  35 ms"]
    assert report["GitHub"]["summary"] == "1 requests in the last hour (limit 60)"
    assert report["GitHub"]["lines"][0]["text"].endswith("no answer")
    pump(0.1)
    assert item_named(page.view.rootObject(), "requestsButton").isVisible()
    assert not qml_warnings, qml_warnings


def test_requests_dialog_opens_with_the_report(qml_warnings, page):  # noqa: F811
    from PySide6.QtCore import QMetaObject, QObject

    request_log.record(request_log.GITHUB, "GET repos/*/releases/latest", 200, 35)
    root = page.view.rootObject()
    dialog = root.findChild(QObject, "requestsDialog")
    dialog.setProperty("report", page.backend.requestsReport())
    QMetaObject.invokeMethod(dialog, "open")
    pump(0.3)
    assert dialog.property("opened") is True
    assert not qml_warnings, qml_warnings
    QMetaObject.invokeMethod(dialog, "close")
    pump(0.1)
