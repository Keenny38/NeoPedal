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
Online races you drove (Results & Replays page, "Online" list: qml/analysis/OnlineResults.qml)

Read from the results files of the game (race_schedule_info.read_results: sessions of online servers), newest
first, a page at a time (More Results). Race picked: its whole classification, your place, positions & lap times lap
by lap (you, the winner, the cars around you) & a summary of the races read. Nothing is asked online. Read only while
the list shows (the page tells list_shown).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from ... import race_schedule_info as info
from ...i18n import tr
from ...process import race_schedule as rs
from . import page_settings
from .game_pictures import LogoCache
from .page_backend import PageBackend
from .schedule_view import counted, csv_text, is_player, result_view, track_of

logger = logging.getLogger(__name__)

SETTINGS_FILE = "online_results.json"
KINDS = ("daily",)  # the results files do not tell the kind of event: every race listed with the daily ones
CHART_CARS = 3  # cars around you drawn on the lap chart (each side)
LOCAL_MARGIN = 3 * 3600.0  # results file of an online race: race session started at most this late after the event
LOCAL_EARLY = 600.0  # or this early before (clocks): the online event starts with its practice


def rank_level(rank: tuple[str, int]) -> float:
    """Height of a rank on the rank chart (Bronze 1 = 1 ... Platinum 3 = 12), -1 if unknown"""
    number = rs.rank_number(*rank)
    return -1.0 if number < 0 or not rank[0] else (number // 10) * 3 + max(rank[1], 1)


def local_session(result: rs.OnlineResult, sessions, track: str) -> str:
    """Results file of an online race on this computer: race session of results_index.SessionInfo on its track
    (layout name as shown, see process.track_names) started from LOCAL_EARLY before the event start to LOCAL_MARGIN
    after, the closest to it; "" if none"""
    from ...process.results_file import layout_of
    from ...userfile.game_images import images

    key = track.casefold()
    best, found = LOCAL_MARGIN + 1.0, ""
    for info_ in sessions:
        if "race" not in str(info_.kind).casefold() or info_.time <= 0:
            continue
        gap = info_.time - result.time
        if not -LOCAL_EARLY <= gap <= LOCAL_MARGIN or abs(gap) >= best:
            continue
        if key and images.track_name(layout_of(info_), info_.track).casefold() == key:
            best, found = abs(gap), info_.path
    return found


def read_page(kind: str, page: int) -> tuple[list[rs.OnlineResult] | None, str]:
    """Page of your online races (results files) & why not read ("" if read), blocking (worker thread)"""
    return info.read_results(kind, page), ""


def not_read_text(_status: str) -> str:
    """Why your online races were not read"""
    return tr("Results files of the game not read: try again in a moment.")


def own_result(result: rs.OnlineResult, player: str) -> rs.OnlineResult:
    """Race with your own Driver & Safety Rank changes & ranks on your row in team races (rows are cars, named by
    car or team: no change given on them)"""
    own = next((driver for driver in result.players if is_player(driver.name, player)), None)
    if own is None:
        return result
    for index, row in enumerate(result.rows):
        if not is_player(row.name, player) and any(is_player(name, player) for name in row.drivers):
            mine = row._replace(dr_change=own.dr_change, sr_change=own.sr_change, reasons=own.reasons,
                                driver_rank=own.driver_rank, safety_rank=own.safety_rank)
            return result._replace(rows=(*result.rows[:index], mine, *result.rows[index + 1:]))
    return result


def rank_lines(results: list[rs.OnlineResult], player: str) -> dict:
    """Your Driver & Safety Rank race after race (oldest first) as TpRankLine points ({x, y} 0-1, Bronze 1 at the
    bottom) & the last ranks, {} with fewer than 2 races"""
    from .schedule_view import rank_text

    ranks = []
    for result in (own_result(race, player) for race in reversed(results)):  # oldest first
        mine = next((row for row in result.rows
                     if any(is_player(name, player) for name in (row.name, *row.drivers))), None)
        if mine is not None and mine.driver_rank[0]:
            ranks.append((mine.driver_rank, mine.safety_rank))
    if len(ranks) < 2:
        return {}

    def points(index: int) -> list[dict]:
        levels = [(number, rank_level(rank[index])) for number, rank in enumerate(ranks)]
        return [{"x": number / (len(ranks) - 1), "y": (level - 1) / 11} for number, level in levels if level >= 1]

    return {"dr": points(0), "sr": points(1), "drText": rank_text(ranks[-1][0]), "srText": rank_text(ranks[-1][1]),
            "races": counted(len(ranks), "race", "races")}


def summary_of(results: list[rs.OnlineResult], player: str) -> dict:
    """Races read: count, wins, podiums, average finish (place in your class in multi-class races), clean races
    (Safety Rank kept) & Driver Rank change when the races tell rank changes (the results files do not)"""
    places, clean, changes, ranked = [], 0, 0.0, False
    for result in (own_result(race, player) for race in results):
        mine = next((row for row in result.rows if any(is_player(name, player) for name in (row.name, *row.drivers))),
                    None)
        if mine is None:
            continue
        multi_class = len({row.vehicle_class for row in result.rows if row.vehicle_class}) > 1
        place = (mine.class_position or mine.position) if multi_class else mine.position
        if place:  # races without your place left out of every figure but the Driver Rank change
            places.append(place)
            clean += mine.sr_change is not None and mine.sr_change >= 0
        changes += mine.dr_change or 0.0
        ranked = ranked or mine.dr_change is not None or mine.sr_change is not None
    if not places:
        return {}
    return {
        "races": counted(len(places), "race", "races"),
        "figures": [
            {"label": tr("Wins"), "value": str(sum(place == 1 for place in places))},
            {"label": tr("Podiums"), "value": str(sum(place <= 3 for place in places))},
            {"label": tr("Avg. Finish"), "value": f"P{sum(places) / len(places):.1f}"},
            *([{"label": tr("Clean Races"), "value": f"{clean}/{len(places)}"},
               {"label": "DR", "value": f"{changes:+g}"}] if ranked else []),
        ],
    }


def lap_chart(result: rs.OnlineResult, player: str) -> dict:
    """Lap by lap: positions & lap times of you, the winner & the cars around you (lines), axis limits"""
    rows = [row for row in result.rows if row.lap_positions]
    mine = next((row for row in rows if any(is_player(name, player) for name in (row.name, *row.drivers))), None)
    shown = rows[:1]
    if mine is not None:
        index = rows.index(mine)
        shown += rows[max(index - CHART_CARS, 0):index + CHART_CARS + 1]
    shown = list(dict.fromkeys(shown))
    lines = []
    laps = cars = 0
    every_time: list[float] = []
    for row in shown:
        valid = sorted(lap for lap in row.lap_times if lap > 0)
        median = valid[len(valid) // 2] if valid else 0.0
        # lap times off the pace (pit, first lap) cut to keep the scale readable
        times = [min(lap, median * 1.15) if lap > 0 and median else 0.0 for lap in row.lap_times]
        lines.append({"name": row.name, "me": row is mine, "winner": bool(rows) and row is rows[0],
                      "positions": list(row.lap_positions), "times": times})
        laps = max(laps, len(row.lap_positions))
        cars = max(cars, max(row.lap_positions, default=0))
        every_time += [lap for lap in times if lap > 0]
    return {"lines": lines, "laps": laps, "cars": cars, "fastest": min(every_time, default=0.0),
            "slowest": max(every_time, default=0.0)}


class OnlineResultsBackend(PageBackend):
    """Online results list & race picked (context property "online" of the Results & Replays page)"""

    listChanged = Signal()
    selectionChanged = Signal()
    stateChanged = Signal()
    sessionWanted = Signal(str)  # results file to show (page: sessions list)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent, "Online Results")
        self.logos = LogoCache()
        self.page_file = page_settings.PageSettings(SETTINGS_FILE, page_settings.SAVE_DELAY_MS, self,
                                                    lambda: {"kind": self._kind})
        kind = self.page_file.load().get("kind")
        self._kind = kind if isinstance(kind, int) and not isinstance(kind, bool) and 0 <= kind < len(KINDS) else 0
        self._results: dict[str, list[rs.OnlineResult]] = {name: [] for name in KINDS}
        self._page: dict[str, int] = {name: 0 for name in KINDS}
        self._end: dict[str, bool] = {name: False for name in KINDS}
        self._loading = False
        self._error = ""
        self._selected = ""  # key of the race picked
        self._shown = False
        # Sessions of the results files read by the page (set by the page)
        self.sessions: Callable[[], list] = list
        self._note = ""  # told under the race picked ("no results file...")
        self._laps_asked: set[str] = set()  # races whose laps were asked
        self._laps_reading = ""  # race whose laps are read (job "laps": a newer one drops its answer)
        self._values: dict[str, Any] = {"rows": [], "selected": {}, "chart": {}, "ranks": {}, "summary": {}}

    # Properties
    @Property(list, notify=listChanged)
    def rows(self) -> list:
        """Races of the kind shown (see schedule_view.result_view, classification left out of the list)"""
        return self._values["rows"]

    @Property(dict, notify=listChanged)
    def summary(self) -> dict:
        """Races read of the kind shown: count & figures (wins, podiums, average finish, clean races, DR)"""
        return self._values["summary"]

    @Property(dict, notify=listChanged)
    def ranks(self) -> dict:
        """Your Driver & Safety Rank after each race read (oldest first): points (dr, sr levels), labels"""
        return self._values["ranks"]

    @Property(dict, notify=selectionChanged)
    def selected(self) -> dict:
        """Race picked (see schedule_view.result_view), {} if none"""
        return self._values["selected"]

    @Property(dict, notify=selectionChanged)
    def chart(self) -> dict:
        """Lap by lap of the race picked (see lap_chart)"""
        return self._values["chart"]

    @Property(dict, notify=stateChanged)
    def state(self) -> dict:
        """kind, loading, error, more (pages left), selectedKey"""
        return {"kind": self._kind, "loading": self._loading, "error": self._error,
                "more": not self._end[KINDS[self._kind]], "selectedKey": self._selected, "note": self._note}

    # Page state
    def page_shown(self):
        pass

    def page_hidden(self):
        pass

    def release_resources(self):
        self.page_file.flush()

    @Slot(bool)
    def list_shown(self, shown: bool):
        """Online list shown on the page: first page read once, laps of the race picked read (list shown only)"""
        self._shown = shown
        if shown and not self._results[KINDS[self._kind]] and not self._end[KINDS[self._kind]]:
            self.more()
            return
        result = self.result_of(self._selected) if shown else None
        if result is not None and not any(row.lap_positions for row in result.rows):
            self.read_laps(result)

    # Reading
    @Slot(int)
    def setKind(self, index: int):
        if 0 <= index < len(KINDS) and index != self._kind:
            self._kind = index
            self._selected = ""
            self.page_file.save()
            self.publish()
            if not self._results[KINDS[index]]:
                self.more()

    @Slot()
    def more(self):
        """Next page of your online races of the kind shown"""
        kind = KINDS[self._kind]
        if self._loading or self._end[kind]:
            return
        page = self._page[kind] + 1
        self._loading, self._error = True, ""
        self.stateChanged.emit()
        self.jobs.run("online results", lambda: read_page(kind, page),
                      lambda found: self.read_done(kind, page, *found), lambda error: self.read_failed(kind, error),
                      key="results")

    @Slot()
    def readAgain(self):
        """Races read again from the first page (new races driven meanwhile)"""
        kind = KINDS[self._kind]
        self.jobs.cancel("results")  # page read meanwhile (More Results, other kind) dropped
        self._loading = False
        self._results[kind], self._page[kind], self._end[kind] = [], 0, False
        self._laps_asked.clear()  # races read again come without their laps
        self._note = ""
        self.publish()
        self.more()

    def read_done(self, kind: str, page: int, found: list | None, status: str = ""):
        self._loading = False
        shown = KINDS[self._kind]
        if found is None:
            if kind == shown:  # page of another kind failed: never told on the list shown
                self._error = not_read_text(status)
        else:
            known = {(result.event_id, result.split) for result in self._results[kind]}
            for result in found:  # once each (pages move while new races are added)
                if (result.event_id, result.split) not in known:
                    known.add((result.event_id, result.split))
                    self._results[kind].append(result)
            self._page[kind] = page
            # end of the list told by the races answered (a race may be unreadable)
            answered = found.answered if isinstance(found, info.ResultsPage) else len(found)
            self._end[kind] = answered < info.results_take(kind)
            if kind == shown and not self._selected and self._results[kind]:
                first = self._results[kind][0]
                self._selected = f"result/{first.event_id}/{first.split}"
        self.publish()
        if kind != shown and not self._results[shown] and not self._end[shown]:
            self.more()  # kind changed while this page was read (or failed)

    def read_failed(self, kind: str, error: BaseException):
        logger.warning("ONLINE RESULTS: not read: %s", error)
        self.read_done(kind, 0, None, "failed")

    # Publishing
    def view_of(self, result: rs.OnlineResult) -> dict:
        def logo(track: str) -> str:
            return self.logos.track(track) if track else ""

        player = info.player_name()
        return result_view(own_result(result, player), info.state().schedule, player, time.time(), logo)

    def publish(self):
        kind = KINDS[self._kind]
        results = self._results[kind]
        player = info.player_name()
        rows = []
        for result in results:
            shown = self.view_of(result)
            shown.pop("rows")
            rows.append(shown)
        self._values["ranks"] = rank_lines(results, player)
        self._values["rows"] = rows
        self._values["summary"] = summary_of(results, player)
        self.listChanged.emit()
        self.publish_selected()
        self.stateChanged.emit()

    def publish_selected(self):
        result = self.result_of(self._selected)
        if result is not None and not any(row.lap_positions for row in result.rows):
            self.read_laps(result)
        self._values["selected"] = self.view_of(result) if result is not None else {}
        self._values["chart"] = lap_chart(result, info.player_name()) if result is not None else {}
        self.selectionChanged.emit()

    def read_laps(self, result: rs.OnlineResult):
        """Laps of a race (one ask, whole race read again; list shown only), lap chart shown once read"""
        key = f"result/{result.event_id}/{result.split}"
        if not self._shown or key in self._laps_asked:
            return
        if self._laps_reading:  # its answer dropped below: asked again once picked again
            self._laps_asked.discard(self._laps_reading)
        self._laps_asked.add(key)
        self._laps_reading = key
        self.jobs.run("race laps", lambda: info.read_result(result.event_id, result.split),
                      lambda found: self.laps_read(result, found), lambda error: self.laps_failed(key, error),
                      key="laps")

    def laps_failed(self, key: str, error: BaseException):
        logger.warning("ONLINE RESULTS: laps not read: %s", error)
        self.laps_read_over(key, True)

    def laps_read_over(self, key: str, failed: bool):
        """Laps job of a race over: asked again when the race is picked again if not read"""
        if self._laps_reading == key:
            self._laps_reading = ""
        if failed:
            self._laps_asked.discard(key)

    def laps_read(self, old: rs.OnlineResult, found: rs.OnlineResult | None):
        self.laps_read_over(f"result/{old.event_id}/{old.split}", found is None)
        if found is None or not any(row.lap_positions for row in found.rows):
            return
        for results in self._results.values():
            for index, result in enumerate(results):
                if result is old:
                    results[index] = found._replace(time=old.time or found.time)
        if self._selected == f"result/{old.event_id}/{old.split}":
            self.publish_selected()

    def result_of(self, key: str) -> rs.OnlineResult | None:
        for result in self._results[KINDS[self._kind]]:
            if f"result/{result.event_id}/{result.split}" == key:
                return result
        return None

    # Actions
    @Slot(str)
    def select(self, key: str):
        if key != self._selected:
            self._selected, self._note = key, ""
            self.publish_selected()
            self.stateChanged.emit()

    @Slot()
    def openLocal(self):
        """Results file of the race picked shown in the sessions list (its replay & recorded laps from there)"""
        result = self.result_of(self._selected)
        if result is None:
            return
        path = local_session(result, self.sessions(), track_of(result.track, result.track, info.state().schedule)[0])
        if path:
            self.sessionWanted.emit(path)
            return
        self._note = tr("No results file of this race on this computer")
        self.stateChanged.emit()

    @Slot()
    def exportClassification(self):
        """Classification of the race picked as a CSV file (file dialog)"""
        result = self.result_of(self._selected)
        if result is None:
            return
        from PySide6.QtWidgets import QFileDialog

        from ...formatter import strip_invalid_char

        widget = self.parent()
        parent = widget.window() if widget is not None and hasattr(widget, "window") else None
        name = strip_invalid_char(f"{result.title} split {result.split}") or "race"
        path, _ = QFileDialog.getSaveFileName(parent, tr("Export Classification"), f"{name}.csv", tr("CSV (*.csv)"))
        if not path:
            return
        rows = [[str(row.position or ""), str(row.class_position or ""), row.vehicle_class, row.number, row.name,
                 row.team, row.car, f"{row.best_lap:.3f}" if row.best_lap else "", str(row.laps or ""), row.status,
                 "" if row.dr_change is None else f"{row.dr_change:+g}",
                 "" if row.sr_change is None else f"{row.sr_change:+g}"] for row in result.rows]
        header = ["Position", "Class Position", "Class", "Number", "Driver", "Team", "Car", "Best Lap", "Laps",
                  "Status", "DR", "SR"]
        try:
            with open(path, "w", encoding="utf-8", newline="") as file:
                file.write(csv_text(header, rows))
        except OSError as error:
            logger.warning("ONLINE RESULTS: classification not exported: %s", error)
