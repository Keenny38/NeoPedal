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
Reminders of online races to come (Upcoming Races page): told some minutes before the start, as a notification of
the app and a message of the tray icon (shown over the game), whichever page is open

Kept in the user config folder (race_reminders.json): {"reminders": [{key, title, track, start, minutes}]}, read
when first used (Home page at start, Upcoming Races page), checked every CHECK_MS; reminders told or over are
dropped. Each new read of the schedule (race_schedule_info) moves a reminder whose start moved, or drops it if the
start is gone, and tells it.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, QTimer, Signal

from ...i18n import tr
from .page_settings import load_settings, write_settings

if TYPE_CHECKING:
    from ...process.race_schedule import Event, Schedule

logger = logging.getLogger(__name__)

SETTINGS_FILE = "race_reminders.json"
CHECK_MS = 15000
MINUTES = (5, 10, 30)  # reminder choices before a start
MAX_REMINDERS = 100
MOVE_SECONDS = 3600.0  # start of a reminder gone from the schedule: reminder moved to a start of the race this close


def _valid(entry: Any) -> dict | None:
    if not isinstance(entry, dict):
        return None
    key, start, minutes = entry.get("key"), entry.get("start"), entry.get("minutes")
    if not isinstance(key, str) or not key or isinstance(start, bool) or not isinstance(start, (int, float)):
        return None
    if isinstance(minutes, bool) or not isinstance(minutes, int) or not 0 < minutes <= 24 * 60:
        return None
    return {"key": key, "title": str(entry.get("title") or ""), "track": str(entry.get("track") or ""),
            "start": float(start), "minutes": minutes, "registered": entry.get("registered") is True}


def due_reminders(reminders: list[dict], now: float) -> tuple[list[dict], list[dict]]:
    """Reminders to tell now & reminders kept (not due yet); reminders due while the app was closed (or the PC
    asleep) told if the start is to come, dropped once it passed"""
    told, kept = [], []
    for entry in reminders:
        due = entry["start"] - entry["minutes"] * 60
        if now < due:
            kept.append(entry)
        elif now < entry["start"]:
            told.append(entry)
    return told, kept


def _routes(event: Event) -> tuple[str, ...]:
    """Requests (race_schedule ROUTES keys) a race is read from"""
    return ("schedule", f"daily_{event.tier}") if event.kind == "daily" else (event.kind,)


def follow_schedule(reminders: list[dict], schedule: Schedule,
                    now: float) -> tuple[list[dict], list[tuple[dict, dict]], list[dict]]:
    """Reminders after a new read of the schedule: start gone moved to the closest start of the same race (key
    "<race key>@<start>", see schedule_view.race_key) within MOVE_SECONDS, else dropped; kept as they are when the race is not in the
    schedule or one of its requests was not answered. Reminders kept, moved (old, new) & dropped"""
    from .schedule_view import race_key

    races = {race_key(event, schedule.events): event for event in schedule.events
             if not any(route in schedule.missing for route in _routes(event))}
    keys = {entry["key"] for entry in reminders}
    kept: list[dict] = []
    moved: list[tuple[dict, dict]] = []
    dropped: list[dict] = []
    for entry in reminders:
        race, at, _start = entry["key"].rpartition("@")
        event = races.get(race) if at else None
        times = [start.time for start in event.starts] if event is not None else []
        if event is None or entry["start"] <= now or int(entry["start"]) in map(int, times):
            kept.append(entry)
            continue
        close = [moment for moment in times if moment > now and abs(moment - entry["start"]) <= MOVE_SECONDS
                 and f"{race}@{int(moment)}" not in keys]
        if not close:
            dropped.append(entry)
            continue
        moment = min(close, key=lambda moment: abs(moment - entry["start"]))
        new = {**entry, "key": f"{race}@{int(moment)}", "start": moment}
        keys.add(new["key"])
        kept.append(new)
        moved.append((entry, new))
    return kept, moved, dropped


def reminder_text(entry: dict, now: float) -> str:
    """"LMGT3 Fixed starts in 10 min (Algarve International Circuit)" """
    minutes = max(round((entry["start"] - now) / 60), 1)
    text = tr("%1 starts in %2 min").replace("%1", entry["title"]).replace("%2", str(minutes))
    return f"{text} ({entry['track']})" if entry["track"] else text


