"""Bug audit of the Overlays page & overlay options (2026-11-02): regression tests of the fixed bugs

See audit_bugs_overlays_options_2026-11-02.md (B-xxx numbers).
"""

import copy

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QRect

from neopedal.setting import cfg
from neopedal.ui.quick import overlay_backend
from neopedal.ui.quick.overlay_backend import OverlayBackend
from tests.test_overlays_page_more import NAMES, FakeControl, solid


@pytest.fixture
def page(ui_env, monkeypatch):
    for name in NAMES:
        cfg.user.setting[name]["enable"] = name in ("brake_temperature", "speedometer")
    monkeypatch.setattr(overlay_backend, "render_preview", lambda name: solid("#336699"))
    monkeypatch.setattr(overlay_backend, "make_live_preview", lambda name: None)
    control = FakeControl(NAMES)
    backend = OverlayBackend(None, control, lambda name: None, lambda text: True)
    backend.test_control = control
    yield backend
    backend.close()
    backend.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QCoreApplication.processEvents()


# B-003: page undo history kept across preset loads, undo inverting the state
def test_b003_toggle_undo_never_switches_overlay_of_another_preset(page, monkeypatch):
    """Overlay switched on in preset A, preset B loaded, Ctrl+Z: overlay of B left as it is (was: switched off)"""
    monkeypatch.setattr(cfg.filename, "setting", "A.json")
    page.toggle("fuel")
    assert cfg.user.setting["fuel"]["enable"] and page.canUndo
    loaded = copy.deepcopy(cfg.user.setting)  # preset B: fuel on there by the user's choice
    monkeypatch.setattr(cfg.user, "setting", loaded)
    monkeypatch.setattr(cfg.filename, "setting", "B.json")
    page.refresh()
    assert not page.canUndo
    page.undo()
    assert cfg.user.setting["fuel"]["enable"]


def test_b003_toggle_undo_restores_state_switched_elsewhere(page):
    """Overlay switched on from the page, then off elsewhere (tray, options page): Ctrl+Z leaves it off (was: on)"""
    page.toggle("fuel")
    assert cfg.user.setting["fuel"]["enable"]
    page.test_control.toggle("fuel")
    page.refresh()
    page.undo()
    assert not cfg.user.setting["fuel"]["enable"]
    page.toggle("fuel")  # plain undo still switches back
    page.undo()
    assert not cfg.user.setting["fuel"]["enable"]


def test_b003_toast_undo_of_another_preset_does_nothing(page, monkeypatch):
    """Undo button of a toast clicked once another preset is loaded: nothing switched"""
    monkeypatch.setattr(cfg.filename, "setting", "A.json")
    toast_undo = page._push_undo("toggle", "fuel", lambda: page.test_control.toggle("fuel"))
    monkeypatch.setattr(cfg.filename, "setting", "B.json")
    before = cfg.user.setting["fuel"]["enable"]
    toast_undo()
    assert cfg.user.setting["fuel"]["enable"] == before


# B-004: Ctrl+Z of a screen view move undid the last change of the edit mode history (any overlay)
def screen_move(page, monkeypatch):
    """Running speedometer moved from the screen view (as Base.move_overlay: edit mode history & setting)"""
    from neopedal.widget._base import position_values
    from neopedal.widget._edit_mode import edit_mode

    monkeypatch.setattr(overlay_backend, "positions_locked", lambda: False)
    monkeypatch.setattr(overlay_backend, "screen_rects", lambda: [("Main", QRect(0, 0, 1920, 1080), True)])
    page._positions_locked = False
    edit_mode().history.clear()
    widget = page.test_control.widgets["speedometer"]
    widget.rect = QRect(100, 100, 200, 100)

    def move_overlay(pos, action, merge=False):
        before = position_values(widget.rect.topLeft())
        widget.rect.moveTopLeft(pos)
        cfg.user.setting["speedometer"].update(position_values(pos))
        edit_mode().record("speedometer", action, before, position_values(pos), merge)

    widget.move_overlay = move_overlay
    page.moveOverlay("speedometer", 500, 400)
    assert widget.rect.topLeft() == QPoint(500, 400)
    return widget


