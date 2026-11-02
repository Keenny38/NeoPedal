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


# B-018: Delta Best delta range 0 or negative: every delta shown as 0, or with the wrong sign
def picture(name: str, modern: bool, **values) -> bytes:
    from neopedal.ui.widget_preview import render_widget

    cfg.user.config["overlay_style"]["overlay_theme"] = "Modern Dark" if modern else "Legacy Dark"
    shown = dict(cfg.user.setting[name], enable_classic_layout=not modern, **values)
    render_widget(cfg, name, shown)  # first render of a process: glyphs drawn slightly differently
    image = render_widget(cfg, name, shown).toImage()
    return bytes(image.constBits())


@DESIGNS
@pytest.mark.parametrize("name", ["deltabest", "deltabest_extended"])
def test_b018_delta_range_kept_positive(ui_env, bundled_fonts, name, modern):
    assert picture(name, modern, delta_display_range=-2) == picture(name, modern, delta_display_range=2)
    assert picture(name, modern, delta_display_range=0) == picture(name, modern, delta_display_range=0.001)


# B-019: Brake Bias (modern): boxes sized for the default decimal places, more decimals cut with "..."
def picture_width(name: str, modern: bool, **values) -> int:
    from neopedal.ui.widget_preview import render_widget

    cfg.user.config["overlay_style"]["overlay_theme"] = "Modern Dark" if modern else "Legacy Dark"
    return render_widget(cfg, name, dict(cfg.user.setting[name], enable_classic_layout=not modern, **values)).width()


@pytest.mark.parametrize("key", ["decimal_places_brake_bias", "decimal_places_baseline_bias_delta",
                                 "decimal_places_brake_migration"])
def test_b019_brake_bias_modern_boxes_fit_decimal_places(ui_env, bundled_fonts, key):
    default = cfg.user.setting["brake_bias"][key]
    assert picture_width("brake_bias", True, **{key: default + 2}) > picture_width("brake_bias", True)


# B-020: Fuel & Virtual Energy (classic): start & refill marks drawn out of the bar at 100 % (full tank)
def test_b020_level_marks_kept_inside_bar(ui_env):
    from neopedal.widget._painter import FuelLevelBar

    bar = FuelLevelBar(None, width=150, height=10, start_mark_width=3, refill_mark_width=3, input_color="#FFFFFF",
                       bg_color="#000000", start_mark_color="#FF0000", refill_mark_color="#00FF00",
                       show_start_mark=True, show_refill_mark=True)
    try:
        bar.update_input(0.5, 1.0, 1.2)  # started full, refill above the tank (full tank needed)
        assert bar.rect_start.right() <= 150 and bar.rect_refuel.right() <= 150
        bar.update_input(0.5, 0.4, 0.6)  # inside: drawn where they were
        assert bar.rect_start.left() == 60 and bar.rect_refuel.left() == 90
    finally:
        bar.deleteLater()


# B-015: pace notes volume (and update interval) changed while playing: kept until the car is reset
def test_b015_pace_notes_volume_change_applied(ui_env):
    pytest.importorskip("PySide6.QtMultimedia")
    from neopedal import realtime_state
    from neopedal.ui.pace_notes_view import PaceNotesPlayback

    mcfg = cfg.user.setting["pace_notes_playback"]
    mcfg.update(enable=True, pace_notes_sound_volume=50)
    playback = PaceNotesPlayback(None)
    player = playback.player
    try:
        player.reset_playback(realtime_state.resets)
        mcfg["pace_notes_sound_volume"] = 10  # saved in Settings page
        playback.refresh(True)  # app refresh after saving
        assert player.audio_device.volume() == pytest.approx(0.1)
    finally:
        player._update_timer.stop()
        mcfg["enable"] = False
        playback.refresh(True)
        playback.deleteLater()


# B-016: Radar radius & scale accepted by the page made drawing pictures of 20000 pixels (GB of memory)
@DESIGNS
def test_b016_radar_area_kept_reasonable(ui_env, modern):
    from neopedal.widget.radar import RadarMixin

    class Radar(RadarMixin):
        def __init__(self, wcfg):
            self.wcfg = wcfg

    radar = Radar(dict(cfg.user.setting["radar"], radar_radius=200, global_scale=50))
    radar.setup_radar()
    assert radar.area_size <= 4096 and radar.global_scale == radar.area_center / radar.radar_radius
    normal = Radar(dict(cfg.user.setting["radar"]))
    normal.setup_radar()
    assert normal.area_center == round(normal.radar_radius * cfg.user.setting["radar"]["global_scale"])
    if modern:
        from neopedal.widget._modern.radar import Realtime

        assert Realtime.area_size_option(radar) == radar.area_size


# B-017: line widths up to 4000 (Trailing: 30 ms of work per update on the GUI thread, every overlay slowed)
def test_b017_line_width_limited(ui_env):
    from neopedal.template.option_limits import clamp_to_limit, option_limit
    from neopedal.ui.widget_preview import _with_preview_widget

    assert option_limit("throttle_line_width").maximum == 50 and clamp_to_limit("start_line_width", 4000) == 50
    cfg.user.config["overlay_style"]["overlay_theme"] = "Legacy Dark"
    values = dict(cfg.user.setting["trailing"], enable_classic_layout=True, throttle_line_width=4000)
    assert _with_preview_widget(cfg, "trailing", values, 1.0, lambda widget: widget.samples_offset) <= 51


# B-034: Black Box options dimmed under one part while used by another one shown
BLACK_BOX_SHARED = (
    ("status_icon_scale", {"show_headlights_indicator": False, "show_wipers_indicator": True}),
    ("status_icons_side", {"show_headlights_indicator": False, "show_engine_status": True}),
    ("warning_outline_width", {"show_slip_warning": False, "show_tyre_status": True}),
    ("tyre_temperature_warning_threshold", {"show_tyre_temperature": False, "show_tyre_surface_overheat": True}),
    ("throttle_color", {"show_pedal_bars": False, "show_incident_recorder": True}),
    ("pedal_input_source", {"show_pedal_bars": False, "show_incident_recorder": True}),
    ("abs_active_color", {"show_abs_indicator": False, "show_incident_recorder": True}),
    ("tc_active_color", {"show_tc_indicator": False, "show_incident_recorder": True}),
    ("damage_panel_suspension_light_threshold", {"show_damage_panel": False, "show_suspension": True,
                                                 "show_coilover_damage": True}),
    ("gauge_refill_mark_color", {"show_gauge_refill_mark": False}),
)


@pytest.mark.parametrize(("key", "values"), BLACK_BOX_SHARED)
def test_b034_black_box_shared_options_active_while_used(ui_env, key, values):
    assert not dimmed("black_box", key, False, display_profile="Custom", **values)  # classic: every color shown


def test_b034_black_box_shared_options_dimmed_when_unused(ui_env):
    assert dimmed("black_box", "status_icon_scale", False, display_profile="Custom", show_headlights_indicator=False,
                  show_wipers_indicator=False, show_engine_status=False)


