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
Journal of the requests the app sends to online services (GitHub, community lap times sheet, public RaceControl
site, badge icons of the game image server)

Memory only, never written: the route (no address of a server, no name, no query) and the status of the last
requests of each service, and how many were sent in the last hour. Shown by the requests dialog of Upcoming Races
and told in the bug report. Any thread may add a line.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import NamedTuple

KEEP_LINES = 40  # lines kept for each service
HOUR = 3600.0
GITHUB = "GitHub"
SHEET = "Lap times sheet"
PUBLIC_SITE = "RaceControl public site"  # public home page, no sign in (process/public_schedule.py)
BADGE_ICONS = "Badge icons"  # game menu image server, no sign in (userfile/badge_icons.py)
NOT_SENT = -1  # status of a request not sent (limits of the app, service asked to wait)


class Line(NamedTuple):
    """One request: time (seconds since epoch), route, status (0: no answer, -1: not sent), milliseconds"""

    time: float
    route: str
    status: int
    milliseconds: int


_lock = threading.Lock()
_lines: dict[str, deque[Line]] = {}
_sent: dict[str, deque[float]] = {}  # time of each request sent in the last hour


def record(service: str, route: str, status: int, milliseconds: float = 0.0, now: float | None = None) -> None:
    """Add a request of service (status: HTTP status, 0 no answer, NOT_SENT not sent: limits)"""
    now = time.time() if now is None else now
    with _lock:
        lines = _lines.setdefault(service, deque(maxlen=KEEP_LINES))
        lines.append(Line(now, route, int(status), int(milliseconds)))
        if status != NOT_SENT:
            sent = _sent.setdefault(service, deque())
            sent.append(now)
            while sent and now - sent[0] >= HOUR:
                sent.popleft()


def snapshot(now: float | None = None) -> dict[str, dict]:
    """By service: requests of the last hour, last lines (newest first)"""
    now = time.time() if now is None else now
    with _lock:
        return {service: {"hour": sum(1 for moment in _sent.get(service, ()) if now - moment < HOUR),
                          "lines": list(reversed(lines))}
                for service, lines in _lines.items()}


def clear() -> None:
    with _lock:
        _lines.clear()
        _sent.clear()
