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
Reminders of online races to come (Upcoming Races page): told some minutes before the start (and again a few
minutes before it, option), as a notification of the app (Open Upcoming Races, Remind Me in 2 Min), a Windows
notification (shown over the game), a message of the Race Notifications overlay & of the Web Dashboard, a flashing
taskbar button and a sound (option: always, or only while Windows hides its notifications), whichever page is open

Kept in the user config folder (race_reminders.json): {"reminders": [{key, title, track, start, minutes, steps}]}
(steps: minutes before the start still to tell, first the one chosen), read
when first used (Home page at start, Upcoming Races page), checked every CHECK_MS; reminders told or over are
dropped. Each new read of the schedule (race_schedule_info) moves a reminder whose start moved, or drops it if the
start is gone, and tells it. The check timer runs only while reminders are set.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, QTimer, Signal

from ...i18n import tr
from ...setting import cfg
from ..notification import MessageText, message_text
from .page_settings import load_settings, write_settings

if TYPE_CHECKING:
    from ...process.race_schedule import Event, Schedule

logger = logging.getLogger(__name__)

SETTINGS_FILE = "race_reminders.json"
CHECK_MS = 15000
MINUTES = (5, 10, 30)  # reminder choices before a start (with the default one, see reminder_choices)
SCHEDULE_ACTION = "tool:race_schedule_viewer.RaceScheduleViewer"  # Upcoming Races page
MAX_REMINDERS = 100
MOVE_SECONDS = 3600.0  # start of a reminder gone from the schedule: reminder moved to a start of the race this close
SNOOZE_MINUTES = 2  # Remind Me in 2 Min
SNOOZE_PREFIX = "snooze:"  # action key of Remind Me in 2 Min: snooze:[key, title, track, start] (JSON)
# race_reminder_sound choices (regex_pattern.CHOICE_COMMON)
SOUND_HIDDEN, SOUND_ALWAYS, SOUND_NEVER = "When Windows Hides Notifications", "Always", "Never"
# Windows notification states (SHQueryUserNotificationState) hiding notifications: screen saver or locked, full
# screen application, full screen Direct3D game, presentation mode, quiet time
HIDING_STATES = frozenset((1, 2, 3, 4, 6))


def _valid(entry: Any) -> dict | None:
    if not isinstance(entry, dict):
        return None
    key, start, minutes = entry.get("key"), entry.get("start"), entry.get("minutes")
    if not isinstance(key, str) or not key or isinstance(start, bool) or not isinstance(start, (int, float)):
        return None
    if isinstance(minutes, bool) or not isinstance(minutes, int) or not 0 < minutes <= 24 * 60:
        return None
    steps = entry.get("steps")
    if not (isinstance(steps, list) and steps and all(
            isinstance(step, int) and not isinstance(step, bool) and 0 < step <= 24 * 60 for step in steps)):
        steps = [minutes]
    return {"key": key, "title": str(entry.get("title") or ""), "track": str(entry.get("track") or ""),
            "start": float(start), "minutes": minutes, "steps": sorted(set(steps), reverse=True)}


def entry_steps(entry: dict) -> list[int]:
    """Minutes before the start still to tell, earliest first"""
    return entry.get("steps") or [entry["minutes"]]


def due_reminders(reminders: list[dict], now: float) -> tuple[list[dict], list[dict]]:
    """Reminders to tell now & reminders kept (a step not due yet: steps left); reminders due while the app was
    closed (or the PC asleep) told once if the start is to come, dropped once it passed"""
    told, kept = [], []
    for entry in reminders:
        steps = entry_steps(entry)
        left = [step for step in steps if now < entry["start"] - step * 60]
        if len(left) < len(steps) and now < entry["start"]:
            told.append(entry)
        if left and now < entry["start"]:
            kept.append(entry if left == steps else {**entry, "steps": left})
    return told, kept


def _routes(event: Event) -> tuple[str, ...]:
    """Kinds of race read a race comes from (Schedule.missing: not read)"""
    return (event.kind,)


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


def default_minutes() -> int:
    """Minutes before a start of a new reminder (option), first of the reminder choices"""
    minutes = cfg.notification.get("number_of_minutes_before_race_reminder", 10)
    return min(max(minutes, 1), 120) if isinstance(minutes, int) and not isinstance(minutes, bool) else 10


