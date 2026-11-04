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
Session Widget, modern design

Session type, system clock, remaining session time, estimated remaining laps.
"""

from __future__ import annotations

import time
from itertools import islice
from time import strftime
from typing import TYPE_CHECKING

from PySide6.QtGui import QColor, QPainter

from ... import calculation as calc
from ...api_control import api
from ...const_common import MAX_SECONDS
from ...demo_state import drawing_demo
from ...i18n import tr_overlay
from ...module_info import minfo
from ...userfile.lap_reference import LEVEL_COLORS, LEVELS
from .._common import player_race_laps, system_clock_samples
from .base import DASH, ModernOverlay, signed
from .stats import Stat, StatsMixin, Value

if TYPE_CHECKING:
    from ...template.widget_config_types import SessionConfig

SESSION_NAMES = ("TEST", "PRACTICE", "QUALIFY", "WARMUP", "RACE")
# Custom session name options (classic), same order as SESSION_NAMES
SESSION_TEXT_OPTIONS = (
    "session_text_testday", "session_text_practice", "session_text_qualify", "session_text_warmup", "session_text_race",
)


PACE_SECONDS = 5.0  # field pace worked out again this often (best laps move a few times a lap)
SHEET_SECONDS = 600.0  # community lap times sheet read again from its cache file this late (downloaded by Driver Stats)


class FieldPace:
    """Pace of the drivers of your class from shared memory: median community level (lap times sheet of Driver Stats,
    cached on disk) of their best laps on this track, no request"""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._next = 0.0
        self._level = -1
        self._sheet_time = -SHEET_SECONDS
        self._table = None

    def table(self):
        now = self._clock()
        if self._table is None or now - self._sheet_time >= SHEET_SECONDS:
            from ...setting import cfg
            from ...userfile import lap_reference

            text, _ = lap_reference.load_cache(cfg.path.config)
            self._table = lap_reference.parse_lap_references(text) if text else lap_reference.LapReferenceTable()
            self._sheet_time = now
        return self._table

    def level(self) -> int:
        now = self._clock()
        if now < self._next:
            return self._level
        self._next = now + PACE_SECONDS
        self._level = field_level(self.table(), api.read.session.track_name(), api.read.vehicle.class_name(),
                                  [(veh.vehicleClass, veh.bestLapTime)
                                   for veh in islice(minfo.vehicles.dataSet, minfo.vehicles.totalVehicles)])
        return self._level


def field_level(table, track: str, vehicle_class: str, cars: list[tuple[str, float]]) -> int:
    """Median community level (LEVELS index) of the best laps of the cars of vehicle_class, -1 if unknown (no sheet
    for the track & class, no best lap yet)"""
    reference = table.find(track, "", vehicle_class) if track and vehicle_class else None
    if reference is None:
        return -1
    levels = sorted(level for level in (reference.level(best) for car_class, best in cars
                                        if car_class == vehicle_class and 0 < best < MAX_SECONDS) if level >= 0)
    return levels[len(levels) // 2] if levels else -1


class Realtime(StatsMixin, ModernOverlay):
    """Draw widget"""

    wcfg: SessionConfig

    options = (
        "font_size", "layout", "show_session_name", *SESSION_TEXT_OPTIONS, "show_system_clock",
        "system_clock_format", "show_session_time", "show_estimated_laps", "show_predicted_extra_laps",
        "display_order_session_name", "display_order_system_clock", "display_order_session_time",
        "display_order_estimated_laps", "show_field_pace", "display_order_field_pace",
    )

    def __init__(self, config, widget_name):
        super().__init__(config, widget_name)
        wcfg = self.wcfg
        theme = self.theme
        # Session names changed by user, else design names (translated)
        self.session_names = tuple(
            self.user_text(key, tr_overlay(name)) for key, name in zip(SESSION_TEXT_OPTIONS, SESSION_NAMES)
        )
        stats = []
        if wcfg["show_session_name"]:
            sample = self.widest("strong", self.session_names)
            stats.append(Stat("session_name", "Session", sample, "strong"))
        if wcfg["show_system_clock"]:
            sample = self.widest("value", system_clock_samples(wcfg["system_clock_format"]))
            stats.append(Stat("system_clock", "Clock", sample))
        if wcfg["show_session_time"]:
            stats.append(Stat("session_time", "Remaining", "~88:88:88", "strong", theme.accent))
        if wcfg["show_estimated_laps"]:
            sample = "888.888 (+8)" if wcfg["show_predicted_extra_laps"] else "888.888"
            stats.append(Stat("estimated_laps", "Laps left", sample))
        if wcfg["show_field_pace"]:
            sample = self.widest("value", tuple(tr_overlay(level) for level in LEVELS))
            stats.append(Stat("field_pace", "Field pace", sample))
        stats = self.display_ordered(stats)
        self.keys = tuple(stat.key for stat in stats)
        self.pace = FieldPace()
        self.rank_colors: dict[str, QColor] = {}
        width, height = self.build_stats(stats, vertical=wcfg["layout"] == 0)
        self.set_size(width, height)

    def paint_static(self, painter: QPainter):
        self.paint_stats_static(painter)

    def paint(self, painter: QPainter):
        self.draw_stats(painter, self.state)

    def timerEvent(self, event):
        """Update when vehicle on track"""
        theme = self.theme
        remaining = api.read.session.remaining()
        offset = minfo.vehicles.finishTimeOffset
        est_remaining = remaining - offset
        values = []
        for key in self.keys:
            if key == "session_name":
                index = api.read.session.session_type()
                name = self.session_names[index] if 0 <= index < len(self.session_names) else ""
                values.append(Value(name, theme.positive if index == 4 else theme.text))
            elif key == "system_clock":
                values.append(Value(strftime(self.wcfg["system_clock_format"]), theme.text_dim))
            elif key == "session_time":
                if offset:
                    text = f"~{calc.sec2countdown(max(est_remaining, 0))}"
                else:
                    text = calc.sec2sessiontime(max(remaining, 0))
                values.append(Value(text))
            elif key == "estimated_laps":
                values.append(Value(self.laps_left(est_remaining)))
            elif key == "field_pace":
                values.append(self.field_pace_value())
        self.refresh(tuple(values))

    def field_pace_value(self) -> Value:
        """Community level (lap times sheet) of the usual best lap of the drivers of your class, dash if unknown"""
        level = 2 if drawing_demo() else self.pace.level()
        if level < 0:
            return Value(DASH, self.theme.text_dim)
        colors = self.rank_colors
        if not colors:  # level colors made once
            colors.update((name, QColor(color)) for name, color in zip(LEVELS, LEVEL_COLORS))
        return Value(tr_overlay(LEVELS[level]), colors.get(LEVELS[level], self.theme.text))

    def laps_left(self, est_remaining: float) -> str:
        """Estimated remaining laps"""
        laps_done, lap_total = player_race_laps(est_remaining)
        laps = max(lap_total - laps_done, 0)
        text = f"{laps:.3f}"[:7]
        if self.wcfg["show_predicted_extra_laps"]:
            return f"{text} ({signed(minfo.vehicles.finishLapOffset)})"
        return text
