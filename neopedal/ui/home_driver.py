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
Driver card of Home page: game profile, Driver Rank & Safety Rank (progress, change since previous rank, rank over
time), badge, race record of results files, other game accounts of this computer

Results files & profile read on a worker thread (read_driver_data), card made on the UI thread (driver_card).
Same figures & rows as the driver card of Driver Stats Viewer.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import NamedTuple

from ..i18n import tr, trm
from ..process import driver_ranks as dr
from ..process import results_file as rf
from ..process import results_index as ri
from ..process.player_profile import PlayerProfile, player_profile
from ..setting import cfg
from .quick.formatting import country_name, format_date, localized_number

STALE_RANKS_DAYS = 7  # remembered ranks older than this: note shown as old (clock, warning color)
CHART_MIN_SPAN = 0.25  # rank over time zoomed on its values, at least a quarter of a tier high


class DriverData(NamedTuple):
    """Game profile & race record of results files (worker thread)"""

    profile: PlayerProfile | None
    record: ri.RaceRecord
    last_driver: str  # player name of newest results file, "" if none


def read_driver_data() -> DriverData:
    """Profile & race record of results folders of race results page (worker thread)

    Results files read only when new or changed (summaries cache in config folder, kept across restarts).
    Driver card rows module imported here too (not on the UI thread when ranks come).
    """
    from .quick import stats_common  # noqa: F401

    folders = rf.results_folders(rf.chosen_results_folder(cfg.path.config))
    summaries = ri.read_summaries(folders, cfg.path.config)
    return DriverData(player_profile(folders), ri.race_record(summaries),
                      summaries[-1].driver if summaries else "")


def record_figures(record: ri.RaceRecord) -> list[dict]:
    """Race record tiles: label & value, same labels as driver card of Driver Stats Viewer"""
    figures = [
        {"label": tr("Races"), "value": str(record.races)},
        {"label": tr("Wins"), "value": str(record.wins)},
        {"label": tr("Podiums"), "value": str(record.podiums)},
    ]
    if record.average_finish:
        figures.append({"label": tr("Avg. Finish"), "value": f"P{localized_number(record.average_finish, 1)}"})
    figures.append({"label": tr("Clean Races"), "value": f"{record.clean}/{record.races}"})
    return figures


def next_rank_text(rank: dr.Rank) -> str:
    """Rank & tier after this one ("Silver 3", "Gold 1"), "" at the top rank or rank unknown"""
    try:
        index = dr.RANK_ORDER.index(rank.name.capitalize())
    except ValueError:
        return ""
    if 0 < rank.tier < 3:
        return f"{rank.name} {rank.tier + 1}"
    return f"{dr.RANK_ORDER[index + 1]} 1" if index + 1 < len(dr.RANK_ORDER) else ""


def rank_tip(rank: dr.Rank, change: str) -> str:
    """Tooltip of a rank row: what the progress & change percents mean"""
    after = next_rank_text(rank)
    progress = max(min(rank.progress, 100), 0)
    lines = [trm(f"{progress}% of the way to {after}") if after else tr("Top rank reached")]
    if change:
        lines.append(trm(f"{change} of a tier since the previous rank seen"))
    return "\n".join(lines)


def zoomed_chart(points: list[dict]) -> list[dict]:
    """Rank over time zoomed on its values (a change of a few percents shows), empty when the rank never moved
    (flat line: nothing to tell)"""
    if len(points) < 2:
        return []
    values = [point["y"] for point in points]
    low, high = min(values), max(values)
    if high - low < 1e-9:
        return []
    span = max(high - low, CHART_MIN_SPAN / (len(dr.RANK_ORDER) * 3))
    base = (low + high - span) / 2
    return [{**point, "y": min(max((point["y"] - base) / span, 0.0), 1.0)} for point in points]


def driver_card(player: dr.DriverRanks | None, remembered: bool, updated: float,
                history: Sequence[dr.HistoryEntry], data: DriverData | None,
                others: list[dr.OtherAccount] | None = None) -> dict | None:
    """Driver card of Home page, None if nothing known (card hidden)

    Args:
        player: ranks of game menu (see RankWatcher.player), remembered: last ranks seen (game cache emptied),
            updated: when ranks were seen.
        history: rank history (change since previous rank, rank over time).
        data: profile & race record, None until read.
        others: last ranks of other game accounts of this computer.

    Returns:
        name, ranks (label, value, colors of dark & light pages, progress, change & its tone, chart points zoomed
        on their values, tooltip), badge, identity line, race record figures, note (ranks remembered) & noteStale
        (seen over a week ago), other accounts (see stats_common.other_account_rows).
    """
    from .quick.stats_common import badge_card, other_account_rows, rank_rows

    profile = data.profile if data is not None else None
    record = data.record if data is not None else None
    others = others or []
    if player is None and profile is None and not (record and record.races) and not others:
        return None
    name = (profile.name or profile.nickname) if profile is not None else ""
    name = name or (player.name if player is not None else "") or (data.last_driver if data is not None else "")
    identity = ""
    if profile is not None:
        parts = (country_name(profile.nationality), profile.team, f"#{profile.number}" if profile.number else "")
        identity = " · ".join(part for part in parts if part)
    ranks = rank_rows(player, history)
    if player is not None:  # rows in order of driver & safety ranks known
        known = [rank for rank in (player.driver, player.safety) if rank is not None]
        for row, rank in zip(ranks, known):
            row["tip"] = rank_tip(rank, row["change"])
            row["chart"] = zoomed_chart(row["chart"])
    noted = player is not None and remembered and updated > 0
    return {
        "name": name or tr("Driver"),
        "ranks": ranks,
        "badge": badge_card(player),
        "identity": identity,
        "figures": record_figures(record) if record is not None and record.races else [],
        "note": trm(f"Last ranks seen in game menu, {format_date(updated)}") if noted else "",
        "noteStale": noted and time.time() - updated > STALE_RANKS_DAYS * 86400,
        "others": other_account_rows(others),
    }
