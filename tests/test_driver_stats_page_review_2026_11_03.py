"""Driver Stats page review 2026-11-03: fuel of imported sessions, one "no value" mark, empty cars hidden & cleaned
up, races of results files, empty columns, activity period, rank line scale, sheet date, rival names, ranks
refresh, lap times of race results completed once"""

from datetime import datetime, timedelta

import pytest
from PySide6.QtCore import QCoreApplication

from neopedal.process import driver_ranks as dr
from neopedal.process import results_file as rf
from neopedal.process import results_index as ri
from neopedal.process.results_text import MISSING
from neopedal.setting import cfg
from neopedal.ui.quick import stats_analysis, stats_common
from neopedal.ui.quick.formatting import sheet_date_text
from neopedal.ui.quick.stats_overview import display_name
from neopedal.userfile import driver_history
from neopedal.userfile.driver_history import SessionRecord
from tests.test_driver_stats_viewer import (  # noqa: F401  (fixtures)
    OREGA,
    SPA,
    STATS,
    backend,
    dialogs,
    load_stats,
    settle,
    window,
    write_stats,
)

EMPTY = {"pb": 99999.0, "starts": 1}  # car loaded then left: nothing to show


def summary(**values) -> ri.ResultSummary:
    base = {"path": "race.xml", "game": "LMU", "start": 1_700_000_000.0, "end": 1_700_003_000.0, "kind": "Race",
            "code": "R", "track": SPA, "venue": "", "game_version": "1.42", "setting": "Multiplayer", "server": "",
            "cars": 20, "class_cars": 10, "driver": "Me", "vehicle": "", "car": "", "car_class": "LMP2",
            "position": 5, "class_position": 1, "status": rf.FINISHED, "best_lap": 120.0, "laps": 20, "gap_laps": 0,
            "gap_time": 1.0, "contacts": 0, "impacts": 0, "penalties": 0, "track_limits": 0.0}
    base.update(values)
    return ri.ResultSummary(**base)


# --- 1. Consumption: distance of sessions imported from results files (no fuel) left out
def test_consumption_leaves_out_imported_distance(backend, monkeypatch):  # noqa: F811
    imported = SessionRecord(1_700_003_000.0, SPA, OREGA, 4, 0.0, valid=10, meters=30000.0)  # ends at session end
    recorded = SessionRecord(1_700_100_000.0, SPA, OREGA, 1, 121.5, valid=20, meters=20000.0)
    driver_history.save_history(cfg.path.config, [imported, recorded])
    backend.reload_stats()
    settle(backend)
    race = summary()
    monkeypatch.setattr(backend, "record_result", lambda record: race if record == imported else None)
    backend.selectTrack(SPA)
    backend.refresh_table()
    # 20 L over the 20 km recorded with fuel (not 50 km): 100 L/100 km
    assert backend.cell(OREGA, "consumption").value == pytest.approx(100.0)
    assert backend.cell("Hyper - Ferrari", "liters").text == MISSING  # no fuel recorded: no "0.00"


# --- 2, 3, 7. One mark for no value, empty cars hidden, empty columns left out
def test_empty_cars_hidden_and_empty_columns_left_out(backend):  # noqa: F811
    write_stats({**STATS, SPA: {**STATS[SPA], " - Ferrari": EMPTY}, "Empty Track": {"GT3 - BMW": EMPTY}})
    backend.reload_stats()
    settle(backend)
    backend.selectTrack(SPA)
    assert " - Ferrari" not in backend.row_keys() and backend.trackInfo["subtitle"].startswith("2 vehicles")
    keys = [column["key"] for column in backend.columns]
    assert "theory" not in keys and "wet_pb" not in keys  # no sector best, no wet session
    assert backend.cell("Hyper - Ferrari", "gap").text in (MISSING,) or "%" in backend.cell("Hyper - Ferrari", "gap").text
    assert all(cell.text != "-" for _, cells in backend._table for cell in cells.values())
    backend.selectTrack("")
    assert "Empty Track" not in backend.row_keys() and backend.trackInfo["subtitle"].startswith("2 tracks")


# --- 4. Clean up: empty cars removed with their history, impossible lap times reset, undone
def test_clean_up_removes_empty_cars_and_impossible_lap_times(backend):  # noqa: F811
    write_stats({**STATS, SPA: {**STATS[SPA], " - Ferrari": EMPTY,
                                "Hyper - BMW": {"pb": 36759.652, "valid": 1, "meters": 6000.0}}})
    driver_history.save_history(cfg.path.config, [SessionRecord(1_700_000_000.0, SPA, " - Ferrari", 1, 0.0)])
    backend.reload_stats()
    settle(backend)
    backend.cleanUpStats()
    settle(backend)
    saved = load_stats()
    assert " - Ferrari" not in saved[SPA] and saved[SPA]["Hyper - BMW"]["pb"] == 99999.0
    assert not [record for record in driver_history.load_history(cfg.path.config) if record.vehicle == " - Ferrari"]
    backend.undo()
    settle(backend)
    assert " - Ferrari" in load_stats()[SPA]
    assert stats_common.clean_up_stats({SPA: {"V": EMPTY}}) == ({(SPA, "V")}, 0)