def last_minutes() -> int:
    """Minutes before a start of the last reminder (option), 0 for none"""
    minutes = cfg.notification.get("number_of_minutes_before_last_race_reminder", 0)
    return min(max(minutes, 0), 60) if isinstance(minutes, int) and not isinstance(minutes, bool) else 0


def reminder_steps(minutes: int) -> list[int]:
    """Minutes before a start told for a reminder: the chosen ones, then the last reminder if closer"""
    last = last_minutes()
    return [minutes, last] if 0 < last < minutes else [minutes]


def reminder_choices() -> tuple[int, ...]:
    """Minutes before a start offered for a reminder: usual ones & the default one"""
    return tuple(sorted({*MINUTES, default_minutes()}))


def _with_track(message: tuple, entry: dict) -> MessageText:
    """Track of the race after a message"""
    return (*message, ("(%1)", (entry["track"],))) if entry["track"] else message


def minutes_left(entry: dict, now: float) -> int:
    return max(round((entry["start"] - now) / 60), 1)


def reminder_message(entry: dict, now: float) -> MessageText:
    """"LMGT3 Fixed starts in 10 min (Algarve International Circuit)", see notification.MessageText"""
    return _with_track((("%1 starts in %2 min", (entry["title"], str(minutes_left(entry, now)))),), entry)


def change_message(entry: dict, template: str, now: float) -> MessageText:
    """"Reminder moved: LMGT3 Fixed now starts at 15:30 (Algarve International Circuit)" (English template)"""
    from .schedule_view import start_text

    return _with_track(((template, (entry["title"], start_text(entry["start"], now))),), entry)


def windows_hides_notifications() -> bool:
    """Windows hides its notifications now (full screen game, presentation, locked screen; read only), False if
    unknown or not Windows. Do Not Disturb of Windows 11 is not told by this state."""
    if sys.platform != "win32":
        return False
    import ctypes

    state = ctypes.c_int(0)
    try:
        if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:  # S_OK
            return False
    except (OSError, AttributeError):
        return False
    return state.value in HIDING_STATES


def sound_wanted() -> bool:
    """Reminder sound played now (race_reminder_sound option)"""
    mode = cfg.notification.get("race_reminder_sound", SOUND_HIDDEN)
    return mode == SOUND_ALWAYS or (mode == SOUND_HIDDEN and windows_hides_notifications())


_player: Any = None  # sound file player, made when first used (QtMultimedia imported then)


def play_reminder_sound():
    """Sound of a reminder: sound file of race_reminder_sound_file_name, else the Windows information sound (never
    waited for)"""
    global _player
    filename = cfg.notification.get("race_reminder_sound_file_name", "")
    if isinstance(filename, str) and filename and os.path.isfile(filename):
        from PySide6.QtCore import QCoreApplication, QUrl
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

        if _player is None:
            _player = QMediaPlayer(QCoreApplication.instance())
            _player.setAudioOutput(QAudioOutput(_player))
        _player.setSource(QUrl.fromLocalFile(filename))
        _player.play()
        return
    if sys.platform == "win32":
        import winsound

        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    else:
        from PySide6.QtWidgets import QApplication

        QApplication.beep()


def snooze_action(entry: dict) -> str:
    """Action key of Remind Me in 2 Min of a reminder (kept with the message, works after the reminder is gone)"""
    return SNOOZE_PREFIX + json.dumps([entry["key"], entry["title"], entry["track"], entry["start"]])


