"""Non-regression tests of the bug audit of the Upcoming Races page & what serves it (2026-11-02,
audit_bugs_upcoming_races_2026-11-02.md): simulated RaceControl answers, clock & time zone, never network"""

from __future__ import annotations

import calendar
import io
import json
import threading
import time
import types
from pathlib import Path

from PySide6.QtCore import Q_ARG, Q_RETURN_ARG, QCoreApplication, QMetaObject, QObject

from neopedal import race_schedule_info as info
from neopedal.process import race_schedule as rs
from neopedal.process import raceos
from neopedal.ui.quick import stats_overview
from tests.test_audit_g_qml_pages import click, item_named, items_of, pump
from tests.test_driver_stats_viewer import backend, dialogs, settle, window  # noqa: F401
from tests.test_perf_page_state import qml_warnings  # noqa: F401
from tests.test_race_schedule import (  # noqa: F401
    CARS,
    NOW,
    TRACKS,
    FakeClient,
    answers,
    board_answer,
    fresh_info,
    iso,
    online,
    page,
    schedule,
)

# Reading, parsers & reminders (B-001..B-007)


DAY = calendar.timegm((2026, 11, 2, 0, 0, 0))  # 2026-11-02 00:00 UTC
OLD = NOW + 600  # start of "LMP2 Fixed" a reminder is set for (schedule of tests.test_race_schedule)
RACE = "daily/beginner/LMP2 Fixed"


def daily_answer(tier: str, title: str, first: float, every: float, count: int) -> dict:
    """daily/schedule of one UTC day (real answer: times 00:xx -> 23:xx of the day)"""
    return {"tiers": {tier: [{"eventname": title, "track": "Sebring", "scene": "SebringWEC", "cars": [],
                               "duration": "31m30s", "times": [iso(first + i * every) for i in range(count)]}]},
            "frequency": {tier: "45 mins"}}


def daily_item(tier: str, title: str, start: float) -> dict:
    return {"id": f"id-{int(start)}", "registrations": 3, "configuration": {
        "title": title, "starts": iso(start), "registrationOpens": iso(start - 1800),
        "tier": {"name": tier, "entryRequirement": {"rank": "Bronze", "tier": 0}},
        "content": {"track": {"name": "SebringWEC", "friendly": "Sebring",
                              "subItems": [{"name": "Sebring International", "scn": "SebringWEC"}]}},
        "sessions": [{"type": "RACE1", "duration": "20m"}]}}


def read_schedule(moved: dict[float, float | None], missing: tuple[str, ...] = ()) -> rs.Schedule:
    """Schedule read again: starts of "LMP2 Fixed" moved (old -> new time, None: cancelled)"""
    found = schedule()
    events = []
    for event in found.events:
        if event.title == "LMP2 Fixed":
            starts = [start._replace(time=moved.get(start.time, start.time)) for start in event.starts]
            event = event._replace(starts=tuple(start for start in starts if start.time is not None))
        events.append(event)
    return found._replace(events=tuple(events), missing=found.missing + missing)


def make_reminders(monkeypatch, now):
    from neopedal.ui.notification import message_text
    from neopedal.ui.quick import schedule_reminders as sr

    told = []
    monkeypatch.setattr(sr.RaceReminders, "tell",
                        staticmethod(lambda message, *args, **kwargs: told.append(message_text(message))))
    reminders = sr.RaceReminders(clock=lambda: now[0])
    reminders.set(f"{RACE}@{int(OLD)}", "LMP2 Fixed", "Portimao", OLD, 5)
    return reminders, told


def set_state(monkeypatch, found: rs.Schedule, status: str = info.READ, serial: int = 7):
    monkeypatch.setattr(info, "_state", info.State(found, status, 0.0, serial))


# B-001: a reminder follows its start moved by RaceControl (closest start of the race within 1 h), told
def test_b001_reminder_moved_with_its_start(ui_env, monkeypatch):
    from neopedal.ui.quick import schedule_reminders as sr
    from neopedal.ui.quick.schedule_view import start_text

    now = [NOW]
    reminders, told = make_reminders(monkeypatch, now)
    set_state(monkeypatch, read_schedule({OLD: OLD + 1800}))  # 15:00 -> 15:30
    reminders.check()
    assert reminders.keys() == {f"{RACE}@{int(OLD + 1800)}": 5}
    assert told == [sr.tr("Reminder moved: %1 now starts at %2").replace("%1", "LMP2 Fixed").replace(
        "%2", start_text(OLD + 1800, NOW)) + " (Portimao)"]
    now[0] = OLD - 300  # old reminder time: nothing told
    reminders.check()
    assert len(told) == 1
    now[0] = OLD + 1800 - 300
    reminders.check()
    assert told[1] == "LMP2 Fixed starts in 5 min (Portimao)" and reminders.keys() == {}
    again = sr.RaceReminders(clock=lambda: now[0])  # saved
    assert again.keys() == {}


# B-001: a reminder whose start is cancelled (no start of the race within 1 h) is removed, told
def test_b001_reminder_of_cancelled_start_removed(ui_env, monkeypatch):
    from neopedal.ui.quick import schedule_reminders as sr

    now = [NOW]
    reminders, told = make_reminders(monkeypatch, now)
    set_state(monkeypatch, read_schedule({OLD: None, NOW + 3300: NOW + 3300 + 3600}))
    reminders.check()
    assert reminders.keys() == {}
    assert len(told) == 1 and told[0].startswith(sr.tr("Reminder removed: %1 no longer starts at %2").replace(
        "%1", "LMP2 Fixed").split("%2")[0])
    now[0] = OLD - 300
    reminders.check()
    assert len(told) == 1  # never told at the old time
    assert sr.RaceReminders(clock=lambda: now[0]).keys() == {}


# B-001: nothing changed while the schedule is not read (game closed, failed read, route of the race not answered)
def test_b001_reminder_kept_when_schedule_not_read(ui_env, monkeypatch):
    now = [NOW]
    reminders, told = make_reminders(monkeypatch, now)
    key = {f"{RACE}@{int(OLD)}": 5}
    cancelled = read_schedule({OLD: None, NOW + 3300: None})
    for serial, (found, status) in enumerate([
            (cancelled, info.NO_GAME), (cancelled, info.FAILED), (cancelled, ""),
            (cancelled._replace(read_time=0.0), info.READ),
            (read_schedule({OLD: None, NOW + 3300: None}, ("daily_beginner",)), info.READ),
            (read_schedule({OLD: None, NOW + 3300: None}, ("schedule",)), info.READ),
            (cancelled._replace(events=()), info.READ)], 10):  # race missing: never judged
        set_state(monkeypatch, found, status, serial)
        reminders.check()
        assert reminders.keys() == key and told == [], (serial, status)
    set_state(monkeypatch, read_schedule({}), info.READ, 30)  # start still there: kept untold
    reminders.check()
    assert reminders.keys() == key and told == []
    now[0] = OLD - 300
    reminders.check()
    assert told == ["LMP2 Fixed starts in 5 min (Portimao)"]