def change_text(entry: dict, text: str, now: float) -> str:
    """"Reminder moved: LMGT3 Fixed now starts at 15:30 (Algarve International Circuit)" """
    from .schedule_view import start_text

    text = text.replace("%1", entry["title"]).replace("%2", start_text(entry["start"], now))
    return f"{text} ({entry['track']})" if entry["track"] else text


class RaceReminders(QObject):
    """Race reminders of the app (one object, see reminders())"""

    changed = Signal()

    def __init__(self, parent: QObject | None = None, clock=None):
        super().__init__(parent)
        self._clock = clock if clock is not None else lambda: time.time()  # time.time looked up at each call
        data = load_settings(SETTINGS_FILE).get("reminders")
        self._reminders = [entry for entry in map(_valid, data if isinstance(data, list) else ()) if entry]
        self._serial = -1  # serial of the schedule state last compared with the reminders
        self._timer = QTimer(self)
        self._timer.setInterval(CHECK_MS)
        self._timer.timeout.connect(self.check)
        self._timer.start()
        self.check()

    def keys(self) -> dict[str, int]:
        """Start key -> minutes before of every reminder"""
        return {entry["key"]: entry["minutes"] for entry in self._reminders}

    def minutes_of(self, key: str) -> int:
        return self.keys().get(key, 0)

    def set(self, key: str, title: str, track: str, start: float, minutes: int, registered: bool = False):
        """Reminder of a start set (minutes > 0) or removed (0); registered: set by a registration to that start
        (removed when the player leaves the race, see drop_registered), else set by the player"""
        reminders = [entry for entry in self._reminders if entry["key"] != key]
        if minutes > 0 and start > self._clock():
            reminders.append({"key": key, "title": title, "track": track, "start": start, "minutes": minutes,
                              "registered": registered})
            reminders = sorted(reminders, key=lambda entry: entry["start"])[:MAX_REMINDERS]
        self._reminders = reminders
        self.save()
        self.changed.emit()

    def drop_registered(self, key: str) -> bool:
        """Reminder a registration set for that start removed (player left the race: never told to join a race
        left), one the player set kept; True if removed"""
        if not any(entry["key"] == key and entry["registered"] for entry in self._reminders):
            return False
        self.set(key, "", "", 0.0, 0)
        return True

    def save(self):
        try:
            write_settings(SETTINGS_FILE, {"reminders": self._reminders})
        except OSError as error:
            logger.warning("RACE REMINDERS: not saved: %s", error)

    def check(self):
        now = self._clock()
        changes = self.follow_schedule(now) if self._reminders else []
        told, kept = due_reminders(self._reminders, now)
        if len(kept) == len(self._reminders) and not changes:
            return
        self._reminders = kept
        self.save()
        for text in changes:
            self.tell(text)
        for entry in told:
            self.tell(reminder_text(entry, now))
        self.changed.emit()

    def follow_schedule(self, now: float) -> list[str]:
        """Reminders moved or dropped by a new read of the schedule (none while not read: game closed, failed),
        texts telling it"""
        from ... import race_schedule_info as info

        state = info.state()
        if state.serial == self._serial:
            return []
        self._serial = state.serial
        if state.status != info.READ or not state.schedule.read_time:
            return []
        self._reminders, moved, dropped = follow_schedule(self._reminders, state.schedule, now)
        return ([change_text(new, tr("Reminder moved: %1 now starts at %2"), now) for _old, new in moved]
                + [change_text(entry, tr("Reminder removed: %1 no longer starts at %2"), now) for entry in dropped])

    @staticmethod
    def tell(text: str):
        """Notification of the app & message of the tray icon (shown over the game, window hidden or not)"""
        from PySide6.QtWidgets import QSystemTrayIcon

        from ...const_app import APP_NAME
        from ..notification import main_window, notification_store

        notification_store().add(text, "info")
        window = main_window()
        tray = window.findChild(QSystemTrayIcon) if window is not None else None
        if tray is not None and tray.isVisible() and QSystemTrayIcon.supportsMessages():
            tray.showMessage(APP_NAME, text, QSystemTrayIcon.MessageIcon.Information, 15000)


_reminders: RaceReminders | None = None


def reminders() -> RaceReminders:
    """Race reminders of the app, created once (after QApplication)"""
    global _reminders
    if _reminders is None:
        from PySide6.QtCore import QCoreApplication

        _reminders = RaceReminders(QCoreApplication.instance())
        from .race_watch import race_watch

        race_watch()  # your registered races followed live, started with the reminders
    return _reminders
