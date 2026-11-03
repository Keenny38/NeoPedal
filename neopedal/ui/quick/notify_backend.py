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
Notification center (qml/shell/NotificationCenter.qml): messages of the app with level, time & actions (view log,
create bug report, what's new...) in groups by day, filtered by level & searched, modes on (listed under "Now");
a message is marked read once clicked, the messages shown once it closes (not those of another level filter or
search). Warnings & errors can be muted (Don't Show Again), every muted message shown again at once.
"""

from __future__ import annotations

import contextlib

from PySide6.QtCore import Property, QDate, QLocale, QObject, QPoint, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

from ...i18n import current_language, tr
from ..notification import SEVERITIES, message_text, notification_store, run_notification_action
from .models import DictListModel
from .shell_popup import ShellBackend, ShellPopup, popup_size

KIND = "notifications"
# Roles of the messages model ("id" is a QML keyword: entryId)
MESSAGE_ROLES = ("entryId", "text", "severity", "count", "time", "day", "read", "actions")
FILTERS = ("", *SEVERITIES)  # "": every message


def time_text(moment, locale: QLocale | None = None) -> str:
    """Time of a message (its day is the title of its group, see day_text), in app language"""
    locale = locale or QLocale(current_language())
    return locale.toString(moment.time(), QLocale.FormatType.ShortFormat)


def day_text(moment, locale: QLocale | None = None, today: QDate | None = None) -> str:
    """Group of a message: Today, Yesterday, else its date, in app language"""
    days = moment.date().daysTo(today or QDate.currentDate())
    if days == 0:
        return tr("Today")
    if days == 1:
        return tr("Yesterday")
    return (locale or QLocale(current_language())).toString(moment.date(), QLocale.FormatType.LongFormat)


class NotificationBackend(ShellBackend):
    """Messages & modes on for QML, actions run on the main window (popup closed first)

    Messages are a model synced in place (a new message is inserted at the top, a read mark changes one row: the
    history list never rebuilds its delegates); another level filter rebuilds it. Modes on (a few) have their own
    signal. Clear All can be undone while the popup is open.
    """

    entriesChanged = Signal()  # messages (entries, entryCount, unreadCount, counts, filter)
    activeChanged = Signal()  # modes on, listed under "Now"
    undoChanged = Signal()
    searchChanged = Signal()
    mutedChanged = Signal()  # muted messages (mutedCount)

    def __init__(self, window: QWidget):
        super().__init__()
        self._window = window
        self.model = DictListModel(MESSAGE_ROLES, self)
        self._entries: list[dict] = []
        self._active: list[dict] = []
        self._unread = 0
        self._filter = ""
        self._search = ""  # words searched, lower case
        self._muted = 0
        self._counts: dict[str, int] = {}
        self._cleared: list[dict] = []  # messages removed by Clear All (Undo)
        store = notification_store()
        store.changed.connect(self.refresh)
        self.refresh()

    def refresh(self, refilter: bool = False):
        store = notification_store()
        locale, today = QLocale(current_language()), QDate.currentDate()  # once for every message
        entries = [{
            "id": entry["id"], "text": message_text(entry["source"]), "severity": entry["severity"],
            "count": entry["count"], "time": time_text(entry["time"], locale),
            "day": day_text(entry["time"], locale, today), "read": entry["read"],
            "actions": [{"label": tr(action["label"]), "key": action["key"]} for action in entry["actions"]],
        } for entry in store.entries()]
        active = [{"text": text, "key": key} for text, key in store.active()]
        unread, muted = store.unread_count(), store.muted_count()
        if refilter or (entries, unread, muted) != (self._entries, self._unread, self._muted):
            if muted != self._muted:
                self._muted = muted
                self.mutedChanged.emit()
            self._entries, self._unread = entries, unread
            self._counts = {severity: sum(entry["severity"] == severity for entry in entries)
                            for severity in SEVERITIES}
            if self._filter and not self._counts[self._filter]:  # no message left at this level: every message
                self._filter = ""
            shown = self.shown_entries()
            self.model.sync([{"entryId": entry["id"], **{name: entry[name] for name in MESSAGE_ROLES[1:]}}
                             for entry in shown], key="entryId", reset_if_mostly_new=refilter)
            self.entriesChanged.emit()
        if active != self._active:
            self._active = active
            self.activeChanged.emit()

    def shown_entries(self) -> list[dict]:
        """Messages of the level filter & search"""
        words = self._search.split()
        return [entry for entry in self._entries if (not self._filter or entry["severity"] == self._filter)
                and all(word in entry["text"].lower() for word in words)]

    @Property(QObject, constant=True)
    def messages(self) -> QObject:
        """Messages model of the level filter, newest first (QML list)"""
        return self.model

    @Property(list, notify=entriesChanged)
    def entries(self) -> list[dict]:
        """Every message as dicts (Python callers & tests; the QML list reads the model)"""
        return self._entries

    @Property(int, notify=entriesChanged)
    def entryCount(self) -> int:
        return len(self._entries)

    @Property(dict, notify=entriesChanged)
    def counts(self) -> dict:
        """Messages of each level: {"error": 2, "warning": 0, "info": 5}"""
        return self._counts

    @Property(str, notify=entriesChanged)
    def filter(self) -> str:
        """Level shown ("error", "warning", "info"), "" for every message"""
        return self._filter

    @Slot(str)
    def setFilter(self, level: str):
        level = level if level in FILTERS else ""
        if level != self._filter:
            self._filter = level
            self.refresh(refilter=True)

    @Property(str, notify=searchChanged)
    def search(self) -> str:
        return self._search

    @Slot(str)
    def setSearch(self, text: str):
        """Messages containing every word (any case)"""
        text = " ".join(text.lower().split())
        if text != self._search:
            self._search = text
            self.searchChanged.emit()
            self.refresh(refilter=True)

    @Property(int, notify=mutedChanged)
    def mutedCount(self) -> int:
        """Messages not shown again (Don't Show Again)"""
        return self._muted

    @Slot(int)
    def mute(self, entry_id: int):
        notification_store().mute(entry_id)

    @Slot()
    def unmuteAll(self):
        notification_store().unmute_all()

    @Slot(int)
    def markRead(self, entry_id: int):
        """Message clicked: seen"""
        notification_store().mark_read({entry_id})

    @Slot()
    def openSettings(self):
        """Notification settings (Settings page)"""
        self.runAction("option:notification/")

    @Property(list, notify=activeChanged)
    def active(self) -> list[dict]:
        return self._active

    @Property(int, notify=entriesChanged)
    def unreadCount(self) -> int:
        return self._unread

    @Property(bool, notify=undoChanged)
    def canUndoClear(self) -> bool:
        return bool(self._cleared)

    @Slot(str)
    def runAction(self, key: str):
        """Action of a message or mode: popup closed, then run on the main window"""
        self.closeRequested.emit()
        window = self._window
        QTimer.singleShot(0, window, lambda: run_notification_action(window, key))

    @Slot(int)
    def copyText(self, entry_id: int):
        """Text of a message copied (bug report, forum post)"""
        entry = next((entry for entry in self._entries if entry["id"] == entry_id), None)
        if entry is not None:
            QGuiApplication.clipboard().setText(entry["text"])

    @Slot(int)
    def remove(self, entry_id: int):
        notification_store().remove(entry_id)

    @Slot()
    def clearAll(self):
        """Every message removed, Undo at hand while the popup is open"""
        self._cleared = notification_store().clear()
        self.undoChanged.emit()

    @Slot()
    def undoClear(self):
        cleared, self._cleared = self._cleared, []
        notification_store().restore(cleared)
        self.undoChanged.emit()

    @Slot()
    def close(self):
        self.closeRequested.emit()

    def popup_closed(self):
        """Messages shown (level filter & search) seen: marked read, the others stay unread (bell badge)"""
        with contextlib.suppress(RuntimeError, TypeError):  # closed twice: already disconnected
            notification_store().changed.disconnect(self.refresh)
        notification_store().mark_read({entry["id"] for entry in self.shown_entries()})


class NotificationCenter(ShellPopup):
    """Notification center popup"""

    @classmethod
    def open_at(cls, window: QWidget, anchor: QWidget | None = None) -> NotificationCenter | None:
        """Open next to anchor (bell of the rail), or over the window; clicking the bell again closes it"""
        shown = cls.shown(KIND)
        if shown is not None:
            shown.close()
            return None
        if cls.just_closed(KIND):
            return None
        size = popup_size(window, 35, 40)  # em of QML pages
        popup = cls(window, KIND, "NotificationCenter.qml", NotificationBackend(window), size)
        if anchor is not None:
            corner = anchor.mapToGlobal(anchor.rect().bottomRight())
            if anchor.mapTo(window, QPoint(0, 0)).y() < window.height() // 2:  # bell in the title bar: below it
                position = QPoint(corner.x() - size.width() + 1, corner.y() + 4)
            else:  # bell of the rail: opening upward, right of it
                position = QPoint(corner.x() + 4, corner.y() - size.height())
        else:
            frame = window.geometry()
            position = frame.topRight() - popup.rect().topRight()
        popup.popup(position)
        return popup
