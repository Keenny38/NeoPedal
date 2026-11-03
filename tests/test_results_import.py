"""Driver stats completed from game results files (process/results_import.py): laps counted as the stats
module counts them, sessions never recorded found, never counted twice, import & undo from the driver card"""

import json

import pytest

from neopedal.process import results_file as rf
from neopedal.process import results_import as imp
from neopedal.process import results_index as ri
from neopedal.setting import cfg
from neopedal.userfile import driver_history
from neopedal.userfile.driver_history import SessionRecord
from neopedal.userfile.driver_stats import DriverStats
from tests.test_driver_stats_viewer import (  # noqa: F401  (fixtures)
    OREGA,
    SPA,
    STATS,
    backend,
    dialogs,
    item_texts,
    page,
    settle,
    window,
)
from tests.test_race_results import RACE_NAME, RACE_XML
from tests.test_results_links import results_data

END = 1_790_001_000.0  # results file written
SARTHE = "Circuit de la Sarthe"


def lap(number, time=0.0, start=-1.0, sectors=(0.0, 0.0, 0.0), pit=False) -> rf.Lap:
    return rf.Lap(number, 1, time, start, sectors, 0.0, "Medium", pit, -1.0, -1.0, -1.0, -1.0, ())


def entry(laps, **changes) -> rf.Entry:
    values = {"name": "Me", "team": "", "vehicle": "Car #1", "car": "Ferrari 499P", "car_class": "Hyper",
              "number": "1", "grid": 0, "position": 1, "class_grid": 0, "class_position": 1,
              "laps_completed": len(laps), "best_lap": 0.0, "finish_time": 0.0, "pitstops": 0, "status": "None",
              "dnf_reason": "", "human": True, "player": True, "aids": "", "laps": tuple(laps), "swaps": ()}
    return rf.Entry(**{**values, **changes})


# Laps counted as the stats module counts them
def test_practice_laps_out_valid_invalidated_and_back_to_garage():
    laps = [
        lap(1),  # placeholder: out lap from garage, start unknown
        lap(2, 100.0, 500.0, (30.0, 40.0, 30.0)),
        lap(3, 0.0, 600.0, (30.0, 40.0, 0.0)),  # track limits: invalid, completed (next lap)
        lap(4, 99.0, 702.0, (30.0, 39.0, 30.0)),
        lap(5, 0.0, 801.0, (31.0, 0.0, 0.0)),  # left on track (back to garage)
    ]
    counts = imp.count_laps(entry(laps), laps, 100.0)
    assert (counts.valid, counts.invalid) == (2, 1)
    assert counts.best is not None and counts.best.time == 99.0
    assert counts.seconds == pytest.approx(100 + 100 + 102 + 99 + 31)  # out lap: usual lap time
    assert counts.laps == pytest.approx(1 + 1 + 1 + 1 + 1 / 3)


def test_restart_and_session_joined_late_not_counted_as_laps():
    laps = [
        lap(1, 36759.0, 100.0, (16.0, 36700.0, 40.0)),  # joined late: not a lap time
        lap(2, 0.0, 36860.0, (0.0, 0.0, 0.0)),  # out lap: time spent capped to usual lap time
        lap(3, 0.0, 37000.0, (30.0, 0.0, 0.0)),  # restart 10 s later: not completed
        lap(4, 98.0, 37010.0, (30.0, 38.0, 30.0)),
    ]
    counts = imp.count_laps(entry(laps), laps, 100.0)
    assert (counts.valid, counts.invalid) == (1, 1)  # time far over usual lap time: invalid lap
    assert counts.seconds < 1000  # never the hours of the bad lap time


def test_pit_lap_never_counted_invalid():
    laps = [lap(1, 0.0, 0.0, (30.0, 40.0, 0.0), pit=True), lap(2, 100.0, 120.0, (30.0, 40.0, 30.0))]
    assert imp.count_laps(entry(laps), laps, 100.0).invalid == 0


