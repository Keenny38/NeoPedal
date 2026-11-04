"""Upcoming Races: daily races of the public RaceControl site, shared reads, reminders, your laps, rows of the page &
Home card, filters, menu, calendar export, QML page, your online races of the results files"""

import time

import pytest
from PySide6.QtCore import QCoreApplication

from neopedal import race_schedule_info as info
from neopedal.process import race_schedule as rs
from tests.test_audit_g_qml_pages import item_named, items_of, pump
from tests.test_perf_page_state import qml_warnings  # noqa: F401

NOW = 1_793_580_000.0  # 2026-11-02 00:40 UTC


def iso(seconds: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))


TRACKS = [
    {"sceneDesc": "PORTIMAOWEC", "displayProperties": {"shortName": "Algarve International Circuit"},
     "shortName": "Algarve International Circuit 1.27", "owned": True},
    {"sceneDesc": "MONZAWEC", "shortName": "Aut\ufffddromo Monza 1.2", "owned": False},
    {"sceneDesc": "SPAELMS", "shortName": "Circuit de Spa-Francorchamps 1.3", "owned": True},
]


def event(title: str, tier: str, track: str, scene: str, starts: list[float], minutes: float) -> rs.Event:
    """Daily race as the public page gives it (process/public_schedule.parse_daily)"""
    return rs.Event("daily", tier, title, track, scene, tuple(rs.Start(start) for start in starts), minutes * 60)


def schedule(now_read: float = NOW) -> rs.Schedule:
    events = (event("LMP2 Fixed", "beginner", "Portimao Wec 2023", "portimaowec", [NOW - 1800, NOW + 600, NOW + 3300],
                    31.5),
              event("Hyper Hour", "advanced", "Monza", "monzawec", [NOW + 1200], 72.5))
    return rs.Schedule(now_read, events, rs.parse_track_catalog(TRACKS), (), {"beginner": 900.0, "advanced": 1800.0})


def logo(_track):
    return ""


def test_game_catalogs():
    tracks = rs.parse_track_catalog(TRACKS)
    assert rs.track_of("PortimaoWEC", "x", tracks) == ("Algarve International Circuit", True)  # version cut
    assert rs.track_of("MonzaWEC", "Monza", tracks) == ("Monza", False)  # name broken by the game (U+FFFD)
    assert rs.track_of("Nowhere", "Nowhere", tracks) == ("Nowhere", None)


def test_next_starts_keep_running_race():
    race = next(item for item in schedule().events if item.title == "LMP2 Fixed")
    assert [start.time for start in rs.next_starts(race, NOW)] == [NOW - 1800, NOW + 600, NOW + 3300]  # 31 min
    assert [start.time for start in rs.next_starts(race, NOW + 300)] == [NOW + 600, NOW + 3300]


def test_calendar_file():
    text = rs.ics_text([{"uid": "a b", "title": "LMP2, Fixed; x", "start": NOW, "end": NOW + 1800,
                         "location": "Monza", "description": "line1\nline2 " + "x" * 120}], NOW - 60)
    lines = text.split("\r\n")
    assert lines[0] == "BEGIN:VCALENDAR" and lines[-2] == "END:VCALENDAR" and text.endswith("\r\n")
    assert "SUMMARY:LMP2\\, Fixed\\; x" in lines and "DTSTART:20261102T004000Z" in lines
    assert all(len(line.encode()) <= 75 for line in lines)
    assert any(line.startswith(" ") for line in lines)  # long description folded


# Shared reads
def settle_schedule_reads(timeout: float = 10.0):
    """Schedule reads started by earlier tests ended: the app's race watch (made by the first Home or Upcoming
    Races page of the process) and Home pages read it on page jobs, with the patches of whichever test runs then"""
    from neopedal.jobs import page_pool

    pool = page_pool()
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        with pool._lock:  # nothing waiting, every worker idle: no read about to start either
            if not pool._queue and pool._idle == pool._workers:
                break
        time.sleep(0.01)
    assert info._lock.acquire(timeout=30.0), "schedule read of an earlier test stuck"  # one running ends first
    info._lock.release()


class PublicPage:
    """Public page of RaceControl: schedule answered (never a real request), reads counted"""

    def __init__(self):
        self.reads = 0
        self.answer: rs.Schedule | None = schedule()

    def read(self, now=None):
        self.reads += 1
        return self.answer


