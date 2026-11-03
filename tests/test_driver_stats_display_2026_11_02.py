"""Driver Stats display fixes of 2026-11-02: lap time of a game clock jump (LMU DQ: a "valid" lap of 10 h)
never a best lap, nor shown as one"""

import json
import os

import pytest

from neopedal.const_common import MAX_LAPTIME
from neopedal.module import module_stats
from neopedal.module_info import StatsInfo
from neopedal.process import results_index as ri
from neopedal.ui.quick import stats_common
from neopedal.ui.quick.stats_analysis import weekly_progress
from neopedal.ui.quick.stint_analysis import best_by_class
from neopedal.userfile import driver_stats
from neopedal.userfile.driver_history import SessionRecord, parse_record, session_record
from tests.test_lap_reference import viewer  # noqa: F401
from tests.test_module_mapping_stats_notes import drive_stats_lap, stats_env, tele  # noqa: F401
from tests.test_results_links import summary as results_summary

JUMP = 36759.652  # best lap of a record written after an LMU disqualification (10 h 12 min)
NOW = 1_793_400_000.0
TRACK = "Michelin Raceway Road Atlanta"


def test_history_record_with_clock_jump_has_no_best_lap():
    data = {"time": NOW, "track": TRACK, "vehicle": "Hyper - BMW", "session": 4, "best": JUMP, "valid": 1,
            "seconds": 209.45, "finish": 3}
    record = parse_record(data)
    assert record is not None and record.best == 0.0
    assert record.valid == 1  # the rest of the record kept
    assert parse_record({**data, "best": 71.25}).best == pytest.approx(71.25)
    assert session_record(track=TRACK, vehicle="Hyper - BMW", session=4, best=JUMP, valid=1, invalid=0,
                          meters=6497.0, seconds=209.0, position=0, finish=3, time=NOW).best == 0.0


def test_stats_lap_time_longer_than_any_lap_shown_as_none():
    assert stats_common.valid_laptime(JUMP) == 0.0
    assert stats_common.valid_laptime(MAX_LAPTIME - 1) == MAX_LAPTIME - 1
    assert stats_common.parse_display_value("pb", JUMP) == stats_common.MISSING
    assert stats_common.parse_display_value("pb", 85.2) != stats_common.MISSING


def test_week_progress_never_shows_clock_jump_as_first_lap_time():
    records = [SessionRecord(NOW - 3600, TRACK, "Hyper - BMW", 4, JUMP, valid=1, seconds=209.0)]
    items = weekly_progress(records, {}, NOW)
    assert [item["kind"] for item in items] == ["summary"]  # driving counted, no "record" row


def test_clock_jump_lap_never_recorded_as_best(stats_env):  # noqa: F811
    telemetry, filepath = stats_env
    gen = module_stats.record_driver_stats(StatsInfo(), filepath, "Class", max_moved_distance=1500,
                                           podium_by_class=False)
    gen.send(1)
    telemetry["vehicle.position_xyz"] = (0.0, 0.0, 0.0)
    drive_stats_lap(telemetry, gen, 0.0, MAX_LAPTIME + 100)
    gen.send(2)  # saved on reset
    stats = driver_stats.load_driver_stats(("SimTrack", "GT3"), filepath)
    assert stats.valid == 1
    assert stats.pb == driver_stats.DriverStats().pb  # no personal best


# Clock jump lap time already saved in stats files (versions until 0.28.1): read as no lap time, replaced on save


def write_stats(tmp_path, stats: dict) -> str:
    folder = f"{tmp_path}{os.sep}"
    with open(f"{folder}driver.stats", "w", encoding="utf-8") as file:
        json.dump(stats, file)
    return folder


def test_saved_clock_jump_lap_time_loaded_as_none(tmp_path):
    folder = write_stats(tmp_path, {TRACK: {"Hyper - BMW": {"pb": 71.748, "rb": JUMP, "qb": 99999.0, "valid": 3}}})
    stats = driver_stats.load_driver_stats((TRACK, "Hyper - BMW"), folder)
    assert stats.pb == pytest.approx(71.748)
    assert stats.rb == driver_stats.DriverStats().rb and stats.qb == driver_stats.DriverStats().qb
    assert stats.valid == 3
    checked = driver_stats.validate_stats_file({TRACK: {"Hyper - BMW": {"pb": JUMP, "rb": 72.5, "qb": 99999.0}}})
    assert checked[TRACK]["Hyper - BMW"] == {"pb": 99999.0, "rb": 72.5, "qb": 99999.0}


