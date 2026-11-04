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
Upcoming Races page backend (qml/analysis/RaceSchedule.qml): daily online races of Le Mans Ultimate to come

Daily races by tier from the public page of RaceControl (race_schedule_info: no sign in, no game ticket), as cards,
a compact list or a timeline of the next hours; search, owned tracks only. Each race tells your personal best &
community level of each class on its track (Driver Stats files). A race opens a menu: register in the game (its
window brought to the front), driver stats, recorded laps, race calculator, reminder before the start, calendar
export.

Read in background while the page shows, again when due (race_schedule_info.READ_SECONDS); times to start told
again every TICK_MS (FAST_TICK_MS while a start is close). Each list is one property, told to the page only when
changed.
"""

from __future__ import annotations

import logging
import time
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
from .schedule_personal import EMPTY as NO_PERSONAL
from .schedule_personal import PersonalData, personal_row, read_personal
from .schedule_reminders import reminder_choices, reminders
from .schedule_view import (
    SOON_SECONDS,
    event_row,
    frequency_text,
    ics_event,
    start_text,
    tier_text,
    timeline,
)

logger = logging.getLogger(__name__)

SETTINGS_FILE = "race_schedule.json"
ROW_ROLES = ("modelData",)  # page lists: one role holding the row (delegates keep `modelData`)
TICK_MS = 30000  # times to start told again (read again once due, see race_schedule_info.READ_SECONDS)
FAST_TICK_MS = 5000  # while a start is close (SOON_SECONDS): countdown & pulse follow
PERSONAL_SECONDS = policy.PAGE_PERSONAL_SECONDS
TIMELINE_HOURS = (3, 6, 12)
VIEWS = ("cards", "list", "timeline")
TABS = ("daily", "hosted", "community")  # daily races, hosted races, community events (public pages of RaceControl)
NO_SAFETY = ("", 0)  # races of the public page tell no Safety Rank needed: every race open


def status_note(status: str, schedule: rs.Schedule) -> tuple[str, str]:
    """Level ("", info, warning) & text telling why the races shown may be old or missing"""
    if status == info.OFF:
        return "warning", tr("Reading the daily races from the public RaceControl site is off.")
    if status == info.FAILED:
        return "warning", tr("The public RaceControl site did not answer: last races read are shown.") if (
            schedule.read_time > 0) else tr("The public RaceControl site did not answer.")
    if status == info.PUBLIC:
        return "info", tr("Daily races of the public RaceControl site, read without signing in. Register in the game.")
    return "", ""


def public_row(event: rs.PublicEvent, now: float) -> dict:
    """What a card of a hosted race or community event shows: title, organizer, when (next start, "every week"),
    track, classes, sessions, places taken, rounds, its page"""
    when = start_text(event.start, now) if event.start > 0 else ""
    if event.weekly and when:
        when = tr("%1 · every week").replace("%1", when)
    places = f"{event.registered}/{event.capacity}" if event.registered >= 0 and event.capacity > 0 else ""
    details = [part for part in (event.drivers, event.rounds) if part]
    row = {"key": event.url or event.title, "title": event.title, "organizer": event.organizer, "when": when,
           "startTime": event.start, "track": event.track, "classes": event.classes,
           "sessions": "  ·  ".join(event.sessions), "places": places, "full": bool(places) and
           event.registered >= event.capacity, "details": "  ·  ".join(details), "url": event.url}
    row["search"] = " ".join((event.title, event.organizer, event.track, event.classes)).casefold()
    return row


def requests_status(status: int) -> str:
    """Answer of a request told by the requests dialog: status, "no answer" or "not sent" (limits)"""
    if status == -1:
        return tr("not sent (limits)")
    return str(status) if status > 0 else tr("no answer")


def _int_setting(saved: dict, name: str, count: int, default: int = 0) -> int:
    value = saved.get(name)
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < count else default


class RaceScheduleBackend(PageBackend):
    """Upcoming Races page state & actions"""

    statusChanged = Signal()
    listsChanged = Signal()
    settingsChanged = Signal()
    timelineChanged = Signal()
    filtersCleared = Signal()  # search field emptied by the page
    expandedChanged = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent, "Upcoming Races")
        self.logos = LogoCache()
        self.page_file = page_settings.PageSettings(SETTINGS_FILE, page_settings.SAVE_DELAY_MS, self,
                                                    self.page_settings)
        saved = self.page_file.load()
        self._view = _int_setting(saved, "view", len(VIEWS))
        self._tab = _int_setting(saved, "tab", len(TABS))
        self._owned_only = saved.get("owned_only") is True
        self._search = ""
        self._values: dict[str, Any] = {"status": {}, "daily": [], "count": 0, "timeline": {}, "hosted": [],
                                        "community": [], "counts": [0, 0, 0]}
        # Lists as the page shows them: rows updated in place by key (cards kept, a click or an open menu never lost
        # to a list made again at each tick)
        self._models = {name: self.row_model() for name in ("daily", "timeline")}
        self._race_models = {tier: self.row_model() for tier in rs.DAILY_TIERS}
        self._expanded: list[str] = []  # races with every following start shown
        self._sources: dict[str, tuple[dict, rs.Event]] = {}  # row key -> (row, race)
        self._personal: PersonalData = NO_PERSONAL
        self._personal_time = -PERSONAL_SECONDS
        self._reading = False
        hours = saved.get("timeline_hours")
        self._timeline_hours = hours if hours in TIMELINE_HOURS else 6
        self._timer = self.page_timer(self.tick, TICK_MS)
        notifier().changed.connect(self.pictures_changed)  # track logos fetched from game meanwhile
        reminders().changed.connect(self.reminders_changed)

    # Publishing
    def publish(self, name: str, value: Any, signal: Any):
        if self._values.get(name) != value:
            self._values[name] = value
            signal.emit()

    @Property(dict, notify=statusChanged)
    def status(self) -> dict:
        """Read state: loading, level & note, read, updated, age, option off"""
        return self._values["status"]

    @Property(list, notify=listsChanged)
    def daily(self) -> list:
        """Daily races by tier: tier, tierText, frequency, races (see schedule_view.event_row)"""
        return self._values["daily"]

    @Property(int, notify=listsChanged)
    def count(self) -> int:
        """Races shown"""
        return self._values["count"]

    @Property(list, notify=listsChanged)
    def hosted(self) -> list:
        """Hosted races to come (see public_row)"""
        return self._values["hosted"]

    @Property(list, notify=listsChanged)
    def community(self) -> list:
        """Community events to come (see public_row)"""
        return self._values["community"]

    @Property(list, notify=listsChanged)
    def counts(self) -> list:
        """Rows of each tab (TABS) as filtered"""
        return self._values["counts"]

    @Property(int, notify=settingsChanged)
    def tab(self) -> int:
        """Tab shown: daily races (0), hosted races (1), community events (2)"""
        return self._tab

    @Slot(int)
    def setTab(self, index: int):
        if 0 <= index < len(TABS) and index != self._tab:
            self._tab = index
            self.settingsChanged.emit()
            self.page_file.save()

    @Slot(str)
    def openEvent(self, url: str):
        """Page of a hosted race or community event on the RaceControl site, in the web browser (register there)"""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        from ...process.public_schedule import SITE

        if url.startswith(SITE + "/"):
            QDesktopServices.openUrl(QUrl(url))

    def row_model(self) -> DictListModel:
        from PySide6.QtQml import QQmlEngine

        model = DictListModel(ROW_ROLES, self)
        QQmlEngine.setObjectOwnership(model, QQmlEngine.ObjectOwnership.CppOwnership)  # also given by raceModel
        return model

    @staticmethod
    def sync_rows(model: DictListModel, rows: list[dict]):
        model.sync([{"key": row["key"], "modelData": row} for row in rows])

    dailyModel = Property(QObject, lambda self: self._models["daily"], constant=True)  # tier groups (no races)
    timelineModel = Property(QObject, lambda self: self._models["timeline"], constant=True)  # lanes

    @Slot(str, result=QObject)
    def raceModel(self, tier: str) -> QObject | None:
        """Daily races of a tier, as the page shows them"""
        return self._race_models.get(tier)

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

    @Property(int, notify=timelineChanged)
    def timelineHours(self) -> int:
        return self._timeline_hours

    @Property(int, notify=settingsChanged)
    def view(self) -> int:
        """Races shown as cards (0), a compact list (1) or a timeline (2)"""
        return self._view

    @Property(bool, notify=settingsChanged)
    def ownedOnly(self) -> bool:
        return self._owned_only

    @Property(str, notify=settingsChanged)
    def search(self) -> str:
        return self._search

    # Page state
    def page_shown(self):
        self._timer.start()
        self.publish_all()  # last read at once
        self.read()
        self.read_personal_due()

    def page_hidden(self):
        self._timer.stop()

    def release_resources(self):
        import contextlib

        self._timer.stop()
        self.page_file.flush()
        with contextlib.suppress(RuntimeError, TypeError):  # never connected or already gone
            reminders().changed.disconnect(self.reminders_changed)

    def page_settings(self) -> dict:
        return {"view": self._view, "tab": self._tab, "owned_only": self._owned_only,
                "timeline_hours": self._timeline_hours}

    def tick(self):
        if not self.page_visible:
            return
        if info.due():
            self.read()
        self.read_personal_due()
        self.publish_all()

    # Reading
    def read(self, force: bool = False):
        if self._reading:
            return
        self._reading = True
        self.publish_status()
        self.jobs.run("race schedule", lambda: info.read(force), self.read_done, self.read_failed, key="schedule")

    def read_done(self, _state: info.State):
        self._reading = False
        self.publish_all()

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

    def personal_read(self, data: PersonalData):
        self._personal = data
        self.publish_all()

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
        state = info.state()
        schedule = state.schedule
        level, note = status_note(state.status, schedule)
        self.publish("status", {
            "loading": self._reading,
            "level": level,
            "note": note,
            "off": state.status == info.OFF,
            "read": schedule.read_time > 0,
            "updated": date_text(schedule.read_time) if schedule.read_time > 0 else "",
            "age": relative_date(schedule.read_time) if schedule.read_time > 0 else "",  # "5 min ago": always told
            "readFull": long_date_time(schedule.read_time) if schedule.read_time > 0 else "",
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

    def shown(self, row: dict | None) -> TypeGuard[dict]:
        """Row kept by the filters: owned only, search"""
        if row is None:
            return False
        if self._owned_only and row.get("carsOwned") is False:
            return False
        return not (self._search and self._search not in row.get("search", ""))

    def with_extras(self, row: dict, source: rs.Event, track: str, scene: str) -> dict:
        """Row with your laps on its track & its reminder"""
        self._sources[row["key"]] = (row, source)
        row["personal"] = self.personal(track, scene)
        start_key = row.get("startKey", "")
        row["reminder"] = reminders().minutes_of(start_key) if start_key else 0
        return row

    def publish_all(self):
        """Every list made again from the last read (times to start move on)"""
        self.publish_status()
        schedule, now = info.state().schedule, time.time()

        def logo(track: str) -> str:
            return self.logos.track(track) if track else ""

        self._sources = {}
        daily: list[dict[str, Any]] = []
        for tier in rs.DAILY_TIERS:
            rows = [self.with_extras(row, event, row["track"], event.scene) for event in schedule.events
                    if event.kind == "daily" and event.tier == tier
                    if self.shown(row := event_row(event, schedule, NO_SAFETY, now, logo))]
            if rows:
                rows.sort(key=lambda row: row["startTime"])
                daily.append({"tier": tier, "tierText": tier_text(tier), "races": rows,
                              "frequency": frequency_text(schedule.frequency.get(tier, 0.0))})
        line = timeline(((group["tier"], group["races"]) for group in daily), schedule, now, self._timeline_hours)
        self.sync_rows(self._models["timeline"], line["lanes"])
        self.publish("timeline", line, self.timelineChanged)
        count = sum(len(group["races"]) for group in daily)
        hosted = [row for row in (public_row(event, now) for event in schedule.hosted) if self.shown(row)]
        community = [row for row in (public_row(event, now) for event in schedule.community) if self.shown(row)]
        counts = [count, len(hosted), len(community)]
        if self._values["hosted"] != hosted or self._values["community"] != community or self._values["counts"] != counts:
            self._values.update(hosted=hosted, community=community, counts=counts)
            if self._values["daily"] == daily and self._values["count"] == count:
                self.listsChanged.emit()
        if self._values["daily"] != daily or self._values["count"] != count:
            self._values["daily"], self._values["count"] = daily, count
            groups = {group["tier"]: group for group in daily}
            for tier, model in self._race_models.items():
                self.sync_rows(model, groups[tier]["races"] if tier in groups else [])
            self._models["daily"].sync([{"key": group["tier"], "modelData": {
                "tier": group["tier"], "tierText": group["tierText"], "frequency": group["frequency"],
                "count": len(group["races"])}} for group in daily])
            self.listsChanged.emit()
        soon = any(0 < race["startTime"] - now <= SOON_SECONDS for group in daily for race in group["races"])
        self._timer.setInterval(FAST_TICK_MS if soon else TICK_MS)

    # Settings
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

    @Slot(bool)
    def setOwnedOnly(self, value: bool):
        if value != self._owned_only:
            self._owned_only = value
            self.settingsChanged.emit()
            self.page_file.save()
            self.publish_all()

    @Slot()
    def clearFilters(self):
        self._search, self._owned_only = "", False
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
        """Public page read again (at most every race_schedule_info.FORCE_SECONDS), driver stats too"""
        self._personal_time = -PERSONAL_SECONDS
        self.read(force=True)
        self.read_personal_due()

    @Slot(result="QVariantList")
    def requestsReport(self) -> list:
        """Requests sent to online services since the app started (request_log): by service, how many in the last
        hour (against its limit), the last ones (time, route, answer)"""
        from ... import request_log

        limits = {request_log.GITHUB: 60}
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
        """Settings page on the public race schedule option"""
        from ..app_settings import open_app_settings

        open_app_settings(self.parent(), "application", "enable_public_race_schedule")

    # Menu of a race
    @staticmethod
    def menu_start(row: dict, source: rs.Event, start: float = 0.0) -> dict | None:
        """Start a menu acts on: the row's first (card, list) or the one at start (timeline block): reminder key,
        time, end; None once that start is gone"""
        first = row.get("startTime", 0.0)
        if not start or abs(start - first) < 1:
            return {"key": row.get("startKey", ""), "time": first, "end": row.get("endTime", first)}
        found = next((item for item in source.starts if abs(item.time - start) < 1), None)
        if found is None:
            return None
        return {"key": f"{row['key']}@{int(found.time)}", "time": found.time,
                "end": found.time + row.get("endTime", first) - first}

    @Slot(str, result=list)
    @Slot(str, float, result=list)
    def raceActions(self, key: str, start: float = 0.0) -> list:
        """Entries of the menu of a race: id, text, enabled, vehicle, section (separator between two sections: race,
        plan, mine), menu (title of the submenu it is in, "": the menu itself; checked: reminder entries).
        start: start of a timeline block (0: the row's first)"""
        found = self._sources.get(key)
        if found is None:
            return []
        row, source = found
        chosen = self.menu_start(row, source, start)
        now = time.time()
        upcoming = chosen is not None and chosen["time"] > now
        entries = []

        def add(section: str, entry: dict, menu: str = ""):
            entries.append({"enabled": True, "vehicle": "", **entry, "section": section, "menu": menu})

        # The race: registered in the game (its window brought to the front, or the game started)
        if upcoming and chosen is not None:
            add("race", {"id": "game", "text": tr("Register in the Game")})
            when = start_text(chosen["time"], now)
            # Planning: reminder minutes in one submenu (start time in its title, not repeated on each entry)
            current = reminders().minutes_of(chosen["key"]) if chosen["key"] else 0
            remind = tr("Remind Me Before %1").replace("%1", when)
            for minutes in reminder_choices():
                add("plan", {"id": f"remind:{minutes}", "text": tr("%1 min").replace("%1", str(minutes)),
                             "checked": current == minutes}, remind)
            if current:
                add("plan", {"id": "remind:0", "text": tr("Cancel Reminder")}, remind)
        if chosen is not None:
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
            add("mine", {"id": "prepare", "text": tr("Prepare Race in Calculator"), "enabled": bool(row.get("track"))})
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
        track = personal.get("statsTrack") or row.get("track", "")
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
        elif action == "game":
            self.show_game()
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

    # Game (registration & joining stay in the game: car, livery & settings set by its menu)
    def host_widget(self):
        from PySide6.QtWidgets import QWidget

        widget = self.parent()
        return widget if isinstance(widget, QWidget) else None

    def toast(self, text: str, level: str = "success"):
        from .dialogs import page_toast

        page_toast(self.host_widget(), text, level)

    @Slot()
    def startGame(self):
        """Le Mans Ultimate started by Steam"""
        from .replays_common import start_game

        if start_game():
            self.toast(tr("Le Mans Ultimate is starting: register in its Online menu."), "info")
        else:
            self.toast(tr("Steam could not be opened: start Le Mans Ultimate yourself"), "warning")

    def show_game(self):
        """Window of Le Mans Ultimate brought to the front (its menu registers), the game started when closed"""
        from .game_window import show_game_window

        if show_game_window():
            self.toast(tr("Le Mans Ultimate is in front: register in its Online menu."), "info")
        else:
            self.startGame()

    def calendar_events(self, key: str, start: float = 0.0) -> list[dict]:
        found = self._sources.get(key)
        if found is None:
            return []
        row, source = found
        chosen = self.menu_start(row, source, start)
        if chosen is None:
            return []
        description = " · ".join(part for part in (row["tierText"], row["sessions"]) if part)
        return [ics_event(chosen["key"], row["title"], chosen["time"], chosen["end"], row["track"], description)]

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