def test_b004_page_undo_of_move_keeps_later_change_of_another_overlay(page, monkeypatch):
    from neopedal.widget._edit_mode import edit_mode

    widget = screen_move(page, monkeypatch)
    cfg.user.setting["fuel"]["opacity"] = 0.5  # then, in game: opacity of fuel changed from its menu
    edit_mode().record("fuel", "Opacity", {"opacity": 0.9}, {"opacity": 0.5})
    page.undo()
    assert cfg.user.setting["fuel"]["opacity"] == 0.5  # was: put back to 0.9
    assert widget.rect.topLeft() == QPoint(100, 100)  # the move of the page undone
    edit_mode().history.clear()


def test_b004_page_undo_of_move_with_nothing_since(page, monkeypatch):
    from neopedal.widget._edit_mode import edit_mode

    screen_move(page, monkeypatch)
    page.undo()  # undone in edit mode history (moves the running overlay, redo kept)
    setting = cfg.user.setting["speedometer"]
    assert (setting["position_x"], setting["position_y"]) == (100, 100)
    assert edit_mode().history.peek_redo() is not None
    edit_mode().history.clear()


def test_b004_page_undo_of_move_never_undoes_later_move(page, monkeypatch):
    from neopedal.widget._edit_mode import edit_mode

    widget = screen_move(page, monkeypatch)
    widget.move_overlay(QPoint(700, 300), "Centering")  # moved again in game since
    page.undo()
    assert widget.rect.topLeft() == QPoint(700, 300)
    edit_mode().history.clear()


# B-005: friction circle (modern) drew one reference ring per G: a big Display Radius G froze the app
def test_b005_friction_circle_modern_big_radius_drawn_at_once(ui_env, bundled_fonts):
    import time

    from neopedal.ui.widget_preview import render_widget

    cfg.user.config["overlay_style"]["overlay_theme"] = "Modern Dark"
    values = dict(cfg.user.setting["friction_circle"], enable_classic_layout=False, show_reference_circle=True)
    normal = render_widget(cfg, "friction_circle", values).toImage()
    started = time.perf_counter()
    huge = render_widget(cfg, "friction_circle", dict(values, display_radius_g=1e6)).toImage()
    assert time.perf_counter() - started < 5  # was: about 50 s (one million rings & labels)
    assert not huge.isNull() and huge.size() == normal.size()


# B-006: steering meter (classic) drew every scale mark, even a pixel apart: a typo in the range froze the app
def test_b006_steering_meter_classic_huge_range_drawn_at_once(ui_env, bundled_fonts):
    import time

    from neopedal.ui.widget_preview import render_widget

    cfg.user.config["overlay_style"]["overlay_theme"] = "Legacy Dark"
    values = dict(cfg.user.setting["steering_meter"], enable_classic_layout=True, show_scale_mark=True)
    normal = render_widget(cfg, "steering_meter", dict(values, manual_steering_range=900)).toImage()
    started = time.perf_counter()
    huge = render_widget(cfg, "steering_meter", dict(values, manual_steering_range=10**9)).toImage()
    assert time.perf_counter() - started < 5  # was: about 7 s (50 million marks)
    assert not huge.isNull() and huge.size() == normal.size()


# B-001: position applied from Overlay Options or Find Option lost at next load (screen layout profile not stored)
@pytest.fixture
def options(ui_env):
    from neopedal.ui.quick.overlay_options_backend import OverlayOptionsBackend
    from tests.test_overlay_options import Control, Host

    backend = OverlayOptionsBackend(None, Host(), Control())
    yield backend
    backend.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QCoreApplication.processEvents()


def test_b001_position_applied_from_options_page_kept_at_next_load(options, monkeypatch):
    from neopedal import loader

    cfg.application["enable_layout_per_screen_setup"] = True
    monkeypatch.setattr(cfg.filename, "setting", "default.json")
    loader.sync_screen_layout()  # start: profile of this screen setup written
    before = cfg.user.setting["speedometer"]["position_x"]
    options.selectOverlay("speedometer")
    options.setNumber("speedometer/position_x", before + 300)
    assert options.apply()
    loader.sync_screen_layout()  # next start, preset reload or screen change
    assert cfg.user.setting["speedometer"]["position_x"] == before + 300


def test_b001_position_reset_from_find_option_kept_at_next_load(ui_env, monkeypatch):
    from neopedal import loader
    from neopedal.ui.quick import finder_backend

    cfg.application["enable_layout_per_screen_setup"] = True
    monkeypatch.setattr(cfg.filename, "setting", "default.json")
    monkeypatch.setattr(finder_backend, "run_after_saving", lambda callback: None)
    default = cfg.default.setting["speedometer"]["position_x"]
    cfg.user.setting["speedometer"]["position_x"] = default + 300
    loader.sync_screen_layout()
    finder = finder_backend.FinderBackend(None, lambda entry: None)
    try:
        key = next(key for key, entry in finder._by_key.items()
                   if entry.section == "speedometer" and entry.key == "position_x")
        finder.resetOption(key)
        loader.sync_screen_layout()
        assert cfg.user.setting["speedometer"]["position_x"] == default
    finally:
        finder.deleteLater()


