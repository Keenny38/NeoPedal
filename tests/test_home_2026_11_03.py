"""Home page review 2026-11-03: no duplicates (quick access without the navigation bar, version & updates in the help
menu, overlays & preset in one card), hierarchy (slim status line, driver ranks in big type, best lap in big type with
lap bars, debrief at once, driving time of each day), relative dates, live race countdown & register, ranks read
again from the card, cards placed row by row without holes"""

import time
from types import SimpleNamespace

from neopedal.process.results_text import MISSING
from neopedal.setting import cfg
from neopedal.ui import home_debrief, home_driver
from neopedal.ui.quick import home_backend
from neopedal.ui.quick.formatting import long_date_time, relative_date
from neopedal.userfile.driver_history import SessionRecord
from neopedal.userfile.session_debrief import Debrief, DebriefLap
from tests.test_audit_g_qml_pages import item_named, items_of, pump
from tests.test_home_view import item_texts
from tests.test_perf_page_state import qml_warnings  # noqa: F401
from tests.test_ui_audit_2026_10_29_home import home, on_track  # noqa: F401


# --- Dates
def test_relative_date():
    now = 1_790_000_000.0
    assert relative_date(now - 5, now) == "Just now"
    assert relative_date(now - 600, now) == "10 min ago"
    assert relative_date(now - 7200, now) == "2 h ago"
    assert relative_date(now - 86400 * 1.5, now) == "Yesterday"
    assert relative_date(now - 86400 * 3, now) == "3 days ago"
    assert relative_date(now - 86400 * 30, now) not in ("", MISSING)  # short date after a week
    assert relative_date(0.0, now) == MISSING and long_date_time(0.0) == ""
    assert "·" in long_date_time(now)  # date & time (tooltip)


def test_last_session_date_relative():
    record = SessionRecord(time=time.time() - 7200, track="Spa", vehicle="Oreca 07", session=1, best=123.4)
    card = home_backend.last_session_card(record, home_backend.LogoCache())
    assert card["date"] == "2 h ago" and card["dateTip"]


# --- Lap bars & day bars
def debrief_of(times: list[tuple[float, bool]]) -> Debrief:
    record = SessionRecord(time=1.0, track="Spa", vehicle="Oreca 07")
    laps = tuple(DebriefLap(f"{index}.lap", index + 1, laptime, valid) for index, (laptime, valid) in enumerate(times))
    best = min(laptime for laptime, valid in times if valid)
    return Debrief(record, laps, best, 0.0, 0.0, 0, 0.0, 0.0, 0.0, 0.0, "", "", "", "")


def test_lap_bars():
    bars = home_debrief.lap_bars(debrief_of([(100.0, True), (102.0, True), (130.0, False)]))
    assert [bar["ratio"] for bar in bars] == [1.0, 0.5, home_debrief.LAP_BAR_MIN]
    assert [bar["best"] for bar in bars] == [True, False, False] and bars[2]["valid"] is False
    assert bars[0]["tip"] == "Lap 1 · 1:40.000" and bars[2]["tip"].endswith("Invalid lap")
    assert home_debrief.lap_bars(debrief_of([(100.0, True)])) == []  # one lap: nothing to compare


def test_week_days_and_bars():
    now = time.mktime((2026, 11, 3, 12, 0, 0, 0, 0, -1))
    records = [SessionRecord(time=now - 600, track="Spa", vehicle="GT3", seconds=1200.0),
               SessionRecord(time=now - 86400 * 2, track="Spa", vehicle="GT3", seconds=600.0),
               SessionRecord(time=now - 86400 * 10, track="Spa", vehicle="GT3", seconds=900.0)]  # before the week
    days = home_backend.week_days(records, now)
    assert len(days) == 7 and [seconds for _start, seconds in days] == [0, 0, 0, 0, 600.0, 0, 1200.0]
    assert days[-1][0] == time.mktime((2026, 11, 3, 0, 0, 0, 0, 0, -1))  # today last, from midnight
    bars = home_backend.day_bars(days)
    assert [bar["ratio"] for bar in bars] == [0, 0, 0, 0, 0.5, 0, 1.0] and bars[-1]["today"]
    assert all(len(bar["label"]) == 1 for bar in bars) and "20 min" in bars[-1]["tip"]
    assert home_backend.day_bars([(now, 0.0)] * 7) == []  # nothing driven
    items = [{"kind": "summary", "sessions": 1, "laps": 3, "seconds": 1200.0, "meters": 0.0, "tracks": 1, "vehicles": 1}]
    assert len(home_backend.week_card(items, days)["days"]) == 7