@pytest.fixture
def fresh_info(monkeypatch, tmp_path):
    from neopedal.process import public_schedule
    from neopedal.setting import cfg
    from neopedal.ui.quick import race_watch as rw

    watch = rw._watch
    paused = watch is not None and watch._timer.isActive()
    if paused:  # app's race watch reads nothing during the test (events run by page tests), started again after
        watch._timer.stop()
    settle_schedule_reads()
    monkeypatch.setattr(info, "_state", info.State(rs.EMPTY, "", -1.0, 0))
    monkeypatch.setattr(cfg.path, "config", f"{tmp_path.as_posix()}/")
    monkeypatch.setattr(info, "_game_tracks", lambda: rs.parse_track_catalog(TRACKS))
    monkeypatch.setattr(info, "enabled", lambda: True)
    page = PublicPage()
    monkeypatch.setattr(public_schedule, "read", page.read)
    yield page
    if paused:
        watch._timer.start()


def test_read_once_an_hour(fresh_info, monkeypatch):
    state = info.read()
    assert state.status == info.PUBLIC and len(state.schedule.events) == 2 and fresh_info.reads == 1
    assert not info.due() and info.read() is state and fresh_info.reads == 1  # read again only after READ_SECONDS
    assert info.due(state.tried + info.READ_SECONDS)
    assert info.read(force=True) is state and fresh_info.reads == 1  # Read Again at once: not asked twice
    monkeypatch.setattr(info.time, "monotonic", lambda: state.tried + info.FORCE_SECONDS)
    info.read(force=True)
    assert fresh_info.reads == 2


def test_read_failed_keeps_the_races_and_tries_again_soon(fresh_info, monkeypatch):
    first = info.read()
    fresh_info.answer = None  # offline, or the page changed
    monkeypatch.setattr(info.time, "monotonic", lambda: first.tried + info.READ_SECONDS)
    again = info.read()
    assert again.status == info.PUBLIC and again.schedule is first.schedule and again.failures == 1
    assert info.due(again.tried + info.RETRY_SECONDS) and not info.due(again.tried + info.RETRY_SECONDS - 1)


def test_never_read_page_tells_failed(fresh_info):
    fresh_info.answer = None
    assert info.read().status == info.FAILED


def test_option_off_reads_nothing(fresh_info, monkeypatch):
    info.read()
    monkeypatch.setattr(info, "enabled", lambda: False)
    assert info.due()  # turned off: told at once
    state = info.read()
    assert state.status == info.OFF and state.schedule.empty and fresh_info.reads == 1
    monkeypatch.setattr(info, "enabled", lambda: True)
    assert info.due() and info.read().status == info.PUBLIC  # turned on again: read at once


# Rows
def test_event_rows_next_start(ui_env):
    from neopedal.ui.quick import schedule_view as view

    found = schedule()
    lmp2 = next(item for item in found.events if item.title == "LMP2 Fixed")
    row = view.event_row(lmp2, found, NOW, logo)
    assert row["startTime"] == NOW + 600 and not row["running"] and row["soon"]  # running one skipped
    assert row["until"] == "in 10 min" and row["track"] == "Algarve International Circuit"
    assert row["length"] == "32 min" and row["sessions"] == "Race 32 min" and row["owned"] == "" and row["trackOwned"]
    hyper = next(item for item in found.events if item.title == "Hyper Hour")
    row = view.event_row(hyper, found, NOW, logo)
    assert row["owned"] == "Track not owned" and not row["trackOwned"]
    assert view.event_row(lmp2, found, NOW + 4 * 3600, logo) is None  # all over
    cards = view.home_card(found, NOW, logo, 3)
    assert [card["title"] for card in cards] == ["LMP2 Fixed", "Hyper Hour"]
    assert view.until_text(NOW + 3 * 86400, NOW) == "in 3 days"
    assert view.until_text(NOW - 60, NOW, 600) == "Running"
    assert view.length_text(5400) == "1 h 30" and view.length_text(36000) == "10 h"


