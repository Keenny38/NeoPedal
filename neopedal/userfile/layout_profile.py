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
Layout profiles: widget positions remembered per screen setup (single screen, triple screen...)

Stored next to preset as "<preset name>.layouts" (not ".json", so not listed as preset):
    {"1920x1080+0+0": {"speedometer": [x, y], ...}, "5760x1080+0+0": {...}}
When preset is loaded with a known screen setup, its widget positions are restored.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterable

from ..validator import json_loads_checked
from . import write_text_file

logger = logging.getLogger(__name__)

FILE_EXTENSION = ".layouts"
MAX_PROFILES = 20


def screen_key() -> str:
    """Screen setup identifier: geometry of every screen, sorted"""
    from PySide6.QtGui import QGuiApplication

    geometries = sorted(
        (rect.x(), rect.y(), rect.width(), rect.height())
        for rect in (screen.geometry() for screen in QGuiApplication.screens())
    )
    return ";".join(f"{width}x{height}+{x}+{y}" for x, y, width, height in geometries)


def profile_filename(settings_path: str, preset_filename: str) -> str:
    """Layout profile file of preset"""
    return os.path.join(settings_path, f"{os.path.splitext(preset_filename)[0]}{FILE_EXTENSION}")


def widget_positions(setting: dict, widget_names: Iterable[str]) -> dict[str, list[int]]:
    """Positions of every widget in preset setting"""
    positions = {}
    for name in widget_names:
        options = setting.get(name)
        if isinstance(options, dict) and "position_x" in options and "position_y" in options:
            positions[name] = [int(options["position_x"]), int(options["position_y"])]
    return positions


def apply_positions(setting: dict, positions: dict) -> bool:
    """Set widget positions from profile, returns True if any changed"""
    changed = False
    for name, position in positions.items():
        options = setting.get(name)
        if not isinstance(options, dict) or not isinstance(position, list) or len(position) != 2:
            continue
        x, y = position
        if not isinstance(x, int) or not isinstance(y, int):
            continue
        if (options.get("position_x"), options.get("position_y")) != (x, y):
            options["position_x"], options["position_y"] = x, y
            changed = True
    return changed


def load_profiles(filename: str) -> dict[str, dict] | None:
    """Load layout profiles: empty if missing; None if not readable now (held by antivirus or cloud sync, no
    access: never saved over, profiles of other screen setups kept); an invalid file (bad JSON, edited by hand)
    is kept as a timestamped backup before it is replaced, None if that backup fails"""
    try:
        with open(filename, "rb") as file:
            raw = file.read()
    except FileNotFoundError:
        return {}
    except OSError as error:
        logger.error("USERDATA: layout profile %s not readable, not saved this time: %s", filename, error)
        return None
    try:
        data = json_loads_checked(raw.decode("utf-8-sig"))  # BOM if edited by user
    except (ValueError, RecursionError) as error:  # UnicodeDecodeError & JSON errors; RecursionError: too deep
        logger.error("USERDATA: invalid layout profile %s: %s", filename, error)
        data = None
    if not isinstance(data, dict):
        return {} if backup_invalid(filename) else None
    return {key: value for key, value in data.items() if isinstance(key, str) and isinstance(value, dict)}


def backup_invalid(filename: str) -> bool:
    """Invalid profile file copied to a timestamped backup (replaced by next save), True if kept"""
    from .json_setting import create_backup_file, set_backup_timestamp

    folder, name = os.path.split(filename)
    if create_backup_file(name, os.path.join(folder, ""), set_backup_timestamp(), show_log=True):
        return True
    logger.error("USERDATA: invalid layout profile %s not backed up, not saved this time", filename)
    return False


def save_profiles(filename: str, profiles: dict[str, dict]) -> bool:
    """Save layout profiles, keep most recent ones (file order is recency: never sorted)"""
    if len(profiles) > MAX_PROFILES:
        profiles = dict(list(profiles.items())[-MAX_PROFILES:])
    return write_text_file(filename, json.dumps(profiles, indent=4))


def sync_layout(setting: dict, widget_names: Iterable[str], filename: str, key: str) -> bool:
    """Restore positions of screen setup if known, then store current positions

    Returns:
        True if preset positions changed (preset needs saving).
    """
    profiles = load_profiles(filename)
    if profiles is None:  # not readable now: positions of preset kept, file left as it is
        return False
    changed = key in profiles and apply_positions(setting, profiles[key])
    if changed:
        logger.info("LAYOUT: restored widget positions for screen setup %s", key)
    store_layout(setting, widget_names, filename, key, profiles)
    return changed


def store_layout(
    setting: dict, widget_names: Iterable[str], filename: str, key: str, profiles: dict | None = None,
) -> None:
    """Store current widget positions for screen setup (profiles: loaded already), nothing written if the file
    is not readable now (profiles of other screen setups never replaced)"""
    if profiles is None:
        profiles = load_profiles(filename)
        if profiles is None:
            return
    positions = widget_positions(setting, widget_names)
    if profiles.get(key) == positions and next(reversed(profiles), None) == key:  # unchanged & most recent
        return
    profiles.pop(key, None)  # most recent last
    profiles[key] = positions
    save_profiles(filename, profiles)