# B-035: Black Box options of the event log & incident recorder active while both are off
def test_b035_black_box_log_and_recorder_options_follow_them(ui_env):
    off = {"display_profile": "Custom", "show_event_log": False, "show_incident_recorder": False}
    for key in ("event_log_line_scale", "damage_event_threshold", "incident_color"):
        assert dimmed("black_box", key, False, **off), key
    assert not dimmed("black_box", "damage_event_threshold", False, **dict(off, show_incident_recorder=True))
    assert not dimmed("black_box", "event_log_line_scale", False, **dict(off, show_event_log=True))


# B-036: Black Box font offset options shown, never read by its designs (dead options): hidden
def test_b036_black_box_dead_font_offset_options_hidden(ui_env):
    for modern in (True, False):
        keys = shown_keys("black_box", modern)
        assert "enable_auto_font_offset" not in keys and "font_offset_vertical" not in keys


# B-040: Brake Temperature options active while unused (modern off brake duration, classic swap style colors)
def test_b040_brake_temperature_unused_options_dimmed(ui_env):
    assert dimmed("brake_temperature", "off_brake_duration", True, show_average=False)
    assert dimmed("brake_temperature", "background_color_temperature", False, swap_style=False)
    assert not dimmed("brake_temperature", "font_color_temperature", False, swap_style=False)
    assert dimmed("brake_temperature", "font_color_temperature", False, swap_style=True)
    assert not dimmed("brake_temperature", "background_color_temperature", False, swap_style=True)


# B-041: Damage integrity color dimmed by show_inverted_integrity, integrity options active without the reading
@DESIGNS
def test_b041_damage_integrity_options_follow_reading(ui_env, modern):
    keys = shown_keys("damage", modern)
    if "font_color_integrity" in keys:
        assert not dimmed("damage", "font_color_integrity", modern, show_inverted_integrity=False)
    for key in ("show_inverted_integrity", "show_aero_integrity_if_available"):
        assert dimmed("damage", key, modern, show_integrity_reading=False), key


# B-042: Damage Stats (classic) prefixes active while prefixes hidden
def test_b042_damage_stats_prefixes_follow_prefix_switch(ui_env):
    assert dimmed("damage_stats", "prefix_aero_integrity", False, show_integrity_prefix=False)


# B-043: Force (classic) lift force color active without downforce rows
def test_b043_force_lift_color_follows_downforce_rows(ui_env):
    assert dimmed("force", "warning_color_liftforce", False, show_front_downforce=False, show_rear_downforce=False)
    assert not dimmed("force", "warning_color_liftforce", False, show_front_downforce=False, show_rear_downforce=True)


# B-044: gauge overlays (classic) bar gap active without the caption it spaces
@pytest.mark.parametrize("name", ["brake_pressure", "ride_height", "suspension_force", "suspension_position",
                                  "slip_angle", "slip_ratio", "tyre_load", "tyre_deflection"])
def test_b044_bar_gap_follows_caption(ui_env, name):
    assert dimmed(name, "bar_gap", False, show_caption=False)
    assert not dimmed(name, "bar_gap", False, show_caption=True)


# B-049: Track Clock time scale options under the clock switch; manual scale active while synced
@DESIGNS
def test_b049_track_clock_time_scale_options(ui_env, modern):
    hidden_clock = {"show_track_clock": False, "show_time_scale": True}
    assert not dimmed("track_clock", "enable_track_clock_synchronization", modern, **hidden_clock)
    assert not dimmed("track_clock", "track_clock_time_scale", modern, enable_track_clock_synchronization=False,
                      **hidden_clock)
    assert dimmed("track_clock", "track_clock_time_scale", modern, enable_track_clock_synchronization=True)


# B-050: Delta Best reading range under the bar switch, bar options without it
@DESIGNS
def test_b050_deltabest_range_and_bar_options(ui_env, modern):
    assert not dimmed("deltabest", "delta_display_range", modern, show_delta_bar=False)
    assert dimmed("deltabest", "enable_animated_deltabest", modern, show_delta_bar=False)
    assert dimmed("deltabest", "layout", modern, show_delta_bar=False)


# B-051: Session estimated laps options under the extra laps switch
@DESIGNS
def test_b051_session_estimated_laps_options(ui_env, modern):
    keys = shown_keys("session", modern)
    for key in ("prefix_estimated_laps", "font_color_estimated_laps", "background_color_estimated_laps"):
        if key in keys:
            assert not dimmed("session", key, modern, show_predicted_extra_laps=False), key
    assert dimmed("session", "show_predicted_extra_laps", modern, show_estimated_laps=False)


# B-052: Timing (classic) invalid lap color dimmed with last lap hidden, though current lap uses it
def test_b052_timing_invalid_color_of_last_or_current_lap(ui_env):
    assert not dimmed("timing", "font_color_invalid_last", False, show_last=False, show_current=True)
    assert dimmed("timing", "font_color_invalid_last", False, show_last=False, show_current=False)


# B-060: Fuel & Virtual Energy (classic) low colors dimmed with the warning flash off
def test_b060_low_amount_colors_without_flash(ui_env):
    assert not dimmed("fuel", "warning_color_low_fuel", False, show_low_fuel_warning_flash=False)
    assert not dimmed("virtual_energy", "warning_color_low_energy", False, show_low_energy_warning_flash=False)


# B-065: Instrument ignition options active with the ignition hidden
@DESIGNS
def test_b065_instrument_ignition_options(ui_env, modern):
    for key in ("warning_color_engine_off", "warning_color_stalling", "stalling_rpm_threshold"):
        if key in shown_keys("instrument", modern):
            assert dimmed("instrument", key, modern, show_ignition=False), key


# B-061: Gear speed limiter options under the speed switch, though the limiter shows without the speed
@DESIGNS
def test_b061_gear_limiter_options_follow_limiter(ui_env, modern):
    assert not dimmed("gear", "show_speed_limiter", modern, show_speed=False)
    assert not dimmed("gear", "speed_limiter_text", modern, show_speed=False, show_speed_limiter=True)
    assert dimmed("gear", "speed_limiter_text", modern, show_speed_limiter=False)


# B-062: Gear RPM zones dimmed without the RPM bar, though they color the gear too
@DESIGNS
def test_b062_gear_rpm_zones_used_without_rpm_bar(ui_env, modern):
    keys = shown_keys("gear", modern)
    for key in ("rpm_multiplier_safe", "rpm_multiplier_redline", "rpm_multiplier_critical", "rpm_color_safe"):
        if key in keys:
            assert not dimmed("gear", key, modern, show_rpm_bar=False), key


# B-063: Engine Temperature prefixes under water temperature, rate options under net change
@DESIGNS
def test_b063_engine_temperature_options(ui_env, modern):
    keys = shown_keys("engine_temperature", modern)
    if "show_temperature_prefix" in keys:
        assert not dimmed("engine_temperature", "show_temperature_prefix", modern, show_water_temperature=False)
        assert not dimmed("engine_temperature", "font_color_rate_of_change", modern, show_net_change_per_lap=False,
                          show_rate_of_change=True)
    assert not dimmed("engine_temperature", "rate_of_change_interval", modern, show_net_change_per_lap=False,
                      show_rate_of_change=True)
    assert dimmed("engine_temperature", "rate_of_change_interval", modern, show_rate_of_change=False)