# B-002: undo & redo of Overlay Options kept across a preset load: edit made for preset A applied to B unasked
def test_b002_redo_after_preset_load_never_applies_edit_of_other_preset(options, monkeypatch):
    oid = f"{options.overlay}/update_interval"
    monkeypatch.setattr(cfg.filename, "setting", "A.json")
    options.setNumber(oid, 77)
    options.undo()  # nothing pending
    monkeypatch.setattr(cfg.filename, "setting", "B.json")
    options.refresh()  # app refresh after the preset load
    options.redo()
    assert options.pendingCount == 0 and not options.canRedo and not options.canUndo


def test_b002_edit_typed_on_after_preset_load_asks_before_apply(options, monkeypatch):
    oid = f"{options.overlay}/update_interval"
    monkeypatch.setattr(cfg.filename, "setting", "A.json")
    options.typeText(oid, "7")
    options._pending.clear()  # same value saved meanwhile (refresh): nothing pending, marker cleared
    options.refresh()
    monkeypatch.setattr(cfg.filename, "setting", "B.json")
    options.typeText(oid, "77")  # keys typed on in the same field: merged step
    assert options._preset == "B.json"  # was "": saved into B with no question had A been loaded meanwhile


# Page rules (Overlay Options): option dimmed ("Used only while...") only while it does nothing
def dimmed(name: str, key: str, modern: bool, **values) -> bool:
    """Option row dimmed by the page for these values (on/off option it depends on, or rules of option_rules)"""
    from neopedal.ui.quick.overlay_options_backend import OverlayOptionsBackend, build_layout

    shown = dict(cfg.user.setting[name], **values)
    if "enable_classic_layout" in shown:
        shown["enable_classic_layout"] = not modern
    layout = build_layout(name, shown)
    assert key in layout.keys, f"{name}/{key} not shown"
    overrides = OverlayOptionsBackend._overrides(layout, shown)
    return (bool(OverlayOptionsBackend._off_control(layout, shown, overrides, key))
            or key in OverlayOptionsBackend._inactive(layout, shown))


DESIGNS = pytest.mark.parametrize("modern", [True, False], ids=["modern", "classic"])
HEATMAP_OVERLAYS = ("brake_temperature", "tyre_temperature", "tyre_inner_layer", "tyre_carcass", "tyre_overview",
                    "tyre_temp_trend")


# B-021: heatmap_name dimmed while used (automatic heatmap off), active while unused (on)
@DESIGNS
@pytest.mark.parametrize("name", HEATMAP_OVERLAYS)
def test_b021_heatmap_name_dimmed_only_with_automatic_heatmap(ui_env, name, modern):
    assert dimmed(name, "heatmap_name", modern, enable_heatmap_auto_matching=True)
    assert not dimmed(name, "heatmap_name", modern, enable_heatmap_auto_matching=False)


def shown_keys(name: str, modern: bool) -> tuple[str, ...]:
    from neopedal.ui.quick.overlay_options_backend import build_layout

    return build_layout(name, dict(cfg.user.setting[name], enable_classic_layout=not modern)).keys


# B-022: wheel toe section led by enable_symmetric_toe_angle (dimming every reading), totals not led by their switch
TOE_WHEEL = ("decimal_places_toe_angle", "toe_angle_smoothing_samples", "font_color_toe_angle",
             "background_color_toe_angle", "show_total_toe_angle")
TOE_TOTAL = ("decimal_places_total_toe_angle", "total_toe_angle_smoothing_samples",
             "font_color_total_toe_angle_positive", "font_color_total_toe_angle_negative",
             "background_color_total_toe_angle")


@DESIGNS
def test_b022_wheel_toe_options_follow_their_own_switch(ui_env, modern):
    keys = shown_keys("wheel_toe", modern)
    for key in (key for key in TOE_WHEEL if key in keys):
        assert not dimmed("wheel_toe", key, modern, enable_symmetric_toe_angle=False), key
    for key in (key for key in TOE_TOTAL if key in keys):
        assert not dimmed("wheel_toe", key, modern, enable_symmetric_toe_angle=False, show_total_toe_angle=True), key
        assert dimmed("wheel_toe", key, modern, show_total_toe_angle=False), key