def test_day_names_and_timeline(ui_env):
    from neopedal.ui.quick import schedule_view as view

    noon = time.mktime((2026, 11, 2, 12, 0, 0, 0, 0, -1))
    assert view.start_text(noon + 3600, noon) == time.strftime("%H:%M", time.localtime(noon + 3600))
    assert view.start_text(noon + 86400, noon).startswith("Tomorrow ")
    assert view.start_text(noon + 3 * 86400, noon) != view.start_text(noon + 86400, noon)
    found = schedule()
    rows = [row for item in found.events if (row := view.event_row(item, found, NOW, logo))]
    line = view.timeline([("beginner", [rows[0]]), ("advanced", rows[1:])], found, NOW)
    assert [lane["tierText"] for lane in line["lanes"]] == ["Beginner", "Advanced"]
    blocks = line["lanes"][0]["items"]
    places = [((max(block["start"], NOW) - NOW) / line["period"],
               (min(block["end"], NOW + line["period"]) - max(block["start"], NOW)) / line["period"])
              for block in blocks]
    assert [round(at, 3) for at, _width in places] == [0.0, round(600 / 21600, 3), round(3300 / 21600, 3)]
    assert blocks[0]["running"] and all(0 < width <= 1 for _at, width in places) and line["now"] == NOW
    later = view.timeline([("beginner", [rows[0]]), ("advanced", rows[1:])], found, NOW + 5)
    assert later["lanes"] == line["lanes"]  # a tick later: same lanes, nothing made again


def test_rows_in_french(ui_env):
    from neopedal import i18n
    from neopedal.ui.quick import schedule_view as view

    i18n.set_language("Français")
    try:
        assert view.until_text(NOW + 600, NOW) == "dans 10 min"
        assert view.until_text(NOW - 60, NOW, 600) == "En cours"
        assert view.tier_text("beginner") == "Débutant"
        assert view.frequency_text(900) == "toutes les 15 min"
    finally:
        i18n.set_language("English")


def test_reminders_told_once(ui_env, monkeypatch):
    from neopedal.ui.notification import message_text
    from neopedal.ui.quick import schedule_reminders as sr

    now = [NOW]
    told = []
    monkeypatch.setattr(sr.RaceReminders, "tell",
                        staticmethod(lambda message, *args, **kwargs: told.append(message_text(message))))
    reminders = sr.RaceReminders(clock=lambda: now[0])
    reminders.set("race@1", "LMP2 Fixed", "Monza", NOW + 1200, 10)
    reminders.set("race@2", "Old", "", NOW - 60, 10)  # started: never set
    assert reminders.keys() == {"race@1": 10}
    reminders.check()
    assert told == []
    now[0] = NOW + 600
    reminders.check()
    assert told == ["LMP2 Fixed starts in 10 min (Monza)"] and reminders.keys() == {}
    reminders.check()
    assert len(told) == 1
    assert sr._valid({"key": "a", "start": "x", "minutes": 5}) is None


def test_reminders_follow_the_public_races(ui_env, fresh_info, monkeypatch):
    from neopedal.ui.quick import schedule_reminders as sr
    from neopedal.ui.quick.schedule_view import race_key

    found = schedule()
    lmp2 = found.events[0]
    key = f"{race_key(lmp2, found.events)}@{int(NOW + 600)}"
    later = found._replace(events=(lmp2._replace(starts=(rs.Start(NOW + 900),)), *found.events[1:]))
    entry = {"key": key, "title": "LMP2 Fixed", "track": "", "start": NOW + 600, "minutes": 10, "steps": [10],
             "registered": False}
    reminders, moved_pairs, dropped = sr.follow_schedule([entry], later, NOW)
    assert [entry["start"] for entry in reminders] == [NOW + 900] and moved_pairs and not dropped  # start moved


def test_your_laps_on_the_track(ui_env):
    from neopedal.ui.quick.schedule_personal import PersonalData, personal_row
    from neopedal.userfile.lap_reference import LapReferenceTable

    data = PersonalData({"Algarve International Circuit": {"GT3 - Porsche": {"pb": 102.314},
                                                           "GT3 - Ferrari": {"pb": 103.0}, "LMP3": {"pb": 0}}},
                        {"GT3 - Porsche": "GT3", "GT3 - Ferrari": "GT3"}, {"Algarve International Circuit": NOW},
                        LapReferenceTable(), {"portimaowec": ("Algarve International Circuit",)},
                        frozenset({"Algarve International Circuit - GT3"}))
    row = personal_row(data, "Portimao Wec 2023", "portimaowec", lambda level: "")
    assert row["known"] and row["statsTrack"] == "Algarve International Circuit"
    assert [(best["vehicleClass"], best["vehicle"], best["best"]) for best in row["bests"]] == [
        ("GT3", "GT3 - Porsche", "1:42.314")]  # fastest of the class, lap time 0 left out
    assert personal_row(data, "Nowhere", "x", lambda level: "") == {
        "known": False, "statsTrack": "", "bests": [], "lastDriven": 0.0}


