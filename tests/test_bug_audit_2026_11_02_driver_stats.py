"""Bug audit of Driver Stats (2026-11-02): recording, stats & history files, viewer page, Home debrief, DR/SR ranks

Files in tmp_path only, game data scripted, network never called.
"""

from __future__ import annotations

import builtins
import json
import os

import pytest

from neopedal import realtime_state
from neopedal.module import module_stats
from neopedal.module._base import MODULE_STOP
from neopedal.module_info import StatsInfo
from neopedal.userfile import driver_history, driver_stats
from neopedal.userfile.driver_stats import DriverStats
from tests.test_audit_pending_lap_files import (  # noqa: F401  fixtures: scripted game & clocks
    ModuleLoop,
    clock,
    drive_stats_lap,
    synchronous_saves,
    tele,
)

REAL_OPEN = builtins.open
# Driving: lap times not reported yet, moving at 50 m/s in qualifying
STINT_TELE = {
    "timing.start": 0.0, "timing.elapsed": 0.0, "timing.last_laptime": -1.0, "vehicle.speed": 50.0,
    "vehicle.position_xyz": (0.0, 0.0, 0.0), "engine.fuel": 50.0, "session.session_type": 2,
}


def read_stats(filepath: str) -> dict:
    with open(os.path.join(filepath, "driver.stats"), encoding="utf-8") as file:
        return json.load(file)


