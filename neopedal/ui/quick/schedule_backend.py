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
Upcoming Races page backend (qml/analysis/RaceSchedule.qml): online races of Le Mans Ultimate to come

Tabs: daily races (by tier), weekly & special events, championships, co-op events, servers hosted by players.
Races as cards, a compact list or a timeline of the next hours; search, class filter, owned cars only, Open to Me
(races your Safety Rank opens, servers without password & not full). Each race tells your personal best & level of
each class on its track (Driver Stats files). A race opens a menu: driver stats, recorded laps, race calculator,
reminder before the start, calendar export, field of the next start (read on demand, like championship sessions
and co-op leaderboards).

Read in background through race_schedule_info (RaceControl, signed in with the game) while the page shows, again
every few minutes; times to start told again every TICK_MS (FAST_TICK_MS while a start is close). Each list is one
property, told to the page only when changed.
"""

from __future__ import annotations

import contextlib
import logging
import math
import time
from collections.abc import Callable
from functools import partial
from typing import Any, TypeGuard

from PySide6.QtCore import Property, QObject, Signal, Slot

from ... import net_policy as policy
from ... import race_schedule_info as info
from ...i18n import tr
from ...process import race_schedule as rs
from . import page_settings
from .formatting import date_text, long_date_time, relative_date
from .game_pictures import LogoCache, notifier
from .models import DictListModel
from .page_backend import PageBackend
from .race_watch import race_watch
from .schedule_personal import EMPTY as NO_PERSONAL
from .schedule_personal import PersonalData, personal_row, read_personal, stats_track
from .schedule_reminders import default_minutes, reminder_choices, reminders
from .schedule_view import (
    SOON_SECONDS,
    championship_detail_view,
    championship_progress,
    championship_row,
    coop_board_view,
    coop_row,
    counted,
    csv_text,
    event_row,
    field_view,
    frequency_text,
    ics_event,
    leaderboard_class_choices,
    leaderboard_rows,
    place_text,
    practice_view,
    profile_view,
    server_row,
    standing_text,
    start_text,
    tier_text,
    timeline,
    track_of,
)

logger = logging.getLogger(__name__)

SETTINGS_FILE = "race_schedule.json"
ROW_ROLES = ("modelData",)  # page lists: one role holding the row (delegates keep `modelData`)
TICK_MS = 30000  # times to start told again (read again once due, see race_schedule_info.READ_SECONDS)
FAST_TICK_MS = 5000  # while a start is close (SOON_SECONDS): countdown & pulse follow
PERSONAL_SECONDS = policy.PAGE_PERSONAL_SECONDS
MANUAL_SECONDS = policy.PAGE_MANUAL_SECONDS
# a press every minute used up the 120 requests an hour; a press sooner reads what is due
TABS = ("daily", "events", "championships", "coop", "servers")
BOARD_CACHE_SECONDS = policy.PAGE_BOARD_CACHE_SECONDS
UNRANKED_SECONDS = policy.PAGE_UNRANKED_SECONDS
TIMELINE_HOURS = (3, 6, 12)
PLACES_SECONDS = policy.PAGE_PLACES_SECONDS
PLACES_DRIVEN_SECONDS = policy.PAGE_PLACES_DRIVEN_SECONDS
VIEWS = ("cards", "list", "timeline")
LIVE_FIELD_SECONDS = policy.PAGE_LIVE_FIELD_SECONDS
LIVE_FIELD_MISSES = policy.PAGE_LIVE_FIELD_MISSES
LIVE_FIELD_EVERY = policy.PAGE_LIVE_FIELD_EVERY
# lists read every LIVE_READ_SECONDS meanwhile
SERVER_SORTS = ("players", "region", "name")


def player_safety() -> tuple[str, int]:
    """Safety Rank of the player (rank, tier), ("", 0) if unknown"""
    from ...rank_info import ranks

    player = ranks.player
    safety = player.safety if player is not None else None
    return (safety.name, safety.tier) if safety is not None else ("", 0)


def player_name() -> str:
    from ...rank_info import ranks

    player = ranks.player
    return player.name if player is not None else ""


def status_note(status: str, schedule: rs.Schedule) -> tuple[str, str]:
    """Level ("", info, warning) & text telling why the races shown may be old or missing"""
    if status == info.OFF:
        return "warning", tr("Reading races from RaceControl is off (Driver Rank & Safety Rank online option).")
    old = schedule.read_time > 0
    if status == info.NO_GAME:
        # Races last read stay shown: told when (game needed only to read them again, never to see them)
        return "info", (tr("Last read: %1. Start Le Mans Ultimate to update the races.").replace(
            "%1", start_text(schedule.read_time, time.time())) if old
                        else tr("Start Le Mans Ultimate: races are read from RaceControl with the game sign in."))
    if status == info.NO_ACCOUNT:
        return "warning", tr("No RaceControl account found for this Steam account.")
    if status == info.FAILED:
        return "warning", tr("RaceControl did not answer: last races read are shown.") if old else tr(
            "RaceControl did not answer.")
    return "", ""


def requests_status(status: int) -> str:
    """Answer of a request told by the requests dialog: status, "no answer" or "not sent" (limits)"""
    if status == -1:
        return tr("not sent (limits)")
    return str(status) if status > 0 else tr("no answer")


def not_done_text(reason: str, refused: str, silent: str) -> str:
    """Why a registration (or leave) was not done (reason of info.register): RaceControl reason (refused: its text
    with %1), not sent (limits), sent without answer (may be done), else silent"""
    if reason == info.NOT_SENT:
        return tr("Not sent: too many requests to RaceControl for now. Try again in a minute.")
    if reason == info.NO_ANSWER:
        return tr("RaceControl did not answer in time: it may be done anyway. Races are read again, check them "
                  "before trying again.")
    return refused.replace("%1", reason) if reason else silent


def requests_left() -> int:
    """Requests the player's own asks may still send now within RaceControl limits (0 while asked to wait)"""
    from ...rank_info import online_client

    room = getattr(online_client(), "room", None)  # client of tests without it: never limited
    return room() if room is not None else 1


def unread_text(status: str) -> str:
    """Why something asked from the page (detail, car list, leaderboard) was not read: reading off, RaceControl
    refusing this connection (403), game closed, request limits reached (nothing sent), no account, else no answer;
    status: race_schedule_info.unread_status (worker thread) or the status of the last read"""
    if status == info.OFF:
        return status_note(status, rs.EMPTY)[1]
    blocked = info.blocked_minutes()
    if blocked:  # the game is refused too meanwhile
        return tr("Not read: RaceControl refuses requests from this connection for now. Try again in %1 min.").replace(
            "%1", str(blocked))
    if status == info.NO_GAME:
        return tr("Not read: start Le Mans Ultimate and try again.")
    if requests_left() < 1:
        return tr("Not sent: too many requests to RaceControl for now. Try again in a minute.")
    if status == info.NO_ACCOUNT:
        return status_note(status, rs.EMPTY)[1]
    return tr("Not read: RaceControl did not answer. Try again in a moment.")


def read_with_reason(work: Callable[[], Any]) -> tuple[Any, str]:
    """Answer of work & why it is None (unread_text, "" if read), blocking (worker thread: the game may be asked)"""
    answer = work()
    return answer, "" if answer is not None else unread_text(info.unread_status())


def _int_setting(saved: dict, name: str, count: int, default: int = 0) -> int:
    value = saved.get(name)
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < count else default



def read_fields(asked: list[tuple[str, str, str, dict]]) -> list[tuple[str, dict, rs.FieldLevel | None]]:
    """Fields of starts (detail key, event type, event id, extra), read one after another (worker thread); stops
    once RaceControl limits leave no room (starts left out: asked again at a next tick)"""
    read = []
    for detail, kind, event_id, extra in asked:
        if info.room() < 1:
            break
        read.append((detail, extra, info.read_field(kind, event_id)))
    return read