# B-064: Gear consumption bar options & reading fonts active while unused
@DESIGNS
def test_b064_gear_consumption_and_fonts(ui_env, modern):
    for key in ("high_consumption_threshold", "show_consumption_reading"):
        assert dimmed("gear", key, modern, show_consumption_bar=False), key
    if not modern:
        assert dimmed("gear", "font_scale_speed", modern, show_speed_below_gear=False)
        assert dimmed("gear", "font_size_rpm", modern, show_rpm_reading=False)


# B-070: Steering Wheel angle reading options active without the reading
@DESIGNS
def test_b070_steering_wheel_reading_options(ui_env, modern):
    keys = shown_keys("steering_wheel", modern)
    for key in ("decimal_places", "show_degree_sign", "font_color_steering_angle", "font_name"):
        if key in keys:
            assert dimmed("steering_wheel", key, modern, show_steering_angle=False), key


# B-071: Pedal font (classic) & brake pressure options active while unused
@DESIGNS
def test_b071_pedal_unused_options(ui_env, modern):
    assert dimmed("pedal", "show_brake_pressure", modern, show_brake_filtered=False)
    if not modern:
        assert dimmed("pedal", "font_size", modern, show_readings=False)


# B-072: Steering Angle, Steering Meter (classic) & Telemetry Compare (classic) options active while unused
def test_b072_steering_and_telemetry_unused_options(ui_env):
    hidden = {"show_ackermann_percentage": False, "show_turning_radius": False,
              "show_turning_radius_under_slip_angle": False}
    assert dimmed("steering_angle", "wheelbase", True, **hidden)
    assert not dimmed("steering_angle", "wheelbase", True, **dict(hidden, show_turning_radius=True))
    assert dimmed("steering_angle", "wheel_track_front", True, show_ackermann_percentage=False)
    assert dimmed("steering_meter", "font_size", False, show_steering_angle=False)
    assert dimmed("telemetry_compare", "line_color_gear", False, show_gear=False)


# B-058: timing overlays options active without what uses them
def test_b058_timing_overlays_unused_options(ui_env):
    assert dimmed("delta_graph", "position_mark_color", False, show_position_mark=False)
    assert dimmed("stint_timer", "stint_warning_minutes", True, maximum_stint_minutes=0)
    assert not dimmed("stint_timer", "stint_warning_minutes", True, maximum_stint_minutes=60)
    assert dimmed("stint_timer", "minimum_driving_minutes", True, show_driver_times=False)
    assert dimmed("laps_and_position", "warning_color_invalid_lap", False, show_invalid_lap_highlight=False)
    for name in ("lap_time_history", "stint_history"):
        assert dimmed(name, "caption_text_virtual_energy", False, show_caption=False)
        assert dimmed(name, "caption_text_virtual_energy", False, show_caption=True,
                      show_virtual_energy_if_available=False)


# B-074: tyre overlays & Friction Circle options active while unused
def test_b074_tyre_overlays_unused_options(ui_env):
    assert dimmed("tyre_temperature", "background_color_surface", False, swap_style=False)
    assert dimmed("tyre_carcass", "font_color_carcass", False, swap_style=True)
    assert dimmed("tyre_pressure", "font_color_tyre_compound", False, show_compound_color_by_type=True)
    assert dimmed("tyre_temp_trend", "trend_duration", True, show_trend_by_lap=True)
    assert dimmed("friction_circle", "trace_fade_out_step", True, show_trace_fade_out=False)
    assert dimmed("friction_circle", "font_color_highlight", False, show_readings=False)
    assert dimmed("tyre_wear", "caption_text_flat_spot", False, show_caption=True, show_flat_spot=False)
    assert not dimmed("tyre_wear", "caption_text_remaining", False, show_caption=True, show_remaining=True)


# B-077: Relative (classic) name colors active while lap difference colors the names
def test_b077_relative_name_colors_with_lap_difference(ui_env):
    for key in ("font_color_position", "font_color_driver_name", "font_color_vehicle_name"):
        assert dimmed("relative", key, False, show_lap_difference=True), key
        assert not dimmed("relative", key, False, show_lap_difference=False, show_position=True,
                          show_driver_name=True, show_vehicle_name=True), key


# B-080: driver lists options active without what uses them
def test_b080_driver_list_options(ui_env):
    for name in ("relative", "standings", "rivals"):
        if "show_pit_request" in shown_keys(name, False):
            assert dimmed(name, "show_pit_request", False, show_pitstop_count=False), name
        if "show_lap_difference" in shown_keys(name, True):
            assert dimmed(name, "show_lap_difference", True, column_driver_name=False), name
    assert dimmed("relative", "nearest_time_gap_threshold_front", True, show_highlighted_nearest_time_gap=False)
    assert dimmed("relative", "font_color_fastest_last_laptime", False, show_highlighted_fastest_last_laptime=False)


# B-081: Heading slip angle reading under the yaw angle reading
@DESIGNS
def test_b081_heading_slip_reading_own_switch(ui_env, modern):
    assert not dimmed("heading", "show_slip_angle_reading", modern, show_yaw_angle_reading=False)
    if "font_color_slip_angle" in shown_keys("heading", modern):
        assert dimmed("heading", "font_color_slip_angle", modern, show_slip_angle_reading=False)
        assert not dimmed("heading", "font_color_slip_angle", modern, show_yaw_angle_reading=False,
                          show_slip_angle_reading=True)


# B-082: Spotter (classic) bar colors dimmed without the bar background
def test_b082_spotter_bar_colors(ui_env):
    for key in ("bar_color_nearby", "bar_color_critical", "bar_color_clear"):
        assert not dimmed("spotter", key, False, show_bar_background=False), key
    assert dimmed("spotter", "bar_background_color", False, show_bar_background=False)


# B-083: Chat (classic) message colors dimmed without message time
def test_b083_chat_message_colors(ui_env):
    for key in ("font_color_message", "font_color_new_message", "background_color_message"):
        assert not dimmed("chat", key, False, show_message_time=False), key


# B-084: Race Notifications class position change dimmed by the overall one
@DESIGNS
def test_b084_class_position_change_own_switch(ui_env, modern):
    assert not dimmed("race_notifications", "show_position_change_in_class", modern, show_position_change=False)


# B-085: Wind Direction calm threshold dimmed without strength colors
@DESIGNS
def test_b085_wind_calm_threshold(ui_env, modern):
    assert not dimmed("wind_direction", "wind_strength_threshold_calm", modern, show_wind_strength_color=False)


