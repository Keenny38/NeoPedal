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
