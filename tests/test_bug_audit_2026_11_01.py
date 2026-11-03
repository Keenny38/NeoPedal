"""Bug audit of 2026-11-01 (AUDIT_BUGS.md): one test per fixed bug, failing before its fix"""

import os
import re
import time

import pytest

from tests.test_broadcast_director import director_page  # noqa: F401  # fixture
from tests.test_dialog_pages import window as main_window  # noqa: F401  # fixture
from tests.test_modern_graphic_widgets import oval, widgets  # noqa: F401  # fixtures
from tests.test_overlay_options import options as overlay_options  # noqa: F401  # fixture
from tests.test_race_calculator import host  # noqa: F401  # fixture
from tests.test_race_calculator import page as race_page  # noqa: F401  # fixture
from tests.test_race_results import backend as results_page  # noqa: F401  # fixture
from tests.test_race_results import results_folder  # noqa: F401  # fixture


# B-002: /director source asked again and again without pause
def test_b002_empty_section_feed_waits_before_answering():
    """Nothing published yet (version 0): a source asking v=0 waits like any long poll, not answered at once"""
    from neopedal.stream_director_feeds import SectionFeed

    feed = SectionFeed()
    begin = time.monotonic()
    version, sections, full = feed.sections(0, timeout=0.2)
    assert time.monotonic() - begin >= 0.15
    assert (version, sections, full) == (0, {}, True)
    feed.publish({"tower": [1]})
    begin = time.monotonic()
    assert feed.sections(0, timeout=2.0)[0] == 1 and time.monotonic() - begin < 1.0  # new state at once
    begin = time.monotonic()
    assert feed.sections(7, timeout=2.0)[2] and time.monotonic() - begin < 1.0  # page of another run: at once


def test_b002_director_script_pauses_after_error_or_quick_unchanged_answer():
    """Page of the source: answer not OK (403 after a new token, 404, 500) or unchanged answer given at once
    (server of an older version) waits before asking again, never polls at full speed"""
    from neopedal.stream_director_script import DIRECTOR_SCRIPT

    for name in ("poll", "pollLive"):
        body = re.search(r"async function " + name + r"\(\)\{(.*?)\n\}", DIRECTOR_SCRIPT, re.S).group(1)
        assert f"if(!once)setTimeout({name},0)" not in body  # never asked again at once whatever the answer
        assert f"if(!once)setTimeout({name},pause)" in body
        assert "response.status===403" in body and "Date.now()-started" in body


# B-001: QML views unloaded by setSource(QUrl()) from Python (Qt image thread waiting for the GIL: app frozen)
PAGE_QML = """import QtQuick
Item { width: 100; height: 100; property string label: i18n.tr("Close") }
"""


