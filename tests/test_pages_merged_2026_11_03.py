"""Pages merged 2026-11-03: the 7 editors in one Data Editors page (one tab each), Pace Notes page in its Notes tab,
Overlay Performance in a tab of the Modules page, Plugin Manager opened from the Overlays page, Tools page left out
(Tools menu & command palette); former paths & keys (navigation bar, quick access, pages reopened, links) lead to
the new places"""

import warnings
from contextlib import suppress

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QSystemTrayIcon

from neopedal import app_signal
from neopedal.setting import cfg
from tests.test_perf_page_state import qml_warnings  # noqa: F401


def flush():
    for _ in range(3):
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QCoreApplication.processEvents()


@pytest.fixture
def window(ui_env, monkeypatch):
    from neopedal.ui import app as app_module

    monkeypatch.setattr(app_module.AppWindow, "set_window_state", lambda self: None)
    cfg.application["show_setup_wizard_at_startup"] = False
    main = app_module.AppWindow()
    yield main
    for page in main.centralWidget().dialog_pages():
        if page.dialog is not None:
            with suppress(AttributeError):
                page.dialog.set_unmodified()
            page.dialog.close()
    tray = main.findChild(QSystemTrayIcon)
    if tray:
        tray.hide()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for signal in (app_signal.hotkey, app_signal.refresh, app_signal.quitapp, app_signal.reload, app_signal.updates):
            with suppress(RuntimeError, TypeError):
                signal.disconnect()
    main.deleteLater()
    flush()


def data_page(window):
    return next(page for page in window.centralWidget().dialog_pages()
                if page.dialog is not None and type(page.dialog).__name__ == "DataEditors")


# Registry & saved keys
def test_registry_after_merge():
    from neopedal.template.page_registry import DATA_EDITOR_TABS, main_pages, page_spec, tool_pages
    from neopedal.ui.tools_view import LISTED_TOOL_SECTIONS

    assert [page.name for page in main_pages()] == ["home", "widget", "preset"]
    tools = {page.name for page in tool_pages()}
    assert "data_editors" in tools and "track_map_viewer" not in tools
    assert not tools & {key for key, _, _ in DATA_EDITOR_TABS}
    listed = [path for _, entries in LISTED_TOOL_SECTIONS for _, _, path in entries]
    assert "data_editors.DataEditors" in listed
    for hidden in ("plugin_manager", "perf_view"):  # pages of a button (Overlays, Settings > Modules) & palette
        assert page_spec(hidden) is not None and f"{hidden}." not in " ".join(listed)


def test_former_keys_of_bar_and_quick_access():
    from neopedal.ui.home_view import parse_quick_items
    from neopedal.ui.nav_rail import parse_rail_items

    saved = "home,brake_editor,pacenotes,heatmap_editor,tools,track_notes_editor,lap_viewer,module,hotkey,spectate"
    assert parse_rail_items(saved) == ["home", "data_editors", "lap_viewer", "app_settings", "broadcast_director"]
    assert parse_quick_items("pacenotes,tools,track_map_viewer,module") == ["data_editors", "app_settings"]


def test_settings_migrated_once():
    from neopedal.setting_preupdate import preupdate_global_setting

    for old, new in ((0, 0), (1, 1), (2, 0), (3, 2), (4, 0), (5, 0), (6, 0), (7, 0)):
        setting = {"application": {"last_page_index": old, "enable_global_hotkey": False},
                   "notification": {"notify_global_hotkey": True}}
        preupdate_global_setting((2, 51, 10), setting)
        assert setting["application"] == {"last_page_index": new}, old  # hotkeys always on: switch dropped
        assert setting["notification"] == {}
    setting = {"application": {"last_page_index": 2}}
    preupdate_global_setting((2, 51, 11), setting)  # done once
    assert setting["application"]["last_page_index"] == 2