def test_reference_lap_median_else_track_length():
    result = rf.parse_results(RACE_XML.encode("utf-8"), RACE_NAME, ["alice driver"])
    assert imp.reference_lap(result) == pytest.approx(100.0)  # best laps 97.9, 100.0, 110.0
    untimed = result._replace(entries=tuple(car._replace(best_lap=0.0) for car in result.entries))
    assert imp.reference_lap(untimed) == pytest.approx(13626.0 / imp.LAP_SPEED)


# Keys as the stats module makes them
def summary(**changes) -> ri.ResultSummary:
    result = rf.parse_results(RACE_XML.encode("utf-8"), f"c:/Le Mans Ultimate/UserData/Log/Results/{RACE_NAME}",
                              ["alice driver"])
    found = ri.summarize(result, END, ["alice driver"])
    assert found is not None
    return found._replace(**changes)


@pytest.mark.parametrize(("classification", "brands", "key"), [
    ("Class", {}, "Hyper"),
    ("Class - Brand", {}, "Hyper - Toyota"),
    ("Class - Brand", {"Car A #1": "Toyota Gazoo"}, "Hyper - Toyota Gazoo"),
    ("Vehicle", {}, "Car A #1"),
])
def test_stats_keys(classification, brands, key):
    assert imp.stats_vehicle_key(summary(), classification, brands) == key
    assert imp.stats_track_key(summary()) == SARTHE  # layout, not event name
    assert imp.stats_vehicle_key(summary(car_class=""), "Class - Brand", {}) == ""  # never " - Brand"


def test_race_session_imported_with_own_laps_and_class_position():
    result = rf.parse_results(RACE_XML.encode("utf-8"), RACE_NAME, ["alice driver"])
    session = imp.import_session(result, summary(), ["alice driver"], "Class - Brand", {}, True)
    assert session is not None
    record, stats = session.record, session.stats
    assert (record.track, record.vehicle, record.session, record.vehicle_class) == (SARTHE, "Hyper - Toyota", 4, "Hyper")
    assert (stats.valid, stats.invalid) == (2, 0)  # lap 1 driven by teammate
    assert stats.pb == stats.rb == pytest.approx(97.9) and stats.qb == DriverStats().qb
    assert (stats.starts, stats.races, stats.wins, stats.podiums, stats.positions, stats.placed) == (1, 1, 1, 1, 1, 1)
    assert (record.position, record.finish, record.start_position, record.online) == (1, 1, 2, 1)
    assert record.time == END and record.game_version == "1.42" and record.compound == "Medium"
    assert stats.meters == pytest.approx(2 * 13626.0)


def test_retired_race_counts_start_and_dnf():
    result = rf.parse_results(RACE_XML.encode("utf-8"), RACE_NAME, ["alice driver"])
    session = imp.import_session(result, summary(status="DNF"), ["alice driver"], "Class", {}, False)
    assert session is not None
    assert (session.stats.starts, session.stats.races, session.stats.dnf, session.stats.wins) == (1, 0, 1, 0)
    assert session.record.finish == 2 and session.record.position == 0


# Sessions never recorded, never counted twice
def test_candidates_leave_out_recorded_linked_and_other_games():
    sessions = [
        summary(path="a.xml"),
        summary(path="linked.xml"),
        summary(path="rf2.xml", game="rFactor 2"),
        summary(path="nolap.xml", laps=0, best_lap=0.0),
        summary(path="recorded.xml", start=END + 5000, end=END + 6000),
        summary(path="other_track.xml", start=END + 5000, end=END + 6000, course="Monza", track="Monza", venue="Monza"),
    ]
    records = [SessionRecord(END + 6100, SARTHE, "Hyper - Ferrari", 1)]  # stint of "recorded.xml" (link missed)
    found = imp.import_candidates(sessions, records, ["linked.xml"])
    assert [found_summary.path for found_summary in found] == ["a.xml", "other_track.xml"]