def quick_page(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    from neopedal.ui import quick

    (tmp_path / "AuditPage.qml").write_text(PAGE_QML, encoding="utf-8", newline="\n")
    monkeypatch.setattr(quick, "QML_FOLDER", str(tmp_path))
    parent = QWidget()
    layout = QVBoxLayout(parent)
    view = quick.create_quick_view(parent, "AuditPage.qml", {}, samples=0)
    layout.addWidget(view)
    parent.setFocusProxy(view)
    assert view.rootObject() is not None
    return parent, view


def flush_deletes():
    import gc

    from PySide6.QtCore import QCoreApplication, QEvent

    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.collect()


def test_b001_released_views_deleted_by_event_loop(tmp_path, monkeypatch):
    """Views of a page released: hidden now, QML left loaded (never torn down from Python), deleted by the event
    loop before the page"""
    import shiboken6

    from neopedal.ui.lazy_page import release_quick_views

    parent, view = quick_page(tmp_path, monkeypatch)
    try:
        release_quick_views(parent)
        assert view.isHidden()
        assert view.rootObject() is not None  # not unloaded by setSource(QUrl()) in this call
        flush_deletes()
        assert not shiboken6.isValid(view)
        release_quick_views(parent)  # nothing left: no error
    finally:
        parent.deleteLater()
        flush_deletes()


def test_b001_language_reload_builds_new_view(tmp_path, monkeypatch):
    """Page in new language: new view in place of the old one (layout & focus proxy), old one deleted later,
    never emptied by setSource(QUrl())"""
    import shiboken6

    from neopedal.ui import quick

    parent, view = quick_page(tmp_path, monkeypatch)
    try:
        new_view = quick.reload_in_language(view, "AuditPage.qml", {})
        assert new_view is not view and new_view.rootObject() is not None
        assert parent.layout().indexOf(new_view) == 0 and parent.layout().indexOf(view) < 0
        assert parent.focusProxy() is new_view
        assert view.isHidden() and view.rootObject() is not None  # old QML left for the event loop
        flush_deletes()
        assert not shiboken6.isValid(view) and shiboken6.isValid(new_view)
    finally:
        parent.deleteLater()
        flush_deletes()


def test_b001_wizard_release_never_unloads_from_python(ui_env, monkeypatch):
    import shiboken6
    from PySide6.QtGui import QImage

    from neopedal.ui import setup_wizard
    from neopedal.ui.quick import setup_backend

    def render(name, setting, style):
        image = QImage(40, 20, QImage.Format.Format_ARGB32)
        image.fill(0xFF336699)
        return image

    monkeypatch.setattr(setup_backend, "render_overlay", render)
    wizard = setup_wizard.SetupWizard(None, detect_games=False)
    view = wizard.view
    try:
        wizard.release_page()
        assert view.isHidden() and view.rootObject() is not None
        flush_deletes()
        assert not shiboken6.isValid(view)
        wizard.release_page()  # again (app quit after closed): no error
    finally:
        wizard.deleteLater()
        flush_deletes()


# B-005: modern Heading overlay not built for some sizes (square root of a negative number: complex value)
@pytest.mark.parametrize("font_size", [15, 30])
def test_b005_heading_built_at_every_size(widgets, font_size):  # noqa: F811
    """Sizes where the reading chips are a little narrower than the inner ring (window of 0.15 unit found from
    the chip row of a large dial: fonts & language change it), every size built"""
    options = {"font_size": font_size, "decimal_places": 2, "show_yaw_angle_reading": True,
               "show_slip_angle_reading": True}
    large = widgets("heading", display_size=600, **options)
    half_row = (large.chips[-1][2].right() - large.chips[0][2].left()) / 2
    unit = large.unit
    middle = 2 * (half_row + unit * 0.075 + 1 + unit * 1.15)  # inner ring radius = half row + 0.075 unit
    for size in range(int(middle) - 4, int(middle) + 5):
        widget = widgets("heading", display_size=size, **options)
        assert half_row < widget.inner or size < middle  # window reached
        assert all(isinstance(chip[2].top(), float) for chip in widget.chips)


# B-004: profiles of other screen setups lost when the .layouts file could not be read for a moment
def test_b004_unreadable_layout_file_never_saved_over(tmp_path, monkeypatch):
    import builtins
    import json

    from neopedal.userfile import layout_profile

    filename = str(tmp_path / "default.layouts")
    other = {"5760x1080+0+0": {"speedometer": [10, 20]}}
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(other, file)
    setting = {"speedometer": {"position_x": 1, "position_y": 2}}

    def locked(name, *args, **kwargs):  # held by antivirus / cloud sync
        if str(name) == filename:
            raise PermissionError(13, "locked", name)
        return builtins.open(name, *args, **kwargs)

    monkeypatch.setattr(layout_profile, "open", locked, raising=False)
    assert layout_profile.load_profiles(filename) is None
    assert not layout_profile.sync_layout(setting, ("speedometer",), filename, "1920x1080+0+0")
    layout_profile.store_layout(setting, ("speedometer",), filename, "1920x1080+0+0")
    monkeypatch.undo()
    with open(filename, encoding="utf-8") as file:
        assert json.load(file) == other  # other screen setup kept
    layout_profile.store_layout(setting, ("speedometer",), filename, "1920x1080+0+0")  # readable again
    assert set(layout_profile.load_profiles(filename)) == {"5760x1080+0+0", "1920x1080+0+0"}


def test_b004_invalid_layout_file_backed_up_before_replaced(tmp_path):
    from neopedal.userfile import layout_profile

    filename = tmp_path / "default.layouts"
    filename.write_text('{"5760x1080+0+0": {"speedometer": [10, 20]', encoding="utf-8")  # cut short
    setting = {"speedometer": {"position_x": 1, "position_y": 2}}
    layout_profile.store_layout(setting, ("speedometer",), str(filename), "1920x1080+0+0")
    backups = [path for path in tmp_path.iterdir() if path.name.startswith("default.layouts.backup")]
    assert len(backups) == 1 and backups[0].read_text(encoding="utf-8").startswith('{"5760x1080')
    assert set(layout_profile.load_profiles(str(filename))) == {"1920x1080+0+0"}


# B-011: Broadcast Director page closed during an instant replay: game left in the replay of the session
def test_b011_page_closed_during_instant_replay_goes_back_to_live(director_page, monkeypatch):  # noqa: F811
    from neopedal.process import director as dr
    from neopedal.ui.quick import game_camera
    from tests.test_broadcast_director import car, poll, race_answers
    from tests.test_game_info import wait_commands

    monkeypatch.setattr(game_camera, "REPLAY_READY", 0.0)
    monkeypatch.setattr(game_camera, "SEEK_WAIT", 0.0)
    page, backend = director_page, director_page.backend
    cars = (car(1, 1, distance=2000.0), car(2, 2, distance=1000.0))
    poll(page, race_answers(100.0, *cars, contacts=((96.0, "Driver 2", "Immovable"),)))
    poll(page, race_answers(101.0, *cars, contacts=((96.0, "Driver 2", "Immovable"),
                                                   (100.6, "Driver 1", "Driver 2"))))
    key = next(row["key"] for row in backend.feedRows.rows if row["kind"] == dr.CONTACT)
    game = page.game
    toggle = ("POST", "/rest/replay/toggleactive")

    class Answers(dict):  # replay open while toggled an odd number of times
        def get(self, key, default=None):
            if key == "/rest/replay/isActive":
                return game.sent.count(toggle) % 2 == 1
            return super().get(key, default)

    game.answers = Answers(game.answers)
    backend.replayEvent(key)
    wait_commands(backend.camera)
    assert backend.instantReplay and game.sent.count(toggle) == 1
    backend.release()  # page closed before the replay ends
    deadline = time.monotonic() + 5
    while game.sent.count(toggle) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert game.sent.count(toggle) == 2  # replay left: live session shown again
    assert not backend._instant_timer.isActive()


# B-009: app ended by Windows (shutdown, log off, installer closing apps) without the Quit menu: nothing saved
def test_b009_app_end_without_quit_menu_closes_once(monkeypatch):
    from neopedal import loader

    calls = []
    for name in ("write_pending", "cancel_reload", "unload_modules"):
        monkeypatch.setattr(loader, name, lambda name=name, **_: calls.append(name))
    monkeypatch.setattr(loader, "wait_data_saver", lambda timeout: True)
    monkeypatch.setattr(loader.replay, "stop_recording", lambda: calls.append("replay"))
    monkeypatch.setattr(loader.replay, "wait_closed", lambda timeout: True)
    class Api:  # game connection (slots class: methods read-only)
        def stop(self):
            calls.append("api")

        def close(self):
            pass

    monkeypatch.setattr(loader, "api", Api())
    from types import SimpleNamespace

    settings = SimpleNamespace(flush=lambda *args, **kwargs: calls.append("flush"), path=SimpleNamespace(config=""))
    monkeypatch.setattr(loader, "cfg", settings)
    monkeypatch.setattr(loader, "_closed", False)
    loader.close_at_exit()  # event loop ended by the system: closed as Quit does
    assert calls == ["write_pending", "cancel_reload", "unload_modules", "replay", "api", "flush"]
    loader.close_at_exit()  # closed already (Quit menu, then the event loop ends): nothing done twice
    assert len(calls) == 6


# B-003, B-006, B-024: Linux install script (executable files, paths with spaces, errors, plugins kept)
def bash_shell():
    import shutil
    import sys

    found = shutil.which("bash")
    if found is None or (sys.platform == "win32" and "system32" in found.lower()):  # WSL launcher: not this tree
        return None
    return found


def fake_source(folder):
    """Source tree with the files install.sh copies (small fakes), install files of the repository"""
    import shutil
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for name in ("install.sh", "NeoPedal.sh", "NeoPedal.desktop", "run.py", "README.md", "CHANGELOG.md",
                 "CHANGELOG.fr.md", "NOTICE.md", "LICENSE.txt"):
        shutil.copy(root / name, folder / name)
    for path in ("images/icon.png", "images/notice.txt", "fonts/Font.ttf", "fonts/OFL.txt", "docs/index.md",
                 "neopedal/__init__.py", "neopedal/ui/qml/Page.qml"):
        (folder / path).parent.mkdir(parents=True, exist_ok=True)
        (folder / path).write_text("x\n", encoding="utf-8")
    for package in ("pyLMUSharedMemory", "pyRfactor2SharedMemory"):
        for name in ("__init__.py", "README.md", "License.txt"):
            (folder / package).mkdir(exist_ok=True)
            (folder / package / name).write_text("x\n", encoding="utf-8")


def run_install(bash, source, prefix, cwd):
    import subprocess

    return subprocess.run([bash, str(source / "install.sh"), prefix.as_posix()], input="y\n", cwd=cwd,
                          capture_output=True, text=True, timeout=120, check=False)


def test_b003_launcher_files_executable_in_git():
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(["git", "ls-files", "-s", "run.py", "install.sh", "NeoPedal.sh"], cwd=root,
                            capture_output=True, text=True, check=False)
    if result.returncode != 0 or not result.stdout:
        pytest.skip("not a git checkout")
    modes = {line.split()[-1]: line.split()[0] for line in result.stdout.splitlines()}
    assert modes == {"run.py": "100755", "install.sh": "100755", "NeoPedal.sh": "100755"}


def test_b006_install_with_spaces_from_other_folder_keeps_plugins(tmp_path):
    bash = bash_shell()
    if bash is None:
        pytest.skip("bash not available")
    source = tmp_path / "Mes Projets" / "NeoPedal src"
    source.mkdir(parents=True)
    fake_source(source)
    prefix = tmp_path / "pre fix"
    for folder in ("share/applications", "bin"):
        (prefix / folder).mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    result = run_install(bash, source, prefix, elsewhere)
    assert result.returncode == 0, result.stdout + result.stderr
    installed = prefix / "share" / "NeoPedal"
    launcher = (prefix / "bin" / "NeoPedal").read_text(encoding="utf-8")
    assert f"{installed.as_posix()}/run.py" in launcher  # not empty: source path with spaces read
    assert (prefix / "share/applications/NeoPedal.desktop").read_text(encoding="utf-8").strip()
    assert (installed / "neopedal/ui/qml/Page.qml").is_file() and (installed / "run.py").is_file()
    # Plugin installed by the user, then installed again (update): plugin kept
    (installed / "plugins").mkdir()
    (installed / "plugins" / "mine.py").write_text("plugin\n", encoding="utf-8")
    result = run_install(bash, source, prefix, elsewhere)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (installed / "plugins" / "mine.py").read_text(encoding="utf-8") == "plugin\n"
    assert not [path for path in (prefix / "share").iterdir() if path.name.startswith("NeoPedal-plugins")]


def test_b006_install_stops_at_first_error(tmp_path):
    bash = bash_shell()
    if bash is None:
        pytest.skip("bash not available")
    source = tmp_path / "src"
    source.mkdir()
    fake_source(source)
    (source / "NOTICE.md").unlink()  # file missing: install stops, never "Installation finished"
    prefix = tmp_path / "prefix"
    for folder in ("share/applications", "bin"):
        (prefix / folder).mkdir(parents=True)
    result = run_install(bash, source, prefix, source)
    assert result.returncode != 0 and "Installation finished" not in result.stdout


# B-024: plugins folder inside a read-only install (Linux /usr/local/share): error shown, never raised
def test_b024_plugins_folder_not_writable_tells_why(ui_env, monkeypatch):
    from neopedal.ui import plugin_manager

    warnings, opened = [], []

    def refused(folder, exist_ok=False):
        raise PermissionError(13, "Permission denied", folder)

    monkeypatch.setattr(plugin_manager.os, "makedirs", refused)
    monkeypatch.setattr(plugin_manager.QMessageBox, "warning", lambda parent, title, text: warnings.append(text))
    monkeypatch.setattr(plugin_manager.QDesktopServices, "openUrl", lambda url: opened.append(url))
    manager = plugin_manager.PluginManager(None)
    try:
        manager.open_folder()
    finally:
        manager.close()
        manager.deleteLater()
    assert len(warnings) == 1 and "Permission denied" in warnings[0] and not opened


# B-007: user folder typed in config.json without its final separator: files written beside the folder
def test_b007_user_folder_without_separator_fixed_at_load(tmp_path):
    from neopedal.setting import FilePath
    from neopedal.setting_validator import PresetValidator
    from neopedal.template.setting_global import GLOBAL_DEFAULT

    folder = (tmp_path / "presets").as_posix()
    windows_style = str(tmp_path / "tele")  # backslashes on Windows
    config = {"user_path": {"settings_path": folder, "telemetry_path": windows_style}}
    config = PresetValidator.global_preset(config, GLOBAL_DEFAULT)
    assert config["user_path"]["settings_path"] == f"{folder}/"  # written back by save_loaded (file changed)
    assert config["user_path"]["telemetry_path"] == f"{windows_style}/"
    paths = FilePath()
    user = dict(config["user_path"], settings_path=folder)  # in memory too (folder set by any other way)
    paths.update(user, GLOBAL_DEFAULT["user_path"])
    assert paths.settings == f"{folder}/" and os.path.isdir(folder)


def test_b007_empty_or_complete_paths_unchanged():
    from neopedal.setting_validator import folder_path

    assert folder_path("") == ""
    assert folder_path("settings/") == "settings/" and folder_path(r"C:\NeoPedal" + "\\") == r"C:\NeoPedal" + "\\"
    assert folder_path("D:/NeoPedal/presets") == "D:/NeoPedal/presets/"


# B-025: user folder & default folder both impossible to make (read-only portable copy): os.listdir("") at start
def test_b025_folder_impossible_to_make_falls_back_to_config_folder(tmp_path, monkeypatch):
    from neopedal import setting

    config = tmp_path / "config"
    config.mkdir()
    blocked = tmp_path / "read only"  # stands for a folder that can't be made
    real = setting.set_user_data_path
    monkeypatch.setattr(setting, "set_user_data_path",
                        lambda path: "" if str(path).startswith(blocked.as_posix()) else real(path))
    paths = setting.FilePath()
    paths.config = f"{config.as_posix()}/"
    paths.update({"settings_path": f"{blocked.as_posix()}/mine/"}, {"settings_path": f"{blocked.as_posix()}/settings/"})
    assert paths.settings == f"{config.as_posix()}/settings/"  # never empty: preset list read there
    assert os.path.isdir(paths.settings)


# B-008: lap cache file touched by another reader (worker process, export): lazy columns parsed from CSV again
def test_b008_cache_touched_by_other_reader_still_used(tmp_path, monkeypatch):
    from neopedal.userfile import lap_cache
    from tests.test_bug_audit_2026_10_29_lap_race import write_lap

    folder = str(tmp_path)
    path = write_lap(folder)
    lap_cache.load_cached_lap(folder, path)  # cache made
    lap = lap_cache.load_cached_lap(folder, path)  # page: lap read from cache, columns read when used
    target = lap_cache.cache_file(folder, path)
    later = time.time() + 5
    os.utime(target, (later, later))  # worker process read the same lap meanwhile (file touched: recently used)
    calls = []
    monkeypatch.setattr(lap_cache, "load_lap", lambda name: calls.append(name))
    assert len(lap.columns["tyre_pres_fl"]) == 100
    assert not calls  # read from the cache file, CSV never parsed again


def test_b008_cache_file_replaced_columns_read_from_lap(tmp_path):
    """Cache file written again for a changed lap: columns of the older lap never read from the new file"""
    from neopedal.userfile import lap_cache
    from tests.test_bug_audit_2026_10_29_lap_race import write_lap

    folder = str(tmp_path)
    path = write_lap(folder)
    lap_cache.load_cached_lap(folder, path)
    lap = lap_cache.load_cached_lap(folder, path)
    target = lap_cache.cache_file(folder, path)
    with open(target, "r+b") as file:  # other content, same size (cache of another lap stamp)
        file.seek(lap_cache.ARRAYS_HEAD.size + 2)
        file.write(b"#")
    assert len(lap.columns["tyre_pres_fl"]) == 100  # read again from the lap file (still there, unchanged)


# B-026: lap columns dropped while iterated (cache & lap file changed): RuntimeError instead of KeyError
def test_b026_columns_dropped_during_iteration_raise_key_error(tmp_path, monkeypatch):
    from array import array

    from neopedal.userfile import lap_cache
    from neopedal.userfile.telemetry_lap import LapData

    monkeypatch.setattr(lap_cache, "load_lap", lambda path: LapData("lap", {"speed": [1.0, 2.0]}, None))
    monkeypatch.setattr(lap_cache, "columns_unreadable", lambda path, reason: None)
    entries = {"speed": (0, "d", 2), "tyre_temp_fl": (0, "d", 2)}  # second column gone from the lap file
    columns = lap_cache.CachedColumns(str(tmp_path / "gone.cache"), (0, b""), "lap.csv", entries, {})
    with pytest.raises(KeyError):  # the documented loss of a column, never "dictionary changed size"
        dict(columns.items())
    assert columns["speed"] == array("d", [1.0, 2.0]) and "tyre_temp_fl" not in columns and len(columns) == 1


# B-012: undo / redo of a stats edit whose stats were not saved while the session history changed
def test_b012_undo_history_changed_stats_unsaved_told_and_revertible(monkeypatch):
    from types import SimpleNamespace

    from neopedal.ui.quick import stats_edits
    from neopedal.ui.quick.stats_io import StatsEdit

    edits = stats_edits.StatsEdits
    removed, added = ("old session",), ("new session",)
    edit = StatsEdit(("Track", "Car"), {"pb": 90.0}, None, removed, added)  # car removed with its sessions
    monkeypatch.setattr(edits, "load_fresh_stats", classmethod(lambda cls: {}))
    monkeypatch.setattr(edits, "save_edit", staticmethod(lambda stats, gone, new, history=None: None))
    outcome, history_edit = edits.apply_edit(edit, True)  # undo: sessions back, stats file locked
    assert outcome == "history"
    assert history_edit == StatsEdit(edit.path, None, None, added, removed, history_only=True)
    told = []
    page = SimpleNamespace(_edits_undo=[], _edits_redo=[], reload_stats=lambda select=None: None,
                           stats_unreadable=lambda: told.append("unreadable"), stats_unsaved=lambda: told.append("unsaved"),
                           stats_unsaved_history_changed=lambda: told.append("history"))
    edits.edit_applied(page, (outcome, history_edit), edit, True)
    assert told == ["history"]  # not "unable to read"
    assert page._edits_undo == [edit, history_edit] and page._edits_redo == []  # Ctrl+Z reverts the history first
    monkeypatch.setattr(edits, "save_edit", staticmethod(lambda stats, gone, new, history=None: False))
    assert edits.apply_edit(edit, False) == ("unsaved", None)  # nothing changed: told it was not saved
    edits.edit_applied(page, ("unsaved", None), edit, False)
    assert told[-1] == "unsaved" and page._edits_redo == [edit]


# B-027: game answers arriving after the race calculator was turned off still filled its inputs
def test_b027_answers_after_calculator_off_ignored(race_page):  # noqa: F811
    from neopedal.process.team_usage import StintUsage
    from neopedal.ui.quick.race_team_plan import team_names
    from tests.test_race_live_data import REFUEL_SCREEN

    backend = race_page.backend
    backend.set_values({"input_drivers": 2, "input_driver_names": "A\nB"})
    backend.setGameData(False)  # turned off while the team & garage requests were on their way
    values = dict(backend.values)
    backend.received_team(([StintUsage("Bob Real", 1, 1, 10, 9, 0.05, 0.0, 1.0)], 100.0))
    backend.received_garage([REFUEL_SCREEN, None, None])
    assert backend.values == values and team_names(backend.values["input_driver_names"]) == ["A", "B"]
    assert not backend.team_request.busy and not backend.garage_request.busy


# B-010: "Minimize to tray" on a desktop without notification area: window hidden with no way back
@pytest.mark.parametrize("tray", [False, True])
def test_b010_close_without_notification_area_minimizes(main_window, monkeypatch, tray):  # noqa: F811
    from PySide6.QtGui import QCloseEvent
    from PySide6.QtWidgets import QSystemTrayIcon

    from neopedal.setting import cfg
    from neopedal.ui import app as app_module

    quits = []
    monkeypatch.setattr(app_module.AppWindow, "quit_app", lambda self: quits.append(1) or True)
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: tray))
    monkeypatch.setattr(QSystemTrayIcon, "isVisible", lambda self: tray)
    monkeypatch.setitem(cfg.application, "minimize_to_tray", True)
    main_window.show()
    event = QCloseEvent()
    main_window.closeEvent(event)
    assert not event.isAccepted() and not quits  # app keeps running either way
    if tray:
        assert main_window.isHidden()  # back from its notification area icon
    else:
        assert main_window.isVisible() and main_window.isMinimized()  # back from the task bar