# --- 5. Races of All Tracks: game results files, as the driver card (which no longer repeats them)
def test_career_races_from_results_files(backend):  # noqa: F811
    backend.results = [summary(path="a.xml"), summary(path="b.xml", class_position=3),
                       summary(path="c.xml", kind="Qualify")]
    backend._results_serial += 1
    backend.selectTrack("")
    backend.refresh_table()
    races = next(tile for tile in backend.tiles if tile["title"] == "Races")
    assert races["value"] == "2" and races["detail"] == "1 win · 2 podiums" and "results files" in races["tip"]
    labels = [figure["label"] for figure in backend.driver_data()["figures"]]
    assert "Races" not in labels and "Avg. Finish" in labels


# --- 11. Activity of the last 12 months starts at the week of the first session (26 weeks at least)
def test_activity_from_first_session_week(backend):  # noqa: F811
    first = datetime.now() - timedelta(days=200)
    driver_history.save_history(cfg.path.config, [SessionRecord(first.timestamp(), SPA, OREGA, 1, 121.5,
                                                                seconds=600.0)])
    backend.reload_stats()
    settle(backend)
    backend.selectTrack("")
    weeks = backend.activity_data()["weeks"]
    assert 26 <= weeks <= 31 and weeks < stats_common.ACTIVITY_WEEKS


# --- 12. Rank line over the tiers reached
def test_rank_line_scaled_to_tiers_reached():
    history = [dr.HistoryEntry(1.0, dr.Rank("Silver", 2, 40), dr.Rank("Platinum", 3, 100)),
               dr.HistoryEntry(2.0, dr.Rank("Silver", 2, 25), dr.Rank("Platinum", 3, 100))]
    driver = stats_analysis.rank_chart(history, "driver")
    assert [point["y"] for point in driver] == [pytest.approx(0.40), pytest.approx(0.25)]
    assert all(0 <= point["y"] <= 1 for point in stats_analysis.rank_chart(history, "safety"))  # top tier: no /0


# --- 13, 14. Sheet date as app dates, rival names without their number
def test_sheet_date_and_rival_names():
    assert sheet_date_text("2026.10.30. 08:48 CEST") == f"{stats_common.format_date(datetime(2026, 10, 30, 12).timestamp())} 08:48 CEST"
    assert sheet_date_text("soon") == "soon"
    assert [display_name(name) for name in ("Paul Atreides#2773", "Nigel Wood", "#123")] == [
        "Paul Atreides", "Nigel Wood", "#123"]


# --- 17. Ranks read again on demand, a few minutes apart
def test_ranks_read_now_rate_limited():
    clock = [1000.0]
    watcher = dr.RankWatcher(lambda: dr.Located("", "", ()), clock=lambda: clock[0])
    assert watcher.read_now() and watcher._online_due == [1000.0]
    assert not watcher.read_now()  # asked again at once: refused
    clock[0] += dr.ONLINE_MANUAL_SECONDS
    assert watcher.read_now()


# --- 19. Lap times of race results completed at once, each once (an undo keeps it out)
def test_lap_times_of_results_completed_once(backend, monkeypatch):  # noqa: F811
    monkeypatch.setattr(backend, "_page_visible", True)
    fix = ri.BestLapFix(SPA, OREGA, "pb", 120.9, 121.5, "race.xml", 1_700_003_000.0)
    backend._fixes = [fix]
    backend.auto_complete()
    settle(backend)
    assert load_stats()[SPA][OREGA]["pb"] == pytest.approx(120.9)
    backend.undo()
    settle(backend)
    assert load_stats()[SPA][OREGA]["pb"] == pytest.approx(121.5)
    backend._fixes = [fix]
    backend.auto_complete()  # undone: never taken again on its own
    settle(backend)
    for _ in range(3):
        QCoreApplication.processEvents()
    assert load_stats()[SPA][OREGA]["pb"] == pytest.approx(121.5)


def test_results_clock_jump_never_completed():
    """LMU writes the 10 h "lap" of a disqualified race in its results file too: never a lap time to complete"""
    stats = {SPA: {OREGA: {"pb": 121.5}}}
    jump = summary(best_lap=36759.652, car_class="LMP2_ELMS", vehicle="Oreca 07", car="Oreca 07")
    assert ri.best_lap_fixes([jump], stats, {"race.xml": OREGA}, "Class - Brand", {}) == []
