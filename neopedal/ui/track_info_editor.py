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
Track info editor: pit lane, speed trap, map orientation, sun times & primary preset of each track
(table editor page, see quick/table_editor.py)

Distances & pit speed follow the user's Units settings (stored in meters & m/s). Primary preset: chosen among
existing presets, the same setting as the Presets page (track tags); a preset since deleted is marked "not found".
Speed trap cell menu sets it from the car position (current track, out of pit lane).

Map of the selected track beside the table (Tracks tab of Data Editors, former Track Map Viewer page): pit entry,
pit exit & speed trap marked on it, their cell menu sets them from the map position.
"""

from __future__ import annotations

import html
import os
from collections.abc import Callable

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtWidgets import QSplitter

from ..api_control import api
from ..const_file import ConfigType
from ..i18n import colon, tr
from ..setting import cfg
from ..template.setting_tracks import TRACKINFO_DEFAULT
from ._common import UIScaler
from .quick.table_editor import (
    KIND_CLOCK,
    KIND_NAME,
    KIND_NUMBER,
    KIND_PRESET,
    Column,
    TableEditorBackend,
    dict_rows,
)
from .quick.table_editor_host import TableEditorPage

KEYS = tuple(TRACKINFO_DEFAULT)
PIT_ENTRY = KEYS.index("pit_entry") + 1  # column
PIT_EXIT = KEYS.index("pit_exit") + 1
SPEED_TRAP = KEYS.index("speed_trap") + 1
PRESET = KEYS.index("preset") + 1
# Places marked on the map of the selected track: column, text, color
MARKS = ((PIT_ENTRY, "Pit entry", "#F0883E"), (PIT_EXIT, "Pit Exit", "#3FB950"), (SPEED_TRAP, "Speed Trap", "#58A6FF"))


class TrackBackend(TableEditorBackend):
    """Tracks: name, then TRACKINFO_DEFAULT values"""

    COLUMNS = (
        Column("", "Track name", KIND_NAME, width=12),
        Column("pit_entry", "Pit entry", KIND_NUMBER, width=5, unit="distance", map_action=True),
        Column("pit_exit", "Pit Exit", KIND_NUMBER, width=5, unit="distance", map_action=True),
        Column("pit_speed", "Pit speed", KIND_NUMBER, width=5, unit="speed", decimals=2),
        Column("speed_trap", "Speed Trap", KIND_NUMBER, width=5, unit="distance", action="telemetry",
               map_action=True),
        Column("orientation", "Map orientation", KIND_NUMBER, width=4, symbol="°"),
        Column("sunrise", "Sunrise", KIND_CLOCK, width=4),
        Column("sunset", "Sunset", KIND_CLOCK, width=4),
        Column("preset", "Primary preset", KIND_PRESET, width=9),
    )
    CONFIG_TYPE = ConfigType.TRACKS
    NEW_NAME = "New Track Name"
    RESET_TEXT = "Reset every track to default? Changes are saved only by Save."

    def setup(self):
        # Map shown beside the table: (track name of map, position along track in meters), None if no map
        self.map_position: Callable[[], tuple[str, float] | None] = lambda: None

    def load(self) -> list[list]:
        rows = [self.rounded(row) for row in dict_rows(cfg.user.tracks, KEYS, TRACKINFO_DEFAULT)]
        self.loaded_presets = {row[0]: row[PRESET] for row in rows}  # primary presets when page opened
        return rows

    def default_rows(self) -> list[list]:
        return [self.rounded(row) for row in dict_rows(cfg.default.tracks, KEYS, TRACKINFO_DEFAULT)]

    @staticmethod
    def rounded(row: list) -> list:
        """Numbers rounded as shown before (4 decimals)"""
        return [round(value, 4) if isinstance(value, float) else value for value in row]

    def to_setting(self, rows: list[list]) -> dict:
        """Primary preset left as is here keeps the one set from the Presets page meanwhile (saved at once there)"""
        saved = cfg.user.tracks
        setting = {}
        for row in rows:
            data = dict(zip(KEYS, row[1:]))
            current = saved.get(row[0])
            if (isinstance(current, dict) and "preset" in current
                    and data["preset"] == self.loaded_presets.get(row[0], data["preset"])):
                data["preset"] = current["preset"]
            setting[row[0]] = data
        return setting

    def read_saved(self) -> bool:
        """Primary presets set from the Presets page while hidden shown (rows left as is here)"""
        changed = False
        for row in self.rows:
            current = cfg.user.tracks.get(row[0])
            loaded = self.loaded_presets.get(row[0])
            if isinstance(current, dict) and row[PRESET] == loaded and current.get("preset", loaded) != loaded:
                row[PRESET] = self.loaded_presets[row[0]] = current.get("preset", "")
                changed = True
        if changed:
            self._host.record_change()  # own undo step, editor not marked modified
        return changed

    def store(self, setting: dict):
        super().store(setting)
        self.loaded_presets = {name: data["preset"] for name, data in setting.items()}
        changed = False
        for row in self.rows:  # primary presets kept from the Presets page shown
            preset = self.loaded_presets.get(row[0], row[PRESET])
            if preset != row[PRESET]:
                row[PRESET] = preset
                changed = True
        if changed:
            self.refresh()
            self._host.record_change()  # own undo step, editor not marked modified

    def new_row(self, name: str) -> list:
        return [name, *TRACKINFO_DEFAULT.values()]

    def session_rows(self) -> list[list]:
        """Track of the session"""
        track_name = api.read.session.track_name()
        return [self.new_row(track_name)] if track_name else []

    def cell_action(self, key: int, column: int):
        """Speed trap at car position (asked first): current track only, out of pit lane"""
        number = self.index_of(key)
        track_name = str(self.rows[number][0])
        current_name = api.read.session.track_name()
        if track_name != current_name:
            self._host.warn(
                f"Unable to set speed trap position for selected track:<br><b>{html.escape(track_name)}</b><br><br>"
                f"Only support to set speed trap position for current track:<br><b>{html.escape(current_name)}</b>"
            )
            return
        if api.read.vehicle.in_pits():
            self._host.warn("Cannot set speed trap position while in pit lane.")
            return
        position = round(api.read.lap.distance(), 4)
        shown = self.display(SPEED_TRAP, position)
        self.ask(
            tr("Set from Telemetry"),
            tr("Speed trap set at the car position:") + f" {shown}\n{track_name}", tr("Set"),
            "set_value", key, SPEED_TRAP, position)

    def map_action(self, key: int, column: int):
        """Pit entry, pit exit or speed trap at the position of the map shown (asked first): map of the same track"""
        number = self.index_of(key)
        track_name = str(self.rows[number][0])
        shown = self.map_position()
        if shown is None or shown[0] != track_name:
            self._host.warn(
                f"No track map of <b>{html.escape(track_name)}</b> shown.<br><br>"
                "Track maps are recorded by the Mapping module while you drive.")
            return
        position = round(shown[1], 4)
        label = tr(self.COLUMNS[column].header)
        self.ask(
            tr("Set from Map Position"), f"{label}{colon()}{self.display(column, position)}\n{track_name}", tr("Set"),
            "set_value", key, column, position)

    def current_row(self) -> list | None:
        number = self.index_of(self._current_key)
        return self.rows[number] if number >= 0 else None

    def set_value(self, key: int, column: int, value: float):
        """Cell value set (base unit), one undo step"""
        number = self.index_of(key)
        if number >= 0 and self.rows[number][column] != value:
            self.rows[number][column] = value
            self.changed()


class TrackInfoEditor(TableEditorPage):
    """Track info editor: table, map of the selected track beside it (made with the table)"""

    BACKEND = TrackBackend
    TITLE = "Track Info Editor"

    def __init__(self, parent):
        from .track_map_viewer import TrackMapViewer

        self.map_viewer: TrackMapViewer | None = None
        super().__init__(parent)
        backend: TrackBackend = self.backend  # type: ignore[assignment]
        backend.map_position = self.map_position
        backend.selectionChanged.connect(self.show_current_track)
        backend.historyChanged.connect(self.update_marks)  # values edited, undone, reset

    def ensure_view(self) -> QQuickWidget:
        """Table & map, made when first shown"""
        if self.view is None:
            from .quick import create_quick_view
            from .track_map_viewer import TrackMapViewer

            splitter = QSplitter(Qt.Orientation.Horizontal, self)
            splitter.setChildrenCollapsible(False)
            view = create_quick_view(splitter, "TableEditor.qml", {"backend": self.backend})
            viewer = TrackMapViewer(splitter)
            viewer.setWindowFlags(Qt.WindowType.Widget)
            viewer.in_app_page = True  # part of this page: its dialogs open over it
            viewer.installEventFilter(self)  # Esc closes the page, not the map
            view.setMinimumWidth(UIScaler.size(24))  # table never squeezed out by the map
            viewer.setMinimumSize(UIScaler.size(18), 0)
            splitter.addWidget(view)
            splitter.addWidget(viewer)
            splitter.setStretchFactor(0, 3)
            splitter.setStretchFactor(1, 2)
            splitter.setSizes([3000, 2000])  # table 60 %, map 40 % (scaled to the page width)
            self._layout.addWidget(splitter)
            splitter.show()  # child added to a shown page is not shown by itself
            self.setFocusProxy(view)
            self.view = view
            self.map_viewer = viewer
            self.show_current_track()
        return self.view

    def map_position(self) -> tuple[str, float] | None:
        """Track name & position of the map shown, None if no map loaded"""
        viewer = self.map_viewer
        if viewer is None or not viewer.backend.raw_coords:
            return None
        return viewer.backend.map_name, viewer.backend._position

    def show_current_track(self):
        """Map of the selected track (if recorded), its places marked"""
        viewer = self.map_viewer
        row = self.backend.current_row()  # type: ignore[attr-defined]
        if viewer is None or row is None:
            return
        from .quick.track_map_backend import map_path

        name = str(row[0])
        folder = cfg.path.track_map
        if os.path.isfile(map_path(folder, name)) and map_path(folder, name) != viewer.backend.map_file:
            viewer.backend.load_map(folder, name)
        self.update_marks()

    def show_track(self, name: str) -> bool:
        """Row of track selected & its map shown (Driver Stats map button), False if not listed"""
        self.ensure_view()
        for key, row in zip(self.backend.keys, self.backend.rows):
            if row[0] == name:
                self.backend.select(key, 0)
                return True
        from .quick.track_map_backend import map_path

        if self.map_viewer is not None and os.path.isfile(map_path(cfg.path.track_map, name)):
            self.map_viewer.backend.load_map(cfg.path.track_map, name)  # recorded map of a track not listed
        return False

    def update_marks(self, *_):
        """Pit entry, pit exit & speed trap of the selected track on its map (values set only)"""
        viewer = self.map_viewer
        if viewer is None:
            return
        row = self.backend.current_row()  # type: ignore[attr-defined]
        marks = []
        if row is not None and row[0] == viewer.backend.map_name:
            marks = [(row[column], tr(text), color) for column, text, color in MARKS
                     if isinstance(row[column], (int, float)) and row[column] > 0]
        viewer.backend.set_marks(marks)

    def eventFilter(self, watched, event):
        # Esc in the map (QDialog would hide it alone): sent to this page, closed like the table
        if (watched is self.map_viewer and event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent)
                and event.key() == Qt.Key.Key_Escape):
            QCoreApplication.sendEvent(self, QKeyEvent(event.type(), event.key(), event.modifiers()))
            return True
        return super().eventFilter(watched, event)

    def free_page(self):
        """Map freed first (its QML before its backend), then the table"""
        viewer, self.map_viewer = self.map_viewer, None
        if viewer is not None:
            viewer.release_page()
        super().free_page()