# B-015: lap tooltip of the Session tab showing "Track Temp NaN" (Python None reaches QML as undefined)
def test_b015_track_temperature_tested_as_number():
    from pathlib import Path

    from PySide6.QtCore import QObject, QUrl, Slot
    from PySide6.QtQml import QQmlComponent, QQmlEngine

    class Backend(QObject):
        @Slot(result="QVariant")
        def lap(self):
            return {"temp": None}

    engine = QQmlEngine()
    backend = Backend()
    engine.rootContext().setContextProperty("backend", backend)
    component = QQmlComponent(engine)
    component.setData(b'import QtQml\nQtObject { property var lap: backend.lap()\n'
                      b'property bool isNull: lap.temp === null\nproperty bool isNumber: typeof lap.temp === "number" }',
                      QUrl())
    item = component.create()
    assert item is not None and item.property("isNull") is False  # undefined, not null: "!== null" never stops it
    assert item.property("isNumber") is False
    root = Path(__file__).resolve().parents[1]
    page = (root / "neopedal/ui/qml/telemetry/SessionView.qml").read_text(encoding="utf-8")
    assert "lap.temp !== null" not in page and 'typeof lap.temp === "number"' in page


# B-018: session name of the Broadcast Director header left shown once the game left the session
def test_b018_session_text_told_when_session_left(director_page):  # noqa: F811
    from neopedal.ui.quick.director_shared import MENU, SESSION

    backend = director_page.backend
    backend.session_key = ("Spa", "RACE1", *backend.session_key[2:])
    backend.set_state(SESSION)
    told = []
    backend.clockChanged.connect(lambda: told.append(backend.sessionText))
    backend.set_state(MENU)  # back to the menu of the game
    assert told and told[-1] == ""  # QML reads the text again: header emptied