# B-002: reminder told when the app starts (or the PC wakes) after its time but before the start, real time left
def test_b002_reminder_told_when_app_started_late_before_start(ui_env, monkeypatch):
    from neopedal.ui.notification import message_text
    from neopedal.ui.quick import schedule_reminders as sr

    start = DAY + 3600
    entry = {"key": "k", "title": "LMP3 Fixed", "track": "Sebring", "start": start, "minutes": 30}
    assert sr.due_reminders([entry], start - 15 * 60) == ([entry], [])  # 15 min after the reminder time
    assert sr.due_reminders([entry], start) == ([], [])  # start passed: dropped
    now = [start - 15 * 60]
    told = []
    monkeypatch.setattr(sr.RaceReminders, "tell",
                        staticmethod(lambda message, *args, **kwargs: told.append(message_text(message))))
    reminders = sr.RaceReminders(clock=lambda: now[0])
    reminders.set("k", "LMP3 Fixed", "Sebring", start, 30)
    reminders.check()
    assert told == ["LMP3 Fixed starts in 15 min (Sebring)"] and reminders.keys() == {}


# B-003: next start of the daily list kept after the last start of the UTC day of the schedule
def test_b003_daily_race_kept_after_last_start_of_utc_day():
    last = DAY + 23 * 3600 + 15 * 60  # 23:15 UTC, last start of the day
    found = rs.parse_schedule({"schedule": daily_answer("beginner", "LMP3 Fixed", DAY, 2700, 32),
                               "daily_beginner": [daily_item("beginner", "LMP3 Fixed", DAY + 86400)]},
                              {}, {}, last + 3600)
    event = found.events[0]
    assert event.starts[-1].time == DAY + 86400 and event.starts[-1].registrations == 3
    assert [start.time for start in rs.next_starts(event, last + 1900)] == [DAY + 86400]


# B-004: entry requirement of the daily tier (game menu rule) kept when the daily list is not answered
def test_b004_requirement_kept_without_daily_list():
    found = rs.parse_schedule({"schedule": daily_answer("advanced", "ELMS Super 60", DAY, 5400, 16)}, {}, {}, DAY)
    assert found.events[0].requirement == rs.Requirement("Gold", 0)
    found = rs.parse_schedule({"daily_intermediate": [daily_item("intermediate", "GT3", DAY + 600)]}, {}, {}, DAY)
    assert found.events[0].requirement == rs.Requirement("Silver", 0)


# B-005: empty date of RaceControl (0001-01-01) read as no date: fallbacks used
def test_b005_empty_date_read_as_none():
    assert rs._time("0001-01-01T00:00:00Z") == 0.0
    assert rs._time("1970-01-01T00:00:00Z") == 0.0
    item = daily_item("beginner", "GT3", DAY + 600)
    item["configuration"]["starts"] = "0001-01-01T00:00:00Z"
    item["raceStartsAt"] = iso(DAY + 600)
    item["configuration"]["registrationOpens"] = "0001-01-01T00:00:00Z"
    item["registrationOpens"] = iso(DAY - 1200)
    event = rs.parse_daily(None, {"beginner": [item]})[0]
    assert event.starts == (rs.Start(DAY + 600, 3, DAY - 1200, False, f"id-{int(DAY + 600)}"),)
    coop = rs.parse_coop([{"name": "x", "track": "Spa", "starts": iso(DAY), "ends": "0001-01-01T00:00:00Z"}])
    assert coop[0].ends == 0.0


# B-006: an answer the parser cannot read marks the read tried (no read again at every tick), old schedule kept
def test_b006_read_marked_tried_when_parse_fails(fresh_info, monkeypatch):  # noqa: F811
    monkeypatch.setattr(info, "FORCE_SECONDS", 0.0)  # refresh asked again at once read too
    first = info.read()
    assert first.status == info.READ

    def unreadable(*args):
        raise KeyError("x")

    monkeypatch.setattr(rs, "parse_schedule", unreadable)
    state = info.read(force=True)
    assert state.status == info.FAILED and state.schedule is first.schedule
    assert not info.due()


# B-006: giant numbers & non finite durations read as unreadable
def test_b006_giant_numbers_unreadable(fresh_info):  # noqa: F811
    assert rs._int("1e999") == 0 and rs._int("1e999", -1) == -1
    assert rs.time_of_day("1" + "0" * 400 + "h") == ""
    fresh_info.data["championships"] = [{"name": "x", "rounds": [{"no": "1e999", "sessions": [
        {"type": "Race", "duration": "20m", "timeOfDay": "1" + "0" * 400 + "h"}]}]}]
    state = info.read(force=True)
    assert state.status == info.READ and state.schedule.championships[0].rounds[0].number == 0
    assert not info.due()


class Http429:
    """RaceControl answers: sign in, then statuses given (429 with Retry-After)"""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, method, url, body, headers, timeout):
        self.calls.append(url)
        if url == raceos.AUTH_URL:
            return 200, json.dumps({"accessToken": "tok", "expiresAt": iso(NOW + 3600), "player": None}).encode()
        status, retry = self.answers.pop(0)
        return raceos.Reply(status, b"[1]" if status == 200 else b"", retry) if retry else (status, b"[1]")


# B-007: after a 429 nothing is asked until the wait asked (Retry-After), else 5 min doubled up to 1 h
def test_b007_client_waits_after_429():
    clock = [1000.0]
    http = Http429((429, "120"), (429, ""), (429, ""), (200, ""), (429, ""))
    client = raceos.RaceOSClient(lambda: "ticket", http=http, clock=lambda: clock[0], wall_clock=lambda: NOW)
    assert client.get("api/v1/a") is None and client.busy_for() == 120
    asked = len(http.calls)
    assert client.get("api/v1/b") is None and len(http.calls) == asked  # never sent while waiting
    clock[0] += 120
    assert client.get("api/v1/c") is None and client.busy_for() == raceos.BUSY_SECONDS * 2  # second 429: doubled
    clock[0] += raceos.BUSY_SECONDS * 2
    assert client.get("api/v1/d") is None and client.busy_for() == raceos.BUSY_SECONDS * 4
    clock[0] += raceos.BUSY_SECONDS * 4
    assert client.get("api/v1/e") == [1] and client.busy_for() == 0
    assert client.get("api/v1/f") is None and client.busy_for() == raceos.BUSY_SECONDS  # read done: wait reset
    assert raceos.retry_after("Thu, 01 Jan 1970 00:10:00 GMT", 300.0) == 300.0  # HTTP date
    assert raceos.retry_after("99999", 0.0) == raceos.RETRY_MAX_SECONDS and raceos.retry_after("x", 0.0) is None


