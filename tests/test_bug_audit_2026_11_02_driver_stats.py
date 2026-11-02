"""Bug audit of Driver Stats (2026-11-02): recording, stats & history files, viewer page, Home debrief, DR/SR ranks

Files in tmp_path only, game data scripted, network never called.
"""

from __future__ import annotations

import builtins
import json
import os

from neopedal.userfile import driver_stats
from neopedal.userfile.driver_stats import DriverStats


def read_stats(filepath: str) -> dict:
    with open(os.path.join(filepath, "driver.stats"), encoding="utf-8") as file:
        return json.load(file)


def hold_stats_file(monkeypatch, count: int) -> None:
    """driver.stats text reads fail count times (file held by antivirus or cloud sync)"""
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


# B-001
def test_b001_stats_file_held_at_load_never_reset(tmp_path, monkeypatch):
    """File held longer than the load attempts: not saved (kept by caller), other tracks never lost"""
    filepath = f"{tmp_path}/"
    driver_stats.save_driver_stats(("Spa", "GT3"), DriverStats(valid=100, pb=130.0), filepath)
    driver_stats.save_driver_stats(("Monza", "GT3"), DriverStats(valid=50, pb=110.0), filepath)
    hold_stats_file(monkeypatch, 11)  # 10 attempts & last load
    saved = driver_stats.save_driver_stats(("Spa", "GT3"), DriverStats(valid=1), filepath)
    monkeypatch.undo()
    stats = read_stats(filepath)
    assert saved is False
    assert stats["Monza"]["GT3"]["valid"] == 50 and stats["Spa"]["GT3"]["valid"] == 100


def test_b001_invalid_stats_file_still_backed_up_and_reset(tmp_path):
    filepath = f"{tmp_path}/"
    with open(os.path.join(filepath, "driver.stats"), "w", encoding="utf-8") as file:
        file.write('{"Spa": {"GT3": ')  # cut short
    assert driver_stats.save_driver_stats(("Spa", "GT3"), DriverStats(valid=2), filepath) is True
    assert read_stats(filepath)["Spa"]["GT3"]["valid"] == 2
    assert any(name.startswith("driver.stats.backup-") for name in os.listdir(filepath))