# B-019: Test on Screen button of Overlay Options never told the test ended unless clicked on this page first
def test_b019_test_on_screen_state_followed_from_start(overlay_options):  # noqa: F811
    from neopedal.ui.overlay_test import overlay_test

    told = []
    overlay_options.previewChanged.connect(lambda: told.append(overlay_options.testing))
    overlay_test().changed.emit()  # test started elsewhere (Overlays page, wizard) or ended by itself
    assert told  # button reads "testing" again
    overlay_options.release()
    told.clear()
    overlay_test().changed.emit()  # page closed: no longer told
    assert not told


# B-020: color of note marks on the map of the track notes editor not shown again after the map config changed
def test_b020_marks_told_again_when_map_config_changes(ui_env):
    from PySide6.QtWidgets import QWidget

    from neopedal.ui.quick.track_notes_backend import TrackNotesBackend

    parent = QWidget()
    backend = TrackNotesBackend(parent)
    try:
        told = []
        backend.marksChanged.connect(lambda: told.append(backend.marksColor))
        backend._map.configChanged.emit()  # marked coordinates color changed in the map config (same marks)
        assert told
    finally:
        backend.release()
        parent.deleteLater()
        flush_deletes()


# B-021: search field of the results sessions kept its text once the backend cleared the search
def test_b021_search_field_told_when_search_cleared(results_page):  # noqa: F811
    from pathlib import Path

    backend = results_page
    path = backend.sessions[0].path
    backend.setSearch("no such track")
    assert backend.shownCount == 0
    cleared = []
    backend.searchCleared.connect(lambda: cleared.append(backend.searchText))
    assert backend.show_path(path)  # session asked by another page (driver stats, replays): filters cleared
    assert cleared == [""] and backend.shownCount > 0
    backend.setSearch("again")
    backend.clearFilters()
    assert cleared == ["", ""]
    root = Path(__file__).resolve().parents[1]
    page = (root / "neopedal/ui/qml/analysis/ResultsSessionList.qml").read_text(encoding="utf-8")
    assert "function onSearchCleared()" in page  # field emptied too