class RaceScheduleBackend(PageBackend):
    """Upcoming Races page state & actions"""

    statusChanged = Signal()
    listsChanged = Signal()
    settingsChanged = Signal()
    detailsChanged = Signal()
    boardChanged = Signal()
    timelineChanged = Signal()
    classesChanged = Signal()
    profileChanged = Signal()
    filtersCleared = Signal()  # search field emptied by the page
    expandedChanged = Signal()
    openHiddenChanged = Signal()
    registrationChanged = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent, "Upcoming Races")
        self.logos = LogoCache()
        self.page_file = page_settings.PageSettings(SETTINGS_FILE, page_settings.SAVE_DELAY_MS, self,
                                                    self.page_settings)
        saved = self.page_file.load()
        self._tab = _int_setting(saved, "tab", len(TABS))
        self._view = _int_setting(saved, "view", len(VIEWS))
        self._server_sort = _int_setting(saved, "server_sort", len(SERVER_SORTS))
        self._open_only = saved.get("open_only") is not False  # on unless turned off
        self._owned_only = saved.get("owned_only") is True
        classes = saved.get("classes")
        self._classes = [name for name in classes if isinstance(name, str)] if isinstance(classes, list) else []
        self._search = ""
        self._values: dict[str, Any] = {
            "status": {}, "daily": [], "events": [], "championships": [], "coop": [], "servers": [], "counts": [],
            "timeline": {}, "classChoices": [], "openHidden": [],
        }
        # Lists as the page shows them: rows updated in place by key (cards kept, a click or an open menu never lost
        # to a list made again at each tick)
        self._models = {name: self.row_model() for name in ("daily", "events", "championships", "coop", "servers",
                                                            "timeline")}
        self._race_models = {tier: self.row_model() for tier in rs.DAILY_TIERS}
        self._open_hidden = [0] * len(TABS)  # rows of each tab hidden by Open to Me only
        self._expanded: list[str] = []  # races with every following start shown
        self._details: dict[str, dict] = {}  # field of a start, championship sessions, co-op board, by key
        self._championship_raw: dict[str, rs.ChampionshipDetail] = {}  # sessions read, worded again at each tick
        self._loading: set[str] = set()  # details being read
        self._loading_list: list[str] = []  # the same, as told to the page
        self._sources: dict[str, Any] = {}  # row key -> (row, event / championship / co-op event)
        self._personal: PersonalData = NO_PERSONAL
        self._personal_time = -PERSONAL_SECONDS
        self._manual_read = -MANUAL_SECONDS  # monotonic time Read Again last asked RaceControl
        self._reading = False
        self._rank_serial = -1
        # Places asked, places left, not ranked & forbidden fields kept when the page is made again (fewer requests)
        self._memory = info.page_memory()
        # leaderboard key -> your rank & drivers ranked (the last ones read once asked before this page was made)
        self._places: dict[str, tuple[int, int]] = (
            dict(info.places()) if self._memory.places_time > -math.inf else {})
        self._board: dict[str, Any] = {"open": False}  # leaderboard shown (see openBoard)
        self._board_source: rs.Board | None = None
        self._board_cache: dict[tuple[str, str, int], tuple[float, rs.Leaderboard]] = {}
        self._unranked = self._memory.unranked  # leaderboard key -> time your place was found 0
        self._profile: dict[str, Any] = {"open": False}
        self._registration: dict[str, Any] = {"open": False}  # registration dialog (see openRegistration)
        self._registration_event: dict | None = None  # event read for it (overview: memory only)
        self._registration_cars: tuple[rs.CarChoice, ...] = ()
        hours = saved.get("timeline_hours")
        self._timeline_hours = hours if hours in TIMELINE_HOURS else 6
        self._timer = self.page_timer(self.tick, TICK_MS)
        notifier().changed.connect(self.pictures_changed)  # track logos fetched from game meanwhile
        reminders().changed.connect(self.reminders_changed)
        race_watch().changed.connect(self.reminders_changed)  # server of your race ready: told on its card
        self._live_fields: dict[str, float] = {}  # field detail key -> monotonic time of its last live read
        self._field_misses = self._memory.field_misses  # event id -> live reads in a row not answered (forbidden)

    @property
    def _places_time(self) -> float:
        return self._memory.places_time

    @_places_time.setter
    def _places_time(self, value: float):
        self._memory.places_time = value

    @property
    def _places_left(self) -> dict[str, rs.Board]:
        return self._memory.places_left

    @_places_left.setter
    def _places_left(self, value: dict[str, rs.Board]):
        self._memory.places_left = value

    # Publishing
    def publish(self, name: str, value: Any, signal: Any):
        if self._values.get(name) != value:
            self._values[name] = value
            signal.emit()

    @Property(dict, notify=statusChanged)
    def status(self) -> dict:
        """Read state: loading, level & note, updated, rank (known, unknown note), option off"""
        return self._values["status"]

    @Property(list, notify=listsChanged)
    def daily(self) -> list:
        """Daily races by tier: tier, tierText, frequency, races (see schedule_view.event_row)"""
        return self._values["daily"]

    @Property(list, notify=listsChanged)
    def events(self) -> list:
        """Weekly & special races (see schedule_view.event_row)"""
        return self._values["events"]

    @Property(list, notify=listsChanged)
    def championships(self) -> list:
        return self._values["championships"]

    @Property(list, notify=listsChanged)
    def coop(self) -> list:
        return self._values["coop"]

    @Property(list, notify=listsChanged)
    def servers(self) -> list:
        return self._values["servers"]

    def row_model(self) -> DictListModel:
        from PySide6.QtQml import QQmlEngine

        model = DictListModel(ROW_ROLES, self)
        QQmlEngine.setObjectOwnership(model, QQmlEngine.ObjectOwnership.CppOwnership)  # also given by raceModel
        return model

    @staticmethod
    def sync_rows(model: DictListModel, rows: list[dict]):
        model.sync([{"key": row["key"], "modelData": row} for row in rows])

    dailyModel = Property(QObject, lambda self: self._models["daily"], constant=True)  # tier groups (no races)
    eventsModel = Property(QObject, lambda self: self._models["events"], constant=True)
    championshipsModel = Property(QObject, lambda self: self._models["championships"], constant=True)
    coopModel = Property(QObject, lambda self: self._models["coop"], constant=True)
    serversModel = Property(QObject, lambda self: self._models["servers"], constant=True)
    timelineModel = Property(QObject, lambda self: self._models["timeline"], constant=True)  # lanes

    @Slot(str, result=QObject)
    def raceModel(self, tier: str) -> QObject | None:
        """Daily races of a tier, as the page shows them"""
        return self._race_models.get(tier)

    @Property(list, notify=listsChanged)
    def counts(self) -> list:
        """Rows of each tab"""
        return self._values["counts"]

    @Property(list, notify=openHiddenChanged)
    def openHidden(self) -> list:
        """Rows of each tab hidden by Open to Me only (empty tab: told why)"""
        return self._values["openHidden"]

    @Property(dict, notify=registrationChanged)
    def registration(self) -> dict:
        return self._registration

    @Property(list, notify=expandedChanged)
    def expandedStarts(self) -> list:
        """Keys of the races showing every following start (kept when lists are made again)"""
        return self._expanded

    @Slot(str, bool)
    def setStartsExpanded(self, key: str, expanded: bool):
        if (key in self._expanded) != expanded:
            self._expanded = [*self._expanded, key] if expanded else [item for item in self._expanded if item != key]
            self.expandedChanged.emit()

    @Property(dict, notify=timelineChanged)
    def timeline(self) -> dict:
        """Next hours of the daily races: marks & lanes (see schedule_view.timeline)"""
        return self._values["timeline"]

    @Property(list, notify=classesChanged)
    def classChoices(self) -> list:
        """Classes of the races & servers read (filter chips): name, label, color, selected"""
        return self._values["classChoices"]

    @Property(dict, notify=detailsChanged)
    def details(self) -> dict:
        """Details read on demand by key: field of a start, championship sessions, co-op leaderboard"""
        return dict(self._details)

    @Property(list, notify=detailsChanged)
    def loadingDetails(self) -> list:
        """Keys of the details being read"""
        return self._loading_list

    @Property(dict, notify=boardChanged)
    def board(self) -> dict:
        """Weekly leaderboard shown: open, title, subtitle, classes, vehicleClass, page, pages, count, rows (see
        schedule_view.leaderboard_rows), myPlace, myPage, loading, error"""
        return self._board

    @Property(int, notify=timelineChanged)
    def timelineHours(self) -> int:
        return self._timeline_hours

    @Property(int, notify=settingsChanged)
    def tab(self) -> int:
        return self._tab

    @Property(int, notify=settingsChanged)
    def view(self) -> int:
        """Races shown as cards (0), a compact list (1) or a timeline (2, daily races)"""
        return self._view

    @Property(int, notify=settingsChanged)
    def serverSort(self) -> int:
        return self._server_sort

    @Property(bool, notify=settingsChanged)
    def openOnly(self) -> bool:
        return self._open_only

    @Property(bool, notify=settingsChanged)
    def ownedOnly(self) -> bool:
        return self._owned_only

    @Property(str, notify=settingsChanged)
    def search(self) -> str:
        return self._search

    # Page state
    def page_shown(self):
        self._timer.start()
        self.publish_all()  # last read (memory, disk) at once
        self.read()
        self.read_personal_due()

    def page_hidden(self):
        self._timer.stop()

    def release_resources(self):
        self._timer.stop()
        self.page_file.flush()
        with contextlib.suppress(RuntimeError, TypeError):  # never connected or already gone
            reminders().changed.disconnect(self.reminders_changed)
        with contextlib.suppress(RuntimeError, TypeError):
            race_watch().changed.disconnect(self.reminders_changed)

    def page_settings(self) -> dict:
        return {"tab": self._tab, "view": self._view, "server_sort": self._server_sort, "open_only": self._open_only,
                "owned_only": self._owned_only, "classes": list(self._classes), "timeline_hours": self._timeline_hours}

    def tick(self):
        if not self.page_visible:
            return
        if info.due(live=True) or (self.servers_shown() and info.hosted_stale()):
            self.read()
        self.read_personal_due()
        self.publish_all()
        self.read_live_fields(time.time())
        self.read_places_left()

    def servers_shown(self) -> bool:
        return TABS[self._tab] == "servers"

    # Reading
    def read(self, force: bool = False, tab: str = ""):
        if self._reading:
            return
        self._reading = True
        self.publish_status()
        servers = self.servers_shown()
        self.jobs.run("race schedule", lambda: info.read(force, live=True, servers=servers, tab=tab), self.read_done,
                      self.read_failed, key="schedule")

    def read_done(self, _state: info.State):
        self._reading = False
        self.publish_all()
        self.read_places_due()

    def read_places_due(self, force: bool = False):
        """Your place in the weekly leaderboard of each race & current championship round, in background when due"""
        if not force and (time.monotonic() - self._places_time < policy.stretch(PLACES_SECONDS) or self.jobs.is_busy("places")):
            return
        schedule = info.state().schedule
        boards = {event.board.key: event.board for event in schedule.events if event.board is not None}
        tracks = {event.board.key: (event.track, event.scene) for event in schedule.events if event.board is not None}
        for item in schedule.championships:
            current = item.current_round(time.time())
            if current is not None and current.board is not None:
                boards[current.board.key] = current.board
                tracks[current.board.key] = (current.track, current.scene)
        if not force:  # only the tracks driven lately (driver stats read: none before, asked again when read)
            boards = {key: board for key, board in boards.items() if self.driven_lately(*tracks[key])}
        now = time.monotonic()
        if not force:  # not ranked there a while ago: asked again later (fewer asks)
            boards = {key: board for key, board in boards.items()
                      if now - self._unranked.get(key, -UNRANKED_SECONDS) >= UNRANKED_SECONDS}
        if not boards or not info.enabled():
            return
        self._places_time = time.monotonic()
        self.read_places_of(boards)

    def read_places_of(self, boards: dict[str, rs.Board]):
        """Places of these leaderboards in background; the ones RaceControl limits left unasked kept for a next tick
        (read_places_left)"""
        self._places_left = {}
        asked: set[str] = set()

        def done(places: dict):
            self._places_left = {key: board for key, board in boards.items() if key not in asked}
            self.places_read(places)

        self.jobs.run("your places", lambda: info.read_places(boards, asked), done, self.places_failed,
                      key="places")

    def read_places_left(self):
        """Places not asked at the last read (RaceControl limits reached) asked once there is room again"""
        if self._places_left and not self.jobs.is_busy("places") and info.room() >= 2:
            self.read_places_of(self._places_left)

    def places_read(self, places: dict):
        now = time.monotonic()
        for key, (rank, _count) in places.items():
            if rank:
                self._unranked.pop(key, None)
            else:
                self._unranked[key] = now
        self._places = {**self._places, **places}
        info.set_places(self._places)  # Home card
        self.publish_all()

    def places_failed(self, error: BaseException):
        logger.warning("RACE SCHEDULE: leaderboard places not read: %s", error)

    def read_failed(self, error: BaseException):
        logger.warning("RACE SCHEDULE: not read: %s", error)
        self._reading = False
        self.publish_all()

    def read_personal_due(self):
        """Driver stats, session history & community lap times read in background when due"""
        if time.monotonic() - self._personal_time < PERSONAL_SECONDS or self.jobs.is_busy("personal"):
            return
        self._personal_time = time.monotonic()
        self.jobs.run("your laps", read_personal, self.personal_read, self.personal_failed, key="personal")

    def driven_lately(self, track: str, scene: str) -> bool:
        """A session on that track in the last PLACES_DRIVEN_SECONDS (history of driver stats)"""
        data = self._personal
        key = stats_track(data, track, scene)
        return bool(key) and 0 <= time.time() - data.last_driven.get(key, 0.0) < PLACES_DRIVEN_SECONDS

    def personal_read(self, data: PersonalData):
        first = self._personal is NO_PERSONAL
        self._personal = data
        self.publish_all()
        if first:  # places wait for the tracks you drove
            self.read_places_due()

    def personal_failed(self, error: BaseException):
        logger.warning("RACE SCHEDULE: driver stats not read: %s", error)

    @Slot()
    def pictures_changed(self):
        if self.defer_while_hidden(self.pictures_changed):
            return
        self.publish_all()

    @Slot()
    def reminders_changed(self):
        if self.defer_while_hidden(self.reminders_changed):
            return
        self.publish_all()

    @Slot()
    def refresh(self):
        """Setting changed: texts made again (once shown)"""
        if self.defer_while_hidden(self.refresh):
            return
        self.publish_all()

    def publish_status(self):
        from ...rank_info import ranks

        ranks.poll()  # ranks read in background when due (page opened before Home read them)
        self._rank_serial = ranks.serial
        state = info.state()
        schedule = state.schedule
        level, note = status_note(state.status, schedule)
        blocked = info.blocked_minutes()
        if blocked:  # RaceControl refuses this connection: nothing asked (the game is refused too meanwhile)
            level, note = "warning", tr("RaceControl refuses requests from this connection for now (probably too "
                                        "many): nothing is asked for %1 min. The game is refused too meanwhile.").replace(
                "%1", str(blocked))
        safety = player_safety()
        self.publish("status", {
            "loading": self._reading,
            "level": level,
            "note": note,
            "off": state.status == info.OFF,
            "noGame": state.status == info.NO_GAME,
            "read": schedule.read_time > 0,
            "updated": date_text(schedule.read_time) if schedule.read_time > 0 else "",
            "age": relative_date(schedule.read_time) if schedule.read_time > 0 else "",  # "5 min ago": always told
            "readFull": long_date_time(schedule.read_time) if schedule.read_time > 0 else "",
            "rank": f"SR {safety[0]} {safety[1]}" if safety[0] else tr("SR unknown"),
            "rankKnown": bool(safety[0]),
        }, self.statusChanged)

    # Rows
    def level_color(self, level: int) -> str:
        """Community level color as on the Driver Stats page (colorblind palette, darker on a light theme)"""
        if level < 0:
            return ""
        from PySide6.QtGui import QColor, QPalette
        from PySide6.QtWidgets import QApplication

        from ...setting import cfg
        from ...userfile.lap_reference import LEVEL_COLORS
        from .. import colorblind_state
        from .stats_common import COLORBLIND_LEVEL_COLORS, CONFIG_NAME

        config = cfg.user.config.get(CONFIG_NAME, {})
        colorblind = colorblind_state().enabled or bool(config.get("enable_colorblind_colors", False))
        color = QColor((COLORBLIND_LEVEL_COLORS if colorblind else LEVEL_COLORS)[level])
        if QApplication.palette().color(QPalette.ColorRole.Window).lightness() >= 128:
            color = color.darker(135)
        return color.name()

    def personal(self, track: str, scene: str) -> dict:
        from ...setting import cfg
        from .stats_common import CONFIG_NAME

        use_reference = bool(cfg.user.config.get(CONFIG_NAME, {}).get("enable_lap_reference", True))
        return personal_row(self._personal, track, scene, self.level_color, use_reference)

    def shown(self, row: dict | None, tab: int = -1) -> TypeGuard[dict]:
        """Row kept by the filters: Open to Me, owned only, classes, search (rows of tab hidden by Open to Me only
        counted)"""
        if row is None:
            return False
        if self._owned_only and row.get("carsOwned") is False:
            return False
        if self._classes and not set(self._classes) & set(row.get("classNames", ())):
            return False
        if self._search and self._search not in row.get("search", ""):
            return False
        if self._open_only and row.get("open") == 0:
            if tab >= 0:
                self._open_hidden[tab] += 1
            return False
        return True

    def with_extras(self, row: dict, source: Any, track: str = "", scene: str = "") -> dict:
        """Row with your laps on its track, its reminder & details read on demand"""
        self._sources[row["key"]] = (row, source)
        if track:
            row["personal"] = self.personal(track, scene)
        start_key = row.get("startKey", "")
        row["reminder"] = reminders().minutes_of(start_key) if start_key else 0
        rank, count = self._places.get(row.get("board", ""), (0, 0))
        row["place"] = place_text(rank, count)
        if isinstance(source, rs.Event):
            row["serverReady"] = race_watch().is_ready(row.get("eventId", ""))
        return row

    def publish_all(self):
        """Every list made again from the last read (times to start move on)"""
        from ...rank_info import ranks

        self.publish_status()
        state = info.state()
        schedule, now, safety = state.schedule, time.time(), player_safety()

        def logo(track: str) -> str:
            return self.logos.track(track) if track else ""

        self._sources = {}
        self._open_hidden = [0] * len(TABS)
        daily: list[dict[str, Any]] = []
        for tier in rs.DAILY_TIERS:
            rows = [self.with_extras(row, event, row["track"], event.scene) for event in schedule.events
                    if event.kind == "daily" and event.tier == tier
                    if self.shown(row := event_row(event, schedule, safety, now, logo), 0)]
            if rows:
                rows.sort(key=lambda row: row["startTime"])
                daily.append({"tier": tier, "tierText": tier_text(tier), "races": rows,
                              "frequency": frequency_text(schedule.frequency.get(tier, 0.0))})
        events = [self.with_extras(row, event, row["track"], event.scene) for event in schedule.events
                  if event.kind != "daily" if self.shown(row := event_row(event, schedule, safety, now, logo), 1)]
        events.sort(key=lambda row: row["startTime"])
        championships = [self.with_extras(row, item, row["roundTrack"], row["roundScene"])
                         for item in schedule.championships
                         if self.shown(row := championship_row(item, schedule, safety, now, logo), 2)]
        coop = [self.with_extras(row, event, row["track"], row["scene"]) for event in schedule.coop
                if (row := coop_row(event, schedule, now, logo)) is not None
                and (not self._search or self._search in row["search"])
                and not (self._owned_only and row["carsOwned"] is False)]
        pairs = [(server_row(server, schedule, logo), server) for server in schedule.servers]
        servers = [self.with_extras(row, server, row["track"], server.scene) for row, server in pairs  # its menu
                   if (not self._classes or set(self._classes) & set(row["classNames"]))
                   and (not self._search or self._search in row["search"])
                   and not (self._owned_only and row["owned"])]
        locked = [row for row in servers if row["password"] or row["full"]] if self._open_only else []
        if locked:
            self._open_hidden[4] = len(locked)
            servers = [row for row in servers if not (row["password"] or row["full"])]
        sort = SERVER_SORTS[self._server_sort]
        if sort == "region":
            servers.sort(key=lambda row: (row["region"].casefold(), -row["playerCount"]))
        elif sort == "name":
            servers.sort(key=lambda row: row["name"].casefold())
        names: dict[str, None] = {}
        car_lists = [*(item.cars for item in schedule.events), *(item.cars for item in schedule.championships),
                     *(item.cars for item in schedule.servers)]
        for cars in car_lists:
            names.update(dict.fromkeys(rs.classes_of(cars, schedule.cars)))
        from ...formatter import class_style

        choices = [{"name": name, "label": class_style(name)[0], "color": class_style(name)[1],
                    "selected": name in self._classes, "missing": False} for name in sorted(names)]
        # Class chosen before but in no race now: still filtering, so shown checked (dim), removable in one click
        choices += [{"name": name, "label": class_style(name)[0], "color": class_style(name)[1], "selected": True,
                     "missing": True} for name in self._classes if name not in names]
        lists = {"daily": daily, "events": events, "championships": championships, "coop": coop, "servers": servers}
        self.publish("openHidden", list(self._open_hidden), self.openHiddenChanged)
        line = timeline(((group["tier"], group["races"]) for group in daily), schedule, now, self._timeline_hours)
        self.sync_rows(self._models["timeline"], line["lanes"])
        self.publish("timeline", line, self.timelineChanged)
        self.publish("classChoices", choices, self.classesChanged)
        counts = [sum(len(group["races"]) for group in daily), len(events), len(championships), len(coop),
                  len(servers)]
        if any(self._values[name] != value for name, value in lists.items()) or self._values["counts"] != counts:
            self._values.update(lists)
            self._values["counts"] = counts
            for name in ("events", "championships", "coop", "servers"):
                self.sync_rows(self._models[name], lists[name])
            groups = {group["tier"]: group for group in daily}
            for tier, model in self._race_models.items():
                self.sync_rows(model, groups[tier]["races"] if tier in groups else [])
            self._models["daily"].sync([{"key": group["tier"], "modelData": {
                "tier": group["tier"], "tierText": group["tierText"], "frequency": group["frequency"],
                "count": len(group["races"])}} for group in daily])
            self.listsChanged.emit()
        soon = any(0 < row["startTime"] - now <= SOON_SECONDS
                   for row in (*events, *championships, *(race for group in daily for race in group["races"])))
        self._timer.setInterval(FAST_TICK_MS if soon else TICK_MS)
        self._rank_serial = ranks.serial
        self.refresh_details(now)

    # Settings
    @Slot(int)
    def setTab(self, index: int):
        if 0 <= index < len(TABS) and index != self._tab:
            self._tab = index
            self.settingsChanged.emit()
            self.page_file.save()
            if self.page_visible and self.servers_shown() and info.hosted_stale():  # read only on their tab
                self.read()

    @Slot(int)
    def setView(self, index: int):
        if 0 <= index < len(VIEWS) and index != self._view:
            self._view = index
            self.settingsChanged.emit()
            self.page_file.save()

    @Slot(int)
    def setTimelineHours(self, hours: int):
        if hours in TIMELINE_HOURS and hours != self._timeline_hours:
            self._timeline_hours = hours
            self.timelineChanged.emit()
            self.page_file.save()
            self.publish_all()

    @Slot(int)
    def setServerSort(self, index: int):
        if 0 <= index < len(SERVER_SORTS) and index != self._server_sort:
            self._server_sort = index
            self.settingsChanged.emit()
            self.page_file.save()
            self.publish_all()

    @Slot(bool)
    def setOpenOnly(self, value: bool):
        if value != self._open_only:
            self._open_only = value
            self.settingsChanged.emit()
            self.page_file.save()
            self.publish_all()

    @Slot(bool)
    def setOwnedOnly(self, value: bool):
        if value != self._owned_only:
            self._owned_only = value
            self.settingsChanged.emit()
            self.page_file.save()
            self.publish_all()

    @Slot(str)
    def toggleClass(self, name: str):
        self._classes = [item for item in self._classes if item != name] if name in self._classes else [
            *self._classes, name]
        self.settingsChanged.emit()
        self.page_file.save()
        self.publish_all()

    @Slot()
    def clearFilters(self):
        self._classes, self._search, self._owned_only = [], "", False
        self.filtersCleared.emit()
        self.settingsChanged.emit()
        self.page_file.save()
        self.publish_all()

    @Slot(str)
    def setSearch(self, text: str):
        text = text.strip().casefold()
        if text != self._search:
            self._search = text
            self.settingsChanged.emit()
            self.publish_all()

    @Slot()
    def readAgain(self):
        self._personal_time = -PERSONAL_SECONDS
        now = time.monotonic()
        if now - self._manual_read >= MANUAL_SECONDS:  # asked again too soon: read only what is due
            self._manual_read = now
            self.read(force=True, tab=TABS[self._tab])
        else:
            self.read()
        self.read_personal_due()

    @Slot(result="QVariantList")
    def requestsReport(self) -> list:
        """Requests sent to online services since the app started (request_log): by service, how many in the last
        hour against its limit, the last ones (time, route, answer)"""
        from ... import request_log
        from ...process import raceos

        limits = {request_log.RACE_CONTROL: policy.hour_cap(raceos.MAX_PER_HOUR), request_log.GITHUB: 60}
        report = []
        for service, data in request_log.snapshot().items():
            limit = limits.get(service, 0)
            summary = (tr("%1 requests in the last hour (limit %2)").replace("%1", str(data["hour"])).replace(
                "%2", str(limit)) if limit else tr("%1 requests in the last hour").replace("%1", str(data["hour"])))
            lines = [{"when": time.strftime("%H:%M:%S", time.localtime(line.time)),
                      "text": f"{line.route}  ·  {requests_status(line.status)}"
                              + (f"  ·  {line.milliseconds} ms" if line.milliseconds else "")}
                     for line in data["lines"][:20]]
            report.append({"name": service, "summary": summary, "lines": lines})
        return report

    @Slot()
    def openOnlineOption(self):
        """Settings page on the RaceControl online option"""
        from ..app_settings import open_app_settings

        open_app_settings(self.parent(), "application", "enable_online_driver_ranks")

    # Menu of a race
    @staticmethod
    def menu_start(row: dict, source: Any, start: float = 0.0) -> dict | None:
        """Start a menu acts on: the row's first (card, list) or the one at start (timeline block): reminder key,
        time, end, event id ("" unknown), field detail key, player registered, registration opening (0 unknown);
        None once that start is gone"""
        first = row.get("startTime", 0.0)
        found = next((item for item in source.starts if abs(item.time - (start or first)) < 1), None) if isinstance(
            source, rs.Event) else None
        if not start or abs(start - first) < 1:
            return {"key": row.get("startKey", ""), "time": first, "end": row.get("endTime", first),
                    "eventId": row.get("eventId", ""), "detail": f"field:{row['key']}",
                    "registered": found.registered if found is not None else row.get("registeredMe") is True,
                    "opens": found.opens if found is not None else 0.0}
        if found is None:
            return None
        key = f"{row['key']}@{int(found.time)}"
        return {"key": key, "time": found.time, "end": found.time + row.get("endTime", first) - first,
                "eventId": found.event_id, "detail": f"field:{key}", "registered": found.registered,
                "opens": found.opens}

    @staticmethod
    def registration_entries(row: dict, source: rs.Event, chosen: dict, now: float) -> list[dict]:
        """Register or leave entry of a start; game started first when closed (RaceControl signs in with it)"""
        status = info.state().status
        if source.team:
            return [{"id": "register", "text": tr("Register in the Game (Team Race)"), "enabled": False,
                     "vehicle": ""}]
        if status == info.NO_GAME:
            return [{"id": "launch", "text": tr("Start Le Mans Ultimate to Register"), "enabled": True,
                     "vehicle": ""}]
        possible = bool(chosen["eventId"]) and status != info.OFF
        if chosen["registered"]:
            return [{"id": "unregister", "text": tr("Leave This Race…"), "enabled": possible, "vehicle": ""}]
        opened = chosen["opens"] <= now
        return [{"id": "register", "vehicle": "", "enabled": possible and opened and row.get("open") != 0,
                 "text": tr("Register…") if opened else tr("Registration Opens %1").replace(
                     "%1", start_text(chosen["opens"], now))}]

    @Slot(str, result=list)
    @Slot(str, float, result=list)
    def raceActions(self, key: str, start: float = 0.0) -> list:
        """Entries of the menu of a race, championship or co-op event: id, text, enabled, vehicle, section (separator
        between two sections: race, plan, mine), menu (title of the submenu it is in, "": the menu itself; checked:
        reminder entries; detail & detailTitle: field entry). start: start of a timeline block (0: the row's first)"""
        found = self._sources.get(key)
        if found is None:
            return []
        row, source = found
        chosen = self.menu_start(row, source, start)
        now = time.time()
        upcoming = isinstance(source, rs.Event) and chosen is not None and chosen["time"] > now
        entries = []

        def add(section: str, entry: dict, menu: str = ""):
            entries.append({"enabled": True, "vehicle": "", **entry, "section": section, "menu": menu})

        # The race: register (first: what the menu is mostly opened for), its field, its leaderboard
        if upcoming and chosen is not None:
            for entry in self.registration_entries(row, source, chosen, now):
                add("race", entry)
            when = start_text(chosen["time"], now)
            add("race", {"id": "field", "text": tr("Show Field"), "enabled": bool(chosen["eventId"]),
                         "detail": chosen["detail"], "detailTitle": f"{when} · {row['title']}"})
        if isinstance(source, rs.Event) and not source.team:  # read again at each click (players move on)
            add("race", {"id": "practice", "text": tr("Practice Servers"), "detail": f"practice:{key}",
                         "detailTitle": row.get("title", "")})
        if row.get("board"):
            add("race", {"id": "board", "text": tr("Round Leaderboard") if isinstance(source, rs.Championship)
                         else tr("Weekly Leaderboard")})
        # Planning: reminder minutes in one submenu (start time in its title, not repeated on each entry), calendar
        if upcoming and chosen is not None:
            current = reminders().minutes_of(chosen["key"]) if chosen["key"] else 0
            remind = tr("Remind Me Before %1").replace("%1", when)
            for minutes in reminder_choices():
                add("plan", {"id": f"remind:{minutes}", "text": tr("%1 min").replace("%1", str(minutes)),
                             "checked": current == minutes}, remind)
            if current:
                add("plan", {"id": "remind:0", "text": tr("Cancel Reminder")}, remind)
        if isinstance(source, rs.Championship) or (isinstance(source, rs.Event) and chosen is not None):
            add("plan", {"id": "export", "text": tr("Export to Calendar…")})
        # Mine: stats, laps & calculator of the classes driven there; one submenu per action when several classes
        personal = row.get("personal", {})
        bests = personal.get("bests", [])
        several = len(bests) > 1
        for action, plain, single in (("stats", tr("Driver Stats"), tr("Driver Stats · %1")),
                                      ("laps", tr("Recorded Laps"), tr("Recorded Laps · %1")),
                                      ("prepare", tr("Prepare Race"), tr("Prepare Race · %1"))):
            for best in bests:
                name = best["vehicleClass"]
                add("mine", {"id": action, "vehicle": best["vehicle"],
                             "enabled": action != "laps" or bool(best["lapsFolder"]),
                             "text": name if several else single.replace("%1", name)},
                    plain if several else "")
        if not bests:
            add("mine", {"id": "stats", "text": tr("Track Stats"), "enabled": bool(personal.get("known"))})
            add("mine", {"id": "prepare", "text": tr("Prepare Race in Calculator"),
                         "enabled": bool(row.get("track") or row.get("roundTrack"))})
        return entries

    @Slot(str, str, str)
    @Slot(str, str, str, float)
    def runRaceAction(self, key: str, action: str, vehicle: str, start: float = 0.0):
        """Menu entry chosen; start: start of a timeline block (0: the row's first)"""
        found = self._sources.get(key)
        if found is None:
            return
        row, source = found
        personal = row.get("personal", {})
        track = personal.get("statsTrack") or row.get("track") or row.get("roundTrack", "")
        if action == "stats":
            self.open_stats(personal.get("statsTrack", ""), vehicle)
        elif action == "laps":
            folder = next((best["lapsFolder"] for best in personal.get("bests", []) if best["vehicle"] == vehicle), "")
            self.open_laps(folder)
        elif action == "prepare":
            best = next((best["seconds"] for best in personal.get("bests", []) if best["vehicle"] == vehicle), 0.0)
            self.prepare_race(track, vehicle, best)
        elif action.startswith("remind:"):
            chosen = self.menu_start(row, source, start)
            if chosen is None or not chosen["key"]:
                return
            minutes = int(action.split(":", 1)[1])
            reminders().set(chosen["key"], row["title"], row["track"], chosen["time"], minutes)
        elif action == "field":
            self.read_field(key, start)
        elif action == "practice":
            self.read_practice(key)
        elif action == "launch":
            self.start_game()
        elif action == "register":
            self.openRegistration(key, start)
        elif action == "unregister":
            self.leave_race(key, start)
        elif action == "board":
            self.openBoard(key)
        elif action == "export":
            self.export_calendar(key, start)

    def host_window(self):
        widget = self.parent()
        return widget.window() if widget is not None and hasattr(widget, "window") else None

    def open_stats(self, track: str, vehicle: str):
        from ..tools_view import open_tool

        viewer = open_tool("driver_stats_viewer.DriverStatsViewer", self.parent())
        backend = getattr(viewer, "backend", None)
        if backend is not None and track:
            backend.show_combo(track, vehicle)

    def open_laps(self, folder: str):
        if not folder:
            return
        from ..tools_view import open_tool

        viewer = open_tool("lap_viewer.LapViewer", self.parent())
        backend = getattr(viewer, "backend", None)
        if backend is None:
            return
        if folder not in backend.tracks:  # recorded since the lap viewer opened
            backend.refresh()
        backend.currentTrack = folder

    def prepare_race(self, track: str, vehicle: str, lap_time: float):
        from .stats_overview import race_preparation

        prepare = race_preparation()
        if prepare is None or not track:
            return
        try:
            prepare(self.parent(), track, vehicle, lap_time)
        except Exception:  # calculator of another page: logged, never breaks this page
            logger.exception("RACE SCHEDULE: race calculator not prepared for %s, %s", track, vehicle)

    # Game start & registration (joining the server stays in the game: car, livery & settings set by its menu)
    def host_widget(self):
        from PySide6.QtWidgets import QWidget

        widget = self.parent()
        return widget if isinstance(widget, QWidget) else None

    def toast(self, text: str, level: str = "success"):
        from .dialogs import page_toast

        page_toast(self.host_widget(), text, level)

    @Slot()
    def startGame(self):
        """Le Mans Ultimate started by Steam: races read again once it answers"""
        from .replays_common import start_game

        if start_game():
            self.toast(tr("Le Mans Ultimate is starting: races are read again once it answers."), "info")
        else:
            self.toast(tr("Steam could not be opened: start Le Mans Ultimate yourself"), "warning")

    def start_game(self):
        self.startGame()

    def set_registration(self, value: dict):
        if value != self._registration:
            self._registration = value
            self.registrationChanged.emit()

    def other_registration(self, source: rs.Event, event_id: str, now: float) -> str:
        """Note when the player is registered to another start of the same kind & tier (RaceControl allows one at
        a time without RaceControl Pro)"""
        for event in info.state().schedule.events:
            if event.kind != source.kind or event.tier != source.tier:
                continue
            for start in event.starts:
                if start.registered and start.event_id != event_id and start.time > now:
                    return tr("You are already registered to %1 at %2: RaceControl may allow only one race of this "
                              "tier at a time.").replace("%1", event.title).replace("%2", start_text(start.time, now))
        return ""

    @Slot(str)
    @Slot(str, float)
    def openRegistration(self, key: str, start: float = 0.0):
        """Registration dialog of a start: event & your cars read, then one chosen (confirmRegistration)"""
        found = self._sources.get(key)
        if found is None or not isinstance(found[1], rs.Event):
            return
        row, source = found
        chosen = self.menu_start(row, source, start)
        if chosen is None or not chosen["eventId"] or self._registration.get("busy") is True:
            return
        now = time.time()
        entry_type, event_id = source.entry_type, chosen["eventId"]
        self.jobs.cancel("registration")
        self._registration_event, self._registration_cars = None, ()
        self.set_registration({
            "open": True, "loading": True, "busy": False, "error": "", "cars": [], "eventId": event_id,
            "title": row["title"], "track": row["track"], "when": start_text(chosen["time"], now),
            "startKey": chosen["key"], "startTime": chosen["time"],
            "note": self.other_registration(source, event_id, now),
        })
        def work():
            event, reason = read_with_reason(lambda: info.read_overview(entry_type, event_id))
            return event, info.game_cars(), reason

        self.jobs.run("registration", work, lambda result: self.registration_read(event_id, *result),
                      lambda error: self.registration_read(event_id, None, None), key="registration")

    def registration_read(self, event_id: str, event: dict | None, game_cars: object, reason: str = ""):
        current = self._registration
        if current.get("open") is not True or current.get("eventId") != event_id:
            return  # dialog closed, or opened for another start meanwhile
        error = ""
        cars: tuple[rs.CarChoice, ...] = ()
        if event is None:
            error = reason or unread_text(info.state().status)
        elif event.get("teamEvent") is True:
            error = tr("Team races are registered in the game (team & line-up).")
        elif rs.is_registered(event, info.player_id()):
            error = tr("You are already registered to this race.")
        else:
            cars = rs.car_choices(event, game_cars)
            if not cars:
                error = tr("None of the cars of this race is in your garage (or the game did not list them).")
        self._registration_event, self._registration_cars = (event, cars) if cars else (None, ())
        self.set_registration({**current, "loading": False, "error": error, "cars": [
            {"index": index, "vehicleClass": car.vehicle_class, "model": car.model, "livery": car.livery}
            for index, car in enumerate(cars)]})

    @Slot(int)
    def confirmRegistration(self, index: int):
        """Player registered with the car (index of registration cars) of the dialog"""
        event, cars, current = self._registration_event, self._registration_cars, self._registration
        if event is None or not 0 <= index < len(cars) or current.get("busy") is True:
            return
        car = cars[index]
        self.set_registration({**current, "busy": True, "error": ""})
        self.jobs.run("register", lambda: info.register(event, car),
                      lambda result: self.registered(current, car, *result),
                      lambda error: self.registered(current, car, False, ""), key="register")

    def registered(self, asked: dict, car: rs.CarChoice, done: bool, reason: str):
        """Registration answered: dialog closed with a reminder before the start, or refusal told in it"""
        if not done:
            if reason == info.NO_ANSWER:  # may be done anyway: lists read again
                self.read(force=True)
            if self._registration.get("eventId") == asked["eventId"]:
                self.set_registration({**self._registration, "busy": False, "error": not_done_text(
                    reason, tr("RaceControl refused the registration: %1"),
                    tr("Registration not done: RaceControl did not answer."))})
            return
        if self._registration.get("eventId") == asked["eventId"]:
            self.set_registration({"open": False})
        key, start = asked["startKey"], asked["startTime"]
        minutes = reminders().minutes_of(key) if key else 0
        if key and not minutes:
            minutes = default_minutes()  # option: reminder of a start registered from the page (none set yet)
            reminders().set(key, asked["title"], asked["track"], start, minutes, registered=True)
        self.publish_all()
        self.toast(tr("Registered to %1 (%2) with %3. Join the server from the game when it opens: reminder %4 min "
                      "before.").replace("%1", asked["title"]).replace("%2", asked["when"]).replace(
            "%3", car.livery).replace("%4", str(minutes)))

    @Slot()
    def closeRegistration(self):
        """Dialog closed: car list read dropped (a registration sent still answers: told by a toast)"""
        if self._registration.get("busy") is not True:
            self.jobs.cancel("registration")
        self._registration_event, self._registration_cars = None, ()
        self.set_registration({"open": False})

    def leave_race(self, key: str, start: float = 0.0):
        """Registration to a start removed after confirmation"""
        import html

        from .dialogs import confirm

        found = self._sources.get(key)
        if found is None or not isinstance(found[1], rs.Event):
            return
        row, source = found
        chosen = self.menu_start(row, source, start)
        if chosen is None or not chosen["eventId"]:
            return
        entry_type, event_id, title, start_key = source.entry_type, chosen["eventId"], row["title"], chosen["key"]
        when = start_text(chosen["time"], time.time())

        def answered(result: tuple[bool, str]):
            done, reason = result
            if done:
                if start_key:  # reminder the registration set: no "join the server" call for a race left
                    reminders().drop_registered(start_key)
                self.publish_all()
                self.toast(tr("No longer registered to %1 (%2).").replace("%1", title).replace("%2", when))
            else:
                if reason == info.NO_ANSWER:  # may be done anyway: lists read again
                    self.read(force=True)
                self.toast(not_done_text(reason, tr("RaceControl refused: %1"),
                                         tr("Not done: RaceControl did not answer.")), "warning")

        def confirmed(chosen_action: bool):
            if chosen_action:
                self.jobs.run("leave race", lambda: info.unregister(entry_type, event_id), answered,
                              lambda error: answered((False, "")), key="leave race")

        message = tr("Leave <b>%1</b> starting %2? Your place is given back.").replace(
            "%1", html.escape(title)).replace("%2", html.escape(when))
        confirm(self.host_widget(), tr("Leave This Race"), message, tr("Leave Race"), confirmed, danger=True)

    # Details read on demand
    def set_detail(self, key: str, value: dict | None, extra: dict | None = None, reason: str = ""):
        """Detail read (None: not read, reason: why, see unread_text) with what it holds for (extra: start of a
        field, round of sessions)"""
        self._loading.discard(key)
        self._loading_list = sorted(self._loading)
        if value is not None:
            self._details[key] = {**value, **(extra or {})}
        else:
            self._details[key] = {"error": reason or unread_text(info.state().status), **(extra or {})}
        if not self.refresh_details(time.time()):
            self.detailsChanged.emit()

    def start_detail(self, key: str) -> bool:
        if key in self._loading:
            return False
        self._loading.add(key)
        self._loading_list = sorted(self._loading)
        self._details.pop(key, None)
        self._championship_raw.pop(key, None)
        self.detailsChanged.emit()
        return True

    def refresh_details(self, now: float) -> bool:
        """Details kept only while they hold: field of a start not begun (of the row's first start, for the card),
        sessions of the round shown (worded again: times to start move on). True if told to the page"""
        firsts = {key: row.get("startKey", "") for key, (row, _source) in self._sources.items()}
        rounds = {key: row.get("roundNumber", 0) for key, (row, source) in self._sources.items()
                  if isinstance(source, rs.Championship)}
        details: dict[str, dict] = {}
        for key, value in self._details.items():
            kind, _, race = key.partition(":")
            if kind == "field" and (firsts[race] != value.get("startKey") if race in firsts
                                    else value.get("start", 0.0) <= now):
                continue  # start over, or no longer the first start of the card
            if kind == "championship":
                if race in rounds and rounds[race] != value.get("round"):
                    self._championship_raw.pop(key, None)
                    continue  # sessions of another round: read again on demand
                raw = self._championship_raw.get(key)
                if raw is not None:
                    value = {**championship_detail_view(raw, now), "round": value.get("round")}
            details[key] = value
        if details == self._details:
            return False
        self._details = details
        self.detailsChanged.emit()
        return True

    @Slot(str)
    @Slot(str, float)
    def read_field(self, key: str, start: float = 0.0):
        """Field of a start of a race (counts by class & rank): its next start, or the one at start (timeline)"""
        found = self._sources.get(key)
        if found is None:
            return
        row, source = found
        chosen = self.menu_start(row, source, start)
        if chosen is None or not chosen["eventId"] or not self.start_detail(chosen["detail"]):
            return
        detail_key, event_id = chosen["detail"], chosen["eventId"]
        extra = {"startKey": chosen["key"], "start": chosen["time"]}
        self.jobs.run("race field", partial(read_with_reason, lambda: info.read_field(row["entryType"], event_id)),
                      lambda read: self.set_detail(detail_key, field_view(read[0]) if read[0] is not None else None,
                                                   extra, read[1]),
                      lambda error: self.set_detail(detail_key, None, extra), key=detail_key)

    def read_live_fields(self, now: float):
        """Field of the next start of each race of the tab shown starting within LIVE_FIELD_SECONDS read again every
        LIVE_FIELD_EVERY (shown on its card, live), one race after another in one job (RaceControl refuses
        bursts); last field kept while read again or not read"""
        if info.state().status != info.READ or self._tab > 1 or self.jobs.is_busy("live fields"):
            return
        rows = ([race for group in self._values["daily"] for race in group["races"]] if self._tab == 0
                else list(self._values["events"]))
        clock = time.monotonic()
        asked = []
        for row in rows:
            found = self._sources.get(row.get("key", ""))
            if found is None or not isinstance(found[1], rs.Event) or not row.get("eventId"):
                continue
            if not 0 < row.get("startTime", 0.0) - now <= LIVE_FIELD_SECONDS:
                continue
            if self._field_misses.get(row["eventId"], 0) >= LIVE_FIELD_MISSES:
                continue  # entry list not given (RaceControl forbids it for some events): never asked again
            detail = f"field:{row['key']}"
            if detail in self._loading or clock - self._live_fields.get(detail, -LIVE_FIELD_EVERY) < LIVE_FIELD_EVERY:
                continue
            self._live_fields[detail] = clock
            asked.append((detail, found[1].entry_type, row["eventId"],
                          {"startKey": row["startKey"], "start": row["startTime"], "eventId": row["eventId"]}))
        self._live_fields = {key: when for key, when in self._live_fields.items()
                             if clock - when < LIVE_FIELD_SECONDS}
        if asked:
            self.jobs.run("live fields", partial(read_fields, asked),
                          lambda read: self.live_fields_read(read, tuple(item[0] for item in asked)),
                          self.live_field_failed, key="live fields")

    def live_fields_read(self, read: list[tuple[str, dict, rs.FieldLevel | None]], details: tuple[str, ...] = ()):
        """Fields read; starts left out (RaceControl limits: not asked, no miss counted) asked at a next tick"""
        done = {item[0] for item in read}
        for detail in details:
            if detail not in done:
                self._live_fields.pop(detail, None)
        for detail, extra, field in read:
            event_id = extra.get("eventId", "")
            self._field_misses[event_id] = 0 if field is not None else self._field_misses.get(event_id, 0) + 1
            self.live_field_read(detail, extra, field)

    def live_field_read(self, detail: str, extra: dict, field: rs.FieldLevel | None):
        if field is not None:  # not read this time: last one kept
            self.set_detail(detail, field_view(field), extra)

    @staticmethod
    def live_field_failed(_error: BaseException):
        """Live field not read: last one kept, read again at a next tick"""

    def read_practice(self, key: str):
        """Practice servers of a race, read once on demand (players & time left move on: read again from the menu)"""
        found = self._sources.get(key)
        detail_key = f"practice:{key}"
        if found is None or not isinstance(found[1], rs.Event) or not self.start_detail(detail_key):
            return
        event = found[1]
        self.jobs.run("practice servers", partial(read_with_reason, lambda: info.read_practice(event)),
                      lambda read: self.set_detail(detail_key, practice_view(read[0], time.time())
                                                   if read[0] is not None else None, None, read[1]),
                      lambda error: self.set_detail(detail_key, None), key=detail_key)

    def championship_read(self, key: str, number: int, detail: rs.ChampionshipDetail | None, reason: str = ""):
        if detail is not None:
            self._championship_raw[key] = detail
        self.set_detail(key, championship_detail_view(detail, time.time()) if detail is not None else None,
                        {"round": number}, reason)

    @Slot(str)
    def readChampionship(self, key: str):
        """Sessions of the current round with registrations, attempts & practice servers"""
        found = self._sources.get(key)
        if found is None or not found[0].get("id") or not self.start_detail(f"championship:{key}"):
            return
        row = found[0]
        detail_key, number = f"championship:{key}", row["roundNumber"]
        self.jobs.run("championship", partial(read_with_reason, lambda: info.read_championship(row["id"], number)),
                      lambda read: self.championship_read(detail_key, number, *read),
                      lambda error: self.set_detail(detail_key, None, {"round": number}), key=detail_key)

    @Slot(str)
    def readCoopBoard(self, key: str):
        """Best teams of a co-op event & your entry"""
        found = self._sources.get(key)
        if found is None or not self.start_detail(f"coop:{key}"):
            return
        row = found[0]
        detail_key = f"coop:{key}"
        name = player_name()
        self.jobs.run("co-op board", partial(read_with_reason, lambda: info.read_coop_board(row["name"], name)),
                      lambda read: self.set_detail(detail_key, coop_board_view(read[0]) if read[0] is not None
                                                   else None, None, read[1]),
                      lambda error: self.set_detail(detail_key, None), key=detail_key)

    # Weekly leaderboard of a race (every page, any class, friends, a driver)
    @Slot(str)
    def openBoard(self, key: str):
        """Weekly leaderboard of a race or of the current round of a championship, at the page of your place"""
        found = self._sources.get(key)
        if found is None:
            return
        row, source = found
        board = source.board if isinstance(source, rs.Event) else None
        if isinstance(source, rs.Championship):
            current = source.current_round(time.time())
            board = current.board if current is not None else None
        if board is None:
            return
        self._board_source = board
        rank, _count = self._places.get(board.key, (0, 0))
        title = row.get("title") or row.get("name", "")
        subtitle = " · ".join(part for part in (row.get("tierText", ""), row.get("track") or row.get("roundTrack", ""),
                                                row.get("round", "")) if part)
        self._board = {"open": True, "title": title, "subtitle": subtitle,
                       "classes": leaderboard_class_choices(row.get("classNames", [])), "vehicleClass": "",
                       "page": 1, "pages": 1, "count": "", "rows": [], "myPlace": "", "myPage": 0, "standing": "",
                       "friends": False, "found": "", "loading": True, "error": "", "key": key}
        self.boardChanged.emit()
        self.read_board(1 if not rank else (rank - 1) // info.LEADERBOARD_PAGE + 1, "", with_place=True)

    def cached_page(self, board: rs.Board, vehicle_class: str, page: int) -> rs.Leaderboard | None:
        """Page read less than BOARD_CACHE_SECONDS ago, None else"""
        found = self._board_cache.get((board.key, vehicle_class, page))
        return found[1] if found is not None and time.monotonic() - found[0] < BOARD_CACHE_SECONDS else None

    def read_board(self, page: int, vehicle_class: str, with_place: bool = False):
        board = self._board_source
        if board is None:
            return
        # your lap of another class never compared to the first of this one
        mine = {} if vehicle_class == self._board.get("vehicleClass", "") else {"mySeconds": 0.0}
        self._board = {**self._board, "loading": True, "error": "", "vehicleClass": vehicle_class, "friends": False,
                       **mine}
        self.boardChanged.emit()
        cached = self.cached_page(board, vehicle_class, page)
        if cached is not None and not with_place:
            self.jobs.cancel("leaderboard")  # page still read (asked before) never shown over this one
            self.board_read(board, vehicle_class, page, cached, None)
            return

        def work():
            found, reason = read_with_reason(lambda: cached or info.read_leaderboard(board, vehicle_class, page))
            return found, info.read_place(board, vehicle_class) if with_place else None, reason

        self.jobs.run("leaderboard", work, lambda result: self.board_read(board, vehicle_class, page, *result),
                      self.board_failed, key="leaderboard")

    def board_read(self, board: rs.Board, vehicle_class: str, page: int, found: rs.Leaderboard | None,
                   place: tuple[int, int] | None, reason: str = ""):
        if board is not self._board_source or not self._board.get("open"):
            return  # another leaderboard asked meanwhile
        if found is None:
            self.board_failed(None, reason)
            return
        self._board_cache[(board.key, vehicle_class, page)] = (time.monotonic(), found)
        pages = max((found.drivers + info.LEADERBOARD_PAGE - 1) // info.LEADERBOARD_PAGE, 1)
        me = info.player_id()
        update: dict[str, Any] = {
            "page": min(page, pages), "pages": pages, "loading": False,
            "count": counted(found.drivers, "driver ranked", "drivers ranked"),
            "rows": leaderboard_rows(found, me),
            "error": "" if found.drivers else tr("No leaderboard for this race this week"),
        }
        if place is not None:
            rank, count = place
            update["myPlace"] = place_text(rank, count or found.drivers) or tr("Not ranked this week")
            update["myPage"] = (rank - 1) // info.LEADERBOARD_PAGE + 1 if rank else 0
            update["myRank"] = rank
            update["myCount"] = count or found.drivers
        rank = update.get("myRank", self._board.get("myRank", 0))
        count = update.get("myCount", self._board.get("myCount", 0)) or found.drivers
        mine = next((entry.seconds for entry in found.entries if entry.player_id == me), 0.0)
        first_page = self.cached_page(board, vehicle_class, 1) or (found if page == 1 else None)
        update["standing"] = standing_text(rank, count, mine or self._board.get("mySeconds", 0.0), first_page)
        if mine:
            update["mySeconds"] = mine
        self._board = {**self._board, **update}
        self.boardChanged.emit()

    def board_failed(self, error: BaseException | None, reason: str = ""):
        if error is not None:
            logger.warning("RACE SCHEDULE: leaderboard not read: %s", error)
        self._board = {**self._board, "loading": False, "error": reason or unread_text(info.state().status)}
        self.boardChanged.emit()

    @Slot(int)
    def boardPage(self, page: int):
        if self._board.get("open") and 1 <= page <= self._board.get("pages", 1):
            self.read_board(page, self._board.get("vehicleClass", ""))

    @Slot(str)
    def boardClass(self, vehicle_class: str):
        """All classes ("") or one: first page, your place in it"""
        if self._board.get("open"):
            self.read_board(1, vehicle_class, with_place=True)

    @Slot()
    def boardMine(self):
        page = self._board.get("myPage", 0)
        if page:
            self.boardPage(page)

    @Slot(bool)
    def boardFriends(self, friends: bool):
        """You & your RaceControl friends ranked (one ask each), or back to the pages"""
        board = self._board_source
        if board is None or not self._board.get("open"):
            return
        if not friends:
            self.boardPage(self._board.get("page", 1))
            return
        vehicle_class = self._board.get("vehicleClass", "")
        self._board = {**self._board, "loading": True, "friends": True, "error": ""}
        self.boardChanged.emit()
        self.jobs.run("friends ranked", lambda: info.read_friend_places(board, vehicle_class),
                      lambda entries: self.friends_read(board, entries), self.board_failed, key="leaderboard")

    def friends_read(self, board: rs.Board, entries: list):
        if board is not self._board_source or not self._board.get("friends"):
            return
        rows = leaderboard_rows(rs.Leaderboard(len(entries), tuple(entries)), info.player_id())
        for row in rows:
            row["gap"] = ""  # gaps of the friends shown, not of a page
        self._board = {**self._board, "loading": False, "rows": rows,
                       "error": "" if rows else tr("None of your friends ranked this week")}
        self.boardChanged.emit()

    @Slot(str)
    def boardFind(self, name: str):
        """Page of a driver (by name) in the leaderboard shown"""
        board = self._board_source
        name = name.strip()
        if board is None or not name or not self._board.get("open"):
            return
        vehicle_class = self._board.get("vehicleClass", "")
        self._board = {**self._board, "loading": True, "found": ""}
        self.boardChanged.emit()
        self.jobs.run("find driver", lambda: info.find_driver(board, vehicle_class, name),
                      lambda rank: self.driver_found(board, name, rank), self.board_failed, key="leaderboard")

    def driver_found(self, board: rs.Board, name: str, rank: int):
        if board is not self._board_source:
            return
        if not rank:
            self._board = {**self._board, "loading": False, "found": tr("%1 not ranked here").replace("%1", name)}
            self.boardChanged.emit()
            return
        self._board = {**self._board, "found": place_text(rank, 0)}
        self.read_board((rank - 1) // info.LEADERBOARD_PAGE + 1, self._board.get("vehicleClass", ""))

    @Slot()
    def boardExport(self):
        """Page shown (or friends) as a CSV file"""
        rows = self._board.get("rows") or []
        if not rows:
            return
        from PySide6.QtWidgets import QFileDialog

        from ...formatter import strip_invalid_char

        name = strip_invalid_char(f"{self._board.get('title', 'leaderboard')} {self._board.get('page', 1)}")
        path, _ = QFileDialog.getSaveFileName(self.host_window(), tr("Export Leaderboard"), f"{name}.csv",
                                              tr("CSV (*.csv)"))
        if not path:
            return
        header = ["Rank", "Driver", "Lap", "Gap", "Sectors", "Car", "Class", "Tyres", "DR / SR", "Team"]
        table = [[row["rank"], row["name"], row["lap"], row["gap"], row["sectors"], row["car"], row["className"],
                  row["compound"], row["ranks"], row["team"]] for row in rows]
        try:
            with open(path, "w", encoding="utf-8", newline="") as file:
                file.write(csv_text(header, table))
        except OSError as error:
            logger.warning("RACE SCHEDULE: leaderboard not exported: %s", error)

    @Slot()
    def closeBoard(self):
        self._board = {"open": False}
        self._board_source = None
        self.boardChanged.emit()

    # Driver profile (leaderboard & classification rows)
    @Property(dict, notify=profileChanged)
    def profile(self) -> dict:
        """Profile shown: open, loading, name, nationality, dr, sr, badge, error"""
        return self._profile

    @Slot(str)
    def showProfile(self, name: str):
        if not name:
            return
        self._profile = {"open": True, "loading": True, "name": name}
        self.profileChanged.emit()
        self.jobs.run("driver profile", lambda: info.read_profile(name),
                      lambda found: self.profile_read(name, found), lambda error: self.profile_read(name, None),
                      key="profile")

    def profile_read(self, name: str, found):
        if not self._profile.get("open"):
            return  # closed while read
        if self._profile.get("name") != name:
            if found is None or found.name.split("#", 1)[0] != name.split("#", 1)[0]:
                return
        self._profile = {"open": True, "loading": False, **profile_view(found)}
        if "name" not in self._profile:
            self._profile["name"] = name
        self.profileChanged.emit()

    @Slot()
    def closeProfile(self):
        self.jobs.cancel("profile")
        self._profile = {"open": False}
        self.profileChanged.emit()

    # Your progress in a championship
    @Slot(str)
    def readProgress(self, key: str):
        found = self._sources.get(key)
        if found is None or not isinstance(found[1], rs.Championship) or not self.start_detail(f"progress:{key}"):
            return
        item = found[1]
        detail_key = f"progress:{key}"
        self.jobs.run("championship progress", partial(read_with_reason,
                                                       lambda: info.read_championship_results(item.name)),
                      lambda read: self.set_detail(detail_key, championship_progress(
                          read[0], len(item.rounds), info.player_name()) if read[0] is not None else None,
                          None, read[1]),
                      lambda error: self.set_detail(detail_key, None), key=detail_key)

    # Calendar
    def calendar_events(self, key: str, start: float = 0.0) -> list[dict]:
        """Calendar events of a race (its next start, or the one at start: timeline) or a championship (every round
        to come)"""
        found = self._sources.get(key)
        if found is None:
            return []
        row, source = found
        if isinstance(source, rs.Event):
            chosen = self.menu_start(row, source, start)
            if chosen is None:
                return []
            description = " · ".join(part for part in (row["tierText"], row["sessions"], row["requirement"]) if part)
            return [ics_event(chosen["key"], row["title"], chosen["time"], chosen["end"], row["track"], description)]
        if isinstance(source, rs.Championship):
            now = time.time()
            schedule = info.state().schedule
            return [ics_event(f"{row['key']}#{entry.number}",
                              f"{row['name']} · {tr('Round %1').replace('%1', str(entry.number))}",
                              entry.starts, entry.ends, track_of(entry.scene, entry.track, schedule)[0],
                              row["requirement"])
                    for entry in source.rounds if entry.ends > now and entry.starts > 0]
        return []

    def export_calendar(self, key: str, start: float = 0.0):
        events = self.calendar_events(key, start)
        if not events:
            return
        from PySide6.QtWidgets import QFileDialog

        from ...formatter import strip_invalid_char

        name = strip_invalid_char(events[0]["title"]) or "race"
        path, _ = QFileDialog.getSaveFileName(self.host_window(), tr("Export to Calendar"), f"{name}.ics",
                                              tr("Calendar (*.ics)"))
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="") as file:
                file.write(rs.ics_text(events, time.time()))
        except OSError as error:
            logger.warning("RACE SCHEDULE: calendar not exported: %s", error)