# B-023: LED count & size dimmed while single side LEDs (default), RPM colors & off color by unrelated switches
LED_SIZE = ("number_of_led", "led_width", "led_height", "led_radius", "led_outline_color", "led_outline_width")


@DESIGNS
@pytest.mark.parametrize("name", ["rpm_led", "lift_and_coast_led"])
def test_b023_led_size_used_with_single_side_leds(ui_env, name, modern):
    for key in (key for key in LED_SIZE if key in shown_keys(name, modern)):
        assert not dimmed(name, key, modern, enable_double_side_led=False), key


@DESIGNS
def test_b023_led_colors_used_whatever_flicker_and_lift_and_coast(ui_env, modern):
    for key in (key for key in shown_keys("rpm_led", modern) if key.startswith("rpm_color_")):
        assert not dimmed("rpm_led", key, modern, show_rpm_flickering_above_critical=False), key
    if "lift_and_coast_color_off" in shown_keys("lift_and_coast_led", modern):
        assert not dimmed("lift_and_coast_led", "lift_and_coast_color_off", modern, show_lift_and_coast=False)


# B-024: manual steering range dimmed while the angle reading is hidden, though it turns the wheel & scale
@DESIGNS
@pytest.mark.parametrize("name", ["steering_wheel", "steering_meter"])
def test_b024_manual_steering_range_used_without_angle_reading(ui_env, name, modern):
    assert not dimmed(name, "manual_steering_range", modern, show_steering_angle=False)


@DESIGNS
def test_b024_steering_angle_range_used_by_steering_ratio(ui_env, modern):
    assert not dimmed("steering_angle", "manual_steering_range", modern, show_steering_angle=False,
                      show_steering_ratio=True)
    assert dimmed("steering_angle", "manual_steering_range", modern, show_steering_angle=False,
                  show_steering_ratio=False)


# B-026: countdown colors of Track Clock (classic) under enable_time_scaled_countdown (off by default)
COUNTDOWN_COLORS = ("font_color_sunlight_phase_countdown", "background_color_sunlight_phase_countdown",
                    "font_color_phase_day", "font_color_phase_night")


@DESIGNS
def test_b026_track_clock_countdown_colors_follow_countdown(ui_env, modern):
    for key in (key for key in COUNTDOWN_COLORS if key in shown_keys("track_clock", modern)):
        assert not dimmed("track_clock", key, modern, enable_time_scaled_countdown=False), key
        assert dimmed("track_clock", key, modern, show_sunlight_phase_countdown=False), key


# B-027: main background color of Delta Best (classic) under show_game_deltabest_if_available
def test_b027_deltabest_background_color_never_dimmed(ui_env):
    assert not dimmed("deltabest", "background_color_deltabest", False, show_game_deltabest_if_available=False)


# B-028: circle & map backgrounds (classic) under show_background, though drawn without the overlay background
OWN_BACKGROUNDS = (
    ("heading", "show_circle_background", "background_color_circle"),
    ("radar", "show_circle_background", "background_color_circle"),
    ("wind_direction", "show_circle_background", "background_color_circle"),
    ("friction_circle", "show_circle_background", "background_color_circle"),
    ("steering_wheel", "show_circle_background", "background_color_circle"),
    ("track_map", "show_map_background", "background_color_map"),
    ("elevation", "show_elevation_background", "background_color_elevation"),
)


@pytest.mark.parametrize(("name", "switch", "color"), OWN_BACKGROUNDS)
def test_b028_own_background_follows_its_switch_only(ui_env, name, switch, color):
    assert not dimmed(name, switch, False, show_background=False)
    assert not dimmed(name, color, False, show_background=False, **{switch: True})
    assert dimmed(name, color, False, show_background=True, **{switch: False})


def test_b028_friction_circle_fade_follows_circle_background(ui_env):
    assert dimmed("friction_circle", "show_fade_out", False, show_circle_background=False)
    assert dimmed("friction_circle", "fade_in_radius", False, show_circle_background=True, show_fade_out=False)
    assert not dimmed("friction_circle", "fade_out_radius", False, show_background=False,
                      show_circle_background=True, show_fade_out=True)


