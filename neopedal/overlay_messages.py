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
App messages shown while driving by the Race Notifications overlay (option show_app_messages) and on the phone by
the Web Dashboard: race reminders, errors. Windows may hide its own notifications over a full screen
game: this is the way they are seen while driving.

Posted on the UI thread, read by the overlay timer (UI thread) & the dashboard server (its own thread): each message
has a serial number, a reader reads the messages posted since the last one it read (none of before it started). The
same message posted again within REPEAT_SECONDS is skipped (module crashing in a loop).
"""

from __future__ import annotations

import threading
from collections import deque
from time import monotonic
from typing import NamedTuple

MAX_KEPT = 8  # latest messages kept (an overlay shows a few at most)
REPEAT_SECONDS = 300.0


class AppMessage(NamedTuple):
    serial: int
    title: str  # English label (translated by the reader: overlay labels)
    detail: str  # in app language
    level: str  # "info", "warning" or "error"


_messages: deque[AppMessage] = deque(maxlen=MAX_KEPT)
_serial = 0
_last_posted: dict[tuple[str, str], float] = {}  # (title, detail): time posted
_lock = threading.Lock()


def post(title: str, detail: str, level: str = "info") -> bool:
    """Message for the overlays & the dashboard showing app messages, False if posted lately (skipped)"""
    global _serial
    now = monotonic()
    with _lock:
        for key in [key for key, posted in _last_posted.items() if now - posted >= REPEAT_SECONDS]:
            del _last_posted[key]
        if (title, detail) in _last_posted:
            return False
        _last_posted[(title, detail)] = now
        _serial += 1
        _messages.append(AppMessage(_serial, title, detail, level))
        return True


def last_serial() -> int:
    """Serial of the last message posted (messages after it are new)"""
    return _serial


def since(serial: int) -> list[AppMessage]:
    """Messages posted after serial, oldest first"""
    with _lock:
        return [message for message in _messages if message.serial > serial]
