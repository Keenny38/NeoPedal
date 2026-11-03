#  NeoPedal is an open-source overlay application for racing simulation.
#  Copyright (C) 2022-2026 TinyPedal developers, see contributors.md file
#
#  This file is part of NeoPedal.
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Audit before 0.29.0 (2026-11-02), game data & settings: LMU game lock never kept alive by the app once data
stops changing (B1), per-overlay limits applied when presets load (L1), option documentation (L2)"""

from __future__ import annotations

import mmap
import os
import re
import sys
from types import SimpleNamespace

import pytest

from pyLMUSharedMemory import lmu_data, lmu_mmap

DOC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "customization.md")


class FakeClock:
    """time module of lmu_mmap, monotonic clock set by the test"""

    def __init__(self, now: float = 100.0) -> None:
        self.now = now

    def monotonic(self) -> float:
        return self.now


class FakeLock:
    """Lock of the game mapped by the app (busy flag read through lmu_mmap.lock_busy)"""

    def __init__(self) -> None:
        self.busy = False
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def copy_control(monkeypatch):
    """Copy access control on an anonymous buffer (never the game's sections), fake clock & lock"""
    monkeypatch.setattr(lmu_mmap, "platform_mmap", lambda name, size: mmap.mmap(-1, size))
    clock = FakeClock()
    monkeypatch.setattr(lmu_mmap, "time", SimpleNamespace(monotonic=clock.monotonic))
    monkeypatch.setattr(lmu_mmap, "lock_busy", lambda lock: lock.busy)
    locks: list[FakeLock] = []

    def open_lock(name):
        locks.append(FakeLock())
        return locks[-1]

    monkeypatch.setattr(lmu_mmap, "open_game_lock", open_lock)
    control = lmu_mmap.MMapControl("test", lmu_data.LMUObjectOut, lock_name="test_lock")
    control.create(0)
    yield control, clock, locks
    control._lock = None
    control.close()


def write_tick(control, elapsed: float) -> None:
    """Game writes a new tick in its shared memory"""
    live = lmu_data.LMUObjectOut.from_buffer(control._mmap_buffer)
    live.scoring.scoringInfo.mCurrentET = live.telemetry.telemInfo[0].mElapsedTime = elapsed
    del live  # view of the mapping released (close)


# --- B1: game stopped (crashed while writing: busy flag left set), data no longer changes: lock let go
def test_b1_lock_let_go_once_data_unchanged_even_busy(copy_control):
    control, clock, locks = copy_control
    write_tick(control, 1.0)
    assert control.update() is True and len(locks) == 1  # lock of the game found at first change
    lock = locks[0]
    lock.busy = True  # game killed while holding its lock: flag never cleared, data never changes again
    for step in (0.5, 1.0, 1.9):
        clock.now = 100.0 + step
        assert control.update() is False
        assert not lock.closed and control._lock is lock
    clock.now = 102.6  # unchanged since 100.5
    assert control.update() is False
    assert lock.closed and control._lock is None  # section no longer kept alive by the app
    clock.now = 110.0
    assert control.update() is False and len(locks) == 1  # never looked for while data stays frozen


def test_b1_lock_opened_again_at_once_when_data_changes(copy_control):
    control, clock, locks = copy_control
    write_tick(control, 1.0)
    assert control.update() is True
    clock.now = 103.0
    control.update()  # idle timer started
    clock.now = 105.5
    control.update()
    assert locks[0].closed and control._lock is None
    clock.now = 105.6  # game resumed (or started again): lock of the game used again for the next copy
    write_tick(control, 2.0)
    assert control.update() is True and len(locks) == 2 and control._lock is locks[1]
    locks[1].busy = True
    write_tick(control, 3.0)
    assert control.update() is False  # game writing: copy waits for the lock again


def test_b1_lock_kept_while_game_runs(copy_control):
    control, clock, locks = copy_control
    for tick in range(1, 50):  # 5 s of new data every 0.1 s, unchanged ticks in between
        clock.now = 100.0 + tick / 10
        write_tick(control, float(tick))
        assert control.update() is True
        assert control.update() is False
    assert len(locks) == 1 and not locks[0].closed and control._lock is locks[0]


def test_b1_counts_mismatch_frozen_lock_let_go(copy_control):
    control, clock, locks = copy_control
    write_tick(control, 1.0)
    assert control.update() is True
    live = lmu_data.LMUObjectOut.from_buffer(control._mmap_buffer)
    live.scoring.scoringInfo.mNumVehicles = 3  # game stopped between scoring & telemetry writes
    del live
    clock.now = 101.0
    assert control.update() is False
    clock.now = 103.5
    assert control.update() is False
    assert locks[0].closed and control._lock is None


@pytest.mark.skipif(sys.platform != "win32", reason="named shared memory sections: Windows")
def test_b1_restarted_game_gets_fresh_lock(monkeypatch):
    """Real named section (test name, never the game's): game crashed with busy set, started again"""
    monkeypatch.setattr(lmu_mmap, "platform_mmap", lambda name, size: mmap.mmap(-1, size))
    clock = FakeClock()
    monkeypatch.setattr(lmu_mmap, "time", SimpleNamespace(monotonic=clock.monotonic))
    name = f"NeoPedalTestGameLock{os.getpid()}"
    game = mmap.mmap(-1, lmu_mmap.LOCK_SIZE, name)  # lock section of the running game, free
    control = lmu_mmap.MMapControl("test", lmu_data.LMUObjectOut, lock_name=name)
    control.create(0)
    try:
        write_tick(control, 1.0)
        assert control.update() is True and control._lock is not None
        game[lmu_mmap.LOCK_BUSY_OFFSET:lmu_mmap.LOCK_SIZE] = b"\x01\x00\x00\x00"  # Lock() taken
        game.close()  # game killed while writing
        clock.now = 100.5
        assert control.update() is False
        assert lmu_mmap.mapping_exists(name)  # kept by the app for now (busy flag of the dead game)
        probe = mmap.mmap(-1, lmu_mmap.LOCK_SIZE, name, access=mmap.ACCESS_READ)
        try:
            assert probe[lmu_mmap.LOCK_BUSY_OFFSET:] == b"\x01\x00\x00\x00"  # never cleared by the app
        finally:
            probe.close()
        clock.now = 102.6
        control.update()
        assert control._lock is None and not lmu_mmap.mapping_exists(name)
        again = mmap.mmap(-1, lmu_mmap.LOCK_SIZE, name)  # game started again: new section, Reset() runs
        try:
            assert again[:] == b"\x00" * lmu_mmap.LOCK_SIZE
        finally:
            again.close()
    finally:
        control.close()


# --- L1: per-overlay limits (OVERLAY_LIMITS) applied when presets load, generic limits elsewhere
def test_l1_overlay_limits_applied_at_preset_load():
    from neopedal.setting_validator import CLAMPED, PresetValidator
    from neopedal.template.option_limits import clamp_to_limit

    assert clamp_to_limit("bar_width", 100) == 100  # pixels for other overlays
    default = {
        "pit_stop_estimate": {"bar_width": 5},
        "fuel": {"bar_width": 5},
        "heading": {"decimal_places": 1},
        "gap_trend": {"number_of_laps": 5},
    }
    user = {
        "pit_stop_estimate": {"bar_width": 100},
        "fuel": {"bar_width": 100},
        "heading": {"decimal_places": 5},
        "gap_trend": {"number_of_laps": 500},
    }
    PresetValidator._validate(user, default)
    assert user["pit_stop_estimate"]["bar_width"] == 20  # characters: 3 to 20
    assert user["fuel"]["bar_width"] == 100
    assert user["heading"]["decimal_places"] == 2
    assert user["gap_trend"]["number_of_laps"] == 50
    assert ("bar_width", 100, 20) in CLAMPED


def test_l1_validators_still_called_with_two_arguments():
    from neopedal.setting_validator import PresetValidator, ValueValidator

    data = {"bar_width": 9000, "goals_reached": "x", "font_color": "nope"}
    assert ValueValidator.integer("bar_width", data) and data["bar_width"] == 4000
    assert ValueValidator.string_list("goals_reached", data) and "goals_reached" not in data
    assert ValueValidator.color("font_color", data) and "font_color" not in data
    for validator in PresetValidator._value_validators:
        validator("display_order_car_number", {"display_order_car_number": 1})
    user = {"sub": 3, "bar_width": 9000}
    PresetValidator.remove_invalid_key(user, {"sub": {"a": 1}, "bar_width": 5}, section="pit_stop_estimate")
    assert user == {"bar_width": 20}  # value set in place of a dict popped, overlay limit applied


# --- L2: documentation of options
def doc_text() -> str:
    with open(DOC, encoding="utf-8") as file:
        return file.read()


def test_l2_rail_items_default_documented():
    from neopedal.template.page_registry import default_rail

    text = doc_text()
    block = text.split("    rail_items\n", 1)[1].split("\n\n", 1)[0]
    assert f"`{default_rail()}`" in block


def test_l2_clock_format_example_12_hour():
    text = doc_text()
    assert "%H:%M:%S %p" not in text
    assert text.count("`%I:%M:%S %p`") >= 2


def test_l2_car_number_display_order_documented():
    text = doc_text()
    block = text.split("    column_car_number\n", 1)[1].split("\n\n", 1)[0]
    assert re.search(r"`display_order_car_number`", block)
