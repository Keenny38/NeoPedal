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

"""Audit before 0.29.0 (2026-11-02): Driver Stats page settings kept at start, menu shortcuts under the title bar
drawn by the app, no RaceControl wait after a forbidden entry list, stream sources hidden once the app is gone"""

from __future__ import annotations

import copy
import os
import re
import shutil
import subprocess
import sys

import pytest

from neopedal.process import raceos
from neopedal.setting_validator import PresetValidator
from neopedal.template.setting_global import GLOBAL_DEFAULT
from tests.test_audit_pending_lap_files import (  # noqa: F401  fixtures: scripted game & clocks
    ModuleLoop,
    clock,
    drive_stats_lap,
    synchronous_saves,
    tele,
)
from tests.test_ci_preflight import repo  # noqa: F401
from tests.test_raceos_fewer_requests import AUTH, client_of
from tests.test_ui_audit_2026_10_29_shell import window  # noqa: F401

STATS_VALUES = {
    "enable_group_by_class": True, "show_level_limits": True, "stats_tab": 2, "activity_view": 1,
    "activity_year": 2026, "condition_filter": 2, "online_filter": 1, "since_version": "0.27.0",
    "friend_file": "C:/stats/friend.stats", "goals": {"Spa|Porsche 963": 127.5}, "goals_reached": ["Spa|Porsche 963"],
}


def validated(config: dict) -> dict:
    return PresetValidator.global_preset(config, GLOBAL_DEFAULT)


def test_driver_stats_page_settings_kept_at_start():
    """A1: goals, friend file, filters & tab saved by the page were dropped by the validation at each start"""
    config = copy.deepcopy(GLOBAL_DEFAULT)
    config["driver_stats_viewer"].update(copy.deepcopy(STATS_VALUES))
    section = validated(config)["driver_stats_viewer"]
    assert {key: section[key] for key in STATS_VALUES} == STATS_VALUES


def test_driver_stats_page_settings_invalid_values_reset():
    config = copy.deepcopy(GLOBAL_DEFAULT)
    config["driver_stats_viewer"].update(goals=3, goals_reached=[1, 2], friend_file=5, since_version=None)
    section = validated(config)["driver_stats_viewer"]
    assert section["goals"] == {} and section["goals_reached"] == [] and section["friend_file"] == ""
    assert section["since_version"] == ""
    # Defaults copied, never shared: a page changing its list in place leaves the default as it is
    assert section["goals"] is not GLOBAL_DEFAULT["driver_stats_viewer"]["goals"]
    assert section["goals_reached"] is not GLOBAL_DEFAULT["driver_stats_viewer"]["goals_reached"]


def test_driver_stats_page_settings_not_in_settings_page():
    from neopedal.ui.config import HIDDEN_OPTIONS

    added = set(STATS_VALUES)
    assert added <= set(GLOBAL_DEFAULT["driver_stats_viewer"])
    assert added <= set(HIDDEN_OPTIONS["driver_stats_viewer"])


@pytest.fixture
def title_bar_on(monkeypatch):
    if sys.platform != "win32":  # app title bar draws over the Win32 frame (title_bar.FrameHandler): Windows only
        pytest.skip("app title bar: Windows only")
    from neopedal.ui import app as app_module
    from neopedal.ui.title_bar import PageTitleState

    monkeypatch.setattr(app_module, "use_app_title_bar", lambda: True)
    # Set by the window with the title bar, never reset: given back after the test, else page headers of later tests
    # left out their name (CI preflight 2026-11-03: test_ui_audit_2026_10_29_shell headers on every cell)
    monkeypatch.setattr(PageTitleState, "shown", PageTitleState.shown)


def test_menu_shortcuts_run_under_app_title_bar(title_bar_on, window, monkeypatch):  # noqa: F811
    """A2: menu bar of the title bar never shown: Ctrl+, & Ctrl+Shift+F did nothing (Qt runs shortcuts of a shown
    menu bar only)"""
    from PySide6.QtGui import QKeySequence

    from neopedal.ui import menu as menu_module

    assert window.title_bar is not None
    shortcuts = {action.shortcut().toString(): action for action in window.actions() if not action.shortcut().isEmpty()}
    for keys in ("Ctrl+,", "Ctrl+Shift+F"):
        assert QKeySequence(keys).toString() in shortcuts, keys
    opened = []
    monkeypatch.setattr(menu_module, "open_config_application", lambda parent, section="": opened.append(section))
    shortcuts[QKeySequence("Ctrl+,").toString()].trigger()
    assert opened == [""]


