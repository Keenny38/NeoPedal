"""Driver stats completed from a mysimrace.com data export (process/mysimrace_import.py, Driver Stats "⋯" menu)"""

import json

import pytest

from neopedal.process import mysimrace_import as mi
from neopedal.process import results_import
from neopedal.setting import cfg
from neopedal.userfile import driver_history
from neopedal.userfile.driver_history import SessionRecord
from tests.test_driver_stats_viewer import (  # noqa: F401  (fixtures)
    OREGA,
    SPA,
    STATS,
    backend,
    dialogs,
    page,
    settle,
    window,
)
from tests.test_results_links import summary

SARTHE = "Circuit de la Sarthe"
ATLANTA = "Michelin Raceway Road Atlanta"
GARBAGE = b"Ht\xef\xbf\xbd\xdb\x82?M\\u0016\xb5"  # compound field of exports: bytes that are not UTF-8


def export_lap(recorded_at, laptime_ms, track="Circuit de la Sarthe (24H)", car="ORECA 07 Gibson",
               car_class="LMP2_ELMS", session="Practice", compound=""):
    return {"lap_time_ms": laptime_ms, "sector1_ms": 1, "sector2_ms": 1, "sector3_ms": laptime_ms - 2,
            "fuel_percent": "0.00", "tire_compound": compound, "air_temp": "21.0", "track_temp": "30.0",
            "weather": None, "session_type": session, "recorded_at": recorded_at, "track_name": track,
            "car_name": car, "car_class": car_class}


LAPS = [
    # Practice at Le Mans: 3 laps, a pit stop of 20 min between
    export_lap("2026-08-01 20:00:00", 210_000),
    export_lap("2026-08-01 20:03:30", 207_500, compound="Medium"),
    export_lap("2026-08-01 20:27:00", 208_000),
    # Qualifying right after: a session of its own
    export_lap("2026-08-01 20:40:00", 206_900, session="Qualify"),
    # Race at Road Atlanta the next day
    export_lap("2026-08-02 21:00:00", 71_500, track=ATLANTA, car="Ferrari 499P", car_class="Hypercar",
               session="Race"),
    export_lap("2026-08-02 21:01:12", 71_250, track=ATLANTA, car="Ferrari 499P", car_class="Hypercar",
               session="Race"),
]


def write_export(tmp_path, laps=LAPS, name="mysimrace_data_1_2026-11-02.json") -> str:
    path = tmp_path / name
    text = json.dumps({"profil": {"id": 1, "pilot_name": "Me"}, "temps_au_tour": laps, "messages": []})
    path.write_text(text, encoding="utf-8")
    return str(path)


def at(text: str) -> float:
    return mi.parse_time(text)


def test_read_export_keeps_laps_of_le_mans_ultimate(tmp_path):
    other = export_lap("2026-08-03 10:00:00", 90_000, track="Nordschleife", car="Some Car", car_class="TCR")
    broken = {**export_lap("2026-08-03 10:02:00", 90_000), "lap_time_ms": "fast"}
    jump = export_lap("2026-08-03 10:04:00", 36_759_652)  # game clock jump (LMU DQ): never a lap
    path = tmp_path / "export.json"
    data = json.dumps({"temps_au_tour": [*LAPS, other, broken, jump]}).encode("utf-8")
    path.write_bytes(data.replace(b'"tire_compound": ""', b'"tire_compound": "' + GARBAGE + b'"', 1))
    laps, left_out = mi.read_export(str(path))
    assert len(laps) == len(LAPS) and left_out == 3
    assert laps[0] == mi.ExportLap(at("2026-08-01 20:00:00"), 210.0, "Circuit de la Sarthe (24H)",
                                   "ORECA 07 Gibson", "LMP2_ELMS", 1, "")  # garbage compound dropped
    assert laps[1].compound == "Medium" and laps[3].session == 2 and laps[4].car_class == "Hyper"


@pytest.mark.parametrize("content", [b"not json", b"[]", b'{"temps_au_tour": {}}', b'{"laps": []}',
                                     b'{"temps_au_tour": []}'])
def test_read_export_refuses_other_files(tmp_path, content):
    path = tmp_path / "other.json"
    path.write_bytes(content)
    with pytest.raises(ValueError):
        mi.read_export(str(path))


def test_sessions_split_by_session_type_track_car_and_long_gaps():
    laps = [lap for lap in map(mi.parse_lap, LAPS) if lap is not None]
    late = laps[0]._replace(end=laps[2].end + mi.SESSION_GAP + 300)
    groups = mi.group_sessions([*laps, late])
    assert [len(group) for group in groups] == [3, 1, 1, 2]  # later lap of a new session sorted in time


def test_export_sessions_named_as_stats_keys_with_track_length():
    laps = [lap for lap in map(mi.parse_lap, LAPS) if lap is not None]
    stats_user = {SARTHE: {"LMP2_ELMS - Oreca": {"pb": 205.0, "valid": 4}}}
    found = mi.export_sessions(laps, "export.json", stats_user, [], [], "Class - Brand", ["Ferrari"],
                               lengths={SARTHE.casefold(): 13624.0})
    assert (found.recorded, found.in_results) == (0, 0)
    records = [session.record for session in found.sessions]
    assert [(record.track, record.vehicle, record.session) for record in records] == [
        (SARTHE, "LMP2_ELMS - Oreca", 1), (SARTHE, "LMP2_ELMS - Oreca", 2), (ATLANTA, "Hyper - Ferrari", 4)]
    practice, qualifying, race = found.sessions
    assert practice.record.best == 207.5 and practice.record.compound == "Medium"
    assert practice.record.valid == 3 and practice.record.invalid == 0 and practice.record.seconds == 625.5
    assert practice.record.meters == 3 * 13624.0 and practice.record.time == at("2026-08-01 20:27:00")
    assert practice.record.vehicle_class == "LMP2_ELMS" and practice.record.online == -1
    assert (practice.stats.pb, practice.stats.qb, practice.stats.rb) == (207.5, 99999.0, 99999.0)
    assert qualifying.stats.qb == 206.9 and race.stats.rb == 71.25
    assert race.record.meters == 0.0  # no results file of the track: distance unknown
    assert race.stats.starts == 0 and race.record.finish == 0  # race result not in export
    by_class = mi.export_sessions(laps, "export.json", {}, [], [], "Class", [], lengths={})
    assert [session.record.vehicle for session in by_class.sessions] == ["LMP2_ELMS", "LMP2_ELMS", "Hyper"]


