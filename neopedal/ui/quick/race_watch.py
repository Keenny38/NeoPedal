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
Daily races of the public RaceControl site kept read while the app runs, whichever page is open, so that race
reminders follow the starts (moved or cancelled races told) without the Upcoming Races page open. Started with the
race reminders (Home page at start). Read only when due (race_schedule_info.READ_SECONDS): one request an hour.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QTimer

from ... import race_schedule_info as info
from .background import BackgroundJobs

logger = logging.getLogger(__name__)

CHECK_MS = 60000  # read due checked this often


class RaceWatch(QObject):
    """Public daily races read when due (one object, see race_watch())"""

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._jobs = BackgroundJobs(self, "Race watch")
        self._timer = QTimer(self)
        self._timer.setInterval(CHECK_MS)
        self._timer.timeout.connect(self.check)
        self._timer.start()

    def check(self):
        if info.enabled() and info.due() and not self._jobs.is_busy("schedule"):
            self._jobs.run("race schedule", info.read, None, lambda _error: None, key="schedule")


_watch: RaceWatch | None = None


def race_watch() -> RaceWatch:
    """Public daily races kept read, created once (after QApplication)"""
    global _watch
    if _watch is None:
        from PySide6.QtCore import QCoreApplication

        _watch = RaceWatch(QCoreApplication.instance())
    return _watch