class EntriesForbidden:
    """Sign in answered, entry lists forbidden (403), other reads answered"""

    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, method, url, body, headers, timeout):
        self.calls.append(url)
        if url == raceos.AUTH_URL:
            return 200, AUTH
        if "/event/entries/" in url or url.endswith("/refused"):
            return 403, b""
        return 200, b"[]"


def test_forbidden_entry_list_after_sign_in_never_blocks():
    """A3: a 403 on an entry list just after a sign in stopped every request for 1 h (then 2, 4, 6 h)"""
    now = [1000.0]
    http = EntriesForbidden()
    client = client_of(http, now)
    assert client.get("api/v1/event/entries/123") is None  # sign in, then that list refused
    assert client.busy_for() == 0
    assert client.get("api/v1/hosted") == []  # token kept: no new sign in
    assert http.calls.count(raceos.AUTH_URL) == 1


def test_other_403_after_sign_in_still_blocks():
    now = [1000.0]
    client = client_of(EntriesForbidden(), now)
    assert client.get("api/v1/refused") is None
    assert client.busy_for() > 0


def source_script() -> str:
    from neopedal.stream_overlay import SOURCE_HTML

    return re.search(r"<script>(.*)</script>", SOURCE_HTML, re.S).group(1)


def test_stream_sources_hidden_once_server_lost():
    """A4: /overlay & /layout sources kept the last image for good (frozen standings on air) once the app was
    closed, the server turned off or a new access token made"""
    from neopedal.stream_overlay import SOURCE_HTML

    script = source_script()
    assert "body.lost #c,body.lost #layers{visibility:hidden!important}" in SOURCE_HTML
    assert "if(!response.ok){serverLost(true);" in script
    assert "draw();serverLost(false);" in script
    assert "catch(error){seq=0;serverLost(true);" in script
    assert "if(!edit&&Date.now()-failedSince>=LOST_MS)" in script  # layout editor never hidden


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_stream_source_script_valid(tmp_path):
    path = os.path.join(tmp_path, "source.js")
    with open(path, "w", encoding="utf-8") as file:
        file.write(source_script().replace("@@", "__"))
    result = subprocess.run(["node", "--check", path], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


# Release tools: launcher executable bits staged only (core.fileMode off on Windows) kept by the preflight snapshot,
# release commit leaves other staged files staged, matrix copy of an earlier run removed with its read-only files
def test_preflight_snapshot_keeps_staged_executable_bits(repo):  # noqa: F811
    from tests.test_ci_preflight import ci_preflight, run_git

    run_git(repo, "config", "core.fileMode", "false")
    (repo / "run.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    run_git(repo, "add", "run.sh")
    run_git(repo, "commit", "-q", "-m", "launcher")
    run_git(repo, "update-index", "--chmod=+x", "run.sh")  # staged, not committed
    sha, _ = ci_preflight.snapshot()
    assert run_git(repo, "ls-tree", sha, "run.sh").startswith("100755 ")
    assert run_git(repo, "ls-files", "-s", "run.sh").startswith("100755 ")  # real index untouched


def test_release_commit_keeps_files_staged_since(repo, monkeypatch):  # noqa: F811
    import release

    from tests.test_ci_preflight import ci_preflight, run_git

    monkeypatch.setattr(release, "ROOT", str(repo))
    (repo / "code.py").write_text("a = 5\n", encoding="utf-8")
    snapshot, _ = ci_preflight.snapshot()
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n## 0.2.0\n", encoding="utf-8")  # staged by another session
    run_git(repo, "add", "CHANGELOG.md")
    assert release.write_release_commit(snapshot, ["Release 0.2.0"])
    # Index: the committed files as committed, the file staged meanwhile still staged (working tree not compared:
    # racy timestamps of files written within the second)
    assert run_git(repo, "diff", "--cached", "--name-only").splitlines() == ["CHANGELOG.md"]


def test_matrix_copy_of_earlier_run_removed(tmp_path):
    import stat

    from tests.test_ci_preflight import check

    target = tmp_path / "py311-tree"
    pack = target / ".git" / "objects" / "pack" / "pack.idx"
    pack.parent.mkdir(parents=True)
    pack.write_text("x", encoding="utf-8")
    os.chmod(pack, stat.S_IREAD)  # git objects are read-only
    check.remove_tree(str(target))
    assert not target.exists()
    check.remove_tree(str(target))  # missing: nothing to do


# B7: stats saved at a checkpoint, NeoPedal stopped before the history record: session never imported again
def test_checkpoint_marked_until_stint_recorded(tele, tmp_path, clock):  # noqa: F811
    from neopedal.module import module_stats
    from neopedal.module._base import MODULE_STOP
    from neopedal.module_info import StatsInfo
    from neopedal.userfile import driver_history
    from tests.test_bug_audit_2026_11_02_driver_stats import STINT_TELE

    filepath = f"{tmp_path}/"
    tele.update(STINT_TELE)
    gen = module_stats.record_driver_stats(StatsInfo(), filepath, "Class", 1500, False)
    loop = ModuleLoop(gen, resets=1)
    loop.update()
    drive_stats_lap(tele, loop, 0.0, 90.0)
    tele["timing.elapsed"] = 93.0
    loop.update()
    loop.update()
    assert driver_history.read_checkpoints(filepath) == []
    clock["now"] += 301.0
    loop.update()  # checkpoint: stats saved, no record yet
    marks = driver_history.checkpoint_times(filepath)
    assert [track for track, _ in marks] == ["SimTrack"]
    gen.send(MODULE_STOP)  # stint recorded: mark removed
    assert len(driver_history.read_records(filepath)) == 1
    assert driver_history.read_checkpoints(filepath) == []


def test_session_of_checkpointed_stint_never_imported():
    from neopedal.process import results_import as imp
    from tests.test_results_import import END, SARTHE, summary

    crashed = summary(path="crash.xml", start=END + 5000, end=END + 6000)
    assert imp.import_candidates([crashed], [], []) == [crashed]
    assert imp.import_candidates([crashed], [], [], [(SARTHE, END + 5600)]) == []
    assert imp.import_candidates([crashed], [], [], [("Monza", END + 5600)]) == [crashed]  # other track


def test_checkpoint_marks_file_kept_small(tmp_path):
    from neopedal.userfile import driver_history

    filepath = f"{tmp_path}/"
    for start in range(driver_history.MAX_CHECKPOINTS + 5):
        driver_history.mark_checkpoint(filepath, "Spa", float(start), start + 300.0)
    driver_history.mark_checkpoint(filepath, "Spa", 10.0, 999.0)  # same stint: mark moved
    marks = driver_history.read_checkpoints(filepath)
    assert len(marks) == driver_history.MAX_CHECKPOINTS and marks[-1] == ("Spa", 10.0, 999.0)
    assert sum(mark[1] == 10.0 for mark in marks) == 1
    driver_history.clear_checkpoint(filepath, 10.0)
    assert all(mark[1] != 10.0 for mark in driver_history.read_checkpoints(filepath))
    with open(driver_history.checkpoint_path(filepath), "w", encoding="utf-8") as file:
        file.write('[["Spa", "x", 1], ["Spa", 1, NaN], 5, ["Spa", 2, 3]]')
    assert driver_history.read_checkpoints(filepath) == [("Spa", 2.0, 3.0)]  # garbage left out


# Backup restored: stints recorded after it keep their history records and are counted again in the stats
def test_backup_restored_counts_stints_recorded_after_it():
    from neopedal.ui.quick.stats_edits import restored_stats
    from neopedal.userfile.driver_history import SessionRecord

    backup = {"Spa": {"GT3": {"pb": 140.0, "qb": 141.0, "valid": 10, "seconds": 1500.0, "liters": 30.0}}}
    current = {"Spa": {"GT3": {"pb": 120.0, "qb": 141.0, "valid": 15, "seconds": 2300.0, "liters": 45.0}},  # glitch pb
               "Monza": {"LMP2": {"pb": 101.0, "valid": 4, "seconds": 420.0}}}  # changed with no record since
    records = [SessionRecord(500.0, "Spa", "GT3", 2, best=139.0),  # before the backup: in its stats
               SessionRecord(2000.0, "Spa", "GT3", 4, best=138.5, valid=5, seconds=800.0)]
    stats = restored_stats(backup, current, records, created=1000.0)
    spa = stats["Spa"]["GT3"]
    assert (spa["valid"], spa["seconds"], spa["liters"]) == (15, 2300.0, 45.0)  # counters of the newer stint back
    assert spa["pb"] == 138.5 and spa.get("rb") == 138.5 and spa["qb"] == 141.0  # best laps of its record only
    assert "Monza" not in stats  # nothing recorded there since the backup
    assert restored_stats(backup, current, records[:1], created=1000.0) == backup
    assert backup["Spa"]["GT3"]["valid"] == 10  # backup left as read