def test_export_sessions_never_add_recorded_nor_results_sessions():
    laps = [lap for lap in map(mi.parse_lap, LAPS) if lap is not None]
    stint = SessionRecord(at("2026-08-01 20:45:00"), SARTHE, "LMP2_ELMS - Oreca", 2)  # stint end after qualifying
    results = summary(game="LMU", start=at("2026-08-02 20:55:00"), end=at("2026-08-02 21:30:00"))
    found = mi.export_sessions(laps, "export.json", {}, [stint], [results], "Class - Brand", [], lengths={})
    assert [session.record.session for session in found.sessions] == [1]  # practice only
    assert (found.recorded, found.in_results) == (1, 1)


def test_export_sessions_added_as_results_import_adds_them():
    laps = [lap for lap in map(mi.parse_lap, LAPS) if lap is not None]
    stats_user = {SARTHE: {"LMP2_ELMS - Oreca": {"pb": 205.0, "qb": 99999.0, "valid": 4, "seconds": 900.0}}}
    history = [SessionRecord(at("2026-09-01 20:00:00"), SARTHE, "LMP2_ELMS - Oreca", 1, 205.0, valid=4)]
    found = mi.export_sessions(laps, "export.json", stats_user, history, [], "Class - Brand", [], lengths={})
    added = results_import.apply_import(stats_user, history, found.sessions)
    assert len(added) == 3
    oreca = stats_user[SARTHE]["LMP2_ELMS - Oreca"]
    assert oreca["pb"] == 205.0 and oreca["qb"] == 206.9 and oreca["valid"] == 8
    assert stats_user[ATLANTA]["Hyper - Ferrari"]["rb"] == 71.25


# Driver Stats page: "⋯" menu, Import From mysimrace…
@pytest.fixture
def chosen_file(monkeypatch):
    from neopedal.ui.quick import stats_edits

    chosen = {"path": ""}
    monkeypatch.setattr(stats_edits.QFileDialog, "getOpenFileName", lambda *args, **kwargs: (chosen["path"], ""))
    return chosen


def test_page_imports_mysimrace_export_then_undo(backend, chosen_file, tmp_path, monkeypatch):  # noqa: F811
    toasts = []
    monkeypatch.setattr(type(backend), "toast", lambda self, text: toasts.append(text))
    monkeypatch.setattr(type(backend), "toast_undo", lambda self, text: toasts.append(text))
    settle(backend)
    driver_history.save_history(cfg.path.config, [])
    backend.reload_stats()
    settle(backend)
    chosen_file["path"] = write_export(tmp_path)
    backend.importMysimrace()
    settle(backend)
    assert toasts[-1] == "3 session(s) imported from mysimrace"
    with open(f"{cfg.path.config}driver.stats", encoding="utf-8") as file:
        saved = json.load(file)
    assert saved[SARTHE]["LMP2_ELMS - Oreca"]["valid"] == 4 and saved[ATLANTA]["Hyper - Ferrari"]["valid"] == 2
    assert saved[SPA][OREGA] == STATS[SPA][OREGA]  # other stats kept
    assert len(driver_history.load_history(cfg.path.config)) == 3
    backend.importMysimrace()  # same file again: nothing added twice
    settle(backend)
    assert toasts[-1] == "Nothing to import: the sessions of this file are already in your stats"
    assert len(driver_history.load_history(cfg.path.config)) == 3
    backend.undo()
    settle(backend)
    with open(f"{cfg.path.config}driver.stats", encoding="utf-8") as file:
        assert not json.load(file).get(ATLANTA)
    assert driver_history.load_history(cfg.path.config) == []


def test_page_tells_when_file_is_not_an_export(backend, chosen_file, tmp_path, monkeypatch):  # noqa: F811
    toasts = []
    monkeypatch.setattr(type(backend), "toast", lambda self, text: toasts.append(text))
    settle(backend)
    path = tmp_path / "other.json"
    path.write_text('{"name": "not an export"}', encoding="utf-8")
    chosen_file["path"] = str(path)
    backend.importMysimrace()
    settle(backend)
    assert toasts == ["This file is not a mysimrace data export with laps of Le Mans Ultimate"]
    with open(f"{cfg.path.config}driver.stats", encoding="utf-8") as file:
        assert json.load(file) == STATS
    chosen_file["path"] = ""  # dialog cancelled: nothing done
    backend.importMysimrace()
    settle(backend)
    assert len(toasts) == 1


def test_qml_more_menu_offers_mysimrace_import(page):  # noqa: F811
    from PySide6.QtCore import QObject

    page.show()
    settle(page.backend)
    action = page.view.rootObject().findChild(QObject, "statsImportMysimrace")
    assert action is not None and action.property("text") == "Import From mysimrace…"
    assert action.property("enabled") is True
