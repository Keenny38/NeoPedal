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

"""
Overlay Options page: on/off options really controlling other options, where the automatic sections
(cut from option names & order, see ui.quick.overlay_sections) guess wrong

Plain data only (no Qt). Checked against the overlay code: an option is dimmed only while it does nothing.

- TOGGLE_FIXES: section led by the wrong on/off option, led by the right one instead (wrong one kept in it).
- DEPENDENCY_FIXES: option -> on/off option it is used with ("" if none: used whatever other options are),
  on/off option -> itself: leads a section of its own (cut in the section of a sibling item: early pit stops).
- INACTIVE_RULES: options doing nothing with some values of other options (count, choice, "not while on"),
  see OptionUI.inactive for the states.
- ANY_OF: options used by several parts, each switched by its own on/off option: used while any is on.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import NamedTuple

BOTH = "both"
MODERN = "modern"
CLASSIC = "classic"


class OptionFix(NamedTuple):
    """Fixed sections & dependencies of an overlay, for a design (BOTH, MODERN or CLASSIC)"""

    design: str = BOTH
    toggles: Mapping[str, str] = {}
    dependencies: Mapping[str, str] = {}


_PEDAL_ALERTS = {
    # Each alert of a pedal bar is switched on by its own flash option (not by the one listed first)
    "show_abs_activation_flash": "",
    "show_wheel_slip_flash": "",
    "tc_activation_color": "show_tc_activation_flash",
    "abs_activation_color": "show_abs_activation_flash",
    "wheel_lock_color": "show_wheel_lock_flash",
    "wheel_slip_color": "show_wheel_slip_flash",
    "wheel_lock_threshold": "show_wheel_lock_flash",
    "wheel_slip_threshold": "show_wheel_slip_flash",
}
_NOTES_TEXTS = {
    # Texts shown in pits whether pit notes are shown or not (placeholder without pit notes)
    "pit_notes_text": "",
    "pit_comments_text": "",
}
# Early pit stops: own on/off option & section, not part of pit stops (both words "pitstop count")
_EARLY_PITSTOPS = {
    "show_early_pitstop_count": "show_early_pitstop_count",
    **{f"{prefix}_early_pitstop_count": "show_early_pitstop_count"
       for prefix in ("decimal_places", "font_color", "background_color")},
}
_LED_SIZE = ("number_of_led", "led_width", "led_height", "led_radius", "led_outline_color", "led_outline_width")  # LEDs of one side or both
# Trailing: options of a trace & of its pedal bar or alert flash (see ANY_OF)
_TRAILING_SHARED = {
    "throttle_color": ("show_throttle", "show_throttle_bar"), "brake_color": ("show_brake", "show_brake_bar"),
    "clutch_color": ("show_clutch", "show_clutch_bar"),
    "ffb_color": ("show_ffb", "show_ffb_bar"),
    "tc_activation_color": ("show_tc_activation", "show_tc_activation_flash"),
    "abs_activation_color": ("show_abs_activation", "show_abs_activation_flash"),
    **dict.fromkeys(("wheel_lock_color", "wheel_lock_threshold"), ("show_wheel_lock", "show_wheel_lock_flash")),
    **dict.fromkeys(("wheel_slip_color", "wheel_slip_threshold"), ("show_wheel_slip", "show_wheel_slip_flash")),
}
_RPM_MULTIPLIERS = ("rpm_multiplier_low", "rpm_multiplier_safe", "rpm_multiplier_redline", "rpm_multiplier_critical",
                    "rpm_multiplier_over_rev")

OPTION_FIXES: dict[str, tuple[OptionFix, ...]] = {
    "gear": (
        # Bars led by "inverted" switches (off by default): every bar option dimmed while the bar is shown
        OptionFix(CLASSIC, toggles={"show_inverted_battery": "show_battery_bar", "show_inverted_rpm": "show_rpm_bar"},
                  dependencies={key: "show_battery_reading" for key in (
                      "decimal_places_battery", "font_color_battery", "battery_reading_offset_x",
                      "battery_reading_text_alignment")}),
        # RPM zones color the RPM bar, flickering or not
        OptionFix(MODERN, dependencies=dict.fromkeys(_RPM_MULTIPLIERS[1:4], "show_rpm_bar")),
    ),
    "rpm_led": (OptionFix(dependencies={  # zones & colors of every LED, size of single or double side LEDs
        **dict.fromkeys(_RPM_MULTIPLIERS, ""), **dict.fromkeys(_LED_SIZE, ""),
        **dict.fromkeys(("rpm_color_off", "rpm_color_low", "rpm_color_safe", "rpm_color_redline",
                         "rpm_color_critical", "rpm_color_over_rev"), "")}),),
    "lift_and_coast_led": (OptionFix(dependencies={**dict.fromkeys(_LED_SIZE, ""), "lift_and_coast_color_off": ""}),),
    "pedal": (OptionFix(dependencies=_PEDAL_ALERTS),),
    "elevation": (OptionFix(dependencies={
        "show_zero_elevation_line": "",  # drawn without elevation line
        "zero_elevation_line_color": "show_zero_elevation_line",
        "zero_elevation_line_width": "show_zero_elevation_line",
        "show_elevation_progress_line": "",  # drawn without progress fill
        "elevation_progress_line_color": "show_elevation_progress_line",
        "elevation_progress_line_width": "show_elevation_progress_line",
    }),),
    "fuel": (OptionFix(dependencies={
        "low_fuel_lap_threshold": "",  # low amount color, flashing or not
        "show_refueling_level_mark": "show_fuel_level_bar",
        **_EARLY_PITSTOPS,
    }),),
    "virtual_energy": (OptionFix(dependencies={
        "low_energy_lap_threshold": "",
        "show_refilling_level_mark": "show_energy_level_bar",
        **_EARLY_PITSTOPS,
    }),),
    "track_notes": (OptionFix(dependencies=_NOTES_TEXTS),),
    "pace_notes": (OptionFix(dependencies=_NOTES_TEXTS),),
    "push_to_pass": (OptionFix(dependencies=dict.fromkeys((
        # Activation check of the battery charge (cooldown), not of the activation timer
        "activation_threshold_gear", "activation_threshold_speed", "activation_threshold_throttle",
        "minimum_activation_time_delay", "maximum_activation_time_per_lap"), "show_battery_charge")),),
    "navigation": (OptionFix(CLASSIC, dependencies={
        "show_circle_background": "",  # circle drawn without the background
        "background_color_circle": "show_circle_background",
        "circle_outline_width": "show_circle_background",
        "circle_outline_color": "show_circle_background",
    }), OptionFix(dependencies={
        # Cars drawn as arrows or circles: every car option used by both shapes
        **dict.fromkeys(("show_circle_vehicle_shape", "vehicle_size", "vehicle_offset", "vehicle_color_player",
                         "vehicle_outline_width_player", "vehicle_outline_color_player", "vehicle_color_leader",
                         "vehicle_color_same_lap", "vehicle_color_laps_ahead", "vehicle_color_laps_behind",
                         "vehicle_color_in_pit", "vehicle_color_yellow", "vehicle_outline_color",
                         "vehicle_outline_width"), ""),
        **dict.fromkeys(("font_color", "font_color_player"), "show_vehicle_class_standings"),  # place numbers
    })),
    "trailing": (OptionFix(CLASSIC, dependencies={
        "show_pedal_bar_readings": "show_pedal_bars",
        # Font of pedal bar readings only
        **dict.fromkeys(("font_name", "font_size", "font_weight", "enable_auto_font_offset"),
                        "show_pedal_bar_readings"),
    }),),
    "fuel_energy_saver": (OptionFix(dependencies={"remaining_pitstop_threshold": "enable_pit_entry_bias"}),),
    "race_plan": (OptionFix(dependencies={"pit_window_laps": "show_next_stop",
                                          "warning_color_pit_window": "show_next_stop"}),),
    "track_clock": (OptionFix(dependencies={
        "enable_time_scaled_countdown": "show_sunlight_phase_countdown",
        # Time scale: of the clock, the scale reading & the countdown (see ANY_OF)
        "enable_track_clock_synchronization": "", "track_clock_time_scale": "",
        # Colors of the countdown & its arrow, time scaled or not
        **dict.fromkeys(("font_color_sunlight_phase_countdown", "background_color_sunlight_phase_countdown",
                         "font_color_phase_day", "font_color_phase_night"), "show_sunlight_phase_countdown"),
    }),),
    "lap_time_history": (OptionFix(dependencies={"caption_text_virtual_energy": "show_virtual_energy_if_available"}),),
    "stint_history": (OptionFix(dependencies={"caption_text_virtual_energy": "show_virtual_energy_if_available"}),),
    "steering_meter": (OptionFix(MODERN, dependencies={"scale_mark_degree": "show_scale_mark"}),
                       OptionFix(dependencies={"manual_steering_range": ""})),
    "tyre_overview": (OptionFix(dependencies={
        "flat_spot_threshold": "show_tyre_alerts",
        "show_inner_center_outer": "show_surface_temperature",
        "show_alert_highlight": "show_tyre_alerts",
        "show_tread_grooves": "show_tyre_graphic",
        "show_pressure_target_range": "enable_tyre_pressure_target",
        "show_wear_per_lap": "",  # own row, with or without tread gauge
        "heatmap_name": "",  # used while automatic heatmap is off (see INACTIVE_RULES)
        "warning_threshold_remaining": "show_wear",
        "warning_threshold_laps": "show_lifespan_laps",
        # Target ranges & their colors: of pressure target (itself of shown pressure)
        **dict.fromkeys((
            "tyre_pressure_target_minimum", "tyre_pressure_target_maximum", "tyre_pressure_target_rear_minimum",
            "tyre_pressure_target_rear_maximum", "tyre_target_by_compound", "tyre_pressure_low_color",
            "tyre_pressure_high_color"), "enable_tyre_pressure_target"),
    }), OptionFix(MODERN, dependencies={
        "warning_threshold_remaining": "",  # of tread left & tread gauge (see ANY_OF)
    })),
    "track_map": (OptionFix(dependencies={
        "auto_prediction_additional_pitstop_time": "enable_auto_pitout_prediction"}),),
    "corner_coach": (OptionFix(dependencies={"braking_point_tolerance": "show_braking_point"}),),
    # Heatmap picked by compound or brake while automatic: own option used only with it off (see INACTIVE_RULES)
    "brake_temperature": (OptionFix(dependencies={"heatmap_name": ""}),
                          OptionFix(MODERN, dependencies={"off_brake_duration": "show_average"})),
    "tyre_temperature": (OptionFix(dependencies={"heatmap_name": ""}),),
    "tyre_inner_layer": (OptionFix(dependencies={"heatmap_name": ""}),),
    "tyre_carcass": (OptionFix(dependencies={"heatmap_name": ""}),),
    "tyre_temp_trend": (OptionFix(dependencies={"heatmap_name": ""}),),
    # Symmetric toe only flips the sign of right wheels: no option of its own; totals follow their switch
    "wheel_toe": (OptionFix(dependencies={
        **dict.fromkeys(("decimal_places_toe_angle", "toe_angle_smoothing_samples", "font_color_toe_angle",
                         "background_color_toe_angle"), ""),
        "show_total_toe_angle": "show_total_toe_angle",
        **dict.fromkeys(("decimal_places_total_toe_angle", "total_toe_angle_smoothing_samples",
                         "font_color_total_toe_angle_positive", "font_color_total_toe_angle_negative",
                         "background_color_total_toe_angle"), "show_total_toe_angle"),
    }),),
    # Manual range: turns the wheel & bar whether the angle is read or not (Steering Angle: see ANY_OF)
    "steering_wheel": (OptionFix(dependencies={"manual_steering_range": ""}),),
    "steering_angle": (OptionFix(dependencies={"manual_steering_range": ""}),),
    "deltabest": (OptionFix(CLASSIC, dependencies={"background_color_deltabest": ""}),  # delta box, any source
                  # Range of the reading, animation & layout of the bar
                  OptionFix(dependencies={"delta_display_range": "", "enable_animated_deltabest": "show_delta_bar",
                                          "layout": "show_delta_bar"})),
    # Classic standings (no declared sections): class modes have their own options, see _standings
    "standings": (OptionFix(CLASSIC, dependencies={
        **dict.fromkeys(("enable_single_class_exclusive_mode", "maximum_vehicles_combined_mode",
                         "minimum_top_vehicles", "split_gap"), ""),
        "maximum_vehicles_exclusive_mode": "enable_single_class_exclusive_mode",
    }),),
    # Integrity reading options (word "integrity" put the color under the inverted switch)
    "damage": (OptionFix(dependencies=dict.fromkeys(
        ("font_color_integrity", "show_inverted_integrity", "show_aero_integrity_if_available"),
        "show_integrity_reading")),),
    "damage_stats": (OptionFix(CLASSIC, dependencies=dict.fromkeys(  # prefixes drawn only with the switch on
        ("prefix_aero_integrity", "prefix_body_integrity", "prefix_suspension_integrity", "prefix_tyre_integrity"),
        "show_integrity_prefix")),),
    # Estimated laps box: its prefix & colors, extra laps added to it
    "session": (OptionFix(dependencies=dict.fromkeys(
        ("prefix_estimated_laps", "font_color_estimated_laps", "background_color_estimated_laps",
         "show_predicted_extra_laps"), "show_estimated_laps")),),
}
# Trailing pedal bars (both designs): bar options under the pedal bars switch, each alert flash its own switch
OPTION_FIXES["trailing"] += (OptionFix(dependencies={
    **dict.fromkeys(("show_throttle_bar", "show_brake_bar", "show_clutch_bar", "show_ffb_bar",
                     "pedal_bar_width_unfiltered", "pedal_bar_width_filtered", "pedal_bar_gap",
                     "show_pedal_bar_brake_pressure", "pedal_bar_maximum_indicator_height", "pedal_bar_inner_gap",
                     "show_pedal_bar_readings", "show_tc_activation_flash", "show_abs_activation_flash",
                     "show_wheel_lock_flash", "show_wheel_slip_flash", "alert_flash_interval"), "show_pedal_bars"),
    # Colors & thresholds of traces and bars (see ANY_OF)
    **dict.fromkeys(_TRAILING_SHARED, ""),
}), OptionFix(CLASSIC, dependencies={"font_color_pedal_bar_readings": "show_pedal_bar_readings"}))
# Gauge overlays (classic): bar gap spaces the caption from the gauges only
for _name in ("brake_pressure", "ride_height", "suspension_force", "suspension_position", "slip_angle",
              "slip_ratio", "tyre_load", "tyre_deflection"):
    OPTION_FIXES[_name] = (*OPTION_FIXES.get(_name, ()), OptionFix(CLASSIC, dependencies={"bar_gap": "show_caption"}))
# Circle, map & elevation backgrounds (classic): drawn with or without the overlay background, own switch
for _name, _switch, _color in (
        ("heading", "show_circle_background", "background_color_circle"),
        ("radar", "show_circle_background", "background_color_circle"),
        ("wind_direction", "show_circle_background", "background_color_circle"),
        ("friction_circle", "show_circle_background", "background_color_circle"),
        ("steering_wheel", "show_circle_background", "background_color_circle"),
        ("track_map", "show_map_background", "background_color_map"),
        ("elevation", "show_elevation_background", "background_color_elevation")):
    OPTION_FIXES[_name] = (*OPTION_FIXES.get(_name, ()), OptionFix(CLASSIC, dependencies={_switch: "", _color: _switch}))
OPTION_FIXES["friction_circle"] += (OptionFix(CLASSIC, dependencies={  # fade of the circle background
    "show_fade_out": "show_circle_background", "fade_in_radius": "show_fade_out", "fade_out_radius": "show_fade_out"}),)


def fixes_of(name: str, modern: bool) -> tuple[dict[str, str], dict[str, str]]:
    """Section toggle & dependency fixes of overlay for design in use"""
    toggles: dict[str, str] = {}
    dependencies: dict[str, str] = {}
    for fix in OPTION_FIXES.get(name, ()):
        if fix.design == BOTH or fix.design == (MODERN if modern else CLASSIC):
            toggles.update(fix.toggles)
            dependencies.update(fix.dependencies)
    return toggles, dependencies


# Inactive rules: option -> (state, control[, value]), states of OptionUI.inactive plus:
# "count": numbered option over count option, "set": used only while control is not 0,
# "value": used only while choice control is value
Inactive = dict[str, tuple[str, ...]]
_rex_numbered = re.compile(r"^prediction_(\d+)_(leader|player)_pit_time$")
_rex_range_start = re.compile(r"^speed_range_(\d+)_start$")


def _mixed_compound(values: Mapping) -> Inactive:
    """Mixed compound symbol & color: one compound shown per car only (classic driver lists)"""
    inactive: Inactive = {}
    if values.get("show_compound_for_each_wheel", False):
        inactive["mixed_compound_symbol"] = ("off", "show_compound_for_each_wheel")
        inactive["font_color_mixed_compound"] = ("off", "show_compound_for_each_wheel")
    elif not values.get("show_compound_color_by_type", True):
        inactive["font_color_mixed_compound"] = ("on", "show_compound_color_by_type")
    return inactive


def _standings(values: Mapping) -> Inactive:
    """Class mode options doing nothing in the mode chosen (exclusive first, then split, else combined), as
    drivers_ui.standings_inactive of the modern design"""
    inactive = _mixed_compound(values)
    if values.get("enable_single_class_exclusive_mode", False):
        for key in ("enable_multi_class_split_mode", "class_order", "maximum_vehicles_split_mode",
                    "maximum_vehicles_per_split_player", "maximum_vehicles_per_split_others",
                    "maximum_vehicles_combined_mode"):
            inactive[key] = ("off", "enable_single_class_exclusive_mode")
    elif not values.get("enable_multi_class_split_mode", False):  # one list of every class
        for key in ("show_time_gap_from_same_class", "show_time_interval_from_same_class"):
            inactive[key] = ("on", "enable_multi_class_split_mode")
    return inactive


def _predictions(values: Mapping) -> Inactive:
    count = values.get("number_of_prediction", 0)
    return {key: ("count", "number_of_prediction") for key in values
            if (matched := _rex_numbered.match(key)) and int(matched.group(1)) > count}


def _speed_ranges(values: Mapping) -> Inactive:
    return {key: ("set", f"speed_range_{matched.group(1)}_end") for key in values
            if (matched := _rex_range_start.match(key)) and not values.get(f"speed_range_{matched.group(1)}_end")}


def _radar(values: Mapping) -> Inactive:
    """Auto hide timer: not used while radar fades with distance"""
    return {"auto_hide_time_threshold": ("off", "enable_radar_fade")} if values.get("enable_radar_fade") else {}


def _heatmap(values: Mapping) -> Inactive:
    """Heatmap option: not used while the heatmap is picked by compound or brake"""
    return {"heatmap_name": ("off", "enable_heatmap_auto_matching")} if values.get("enable_heatmap_auto_matching") else {}


def _swap_colors(font: str, background: str) -> Callable[[Mapping], Inactive]:
    """Heatmap readings (classic): heatmap colors the background, or the text with swap_style (other color of
    the pair unused)"""
    def rule(values: Mapping) -> Inactive:
        if values.get("swap_style", False):
            return {font: ("off", "swap_style")}
        return {background: ("on", "swap_style")}

    return rule


def _rules(*rules: Callable[[Mapping], Inactive]) -> Callable[[Mapping], Inactive]:
    """Rules of an overlay put together"""
    def rule(values: Mapping) -> Inactive:
        inactive: Inactive = {}
        for each in rules:
            inactive.update(each(values))
        return inactive

    return rule


def _track_clock(values: Mapping) -> Inactive:
    """Time scale set by hand: not used while synced with the game"""
    if values.get("enable_track_clock_synchronization", True):
        return {"track_clock_time_scale": ("off", "enable_track_clock_synchronization")}
    return {}


def _black_box(values: Mapping) -> Inactive:
    """Speed & RPM labels: drawn only with justified center column"""
    if values.get("center_column_alignment", "Justified") == "Justified":
        return {}
    return {key: ("value", "center_column_alignment", "Justified") for key in ("text_speed", "text_rpm")}


INACTIVE_RULES: dict[str, Callable[[Mapping], Inactive]] = {
    "relative": _mixed_compound,
    "standings": _standings,
    "rivals": _mixed_compound,
    "relative_finish_order": _predictions,
    "acceleration": _speed_ranges,
    "radar": _radar,
    "black_box": _black_box,
    "track_clock": _track_clock,
    "brake_temperature": _rules(_heatmap, _swap_colors("font_color_temperature", "background_color_temperature")),
    "tyre_temperature": _heatmap,
    "tyre_inner_layer": _heatmap,
    "tyre_carcass": _heatmap,
    "tyre_overview": _heatmap,
    "tyre_temp_trend": _heatmap,
}


_SETTING_POPUP = "show_setting_change_popup"
_DRIVING_EVENTS = "show_setting_popup_driving_events"  # pop-up of limiter, headlights & wipers states
_ENGINE = ("show_engine_status", "show_engine_overheat_events")
# Option -> on/off options of the parts using it (chains followed: event log events need the event log on)
ANY_OF: dict[str, Mapping[str, tuple[str, ...]]] = {
    "track_clock": dict.fromkeys(("enable_track_clock_synchronization", "track_clock_time_scale"),
                                 ("show_track_clock", "show_time_scale", "show_sunlight_phase_countdown")),
    "force": {"warning_color_liftforce": ("show_front_downforce", "show_rear_downforce")},
    "trailing": _TRAILING_SHARED,
    "steering_angle": {"manual_steering_range": ("show_steering_angle", "show_steering_ratio")},
    "tyre_overview": {
        "show_layer_labels": ("show_carcass_temperature", "show_inner_layer_temperature"),
        # Tread left & tread gauge (modern design only: classic one follows show_wear, see OPTION_FIXES)
        "warning_threshold_remaining": ("show_wear", "show_tread_gauge"),
    },
    "black_box": {
        # Labels of status chips also named by setting change pop-up
        "text_abs": ("show_abs_indicator", _SETTING_POPUP),
        "text_tc": ("show_tc_indicator", _SETTING_POPUP),
        "text_brake_bias": ("show_brake_bias", _SETTING_POPUP),
        "text_brake_migration": ("show_brake_migration", _SETTING_POPUP),
        "text_motor_map": ("show_motor_map", _SETTING_POPUP),
        "text_limiter": ("show_pit_limiter_indicator", _DRIVING_EVENTS),
        **dict.fromkeys(("text_wipers_auto", "text_wipers_slow", "text_wipers_fast"),
                        ("show_wipers_indicator", _DRIVING_EVENTS)),
        # Engine readings & overheat events of event log
        **dict.fromkeys(("text_oil", "text_water", "engine_oil_warning_temperature",
                         "engine_water_warning_temperature"), _ENGINE),
        # Track limits points (center column) & penalty events of event log
        "text_track_limits": ("show_track_limits_points", "show_penalty_events"),
        # Flash over shift point: of RPM LEDs (always) & of gear RPM color (if its shift flash is on)
        "shift_flash_interval": ("show_rpm_leds", "enable_shift_flash"),
        # Status icon size & side: headlights, wipers & engine icons
        **dict.fromkeys(("status_icon_scale", "status_icons_side"),
                        ("show_headlights_indicator", "show_wipers_indicator", "show_engine_status")),
        "warning_outline_width": ("show_slip_warning", "show_tyre_status"),  # detached wheel outline
        "tyre_temperature_warning_threshold": ("show_tyre_temperature", "show_tyre_surface_overheat"),
        # Pedals & ABS / TC of the incident recorder trace
        **dict.fromkeys(("pedal_input_source", "throttle_color", "brake_color"),
                        ("show_pedal_bars", "show_incident_recorder")),
        "abs_active_color": ("show_abs_indicator", "show_incident_recorder"),
        "tc_active_color": ("show_tc_indicator", "show_incident_recorder"),
        # Damage events & incident marks: of the incident recorder & event log
        **dict.fromkeys(("damage_event_threshold", "incident_color"), ("show_incident_recorder", "show_event_log")),
        # Suspension damage of damage panel & coilover damage of suspension view
        **dict.fromkeys((
            "damage_panel_suspension_color_light", "damage_panel_suspension_color_medium",
            "damage_panel_suspension_color_heavy", "damage_panel_suspension_light_threshold",
            "damage_panel_suspension_medium_threshold", "damage_panel_suspension_heavy_threshold",
            "damage_panel_suspension_totaled_threshold"), ("show_damage_panel", "show_coilover_damage")),
    },
}


def font_offset_inactive(values: Mapping) -> Inactive:
    """Font offset set by hand: not used while automatic (every overlay with font options)"""
    if values.get("enable_auto_font_offset"):
        return {"font_offset_vertical": ("off", "enable_auto_font_offset")}
    return {}