# --- Driver: ranks remembered
def test_driver_note_relative(ui_env):
    from neopedal.process import driver_ranks as dr

    player = dr.DriverRanks("Keenny Hess", "", "", "", dr.Rank("Silver", 2, 25), dr.Rank("Bronze", 2, 31), "")
    card = home_driver.driver_card(player, True, time.time() - 86400 * 9, (), None)
    assert card["note"].startswith("Last ranks known · ") and card["noteTip"] and card["noteStale"]
    assert "refresh" not in card  # read from the game file only: nothing to ask again
    card = home_driver.driver_card(player, False, time.time(), (), None)  # current: no note
    assert card["note"] == ""


# --- Quick access: the navigation bar not repeated
def test_quick_access_leaves_navigation_bar_out(home):  # noqa: F811
    from neopedal.ui.nav_rail import current_rail_items

    assert "lap_viewer" in current_rail_items()
    cfg.application["home_quick_access"] = "lap_viewer,bug_report,perf_view"
    try:
        home.backend.refresh_quick()
        assert [row["key"] for row in home.backend.quick] == ["bug_report", "perf_view"]
    finally:
        del cfg.application["home_quick_access"]
        home.backend.refresh_quick()


# --- Status line
def test_status_slim_when_ready_none_on_track(qml_warnings, home, monkeypatch):  # noqa: F811
    from neopedal.api_control import api

    backend = home.backend
    root = home.view.rootObject()
    monkeypatch.setattr(api.read.state, "version", lambda: "not running")
    backend.refresh_live()
    pump(0.1)
    banner = item_named(root, "statusBanner")
    assert banner.isVisible() and not root.property("bannerSlim")
    tall = banner.height()
    backend.publish("status", {"key": "ready", "level": "success", "title": "Ready", "text": "Game connected, overlays on.",
                               "action": "", "actionText": "", "rows": []}, backend.statusChanged)
    pump(0.1)
    assert banner.isVisible() and root.property("bannerSlim") and banner.height() < tall * 0.75
    on_track(monkeypatch)
    backend.refresh_live()
    backend.publish("status", {**backend.status, "rows": []}, backend.statusChanged)  # nothing else to tell
    pump(0.1)
    assert backend.status["level"] == "live" and not banner.isVisible()  # the game card tells the session
    assert not qml_warnings, qml_warnings


# --- Cards placed row by row
def publish_cards(backend, debrief: dict | None = None):
    backend.publish("driver", {"name": "Keenny Hess", "ranks": [], "figures": []}, backend.driverChanged)
    backend.set_loading("driver", False)
    backend.publish("lastSession", {"track": "Spa", "vehicle": "Oreca 07", "session": "Race", "date": "2 h ago",
                                    "dateTip": "Tuesday · 10:00"}, backend.lastSessionChanged)
    backend.publish("debrief", debrief or {}, backend.debriefChanged)
    backend.set_loading("debrief", False)
    backend.publish("week", {"summary": "1 session · 30 min · 12 laps", "highlights": [], "days": [
        {"label": "M", "ratio": 0.0, "today": False, "tip": "Monday"}] * 6 + [
        {"label": "T", "ratio": 1.0, "today": True, "tip": "Tuesday"}]}, backend.weekChanged)
    backend.set_loading("week", False)