# Page
@pytest.fixture
def page(ui_env, fresh_info, monkeypatch):
    from neopedal.ui.quick import schedule_backend, schedule_reminders
    from neopedal.ui.quick.schedule_personal import EMPTY
    from neopedal.ui.race_schedule_viewer import RaceScheduleViewer

    monkeypatch.setattr(schedule_reminders, "_reminders", None)  # file of this test's config folder
    monkeypatch.setattr(time, "time", lambda: NOW)
    monkeypatch.setattr(schedule_backend, "read_personal", lambda: EMPTY)
    monkeypatch.setattr(info, "_state", info.State(schedule(NOW), info.PUBLIC, time.monotonic(), 1))
    viewer = RaceScheduleViewer(None)
    viewer.resize(1200, 800)
    viewer.show()
    pump(0.3)
    yield viewer
    viewer.close()
    pump(0.1)
    schedule_reminders._reminders = None


def test_page_shows_every_view(qml_warnings, page):  # noqa: F811
    backend = page.backend
    assert backend.count == 2
    assert [group["tier"] for group in backend.daily] == ["beginner", "advanced"]
    assert backend.daily[0]["frequency"] == "every 15 min"
    root = page.view.rootObject()
    for view in range(3):
        backend.setView(view)
        pump(0.05)
    assert item_named(root, "timelineBlock") is not None
    assert backend.page_settings()["view"] == 2
    backend.setView(0)
    pump(0.1)
    assert item_named(root, "raceCard").isVisible()
    assert backend.status["note"].startswith("Daily races of the public RaceControl site")
    QCoreApplication.processEvents()
    assert not qml_warnings, qml_warnings


def test_filters(page):
    backend = page.backend
    backend.setSearch("hyper")
    assert backend.count == 1 and backend.daily[0]["races"][0]["title"] == "Hyper Hour"
    backend.clearFilters()
    assert backend.count == 2
    backend.setOwnedOnly(True)  # Monza not owned
    assert backend.count == 1 and backend.daily[0]["races"][0]["title"] == "LMP2 Fixed"
    backend.clearFilters()
    assert not backend.ownedOnly and backend.search == ""


def test_menu_actions(page, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    from neopedal.ui.quick import game_window, schedule_reminders

    backend = page.backend
    key = backend.daily[0]["races"][0]["key"]
    entries = backend.raceActions(key)
    ids = [entry["id"] for entry in entries]
    # Race first (register in the game), then planning (reminders in one submenu, calendar), then my stats
    assert ids[0] == "game" and ids[-2:] == ["stats", "prepare"] and ids.index("remind:10") < ids.index("export")
    assert [entry["section"] for entry in entries] == sorted(
        (entry["section"] for entry in entries), key=["race", "plan", "mine"].index)
    assert not entries[-2]["enabled"]  # never driven there
    start_key = backend.daily[0]["races"][0]["startKey"]
    backend.runRaceAction(key, "remind:10", "")
    assert schedule_reminders.reminders().minutes_of(start_key) == 10
    assert backend.daily[0]["races"][0]["reminder"] == 10
    assert next(entry for entry in backend.raceActions(key) if entry["id"] == "remind:10")["checked"]
    backend.runRaceAction(key, "remind:0", "")
    assert schedule_reminders.reminders().minutes_of(start_key) == 0
    path = tmp_path / "race.ics"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(path), ""))
    backend.runRaceAction(key, "export", "")
    assert "BEGIN:VEVENT" in path.read_text(encoding="utf-8")
    shown = []
    monkeypatch.setattr(game_window, "show_game_window", lambda: shown.append(1) or True)
    backend.runRaceAction(key, "game", "")
    assert shown == [1]  # the game registers: its window brought to the front


