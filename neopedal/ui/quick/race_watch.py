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
Your online races followed live (starts you are registered to, see race_schedule_info), whichever page is open

From BEFORE_SECONDS before a start (practice opens at the start time): your registration checked once (race
cancelled, registration removed: told), then the server of your split read every CHECK_MS until RaceControl gives
it (told once: join it from the game, Join Event), SPLIT_SECONDS after the start or SPLIT_MISSES reads in a row not
answered at most; once the race is over, your ranks read again. Read only, through
the same requests as the game menu: RaceControl hands the game its server through the game's own channel
(websocket), never opened here (a second one could take it from the game). Server address & password never kept.
The schedule is read when due (READ_SECONDS, nothing asked while RaceControl asks to wait) so that registrations
made in the game are seen without any page open. Started with the race reminders (Home page at start); told like them (app notification & tray message over the
game).
"""

from __future__ import annotations

import logging
import time
from functools import partial

from PySide6.QtCore import QObject, QTimer, Signal

from ... import race_schedule_info as info
from ...process import race_schedule as rs
from .background import BackgroundJobs

logger = logging.getLogger(__name__)

CHECK_MS = 60000  # server of your split asked at most this often (RaceControl refuses many requests)
BEFORE_SECONDS = 60.0  # starts followed from this long before them
SPLIT_SECONDS = 1800.0  # server of your split asked until this long after the start (given when practice opens)
SPLIT_MISSES = 5  # server of your split no longer asked after this many reads in a row not answered
MAX_WATCHED = 4  # starts followed at once at most (requests kept few)
FORGET_SECONDS = 86400.0  # what was told of a start forgotten this long after its end


def watched_starts(schedule: rs.Schedule, now: float) -> list[tuple[rs.Event, rs.Start]]:
    """Starts you are registered to, from BEFORE_SECONDS before them to their end, soonest first"""
    found = [(event, start) for event in schedule.events for start in event.starts
             if start.registered and start.event_id and start.time - BEFORE_SECONDS <= now <= rs.race_end(event, start)]
    return sorted(found, key=lambda pair: pair[1].time)[:MAX_WATCHED]


def ended_starts(schedule: rs.Schedule, now: float) -> list[tuple[rs.Event, rs.Start]]:
    """Starts you were registered to that are over (less than FORGET_SECONDS ago)"""
    return [(event, start) for event in schedule.events for start in event.starts
            if start.registered and start.event_id and 0 < now - rs.race_end(event, start) < FORGET_SECONDS]


def race_message(template: str, event: rs.Event, start: rs.Start, now: float) -> tuple:
    """Message of a race (English template: %1 race, %2 start), see notification.MessageText"""
    from .schedule_view import start_text

    return ((template, (event.title, start_text(start.time, now))),)


class RaceWatch(QObject):
    """Your races followed live (one object, see race_watch())"""

    changed = Signal()  # server of a start ready

    def __init__(self, parent: QObject | None = None, clock=None):
        super().__init__(parent)
        self._clock = clock if clock is not None else lambda: time.time()  # time.time looked up at each call
        self._jobs = BackgroundJobs(self, "Race watch")
        self._checked: dict[str, float] = {}  # event id -> start time: registration checked
        self._ready: dict[str, float] = {}  # event id -> start time: server ready (told)
        self._ended: dict[str, float] = {}  # event id -> start time: ranks asked again
        self._misses: dict[str, int] = {}  # event id -> reads of your server in a row not answered
        self._timer = QTimer(self)
        self._timer.setInterval(CHECK_MS)
        self._timer.timeout.connect(self.check)
        self._timer.start()

    def is_ready(self, event_id: str) -> bool:
        """Server of your split of that start given (join it from the game)"""
        return event_id in self._ready

    def check(self):
        if not info.enabled():
            return
        now = self._clock()
        if not self._jobs.is_busy("schedule"):  # registrations made in the game seen without any page open
            self._jobs.run("race schedule", info.read, None, lambda _error: None, key="schedule")
        schedule = info.state().schedule
        for event, start in watched_starts(schedule, now):
            event_id = start.event_id
            if event_id in self._ready or self._jobs.is_busy(event_id):
                continue
            entry_type = event.entry_type
            if event_id not in self._checked:
                self._checked[event_id] = start.time
                self._jobs.run("your race", partial(info.read_overview, entry_type, event_id),
                               partial(self.registration_read, event, start), self.ignored, key=event_id)
            elif (now <= start.time + SPLIT_SECONDS and self._misses.get(event_id, 0) < SPLIT_MISSES
                  and info.room() > 0):  # RaceControl asks to wait or limits reached: asked next check, no miss
                self._jobs.run("your server", partial(info.read_split, entry_type, event_id),
                               partial(self.split_read, event, start), self.ignored, key=event_id)
        for _event, start in ended_starts(schedule, now):
            if start.event_id in self._checked and start.event_id not in self._ended:  # followed: your race
                self._ended[start.event_id] = start.time
                from ...rank_info import ranks

                ranks.read_soon()
        for told in (self._checked, self._ready, self._ended):
            for event_id, start_time in list(told.items()):
                if now - start_time > FORGET_SECONDS:
                    del told[event_id]
        for event_id in [event_id for event_id in self._misses if event_id not in self._checked]:
            del self._misses[event_id]

    @staticmethod
    def ignored(_error: BaseException):
        """Read failed (offline, game closed): asked again at the next check"""

    def registration_read(self, event: rs.Event, start: rs.Start, answer: dict | None):
        """Registration checked when the race opens: cancelled or removed told (not read: server read anyway)"""
        if answer is None:
            return
        now = self._clock()
        if rs.event_cancelled(answer):
            self._ready[start.event_id] = start.time  # nothing more to read
            self.tell(race_message("Race cancelled by RaceControl: %1 (%2)", event, start, now),
                      "Race cancelled", event.title)
        elif info.player_id() and not rs.is_registered(answer, info.player_id()):
            self._ready[start.event_id] = start.time
            self.tell(race_message("No longer registered to %1 (%2): registration removed by RaceControl",
                                   event, start, now), "Registration removed", event.title)

    def split_read(self, event: rs.Event, start: rs.Start, split: rs.SplitState | None):
        """Server of your split read: told once ready (not answered SPLIT_MISSES times in a row: no longer asked)"""
        if split is None:
            self._misses[start.event_id] = self._misses.get(start.event_id, 0) + 1
            return
        self._misses.pop(start.event_id, None)
        if not split.ready or start.event_id in self._ready:
            return
        self._ready[start.event_id] = start.time
        now = self._clock()
        message = race_message("Server ready: %1 (%2). Join it from the game (Join Event).", event, start, now)
        detail = event.title
        if split.splits > 1 and split.split:
            message += (("Split %1 of %2", (str(split.split), str(split.splits))),)
            detail = f"{detail} · {split.split}/{split.splits}"
        self.tell(message, "Server ready", detail, sound=True)
        self.changed.emit()

    @staticmethod
    def tell(message: tuple, title: str, detail: str, sound: bool = False):
        """Told like the race reminders (title & detail: Race Notifications overlay), see RaceReminders.tell"""
        from ..notification import message_text
        from .schedule_reminders import RaceReminders

        logger.info("RACE WATCH: %s", message_text(message))
        RaceReminders.tell(message, title, detail, sound)


_watch: RaceWatch | None = None


def race_watch() -> RaceWatch:
    """Your races followed live, created once (after QApplication)"""
    global _watch
    if _watch is None:
        from PySide6.QtCore import QCoreApplication

        _watch = RaceWatch(QCoreApplication.instance())
    return _watch