# B-007: Retry-After header of a 429 given by http_request (answer still equal to (status, body))
def test_b007_http_request_gives_retry_after(monkeypatch):
    import urllib.error
    import urllib.request
    from email.message import Message

    def busy(self, request, timeout=None):
        headers = Message()
        headers["Retry-After"] = "30"
        raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", headers, io.BytesIO(b"busy"))

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", busy)
    reply = raceos.http_request("GET", f"{raceos.RACEOS_URL}/api/v1/x", None, {}, 1)
    assert reply == (429, b"busy") and reply.retry_after == "30"


# B-007: schedule read stopped at a 429 (remaining routes not asked), not read again while RaceControl waits
def test_b007_schedule_read_stops_at_429(fresh_info, monkeypatch):  # noqa: F811
    from neopedal import rank_info

    clock = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    http = Http429((200, ""), (429, "1800"))
    client = raceos.RaceOSClient(lambda: "ticket", http=http, clock=lambda: clock[0], wall_clock=lambda: NOW)
    monkeypatch.setattr(rank_info, "online_client", lambda: client)
    info.read(force=True)
    assert len(http.calls) == 3  # sign in, first route, second route (429): others never asked
    clock[0] = 1000.0 + 1799
    assert not info.due()  # RaceControl asked 30 min
    info.read(force=True)
    assert len(http.calls) == 3
    clock[0] = 1000.0 + 1800
    assert info.due()


# Upcoming Races page (B-008..B-022)


def wait(condition, loops: int = 200) -> bool:
    for _ in range(loops):
        pump(0.02)
        if condition():
            return True
    return False


def set_schedule(monkeypatch, found: rs.Schedule):
    monkeypatch.setattr(info, "_state", info.State(found, info.READ, time.monotonic(), 1))


def popup_child(viewer, name: str):
    return viewer.view.rootObject().findChild(QObject, name)


# B-017: the menu of a timeline block acts on the start clicked (reminder, field, calendar), not on the first one
def test_b017_timeline_block_menu_acts_on_clicked_start(qml_warnings, page, monkeypatch, tmp_path):  # noqa: F811
    from PySide6.QtWidgets import QFileDialog

    from neopedal.ui.quick import schedule_reminders
    from neopedal.ui.quick.schedule_view import start_text

    backend = page.backend  # noqa: F811
    backend.setOpenOnly(False)
    backend.setTab(0)
    backend.setView(2)
    pump(0.2)
    race = backend.daily[0]["races"][0]
    key, first = race["key"], race["startKey"]
    later = NOW + 3300  # third start of "LMP2 Fixed", no event id known
    lane = next(lane for lane in backend.timeline["lanes"] if lane["key"] == key)
    assert later in [item["start"] for item in lane["items"]]
    root = page.view.rootObject()
    blocks = [item for item in items_of(root) if item.objectName() == "timelineBlock" and item.isVisible()]
    block = next(item for item in blocks if item.property("modelData")["start"] == later)
    click(page.view, block)
    pump(0.1)
    assert root.property("menuKey") == key and root.property("menuStart") == later
    entries = backend.raceActions(key, later)
    remind = next(entry for entry in entries if entry["id"] == "remind:10")
    assert remind["text"] == "10 min" and remind["menu"] == f"Remind Me Before {start_text(later, NOW)}"
    assert not remind["checked"]
    assert not next(entry for entry in entries if entry["id"] == "field")["enabled"]  # no event id for that start
    backend.runRaceAction(key, "remind:10", "", later)
    assert schedule_reminders.reminders().minutes_of(f"{key}@{int(later)}") == 10
    assert schedule_reminders.reminders().minutes_of(first) == 0  # first start untouched
    assert next(entry for entry in backend.raceActions(key, later) if entry["id"] == "remind:10")["checked"]
    assert not next(entry for entry in backend.raceActions(key) if entry["id"] == "remind:10")["checked"]
    path = tmp_path / "race.ics"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(path), ""))
    backend.runRaceAction(key, "export", "", later)
    assert "DTSTART:" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(later)) in path.read_text(encoding="utf-8")
    # The card keeps acting on its first start, which has an event id: field read under the race key
    assert next(entry for entry in backend.raceActions(key) if entry["id"] == "field")["enabled"]
    QCoreApplication.processEvents()
    assert not qml_warnings, qml_warnings


# B-011: a saved class filter no race uses stays shown as a checked chip (removable), Clear Filters shown
def test_b011_saved_class_absent_kept_as_checked_chip(page, monkeypatch):  # noqa: F811
    backend = page.backend  # noqa: F811
    backend.setOpenOnly(False)
    backend.toggleClass("LMP3")  # class of last week, kept in race_schedule.json, no race this week
    pump(0.1)
    chip = next((choice for choice in backend.classChoices if choice["name"] == "LMP3"), None)
    assert chip is not None and chip["selected"] and chip["missing"]
    assert page.view.rootObject().property("filtered") is True
    backend.toggleClass("LMP3")  # removed with one click
    assert backend.counts[:2] == [2, 1] and all(choice["name"] != "LMP3" for choice in backend.classChoices)


# B-010: a cached page shown while another page is read: the read in flight is dropped; buttons off while loading
def test_b010_cached_page_cancels_page_in_flight(page, monkeypatch):  # noqa: F811
    backend = page.backend  # noqa: F811
    backend.setOpenOnly(False)
    gate = threading.Event()
    gate.set()

    def leaderboard(board, cls="", number=1):
        gate.wait(5)
        return rs.parse_leaderboard(board_answer({"page": number, "limit": 100}))

    monkeypatch.setattr(info, "read_leaderboard", leaderboard)
    monkeypatch.setattr(info, "read_place", lambda board, cls="": (150, 250))
    monkeypatch.setattr(info, "player_id", lambda: "me-id")
    backend.openBoard(backend.daily[0]["races"][0]["key"])
    assert wait(lambda: not backend.board.get("loading"))
    backend.boardMine()
    assert wait(lambda: not backend.board.get("loading") and backend.board.get("page") == 2)
    gate.clear()  # next page read is slow
    backend.boardPage(3)
    assert backend.board["loading"]
    pump(0.1)
    mine = popup_child(page, "boardMine")
    assert mine is not None and not mine.property("enabled")  # Show My Place off while loading
    backend.boardMine()  # page 2 cached: shown at once
    assert backend.board["page"] == 2
    gate.set()
    pump(0.3)
    wait(lambda: False, 20)
    assert backend.board["page"] == 2, f"page {backend.board['page']} shown after Show My Place"
    backend.closeBoard()