def test_menu_sections_and_submenus(qml_warnings, page):  # noqa: F811
    from PySide6.QtCore import Q_ARG, Q_RETURN_ARG, QEvent, QMetaObject, QObject

    backend = page.backend
    key = backend.daily[0]["races"][0]["key"]
    backend.runRaceAction(key, "remind:10", "")  # rows made again: personal laps set after
    backend._sources[key][0]["personal"] = {"known": True, "statsTrack": "Portimao", "lastDriven": 0.0, "bests": [
        {"vehicleClass": "Hyper", "vehicle": "Hyper - A", "lapsFolder": "", "seconds": 90.0},
        {"vehicleClass": "LMP3", "vehicle": "LMP3 - B", "lapsFolder": "Portimao - LMP3", "seconds": 99.0}]}
    entries = backend.raceActions(key)
    mine = [entry for entry in entries if entry["section"] == "mine"]
    assert [(entry["menu"], entry["text"], entry["enabled"]) for entry in mine] == [
        ("Driver Stats", "Hyper", True), ("Driver Stats", "LMP3", True), ("Recorded Laps", "Hyper", False),
        ("Recorded Laps", "LMP3", True), ("Prepare Race", "Hyper", True), ("Prepare Race", "LMP3", True)]
    menu = page.view.rootObject().findChild(QObject, "raceMenu")

    def item_at(index):
        return QMetaObject.invokeMethod(menu, "itemAt", Q_RETURN_ARG("QQuickItem*"), Q_ARG("int", index))

    QMetaObject.invokeMethod(menu, "fill", Q_ARG("QVariant", entries))
    items = [item_at(index) for index in range(menu.property("count"))]
    titles = ["|" if "Separator" in item.metaObject().className() else item.property("text") for item in items]
    assert titles[0] == "Register in the Game" and titles.count("|") == 2
    assert titles[titles.index("|") + 1].startswith("Remind Me Before ")
    assert titles[-3:] == ["Driver Stats", "Recorded Laps", "Prepare Race"]
    assert items[titles.index("|") + 1].property("shortcut") == "10 min"  # reminder set shown on its row
    QMetaObject.invokeMethod(menu, "fill", Q_ARG("QVariant", entries))  # filled again: nothing left behind
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert menu.property("count") == len(titles)
    QCoreApplication.processEvents()
    assert not qml_warnings, qml_warnings


def test_cards_kept_while_time_goes_by(qml_warnings, page, monkeypatch):  # noqa: F811
    """Lists told again at each tick update cards in place: none made again (a click or an open menu was lost to
    it), text moved on; timeline blocks kept too, placed from now"""
    from PySide6.QtCore import QMetaObject, QObject, QPoint, QPointF, Qt
    from PySide6.QtTest import QTest

    backend = page.backend
    pump(0.2)
    root = page.view.rootObject()
    gone = []

    def watched(name):
        found = [item for item in items_of(root) if item.objectName() == name and item.isVisible()]
        for item in found:
            item.destroyed.connect(lambda *_args, item_name=name: gone.append(item_name))
        return found

    cards = watched("raceCard")
    until = [card.property("race")["until"] for card in cards]
    menu = root.findChild(QObject, "raceMenu")
    point = cards[0].mapToScene(QPointF(cards[0].width() - 30, 12))
    QTest.mouseClick(page.view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(round(point.x()), round(point.y())))
    pump(0.4)
    assert menu.property("visible")
    lists = []
    backend.listsChanged.connect(lambda: lists.append(1))
    for step in range(1, 13):  # a minute of ticks: times to start move on
        monkeypatch.setattr(time, "time", lambda step=step: NOW + step * 5)
        backend.publish_all()
        pump(0.02)
    assert lists and not gone  # told again, nothing made again
    assert [card.property("race")["until"] for card in cards] != until
    assert menu.property("visible") and menu.property("toggleSource") == cards[0]  # menu still open on its card
    QMetaObject.invokeMethod(menu, "close")
    pump(0.4)
    backend.setView(2)
    pump(0.2)
    blocks = watched("timelineBlock")
    x = blocks[1].property("x")
    for step in range(13, 25):
        monkeypatch.setattr(time, "time", lambda step=step: NOW + step * 5)
        backend.publish_all()
        pump(0.02)
    assert not gone and blocks[1].property("x") < x  # same blocks, moved toward now
    QCoreApplication.processEvents()
    assert not qml_warnings, qml_warnings


def test_page_tells_option_off(qml_warnings, page, monkeypatch):  # noqa: F811
    monkeypatch.setattr(info, "enabled", lambda: False)
    page.backend.readAgain()
    for _ in range(100):
        pump(0.05)
        if page.backend.status.get("off"):
            break
    assert page.backend.status["off"] and page.backend.status["level"] == "warning"
    assert item_named(page.view.rootObject(), "statusNotice").isVisible()
    assert not qml_warnings, qml_warnings