# B-029: Navigation car options under show_circle_vehicle_shape (arrow by default), text colors under no switch
NAV_CARS = ("vehicle_size", "vehicle_offset", "vehicle_color_player", "vehicle_outline_width_player",
            "vehicle_outline_color_player", "vehicle_color_leader", "vehicle_color_same_lap", "vehicle_color_laps_ahead",
            "vehicle_color_laps_behind", "vehicle_color_in_pit", "vehicle_color_yellow", "vehicle_outline_color",
            "vehicle_outline_width")


@DESIGNS
def test_b029_navigation_car_options_used_with_arrow_shape(ui_env, modern):
    keys = shown_keys("navigation", modern)
    for key in (key for key in NAV_CARS if key in keys):
        assert not dimmed("navigation", key, modern, show_circle_vehicle_shape=False), key
    for key in (key for key in ("font_color", "font_color_player") if key in keys):
        assert dimmed("navigation", key, modern, show_vehicle_class_standings=False), key


# B-025: Trailing pedal bars: options under show_ffb_bar or brake pressure, alerts under each other, shared colors
@DESIGNS
def test_b025_trailing_pedal_bar_options_follow_pedal_bars(ui_env, modern):
    bars = {"show_pedal_bars": True}
    assert dimmed("trailing", "pedal_bar_width_filtered", modern, show_pedal_bars=False)
    assert not dimmed("trailing", "pedal_bar_width_filtered", modern, show_ffb_bar=False, **bars)
    assert not dimmed("trailing", "pedal_bar_inner_gap", modern, show_pedal_bar_brake_pressure=False, **bars)
    assert not dimmed("trailing", "show_abs_activation_flash", modern, show_tc_activation_flash=False, **bars)
    assert not dimmed("trailing", "show_wheel_slip_flash", modern, show_wheel_lock_flash=False, **bars)
    assert dimmed("trailing", "show_throttle_bar", modern, show_pedal_bars=False)


def test_b025_trailing_classic_colors_of_trace_or_bar(ui_env):
    assert not dimmed("trailing", "throttle_color", False, show_throttle=False, show_pedal_bars=True)
    assert dimmed("trailing", "throttle_color", False, show_throttle=False, show_pedal_bars=False)
    assert not dimmed("trailing", "tc_activation_color", False, show_tc_activation=False, show_pedal_bars=True,
                      show_tc_activation_flash=True)


# B-009: Reset Overlay put the overlay back to its default position too
def test_b009_reset_overlay_keeps_position(options):
    setting = cfg.user.setting["speedometer"]
    setting.update(position_x=999, position_y=777, opacity=0.5)
    options.selectOverlay("speedometer")
    options.resetOverlay()
    assert options._pending.get("speedometer/opacity") == cfg.default.setting["speedometer"]["opacity"]
    assert "speedometer/position_x" not in options._pending and "speedometer/position_y" not in options._pending


# B-011: Reset Overlay wiped the user profiles of the Black Box (options hidden from the page)
def test_b011_reset_overlay_keeps_hidden_user_profiles(options):
    cfg.user.setting["black_box"]["user_profile_3"] = "show_tyre_compound:1"
    cfg.user.setting["black_box"]["opacity"] = 0.5
    options.selectOverlay("black_box")
    options.resetOverlay()
    assert "black_box/opacity" in options._pending
    assert not any(oid.startswith("black_box/user_profile_") for oid in options._pending)


# B-010: user profile saved while auto compact mode hid items: those items stayed hidden at full size
def test_b010_user_profile_saved_in_compact_mode_keeps_shown_items(options):
    from neopedal.template.widget.black_box_ui import COMPACT_HIDDEN, parse_user_profile

    setting = cfg.user.setting["black_box"]
    setting.update(display_profile="Custom", auto_compact_display_scale=0.8, display_scale=0.6,
                   show_tyre_compound=True)
    options.selectOverlay("black_box")
    options.saveUserProfile("User 1")
    saved = parse_user_profile(options._pending["black_box/user_profile_1"])
    assert "show_tyre_compound" in COMPACT_HIDDEN and saved.get("show_tyre_compound", True)



# B-013: split mode on: combined mode car count dimmed, though it is the limit of single class sessions
def test_b013_combined_car_count_active_in_split_mode(ui_env):
    assert not dimmed("standings", "maximum_vehicles_combined_mode", True, enable_multi_class_split_mode=True,
                      enable_single_class_exclusive_mode=False)
    assert dimmed("standings", "maximum_vehicles_combined_mode", True, enable_single_class_exclusive_mode=True)