# Data Editors
def test_former_editor_path_opens_its_tab(window):
    from neopedal.template.page_registry import DATA_EDITOR_TABS
    from neopedal.ui.data_editors import DataEditors
    from neopedal.ui.tools_view import open_tool

    window.show()
    for key, _, path in DATA_EDITOR_TABS:
        editor = open_tool(path, window)
        assert type(editor).__name__ == path.rsplit(".", 1)[-1]
        page = data_page(window)
        assert page.dialog.tabs.current_key() == key and editor.isVisible()
        assert editor.windowFlags() & Qt.WindowType.Window != Qt.WindowType.Window  # inside the page
    assert len(window.centralWidget().dialog_pages()) == 1  # one page, tabs made once each
    assert DataEditors.last_tab == "track_notes_editor"
    assert open_tool("data_editors.DataEditors", window) is data_page(window).dialog


def test_unsaved_tab_marked_saved_by_ctrl_s_and_asked_on_close(window, monkeypatch):
    from neopedal.ui.tools_view import open_tool

    window.show()
    brakes = open_tool("brake_editor.BrakeEditor", window)
    classes = open_tool("vehicle_class_editor.VehicleClassEditor", window)
    page = data_page(window)
    dialog = page.dialog
    brakes.set_modified()
    flush()
    assert dialog.is_modified() and page.is_modified()
    assert dialog.tabs.tab_bar.tabText(dialog.tabs.index_of("brake_editor")).startswith("• ")
    saved = []
    monkeypatch.setattr(classes.backend, "save", lambda: saved.append("classes"))
    assert dialog.save_action() is not None
    dialog.save_by_shortcut()  # Ctrl+S: tab shown (classes) only
    assert saved == ["classes"]
    asked = []

    def refuse():
        asked.append(dialog.tabs.current_key())
        return False

    monkeypatch.setattr(brakes, "confirm_discard", refuse)
    dialog.close()  # Cancel: page kept, tab with changes shown
    flush()
    assert asked == ["brake_editor"] and window.centralWidget().dialog_pages()
    monkeypatch.setattr(brakes, "confirm_discard", lambda: True)
    dialog.close()
    flush()
    assert not window.centralWidget().dialog_pages()