def test_rail_migration_adds_page_once():
    from neopedal.setting_preupdate import preupdate_global_setting

    old = {"application": {"rail_items": "home,race_results_viewer,preset"}}
    preupdate_global_setting((2, 51, 7), old)
    assert old["application"]["rail_items"] == "home,race_schedule_viewer,race_results_viewer,preset"
    preupdate_global_setting((2, 51, 7), old)
    assert old["application"]["rail_items"].count("race_schedule_viewer") == 1


# Your online races (results files)
def row(position: int, name: str, laps: tuple[float, ...] = ()) -> rs.ResultRow:
    return rs.ResultRow(position, position, position, name, "Ligier JS P325", "LMP3", str(position), "Team", 100.0,
                        1800.0, 4, "Finished Normally", laps, tuple(position for _lap in laps), (name,))


def result(number: int, when: float) -> rs.OnlineResult:
    return rs.OnlineResult(f"race-{number}.xml", when, "LMP3 Fixed", "PortimaoWEC",
                           (row(1, "Keenny Hess", (101.0, 100.0)), row(2, "Other", (102.0, 101.0))))


@pytest.fixture
def online(ui_env, fresh_info, monkeypatch):
    from neopedal.ui.quick.online_results import OnlineResultsBackend

    monkeypatch.setattr(info, "player_name", lambda: "Keenny Hess")
    monkeypatch.setattr(info, "_state", info.State(schedule(NOW), info.PUBLIC, time.monotonic(), 1))
    backend = OnlineResultsBackend(None)
    yield backend
    backend.release()


def wait_online(backend):
    for _ in range(150):
        pump(0.02)
        if not backend.state["loading"] and not backend.jobs.is_busy("laps"):
            return


def test_online_results_list_and_race(online, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    asked = []

    def read_results(page=1):
        asked.append(page)
        found = info.ResultsPage([result(1, NOW - 86400)] * info.RESULTS_TAKE if page == 1
                                 else [result(0, NOW - 3 * 86400)])
        found.answered = len(found)
        return found

    monkeypatch.setattr(info, "read_results", read_results)
    online.list_shown(True)
    wait_online(online)
    assert asked == [1] and len(online.rows) == 1 and online.state["more"]
    assert online.selected["title"] == "LMP3 Fixed" and online.chart["laps"] == 2  # laps of the file
    online.more()
    wait_online(online)
    assert len(online.rows) == 2 and not online.state["more"]
    assert online.summary["figures"][0]["value"] == "2"  # wins
    path = tmp_path / "race.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(path), ""))
    online.exportClassification()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0].endswith(",Laps,Status") and lines[1].startswith("1,1,LMP3,1,Keenny Hess")
    wanted = []
    online.sessionWanted.connect(wanted.append)
    online.openLocal()
    assert wanted == [] and online.state["note"]  # results file gone: told
    race = tmp_path / "race-1.xml"
    race.write_text("", encoding="utf-8")
    online._results[0] = online._results[0]._replace(path=str(race))
    online.select(f"result/{race}")
    online.openLocal()
    assert wanted == [str(race)]  # the race is that results file


def test_results_page_online_list(qml_warnings, ui_env, fresh_info, monkeypatch):  # noqa: F811
    from neopedal.ui.race_results_viewer import RaceResultsViewer

    monkeypatch.setattr(info, "player_name", lambda: "Keenny Hess")
    monkeypatch.setattr(info, "read_results", lambda page=1: info.ResultsPage(
        [result(1, NOW - 86400)] if page == 1 else []))
    monkeypatch.setattr(info, "read_result", lambda path: None)
    viewer = RaceResultsViewer(None)
    viewer.resize(1300, 850)
    viewer.show()
    pump(0.3)
    try:
        viewer.show_online()
        wait_online(viewer.online)
        root = viewer.view.rootObject()
        assert viewer.backend.listMode == 2 and len(viewer.online.rows) == 1
        assert item_named(root, "onlineResultView").isVisible()
        assert item_named(root, "onlineClassification").isVisible()
        assert not qml_warnings, qml_warnings
    finally:
        viewer.close()
        pump(0.1)