# B-015: field of a start passed dropped; championship sessions of the previous round dropped; "in N min" moves on
def test_b015_details_follow_start_and_round(page, monkeypatch):  # noqa: F811
    backend = page.backend  # noqa: F811
    backend.setOpenOnly(False)
    monkeypatch.setattr(info, "read_field", lambda kind, event_id: rs.FieldLevel(
        2, (("LMP2", 2),), (("Silver", 2),), (), True))
    monkeypatch.setattr(info, "read_championship", lambda key, number: rs.ChampionshipDetail(
        (rs.Start(NOW + 600, 4),), 1, 3, ()))
    race = backend.daily[0]["races"][0]
    key = race["key"]
    backend.runRaceAction(key, "field", "")
    assert wait(lambda: f"field:{key}" in backend.details)
    champ = backend.championships[0]["key"]
    backend.readChampionship(champ)
    assert wait(lambda: f"championship:{champ}" in backend.details)
    assert backend.details[f"championship:{champ}"]["sessions"][0]["until"] == "in 10 min"
    monkeypatch.setattr(time, "time", lambda: NOW + 60)
    backend.publish_all()
    assert backend.details[f"championship:{champ}"]["sessions"][0]["until"] == "in 9 min"  # worded again
    assert f"field:{key}" in backend.details  # same start
    monkeypatch.setattr(time, "time", lambda: NOW + 700)  # that start passed, next one shown
    backend.publish_all()
    assert backend.daily[0]["races"][0]["startTime"] == NOW + 3300
    assert f"field:{key}" not in backend.details
    found = schedule(NOW)
    item = found.championships[0]
    current = item.current_round(NOW)
    rounds = (*(entry._replace(current=False) for entry in item.rounds), current._replace(number=3))
    set_schedule(monkeypatch, found._replace(championships=(item._replace(rounds=rounds),)))
    backend.publish_all()
    assert backend.championships[0]["roundNumber"] == 3
    assert f"championship:{champ}" not in backend.details  # sessions of round 2 dropped: read again offered


# B-008: timeline hour marks on whole hours of the local clock (time zone UTC+5:30 simulated)
def test_b008_timeline_marks_on_local_whole_hours(monkeypatch):
    from neopedal.ui.quick import schedule_view as sv

    offset = 5.5 * 3600
    clock = types.SimpleNamespace(
        time=time.time, gmtime=time.gmtime, strftime=time.strftime,
        localtime=lambda moment=None: time.gmtime((time.time() if moment is None else moment) + offset),
        mktime=lambda parts: calendar.timegm((*tuple(parts)[:6], 0, 0, 0)) - offset)
    monkeypatch.setattr(sv, "time", clock)
    monkeypatch.setattr(sv, "clock_minutes", lambda moment: time.strftime("%H:%M", time.gmtime(moment + offset)))
    now = calendar.timegm((2026, 11, 2, 0, 10, 0, 0, 0, 0))
    marks = sv.timeline([], rs.EMPTY, now)["marks"]
    assert marks and all(mark["text"].endswith(":00") for mark in marks), marks
    assert all(0 <= mark["at"] <= 1 for mark in marks)


# B-009: the profile closed while read is not opened again by the late answer (read cancelled)
def test_b009_profile_not_reopened_after_close(page, monkeypatch):  # noqa: F811
    backend = page.backend  # noqa: F811
    gate = threading.Event()

    def slow_profile(name):
        gate.wait(5)
        return rs.Profile(name, "DE", ("Bronze", 3), ("Gold", 1), "")

    monkeypatch.setattr(info, "read_profile", slow_profile)
    backend.showProfile("Driver 7")
    assert backend.profile["open"] and backend.profile["loading"]
    backend.closeProfile()
    assert not backend.jobs.is_busy("profile")
    gate.set()
    wait(lambda: backend.profile.get("open"), 50)
    assert backend.profile == {"open": False}
    backend.profile_read("Driver 7", rs.Profile("Driver 7", "DE", ("Bronze", 3), ("Gold", 1), ""))  # late answer
    assert backend.profile == {"open": False}


# B-012: Owned Cars & Tracks hides championships & co-op events needing a track you don't own
def test_b012_owned_only_filters_championships_and_coop(page, monkeypatch):  # noqa: F811
    found = rs.parse_schedule(answers(), rs.parse_car_catalog(CARS), rs.parse_track_catalog(
        [*TRACKS, {"sceneDesc": "ROADATLANTA", "shortName": "Road Atlanta 1.0", "owned": False}]), NOW)
    set_schedule(monkeypatch, found)
    backend = page.backend  # noqa: F811
    backend.setOpenOnly(False)
    assert backend.championships[0]["owned"] == "Track not owned" and backend.coop[0]["owned"] == "Track not owned"
    assert backend.counts[2:4] == [1, 1]
    backend.setOwnedOnly(True)
    assert backend.counts[2:4] == [0, 0]


# B-013: on the Weekly tab, the view segment shows Cards when the timeline was chosen on the Daily tab
def test_b013_view_segment_weekly_after_timeline(page, monkeypatch):  # noqa: F811
    backend = page.backend  # noqa: F811
    backend.setOpenOnly(False)
    backend.setTab(0)
    backend.setView(2)
    backend.setTab(1)
    pump(0.2)
    root = page.view.rootObject()
    assert item_named(root, "viewMode").property("currentIndex") == 0
    assert any(item.objectName() == "raceCard" and item.isVisible() for item in items_of(root))
    backend.setView(1)
    pump(0.1)
    assert item_named(root, "viewMode").property("currentIndex") == 1


# B-014: Clear Filters empties the search field too
def test_b014_clear_filters_empties_search_field(page, monkeypatch):  # noqa: F811
    backend = page.backend  # noqa: F811
    backend.setOpenOnly(False)
    field = item_named(page.view.rootObject(), "raceSearch")
    field.setProperty("text", "hyper")
    backend.setSearch("hyper")
    assert backend.counts[0] == 1
    backend.clearFilters()
    pump(0.1)
    assert backend.search == "" and backend.counts[0] == 2
    assert field.property("text") == ""


# B-016: "+n more" starts expanded stay expanded at the next list update
def test_b016_expanded_starts_kept_on_next_tick(page, monkeypatch):  # noqa: F811
    backend = page.backend  # noqa: F811
    backend.setOpenOnly(False)
    base = schedule(NOW)
    events = [event._replace(starts=tuple(rs.Start(NOW + 600 + 900 * index) for index in range(14)))
              if event.title == "LMP2 Fixed" else event for event in base.events]
    set_schedule(monkeypatch, base._replace(events=tuple(events)))
    backend.setView(0)
    backend.publish_all()
    pump(0.2)
    root = page.view.rootObject()

    def more_button():
        return next((item for item in items_of(root) if item.objectName() == "moreStarts" and item.isVisible()), None)

    button = more_button()
    assert button is not None and button.property("text").startswith("+")
    click(page.view, button)
    pump(0.1)
    assert more_button().property("text") == "Fewer"
    monkeypatch.setattr(time, "time", lambda: NOW + 60)  # next tick: "in 10 min" -> "in 9 min"
    backend.publish_all()
    pump(0.2)
    assert more_button().property("text") == "Fewer", "expanded starts collapsed by the list update"