# B-086: Flag options active without their part
@DESIGNS
def test_b086_flag_options_follow_their_part(ui_env, modern):
    assert dimmed("flag", "green_flag_text", modern, show_start_lights=False)
    assert dimmed("flag", "disqualify_text", modern, show_finish_state=False)
    assert dimmed("flag", "show_speed_limiter_off_warning", modern, show_speed_limiter=False)
    assert dimmed("flag", "show_speed_limit_difference", modern, show_current_speed_while_limiter_on=False)


# B-087: Track Map options of the mode not in use active
def test_b087_track_map_mode_options(ui_env):
    assert dimmed("track_map", "show_position_in_class", True, enable_multi_class_styling=False)
    assert dimmed("track_map", "vehicle_color_leader", False, enable_multi_class_styling=True)
    assert dimmed("track_map", "fixed_pitstop_duration_3", True, enable_fixed_pitout_prediction=False)
    assert dimmed("track_map", "pitout_duration_minimum", True, enable_fixed_pitout_prediction=True)
    assert dimmed("track_map", "show_pitstop_duration", True, show_pitout_prediction=False)


# B-088: Radar fade active without auto hide
@DESIGNS
def test_b088_radar_fade_follows_auto_hide(ui_env, modern):
    for key in ("enable_radar_fade", "radar_fade_in_radius"):
        assert dimmed("radar", key, modern, enable_auto_hide=False), key


# B-090: notes pit texts active while the overlay hides instead
@pytest.mark.parametrize("name", ["pace_notes", "track_notes"])
def test_b090_notes_pit_texts(ui_env, name):
    assert dimmed(name, "pit_notes_text", True, enable_auto_hide_if_not_available=True)
    assert not dimmed(name, "pit_notes_text", True, enable_auto_hide_if_not_available=False)


# B-031: option opened from Find Option hidden by the "used options only" filter
def test_b031_focused_option_shown_with_used_only_filter(options):
    cfg.user.setting["acceleration"]["speed_range_6_end"] = 0  # range start does nothing: dimmed
    options.setUsedOnly(True)
    options.selectOverlay("speedometer")
    options.focus_option("acceleration", "speed_range_6_start")
    assert options.rowIndex("acceleration/speed_range_6_start") >= 0


# B-032: Apply in a locked preset told "Options saved"
def test_b032_locked_preset_apply_notice(ui_env, monkeypatch):
    from types import SimpleNamespace

    from neopedal.ui import overlay_options

    shown = []
    monkeypatch.setattr(overlay_options, "show_toast", lambda parent, text: shown.append(text))
    monkeypatch.setattr(overlay_options, "run_after_saving", lambda callback: None)
    monkeypatch.setitem(cfg.user.filelock, cfg.filename.setting, {})
    overlay_options.OverlayOptions.applied(SimpleNamespace(module_control=None), ["fuel"])
    assert shown and shown[0] != "Options saved" and "locked" in shown[0]


# B-033: screen layout of arrow key moves stored 0.6 s later, lost by a reload or quit within that time
def test_b033_pending_layout_written_before_reload(ui_env, monkeypatch):
    from neopedal import loader
    from neopedal.widget._edit_mode import edit_mode

    mode = edit_mode()
    stored = []
    monkeypatch.setattr(mode, "store_layout", lambda: stored.append(1))
    mode.store_layout_soon()
    loader.write_pending()  # reload, restart or quit
    assert stored == [1] and not mode._layout_timer.isActive()


# B-037: Black Box options set by auto compact mode noted as set by the display profile
def test_b037_compact_mode_note_names_its_option(options):
    from neopedal.i18n.options import option_label
    from tests.test_overlay_options import row

    cfg.user.setting["black_box"].update(display_profile="Custom", auto_compact_display_scale=0.8, display_scale=0.6)
    options.selectOverlay("black_box")
    options.setAdvanced(True)
    note = row(options, "black_box/show_tyre_compound")["note"]
    assert option_label("auto_compact_display_scale") in note


# B-038: Black Box colorblind theme left red / green pairs (damage panel, energy, refill mark)
def test_b038_colorblind_theme_converts_semantic_colors(ui_env):
    from neopedal.template.widget.black_box_ui import BLACK_BOX_COLOR_THEMES, theme_color

    theme = BLACK_BOX_COLOR_THEMES["Colorblind Safe"]
    defaults = cfg.default.setting["black_box"]
    for key in ("damage_panel_suspension_color", "damage_panel_body_color_detached", "energy_gauge_color",
                "gauge_refill_mark_color", "warning_color_high_battery"):
        assert theme_color(defaults[key], theme) != defaults[key].upper(), key


# B-039: Black Box preview drawn compact (auto resize): battery & other blocks never shown
@DESIGNS
def test_b039_black_box_preview_shows_blocks_of_its_data(ui_env, bundled_fonts, modern):
    values = {"enable_auto_resize": True, "display_profile": "Custom"}
    assert picture("black_box", modern, show_battery_bar=True, **values) != picture(
        "black_box", modern, show_battery_bar=False, **values)


# B-054: Laps and Position (modern) red "0/1" with a limit of one point
def test_b054_limit_of_one_point_not_red_at_zero(ui_env, bundled_fonts):
    from types import SimpleNamespace

    from neopedal.ui.widget_preview import _with_preview_widget

    cfg.user.config["overlay_style"]["overlay_theme"] = "Modern Dark"
    values = dict(cfg.user.setting["laps_and_position"], enable_classic_layout=False, show_track_limits_points=True)
    class Proxy:
        """Reader part of the simulated race, some calls replaced"""

        def __init__(self, real, **calls):
            self._real = real
            self.__dict__.update(calls)

        def __getattr__(self, name):
            return getattr(self._real, name)

    def colors(widget):
        import sys

        module = sys.modules[type(widget).__module__]  # preview: module api swapped for simulated race
        shown = []
        widget.refresh = shown.append
        real = module.api
        try:
            session = Proxy(real.read.session, cut_points=lambda: 0.0, limits_points=lambda: 1.0, in_race=lambda: 1)
            module.api = SimpleNamespace(read=Proxy(real.read, session=session))
            widget.timerEvent(None)
        finally:
            module.api = real
        return [value.color for value in shown[-1] if value.text == "0/1"], widget.theme.negative

    found, negative = _with_preview_widget(cfg, "laps_and_position", values, 1.0, colors)
    assert found and negative not in found


# B-056: Delta Graph mark placed on the rounded delta (steps off the curve with few decimal places)
@DESIGNS
def test_b056_delta_graph_mark_on_delta(ui_env, bundled_fonts, modern):
    from neopedal.demo_data import demo_session
    from neopedal.ui.widget_preview import _with_preview_widget

    cfg.user.config["overlay_style"]["overlay_theme"] = "Modern Dark" if modern else "Legacy Dark"
    session = demo_session(cfg.user.setting["standings"])

    def mark_y(widget):
        session.minfo.delta.deltaBest = 0.4
        return widget.read_graph()[2]

    old = session.minfo.delta.deltaBest
    try:
        marks = [_with_preview_widget(cfg, "delta_graph", dict(cfg.user.setting["delta_graph"], decimal_places=places,
                                                               enable_classic_layout=not modern), 1.0, mark_y)
                 for places in (0, 3)]
    finally:
        session.minfo.delta.deltaBest = old
    assert abs(marks[0] - marks[1]) < 1  # was: 0 decimal place put the mark at 0 s (delta rounded)