def test_cards_placed_without_holes(qml_warnings, home):  # noqa: F811
    backend = home.backend
    root = home.view.rootObject()
    publish_cards(backend)
    pump(0.2)
    driver, overlays = item_named(root, "driverCard"), item_named(root, "overlaysCard")
    last, week = item_named(root, "lastSessionCard"), item_named(root, "weekCard")
    assert root.property("columns") == 3
    assert driver.y() == overlays.y() and last.y() == week.y() > driver.y()  # driver & overlays, then last & week
    assert driver.width() > overlays.width() * 1.8 and last.width() > week.width() * 1.8
    assert item_named(root, "dayBars").isVisible()
    theme = home.view.rootContext().contextProperty("theme")
    home.resize(int(theme.property("bpWide")) - 10, 1000)  # 2 columns: overlays & week side by side, driver & last
    # session whole rows
    pump(0.3)
    assert root.property("columns") == 2
    assert overlays.y() == week.y() and driver.y() < overlays.y() < last.y()
    backend.publish("week", {}, backend.weekChanged)  # week gone: overlays widened over the hole
    pump(0.3)
    assert overlays.width() > driver.width() * 0.9
    assert not qml_warnings, qml_warnings


def test_debrief_best_lap_big_and_bars(qml_warnings, home):  # noqa: F811
    backend = home.backend
    root = home.view.rootObject()
    bars = [{"ratio": 1.0, "valid": True, "best": True, "tip": "Lap 1 · 1:30.000"},
            {"ratio": 0.4, "valid": True, "best": False, "tip": "Lap 2 · 1:31.000"}]
    publish_cards(backend, {"best": "1:30.000", "figures": ["2 laps"], "personal": "new",
                            "personalText": "New personal best", "tips": [], "laps": bars, "canOpen": False})
    pump(0.2)
    best = item_named(root, "debriefBest")
    assert best.property("text") == "1:30.000" and best.property("role") == "display"
    assert item_named(root, "lapBars").isVisible() and "New personal best" in item_texts(home.view)
    assert "2 h ago" in item_named(root, "lastSessionDetail").property("text")
    assert not qml_warnings, qml_warnings


# --- Next races: live countdown & register
def race_row(start: float, **values) -> dict:
    row = {"key": "daily:1", "startKey": f"daily:1@{int(start)}", "kind": "daily", "title": "LMGT3 Fixed",
           "track": "Algarve", "trackLogo": "", "start": "12:00", "until": "in 3 min", "running": False, "soon": True,
           "imminent": False, "startTime": start, "classes": [], "tierText": "Beginner", "length": "20 min",
           "place": "", "registeredMe": False, "registrationOpen": True, "eventId": "abc", "settings": "", "open": 1}
    return {**row, **values}


def test_races_countdown(qml_warnings, home, monkeypatch):  # noqa: F811
    from neopedal import race_schedule_info as info
    from neopedal.ui.quick import schedule_view

    backend = home.backend
    root = home.view.rootObject()
    start = time.time() + 125
    rows = [race_row(start), race_row(start + 3600, key="daily:2", soon=False, until="in 1 h 02",
                                      settings="Team race")]
    monkeypatch.setattr(schedule_view, "home_card", lambda *args: [dict(row) for row in rows])
    monkeypatch.setattr(info, "state", lambda: SimpleNamespace(schedule=None, status=info.PUBLIC))
    backend.publish_races()
    assert not any("canRegister" in row for row in backend.races["rows"])  # registered in the game
    pump(1.2)  # countdown ticks
    countdowns = {item.property("text") for item in items_of(root) if item.objectName() == "raceCountdown"}
    assert any(text.startswith("in 2:0") for text in countdowns), countdowns  # minutes & seconds within 10 min
    assert "in 1 h 02" in item_texts(home.view)
    assert not qml_warnings, qml_warnings