def hold_stats_file(monkeypatch, count: int) -> None:
    """driver.stats text reads fail count times (file held by antivirus or cloud sync), see release_stats_file"""
    real_open = builtins.open
    left = {"count": count}

    def held_open(file, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if str(file).endswith("driver.stats") and mode == "r" and left["count"] > 0:
            left["count"] -= 1
            raise PermissionError(13, "held by another program", str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", held_open)
    monkeypatch.setattr(driver_stats, "sleep", lambda seconds: None)


def release_stats_file(monkeypatch) -> None:
    """File no longer held (other patches of the test kept, unlike monkeypatch.undo)"""
    monkeypatch.setattr(builtins, "open", REAL_OPEN)


# B-001
def test_b001_stats_file_held_at_load_never_reset(tmp_path, monkeypatch):
    """File held longer than the load attempts: not saved (kept by caller), other tracks never lost"""
    filepath = f"{tmp_path}/"
    driver_stats.save_driver_stats(("Spa", "GT3"), DriverStats(valid=100, pb=130.0), filepath)
    driver_stats.save_driver_stats(("Monza", "GT3"), DriverStats(valid=50, pb=110.0), filepath)
    hold_stats_file(monkeypatch, 11)  # 10 attempts & last load
    saved = driver_stats.save_driver_stats(("Spa", "GT3"), DriverStats(valid=1), filepath)
    release_stats_file(monkeypatch)
    stats = read_stats(filepath)
    assert saved is False
    assert stats["Monza"]["GT3"]["valid"] == 50 and stats["Spa"]["GT3"]["valid"] == 100


def test_b006_stint_not_saved_kept_and_saved_with_next_stint(tele, tmp_path, clock, monkeypatch):  # noqa: F811
    """Stint stats not saved (file held): kept by the module, added to the next stint saved"""
    filepath = f"{tmp_path}/"
    driver_stats.save_driver_stats(("SimTrack", "GT3"), DriverStats(valid=10), filepath)
    tele.update(STINT_TELE)
    gen = module_stats.record_driver_stats(StatsInfo(), filepath, "Class", 1500, False)
    loop = ModuleLoop(gen, resets=1)
    loop.update()
    drive_stats_lap(tele, loop, 0.0, 90.0)
    tele["timing.elapsed"] = 93.0
    loop.update()
    loop.update()  # best lap validated
    hold_stats_file(monkeypatch, 11)  # first stint end: file held
    loop.resets += 1  # back to garage & out again: new stint
    loop.update()
    release_stats_file(monkeypatch)
    assert driver_stats.load_driver_stats(("SimTrack", "GT3"), filepath).valid == 10
    tele.update({"timing.start": 0.0, "timing.elapsed": 0.0, "timing.last_laptime": -1.0})
    loop.update()
    drive_stats_lap(tele, loop, 0.0, 91.0)
    tele["timing.elapsed"] = 94.0
    loop.update()
    loop.update()
    gen.send(MODULE_STOP)
    stats = driver_stats.load_driver_stats(("SimTrack", "GT3"), filepath)
    assert stats.valid == 12 and stats.pb == 90.0


def test_b006_stats_not_saved_at_stop_told(tele, tmp_path, clock, monkeypatch):  # noqa: F811
    filepath = f"{tmp_path}/"
    driver_stats.save_driver_stats(("SimTrack", "GT3"), DriverStats(valid=10), filepath)
    told = []
    monkeypatch.setattr(module_stats, "notify_stats_not_saved", lambda: told.append(True))
    tele.update(STINT_TELE)
    gen = module_stats.record_driver_stats(StatsInfo(), filepath, "Class", 1500, False)
    loop = ModuleLoop(gen, resets=1)
    loop.update()
    drive_stats_lap(tele, loop, 0.0, 90.0)
    tele["timing.elapsed"] = 93.0
    loop.update()
    hold_stats_file(monkeypatch, 1000)
    gen.send(MODULE_STOP)
    assert told == [True]


def test_b006_combined_stats_keeps_best_and_adds_counters():
    combined = driver_stats.combined_stats(DriverStats(pb=91.0, valid=2, meters=10.0),
                                           DriverStats(pb=92.0, qb=90.0, valid=3, meters=5.0))
    assert (combined.pb, combined.qb, combined.valid, combined.meters) == (91.0, 90.0, 5, 15.0)


def test_b001_invalid_stats_file_still_backed_up_and_reset(tmp_path):
    filepath = f"{tmp_path}/"
    with open(os.path.join(filepath, "driver.stats"), "w", encoding="utf-8") as file:
        file.write('{"Spa": {"GT3": ')  # cut short
    assert driver_stats.save_driver_stats(("Spa", "GT3"), DriverStats(valid=2), filepath) is True
    assert read_stats(filepath)["Spa"]["GT3"]["valid"] == 2
    assert any(name.startswith("driver.stats.backup-") for name in os.listdir(filepath))


def test_b006_message_translated():
    from neopedal import i18n

    i18n.set_language("Français")
    try:
        text = i18n.trm("Driver stats of the last stint could not be saved (file locked by another program, "
                        "or disk error?).")
    finally:
        i18n.set_language("English")
    assert text.startswith("Les statistiques pilote du dernier relais n'ont pas pu être enregistrées")


# B-013
def test_b013_stats_saved_at_checkpoints_while_driving(tele, tmp_path, clock, monkeypatch):  # noqa: F811
    """Stats recorded so far saved every checkpoint (kept after a crash), never counted twice, one history record"""
    monkeypatch.setattr(module_stats, "monotonic", lambda: clock["now"], raising=False)
    filepath = f"{tmp_path}/"
    tele.update(STINT_TELE)
    gen = module_stats.record_driver_stats(StatsInfo(), filepath, "Class", 1500, False)
    loop = ModuleLoop(gen, resets=1)
    loop.update()
    drive_stats_lap(tele, loop, 0.0, 90.0)
    tele["timing.elapsed"] = 93.0
    loop.update()
    loop.update()
    assert driver_stats.load_driver_stats(("SimTrack", "GT3"), filepath).valid == 0
    clock["now"] += 301.0
    loop.update()  # checkpoint
    saved = driver_stats.load_driver_stats(("SimTrack", "GT3"), filepath)
    assert (saved.valid, saved.pb) == (1, 90.0)  # kept if the app crashes now
    drive_stats_lap(tele, loop, 90.0, 89.0)
    tele["timing.elapsed"] = 182.0
    loop.update()
    loop.update()
    gen.send(MODULE_STOP)
    stats = driver_stats.load_driver_stats(("SimTrack", "GT3"), filepath)
    assert (stats.valid, stats.pb) == (2, 89.0)
    assert stats.seconds == pytest.approx(182.0)
    records = driver_history.read_records(filepath)
    assert len(records) == 1 and (records[0].valid, records[0].best) == (2, 89.0)
    assert records[0].seconds == pytest.approx(182.0)


# B-005
def test_b005_lap_invalidated_by_game_never_best_lap(tele, tmp_path, clock):  # noqa: F811
    """LMU lap invalidated (track limits) with a lap time: counted invalid, never a personal best; next clean lap
    counts"""
    filepath = f"{tmp_path}/"
    tele.update(STINT_TELE)
    tele.update({"timing.current_laptime": 30.0, "lap.invalidated": True})  # track limits during the lap
    gen = module_stats.record_driver_stats(StatsInfo(), filepath, "Class", 1500, False)
    loop = ModuleLoop(gen, resets=1)
    loop.update()
    drive_stats_lap(tele, loop, 0.0, 85.0)
    tele.update({"timing.elapsed": 88.0, "timing.current_laptime": 3.0, "lap.invalidated": False})
    loop.update()
    loop.update()
    drive_stats_lap(tele, loop, 85.0, 90.0)
    tele["timing.elapsed"] = 178.0
    loop.update()
    loop.update()
    gen.send(MODULE_STOP)
    stats = driver_stats.load_driver_stats(("SimTrack", "GT3"), filepath)
    assert (stats.valid, stats.invalid) == (1, 1)
    assert stats.pb == 90.0 and stats.qb == 90.0
    assert driver_history.read_records(filepath)[0].best == 90.0


def test_b005_lap_invalidated_just_before_leaving_track(tele, tmp_path, clock):  # noqa: F811
    """Lap invalidated, garage just after the line: validated later by game lap time, still no best lap"""
    filepath = f"{tmp_path}/"
    tele.update(STINT_TELE)
    tele.update({"timing.current_laptime": 30.0, "lap.invalidated": True})
    gen = module_stats.record_driver_stats(StatsInfo(), filepath, "Class", 1500, False)
    loop = ModuleLoop(gen, resets=1)
    loop.update()
    drive_stats_lap(tele, loop, 0.0, 85.0, report=False)
    realtime_state.active = False  # back to garage before the lap is counted
    loop.resets += 1
    loop.update()
    tele["timing.last_laptime"] = 85.0
    clock["now"] += 1.0
    loop.update()
    gen.send(MODULE_STOP)
    stats = driver_stats.load_driver_stats(("SimTrack", "GT3"), filepath)
    assert stats.pb > 85.0 and stats.invalid == 1


# B-004
def race_ticks(values: dict, loop: ModuleLoop, start: int, end: int):
    for elapsed in range(start, end, 5):
        values["timing.elapsed"] = float(elapsed)
        values["vehicle.position_xyz"] = (elapsed * 50.0, 0.0, 0.0)
        loop.update()


def test_b004_module_restart_during_race_counts_one_start(tele, tmp_path, clock):  # noqa: F811
    """Modules reloaded during a race (option applied, preset loaded): no second start, no mid race start place"""
    tele.update(STINT_TELE)
    tele.update({"session.session_type": 4, "session.pre_race": True, "vehicle.place": 5,
                 "vehicle.total_vehicles": 1})
    filepath = f"{tmp_path}/"
    gen = module_stats.record_driver_stats(StatsInfo(), filepath, "Class", 1500, False)
    loop = ModuleLoop(gen, resets=1)
    race_ticks(tele, loop, 0, 30)  # formation
    tele["session.pre_race"] = False  # green flag
    race_ticks(tele, loop, 30, 100)
    gen.send(MODULE_STOP)  # loader.reload: modules stopped, data saved
    tele["vehicle.place"] = 2
    gen = module_stats.record_driver_stats(StatsInfo(), filepath, "Class", 1500, False)
    loop = ModuleLoop(gen, resets=1)  # same game stint
    race_ticks(tele, loop, 100, 200)
    gen.send(MODULE_STOP)
    assert driver_stats.load_driver_stats(("SimTrack", "GT3"), filepath).starts == 1
    assert [record.start_position for record in driver_history.read_records(filepath)] == [5, 0]


# B-014
def test_b014_teammate_stint_not_recorded(tele, tmp_path, clock, monkeypatch):  # noqa: F811
    """Team race driver swap (LMU): laps, distance & time of teammate at the wheel never recorded as player's"""
    monkeypatch.setattr(module_stats, "player_profile_names", lambda: frozenset(), raising=False)
    filepath = f"{tmp_path}/"
    tele.update(STINT_TELE)
    tele["vehicle.driver_name"] = "Me"
    gen = module_stats.record_driver_stats(StatsInfo(), filepath, "Class", 1500, False)
    loop = ModuleLoop(gen, resets=1)
    loop.update()
    drive_stats_lap(tele, loop, 0.0, 90.0)
    tele["timing.elapsed"] = 93.0
    loop.update()
    loop.update()
    tele["vehicle.driver_name"] = "Mate"  # driver swap: teammate drives 2 laps
    drive_stats_lap(tele, loop, 90.0, 85.0)
    drive_stats_lap(tele, loop, 175.0, 85.0)
    tele["timing.elapsed"] = 263.0
    loop.update()
    tele["vehicle.driver_name"] = "Me"  # back to player
    loop.update()
    drive_stats_lap(tele, loop, 260.0, 91.0)
    tele["timing.elapsed"] = 354.0
    loop.update()
    loop.update()
    gen.send(MODULE_STOP)
    stats = driver_stats.load_driver_stats(("SimTrack", "GT3"), filepath)
    assert stats.valid == 2 and stats.pb == 90.0
    assert stats.seconds < 200


def test_b014_stint_loaded_while_teammate_drove(tele, tmp_path, clock, monkeypatch):  # noqa: F811
    """Profile name known: the player taking the wheel becomes the stint driver, teammate laps after not counted"""
    monkeypatch.setattr(module_stats, "player_profile_names", lambda: frozenset({"me"}), raising=False)
    filepath = f"{tmp_path}/"
    tele.update(STINT_TELE)
    tele["vehicle.driver_name"] = "Mate"
    gen = module_stats.record_driver_stats(StatsInfo(), filepath, "Class", 1500, False)
    loop = ModuleLoop(gen, resets=1)
    loop.update()
    tele["vehicle.driver_name"] = "Me"
    loop.update()
    drive_stats_lap(tele, loop, 0.0, 90.0)
    tele["timing.elapsed"] = 93.0
    loop.update()
    tele["vehicle.driver_name"] = "Mate"
    drive_stats_lap(tele, loop, 90.0, 85.0)
    tele["timing.elapsed"] = 178.0
    loop.update()
    gen.send(MODULE_STOP)
    assert driver_stats.load_driver_stats(("SimTrack", "GT3"), filepath).valid == 1


# B-011
def test_b011_not_finite_stats_reset_for_viewer():
    """NaN & Infinity (accepted by JSON) never reach the page: table cells and totals stay numbers"""
    from neopedal.ui.quick import stats_common

    data = driver_stats.validate_stats_file(json.loads(
        '{"Spa": {"GT3": {"seconds": NaN, "meters": Infinity, "pb": -Infinity, "valid": 3}}}'))
    vehicle = data["Spa"]["GT3"]
    assert vehicle == {"seconds": 0.0, "meters": 0.0, "pb": driver_stats.MAX_SECONDS, "valid": 3}
    assert stats_common.stat_number({"seconds": float("nan")}, "seconds") == 0
    assert stats_common.format_duration(stats_common.stat_number({"seconds": float("inf")}, "seconds"))


# B-002
SPA_HYPER = ("Spa", "Hyper - Toyota")


def write_stats(filepath: str, data: dict) -> None:
    with open(os.path.join(filepath, "driver.stats"), "w", encoding="utf-8") as file:
        json.dump(data, file)


@pytest.fixture
def stats_folder(tmp_path, monkeypatch):
    from neopedal.setting import cfg

    filepath = f"{tmp_path}/"
    monkeypatch.setattr(cfg.path, "config", filepath)
    return filepath


def test_b002_undo_backup_restore_keeps_stats_recorded_since(stats_folder):
    from neopedal.ui.quick.stats_edits import StatsEdits

    write_stats(stats_folder, {"Spa": {"Hyper - Toyota": {"pb": 128.0, "valid": 20, "meters": 2000.0}}})
    backup = {"Spa": {"Hyper - Toyota": {"pb": 130.0, "valid": 10, "meters": 1000.0}}}
    outcome, edit = StatsEdits.write_edit((), backup, None)  # backup restored
    assert outcome == "saved"
    driver_stats.save_driver_stats(SPA_HYPER, DriverStats(pb=125.0, valid=5, meters=500.0), stats_folder)
    StatsEdits.apply_edit(edit, True)  # undo: stats before restore + stint since
    vehicle = read_stats(stats_folder)["Spa"]["Hyper - Toyota"]
    assert (vehicle["pb"], vehicle["valid"], vehicle["meters"]) == (125.0, 25, 2500.0)
    driver_stats.save_driver_stats(SPA_HYPER, DriverStats(valid=1), stats_folder)
    StatsEdits.apply_edit(edit, False)  # redo: backup + both stints since
    vehicle = read_stats(stats_folder)["Spa"]["Hyper - Toyota"]
    assert (vehicle["pb"], vehicle["valid"], vehicle["meters"]) == (125.0, 16, 1500.0)


def test_b002_undo_lap_times_completed_keeps_newer_best(stats_folder):
    from neopedal.process import results_index as ri
    from neopedal.ui.quick.stats_edits import StatsEdits

    write_stats(stats_folder, {"Spa": {"Hyper - Toyota": {"pb": 130.0, "valid": 10, "meters": 1000.0}}})
    values = {"track": "Spa", "vehicle": "Hyper - Toyota", "stat": "qb", "laptime": 129.0, "current": 0.0,
              "time": 0.0}
    fix = ri.BestLapFix(**{name: values.get(name, "") for name in ri.BestLapFix._fields})
    outcome, edit = StatsEdits.write_fixes((fix,))
    assert outcome == "saved"
    driver_stats.save_driver_stats(SPA_HYPER, DriverStats(pb=124.0, valid=3), stats_folder)
    StatsEdits.apply_edit(edit, True)
    vehicle = read_stats(stats_folder)["Spa"]["Hyper - Toyota"]
    assert (vehicle["pb"], vehicle["valid"]) == (124.0, 13)
    assert driver_stats.best_lap_time(vehicle.get("qb")) == 0.0  # completed lap time undone


# B-003
def test_b003_redo_track_removal_keeps_stints_driven_since(stats_folder):
    from neopedal.ui.quick.stats_edits import StatsEdits

    write_stats(stats_folder, {"Spa": {"Hyper - Toyota": {"pb": 130.0, "valid": 10}}, "Monza": {"GT3": {"valid": 1}}})
    outcome, edit = StatsEdits.write_edit(("Spa",), None, None)  # track removed
    assert outcome == "saved" and "Spa" not in read_stats(stats_folder)
    StatsEdits.apply_edit(edit, True)  # undo
    driver_stats.save_driver_stats(SPA_HYPER, DriverStats(pb=125.0, valid=4), stats_folder)
    backups = len(driver_stats.list_stats_backups(stats_folder))
    StatsEdits.apply_edit(edit, False)  # redo: old stats removed again, new stint kept
    vehicle = read_stats(stats_folder)["Spa"]["Hyper - Toyota"]
    assert (vehicle["pb"], vehicle["valid"]) == (125.0, 4)
    assert len(driver_stats.list_stats_backups(stats_folder)) == backups + 1  # backed up before redo


def test_b003_redo_lap_time_reset_keeps_newer_best(stats_folder):
    from neopedal.ui.quick.stats_edits import StatsEdits

    write_stats(stats_folder, {"Spa": {"Hyper - Toyota": {"pb": 130.0, "valid": 10}}})
    _, edit = StatsEdits.write_edit(("Spa", "Hyper - Toyota", "pb"), driver_stats.MAX_SECONDS, None)
    StatsEdits.apply_edit(edit, True)
    assert read_stats(stats_folder)["Spa"]["Hyper - Toyota"]["pb"] == 130.0
    driver_stats.save_driver_stats(SPA_HYPER, DriverStats(pb=126.0), stats_folder)
    StatsEdits.apply_edit(edit, False)
    assert read_stats(stats_folder)["Spa"]["Hyper - Toyota"]["pb"] == 126.0
    # Undone     # Nothing faster since: reset again done again: best lap driven since the reset still kept
    StatsEdits.apply_edit(edit, True)
    StatsEdits.apply_edit(edit, False)
    assert read_stats(stats_folder)["Spa"]["Hyper - Toyota"]["pb"] == 126.0


def test_b003_redo_vehicle_removal_without_new_stint_removes_it(stats_folder):
    from neopedal.ui.quick.stats_edits import StatsEdits

    write_stats(stats_folder, {"Spa": {"Hyper - Toyota": {"pb": 130.0, "valid": 10}, "GT3": {"valid": 2}}})
    _, edit = StatsEdits.write_edit(SPA_HYPER, None, None)
    StatsEdits.apply_edit(edit, True)
    StatsEdits.apply_edit(edit, False)
    assert read_stats(stats_folder)["Spa"] == {"GT3": {"valid": 2}}


# B-007
def test_b007_lap_time_reset_only_if_still_the_one_shown(stats_folder):
    """Page shows 130.0 while the Stats module saved 125.0: Reset Lap Time leaves the newer best lap"""
    from neopedal.ui.quick.stats_edits import StatsEdits

    write_stats(stats_folder, {"Spa": {"Hyper - Toyota": {"pb": 125.0, "valid": 10}}})
    path = ("Spa", "Hyper - Toyota", "pb")
    assert StatsEdits.write_edit(path, driver_stats.MAX_SECONDS, None, 130.0) == ("changed", None)
    assert read_stats(stats_folder)["Spa"]["Hyper - Toyota"]["pb"] == 125.0
    outcome, _ = StatsEdits.write_edit(path, driver_stats.MAX_SECONDS, None, 125.0)
    assert outcome == "saved"
    assert read_stats(stats_folder)["Spa"]["Hyper - Toyota"]["pb"] == driver_stats.MAX_SECONDS


# B-008
def test_b008_history_backed_up_with_stats_and_restored(stats_folder):
    """Track removed (stats & its sessions), page closed: backup restores the sessions too, newer ones kept"""
    from functools import partial

    from neopedal.ui.quick.stats_common import read_backup_files
    from neopedal.ui.quick.stats_edits import StatsEdits

    write_stats(stats_folder, {"Spa": {"Hyper - Toyota": {"pb": 130.0, "valid": 10}}, "Monza": {"GT3": {"valid": 1}}})
    spa = driver_history.session_record("Spa", "Hyper - Toyota", 1, 130.0, 10, 0, 7000.0, 900.0, 0, 0, 1000.0)
    monza = driver_history.session_record("Monza", "GT3", 1, 0.0, 1, 0, 5000.0, 100.0, 0, 0, 2000.0)
    driver_history.save_history(stats_folder, [spa, monza])

    def remove_spa(records):
        return [record for record in records if record.track == "Spa"], []

    assert StatsEdits.write_edit(("Spa",), None, remove_spa)[0] == "saved"
    assert [record.track for record in driver_history.read_records(stats_folder)] == ["Monza"]
    name, created = driver_stats.list_stats_backups(stats_folder)[0]
    newer = monza._replace(time=created + 60.0)  # stint saved after the backup
    driver_history.append_record(stats_folder, newer)
    stats_backup, history_backup = read_backup_files(stats_folder, name)
    assert history_backup == [spa, monza]
    change = partial(driver_history.restored_history, backup=history_backup, since=created)
    assert StatsEdits.write_edit((), stats_backup, change)[0] == "saved"
    assert driver_history.read_records(stats_folder) == [spa, monza, newer]
    assert "Spa" in read_stats(stats_folder)


def test_b008_history_copies_follow_stats_backups_rotation(stats_folder):
    from neopedal.ui.quick.stats_edits import StatsEdits

    write_stats(stats_folder, {"Spa": {"GT3": {"valid": 1}}})
    driver_history.save_history(stats_folder, [
        driver_history.session_record("Spa", "GT3", 1, 0.0, 1, 0, 1.0, 100.0, 0, 0, 1000.0)])
    for _ in range(driver_stats.BACKUP_COUNT + 2):
        StatsEdits.write_edit(("Spa", "GT3", "valid"), 1, lambda records: ([], []))
    copies = [name for name in os.listdir(stats_folder) if name.startswith(driver_stats.HISTORY_BACKUP_PREFIX)]
    assert len(copies) == driver_stats.BACKUP_COUNT
    assert all(driver_stats.history_backup_path(stats_folder, name) for name, _ in
               driver_stats.list_stats_backups(stats_folder))


# B-015
def test_b015_backup_restored_over_damaged_stats_file(stats_folder, monkeypatch):
    from neopedal.ui.quick.stats_edits import StatsEdits

    damaged = '{"Spa": {"GT3": {"valid": 1'
    with open(os.path.join(stats_folder, "driver.stats"), "w", encoding="utf-8") as file:
        file.write(damaged)
    backup = {"Spa": {"GT3": {"valid": 40, "pb": 120.0}}}
    assert StatsEdits.write_edit((), backup, None) == ("restored", None)
    assert read_stats(stats_folder) == backup
    kept = [name for name, _ in driver_stats.list_stats_backups(stats_folder)]
    with open(os.path.join(stats_folder, kept[0]), encoding="utf-8") as file:
        assert file.read() == damaged  # damaged file kept as backup
    # File only held by another program: never written over
    hold_stats_file(monkeypatch, 1000)
    assert StatsEdits.write_edit((), {"Monza": {}}, None)[0] == "unreadable"
    release_stats_file(monkeypatch)
    assert read_stats(stats_folder) == backup


# B-016
def test_b016_app_closing_waits_for_stats_edit_being_saved(monkeypatch):
    import threading

    from neopedal import loader
    from neopedal.ui.quick import stats_io

    monkeypatch.setattr(stats_io, "_edits_running", set())
    waiters = "_close_waiters" if hasattr(loader, "on_close") else "_pending_writers"
    monkeypatch.setattr(loader, waiters, [])
    finished = threading.Event()
    stats_io.track_edit(finished)
    assert stats_io.wait_edits in getattr(loader, waiters)  # run by loader.close (quit, restart, system end)
    assert stats_io.wait_edits(timeout=0.0) is False
    saving = threading.Timer(0.05, finished.set)  # edit thread writing history, then stats
    saving.start()
    assert stats_io.wait_edits(timeout=10.0) is True and finished.is_set()
    saving.join()


# B-012
def test_b012_rank_history_time_out_of_range_skipped(tmp_path):
    from neopedal.process import driver_ranks

    path = os.path.join(tmp_path, "ranks.history")
    with open(path, "w", encoding="utf-8") as file:
        for time_text in ("NaN", "Infinity", "1e20", "1793580014000", "true", "1700000000"):
            file.write(f'{{"time": {time_text}, "driver": ["Gold", 2, 10], "steam": "1"}}\n')
    assert [entry.time for entry in driver_ranks.read_history(path)] == [1700000000.0]


def test_b012_date_of_damaged_time_shown_as_missing():
    from neopedal.process.results_text import MISSING
    from neopedal.ui.quick.formatting import format_date

    for value in (float("nan"), float("inf"), 1e20, -5.0):
        assert format_date(value) == MISSING
    assert format_date(1700000000.0) != MISSING


# B-026
def test_b026_backup_with_date_out_of_platform_range_skipped(tmp_path, monkeypatch):
    """Backup renamed by hand (year 9999, 1970 east of UTC): OSError on Windows, list of backups still shown"""
    from datetime import datetime

    filepath = f"{tmp_path}/"
    for stamp in ("9999-12-31-23-59-59", "2026-11-02-10-00-00"):
        with open(os.path.join(filepath, f"driver.stats.backup-auto-{stamp}-000000"), "w", encoding="utf-8") as file:
            file.write("{}")

    class Day(datetime):
        def timestamp(self):
            if self.year == 9999:
                raise OSError(22, "Invalid argument")
            return super().timestamp()

    monkeypatch.setattr(driver_stats, "datetime", Day)
    names = [name for name, _ in driver_stats.list_stats_backups(filepath)]
    assert names == ["driver.stats.backup-auto-2026-11-02-10-00-00-000000"]


# Ranks: online source simulated (network never called)
ACCOUNT_A, ACCOUNT_B = "76561190000000001", "76561190000000002"


class FakeOnline:
    """Online ranks source (RaceControl) answering given ranks"""

    def __init__(self, ranks):
        self.ranks = ranks
        self.calls = 0
        self.on = True

    def enabled(self):
        return self.on

    def game_running(self):
        return True

    def fetch(self, account):
        self.calls += 1
        return self.ranks

    def forget(self):
        pass


def rank_storage(*entries) -> str:
    return json.dumps({"profile": json.dumps({"teams": [{"drivers": list(entries)}]})})


def rank_profile(name: str, steam_id: str, rank: str, tier: int, team_only: bool = False) -> dict:
    data = {"name": name, "driverRank": {"rank": rank, "tier": tier, "progress": 0},
            "safetyRank": {"rank": "Gold", "tier": 1, "progress": 0}}
    data["driverId" if team_only else "steamId"] = "x1" if team_only else steam_id
    return data


# B-009
def test_b009_online_ranks_without_steam_id_never_given_to_next_account(tmp_path):
    from neopedal.process import driver_ranks as dr

    storage = os.path.join(tmp_path, "storage.json")
    with open(storage, "w", encoding="utf-8") as file:
        file.write("{}")
    located = {"value": dr.Located(storage, ACCOUNT_A, ("Me",))}
    online = FakeOnline(dr.DriverRanks("Me", "", "", "", dr.Rank("Platinum", 3, 50), None))  # no platforms
    history = os.path.join(tmp_path, "ranks.history")
    watcher = dr.RankWatcher(lambda: located["value"], lambda: history, online=online, run_online=lambda work: work(),
                             active_account=lambda: located["value"].steam_id)
    watcher.check()
    watcher.check()
    online.ranks = None  # account B: online read not done yet
    located["value"] = dr.Located(storage, ACCOUNT_B, ("Other",))
    watcher._checked_time = -99
    watcher.check()
    watcher.check()
    assert [entry.steam_id for entry in dr.read_history(history)] == [ACCOUNT_A]
    assert watcher.player is None or watcher.player.driver != dr.Rank("Platinum", 3, 50)


# B-010
def test_b010_older_file_ranks_never_saved_after_online_ones(tmp_path):
    from neopedal.process import driver_ranks as dr

    storage = os.path.join(tmp_path, "storage.json")
    with open(storage, "w", encoding="utf-8") as file:
        file.write(rank_storage(rank_profile("Me", ACCOUNT_A, "Silver", 1)))
    os.utime(storage, (1_600_000_000, 1_600_000_000))  # game file written long ago
    online = FakeOnline(dr.DriverRanks("Me", ACCOUNT_A, "", "", dr.Rank("Gold", 2, 10), None))
    history = os.path.join(tmp_path, "ranks.history")
    watcher = dr.RankWatcher(lambda: dr.Located(storage, ACCOUNT_A, ("Me",)), lambda: history, online=online,
                             run_online=lambda work: work())
    watcher.check()
    watcher.check()
    online.on = False  # online ranks turned off: game file ranks again
    watcher.check()
    entries = dr.read_history(history)
    assert [entry.time for entry in entries] == sorted(entry.time for entry in entries)
    assert entries[-1].driver == dr.Rank("Gold", 2, 10)


def test_b010_history_saved_out_of_order_read_sorted(tmp_path):
    from neopedal.process import driver_ranks as dr

    path = os.path.join(tmp_path, "ranks.history")
    with open(path, "w", encoding="utf-8") as file:
        file.write('{"time": 1793580014, "driver": ["Gold", 2, 10], "steam": "1"}\n')
        file.write('{"time": 1600000000, "driver": ["Silver", 1, 0], "steam": "1"}\n')
    assert [entry.time for entry in dr.read_history(path)] == [1600000000.0, 1793580014.0]


# B-019
def test_b019_player_found_by_name_gets_account_history_only(tmp_path):
    from neopedal.process import driver_ranks as dr

    storage = os.path.join(tmp_path, "storage.json")
    with open(storage, "w", encoding="utf-8") as file:
        file.write(rank_storage(rank_profile("Me", "", "Silver", 1, team_only=True)))
    history = os.path.join(tmp_path, "ranks.history")
    with open(history, "w", encoding="utf-8") as file:  # other account of this computer
        file.write(json.dumps({"time": 100, "driver": ["Platinum", 3, 90], "safety": None, "steam": ACCOUNT_A}) + "\n")
    watcher = dr.RankWatcher(lambda: dr.Located(storage, ACCOUNT_B, ("Me",)), lambda: history)
    watcher.check()
    assert watcher.player.steam_id == ACCOUNT_B
    assert all(entry.steam_id == ACCOUNT_B for entry in watcher.history_of(watcher.player.steam_id))


# B-017
def test_b017_cut_short_game_file_still_shows_online_ranks(tmp_path):
    """Game killed while writing its storage file: online ranks applied all the same, file read again later"""
    from neopedal.process import driver_ranks as dr

    storage = os.path.join(tmp_path, "storage.json")
    with open(storage, "w", encoding="utf-8") as file:
        file.write('{"profile": "{\\"x\\": 1')  # no ranks, invalid JSON
    online = FakeOnline(dr.DriverRanks("Me", ACCOUNT_A, "", "", dr.Rank("Gold", 2, 10), None))
    watcher = dr.RankWatcher(lambda: dr.Located(storage, ACCOUNT_A, ("Me",)),
                             lambda: os.path.join(tmp_path, "ranks.history"), online=online,
                             run_online=lambda work: work())
    for _ in range(3):
        watcher.check()
    assert watcher.online and watcher.player is not None and watcher.player.driver == dr.Rank("Gold", 2, 10)
    with open(storage, "w", encoding="utf-8") as file:  # written again in full
        file.write(rank_storage(rank_profile("Me", ACCOUNT_A, "Silver", 1)))
    os.utime(storage, (2_000_000_000, 2_000_000_000))
    watcher._checked_time = -99
    watcher.check()
    assert watcher.find_name("Me") is not None


# B-018
def test_b018_online_answer_for_other_account_not_read_again_every_check(tmp_path):
    from neopedal.process import driver_ranks as dr

    storage = os.path.join(tmp_path, "storage.json")
    with open(storage, "w", encoding="utf-8") as file:
        file.write("{}")
    online = FakeOnline(dr.DriverRanks("Me", ACCOUNT_B, "", "", dr.Rank("Gold", 2, 10), None))
    watcher = dr.RankWatcher(lambda: dr.Located(storage, ACCOUNT_A, ("Me",)),
                             lambda: os.path.join(tmp_path, "ranks.history"), online=online,
                             run_online=lambda work: work())
    for _ in range(5):
        watcher._checked_time = -99
        watcher.check()
    assert online.calls == 1  # one sign in, not one per check
    assert watcher.player is None or watcher.player.driver != dr.Rank("Gold", 2, 10)


# B-037
def test_b037_driver_username_never_given_ranks_of_a_homonym():
    """Driver Y's username is the real name of driver X: Y keeps own ranks whatever the answer order"""
    from neopedal.process import driver_ranks as dr
    from neopedal.process import field_ranks as fr
    from tests.test_field_ranks import FakeSource, profile

    mate = profile("Alex Martin", ("Gold", 2, 10))
    other = profile("Speedy", ("Bronze", 1, 0))
    other["name"] = "Alex Martin"  # real name of driver "Speedy"
    source = FakeSource()
    source.post = lambda path, payload: [mate, other]  # homonym answered last
    field = fr.FieldRanks(source, clock=lambda: 0.0, run=lambda work: work())
    field.poll(["Alex Martin", "Speedy"])
    assert field.ranks_of("Alex Martin").driver == dr.Rank("Gold", 2, 10)
    assert field.ranks_of("Speedy").driver == dr.Rank("Bronze", 1, 0)


# Home debrief: laps recorded as the recorder module writes them
DEBRIEF_T = 1_790_000_000


def write_debrief_lap(folder: str, number: int, laptime: float, end: float, vehicle: str = "Car A",
                      session_start: float = 0.0, finished: float = 0.0) -> str:
    from neopedal.module.module_recorder import lap_filename

    os.makedirs(folder, exist_ok=True)
    name = lap_filename(number, laptime, True, end)
    info = {"vehicle": vehicle, "session_start": session_start}
    if finished:
        info["finished"] = finished
    with open(os.path.join(folder, name), "w", encoding="utf-8") as file:
        file.write("# " + json.dumps(info) + "\n")
        file.write("distance\n0\n")
    return name


# B-021
def test_b021_debrief_leaves_out_laps_of_previous_stint(tmp_path):
    """Back to garage 40 s, out again: last lap of previous stint (saved before its record) not in debrief"""
    from neopedal.userfile import session_debrief
    from neopedal.userfile.telemetry_lap import lap_folder_name

    folder = os.path.join(tmp_path, lap_folder_name("Spa - GT3"))
    previous_end = DEBRIEF_T
    write_debrief_lap(folder, 7, 119.0, previous_end - 30, session_start=DEBRIEF_T - 3000)
    start = previous_end + 40
    for number in range(1, 4):
        write_debrief_lap(folder, number, 121.0 + number * 0.1, start + 125 * number, session_start=DEBRIEF_T - 3000)
    previous = driver_history.SessionRecord(time=previous_end, track="Spa", vehicle="Car A", best=119.0, valid=5,
                                            seconds=700, vehicle_class="GT3")
    record = driver_history.SessionRecord(time=start + 125 * 3 + 30, track="Spa", vehicle="Car A", session=1,
                                          best=121.1, valid=3, seconds=125 * 3 + 30, vehicle_class="GT3")
    debrief = session_debrief.build_debrief(record, [previous, record], str(tmp_path))
    assert [lap.number for lap in debrief.laps] == [1, 2, 3]
    assert "lap007" not in debrief.best_path


# B-022
def test_b022_debrief_finds_laps_of_class_with_invalid_file_characters(tmp_path):
    """rF2 mod class "GT3/GT4": laps saved by the recorder module in "Spa - GT3GT4" found by the debrief"""
    from neopedal.formatter import strip_invalid_char
    from neopedal.userfile import session_debrief
    from neopedal.userfile.telemetry_lap import lap_folder_name

    folder = os.path.join(tmp_path, lap_folder_name(strip_invalid_char("Spa - GT3/GT4")))
    write_debrief_lap(folder, 1, 120.0, DEBRIEF_T - 100)
    record = driver_history.SessionRecord(time=DEBRIEF_T, track="Spa", vehicle="Car A", best=120.0, valid=1,
                                          seconds=130, vehicle_class="GT3/GT4")
    assert len(session_debrief.build_debrief(record, [record], str(tmp_path)).laps) == 1