# B-066: Engine Temperature (classic) net change of 0 in cooling color
def test_b066_engine_temperature_zero_net_change_neutral(ui_env):
    from types import SimpleNamespace

    from neopedal.widget.engine_temperature import Realtime

    target = SimpleNamespace(last=None, text="", fg="", update=lambda: None)
    widget = SimpleNamespace(temp_scale=1.0, bar_style_rate=("loss", "gain", "neutral"))
    Realtime.update_net(widget, target, 90.0, 0.0)  # first lap: no change yet
    assert target.fg == "neutral"


# B-047: Brake Performance (classic) "+0.00" before first braking in percentage mode
def test_b047_brake_performance_percentage_first_text(ui_env):
    from neopedal.widget import brake_performance

    cfg.user.setting["brake_performance"].update(enable_classic_layout=True, show_delta_braking_rate=True,
                                                 show_delta_braking_rate_in_percentage=True)
    widget = brake_performance.Realtime(cfg, "brake_performance")
    try:
        assert widget.bar_delta_rate.text == "+0%"  # before any update (first braking)
    finally:
        widget.deleteLater()


# B-053: Timing missing last lap (0) shown in the invalid lap color
def test_b053_classic_timing_no_last_lap_not_invalid(ui_env):
    from types import SimpleNamespace

    from neopedal.widget.timing import Realtime

    target = SimpleNamespace(last=None, fg="", text="", update=lambda: None)
    widget = SimpleNamespace(bar_style_last=("invalid", "valid"))
    for data in (0.0, -0.0):  # no last lap, negated as invalid lap
        target.last = None
        Realtime.update_last(widget, target, data, "")
        assert target.fg == "valid", data


def test_b053_modern_timing_no_last_lap_not_invalid(ui_env, bundled_fonts):
    import sys

    from neopedal.ui.widget_preview import _with_preview_widget

    cfg.user.config["overlay_style"]["overlay_theme"] = "Modern Dark"
    values = dict(cfg.user.setting["timing"], enable_classic_layout=False, show_invalid_lap_indicator=True)

    class Proxy:
        def __init__(self, real, **values):
            self._real = real
            self.__dict__.update(values)

        def __getattr__(self, name):
            return getattr(self._real, name)

    def last_color(widget):
        module = sys.modules[type(widget).__module__]
        shown = []
        widget.refresh = shown.append
        real = module.minfo
        try:
            module.minfo = Proxy(real, delta=Proxy(real.delta, lapTimeLast=0.0, isValidLap=False))
            widget.timerEvent(None)
        finally:
            module.minfo = real
        index = list(widget.keys).index("last")
        return shown[-1][index].color, widget.theme.negative

    color, negative = _with_preview_widget(cfg, "timing", values, 1.0, last_color)
    assert color != negative


# B-089: Radar auto hide distances beyond 1.5 x radius ignored by the quick range check
def test_b089_radar_quick_range_covers_auto_hide_distances(ui_env):
    from neopedal.widget.radar import RadarMixin

    class Radar(RadarMixin):
        def __init__(self, wcfg):
            self.wcfg = wcfg

    radar = Radar(dict(cfg.user.setting["radar"], radar_radius=30, auto_hide_minimum_distance_ahead=100))
    radar.setup_radar()
    assert radar.straight_range >= 100


# B-091: Radar (classic) distance circle width cut to whole pixels
def test_b091_radar_circle_decimal_width(ui_env):
    from types import SimpleNamespace

    from PySide6.QtGui import QColor, QPen

    from neopedal.widget.radar import Realtime

    pen = QPen()
    painter = SimpleNamespace(setPen=lambda pen: None, drawEllipse=lambda *args: None)
    radar = SimpleNamespace(radar_radius=30, global_scale=6, area_center=180)
    Realtime.draw_circle_mark(radar, painter, pen, True, 10, 2.5, QColor("#FFFFFF"))
    assert pen.widthF() == 2.5


# B-073: Friction Circle (classic) dot size 4000: 8000 x 8000 dot picture
def test_b073_friction_circle_dot_picture_limited(ui_env):
    from neopedal.widget import friction_circle

    cfg.user.setting["friction_circle"].update(enable_classic_layout=True, dot_size=4000)
    widget = friction_circle.Realtime(cfg, "friction_circle")
    try:
        assert widget.pixmap_dot.width() <= cfg.user.setting["friction_circle"]["display_size"]
    finally:
        widget.deleteLater()


# B-068: Gear (modern) widened by the reading of a hidden bar
def test_b068_gear_reading_of_hidden_bar(ui_env, bundled_fonts):
    hidden = {"show_rpm_bar": False, "decimal_places_rpm": 9}
    assert picture_width("gear", True, show_rpm_reading=True, **hidden) == picture_width(
        "gear", True, show_rpm_reading=False, **hidden)


# B-048: wheelbase & wheel track accepted 0 (angle frozen) or negative (angle flipped)
@pytest.mark.parametrize("key", ["wheelbase", "wheel_track_front", "wheel_track_rear"])
def test_b048_car_dimensions_limited(key):
    from neopedal.template.option_limits import clamp_to_limit, limit_error

    assert limit_error(key, 0) and limit_error(key, -1800)
    assert not limit_error(key, 1800) and not limit_error(key, 2800)
    assert clamp_to_limit(key, 0) == 100


# B-059: page limits wider than what overlays read (values accepted, cut without telling)
@pytest.mark.parametrize("name, key, minimum, maximum", [
    ("gap_trend", "number_of_laps", 2, 50), ("tyre_temp_trend", "number_of_laps", 2, 100),
    ("stint_timer", "number_of_drivers", 0, 6), ("chat", "number_of_lines", 1, 20),
    ("race_notifications", "number_of_notifications", 1, 8), ("weather_forecast", "number_of_forecasts", 1, 4),
    ("track_map", "number_of_prediction", 1, 20), ("relative_finish_order", "number_of_prediction", 0, 10),
    ("relative_finish_order", "number_of_extra_laps", 1, 1000),
    ("gap_trend", "decimal_places", 0, 3), ("delta_graph", "decimal_places", 0, 3),
    ("telemetry_compare", "decimal_places", 0, 3), ("steering_wheel", "decimal_places", 0, 2),
    ("heading", "decimal_places", 0, 2), ("wind_direction", "decimal_places", 0, 2),
    ("speedometer", "decimal_places", 0, 9), ("standings", "decimal_places_energy_remaining", 0, 2),
    ("friction_circle", "display_radius_g", 1, 20), ("friction_circle", "reference_circle_1_radius_g", 0, 20),
    ("steering_wheel", "manual_steering_range", 0, 3600), ("heading", "dot_size", 1, 1000),
])
def test_b059_limits_match_overlay_code(ui_env, name, key, minimum, maximum):
    from neopedal.ui.quick.option_kinds import number_range

    assert number_range(key, name) == (minimum, maximum)