def snooze(action: str) -> bool:
    """Remind Me in 2 Min (see snooze_action), False if the start is too close or the action broken"""
    try:
        key, title, track, start = json.loads(action.removeprefix(SNOOZE_PREFIX))
    except (ValueError, TypeError):
        return False
    if not isinstance(key, str) or isinstance(start, bool) or not isinstance(start, (int, float)):
        return False
    return reminders().snooze(key, str(title), str(track), float(start))


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
        self.check()
        self.follow_timer()

    def follow_timer(self):
        """Check timer running only while reminders are set"""
        if not self._reminders:
            self._timer.stop()
        elif not self._timer.isActive():
            self._timer.start()

    def keys(self) -> dict[str, int]:
        """Start key -> minutes before of every reminder"""
        return {entry["key"]: entry["minutes"] for entry in self._reminders}

    def minutes_of(self, key: str) -> int:
        return self.keys().get(key, 0)

    def set(self, key: str, title: str, track: str, start: float, minutes: int, steps: list[int] | None = None):
        """Reminder of a start set (minutes > 0) or removed (0); steps: minutes before the start told (default:
        minutes & the last reminder, see reminder_steps)"""
        reminders = [entry for entry in self._reminders if entry["key"] != key]
        if minutes > 0 and start > self._clock():
            reminders.append({"key": key, "title": title, "track": track, "start": start, "minutes": minutes,
                              "steps": steps or reminder_steps(minutes)})
            reminders = sorted(reminders, key=lambda entry: entry["start"])[:MAX_REMINDERS]
        self._reminders = reminders
        self.save()
        self.follow_timer()
        self.changed.emit()

    def snooze(self, key: str, title: str, track: str, start: float) -> bool:
        """Told again in SNOOZE_MINUTES (a step added to the reminder of that start, or a new one), False if the
        start is too close"""
        minutes = int((start - self._clock()) // 60) - SNOOZE_MINUTES
        if minutes < 1:
            return False
        entry = next((entry for entry in self._reminders if entry["key"] == key), None)
        if entry is not None:
            steps = sorted({*entry_steps(entry), minutes}, reverse=True)
            self.set(key, entry["title"], entry["track"], entry["start"], entry["minutes"], steps)
        else:
            self.set(key, title, track, start, minutes, steps=[minutes])
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
        if not told and not changes and len(kept) == len(self._reminders):  # nothing told, moved or dropped
            return
        self._reminders = kept
        self.save()
        self.follow_timer()
        for message in changes:
            self.tell(message)
        for entry in told:
            self.tell(reminder_message(entry, now), "Reminder",
                      f"{entry['title']} · {tr('%1 min').replace('%1', str(minutes_left(entry, now)))}", sound=True,
                      snooze=snooze_action(entry) if minutes_left(entry, now) > SNOOZE_MINUTES else "")
        self.changed.emit()

    def follow_schedule(self, now: float) -> list[MessageText]:
        """Reminders moved or dropped by a new read of the schedule (none while not read: game closed, failed),
        messages telling it"""
        from ... import race_schedule_info as info

        state = info.state()
        if state.serial == self._serial:
            return []
        self._serial = state.serial
        if state.status != info.PUBLIC or not state.schedule.read_time:
            return []
        self._reminders, moved, dropped = follow_schedule(self._reminders, state.schedule, now)
        return ([change_message(new, "Reminder moved: %1 now starts at %2", now) for _old, new in moved]
                + [change_message(entry, "Reminder removed: %1 no longer starts at %2", now) for entry in dropped])

    @staticmethod
    def tell(message: MessageText, title: str = "Reminder", detail: str = "", sound: bool = False, snooze: str = ""):
        """Notification of the app (Open Upcoming Races, Remind Me in 2 Min with snooze action), Windows notification
        (shown over the game, window hidden or not), message of the Race Notifications overlay & Web Dashboard
        (title: English overlay label, detail: short text, the message if empty), flashing taskbar button & sound
        (option, with sound)"""
        from PySide6.QtWidgets import QApplication

        from ... import overlay_messages
        from ..notification import KIND_REMINDER, main_window, notification_store, tray_message

        text = message_text(message)
        actions = (("Open Upcoming Races", SCHEDULE_ACTION),) + ((("Remind Me in 2 Min", snooze),) if snooze else ())
        notification_store().add(message, "info", actions)
        tray_message(text, "info", SCHEDULE_ACTION, KIND_REMINDER)
        overlay_messages.post(title, detail or text)
        window = main_window()
        if window is not None and window.isVisible():  # taskbar button flashes until the window is used
            QApplication.alert(window, 0)
        if sound and sound_wanted():
            play_reminder_sound()


_reminders: RaceReminders | None = None


def reminders() -> RaceReminders:
    """Race reminders of the app, created once (after QApplication)"""
    global _reminders
    if _reminders is None:
        from PySide6.QtCore import QCoreApplication

        _reminders = RaceReminders(QCoreApplication.instance())
        from .race_watch import race_watch

        race_watch()  # public daily races kept read for the reminders, started with them
    return _reminders
