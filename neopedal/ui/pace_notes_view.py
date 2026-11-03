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
Pace notes playback

Settings of pace notes playback are a category of the Settings page (qml/Settings.qml, see
quick/settings_backend.py), with a test sound; the Notes tab of Data Editors turns playback on or off (former
Pace Notes page). Audio playback is kept by the main view while no page is built.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QUrl, Slot

from ..i18n import trm
from ..setting import cfg

if TYPE_CHECKING:
    from .pace_notes_player import PaceNotesPlayer

logger = logging.getLogger(__name__)


class PaceNotesPlayback(QObject):
    """Pace notes audio playback, kept by main view while pace notes page may not be built

    Player only exists while playback is enabled: Qt Multimedia (and its media backend) is
    not loaded otherwise. Call refresh after setting changed (app refresh signal).
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.player: PaceNotesPlayer | None = None
        self.refresh()

    @Slot(bool)  # type: ignore[operator]
    def refresh(self, *_):
        """Create or release player to match playback setting (preset may have changed)"""
        mcfg = cfg.user.setting["pace_notes_playback"]
        if mcfg["enable"]:
            if self.player is None:
                from .pace_notes_player import PaceNotesPlayer

                self.player = PaceNotesPlayer(self, mcfg)
                logger.info("ENABLED: pace notes sounds playback")
            self.player.apply_setting(mcfg)  # volume & update interval used at once (B-015)
        elif self.player is not None:
            self.player.stop()
            self.player.deleteLater()
            self.player = None
            logger.info("DISABLED: pace notes sounds playback")

    def reset_playback(self):
        if self.player is not None:
            self.player.reset_playback()

    def set_volume(self, volume: int):
        if self.player is not None:
            self.player.set_volume(volume)


def test_sound_file(sound_path: str, sound_format: str) -> str:
    """First sound file (name order) of the pace notes sound folder in the sound format, "" if none

    Same checks as a pace note played while driving (see track_notes.pace_note_sound_file): only a file of
    the sound folder, never a network path.
    """
    from ..userfile.track_notes import pace_note_sound_file
    from ..validator import is_network_path

    if not isinstance(sound_path, str) or not isinstance(sound_format, str):
        return ""
    extension = f".{sound_format.strip().strip('.')}".lower()
    folder = os.path.dirname(os.path.abspath(f"{sound_path}_"))
    if is_network_path(sound_path) or is_network_path(folder):
        return ""  # never listed: a network host would be contacted (sign-in hash sent) before the refusal below
    try:
        names = sorted(name for name in os.listdir(folder) if name.lower().endswith(extension))
    except OSError:
        return ""
    for name in names:
        sound_file = pace_note_sound_file(sound_path, name[:-len(extension)], sound_format)
        if sound_file and os.path.isfile(sound_file):
            return sound_file
    return ""


def play_test_sound(owner: QObject, values: dict) -> str:
    """Play a sound of the sound folder with the volume of values (pace notes settings shown, not saved
    yet), "" if played, else why not (translated). One test player per owner page, kept while it lives."""
    sound_format = str(values.get("pace_notes_sound_format", "wav"))
    sound_file = test_sound_file(str(values.get("pace_notes_sound_path", "")), sound_format)
    if not sound_file:
        return trm(f"No .{sound_format.strip().strip('.')} sound in the sound folder")
    from .pace_notes_player import PaceNotesPlayer

    player = owner.findChild(PaceNotesPlayer, "testSoundPlayer")
    if player is None:
        # Own copy of settings with playback off: never plays notes while driving
        player = PaceNotesPlayer(owner, {**cfg.user.setting["pace_notes_playback"], "enable": False})
        player.setObjectName("testSoundPlayer")
    player.stop()
    volume = values.get("pace_notes_sound_volume", 50)
    player.set_volume(int(volume) if isinstance(volume, (int, float)) else 50)
    player.setSource(QUrl.fromLocalFile(sound_file))
    player.play()
    return trm(f"Playing {os.path.basename(sound_file)}")