def test_apply_import_merges_and_skips_stats_counted_before_history():
    stats_user = {SARTHE: {"Hyper - Toyota": {"pb": 97.0, "valid": 10, "seconds": 1000.0}},
                  "Monza": {"GT3 - BMW": {"pb": 110.0, "valid": 3}}}
    records = [SessionRecord(END + 100, "Monza", "GT3 - BMW", 1, valid=3)]  # Sarthe laps predate history
    old = imp.ImportedSession("old.xml", SessionRecord(END, SARTHE, "Hyper - Toyota", 1, valid=2),
                              DriverStats(pb=96.0, valid=2))
    monza = imp.ImportedSession("monza.xml", SessionRecord(END, "Monza", "GT3 - BMW", 4, valid=5),
                                DriverStats(pb=111.0, rb=111.0, valid=5, races=1))
    new = imp.ImportedSession("new.xml", SessionRecord(END, "Spa", "LMP2 - Oreca", 1, valid=1),
                              DriverStats(pb=130.0, valid=1))
    added = imp.apply_import(stats_user, records, [old, monza, new])
    assert added == [monza, new]
    assert stats_user[SARTHE]["Hyper - Toyota"] == {"pb": 97.0, "valid": 10, "seconds": 1000.0}
    assert stats_user["Monza"]["GT3 - BMW"]["valid"] == 8 and stats_user["Monza"]["GT3 - BMW"]["pb"] == 110.0
    assert stats_user["Monza"]["GT3 - BMW"]["rb"] == 111.0 and stats_user["Monza"]["GT3 - BMW"]["races"] == 1
    assert stats_user["Spa"]["LMP2 - Oreca"]["pb"] == 130.0


# Driver card: import & undo
@pytest.fixture
def lmu_results(tmp_path, monkeypatch):
    folder = tmp_path / "Le Mans Ultimate" / "UserData" / "Log" / "Results"
    folder.mkdir(parents=True)
    path = folder / RACE_NAME
    path.write_text(RACE_XML, encoding="utf-8")
    monkeypatch.setattr(ri, "player_names", lambda folders: {folder: ("alice driver",) for folder in folders})
    return summary(path=str(path))


def test_driver_card_imports_sessions_then_undo(backend, lmu_results):  # noqa: F811
    settle(backend)
    driver_history.save_history(cfg.path.config, [])
    backend.reload_stats()
    settle(backend)
    backend.results_loaded(results_data(lmu_results))
    backend.selectTrack("")
    assert backend.driver["imports"] == 1 and "1 session(s)" in backend.driver["importText"]
    backend.importResults()
    settle(backend)
    with open(f"{cfg.path.config}driver.stats", encoding="utf-8") as file:
        saved = json.load(file)
    assert saved[SARTHE]["Hyper - Toyota"]["valid"] == 2 and saved[SARTHE]["Hyper - Toyota"]["wins"] == 1
    assert saved[SPA][OREGA] == STATS[SPA][OREGA]  # other stats kept
    records = driver_history.load_history(cfg.path.config)
    assert [(record.track, record.vehicle, record.session) for record in records] == [(SARTHE, "Hyper - Toyota", 4)]
    backend.results_loaded(results_data(lmu_results))  # results read again after an edit (none in tests)
    assert backend.driver["imports"] == 0  # recorded now: never twice
    backend.undo()
    settle(backend)
    with open(f"{cfg.path.config}driver.stats", encoding="utf-8") as file:
        assert not json.load(file).get(SARTHE)
    assert driver_history.load_history(cfg.path.config) == []
    backend.results_loaded(results_data(lmu_results))
    assert backend.driver["imports"] == 1


def test_qml_driver_card_shows_import(page, lmu_results):  # noqa: F811
    from PySide6.QtCore import QCoreApplication

    page.resize(1400, 860)
    page.show()
    settle(page.backend)  # results of this computer read at first load (none in tests)
    page.backend.results_loaded(results_data(lmu_results))
    page.backend.selectTrack("")
    QCoreApplication.processEvents()
    assert page.backend.driver["imports"] == 1
    texts = item_texts(page.view)
    assert "1 session(s) of the game not in your stats" in texts and "Import…" in texts
