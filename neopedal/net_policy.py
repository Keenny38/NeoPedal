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
Durations, counts and limits of the requests the app sends to online services and of the files it watches, in one
place

Every value says why it is what it is: the rhythm at which the data changes, or a limit of the service. The modules
keep their own names for these values (`READ_SECONDS` of race_schedule_info...), set from here. Plain numbers only,
no import: safe to import from anywhere. RaceOS (online service of the game, read with the game ticket) is never
asked: a developer of Le Mans Ultimate said third-party apps must not call it (2026-11-04).
"""

# Daily races of the public page of RaceControl (race_schedule_info.py, process/public_schedule.py)
SCHEDULE_PUBLIC_SECONDS = 3600.0  # the page lists the starts of the next 9 hours or so: an hour old still shows every race to come
SCHEDULE_RETRY_SECONDS = 300.0  # page not read (offline, error): tried again this late
SCHEDULE_FORCE_SECONDS = 300.0  # Read Again asks the page at most this often (a press sooner shows the last read)
SCHEDULE_GAME_LISTS_AGE = 3600.0  # tracks of the game (local Rest API) asked again this late (owned DLC)

# Upcoming Races page (ui/quick/schedule_backend.py)
PAGE_PERSONAL_SECONDS = 300.0  # driver stats files read again this often while the page shows

# Driver & Safety Rank of the player (process/driver_ranks.py, game menu file)
RANKS_CHECK_SECONDS = 5.0  # storage file modification time checked this often
RANKS_LOCATE_SECONDS = 60.0  # game folder & player looked for again this often while not found (game installed)
RANKS_LOCATE_FOUND_SECONDS = 600.0  # looked for again this often once found (game moved, other Steam user)

# Community lap times sheet (ui/quick/stats_common.py)
SHEET_REFERENCE_MAX_AGE = 24 * 3600  # seconds before cached lap time reference is downloaded again
SHEET_REFERENCE_RETRY_SECONDS = 3600  # seconds after a failed download before the next page opening asks again (3 attempts each: a page opened often while the service is down or rate limiting sent 3 requests every time)