def test_escape_in_a_tab_closes_the_page(window):
    from neopedal.ui.tools_view import open_tool

    window.show()
    editor = open_tool("tyre_compound_editor.TyreCompoundEditor", window)
    flush()
    QCoreApplication.sendEvent(editor, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    flush()
    assert not window.centralWidget().dialog_pages()  # whole page closed, not the tab alone


def test_editor_page_reopened_at_startup(window):
    view = window.centralWidget()
    view.restore_pages(["*heatmap_editor.HeatmapEditor"])  # saved by an older version
    flush()
    assert [type(page.dialog).__name__ for page in view.dialog_pages()] == ["DataEditors"]


# Pace notes playback: Notes tab
def test_notes_tab_turns_pace_notes_playback_on_and_off(window):
    from neopedal.ui.tools_view import open_tool

    window.show()  # saving disabled by ui_env
    notes = open_tool("track_notes_editor.TrackNotesEditor", window)
    backend = notes.backend
    changes = []
    backend.playbackChanged.connect(lambda: changes.append(backend.playback))
    cfg.user.setting["pace_notes_playback"]["enable"] = False
    backend.setPlayback(True)
    assert cfg.user.setting["pace_notes_playback"]["enable"] is True and changes[-1] is True
    backend.setPlayback(False)
    assert cfg.user.setting["pace_notes_playback"]["enable"] is False and changes[-1] is False
    flush()
    assert notes.view.status() == notes.view.Status.Ready, notes.view.errors()


def test_pace_notes_notice_opens_notes_tab(window):
    from neopedal.ui import notification

    link = next(link for key, _, link in notification.MODE_NOTICES if key == "pace_notes_playback")
    window.show()
    notification.run_notification_action(window, link)
    assert data_page(window).dialog.tabs.current_key() == "track_notes_editor"


# Settings: Modules & Hotkeys categories
@pytest.mark.parametrize("category, qml, context", [
    ("modules", "Modules.qml", "moduleBackend"), ("hotkeys", "Hotkeys.qml", "hotkeyBackend")])
def test_settings_category_shows_former_page(window, qml_warnings, category, qml, context):  # noqa: F811
    from PySide6.QtCore import QObject

    from neopedal.ui.app_settings import open_app_settings

    window.show()
    settings = open_app_settings(window, category)
    flush()
    assert settings.backend.category == category
    loader = settings.view.rootObject().findChild(QObject, "embeddedPage")
    assert loader.property("active") and loader.property("item") is not None
    assert settings.view.rootContext().contextProperty(context) is settings.hosts[category].backend
    assert settings._host_shown == category  # its backend told the page shows
    settings.backend.selectCategory("application")
    flush()
    assert not loader.property("active") and settings._host_shown == ""
    assert not [warning for warning in qml_warnings if qml in warning or "Settings.qml" in warning], qml_warnings


def test_module_gear_opens_module_options_in_same_page(window):
    from neopedal.ui.app_settings import open_app_settings

    settings = open_app_settings(window, "modules")
    module = next(iter(settings.hosts["modules"].backend._control.names))
    settings.hosts["modules"].backend._open_config(module)
    assert settings.backend.category == module  # module options: its category of the same Settings page


def test_performance_button_opens_page(window):
    from neopedal.ui.app_settings import open_app_settings

    window.show()
    settings = open_app_settings(window, "modules")
    settings.hosts["modules"].backend.openPerformance()
    flush()
    assert type(window.centralWidget().current_page().dialog).__name__ == "PerformanceView"


def test_global_hotkeys_always_on(ui_env, monkeypatch):
    from neopedal import hotkey_control
    from neopedal.ui.quick.hotkey_backend import HotkeyBackend

    assert "enable_global_hotkey" not in cfg.application
    started = []
    monkeypatch.setattr(hotkey_control.threading, "Thread", lambda **kwargs: started.append(kwargs) or FakeThread())
    control = hotkey_control.HotkeyControl()
    monkeypatch.setattr(hotkey_control, "gather_command", lambda commands: {})
    control.enable()
    assert not started  # no hotkey bound: no thread started then stopped at once (log lines 0.3 s apart)
    monkeypatch.setattr(hotkey_control, "gather_command", lambda commands: {(1,): []})
    control.enable()
    assert started and started[0]["name"] == "Hotkey control"  # no switch to check
    backend = HotkeyBackend(None)
    try:
        assert not hasattr(backend, "setEnabled")
        backend.startCapture(next(iter(cfg.user.shortcuts)))
        assert backend.captureKey  # capture always possible
        backend.cancelCapture()
    finally:
        backend.release()


class FakeThread:
    def start(self):
        pass

    def is_alive(self):
        return False


# Tools menu & palette: one list of pages
def test_tools_menu_is_one_pages_list(window, monkeypatch):
    from neopedal.ui import nav_rail
    from neopedal.ui.menu import ToolsMenu

    tools = window.findChild(ToolsMenu)
    assert not [action for action in tools.actions() if action.menu() is not None]  # no Pages submenu
    monkeypatch.setattr(nav_rail, "current_rail_items", lambda: ["home"])
    tools.aboutToShow.emit()
    shown = [action.text() for action in tools.actions() if action.isVisible() and not action.isSeparator()]
    assert shown[:2] == ["Overlays", "Presets"] and "Data Editors" in shown and "Home" not in shown
    assert not tools.actions()[0].isSeparator() or not tools.actions()[0].isVisible()


def test_palette_lists_tools_as_pages(window):
    from neopedal.ui.command_palette import build_commands

    groups = {command.title: command.kind for command in build_commands(window)}
    assert groups["Lap Telemetry Viewer"] == groups["Presets"] == "Pages"
    assert groups["Modules"] == groups["Hotkeys"] == "Settings"  # Settings categories


# Tracks tab: map of the selected track
def test_tracks_tab_map_marks_and_set_from_map(window, monkeypatch):
    from neopedal.template.page_registry import MAP_VIEWER_PATH
    from neopedal.ui import track_info_editor
    from neopedal.ui.tools_view import open_tool

    window.show()
    tracks = open_tool(MAP_VIEWER_PATH, window)  # former Track Map Viewer: Tracks tab
    assert isinstance(tracks, track_info_editor.TrackInfoEditor) and tracks.map_viewer is not None
    backend = tracks.backend
    backend.set_rows([backend.new_row("Test Track")])
    name = "Test Track"
    viewer = tracks.map_viewer.backend
    monkeypatch.setattr(viewer, "raw_coords", [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)])
    monkeypatch.setattr(viewer, "raw_dists", [(0.0, 0.0), (100.0, 0.0), (200.0, 0.0)])
    monkeypatch.setattr(viewer, "map_name", name)
    monkeypatch.setattr(viewer, "map_length", 200.0)
    monkeypatch.setattr(viewer, "_position", 150.0)  # map position cursor
    assert tracks.show_track(name)
    row = backend.rows[0]
    row[track_info_editor.PIT_ENTRY] = 50.0
    tracks.update_marks()
    assert [mark["text"] for mark in viewer.marks][:1] == ["Pit entry"]
    monkeypatch.setattr(viewer, "map_name", "Other track")  # map of the track not read yet (read in background)
    tracks.update_marks()
    assert viewer.marks == []  # never on the map of another track
    monkeypatch.setattr(viewer, "map_name", name)
    viewer.mapChanged.emit()  # map read: marks of the selected track shown
    assert [mark["text"] for mark in viewer.marks][:1] == ["Pit entry"]
    asked = []
    monkeypatch.setattr(backend, "ask", lambda *args: asked.append(args))
    backend.mapAction(backend.currentKey, track_info_editor.PIT_EXIT)
    assert asked and asked[0][3:] == ("set_value", backend.currentKey, track_info_editor.PIT_EXIT, 150.0)
    warned = []
    monkeypatch.setattr(tracks, "warn", warned.append)
    monkeypatch.setattr(viewer, "map_name", "Other track")
    backend.mapAction(backend.currentKey, track_info_editor.PIT_EXIT)
    assert warned  # map of another track: nothing set
    tracks.set_unmodified()