# B-012: Color theme of the modern Black Box wrote colors the modern design hides (frozen, theme of design lost)
def test_b012_color_themes_of_classic_black_box_only(options):
    cfg.user.setting["black_box"]["enable_classic_layout"] = False
    options.selectOverlay("black_box")
    assert options.overlayInfo["themes"] == []
    options.applyColorTheme("Colorblind Safe")
    assert not options._pending
    cfg.user.setting["black_box"]["enable_classic_layout"] = True
    options.refresh()
    assert options.overlayInfo["themes"]


# B-014: Standings (classic): every class mode option under split mode (exclusive & combined modes dimmed)
def test_b014_classic_standings_class_modes(ui_env):
    no_split = {"enable_multi_class_split_mode": False}
    for key in ("enable_single_class_exclusive_mode", "maximum_vehicles_combined_mode", "minimum_top_vehicles",
                "split_gap"):
        assert not dimmed("standings", key, False, **no_split), key
    assert not dimmed("standings", "maximum_vehicles_exclusive_mode", False, enable_single_class_exclusive_mode=True,
                      **no_split)
    assert dimmed("standings", "maximum_vehicles_exclusive_mode", False, enable_single_class_exclusive_mode=False)
    assert dimmed("standings", "maximum_vehicles_split_mode", False, enable_single_class_exclusive_mode=True)
    assert dimmed("standings", "show_time_gap_from_same_class", False, enable_single_class_exclusive_mode=False,
                  **no_split)


# B-008: screen view: overlay dropped where no screen is (screens of different sizes), invisible
def test_b008_screen_view_keeps_overlay_on_a_screen(page, monkeypatch):
    screens = [("Big", QRect(0, 0, 2560, 1440), True), ("Small", QRect(2560, 0, 1920, 1080), False)]
    monkeypatch.setattr(overlay_backend, "screen_rects", lambda: screens)
    monkeypatch.setattr(overlay_backend, "positions_locked", lambda: False)
    page._positions_locked = False
    widget = page.test_control.widgets["speedometer"]
    widget.rect = QRect(100, 100, 200, 100)
    page.moveOverlay("speedometer", 3500, 1300)
    assert any(rect.contains(widget.rect) for _, rect, _ in screens), widget.rect
    place = page.snapOverlay("speedometer", 3500, 1300, 8, False)
    assert any(rect.contains(QRect(place["x"], place["y"], 200, 100)) for _, rect, _ in screens), place


# B-007: overlay switched on while a preset reload stopped the modules: ran with the old preset, off in the new one
def test_b007_module_switched_on_during_reload_follows_loaded_preset(ui_env, monkeypatch):
    from types import SimpleNamespace

    from neopedal.const_file import ConfigType
    from neopedal.module_control import ModuleControl

    class Module:
        def __init__(self, config, name):
            self.setting = config.user.setting[name]  # as overlays: options of the preset at start
            self.closed = False

        def start(self):
            pass

        def stop(self, discard=False):
            self.closed = True

    names = ["module_force", "module_fuel"]
    control = ModuleControl(SimpleNamespace(__all__=names, **{name: SimpleNamespace(Realtime=Module) for name in names}),
                            ConfigType.MODULE)
    monkeypatch.setitem(cfg.user.setting["module_force"], "enable", True)
    monkeypatch.setitem(cfg.user.setting["module_fuel"], "enable", False)
    control.start()
    control.stop_all()  # reload: modules stopping, GUI running
    control.toggle("module_fuel", wait=True)  # switched on meanwhile
    loaded = copy.deepcopy(cfg.user.setting)  # preset loaded: fuel off there
    loaded["module_fuel"]["enable"] = False
    monkeypatch.setattr(cfg.user, "setting", loaded)
    control.wait_stopping()
    control.start()
    assert "module_fuel" not in control.active_modules  # was: kept running with the preset left
    control.toggle("module_fuel", wait=True)  # on in the loaded preset
    control.stop_all()
    control.toggle("module_force", wait=True)
    control.toggle("module_force", wait=True)  # off & on during reload: started with the preset left
    reloaded = copy.deepcopy(cfg.user.setting)  # same preset loaded again
    monkeypatch.setattr(cfg.user, "setting", reloaded)
    control.wait_stopping()
    control.start()
    assert control.active_modules["module_force"].setting is reloaded["module_force"]
    assert control.active_modules["module_fuel"].setting is reloaded["module_fuel"]
    control.close(wait=True)