# B-018: the gap to the first of a class never uses your lap of another class
def test_b018_my_lap_reset_on_class_change(page, monkeypatch):  # noqa: F811
    backend = page.backend  # noqa: F811
    backend.setOpenOnly(False)

    def leaderboard(board, cls="", number=1):
        answer = board_answer({"page": number, "limit": 100})
        if cls == "" and number == 1:  # all classes: your LMP2 lap on page 1
            answer["entries"][4] = {**answer["entries"][4], "id": "me-id"}
        if cls:  # GT3: you are 150th (not on page 1), first 10 s slower than the LMP2 first
            for entry in answer["entries"]:
                entry["score"] += 10000
        return rs.parse_leaderboard(answer)

    monkeypatch.setattr(info, "read_leaderboard", leaderboard)
    monkeypatch.setattr(info, "read_place", lambda board, cls="": (5, 250) if not cls else (150, 250))
    monkeypatch.setattr(info, "player_id", lambda: "me-id")
    backend.openBoard(backend.daily[0]["races"][0]["key"])
    assert wait(lambda: not backend.board.get("loading"))
    assert backend.board["mySeconds"] > 0 and "s to the first" in backend.board["standing"]
    backend.boardClass("LMP2_ELMS")
    assert wait(lambda: not backend.board.get("loading") and backend.board.get("vehicleClass") == "LMP2_ELMS")
    assert "s to the first" not in backend.board["standing"], backend.board["standing"]
    backend.closeBoard()


# B-019: a tab emptied by Open to Me says so and offers to show everything (not "read from RaceControl")
def test_b019_tab_emptied_by_open_to_me(qml_warnings, page, monkeypatch):  # noqa: F811
    backend = page.backend  # noqa: F811
    backend.setOpenOnly(True)
    backend.setTab(2)  # championship needs SR Gold 1, yours Silver 2
    pump(0.2)
    assert backend.counts[2] == 0 and backend.openHidden[2] == 1
    root = page.view.rootObject()
    states = [item for item in items_of(root) if "TpStateView" in item.metaObject().className() and item.isVisible()]
    shown = [item for item in states if item.property("title") == "No championship"]
    assert shown, [item.property("title") for item in states]
    assert "Open to Me" in shown[0].property("text") and shown[0].property("actionText") == "Show All"
    QMetaObject.invokeMethod(shown[0], "action")
    pump(0.1)
    assert not backend.openOnly and backend.counts[2] == 1
    QCoreApplication.processEvents()
    assert not qml_warnings, qml_warnings


# B-020: two races of the same title in a tier get their own key (suffix "#<scene>"), single races keep theirs
def test_b020_same_title_races_keep_own_keys(ui_env):
    from neopedal.ui.quick import schedule_view as view

    base = schedule(NOW)
    lmp2 = next(event for event in base.events if event.title == "LMP2 Fixed")
    twin = lmp2._replace(scene="MonzaWEC", starts=(rs.Start(NOW + 1500),))
    found = base._replace(events=(*base.events, twin))
    rows = [row for event in found.events if (row := view.event_row(event, found, ("Silver", 3), NOW, lambda _: ""))]
    keys = [row["key"] for row in rows]
    assert len(set(keys)) == len(keys), keys
    assert "daily/advanced/Hyper Hour" in keys  # races not in duplicate keep their key (reminders kept)
    assert {"daily/beginner/LMP2 Fixed#PortimaoWEC", "daily/beginner/LMP2 Fixed#MonzaWEC"} <= set(keys)
    line = view.timeline([("beginner", [row for row in rows if row["tier"] == "beginner"])], found, NOW)
    starts = {lane["key"]: [item["start"] for item in lane["items"]] for lane in line["lanes"]}
    assert starts["daily/beginner/LMP2 Fixed#MonzaWEC"] == [NOW + 1500]
    assert NOW + 1500 not in starts["daily/beginner/LMP2 Fixed#PortimaoWEC"]


# B-021: a running championship session has the running tint (as daily races)
def test_b021_running_championship_session(ui_env):
    from neopedal.ui.quick import schedule_view as view

    found = schedule(NOW)
    row = view.championship_row(found.championships[0], found, ("Silver", 3), NOW + 1000, lambda _: "")
    assert row["until"] == "Running" and row["running"] is True
    row = view.championship_row(found.championships[0], found, ("Silver", 3), NOW, lambda _: "")
    assert row["running"] is False


# B-022: "Find a driver" asks on Enter only, never when the field loses focus
def test_b022_find_driver_on_enter_only(page, monkeypatch):  # noqa: F811
    backend = page.backend  # noqa: F811
    backend.setOpenOnly(False)
    monkeypatch.setattr(info, "read_leaderboard",
                        lambda board, cls="", number=1: rs.parse_leaderboard(board_answer({"page": number, "limit": 100})))
    monkeypatch.setattr(info, "read_place", lambda board, cls="": (150, 250))
    monkeypatch.setattr(info, "player_id", lambda: "me-id")
    asked = []
    monkeypatch.setattr(info, "find_driver", lambda board, cls, name: asked.append(name) or 0)
    backend.openBoard(backend.daily[0]["races"][0]["key"])
    assert wait(lambda: not backend.board.get("loading"))
    pump(0.2)
    field = popup_child(page, "boardFind")
    assert field is not None
    field.setProperty("text", "Driver 230")
    QMetaObject.invokeMethod(field, "textEdited")  # typed
    QMetaObject.invokeMethod(field, "flushSearch")  # what losing the focus does
    pump(0.2)
    assert asked == [] and backend.board.get("found", "") == ""
    QMetaObject.invokeMethod(field, "accepted")  # Enter
    assert wait(lambda: asked == ["Driver 230"])
    backend.closeBoard()


# Online list of Results & Replays (B-023..B-032)


PLAYER = "Alex Tester"


def race(event_id: str, date: float, laps: bool = False, scene: str = "PortimaoWEC") -> dict:
    """Online race of a results answer (simulated): you 1st, another driver 2nd"""
    rows = [{"name": "Other Driver", "position": "2", "carClass": "LMP3"},
            {"name": PLAYER, "position": "1", "carClass": "LMP3"}]
    if laps:
        for row in rows:
            row["laps"] = [{"lapTime": "100", "p": row["position"]}, {"lapTime": "100", "p": row["position"]}]
    return {"eventId": event_id, "splitNo": 1, "date": iso(date), "eventType": "daily", "tier": "beginner",
            "title": f"Race {event_id}", "trackScene": scene,
            "drivers": [{"name": PLAYER, "driverRankAdjustment": 1, "safetyRankAdjustment": 1}],
            "race": {"races": [{"results": rows}]}}