# B-022: "car left" guard of Track map & Navigation compared with the length of the vehicles data (never changes)
@pytest.mark.parametrize("modern", [False, True])
def test_b022_cars_left_never_drawn(widgets, oval, monkeypatch, modern):  # noqa: F811
    from neopedal.module_info import minfo
    from tests.test_modern_graphic_widgets import update

    monkeypatch.setattr(minfo.relative, "drawOrder", list(range(20)))
    widget = widgets("track_map", modern=modern)
    update(widget, 2)
    assert widget.map_scaled
    monkeypatch.setattr(minfo.vehicles, "totalVehicles", 5)  # 15 cars left since the draw order was made
    assert [index for index, *_ in widget.vehicle_positions()] == [0, 1, 2, 3, 4]
    navigation = widgets("navigation", modern=modern)
    update(navigation, 2)  # drawn with the cars left out (no error)


# B-023: downloaded installer left in the temporary folder after each update
def test_b023_old_update_downloads_removed(tmp_path, monkeypatch):
    import tempfile

    from neopedal import update

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    old = tmp_path / f"{update.DOWNLOAD_FOLDER_PREFIX}abc123"
    old.mkdir()
    (old / "NeoPedal-9.9.9-windows-setup.exe").write_bytes(b"MZ")
    recent = tmp_path / f"{update.DOWNLOAD_FOLDER_PREFIX}def456"  # download going on (or installer just started)
    recent.mkdir()
    other = tmp_path / "other-app-update"
    other.mkdir()
    hours_ago = time.time() - 3 * 3600
    for path in (old, old / "NeoPedal-9.9.9-windows-setup.exe", other):
        os.utime(path, (hours_ago, hours_ago))
    assert update.remove_old_downloads() == 1
    assert not old.exists() and recent.is_dir() and other.is_dir()


