"""Non-regression tests of the bug audit of the Upcoming Races page & what serves it (2026-11-02,
audit_bugs_upcoming_races_2026-11-02.md), for what remains since RaceOS reads were removed (2026-11-04): daily races
of the public RaceControl site, reminders, timeline, filters; simulated clock & time zone, never network"""

from __future__ import annotations

import calendar
import time
import types

from PySide6.QtCore import QCoreApplication

from neopedal import race_schedule_info as info
from neopedal.process import race_schedule as rs
from tests.test_audit_g_qml_pages import click, item_named, items_of, pump
from tests.test_perf_page_state import qml_warnings  # noqa: F401
from tests.test_race_schedule import NOW, fresh_info, page, schedule  # noqa: F401

DAY = calendar.timegm((2026, 11, 2, 0, 0, 0))  # 2026-11-02 00:00 UTC
OLD = NOW + 600  # start of "LMP2 Fixed" a reminder is set for (schedule of tests.test_race_schedule)
RACE = "daily/beginner/LMP2 Fixed"


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


def set_state(monkeypatch, found: rs.Schedule, status: str = info.PUBLIC, serial: int = 7):
    monkeypatch.setattr(info, "_state", info.State(found, status, 0.0, serial))


def set_schedule(monkeypatch, found: rs.Schedule):
    monkeypatch.setattr(info, "_state", info.State(found, info.PUBLIC, time.monotonic(), 9))


# B-001: a reminder follows its start moved (closest start of the race within 1 h), told
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
    now[0] = OLD + 1800 - 300
    reminders.check()
    assert told[1] == "LMP2 Fixed starts in 5 min (Portimao)" and reminders.keys() == {}


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


# B-001: nothing changed while the schedule is not read (page not answered, option off, race kind not read)
def test_b001_reminder_kept_when_schedule_not_read(ui_env, monkeypatch):
    now = [NOW]
    reminders, told = make_reminders(monkeypatch, now)
    key = {f"{RACE}@{int(OLD)}": 5}
    cancelled = read_schedule({OLD: None, NOW + 3300: None})
    for serial, (found, status) in enumerate([
            (cancelled, info.FAILED), (cancelled, info.OFF), (cancelled, ""),
            (cancelled._replace(read_time=0.0), info.PUBLIC),
            (read_schedule({OLD: None, NOW + 3300: None}, ("daily",)), info.PUBLIC),
            (cancelled._replace(events=()), info.PUBLIC)], 10):  # race missing: never judged
        set_state(monkeypatch, found, status, serial)
        reminders.check()
        assert reminders.keys() == key and told == [], (serial, status)
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


# B-017: the menu of a timeline block acts on the start clicked (reminder, calendar), the card on its first start
def test_b017_timeline_block_menu_acts_on_clicked_start(qml_warnings, page, monkeypatch, tmp_path):  # noqa: F811
    from PySide6.QtWidgets import QFileDialog

    from neopedal.ui.quick import schedule_reminders
    from neopedal.ui.quick.schedule_view import start_text

    backend = page.backend
    backend.setView(2)
    pump(0.2)
    race = backend.daily[0]["races"][0]
    key, first = race["key"], race["startKey"]
    later = NOW + 3300  # third start of "LMP2 Fixed"
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
    backend.runRaceAction(key, "remind:10", "", later)
    assert schedule_reminders.reminders().minutes_of(f"{key}@{int(later)}") == 10
    assert schedule_reminders.reminders().minutes_of(first) == 0  # first start untouched
    path = tmp_path / "race.ics"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(path), ""))
    backend.runRaceAction(key, "export", "", later)
    assert "DTSTART:" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(later)) in path.read_text(encoding="utf-8")
    QCoreApplication.processEvents()
    assert not qml_warnings, qml_warnings


# B-008: hour marks of the timeline on whole hours of the local clock (time zones off a whole hour too)
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


# B-014: Clear Filters empties the search field too
def test_b014_clear_filters_empties_search_field(page):  # noqa: F811
    backend = page.backend
    field = item_named(page.view.rootObject(), "raceSearch")
    field.setProperty("text", "hyper")
    backend.setSearch("hyper")
    assert backend.count == 1
    backend.clearFilters()
    pump(0.1)
    assert backend.search == "" and backend.count == 2
    assert field.property("text") == ""


# B-016: "+n more" starts expanded stay expanded at the next list update
def test_b016_expanded_starts_kept_on_next_tick(page, monkeypatch):  # noqa: F811
    backend = page.backend
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


# B-020: races of the same title on two tracks keep their own keys (reminders, menus)
def test_b020_same_title_races_keep_own_keys(ui_env):
    from neopedal.ui.quick import schedule_view as view

    base = schedule(NOW)
    lmp2 = next(event for event in base.events if event.title == "LMP2 Fixed")
    twin = lmp2._replace(scene="MonzaWEC", starts=(rs.Start(NOW + 1500),))
    found = base._replace(events=(*base.events, twin))
    rows = [row for event in found.events if (row := view.event_row(event, found, ("", 0), NOW, lambda _: ""))]
    keys = [row["key"] for row in rows]
    assert len(set(keys)) == len(keys), keys
    assert "daily/advanced/Hyper Hour" in keys  # races not in duplicate keep their key (reminders kept)
    assert {"daily/beginner/LMP2 Fixed#portimaowec", "daily/beginner/LMP2 Fixed#MonzaWEC"} <= set(keys)