def test_b059_page_refuses_value_beyond_overlay_limit(options):
    from tests.test_overlay_options import row

    options.selectOverlay("gap_trend")
    assert row(options, "gap_trend/number_of_laps")["maximum"] == 50
    options.setNumber("gap_trend/decimal_places", 9)
    assert options.errorCount == 1
    options.setNumber("gap_trend/decimal_places", 3)
    assert options.errorCount == 0


def test_b059_defaults_within_limits_of_their_overlay(ui_env):
    from neopedal.template.option_limits import limit_error
    from neopedal.template.setting_widget import WIDGET_DEFAULT

    assert not [(name, key, value) for name, values in WIDGET_DEFAULT.items() for key, value in values.items()
                if isinstance(value, (int, float)) and not isinstance(value, bool)
                and limit_error(key, float(value), name)]


# B-057: Pit Stop Estimate bar_width (characters) & Sectors extra_digits: overlays of 24000 - 160000 pixels
@pytest.mark.parametrize("name, key, value", [("pit_stop_estimate", "bar_width", 4000), ("sectors", "extra_digits", 5000)])
@DESIGNS
def test_b057_huge_character_widths_limited(ui_env, bundled_fonts, name, key, value, modern):
    from neopedal.ui.quick.option_kinds import number_range

    assert number_range(key, name)[1] <= 20
    assert picture_width(name, modern, **{key: value}) < 2000


# B-075: Standings (classic) picture drawn on a race made from saved options, not edited ones
def test_b075_preview_race_from_edited_standings(ui_env, bundled_fonts, monkeypatch):
    from neopedal import demo_data
    from neopedal.ui.widget_preview import LivePreview, render_widget

    seen = []
    real_session, real_class = demo_data.demo_session, demo_data.DemoSession
    monkeypatch.setattr(demo_data, "demo_session",
                        lambda standings, scenario="": seen.append(dict(standings)) or real_session(standings, scenario))
    monkeypatch.setattr(demo_data, "DemoSession",
                        lambda standings, scenario="": seen.append(dict(standings)) or real_class(standings, scenario))
    cfg.user.config["overlay_style"]["overlay_theme"] = "Legacy Dark"
    saved = cfg.user.setting["standings"]["minimum_top_vehicles"]
    edited = dict(cfg.user.setting["standings"], enable_classic_layout=True, minimum_top_vehicles=saved + 2)
    render_widget(cfg, "standings", edited)
    assert seen[-1]["minimum_top_vehicles"] == saved + 2
    LivePreview(cfg, "standings", edited).close()
    assert seen[-1]["minimum_top_vehicles"] == saved + 2


# B-078: Rivals (modern) show_player_highlighted did nothing (rivals never lists the player)
def test_b078_rivals_dead_option_removed(ui_env):
    from neopedal.setting_preupdate import preupdate_user_setting
    from neopedal.template.setting_widget import WIDGET_DEFAULT

    assert "show_player_highlighted" not in WIDGET_DEFAULT["rivals"]
    assert "show_player_highlighted" not in shown_keys("rivals", True)
    assert "show_player_highlighted" in WIDGET_DEFAULT["standings"]
    preset = {"rivals": {"show_player_highlighted": False, "column_time_interval": True},
              "standings": {"show_player_highlighted": False}}
    preupdate_user_setting((2, 51, 8), preset)
    assert preset == {"rivals": {"column_time_interval": True}, "standings": {"show_player_highlighted": False}}


# B-069: Gear pit limiter reminder: one option per design with opposite defaults (changing design switched it)
def test_b069_gear_limiter_reminder_one_option(ui_env):
    from neopedal.setting_preupdate import preupdate_user_setting
    from neopedal.template.setting_widget import WIDGET_DEFAULT
    from neopedal.widget._modern.gear import Realtime

    gear = WIDGET_DEFAULT["gear"]
    assert "show_speed_limiter_reminder" not in gear and gear["show_speed_limiter_pit_reminder"] is True
    assert "show_speed_limiter_pit_reminder" in Realtime.options
    for modern in (True, False):
        assert "show_speed_limiter_pit_reminder" in shown_keys("gear", modern)
    for classic, pit, reminder, expected in ((True, False, True, False), (True, True, False, True),
                                             (False, False, True, True), (False, True, False, False)):
        preset = {"gear": {"enable_classic_layout": classic, "show_speed_limiter_pit_reminder": pit,
                           "show_speed_limiter_reminder": reminder}}
        preupdate_user_setting((2, 51, 8), preset)
        assert preset["gear"]["show_speed_limiter_pit_reminder"] is expected, (classic, pit, reminder)
        assert "show_speed_limiter_reminder" not in preset["gear"]


# B-045: classic overlays padded every prefix to the longest one, of hidden items too
@pytest.mark.parametrize("name, show, prefix", [
    ("roll_angle", "show_roll_angle_ratio", "prefix_roll_angle_ratio"),
    ("differential", "show_coast_locking_rear", "prefix_coast_rear"),
    ("weight_distribution", "show_cross_weight", "prefix_cross_weight"),
    ("damage_stats", "show_tyre_integrity", "prefix_tyre_integrity"),
    ("system_performance", "show_neopedal_performance", "prefix_neopedal"),
])
def test_b045_hidden_item_prefix_never_widens(ui_env, bundled_fonts, name, show, prefix):
    hidden = {show: False, "layout": 0}
    assert picture_width(name, False, **hidden, **{prefix: "A very long prefix"}) == picture_width(
        name, False, **hidden)


# B-046: Damage (classic) puncture drawn as an outline only, suspension damage color hidden
def test_b046_damage_puncture_keeps_suspension_color(ui_env, monkeypatch):
    from types import SimpleNamespace

    from PySide6.QtCore import QRect
    from PySide6.QtGui import QColor, QImage, QPainter, QPen

    from neopedal.widget._painter import OverlayStyle
    from neopedal.widget.damage import Realtime

    # Flat fill: rounded corners & depth shading are shared style, left set by tests of other overlays
    monkeypatch.setattr(OverlayStyle, "corner_scale", 0.0)
    monkeypatch.setattr(OverlayStyle, "depth_effects", False)
    image = QImage(30, 40, QImage.Format.Format_ARGB32)
    image.fill(0)
    widget = SimpleNamespace(
        rects_wheels=[QRect(5, 5, 20, 30)], damage_wheel=[False], damage_tyre=[True], damage_susp=[0.9],
        pen_puncture=QPen(QColor("#FF0000")), wcfg={"suspension_damage_light_threshold": 0.02},
        color_damage_wheel=lambda detached, damage: "#00FF00")
    painter = QPainter(image)
    Realtime.draw_damage_wheel(widget, painter)
    painter.end()
    assert image.pixelColor(15, 20).name() == "#00ff00"