def test_saved_clock_jump_lap_time_replaced_by_next_save(tmp_path):
    folder = write_stats(tmp_path, {TRACK: {"Hyper - BMW": {"pb": JUMP, "rb": JUMP, "valid": 1}}})
    driver_stats.save_driver_stats((TRACK, "Hyper - BMW"), driver_stats.DriverStats(rb=80.25, valid=1), folder)
    with open(f"{folder}driver.stats", encoding="utf-8") as file:
        saved = json.load(file)[TRACK]["Hyper - BMW"]
    assert saved["rb"] == pytest.approx(80.25)  # a lap slower than the jump still saved
    assert saved["pb"] == driver_stats.DriverStats().pb  # no lap time: none
    assert saved["valid"] == 2


def test_clock_jump_lap_time_never_kept_by_merges():
    assert driver_stats.best_lap_time(JUMP, 0) == 0.0
    assert driver_stats.best_lap_time(JUMP, 75.0) == 75.0
    assert driver_stats.merge_vehicle_stats({"rb": JUMP}, {"rb": 75.0})["rb"] == 75.0
    assert driver_stats.stats_since({TRACK: {"V": {"pb": JUMP}}}, {TRACK: {"V": {"pb": 99999.0}}}) == {}
    assert best_by_class({TRACK: {"Hyper - BMW": {"pb": JUMP}, "Hyper - Ferrari": {"pb": 72.0}}}, TRACK,
                         lambda vehicle: "Hyper") == {"Hyper": 72.0}


def test_results_best_lap_fix_never_shows_clock_jump_as_current():
    stats = {"24 Heures du Mans": {"Hyper - Toyota": {"pb": JUMP, "rb": JUMP}}}
    lmu = results_summary(game="LMU", car="Toyota GR010", vehicle="Car A #1")
    fixes = ri.best_lap_fixes([lmu], stats, {}, "Class - Brand", {})
    assert [(fix.stat, fix.current) for fix in fixes] == [("pb", 0.0), ("rb", 0.0)]


# --- Automatic lap time goal: limit of next level of community lap times, level reached told once
SPA_E = "Circuit de Spa-Francorchamps Endurance"
OREGA_E = "LMP2_ELMS - Oreca"


def test_automatic_goal_is_next_level(viewer):  # noqa: F811
    viewer.selectRow(OREGA_E)
    goal = viewer.goal
    # Personal best 2:01.500 Competitive (sheet: Alien up to 2:01.08)
    assert goal["set"] and goal["auto"] and goal["time"] == "2:01.080" and goal["source"].endswith("Alien")
    assert goal["gap"] == "+0.420 s to find" and goal["gapColor"] == "loss"
    viewer.set_goal(f"{SPA_E}|{OREGA_E}", 121.3)  # own goal wins
    assert not viewer.goal["auto"] and viewer.goal["time"] == "2:01.300" and viewer.goal["source"] == ""
    viewer.clearGoal()  # automatic again
    assert viewer.goal["auto"] and viewer.goal["time"] == "2:01.080"


def test_level_reached_told_once(viewer, monkeypatch):  # noqa: F811
    import json

    from neopedal.setting import cfg
    from neopedal.ui import toast
    from tests.test_lap_reference import wait_jobs

    toasts = []
    monkeypatch.setattr(toast, "show_toast", lambda host, text, **kwargs: toasts.append(text))
    monkeypatch.setattr(viewer, "_page_visible", True)
    viewer.check_goals()
    assert viewer.goal_levels()[f"{SPA_E}|{OREGA_E}"] == 1 and not toasts  # first seen: kept silently
    stats = {SPA_E: {OREGA_E: {"pb": 121.0}, "Hyper - Ferrari": {"pb": 119.0}, "Oreca 07": {"pb": 125.0}}}
    with open(f"{cfg.path.config}driver.stats", "w", encoding="utf-8") as file:
        json.dump(stats, file)
    viewer.reload_stats()
    wait_jobs(viewer)
    assert len(toasts) == 1 and "Level reached" in toasts[0] and "Alien" in toasts[0] and "2:01.000" in toasts[0]
    viewer.reload_stats()
    wait_jobs(viewer)
    assert len(toasts) == 1  # told once
    viewer.selectTrack(SPA_E)
    viewer.selectRow(OREGA_E)
    assert viewer.goal["auto"] and viewer.goal["time"] == "2:00.500"  # best level: personal best - 0.5 s