class FakeJobs:
    """Jobs kept until delivered by hand; keyed jobs supersede like BackgroundJobs (older result dropped)"""

    def __init__(self):
        self.jobs: list[dict] = []

    def run(self, name, work, done=None, failed=None, key=None, cancellable=False):
        for job in self.jobs:
            if key is not None and job["key"] == key and not job["over"]:
                job["dropped"] = True
        self.jobs.append({"name": name, "work": work, "done": done, "failed": failed, "key": key, "over": False,
                          "dropped": False})
        return len(self.jobs)

    def cancel(self, key):
        found = False
        for job in self.jobs:
            if job["key"] == key and not job["over"] and not job["dropped"]:
                job["dropped"] = found = True
        return found

    def is_busy(self, key):
        return any(job["key"] == key and not job["over"] and not job["dropped"] for job in self.jobs)

    def cancel_all(self):
        for job in self.jobs:
            job["dropped"] = True

    def named(self, name: str) -> list[int]:
        return [index for index, job in enumerate(self.jobs) if job["name"] == name]

    def deliver(self, index: int):
        job = self.jobs[index]
        job["over"] = True
        try:
            value = job["work"]()
        except Exception as error:  # handed over like BackgroundJobs
            if not job["dropped"] and job["failed"]:
                job["failed"](error)
            return
        if not job["dropped"] and job["done"]:
            job["done"](value)

    def deliver_all(self, name: str):
        """Every job of name not delivered yet, in the order asked"""
        for index in self.named(name):
            if not self.jobs[index]["over"]:
                self.deliver(index)


def scripted(online, monkeypatch, pages: dict, laps: dict | None = None):  # noqa: F811
    """Backend with jobs delivered by hand: pages {(kind, page): answers}, laps {event id: answer}"""
    monkeypatch.setattr(info, "player_name", lambda: PLAYER)
    monkeypatch.setattr(info, "read_results", lambda kind, page=1: [  # noqa: F811
        rs.parse_result(item) for item in pages.get((kind, page), [])])
    monkeypatch.setattr(info, "read_result", lambda event_id, split: rs.parse_result((laps or {}).get(event_id)))
    online.jobs = FakeJobs()
    return online.jobs


def daily_pages(count: int = 2) -> dict:
    return {("daily", number): [race(f"p{number}-{index}", NOW - number * 86400 - index * 3600)
                                for index in range(info.results_take("daily"))] for number in range(1, count + 1)}


def titles(online) -> list[str]:  # noqa: F811
    return [row["title"] for row in online.rows]


def test_b023_read_again_during_more_results_keeps_newest(online, monkeypatch):  # noqa: F811
    # B-023: Read Again while More Results reads page 2: only page 2 was kept (newest races lost)
    jobs = scripted(online, monkeypatch, daily_pages())
    online.list_shown(True)
    jobs.deliver(0)  # page 1
    online.more()  # page 2 asked
    online.readAgain()
    jobs.deliver_all("online results")
    assert titles(online) == [f"Race p1-{index}" for index in range(info.results_take("daily"))]
    assert online._page["daily"] == 1 and online.state["more"] and not online.state["loading"]


def test_b024_kind_changed_while_reading(online, monkeypatch):  # noqa: F811
    # B-024: kind changed while a page of another kind is read: new kind never read, other kind's race picked
    pages = daily_pages(1)
    pages[("championship", 1)] = [race("c-0", NOW - 7200)]
    jobs = scripted(online, monkeypatch, pages)
    online.list_shown(True)  # daily page 1 asked
    online.setKind(2)  # championships
    jobs.deliver(0)  # daily page 1 answers
    assert online.state["selectedKey"] == ""  # no daily race picked on the championship list
    jobs.deliver_all("online results")
    assert titles(online) == ["Race c-0"] and online.state["selectedKey"] == "result/c-0/1"
    assert online.selected["title"] == "Race c-0"
    online.setKind(0)
    assert len(online.rows) == info.results_take("daily")  # daily page kept


def test_b025_laps_read_after_picking_another_race_or_failing(online, monkeypatch):  # noqa: F811
    # B-025: laps of race A never read when B was picked before A's laps answered, or when the read failed
    pages = daily_pages(1)
    answers = {item["eventId"]: race(item["eventId"], NOW, laps=True) for item in pages[("daily", 1)]}
    jobs = scripted(online, monkeypatch, pages, answers)
    online.list_shown(True)
    jobs.deliver(0)  # page 1, first race picked: its laps asked
    online.select("result/p1-1/1")  # laps of p1-1 asked: p1-0 answer dropped
    jobs.deliver_all("race laps")
    online.select("result/p1-0/1")
    jobs.deliver_all("race laps")
    assert online.chart["laps"] == 2
    monkeypatch.setattr(info, "read_result", lambda event_id, split: 1 / 0)  # read fails once
    online.select("result/p1-2/1")
    jobs.deliver_all("race laps")
    monkeypatch.setattr(info, "read_result", lambda event_id, split: rs.parse_result(answers[event_id]))
    online.select("result/p1-0/1")
    online.select("result/p1-2/1")
    jobs.deliver_all("race laps")
    assert online.chart["laps"] == 2


def test_b026_laps_read_again_after_read_again(online, monkeypatch):  # noqa: F811
    # B-026: after Read Again the races read again had no laps and were never asked again
    pages = daily_pages(1)
    answers = {item["eventId"]: race(item["eventId"], NOW, laps=True) for item in pages[("daily", 1)]}
    jobs = scripted(online, monkeypatch, pages, answers)
    online.list_shown(True)
    jobs.deliver(0)
    jobs.deliver_all("race laps")
    assert online.chart["laps"] == 2
    online.readAgain()
    jobs.deliver_all("online results")
    jobs.deliver_all("race laps")
    assert online.chart["laps"] == 2


def test_b027_end_of_list_from_races_answered(online, fresh_info, monkeypatch):  # noqa: F811
    # B-027: a full page with one unreadable race ended the list (More Results gone)
    answer = [race(f"x{index}", NOW - index * 3600) for index in range(info.results_take("daily"))]
    answer[2] = {"eventId": "x2", "race": {"races": []}}  # race without race session
    fresh_info.data["api/v1/results"] = answer
    monkeypatch.setattr(info, "player_name", lambda: PLAYER)
    found = info.read_results("daily", 1)
    assert len(found) == len(answer) - 1  # read_championship_results contract kept: races read only
    online.jobs = FakeJobs()
    online.list_shown(True)
    online.jobs.deliver(0)
    assert len(online.rows) == len(answer) - 1 and online.state["more"]


