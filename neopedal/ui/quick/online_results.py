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
the list shows (the page tells list_shown). Each race is a results file: Open Local Session shows it in the
sessions list.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from ... import race_schedule_info as info
from ...i18n import tr
from ...process import race_schedule as rs
from .game_pictures import LogoCache
from .page_backend import PageBackend
from .schedule_view import counted, csv_text, is_player, result_view

logger = logging.getLogger(__name__)

CHART_CARS = 3  # cars around you drawn on the lap chart (each side)


def result_key(result: rs.OnlineResult) -> str:
    """Key of a race on the page (see schedule_view.result_view)"""
    return f"result/{result.path}"


def summary_of(results: list[rs.OnlineResult], player: str) -> dict:
    """Races read: count, wins, podiums, average finish (place in your class in multi-class races)"""
    places = []
    for result in results:
        mine = next((row for row in result.rows if any(is_player(name, player) for name in (row.name, *row.drivers))),
                    None)
        if mine is None:
            continue
        multi_class = len({row.vehicle_class for row in result.rows if row.vehicle_class}) > 1
        place = (mine.class_position or mine.position) if multi_class else mine.position
        if place:  # races without your place left out
            places.append(place)
    if not places:
        return {}
    return {
        "races": counted(len(places), "race", "races"),
        "figures": [
            {"label": tr("Wins"), "value": str(sum(place == 1 for place in places))},
            {"label": tr("Podiums"), "value": str(sum(place <= 3 for place in places))},
            {"label": tr("Avg. Finish"), "value": f"P{sum(places) / len(places):.1f}"},
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
        self._results: list[rs.OnlineResult] = []
        self._page = 0  # pages read
        self._end = False  # every race read
        self._loading = False
        self._error = ""
        self._selected = ""  # key of the race picked
        self._shown = False
        self._note = ""  # told under the race picked ("no results file...")
        self._laps_asked: set[str] = set()  # races whose laps were asked
        self._laps_reading = ""  # race whose laps are read (job "laps": a newer one drops its answer)
        self._values: dict[str, Any] = {"rows": [], "selected": {}, "chart": {}, "summary": {}}

    # Properties
    @Property(list, notify=listChanged)
    def rows(self) -> list:
        """Races read (see schedule_view.result_view, classification left out of the list)"""
        return self._values["rows"]

    @Property(dict, notify=listChanged)
    def summary(self) -> dict:
        """Races read: count & figures (wins, podiums, average finish)"""
        return self._values["summary"]

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
        """loading, error, more (pages left), selectedKey, note"""
        return {"loading": self._loading, "error": self._error, "more": not self._end, "selectedKey": self._selected,
                "note": self._note}

    # Page state
    def page_shown(self):
        pass

    def page_hidden(self):
        pass

    def release_resources(self):
        pass

    @Slot(bool)
    def list_shown(self, shown: bool):
        """Online list shown on the page: first page read once, laps of the race picked read (list shown only)"""
        self._shown = shown
        if shown and not self._results and not self._end:
            self.more()
            return
        result = self.result_of(self._selected) if shown else None
        if result is not None and not any(row.lap_positions for row in result.rows):
            self.read_laps(result)

    # Reading
    @Slot()
    def more(self):
        """Next page of your online races"""
        if self._loading or self._end:
            return
        page = self._page + 1
        self._loading, self._error = True, ""
        self.stateChanged.emit()
        self.jobs.run("online results", lambda: info.read_results(page), lambda found: self.read_done(page, found),
                      self.read_failed, key="results")

    @Slot()
    def readAgain(self):
        """Races read again from the first page (new races driven meanwhile)"""
        self.jobs.cancel("results")  # page read meanwhile (More Results) dropped
        self._loading = False
        self._results, self._page, self._end = [], 0, False
        self._laps_asked.clear()  # races read again come without their laps
        self._note = ""
        self.publish()
        self.more()

    def read_done(self, page: int, found: list | None):
        self._loading = False
        if found is None:
            self._error = tr("Results files of the game not read: try again in a moment.")
        else:
            known = {result.path for result in self._results}
            for result in found:  # once each (pages move while new races are added)
                if result.path not in known:
                    known.add(result.path)
                    self._results.append(result)
            self._page = page
            # end of the list told by the files of the page (a file may be unreadable)
            answered = found.answered if isinstance(found, info.ResultsPage) else len(found)
            self._end = answered < info.RESULTS_TAKE
            if not self._selected and self._results:
                self._selected = result_key(self._results[0])
        self.publish()

    def read_failed(self, error: BaseException):
        logger.warning("ONLINE RESULTS: not read: %s", error)
        self.read_done(0, None)

    # Publishing
    def view_of(self, result: rs.OnlineResult) -> dict:
        def logo(track: str) -> str:
            return self.logos.track(track) if track else ""

        player = info.player_name()
        return result_view(result, info.state().schedule, player, time.time(), logo)

    def publish(self):
        rows = []
        for result in self._results:
            shown = self.view_of(result)
            shown.pop("rows")
            rows.append(shown)
        self._values["rows"] = rows
        self._values["summary"] = summary_of(self._results, info.player_name())
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
        key = result_key(result)
        if not self._shown or key in self._laps_asked:
            return
        if self._laps_reading:  # its answer dropped below: asked again once picked again
            self._laps_asked.discard(self._laps_reading)
        self._laps_asked.add(key)
        self._laps_reading = key
        self.jobs.run("race laps", lambda: info.read_result(result.path),
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
        self.laps_read_over(result_key(old), found is None)
        if found is None or not any(row.lap_positions for row in found.rows):
            return
        for index, result in enumerate(self._results):
            if result is old:
                self._results[index] = found._replace(time=old.time or found.time)
        if self._selected == result_key(old):
            self.publish_selected()

    def result_of(self, key: str) -> rs.OnlineResult | None:
        for result in self._results:
            if result_key(result) == key:
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
        if os.path.isfile(result.path):
            self.sessionWanted.emit(result.path)
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
        name = strip_invalid_char(result.title) or "race"
        path, _ = QFileDialog.getSaveFileName(parent, tr("Export Classification"), f"{name}.csv", tr("CSV (*.csv)"))
        if not path:
            return
        rows = [[str(row.position or ""), str(row.class_position or ""), row.vehicle_class, row.number, row.name,
                 row.team, row.car, f"{row.best_lap:.3f}" if row.best_lap else "", str(row.laps or ""), row.status]
                for row in result.rows]
        header = ["Position", "Class Position", "Class", "Number", "Driver", "Team", "Car", "Best Lap", "Laps",
                  "Status"]
        try:
            with open(path, "w", encoding="utf-8", newline="") as file:
                file.write(csv_text(header, rows))
        except OSError as error:
            logger.warning("ONLINE RESULTS: classification not exported: %s", error)