# B-055: Laps and Position (classic) track limits points cell of 7 characters: "10.25/12.5" cut off
@pytest.mark.parametrize("layout", [0, 1])
def test_b055_track_limits_points_fit(ui_env, layout):
    from neopedal.widget import laps_and_position

    cfg.user.setting["laps_and_position"].update(enable_classic_layout=True, show_track_limits_points=True,
                                                  prefix_track_limits_points="", layout=layout)
    widget = laps_and_position.Realtime(cfg, "laps_and_position")
    try:
        target = widget.bar_cut_points
        cell = len(target.text)
        widget.update_cut_points(target, 10.25, 12.5)
        assert target.text.strip() == "10.25/12.5" and len(target.text) <= cell
    finally:
        widget.deleteLater()


# B-067: Fuel & Virtual Energy (modern) tiles sized for 2 decimal places: more were cut or spilled over
@pytest.mark.parametrize("name, key", [
    ("fuel", "decimal_places_end_remaining"), ("fuel", "decimal_places_remaining"),
    ("fuel", "decimal_places_estimated_minutes"), ("virtual_energy", "decimal_places_estimated_laps"),
    ("virtual_energy", "decimal_places_fuel_ratio"),
])
def test_b067_consumption_tiles_fit_decimals(ui_env, bundled_fonts, name, key):
    shown = {"show_fuel_ratio": True, "show_refueling": True, "show_refilling": True}
    values = {option: value for option, value in shown.items() if option in cfg.user.setting[name]}
    assert picture_width(name, True, **values, **{key: 6}) > picture_width(name, True, **values)
    assert picture_width(name, True, **values, **{key: 0}) == picture_width(name, True, **values)


# B-079: modern gap trend column narrower than "9.9" drawn, arrow & rate never centered
@pytest.mark.parametrize("name", ["relative", "standings", "rivals"])
def test_b079_gap_trend_column_fits_and_centers(ui_env, bundled_fonts, monkeypatch, name):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter

    from neopedal.ui.widget_preview import _with_preview_widget
    from neopedal.widget._modern import table

    cfg.user.config["overlay_style"]["overlay_theme"] = "Modern Dark"
    values = dict(cfg.user.setting[name], enable_classic_layout=False, column_gap_trend=True, font_size=22)
    arrows = []
    monkeypatch.setattr(table, "triangle", lambda painter, rect, up, color: arrows.append(QRectF(rect)))

    def check(widget):
        column = next(column for column in widget.table.columns if column.key == "gap_trend")
        size = widget.table.row_height * table.CHANGE_ARROW
        assert column.width >= size * 1.3 + widget.text_width("value", "9.9")
        image = QImage(400, 100, QImage.Format.Format_ARGB32)
        painter = QPainter(image)
        cell = QRectF(0, 0, 300, widget.table.row_height)
        widget.draw_trend(painter, cell, (9.9, True))
        painter.end()
        assert arrows[-1].left() > 100  # centered, was: at the left edge

    _with_preview_widget(cfg, name, values, 1.0, check)


# B-092: visibility_context (every overlay) without help
def test_b092_visibility_context_help(ui_env):
    from neopedal.i18n.options import option_help_english, option_help_specific

    for name in ("fuel", "standings", "radar"):
        assert "In Pits" in option_help_english(name, "visibility_context")
        assert option_help_specific(name, "visibility_context")


# B-093: helps describing another option or other values
def test_b093_helps_describe_their_option(ui_env):
    from neopedal.i18n.options import option_help_english

    assert "Default is disabled" not in option_help_english("laps_and_position", "warning_color_invalid_lap")
    for name in ("pace_notes", "track_notes"):
        assert "index number" not in option_help_english(name, "show_debugging")
    assert "flat spot" in option_help_english("tyre_wear", "warning_threshold_wear")


# B-013: help of maximum_vehicles_combined_mode said it is unused in split mode (it acts with one class)
def test_b013_combined_count_help_tells_single_class(ui_env):
    from neopedal.i18n.options import option_help_english

    assert "one class" in option_help_english("standings", "maximum_vehicles_combined_mode")


# B-084: Race Notifications overall & class position change sharing one help
def test_b084_position_change_helps_distinct(ui_env):
    from neopedal.i18n.options import option_help_english

    overall = option_help_english("race_notifications", "show_position_change")
    in_class = option_help_english("race_notifications", "show_position_change_in_class")
    assert overall and in_class and overall != in_class


