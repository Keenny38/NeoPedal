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
Driver stats viewer part (StatsEdits, mixin of DriverStatsBackend): Edits of stats & session history (worker thread, undo & redo), backups, lap times completed from results, context menu
"""

from __future__ import annotations

import copy
import html
import logging
import os
import time
from collections.abc import Callable, Iterable
from functools import partial
from typing import Any

from PySide6.QtCore import (
    Property,
    QDateTime,
    QLocale,
    QStandardPaths,
    Slot,
)
from PySide6.QtWidgets import QFileDialog

from ... import calculation as calc
from ...const_common import MAX_SECONDS
from ...i18n import tr, trm
from ...process import mysimrace_import, results_import
from ...process import results_index as ri
from ...setting import cfg
from ...userfile.driver_history import (
    SESSION_GROUPS,
    SessionRecord,
    checkpoint_times,
    load_history,
    replace_records,
    restored_history,
)
from ...userfile.driver_stats import (
    STATS_LOCK,
    DriverStats,
    backup_stats_file,
    is_invalid_stats_file,
    list_stats_backups,
    load_stats_json_file,
    merge_stats_entry,
    merge_stats_since,
    redo_stats_entry,
    save_stats_json_file,
    set_stats_entry,
    stats_entry,
    stats_since,
    validate_stats_file,
)
from . import dialogs
from .formatting import date_locale, format_date
from .stats_common import (
    HEADER_KEYS,
    MAX_FIX_LINES,
    MAX_UNDO,
    ROLLBACK_ATTEMPTS,
    ROLLBACK_DELAY,
    clean_up_stats,
    read_backup_files,
    valid_laptime,
)
from .stats_core import StatsCore
from .stats_io import (
    StatsEdit,
    StatsHost,
    StatsJob,
)

logger = logging.getLogger(__name__)
SESSION_QUALIFYING = 2  # history record sessions with their own best lap time (see results_import.HISTORY_SESSION)
SESSION_RACE = 4


def restored_stats(backup: dict, current: dict, records: list[SessionRecord], created: float) -> dict:
    """Stats of a backup with the stints recorded after it counted again (their history records are kept, see
    restored_history): counters recorded since for their track & car, best lap times of their records (never a
    lap time the backup is restored to get rid of)"""
    newer = [record for record in records if record.time > created]
    if not newer:
        return copy.deepcopy(backup)
    driven = {(record.track, record.vehicle) for record in newer}
    since: dict = {}
    for track, vehicles in stats_since(current, backup).items():
        for vehicle, stats in vehicles.items():
            counters = {key: value for key, value in stats.items() if not DriverStats.is_lap_time(key)}
            if (track, vehicle) in driven and counters:
                since.setdefault(track, {})[vehicle] = counters
    for record in newer:
        if not 0 < record.best < MAX_SECONDS:
            continue
        laps = {"pb": record.best}
        if record.session == SESSION_QUALIFYING:
            laps["qb"] = record.best
        elif record.session == SESSION_RACE:
            laps["rb"] = record.best
        stats = since.setdefault(record.track, {}).setdefault(record.vehicle, {})
        for key, laptime in laps.items():
            if laptime < stats.get(key, MAX_SECONDS):
                stats[key] = laptime
    return merge_stats_since(backup, since)


MAX_FIXES_DONE = 500  # lap times completed automatically remembered (oldest forgotten)


def fix_key(fix: ri.BestLapFix) -> str:
    """Lap time of race results completed in stats: "track|vehicle|stat|lap time" """
    return f"{fix.track}|{fix.vehicle}|{fix.stat}|{fix.laptime:.3f}"


class StatsEdits(StatsHost):
    """Edits of stats & session history (worker thread, undo & redo), backups, lap times completed from results, context menu"""

    @Slot()
    def completeLapTimes(self):
        """Lap times missing or slower in stats taken from results files, at once: undone from the toast (naming
        the first changes) or with Ctrl+Z (reversible: never confirmed)"""
        self.complete_fixes(self._fixes)

    def auto_complete(self):
        """Lap times of race results missing from stats (or faster) taken at once once found, each only once (an
        undo keeps it out, Complete... of the driver card takes it again); page shown, nothing being edited"""
        if self._released or self.defer_while_hidden(self.auto_complete):
            return
        if self.editing or not self._fixes:
            return
        done = self.fixes_done()
        new = [fix for fix in self._fixes if fix_key(fix) not in done]
        if not new:
            return
        self.save_viewer_config(lap_fixes_done=sorted(done | {fix_key(fix) for fix in new})[-MAX_FIXES_DONE:])
        self.complete_fixes(new)

    def fixes_done(self) -> set[str]:
        """Lap times completed automatically once (fix_key), never again"""
        done = self.viewer_config().get("lap_fixes_done", [])
        return {str(key) for key in done} if isinstance(done, list) else set()

    def complete_fixes(self, fixes: list[ri.BestLapFix]):
        """Lap times of fixes saved (worker thread), told with Undo"""
        if not fixes or self.editing:
            return
        lines = []
        for fix in fixes[:MAX_FIX_LINES]:
            before = calc.sec2laptime_full(fix.current) if fix.current else "-"
            lines.append(f"{html.escape(fix.track)} · {html.escape(fix.vehicle)} · {tr(HEADER_KEYS[fix.stat])}: "
                         f"{before} → <b>{calc.sec2laptime_full(fix.laptime)}</b> ({format_date(fix.time)})")
        if len(fixes) > MAX_FIX_LINES:
            lines.append("…")
        done_text = tr("%1 lap time(s) completed from race results").replace("%1", str(len(fixes)))
        self.run_locked(StatsJob("edit", self.write_fixes, (tuple(fixes),), self.edit_written,
                                 ("<br>".join([done_text, *lines]),)))

    @classmethod
    def write_fixes(cls, fixes: tuple[ri.BestLapFix, ...]) -> tuple[str, StatsEdit | None]:
        """Lap times of fixes saved in stats file read again (STATS_LOCK held, worker thread), faster ones kept"""
        with STATS_LOCK:
            stats_user = cls.load_fresh_stats()
            if stats_user is None:
                return "unreadable", None
            backup_stats_file(cfg.path.config)
            before = copy.deepcopy(stats_user)
            for fix in fixes:
                vehicles = stats_user.get(fix.track)
                data = vehicles.get(fix.vehicle) if isinstance(vehicles, dict) else None
                if not isinstance(data, dict):
                    continue
                current = valid_laptime(data.get(fix.stat, 0))
                if not valid_laptime(fix.laptime):  # game clock jump of a results file: never a lap time
                    continue
                if not current or fix.laptime < current - 0.0005:
                    data[fix.stat] = fix.laptime
            if not cls.save_edit(stats_user, (), ()):
                return "unsaved", None
        return "saved", StatsEdit((), before, copy.deepcopy(stats_user))

    @Slot()
    def importResults(self):
        """Sessions of results files never recorded added to stats & session history, at once: undone from the
        toast or with Ctrl+Z (reversible: never confirmed)"""
        candidates = self._imports
        if not candidates or self.editing:
            return
        setting = cfg.user.setting.get("module_stats", {})
        podium_by_class = bool(setting.get("enable_podium_by_class", True)) if isinstance(setting, dict) else True
        self.run_locked(StatsJob("edit", self.write_import, (tuple(candidates), self.classification(),
                                                             dict(cfg.user.brands), podium_by_class),
                                 self.import_written))

    @classmethod
    def write_import(cls, candidates: tuple[ri.ResultSummary, ...], classification: str, brands: dict[str, str],
                     podium_by_class: bool) -> tuple[str, StatsEdit | None, int]:
        """Sessions of candidates read from results files, added to stats & history read again (STATS_LOCK held,
        worker thread): sessions recorded since left out

        Returns:
            Outcome as write_edit ("saved", "history", "unsaved", "unreadable", "none": nothing left to add),
            edit to undo, sessions added.
        """
        sessions = results_import.read_sessions(candidates, classification, brands, podium_by_class)
        with STATS_LOCK:
            stats_user = cls.load_fresh_stats()
            if stats_user is None:
                return "unreadable", None, 0
            try:
                history = load_history(cfg.path.config, strict=True)
            except OSError:  # never rewritten from empty history
                return "unreadable", None, 0
            left = {summary.path for summary in results_import.import_candidates(
                candidates, history, (), checkpoint_times(cfg.path.config))}
            before = copy.deepcopy(stats_user)
            added = results_import.apply_import(stats_user, history,
                                                [session for session in sessions if session.path in left])
            if not added:
                return "none", None, 0
            backup_stats_file(cfg.path.config, with_history=True)
            records = tuple(session.record for session in added)
            saved = cls.save_edit(stats_user, (), records, history)
            if saved is False:
                return "unsaved", None, 0
            if saved is None:
                return "history", StatsEdit((), None, None, (), records, history_only=True), len(added)
        return "saved", StatsEdit((), before, copy.deepcopy(stats_user), (), records), len(added)

    def import_written(self, result: tuple[str, StatsEdit | None, int]):
        """Import saved (UI thread): as an edit, told how many sessions were added"""
        outcome, edit, count = result
        if outcome == "none":
            self.reload_stats()  # sessions recorded since: none left to import
            return
        self.edit_written((outcome, edit), trm(f"{count} session(s) imported from game results"))

    @Slot()
    def cleanUpStats(self):
        """Empty cars removed (with their history) & impossible lap times reset, every track, at once: undone from
        the toast or with Ctrl+Z (reversible: never confirmed)"""
        if self.editing:
            return
        self.run_locked(StatsJob("edit", self.write_clean_up, (), self.clean_up_written))

    @classmethod
    def write_clean_up(cls) -> tuple[str, StatsEdit | None, int]:
        """Clean up applied to stats file read again (STATS_LOCK held, worker thread)

        Returns:
            Outcome as write_import ("none": nothing to clean up), edit to undo, cars removed & lap times reset.
        """
        with STATS_LOCK:
            stats_user = cls.load_fresh_stats()
            if stats_user is None:
                return "unreadable", None, 0
            try:
                history = load_history(cfg.path.config, strict=True)
            except OSError:  # never rewritten from empty history
                return "unreadable", None, 0
            before = copy.deepcopy(stats_user)
            combos, resets = clean_up_stats(stats_user)
            if not combos and not resets:
                return "none", None, 0
            backup_stats_file(cfg.path.config, with_history=True)
            removed = tuple(record for record in history if (record.track, record.vehicle) in combos)
            saved = cls.save_edit(stats_user, removed, (), history)
            if saved is False:
                return "unsaved", None, 0
            if saved is None:
                return "history", StatsEdit((), None, None, removed, (), history_only=True), len(combos) + resets
        return "saved", StatsEdit((), before, copy.deepcopy(stats_user), removed, ()), len(combos) + resets

    def clean_up_written(self, result: tuple[str, StatsEdit | None, int]):
        """Clean up saved (UI thread): as an edit, told how many changes"""
        outcome, edit, count = result
        if outcome == "none":
            self.toast(tr("Nothing to clean up: no empty car, no impossible lap time"))
            return
        self.edit_written((outcome, edit), trm(f"{count} empty car(s) or impossible lap time(s) cleaned up"))

    @Slot()
    def importMysimrace(self):
        """Sessions of a mysimrace.com data export never recorded added to stats & session history, at once:
        undone from the toast or with Ctrl+Z (reversible: never confirmed)"""
        if self.editing:
            return
        folder = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        filename, _ = QFileDialog.getOpenFileName(self._window, tr("Import From mysimrace…"),
                                                  folder or os.path.expanduser("~"), "JSON (*.json)")
        if not filename:
            return
        brands = tuple(str(brand) for brand in cfg.user.brands.values())
        self.run_locked(StatsJob("edit", self.write_mysimrace, (filename, tuple(self.results), self.classification(),
                                                                brands),
                                 self.mysimrace_written))

    @classmethod
    def write_mysimrace(cls, path: str, summaries: tuple[ri.ResultSummary, ...], classification: str,
                        brands: tuple[str, ...]) -> tuple[str, StatsEdit | None, int]:
        """Sessions of a mysimrace export added to stats & history read again (STATS_LOCK held, worker thread):
        sessions recorded, or in results files (imported from results instead), left out

        Returns:
            Outcome as write_import, or "invalid" (not a mysimrace export), edit to undo, sessions added.
        """
        try:
            laps, _ = mysimrace_import.read_export(path)
        except (OSError, ValueError) as error:
            logger.info("DRIVER STATS: %s not imported: %s", os.path.basename(path), error)
            return "invalid", None, 0
        with STATS_LOCK:
            stats_user = cls.load_fresh_stats()
            if stats_user is None:
                return "unreadable", None, 0
            try:
                history = load_history(cfg.path.config, strict=True)
            except OSError:  # never rewritten from empty history
                return "unreadable", None, 0
            found = mysimrace_import.export_sessions(laps, path, stats_user, history, summaries, classification,
                                                     brands)
            before = copy.deepcopy(stats_user)
            added = results_import.apply_import(stats_user, history, found.sessions)
            if not added:
                return "none", None, 0
            backup_stats_file(cfg.path.config, with_history=True)
            records = tuple(session.record for session in added)
            saved = cls.save_edit(stats_user, (), records, history)
            if saved is False:
                return "unsaved", None, 0
            if saved is None:
                return "history", StatsEdit((), None, None, (), records, history_only=True), len(added)
        return "saved", StatsEdit((), before, copy.deepcopy(stats_user), (), records), len(added)

    def mysimrace_written(self, result: tuple[str, StatsEdit | None, int]):
        """mysimrace import saved (UI thread): as an edit, told how many sessions were added, or why none"""
        outcome, edit, count = result
        if self._released:
            return
        if outcome == "invalid":
            self.toast(tr("This file is not a mysimrace data export with laps of Le Mans Ultimate"))
        elif outcome == "none":
            self.reload_stats()
            self.toast(tr("Nothing to import: the sessions of this file are already in your stats"))
        else:
            self.edit_written((outcome, edit), trm(f"{count} session(s) imported from mysimrace"))

    @Slot()
    def deleteSelected(self):
        """Delete key: remove selected vehicle (All Tracks: delete selected track), undone from the toast"""
        if self.selected_stats_key:
            self.removeVehicle()
        elif self._selected["tracks"]:
            self.deleteTrack(self._selected["tracks"])

    # Edits: applied to stats file read again, undo & redo
    def ask(self, message: str, on_yes: Callable[[], object], action_text: str = ""):
        """Confirmation in the page (message translated by message rules), on_yes() once confirmed: later, the
        page keeps running meanwhile (check again what may have changed)"""
        dialogs.confirm(self._window, tr("Confirm"), trm(message), action_text or tr("Confirm"),
                        lambda chosen: chosen and not self._released and on_yes())

    def warning(self, text: str):
        dialogs.alert(self._window, tr("Error"), text)

    @staticmethod
    def load_fresh_stats() -> dict | None:
        """Stats file as saved now (stats module may have saved since loaded), None if invalid"""
        stats_user = load_stats_json_file(filepath=cfg.path.config)
        if stats_user is None:
            return None
        return validate_stats_file(stats_user)

    def stats_unreadable(self):
        self.warning(tr("Unable to read stats file."))

    def stats_unsaved(self):
        self.warning(tr("Unable to save stats file."))

    def stats_changed(self):
        self.warning(tr("Lap time changed since shown (a faster lap was saved): not reset."))
        self.reload_stats()

    def stats_unsaved_history_changed(self):
        self.warning(tr("Unable to save stats file. Session history was changed anyway, use Undo to revert it."))

    @staticmethod
    def save_edit(stats_user: dict, removed: Iterable[SessionRecord], added: Iterable[SessionRecord],
                  history: list[SessionRecord] | None = None) -> bool | None:
        """Save edited stats & history change (STATS_LOCK held, worker thread)

        History changed first: a change (records removed or added once) undone safely if stats not saved,
        tried again a few times.

        Args:
            history: records of history file loaded already (STATS_LOCK held since), else file read.

        Returns:
            True if saved, False if not saved (both files kept),
            None if stats not saved and history change could not be undone (history changed only).
        """
        removed, added = tuple(removed), tuple(added)
        try:
            written = replace_records(cfg.path.config, removed, added, history)
        except OSError:  # history unreadable (never rewritten as empty) or not saved
            return False
        if save_stats_json_file(stats_user=stats_user, filepath=cfg.path.config):
            return True
        for attempt in range(ROLLBACK_ATTEMPTS):
            if attempt:
                time.sleep(ROLLBACK_DELAY)  # worker thread: page not held up
            try:
                replace_records(cfg.path.config, added, removed, written)  # history change undone
                return False
            except OSError as error:
                logger.warning("STATS: history change not undone (attempt %s): %s", attempt + 1, error)
        return None

    def edit_stats(self, path: tuple[str, ...], value: Any,
                   history_change: Callable[[list[SessionRecord]], tuple[list, list]] | None = None,
                   done_text: str = "", expected: float = 0.0) -> bool:
        """Set stats at path (None removes it, empty path: whole file), history changed, undo recorded

        Saved on worker thread after edits asked before (see run_locked), page updated once saved.

        Args:
            history_change: history records -> (records removed, records added), run on worker thread.
            done_text: toast once saved, with Undo (translated, names escaped).
            expected: lap time shown at path (lap time reset), not changed if file holds another one now.

        Returns:
            True if done now (never: saved in background).
        """
        return self.run_locked(StatsJob("edit", self.write_edit, (path, value, history_change, expected),
                                        self.edit_written, (done_text,)))

    @classmethod
    def write_edit(cls, path: tuple[str, ...], value: Any,
                   history_change: Callable[[list[SessionRecord]], tuple[list, list]] | None,
                   expected: float = 0.0) -> tuple[str, StatsEdit | None]:
        """Edit applied to stats file read again (STATS_LOCK held, worker thread), see edit_stats

        Returns:
            Outcome ("saved", "history" changed only, "unsaved", "unreadable", "changed": lap time saved since
            shown, "restored": whole file written over a damaged one, kept as backup, no undo), edit to undo.
        """
        with STATS_LOCK:  # held already (run_locked), reentrant
            stats_user = cls.load_fresh_stats()
            damaged = False
            if stats_user is None:
                # Damaged file (not only locked) replaced by a backup: copied as backup first, then restored
                damaged = not path and is_invalid_stats_file(cfg.path.config)
                if not damaged:
                    return "unreadable", None
                stats_user = {}
            if expected and abs(valid_laptime(stats_entry(stats_user, path) or 0) - expected) > 0.0005:
                return "changed", None  # stats module saved a new lap time since shown: never reset unseen
            backup_stats_file(cfg.path.config, with_history=history_change is not None)
            before = stats_entry(stats_user, path) if path else copy.deepcopy(stats_user)
            history = None
            if history_change is not None or (not path and callable(value)):
                try:
                    history = load_history(cfg.path.config, strict=True)
                except OSError:  # never rewritten from empty history
                    return "unreadable", None
            if path:
                set_stats_entry(stats_user, path, value)
            elif callable(value):  # whole file made from stats & history read now (backup restored)
                value = value(stats_user, history)
                stats_user = copy.deepcopy(value)
            else:
                stats_user = copy.deepcopy(value)
            removed: tuple = ()
            added: tuple = ()
            if history_change is not None and history is not None:
                removed_list, added_list = history_change(history)
                removed, added = tuple(removed_list), tuple(added_list)
            saved = cls.save_edit(stats_user, removed, added, history)
            if saved is False:  # not saved: no undo recorded
                return "unsaved", None
            if saved is None:  # history changed only: its undo recorded
                return "history", StatsEdit(path, None, None, removed, added, history_only=True)
        if damaged:  # damaged file kept as backup, nothing to undo to
            return "restored", None
        return "saved", StatsEdit(path, before, copy.deepcopy(value), removed, added)

    def edit_written(self, result: tuple[str, StatsEdit | None], done_text: str = ""):
        """Edit saved (UI thread): undo recorded & page reloaded, told by a toast with Undo (Ctrl+Z too), or warned"""
        outcome, edit = result
        self._backups = None  # listed again (backup made before edit)
        if outcome == "unreadable":
            self.stats_unreadable()
        elif outcome == "unsaved":
            self.stats_unsaved()
        elif outcome == "changed":
            self.stats_changed()
        elif outcome == "restored":
            self.reload_stats()
            if done_text and not self._released:
                from ..toast import show_toast

                show_toast(self._window, done_text)
        elif edit is not None:
            self.edit_done(edit)
            if outcome == "history":
                self.stats_unsaved_history_changed()
            elif done_text and not self._released:
                self.toast_undo(done_text)

    def toast_undo(self, text: str):
        """Edit saved without confirmation (reversible): page toast with Undo, as Ctrl+Z"""
        from ..toast import show_toast

        show_toast(self._window, text, action_text=tr("Undo"),
                   action=lambda: None if self._released else self.undo())

    def edit_done(self, edit: StatsEdit):
        """Edit saved: undo recorded, page reloaded"""
        self._edits_undo.append(edit)
        del self._edits_undo[:-MAX_UNDO]
        self._edits_redo.clear()
        self.reload_stats()

    @classmethod
    def apply_edit(cls, edit: StatsEdit, undo: bool) -> tuple[str, StatsEdit | None]:
        """Apply edit again (redo) or its reverse (undo, stats recorded since kept) on stats file read again

        Called with STATS_LOCK held (worker thread, see run_locked).

        Returns:
            Outcome as write_edit ("saved", "history" changed only, "unsaved", "unreadable"), and for "history"
            the history change made (its own undo, stats not saved).
        """
        with STATS_LOCK:
            if edit.history_only:
                try:
                    if undo:
                        replace_records(cfg.path.config, edit.history_after, edit.history_before)
                    else:
                        replace_records(cfg.path.config, edit.history_before, edit.history_after)
                except OSError:
                    return "unreadable", None
                return "saved", None
            stats_user = cls.load_fresh_stats()
            if stats_user is None:
                return "unreadable", None
            backup_stats_file(cfg.path.config, with_history=bool(edit.history_before or edit.history_after))
            if not edit.path:  # whole file (backup restored, lap times completed): stats recorded since kept
                since = stats_since(stats_user, edit.after if undo else edit.before)
                stats_user = merge_stats_since(edit.before if undo else edit.after, since)
            elif undo:
                current = stats_entry(stats_user, edit.path)
                set_stats_entry(stats_user, edit.path, merge_stats_entry(current, edit.before, edit.path))
            else:  # redo: stats recorded since kept
                current = stats_entry(stats_user, edit.path)
                set_stats_entry(stats_user, edit.path, redo_stats_entry(current, edit.before, edit.after, edit.path))
            removed, added = (edit.history_after, edit.history_before) if undo else (
                edit.history_before, edit.history_after)
            saved = cls.save_edit(stats_user, removed, added)
            if saved is None:  # stats not saved, history changed anyway: that change undone on its own
                return "history", StatsEdit(edit.path, None, None, removed, added, history_only=True)
            return ("saved" if saved else "unsaved"), None

    @Slot()
    def undo(self):
        """Undo last edit (saved in background), not while an edit is being saved (not in undo stack yet)"""
        if not self._edits_undo or self.editing:
            return
        edit = self._edits_undo.pop()
        self.run_locked(StatsJob("edit", self.apply_edit, (edit, True), self.edit_applied, (edit, True)))

    @Slot()
    def redo(self):
        """Redo last undone edit (saved in background), not while an edit is being saved"""
        if not self._edits_redo or self.editing:
            return
        edit = self._edits_redo.pop()
        self.run_locked(StatsJob("edit", self.apply_edit, (edit, False), self.edit_applied, (edit, False)))

    def edit_applied(self, result: tuple[str, StatsEdit | None], edit: StatsEdit, undo: bool):
        """Undo or redo saved (UI thread): moved to other stack (back to its stack if not saved, told why), page
        reloaded. History changed without stats: edit back to its stack, the history change undone by Ctrl+Z."""
        outcome, history_edit = result
        self._backups = None  # listed again (backup made before undo & redo)
        if outcome == "saved":
            (self._edits_redo if undo else self._edits_undo).append(edit)
        else:
            (self._edits_undo if undo else self._edits_redo).append(edit)
            if outcome == "history" and history_edit is not None:
                self._edits_undo.append(history_edit)
                del self._edits_undo[:-MAX_UNDO]
                self.stats_unsaved_history_changed()
            elif outcome == "unsaved":
                self.stats_unsaved()
            else:
                self.stats_unreadable()
        if undo:
            self.reload_stats(select=edit.path[0] if edit.path else None)
        else:
            self.reload_stats(select=edit.path[0] if len(edit.path) > 1 else None)

    @Property(bool, notify=StatsCore.editsChanged)
    def canUndo(self) -> bool:
        return bool(self._edits_undo)

    @Property(bool, notify=StatsCore.editsChanged)
    def canRedo(self) -> bool:
        return bool(self._edits_redo)

    @Property(bool, notify=StatsCore.tracksChanged)
    def canDelete(self) -> bool:
        return bool(self.selected_stats_key)

    @Slot(str)
    def deleteTrack(self, track: str = ""):
        """Delete stats of track (empty: selected track) & its session history at once: undone from the toast or
        with Ctrl+Z (reversible: never confirmed)"""
        if self.editing:  # stats shown not up to date yet
            return
        track = track or self.selected_stats_key
        if not track or track not in self.stats_temp:
            self.warning(tr("No data found."))
            return
        self.edit_stats((track,), None, lambda records: (
            [record for record in records if record.track == track], []),
            tr("Stats of %1 deleted").replace("%1", f"<b>{html.escape(track)}</b>"))

    @Slot()
    def removeVehicle(self):
        """Remove selected vehicle stats & its session history at once (undone from the toast or with Ctrl+Z)"""
        if self.editing:
            return
        vehicle = self._selected["vehicles"] if self.selected_stats_key else ""
        if not vehicle:  # nothing selected: action disabled, nothing to tell
            return
        if vehicle not in self.selected_stats_dict:
            self.warning(tr("No data found."))
            return
        track = self.selected_stats_key
        self.edit_stats((track, vehicle), None, lambda records: (
            [record for record in records if record.track == track and record.vehicle == vehicle], []),
            tr("Stats of %1 removed").replace("%1", f"<b>{html.escape(vehicle)}</b>"))

    @Slot(str, str)
    def resetLapTime(self, vehicle: str, column: str):
        """Reset lap time of vehicle, its session bests in history too (progression)"""
        if not DriverStats.is_lap_time(column) or not self.selected_stats_key or self.editing:
            return
        data = self.selected_stats_dict.get(vehicle, {})
        laptime = valid_laptime(data.get(column, 0))
        if not laptime:
            self.warning(tr("No lap time found."))
            return
        self.reset_lap_time(self.selected_stats_key, vehicle, column, laptime)

    def reset_lap_time(self, track: str, vehicle: str, column: str, laptime: float):
        """Lap time of vehicle reset at once (undone from the toast or with Ctrl+Z), its session bests in history
        too"""
        if self.editing or track != self.selected_stats_key:  # other track shown meanwhile: edits apply to it
            return
        sessions = {"pb": (), "qb": SESSION_GROUPS[2], "rb": SESSION_GROUPS[3]}[column]

        def reset_history(records: list[SessionRecord]) -> tuple[list, list]:
            reset = [record for record in records
                     if record.track == track and record.vehicle == vehicle and abs(record.best - laptime) < 0.0005
                     and (not sessions or record.session in sessions)]
            return reset, [record._replace(best=0.0) for record in reset]

        done_text = (tr("Lap time %1 reset for %2").replace("%1", f"<b>{calc.sec2laptime_full(laptime)}</b>")
                     .replace("%2", f"<b>{html.escape(vehicle)}</b>"))
        self.edit_stats((track, vehicle, column), DriverStats.__dict__[column], reset_history, done_text, laptime)

    # Backups
    @Property(list, notify=StatsCore.editsChanged)
    def backups(self) -> list[dict]:
        return self.cached_backups()

    def cached_backups(self) -> list[dict]:
        """Automatic backups, listed once (again after an edit makes one), not on every table refresh"""
        if self._backups is None:
            self._backups = self.backup_list()
        return self._backups

    @staticmethod
    def backup_list() -> list[dict]:
        """Automatic backups made before edits, newest first"""
        return [{"name": name, "date": QDateTime.fromSecsSinceEpoch(int(created)).toString(
                    date_locale().dateTimeFormat(QLocale.FormatType.ShortFormat))}
                for name, created in list_stats_backups(cfg.path.config)]

    @Slot(str)
    def restoreBackup(self, name: str):
        """Stats file as saved in backup, read in background then restored as an edit: undone from the toast or
        with Ctrl+Z (stats before restore; reversible: never confirmed)"""
        if self.editing:
            return
        date = next((entry["date"] for entry in self.cached_backups() if entry["name"] == name), name)
        created = next((created for backup, created in list_stats_backups(cfg.path.config) if backup == name), 0.0)
        self.jobs.run("stats backup", partial(read_backup_files, cfg.path.config, name),
                      partial(self.backup_read, date=date, created=created), self.backup_failed, key="backup")

    def backup_read(self, backup: tuple[dict | None, list[SessionRecord] | None], date: str = "",
                    created: float = 0.0):
        """Backup read (checked): restored as an edit, with the session history copied with it (records saved
        since kept)"""
        if self._released or self.editing:
            return
        stats_backup, history_backup = backup
        if stats_backup is None:
            self.warning(tr("Unable to read stats file."))
            return
        history_change = None
        if history_backup is not None:
            history_change = partial(restored_history, backup=history_backup, since=created)
        # Stints recorded after the backup: their history records kept, their stats counted again
        stats = partial(restored_stats, stats_backup, created=created)
        self.edit_stats((), lambda current, records: stats(current, records or []), history_change, done_text=tr("Stats restored from the backup of %1").replace(
            "%1", f"<b>{html.escape(date)}</b>"))

    def backup_failed(self, error: BaseException):
        logger.warning("DRIVER STATS: backup not read", exc_info=(type(error), error, error.__traceback__))
        if not self._released:
            self.warning(tr("Unable to read stats file."))

    # Context menu
    @Slot(str, str, result=list)
    def rowActions(self, key: str, column: str) -> list[dict]:
        """Right click menu entries of row & column: id, text, enabled"""
        actions = []
        editable = not self.editing  # edit being saved: stats shown not up to date yet
        if not self.selected_stats_key:
            actions += [{"id": "show", "text": tr("Show Track"), "enabled": True},
                        {"id": "delete", "text": tr("Delete Track"), "enabled": editable}]
        elif column == "vehicle":
            actions.append({"id": "remove", "text": tr("Remove Car"), "enabled": editable})
        elif DriverStats.is_lap_time(column):
            laptime = valid_laptime(self.selected_stats_dict.get(key, {}).get(column, 0))
            actions.append({"id": "reset", "text": tr("Reset Lap Time"), "enabled": bool(laptime) and editable})
        actions.append({"id": "laps", "text": tr("Open Recorded Laps"), "enabled": bool(self.lap_folder(key))})
        return actions

    @Slot(str, str, str)
    def runAction(self, action: str, key: str, column: str):
        self.selectRow(key)
        if action == "show":
            self.openRow(key)
        elif action == "delete":
            self.deleteTrack(key)
        elif action == "remove":
            self.removeVehicle()
        elif action == "reset":
            self.resetLapTime(key, column)
        elif action == "laps":
            self.openLapViewer()