def test_b028_local_session_same_track_from_event_start(online, monkeypatch):  # noqa: F811
    # B-028: Open Local Session took the closest race session within 3 h on any track, even one started before
    from neopedal.process.results_index import SessionInfo
    from neopedal.setting import cfg
    from neopedal.ui.quick.online_results import local_session
    from neopedal.userfile.game_images import images

    catalog = {"track_names": {"testringwec": "Test Ring GP", "test ring endurance": "Test Ring GP",
                               "test ring gp": "Test Ring GP", "other park": "Other Park"}}
    folder = cfg.path.game_image
    with open(f"{folder}catalog.json", "w", encoding="utf-8") as file:
        json.dump(catalog, file)
    monkeypatch.setattr(images, "_loaded_folder", "")  # catalog of this test read
    result = rs.parse_result(race("r", NOW, scene="TestRingWEC"))

    def session(path: str, start: float, course: str, track: str = "", kind: str = "Race") -> SessionInfo:
        return SessionInfo(path, start, kind, track or course, "Test Ring", course, "", "Multiplayer", 10, 20, 1,
                           "LMP3", None, ())

    other_track = session("other.xml", NOW + 1800, "Other Park")
    before = session("before.xml", NOW - 1200, "Test Ring GP")
    assert local_session(result, [other_track], "Test Ring GP") == ""
    assert local_session(result, [before], "Test Ring GP") == ""
    assert local_session(result, [session("late.xml", NOW + 4 * 3600, "Test Ring GP")], "Test Ring GP") == ""
    good = session("race.xml", NOW + 900, "", "Test Ring Endurance")  # event name only: its layout
    assert local_session(result, [other_track, before, good, session("q.xml", NOW + 600, "Test Ring GP",
                                                                      kind="Qualify")], "Test Ring GP") == "race.xml"
    assert local_session(result, [session("early.xml", NOW - 300, "Test Ring GP")], "Test Ring GP") == "early.xml"
    monkeypatch.setattr(info, "player_name", lambda: PLAYER)
    monkeypatch.setattr(info, "read_results", lambda kind, page=1: [result] if page == 1 else [])  # noqa: F811
    online.jobs = FakeJobs()
    online.list_shown(True)
    online.jobs.deliver(0)
    wanted = []
    online.sessionWanted.connect(wanted.append)
    online.sessions = lambda: [other_track, before]
    online.openLocal()
    assert not wanted and online.state["note"] == "No results file of this race on this computer"
    online.sessions = lambda: [other_track, before, good]
    online.openLocal()
    assert wanted == ["race.xml"]


def test_b029_team_race_own_rank_changes(online, monkeypatch):  # noqa: F811
    # B-029: team races (rows named by the car) lost your Driver & Safety Rank changes & ranks
    from neopedal.ui.quick.online_results import rank_lines, summary_of

    team = race("t", NOW)
    team["drivers"] = [
        {"name": PLAYER, "driverRankAdjustment": 2, "safetyRankAdjustment": 1,
         "drReasons": [{"impact": 2, "positive": True, "reason": "Race you finished 1st"}],
         "driverRank": {"rank": "Silver", "tier": 2}, "safetyRank": {"rank": "Gold", "tier": 1}},
        {"name": "Pat Teammate", "driverRankAdjustment": -1, "safetyRankAdjustment": -3,
         "driverRank": {"rank": "Bronze", "tier": 3}, "safetyRank": {"rank": "Bronze", "tier": 1}}]
    team["teams"] = [{"name": "Team Falcon", "teamMembers": [{"name": "Pat Teammate"}, {"name": PLAYER}]},
                     {"name": "Team Owl", "teamMembers": [{"name": "Other Driver"}]}]
    rows = team["race"]["races"][0]["results"]
    rows[1]["name"], rows[1]["teamName"] = "Falcon #26", "Team Falcon"
    rows[0]["name"], rows[0]["teamName"] = "Owl #7", "Team Owl"
    parsed = rs.parse_result(team)
    assert all(row.dr_change is None for row in parsed.rows)  # one member's change never copied to a car row
    summary = summary_of([parsed], PLAYER)
    assert {figure["label"]: figure["value"] for figure in summary["figures"]}["DR"] == "+2"
    assert {figure["label"]: figure["value"] for figure in summary["figures"]}["Clean Races"] == "1/1"
    assert rank_lines([parsed, parsed], PLAYER)["drText"] == "Silver 2"
    monkeypatch.setattr(info, "player_name", lambda: PLAYER)
    shown = online.view_of(parsed)
    assert (shown["mine"]["dr"], shown["mine"]["sr"]) == ("+2", "+1")
    assert shown["mine"]["reasons"] == "Race you finished 1st (+2)"
    assert [row["dr"] for row in shown["rows"] if not row["me"]] == [""]  # the other car: nothing given


def test_b030_not_read_message_tells_why(online, fresh_info, monkeypatch):  # noqa: F811
    # B-030: any unread list said "start Le Mans Ultimate" (option off, no RaceControl account too)
    from neopedal import rank_info
    from neopedal.ui.quick.schedule_backend import status_note

    monkeypatch.setattr(info, "player_name", lambda: PLAYER)
    monkeypatch.setattr(info, "_game_running", lambda: True)
    online.jobs = FakeJobs()
    monkeypatch.setattr(rank_info, "online_enabled", lambda: False)
    monkeypatch.setattr(info, "_local_folders", lambda: ())  # option off: races of the results files, none here
    online.list_shown(True)
    online.jobs.deliver(0)
    assert online.state["error"] == ""  # read from the files: nothing to tell
    monkeypatch.setattr(rank_info, "online_enabled", lambda: True)
    fresh_info.no_account = True
    online.readAgain()
    online.jobs.deliver_all("online results")
    assert online.state["error"] == status_note(info.NO_ACCOUNT, rs.EMPTY)[1]
    fresh_info.no_account = False
    monkeypatch.setattr(info, "_game_running", lambda: False)
    online.readAgain()
    online.jobs.deliver_all("online results")
    assert online.state["error"] == status_note(info.NO_GAME, rs.EMPTY)[1]


def test_b031_no_laps_read_once_the_list_is_left(ui_env, fresh_info, monkeypatch):  # noqa: F811
    # B-031: a page answered after leaving the online list still asked the laps of the race picked
    from neopedal.ui.race_results_viewer import RaceResultsViewer

    pages = daily_pages(1)
    monkeypatch.setattr(info, "_state", info.State(rs.EMPTY, info.READ, 0.0, 1))
    viewer = RaceResultsViewer(None)
    jobs = scripted(viewer.online, monkeypatch, pages, {})
    viewer.resize(1300, 850)
    viewer.show()
    pump(0.2)
    try:
        viewer.show_online()
        assert jobs.named("online results")
        viewer.hide()
        pump(0.1)
        jobs.deliver_all("online results")
        assert len(viewer.online.rows) == info.results_take("daily") and not jobs.named("race laps")
        viewer.show()
        pump(0.1)
        assert jobs.named("race laps")  # list shown again: laps of the race picked asked
    finally:
        viewer.close()
        pump(0.1)


def test_b032_lap_without_position_not_drawn(qml_warnings, ui_env, fresh_info, monkeypatch):  # noqa: F811
    # B-032: a lap without position (0) was drawn above P1 on the positions chart
    from neopedal.ui.race_results_viewer import RaceResultsViewer

    item = race("g", NOW, laps=True)
    item["race"]["races"][0]["results"][1]["laps"][1].pop("p")
    monkeypatch.setattr(info, "_state", info.State(rs.EMPTY, info.READ, 0.0, 1))
    viewer = RaceResultsViewer(None)
    jobs = scripted(viewer.online, monkeypatch, {("daily", 1): [item]})
    viewer.resize(1300, 850)
    viewer.show()
    pump(0.2)
    try:
        viewer.show_online()
        jobs.deliver_all("online results")
        pump(0.1)
        canvas = item_named(viewer.view.rootObject(), "onlineLapChart")
        assert canvas is not None
        segments = QMetaObject.invokeMethod(canvas, "segments", Q_RETURN_ARG("QVariant"),
                                            Q_ARG("QVariant", [1, 0, 2, 2, -1, 3])).toVariant()
        assert segments == [[[0, 1]], [[2, 2], [3, 2]], [[5, 3]]]
        assert item_named(viewer.view.rootObject(), "onlineLaps").isVisible()  # chart of the race drawn
        assert not qml_warnings, qml_warnings
    finally:
        viewer.close()
        pump(0.1)