def test_b023_cleanup_started_once_app_started(monkeypatch):
    import threading

    from neopedal import loader, update

    done = threading.Event()
    monkeypatch.setattr(update, "remove_old_downloads", lambda: done.set() or 0)
    monkeypatch.setattr(loader, "freeze_collected", lambda: None)
    monkeypatch.setattr(loader, "start_idle_collect_timer", lambda: None)
    loader.finish_start()
    assert done.wait(5)  # in background, page & overlays never wait for the temporary folder


# B-016: retry delays of badge icons & game pictures measured with the wall clock (set back: never asked again)
class Clock:
    """Wall clock set back an hour once started, monotonic clock going on"""

    def __init__(self):
        self.wall, self.steady = 1_800_000_000.0, 1000.0

    def time(self):
        return self.wall

    def monotonic(self):
        return self.steady

    def pass_seconds(self, seconds: float, wall_back: float = 0.0):
        self.steady += seconds
        self.wall += seconds - wall_back


def test_b016_badge_retry_follows_elapsed_time(monkeypatch):
    from types import SimpleNamespace

    from neopedal.userfile import badge_icons

    clock = Clock()
    monkeypatch.setattr(badge_icons, "time", SimpleNamespace(time=clock.time, monotonic=clock.monotonic))
    icons = badge_icons.BadgeIcons()
    queued = []
    monkeypatch.setattr(icons, "_jobs", SimpleNamespace(put=queued.append, empty=lambda: True))
    monkeypatch.setattr(badge_icons.threading, "Thread", lambda **kwargs: SimpleNamespace(start=lambda: None,
                                                                                         is_alive=lambda: True))
    monkeypatch.setattr(badge_icons, "download", lambda url: b"not svg")
    monkeypatch.setattr(icons, "icon_file", lambda key: "missing/icon.svg")
    assert not icons.fetch("abc")  # failed now
    clock.pass_seconds(badge_icons.RETRY_SECONDS + 1, wall_back=3600)  # clock set back meanwhile (NTP, time zone)
    icons.request("abc")
    assert queued == ["abc"]  # asked again once the delay passed