# Broadcast Director: Spectate tab
def test_spectate_tab_of_director(window, monkeypatch):
    from neopedal.ui import notification
    from neopedal.ui.broadcast_director import BroadcastDirector
    from neopedal.ui.spectate_view import SpectateList

    monkeypatch.setattr(BroadcastDirector, "last_tab", "")
    window.show()
    link = next(link for key, _, link in notification.MODE_NOTICES if key == "spectate_mode")
    notification.run_notification_action(window, link)
    flush()
    page = window.centralWidget().current_page()
    assert isinstance(page.dialog, BroadcastDirector) and page.dialog.tabs.current_key() == "spectate"
    assert isinstance(page.dialog.tabs.page(1), SpectateList) and not page.dialog._director_shown
    page.dialog.show_tab("director")
    assert page.dialog._director_shown  # game asked only while the director tab shows
    page.dialog.close()
    flush()


def test_director_opens_on_spectate_without_lmu(ui_env, monkeypatch):
    from neopedal.setting import Setting
    from neopedal.ui.broadcast_director import BroadcastDirector

    monkeypatch.setattr(BroadcastDirector, "last_tab", "")
    monkeypatch.setattr(Setting, "api_key", property(lambda self: "api_rf2"))
    director = BroadcastDirector(None)
    try:
        assert director.tabs.current_key() == "spectate"
    finally:
        director.close()
        flush()


# Overlays page: Plugins button
def test_plugins_button_opens_plugin_manager(window):
    from neopedal.ui.nav_rail import PAGE_INDEX
    from neopedal.ui.overlay_view import OverlayView

    window.show()
    view = window.centralWidget()
    view.select_page(PAGE_INDEX["widget"])
    overlays = window.findChild(OverlayView)
    overlays.backend.openPlugins()
    flush()
    page = view.dialog_pages()[0]
    assert type(page.dialog).__name__ == "PluginManager" and page._button_crumb.text() == "Overlays"