# Driver Stats card (B-033): removed later the same day, same races as this page & the Home card
def test_b033_driver_stats_card_removed(backend):  # noqa: F811
    assert backend.metaObject().indexOfProperty("upcoming") < 0 and not hasattr(stats_overview, "UPCOMING_TICK")
    assert not (Path(stats_overview.__file__).parents[1] / "qml" / "analysis" / "StatsUpcomingCard.qml").exists()


# New bugs found while fixing (B-034..B-038)


def test_b034_championship_results_read_on_after_unreadable_race(fresh_info):  # noqa: F811
    # B-034: a full page with one unreadable race stopped the championship results (races parsed < results_take)
    answer = [race(f"c{index}", NOW - index * 3600) for index in range(info.results_take("championship"))]
    answer[1] = {"eventId": "c1", "race": {"races": []}}  # race without race session
    fresh_info.data["api/v1/results"] = answer  # every page full
    found = info.read_championship_results("Race")
    asked = [path for path in fresh_info.paths if path.startswith("api/v1/results?")]
    assert len(asked) == info.CHAMPIONSHIP_PAGES, asked
    assert len(found) == info.CHAMPIONSHIP_PAGES * (len(answer) - 1)


def test_b035_failed_page_of_other_kind_not_told_on_kind_shown(online, monkeypatch):  # noqa: F811
    # B-035: kind changed while a page of another kind is read, that page fails: its error was told on the kind
    # shown, which was never read until Read Again
    pages = {("championship", 1): [race("c-0", NOW - 7200)]}
    jobs = scripted(online, monkeypatch, pages)

    def read(kind, number=1):
        if kind == "daily":
            raise OSError("no answer")
        return [rs.parse_result(item) for item in pages.get((kind, number), [])]

    monkeypatch.setattr(info, "read_results", read)
    online.list_shown(True)  # daily page 1 asked
    online.setKind(2)  # championships
    jobs.deliver(0)  # daily page fails
    assert online.state["error"] == ""
    jobs.deliver_all("online results")
    assert titles(online) == ["Race c-0"] and online.state["error"] == ""
    online.setKind(0)  # daily read again, fails: told on its list
    jobs.deliver_all("online results")
    assert online.state["error"] and not online.state["loading"]


# B-036: with the schedule read, details of a daily race without configuration.starts matched by raceStartsAt
def test_b036_daily_details_matched_by_race_start_without_config_start():
    start = DAY + 3600
    empty = daily_item("beginner", "LMP3 Fixed", start)
    empty["configuration"].pop("starts")
    empty["raceStartsAt"] = iso(start)
    dated = daily_item("beginner", "LMP3 Fixed", start + 2700)  # real answer: configuration.starts = practice start
    dated["raceStartsAt"] = iso(start + 2700 + 720)  # race start later: never used when configuration.starts is given
    found = rs.parse_daily(daily_answer("beginner", "LMP3 Fixed", start, 2700, 2), {"beginner": [empty, dated]})
    assert found[0].starts == (rs.Start(start, 3, start - 1800, False, f"id-{int(start)}"),
                               rs.Start(start + 2700, 3, start + 900, False, f"id-{int(start + 2700)}"))


# B-037: a partial read (route failed: 500, no answer, read cut by a 429) replaced the whole schedule: races of the
# failed route gone. Last answer of the route kept KEEP_ANSWER_SECONDS from its own read (disk copy after a restart
# too), the route still told missing (reminders never judged on it)
def test_b037_partial_read_keeps_recent_answer_of_failed_route(fresh_info, monkeypatch):  # noqa: F811
    monkeypatch.setattr(info, "FORCE_SECONDS", 0.0)  # refreshes asked one after another all read
    clock = [NOW]
    monkeypatch.setattr(time, "time", lambda: clock[0])

    def read_at(moment: float, failed: str) -> rs.Schedule:
        clock[0] = moment
        fresh_info.data = {**answers(), failed: None} if failed else answers()
        state = info.read(force=True)
        assert state.status == info.READ
        return state.schedule

    def weekly(found: rs.Schedule) -> bool:
        return any(event.title == "WEC Weekly" for event in found.events)

    assert weekly(read_at(NOW, ""))
    found = read_at(NOW + 600, "weekly")  # weekly route fails once
    assert weekly(found) and "weekly" in found.missing
    found = read_at(NOW + 1200, "weekly")
    assert weekly(found) and "weekly" in found.missing
    assert not weekly(read_at(NOW + info.KEEP_ANSWER_SECONDS, "weekly"))  # answer read at NOW too old
    assert weekly(read_at(NOW + 2000, ""))
    monkeypatch.setattr(info, "_state", info.State(rs.EMPTY, "", -1.0, 0))  # restart: disk copy read at NOW + 2000
    monkeypatch.setattr(info, "_disk_read", False)
    found = read_at(NOW + 2600, "weekly")
    assert weekly(found) and "weekly" in found.missing
    assert weekly(read_at(NOW + 3000, ""))
    monkeypatch.setattr(info, "_state", info.State(rs.EMPTY, "", -1.0, 0))  # restart: disk copy read at NOW + 3000
    monkeypatch.setattr(info, "_disk_read", False)
    assert not weekly(read_at(NOW + 3000 + info.KEEP_ANSWER_SECONDS, "weekly"))


# B-038: "Show Field" from the List view read the field but the row had no place to show it
def test_b038_field_shown_under_list_row(qml_warnings, page, monkeypatch):  # noqa: F811
    backend = page.backend  # noqa: F811
    backend.setOpenOnly(False)
    backend.setTab(0)
    backend.setView(1)
    monkeypatch.setattr(info, "read_field", lambda kind, event_id: rs.FieldLevel(
        2, (("LMP2", 2),), (("Silver", 2),), (), True))
    pump(0.2)
    root = page.view.rootObject()
    rows = [item for item in items_of(root) if item.objectName() == "raceRow" and item.isVisible()]
    assert rows
    before = rows[0].height()
    key = rows[0].property("modelData")["key"]
    backend.runRaceAction(key, "field", "")
    assert wait(lambda: f"field:{key}" in backend.details)
    pump(0.2)
    fields = [item for item in items_of(rows[0]) if item.objectName() == "raceRowField" and item.isVisible()]
    assert fields and fields[0].height() > 0, "field read from the list view never shown"
    assert rows[0].height() > before  # row grown to hold it
    QCoreApplication.processEvents()
    assert not qml_warnings, qml_warnings