# B-094 to B-157: options without help (and stale keys / wrong wildcard matches of B-093)
MISSING_HELPS = {
    "acceleration": (
        "bar_width"
    ),
    "battery": (
        "layout"
    ),
    "black_box": (
        "status_icons_side status_icon_scale font_scale_engine show_headlights_indicator "
        "show_engine_status stalling_rpm_threshold engine_oil_warning_temperature "
        "engine_water_warning_temperature text_oil text_water text_engine_off text_ignition"
    ),
    "brake_bias": (
        "layout show_brake_bias suffix_brake_migration"
    ),
    "brake_performance": (
        "layout"
    ),
    "brake_pressure": (
        "bar_padding_horizontal bar_padding_vertical bar_width horizontal_gap vertical_gap "
        "brake_input_size font_scale_caption caption_text"
    ),
    "brake_temperature": (
        "horizontal_gap vertical_gap"
    ),
    "brake_wear": (
        "font_scale_caption caption_text_remaining caption_text_wear_difference "
        "caption_text_live_wear_difference caption_text_lifespan_laps caption_text_lifespan_minutes"
    ),
    "cruise": (
        "layout"
    ),
    "damage_stats": (
        "layout"
    ),
    "deltabest": (
        "bar_padding_horizontal bar_padding_vertical"
    ),
    "deltabest_extended": (
        "layout delta_display_range freeze_duration"
    ),
    "drs": (
        "bar_padding_horizontal bar_padding_vertical"
    ),
    "elevation": (
        "elevation_progress_line_width elevation_line_width zero_elevation_line_width "
        "start_line_width sector_line_width position_mark_width"
    ),
    "engine_temperature": (
        "layout"
    ),
    "friction_circle": (
        "dot_outline_width"
    ),
    "fuel": (
        "font_scale_caption"
    ),
    "fuel_energy_saver": (
        "bar_width"
    ),
    "gear": (
        "bar_padding_horizontal bar_padding_vertical speed_limiter_padding_horizontal "
        "show_inverted_consumption consumption_bar_height"
    ),
    "heading": (
        "dot_size dot_outline_width"
    ),
    "lap_time_history": (
        "font_scale_caption caption_text_laps caption_text_time caption_text_delta "
        "caption_text_fuel caption_text_virtual_energy caption_text_fuel_ratio caption_text_wear "
        "swap_upper_caption"
    ),
    "laps_and_position": (
        "layout"
    ),
    "lift_and_coast_led": (
        "display_margin show_background led_outline_width show_lift_and_coast"
    ),
    "navigation": (
        "start_line_width start_line_length sector_line_width sector_line_length "
        "show_vehicle_class_standings vehicle_outline_width_player"
    ),
    "onboard_setting": (
        "layout font_scale_caption caption_text_abs caption_text_tc caption_text_tc_cut "
        "caption_text_tc_slip caption_text_brake_migration caption_text_motor_map "
        "caption_text_front_arb caption_text_rear_arb swap_upper_caption"
    ),
    "pace_notes": (
        "layout"
    ),
    "pit_stop_estimate": (
        "bar_width font_scale_caption caption_text_pass_duration caption_text_pit_timer "
        "caption_text_stop_duration caption_text_minimum_total_duration "
        "caption_text_actual_relative_refill caption_text_total_relative_refill "
        "caption_text_estimated_laps caption_text_estimated_minutes caption_text_pit_occupancy "
        "caption_text_pit_requests swap_upper_caption swap_lower_caption"
    ),
    "push_to_pass": (
        "layout"
    ),
    "race_plan": (
        "layout"
    ),
    "radar": (
        "angle_mark_style angle_mark_radius angle_mark_width auto_hide_minimum_distance_behind "
        "auto_hide_minimum_distance_side vehicle_maximum_visible_distance_behind "
        "vehicle_maximum_visible_distance_side"
    ),
    "relative": (
        "show_best_laptime show_best_laptime_from_recent_laps_in_race show_average_laptime "
        "show_energy_remaining show_vehicle_integrity show_incidents incidents_high_threshold "
        "incidents_extreme_threshold show_stint_laps show_speed_trap show_lift_and_coast_time "
        "lift_and_coast_reset_threshold lift_and_coast_highlight_threshold"
    ),
    "relative_finish_order": (
        "bar_width"
    ),
    "ride_height": (
        "bar_padding_horizontal bar_padding_vertical bar_width horizontal_gap vertical_gap "
        "font_scale_caption caption_text"
    ),
    "roll_angle": (
        "layout"
    ),
    "rpm_led": (
        "display_margin show_background led_outline_width"
    ),
    "session": (
        "layout"
    ),
    "slip_angle": (
        "bar_padding_horizontal bar_padding_vertical bar_width horizontal_gap vertical_gap "
        "font_scale_caption caption_text"
    ),
    "slip_ratio": (
        "bar_padding_horizontal bar_padding_vertical bar_width horizontal_gap vertical_gap "
        "font_scale_caption caption_text"
    ),
    "steering_angle": (
        "layout"
    ),
    "steering_meter": (
        "bar_padding_horizontal bar_padding_vertical"
    ),
    "steering_wheel": (
        "show_background show_circle_background show_degree_sign rotation_line_width "
        "rotation_line_margin"
    ),
    "stint_history": (
        "font_scale_caption caption_text_laps caption_text_time caption_text_fuel "
        "caption_text_virtual_energy caption_text_tyre caption_text_wear caption_text_delta "
        "caption_text_consistency swap_upper_caption"
    ),
    "suspension_force": (
        "bar_padding_horizontal bar_padding_vertical bar_width horizontal_gap vertical_gap "
        "font_scale_caption caption_text"
    ),
    "suspension_position": (
        "bar_padding_horizontal bar_padding_vertical bar_width horizontal_gap vertical_gap "
        "third_spring_position_mark_width maximum_position_range_size font_scale_caption "
        "caption_text"
    ),
    "suspension_travel": (
        "layout font_scale_caption caption_text_total_travel caption_text_bump_travel "
        "caption_text_rebound_travel caption_text_travel_ratio caption_text_motion_ratio "
        "caption_text_minimum_position caption_text_maximum_position caption_text_live_position"
    ),
    "system_performance": (
        "layout"
    ),
    "track_clock": (
        "layout"
    ),
    "track_map": (
        "start_line_width start_line_length sector_line_width sector_line_length "
        "proximity_circle_width show_vehicle_class_standings vehicle_outline_width_player "
        "vehicle_outline_width vehicle_outline_width_safety_car vehicle_outline_width_laps_ahead "
        "vehicle_outline_width_laps_behind prediction_outline_width auto_prediction_outline_width "
        "fixed_pitstop_duration_1 fixed_pitstop_duration_2 fixed_pitstop_duration_3 "
        "fixed_pitstop_duration_4 fixed_pitstop_duration_5 fixed_pitstop_duration_6 "
        "fixed_pitstop_duration_7 fixed_pitstop_duration_8 fixed_pitstop_duration_9 "
        "fixed_pitstop_duration_10"
    ),
    "track_notes": (
        "layout"
    ),
    "traffic": (
        "font_scale_caption caption_text_slower caption_text_leader caption_text_faster"
    ),
    "trailing": (
        "show_brake show_raw_brake show_clutch show_raw_clutch show_ffb"
    ),
    "tyre_carcass": (
        "horizontal_gap vertical_gap swap_style"
    ),
    "tyre_deflection": (
        "bar_padding_horizontal bar_padding_vertical bar_width horizontal_gap vertical_gap "
        "font_scale_caption caption_text"
    ),
    "tyre_inner_layer": (
        "horizontal_gap vertical_gap"
    ),
    "tyre_load": (
        "bar_padding_horizontal bar_padding_vertical bar_width horizontal_gap vertical_gap "
        "font_scale_caption caption_text"
    ),
    "tyre_pressure": (
        "horizontal_gap vertical_gap"
    ),
    "tyre_temperature": (
        "horizontal_gap vertical_gap"
    ),
    "tyre_wear": (
        "font_scale_caption caption_text_remaining caption_text_wear_difference "
        "caption_text_live_wear_difference caption_text_flat_spot caption_text_lifespan_laps "
        "caption_text_lifespan_minutes caption_text_end_stint_remaining"
    ),
    "virtual_energy": (
        "show_low_energy_warning_flash low_energy_lap_threshold show_energy_level_bar "
        "energy_level_bar_height show_starting_energy_level_mark starting_energy_level_mark_width "
        "show_refilling_level_mark refilling_level_mark_width font_scale_caption "
        "caption_text_refilling caption_text_absolute_refilling"
    ),
    "weather_forecast": (
        "rain_chance_bar_height"
    ),
    "weight_distribution": (
        "layout show_percentage_sign"
    ),
    "wheel_camber": (
        "horizontal_gap vertical_gap font_scale_caption caption_text"
    ),
    "wheel_toe": (
        "horizontal_gap vertical_gap font_scale_caption caption_text"
    ),
    "wind_direction": (
        "show_background direction_mark_north_width direction_mark_major_width "
        "direction_mark_minor_width"
    ),
}


@pytest.mark.parametrize("name", sorted(MISSING_HELPS))
def test_b094_every_option_has_help(ui_env, name):
    from neopedal.i18n.options import option_help_english

    missing = [key for key in "".join(MISSING_HELPS[name]).split() if not option_help_english(name, key)]
    assert not missing


def test_b094_fuel_caption_help_is_a_caption_help(ui_env):
    from neopedal.i18n.options import option_help_english

    for name in ("fuel", "virtual_energy"):
        assert "caption" in option_help_english(name, "caption_text_remaining")
    assert "show_vehicle_standings" not in str(option_help_english("track_map", "show_vehicle_class_standings"))