def test_b016_game_retry_follows_elapsed_time(monkeypatch):
    from types import SimpleNamespace

    from neopedal.userfile import game_images

    clock = Clock()
    monkeypatch.setattr(game_images, "time", SimpleNamespace(time=clock.time, monotonic=clock.monotonic))
    images = game_images.GameImages()
    queued = []
    monkeypatch.setattr(images, "_jobs", SimpleNamespace(put=queued.append, empty=lambda: True))
    assert not images.game_answered(0)  # game did not answer: left alone for a while
    clock.pass_seconds(game_images.RETRY_GAME + 1, wall_back=3600)
    images.request("brand", "Porsche")
    assert queued == [("brand", "Porsche")]


# B-017: replay playback rate measured from a stale time after a pause, rates measured with the wall clock
def test_b017_replay_rate_right_after_pause(monkeypatch):
    from types import SimpleNamespace

    from neopedal.ui.quick import replays_backend

    clock = Clock()
    monkeypatch.setattr(replays_backend, "time", SimpleNamespace(time=clock.time, monotonic=clock.monotonic))
    page = SimpleNamespace(replay_time=-1.0, replay_rate=0.0, time_received=0.0, _answered=0.0, _jumped=False,
                           replayTimeChanged=SimpleNamespace(emit=lambda: None), update_timeline_end=lambda: None)
    update = replays_backend.GameReplaysBackend.update_replay_time
    update(page, 10.0)
    clock.pass_seconds(2)
    update(page, 12.0)  # playing at normal speed
    assert page.replay_rate == pytest.approx(1.0)
    for _ in range(30):  # paused a minute
        clock.pass_seconds(2)
        update(page, 12.0)
    assert page.replay_rate == 0.0
    clock.pass_seconds(2)
    update(page, 14.0)  # played again
    assert page.replay_rate == pytest.approx(1.0)  # not 2 s over the whole pause (0.03x)
    clock.pass_seconds(2, wall_back=3600)  # clock set back while playing
    update(page, 16.0)
    assert page.replay_rate == pytest.approx(1.0)


def test_b017_director_clock_rate_with_wall_clock_set_back(director_page, monkeypatch):  # noqa: F811
    from types import SimpleNamespace

    from neopedal.ui.quick import director_backend

    clock = Clock()
    monkeypatch.setattr(director_backend, "time", SimpleNamespace(time=clock.time, monotonic=clock.monotonic))
    backend = director_page.backend
    backend.session_time = -1.0
    backend.update_clock(100.0)
    clock.pass_seconds(1, wall_back=3600)
    backend.update_clock(101.0)
    assert backend.replay_rate == pytest.approx(1.0)


# B-013: game shared memory made by the app run as administrator before the game started (game may not write it)
@pytest.mark.skipif(os.name != "nt", reason="Windows shared memory")
def test_b013_elevated_app_making_game_memory_warned(monkeypatch, caplog):
    import mmap
    import uuid

    from neopedal.adapter import _sync

    name = f"NeoPedalAuditTest_{uuid.uuid4().hex}"
    monkeypatch.setattr(_sync, "running_as_admin", lambda: True)
    assert not _sync.mapping_exists(name)
    with caplog.at_level("WARNING"):
        assert _sync.warn_elevated_mapping((name,))  # game not started yet: memory made by the app
    assert "administrator" in caplog.text
    held = mmap.mmap(-1, 64, name)  # game started first: memory made by it
    try:
        assert _sync.mapping_exists(name) and not _sync.warn_elevated_mapping((name,))
    finally:
        held.close()
    monkeypatch.setattr(_sync, "running_as_admin", lambda: False)
    assert not _sync.warn_elevated_mapping((name,))  # not administrator: same rights as the game


# B-014: LMU shared memory copied while the game was writing it (lock of the game SDK never looked at)
@pytest.mark.skipif(os.name != "nt", reason="lock of the game: Windows shared memory")
def test_b014_copy_waits_while_game_holds_its_lock():
    import ctypes
    import mmap
    import uuid

    from pyLMUSharedMemory import lmu_data, lmu_mmap
    from pyLMUSharedMemory.lmu_mmap import MMapControl

    tag = uuid.uuid4().hex  # never the names of the real game (may be running on this computer)
    lock = mmap.mmap(-1, 8, f"NeoPedalAuditLock_{tag}")  # made by the "game" first: waiters, busy
    busy = ctypes.c_long.from_buffer(lock, 4)
    control = MMapControl(f"NeoPedalAuditData_{tag}", lmu_data.LMUObjectOut, lock_name=f"NeoPedalAuditLock_{tag}")
    control.create(0)
    try:
        live = control._realtime
        live.generic.events.SME_UPDATE_SCORING = 1
        live.scoring.scoringInfo.mCurrentET = 12.5
        busy.value = 1  # game writing now
        assert control.update() is False and control.data.scoring.scoringInfo.mCurrentET == 0.0
        busy.value = 0  # done: copied at the next update
        assert control.update() is True and control.data.scoring.scoringInfo.mCurrentET == 12.5
        # Game stopped while writing (lock left busy): lock let go after a while, copies go on without it
        busy.value = 1
        live.scoring.scoringInfo.mCurrentET = 13.0
        assert control.update() is False
        control._busy_since -= lmu_mmap.LOCK_STUCK_SECONDS + 0.1  # held longer than a game write
        assert control.update() is True and control.data.scoring.scoringInfo.mCurrentET == 13.0
        assert control._lock is None  # never keeps the lock memory of a stopped game alive
    finally:
        del busy, live
        control.close()
        lock.close()


# B-028: frozen app started by a launcher with a bare or relative name: working folder set from it (fonts lost)
def test_b028_frozen_app_works_in_its_own_folder(tmp_path, monkeypatch):
    import sys

    import run

    exe = tmp_path / "NeoPedal" / "neopedal.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setattr(sys, "argv", ["neopedal.exe"])  # what a launcher typed, from another folder
    assert run.start_folder() == str(exe.parent)
    monkeypatch.setattr(sys, "frozen", False)
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "src" / "run.py")])
    assert run.start_folder() == str(tmp_path / "src")  # from source: folder of run.py


# B-029: GPU vertex copy sized from vertex_count, never from the data really there (read past the buffer)
def test_b029_vertices_copied_never_past_their_data(caplog):
    from array import array

    from neopedal.ui.quick import lines

    plain = lines.Vertices(array("f", [0.0] * 6), 10)  # 3 vertices of data, 10 announced
    assert lines.drawable_count(plain, "short") == 3
    assert "short" in caplog.text
    colored = lines.Vertices(bytearray(lines.COLORED_VERTEX.size * 4), 4, colored=True)
    assert lines.drawable_count(colored, "colored") == 4  # whole data: unchanged
    exact = lines.Vertices(array("f", [0.0] * 8), 4)
    assert lines.drawable_count(exact, "exact") == 4


# B-030: end of Windows session with the window open: close done by close_at_exit, then again by Quit
def test_b030_quit_after_system_close_never_closes_twice(main_window, monkeypatch):  # noqa: F811
    from PySide6.QtWidgets import QApplication

    from neopedal import loader

    closes = []
    monkeypatch.setattr(loader, "close", lambda: closes.append(1))
    monkeypatch.setattr(QApplication, "quit", staticmethod(lambda: None))
    monkeypatch.setattr(type(main_window), "save_window_state", lambda self: None, raising=False)
    monkeypatch.setattr(main_window, "_AppWindow__break_signal", lambda: None, raising=False)
    monkeypatch.setattr(loader, "_closed", True)  # closed already by close_at_exit (aboutToQuit)
    assert main_window.quit_app()
    assert closes == []
    monkeypatch.setattr(loader, "_closed", False)
    main_window._pages_closed = False
    assert main_window.quit_app()  # Quit menu: closed here
    assert closes == [1]
